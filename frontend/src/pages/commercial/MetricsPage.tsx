import { useCallback, useEffect, useState } from "react";
import { Typography, Select, Spin, Progress, Tooltip } from "antd";
import {
  FunnelPlotOutlined, PieChartOutlined, FieldTimeOutlined, RobotOutlined,
  CloudSyncOutlined, BarChartOutlined,
} from "@ant-design/icons";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";
import { KpiCard } from "@/components/KpiCard";
import { useNotifications } from "@/hooks/useNotifications";
import type { CampaignUpdate } from "@/hooks/useNotifications";
import { LABEL_CONFIG } from "@/components/LeadScoreBadge";
import type { ScoreLabel } from "@/components/LeadScoreBadge";

const { Text, Title } = Typography;

// ── Types (miroir de backend/app/schemas/metrics.py) ──────────────────────

interface FunnelMetrics {
  collecte: number; enrichi: number; ecarte: number; qualifie: number;
  email_genere: number; en_attente_validation: number; valide: number; rejete: number;
  synchronise_crm: number; contacte: number; repondu: number; sans_reponse: number;
  taux_qualification: number | null;
  taux_validation_humaine: number | null;
  taux_reponse: number | null;
}

interface ScoringQualityMetrics {
  score_moyen: number | null;
  confidence_moyenne: number | null;
  repartition_label: Record<string, number>;
}

interface CycleTimeMetrics {
  delai_moyen_collecte_enrichissement_h: number | null;
  delai_moyen_enrichissement_scoring_h: number | null;
  delai_moyen_scoring_redaction_h: number | null;
  delai_moyen_total_collecte_email_h: number | null;
}

interface AgentReliabilityMetrics {
  agent_name: string;
  total: number; done: number; failed: number;
  taux_succes: number | null; tentatives_moyennes: number | null; duree_moyenne_s: number | null;
}

interface CrmSyncMetrics {
  total: number; success: number; error: number; taux_succes: number | null;
}

interface MetricsResponse {
  generated_at: string;
  campaign_id: string | null;
  nb_campagnes: number;
  nb_leads_total: number;
  funnel: FunnelMetrics;
  scoring: ScoringQualityMetrics;
  cycle_time: CycleTimeMetrics;
  agents: AgentReliabilityMetrics[];
  crm_sync: CrmSyncMetrics;
}

interface CampaignOption {
  id: string;
  name?: string | null;
  codes_naf: string[];
}

// ── Formatage ──────────────────────────────────────────────────────────────

function formatPct(v: number | null): string {
  return v === null ? "—" : `${v}%`;
}

function formatHours(h: number | null): string {
  if (h === null) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 24) return `${h.toFixed(1)} h`;
  return `${(h / 24).toFixed(1)} j`;
}

function formatDuration(s: number | null): string {
  if (s === null) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

const AGENT_LABELS: Record<string, string> = {
  veille: "Veille",
  enrichissement: "Enrichissement",
  scoring: "Scoring",
  redaction: "Rédaction",
  crm: "CRM",
  pipeline: "Pipeline complet",
  pipeline_resume: "Reprise pipeline",
};

// Ordre du cycle de vie (models/lead.py::LeadStatus) — ce sont des compteurs
// de statut COURANT : un lead qui a progressé (ex. QUALIFIE → SYNCHRONISE_CRM)
// ne compte plus dans les étapes qu'il a déjà franchies (voir taux cumulatifs
// à côté, qui eux tiennent compte de cet historique).
const FUNNEL_STAGES: { key: keyof FunnelMetrics; label: string }[] = [
  { key: "collecte", label: "Collectés" },
  { key: "enrichi", label: "Enrichis" },
  { key: "qualifie", label: "Qualifiés (en attente d'email)" },
  { key: "ecarte", label: "Écartés par le scoring" },
  { key: "email_genere", label: "Emails générés" },
  { key: "en_attente_validation", label: "En attente de validation" },
  { key: "valide", label: "Validés (en attente de synchro)" },
  { key: "rejete", label: "Rejetés par le commercial" },
  { key: "synchronise_crm", label: "Synchronisés CRM" },
  { key: "contacte", label: "Contactés" },
  { key: "repondu", label: "Répondus" },
  { key: "sans_reponse", label: "Sans réponse" },
];

// ── Petits composants de présentation ──────────────────────────────────────

function SectionCard({
  icon, title, children,
}: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`,
      boxShadow: S.card, padding: "18px 20px", flex: 1, minWidth: 320,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span style={{ color: C.indigo, fontSize: 15 }}>{icon}</span>
        <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4 }}>
          {title}
        </Text>
      </div>
      {children}
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0" }}>
      <Text style={{ fontSize: 12.5, color: C.textMuted }}>{label}</Text>
      <Text style={{ fontSize: 12.5, fontWeight: 700, color: C.navy }}>{value}</Text>
    </div>
  );
}

function StageBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <Text style={{ fontSize: 12.5, color: C.text }}>{label}</Text>
        <Text style={{ fontSize: 12.5, fontWeight: 700, color: C.navy }}>{value}</Text>
      </div>
      <Progress percent={pct} showInfo={false} strokeColor={C.indigo} trailColor={C.border} size="small" />
    </div>
  );
}

function LabelBar({ label, value, max }: { label: ScoreLabel; value: number; max: number }) {
  const cfg = LABEL_CONFIG[label];
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, color: cfg.color }}>
          {cfg.icon} {cfg.label}
        </span>
        <Text style={{ fontSize: 12.5, fontWeight: 700, color: C.navy }}>{value}</Text>
      </div>
      <Progress percent={pct} showInfo={false} strokeColor={cfg.color} trailColor={C.border} size="small" />
    </div>
  );
}

function ReliabilityStackedBar({ done, failed, total }: { done: number; failed: number; total: number }) {
  if (total === 0) return <div style={{ height: 8, borderRadius: 4, background: C.border }} />;
  const donePct = (done / total) * 100;
  const failedPct = (failed / total) * 100;
  return (
    <Tooltip title={`${done} réussie${done > 1 ? "s" : ""} · ${failed} échouée${failed > 1 ? "s" : ""}`}>
      <div style={{ display: "flex", gap: 2, height: 8, borderRadius: 4, overflow: "hidden", background: C.border }}>
        {done > 0 && <div style={{ width: `${donePct}%`, background: C.green, borderRadius: 4 }} />}
        {failed > 0 && <div style={{ width: `${failedPct}%`, background: C.red, borderRadius: 4 }} />}
      </div>
    </Tooltip>
  );
}

// ── Page ────────────────────────────────────────────────────────────────

export default function MetricsPage() {
  const [campaigns, setCampaigns] = useState<CampaignOption[]>([]);
  const [campaignId, setCampaignId] = useState<string | undefined>(undefined);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<CampaignOption[]>("/campaigns/").then((res) => setCampaigns(res.data)).catch(() => {});
  }, []);

  const fetchMetrics = useCallback((id?: string) => {
    setLoading(true);
    api.get<MetricsResponse>("/metrics/", { params: id ? { campaign_id: id } : {} })
      .then((res) => setMetrics(res.data))
      .catch(() => setMetrics(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchMetrics(campaignId); }, [campaignId, fetchMetrics]);

  // Rafraîchit automatiquement quand une campagne progresse (mêmes événements
  // temps réel que le tableau de bord) — évite de devoir recharger la page
  // pour voir un nouveau lead scoré ou synchronisé.
  const handleCampaignUpdate = useCallback((update: CampaignUpdate) => {
    if (!campaignId || update.campaign_id === campaignId) fetchMetrics(campaignId);
  }, [campaignId, fetchMetrics]);

  useNotifications(undefined, handleCampaignUpdate);

  const funnelMax = metrics ? Math.max(1, ...FUNNEL_STAGES.map((s) => metrics.funnel[s.key] as number)) : 1;
  const labelMax = metrics
    ? Math.max(1, ...(["CHAUD", "TIEDE", "FROID"] as const).map((l) => metrics.scoring.repartition_label[l] ?? 0))
    : 1;

  return (
    <div className="page-root">
      {/* ── Header ─────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16, marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0, color: C.navy, fontWeight: 800 }}>
            <BarChartOutlined style={{ marginRight: 10, color: C.indigo }} />
            Performance du pipeline
          </Title>
          <Text style={{ color: C.textMuted, fontSize: 13.5 }}>
            Funnel de conversion, qualité du scoring et fiabilité des agents.
          </Text>
        </div>
        <Select
          style={{ minWidth: 240 }}
          placeholder="Toutes les campagnes"
          allowClear
          value={campaignId}
          onChange={(v) => setCampaignId(v)}
          options={campaigns.map((c) => ({
            value: c.id,
            label: c.name ?? c.codes_naf.join(", "),
          }))}
        />
      </div>

      {loading ? (
        <div style={{ padding: "80px 0", textAlign: "center" }}><Spin size="large" /></div>
      ) : !metrics || metrics.nb_leads_total === 0 ? (
        <div style={{
          background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`,
          boxShadow: S.card, padding: "56px 20px", textAlign: "center",
        }}>
          <div style={{
            width: 60, height: 60, borderRadius: "50%", background: C.bg,
            display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 16px", fontSize: 26, color: C.textFaint,
          }}>
            <BarChartOutlined />
          </div>
          <Text style={{ display: "block", color: C.text, fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
            Pas encore de données
          </Text>
          <Text style={{ display: "block", color: C.textMuted, fontSize: 13, maxWidth: 380, margin: "0 auto" }}>
            Les indicateurs apparaîtront dès qu'une campagne aura des leads collectés.
          </Text>
        </div>
      ) : (
        <>
          {/* ── KPI cards ─────────────────────────────────────── */}
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 20 }}>
            <KpiCard
              icon={<FunnelPlotOutlined />}
              label="Leads traités"
              value={metrics.nb_leads_total}
              accent={C.indigo} iconBg="#eef2ff" iconColor={C.indigo}
            />
            <KpiCard
              icon={<PieChartOutlined />}
              label="Taux de qualification"
              value={formatPct(metrics.funnel.taux_qualification)}
              accent={C.purple} iconBg={C.purpleBg} iconColor={C.purple}
            />
            <KpiCard
              icon={<CloudSyncOutlined />}
              label="Validation humaine"
              value={formatPct(metrics.funnel.taux_validation_humaine)}
              accent={C.green} iconBg={C.greenBg} iconColor={C.green}
            />
            <KpiCard
              icon={<RobotOutlined />}
              label="Succès synchro CRM"
              value={formatPct(metrics.crm_sync.taux_succes)}
              accent={C.cyan} iconBg={C.cyanBg} iconColor={C.cyan}
            />
          </div>

          {/* ── Funnel + Scoring ─────────────────────────────── */}
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 20 }}>
            <SectionCard icon={<FunnelPlotOutlined />} title="Funnel de conversion">
              {FUNNEL_STAGES.map((s) => (
                <StageBar key={s.key} label={s.label} value={metrics.funnel[s.key] as number} max={funnelMax} />
              ))}
              <Text style={{ fontSize: 11, color: C.textFaint, display: "block", marginTop: 4 }}>
                Répartition par statut courant — un lead déjà avancé (ex. synchronisé CRM) ne recompte plus dans les étapes précédentes.
              </Text>
            </SectionCard>

            <div style={{ display: "flex", flexDirection: "column", gap: 20, flex: 1, minWidth: 320 }}>
              <SectionCard icon={<PieChartOutlined />} title="Qualité du scoring">
                <StatRow label="Score moyen" value={metrics.scoring.score_moyen !== null ? metrics.scoring.score_moyen.toFixed(2) : "—"} />
                <StatRow label="Confiance moyenne" value={metrics.scoring.confidence_moyenne !== null ? `${metrics.scoring.confidence_moyenne}%` : "—"} />
                <div style={{ marginTop: 12 }}>
                  {(["CHAUD", "TIEDE", "FROID"] as const).map((l) => (
                    <LabelBar key={l} label={l} value={metrics.scoring.repartition_label[l] ?? 0} max={labelMax} />
                  ))}
                </div>
              </SectionCard>

              <SectionCard icon={<FieldTimeOutlined />} title="Délais moyens du pipeline">
                <StatRow label="Collecte → Enrichissement" value={formatHours(metrics.cycle_time.delai_moyen_collecte_enrichissement_h)} />
                <StatRow label="Enrichissement → Scoring" value={formatHours(metrics.cycle_time.delai_moyen_enrichissement_scoring_h)} />
                <StatRow label="Scoring → Rédaction" value={formatHours(metrics.cycle_time.delai_moyen_scoring_redaction_h)} />
                <StatRow label="Total (collecte → email prêt)" value={formatHours(metrics.cycle_time.delai_moyen_total_collecte_email_h)} />
              </SectionCard>
            </div>
          </div>

          {/* ── Agents + CRM ──────────────────────────────────── */}
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            <SectionCard icon={<RobotOutlined />} title="Fiabilité des agents">
              {metrics.agents.length === 0 ? (
                <Text style={{ fontSize: 12.5, color: C.textFaint }}>Aucune tâche exécutée</Text>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {metrics.agents.map((a) => (
                    <div key={a.agent_name}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <Text style={{ fontSize: 12.5, fontWeight: 600, color: C.text }}>
                          {AGENT_LABELS[a.agent_name] ?? a.agent_name}
                        </Text>
                        <Text style={{ fontSize: 12, color: C.textMuted }}>
                          {formatPct(a.taux_succes)} · {formatDuration(a.duree_moyenne_s)}
                          {a.tentatives_moyennes !== null && a.tentatives_moyennes > 1 && (
                            <> · {a.tentatives_moyennes.toFixed(1)} tentatives</>
                          )}
                        </Text>
                      </div>
                      <ReliabilityStackedBar done={a.done} failed={a.failed} total={a.total} />
                    </div>
                  ))}
                  <Text style={{ fontSize: 11, color: C.textFaint, marginTop: 2 }}>
                    Vert = tâches réussies · Rouge = tâches échouées
                  </Text>
                </div>
              )}
            </SectionCard>

            <SectionCard icon={<CloudSyncOutlined />} title="Synchronisation CRM">
              <StatRow label="Total" value={String(metrics.crm_sync.total)} />
              <StatRow label="Réussies" value={String(metrics.crm_sync.success)} />
              <StatRow label="En erreur" value={String(metrics.crm_sync.error)} />
              <div style={{ marginTop: 10 }}>
                <ReliabilityStackedBar done={metrics.crm_sync.success} failed={metrics.crm_sync.error} total={metrics.crm_sync.total} />
              </div>
              <Text style={{ fontSize: 11, color: C.textFaint, display: "block", marginTop: 8 }}>
                Vert = synchronisations réussies · Rouge = en erreur
              </Text>
            </SectionCard>
          </div>
        </>
      )}
    </div>
  );
}
