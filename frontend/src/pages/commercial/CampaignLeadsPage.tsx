import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Typography, Button, Tag, Spin, Tooltip, message,
  InputNumber, Popconfirm, Drawer, Input, Progress,
} from "antd";
import {
  ArrowLeftOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ReloadOutlined, EditOutlined, EyeOutlined,
  MailOutlined, SaveOutlined, CloseOutlined,
} from "@ant-design/icons";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";
import { ScoreBadge, formatCA, formatCaOrUnknown, hasPartialFinancials, type ShapFeature } from "@/components/LeadScoreBadge";

const { Text, Title } = Typography;
const { TextArea } = Input;

// ── Types ─────────────────────────────────────────────────────────────────────

interface Lead {
  id: string;
  company_name: string;
  siret: string;
  secteur: string | null;
  taille_entreprise: string | null;
  adresse: string | null;
  telephone: string | null;
  site_web: string | null;
  email: string | null;
  prenom_dirigeant: string | null;
  nom_dirigeant: string | null;
  titre_dirigeant: string | null;
  ca: number | null;
  resultat_net: number | null;
  score: number | null;
  score_exploitabilite: number | null;
  label_scoring: "CHAUD" | "TIEDE" | "FROID" | "HORS_CIBLE" | null;
  objet_email: string | null;
  contenu_email: string | null;
  email_genere_at: string | null;
  shap_explication: string | null;
  status: string;
}

interface Campaign {
  id: string;
  codes_naf: string[];
  codes_postaux: string[];
  quota: number;
  score_minimum: number;
  status: string;
  leads_count: number;
}

interface LeadListResponse {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_TAG_CONFIG: Record<string, { color: string; label: string }> = {
  QUALIFIE:             { color: "success",    label: "Qualifié"       },
  ECARTE:               { color: "default",    label: "Écarté"         },  // rejet automatique (gris)
  REJETE:               { color: "error",      label: "Rejeté"         },  // rejet humain (rouge)
  EN_ATTENTE_VALIDATION:{ color: "warning",    label: "À valider"      },
  EMAIL_GENERE:         { color: "processing", label: "Email généré"   },
  VALIDE:               { color: "success",    label: "Validé"         },
};

function StatusTag({ status }: { status: string }) {
  const cfg = STATUS_TAG_CONFIG[status] ?? { color: "default", label: status };
  return <Tag color={cfg.color}>{cfg.label}</Tag>;
}

// ── Composant SHAP ────────────────────────────────────────────────────────────

function ShapPanel({ shapJson }: { shapJson: string | null }) {
  if (!shapJson) return <Text style={{ color: C.textFaint, fontSize: 12 }}>Explication non disponible</Text>;

  let features: ShapFeature[] = [];
  try { features = JSON.parse(shapJson); } catch { return null; }

  const maxAbs = Math.max(...features.map((f) => Math.abs(f.contribution)));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {features.map((f) => {
        const pct = maxAbs > 0 ? Math.abs(f.contribution) / maxAbs * 100 : 0;
        const color = f.direction === "positif" ? C.green : C.red;
        return (
          <div key={f.feature}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
              <Text style={{ fontSize: 12, color: C.text }}>{f.label_fr}</Text>
              <Text style={{ fontSize: 12, color, fontWeight: 700 }}>
                {f.direction === "positif" ? "+" : "−"}{Math.abs(f.contribution).toFixed(3)}
              </Text>
            </div>
            <Progress
              percent={pct}
              showInfo={false}
              strokeColor={color}
              trailColor={C.border}
              size="small"
            />
          </div>
        );
      })}
      <Text style={{ fontSize: 11, color: C.textFaint, marginTop: 4 }}>
        Vert = facteur positif · Rouge = facteur limitant
      </Text>
    </div>
  );
}

// ── Drawer fiche lead ─────────────────────────────────────────────────────────

interface LeadDrawerProps {
  lead: Lead | null;
  onClose: () => void;
  onValidate: (leadId: string, status: "VALIDE" | "REJETE") => Promise<void>;
  onSaveEmail: (leadId: string, objet: string, contenu: string) => Promise<void>;
}

function LeadDrawer({ lead, onClose, onValidate, onSaveEmail }: LeadDrawerProps) {
  const [editMode, setEditMode] = useState(false);
  const [objet, setObjet] = useState("");
  const [contenu, setContenu] = useState("");
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    if (lead) {
      setObjet(lead.objet_email ?? "");
      setContenu(lead.contenu_email ?? "");
      setEditMode(false);
    }
  }, [lead?.id]);

  if (!lead) return null;

  const dirigeant = [lead.prenom_dirigeant, lead.nom_dirigeant].filter(Boolean).join(" ");
  const isValidationLead = lead.status === "EN_ATTENTE_VALIDATION";

  const handleValidate = async (status: "VALIDE" | "REJETE") => {
    setValidating(true);
    try { await onValidate(lead.id, status); onClose(); }
    finally { setValidating(false); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSaveEmail(lead.id, objet, contenu);
      setEditMode(false);
    } finally { setSaving(false); }
  };

  return (
    <Drawer
      open={!!lead}
      onClose={onClose}
      width={520}
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Text style={{ fontWeight: 700, color: C.navy, fontSize: 15 }}>{lead.company_name}</Text>
          <StatusTag status={lead.status} />
        </div>
      }
      styles={{ body: { padding: "20px 24px", background: C.bg } }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

        {/* ── Section score ────────────────────────────────────── */}
        <section style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, padding: "14px 16px" }}>
          <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4, display: "block", marginBottom: 10 }}>
            Score XGBoost
          </Text>
          <ScoreBadge score={lead.score} label={lead.label_scoring} partial={hasPartialFinancials(lead.ca, lead.resultat_net)} />

          {lead.shap_explication && (
            <div style={{ marginTop: 14 }}>
              <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4, display: "block", marginBottom: 10 }}>
                Facteurs explicatifs
              </Text>
              <ShapPanel shapJson={lead.shap_explication} />
            </div>
          )}
        </section>

        {/* ── Section entreprise ───────────────────────────────── */}
        <section style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, padding: "14px 16px" }}>
          <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4, display: "block", marginBottom: 10 }}>
            Entreprise
          </Text>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px" }}>
            {lead.secteur && <Row label="Secteur NAF" value={lead.secteur} />}
            {lead.taille_entreprise && <Row label="Taille" value={lead.taille_entreprise} />}
            {lead.adresse && <Row label="Adresse" value={lead.adresse} />}
            {dirigeant && <Row label="Dirigeant" value={`${lead.titre_dirigeant ? lead.titre_dirigeant + " " : ""}${dirigeant}`} />}
            {lead.email && <Row label="Email" value={lead.email} />}
            {lead.telephone && <Row label="Téléphone" value={lead.telephone} />}
            {lead.site_web && <Row label="Site web" value={lead.site_web} />}
            {lead.ca !== null && lead.ca !== 0 && <Row label="CA" value={formatCA(lead.ca)} />}
            {lead.resultat_net !== null && (
              <Row label="Résultat net" value={formatCA(lead.resultat_net)} valueColor={lead.resultat_net >= 0 ? C.green : C.red} />
            )}
          </div>
        </section>

        {/* ── Section email généré ─────────────────────────────── */}
        {(lead.objet_email || lead.contenu_email) && (
          <section style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, padding: "14px 16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4 }}>
                Email généré
              </Text>
              {isValidationLead && !editMode && (
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => setEditMode(true)}
                  style={{ color: C.amber, borderColor: C.amber }}
                >
                  Modifier
                </Button>
              )}
              {editMode && (
                <div style={{ display: "flex", gap: 6 }}>
                  <Button size="small" icon={<CloseOutlined />} onClick={() => { setEditMode(false); setObjet(lead.objet_email ?? ""); setContenu(lead.contenu_email ?? ""); }}>
                    Annuler
                  </Button>
                  <Button size="small" type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
                    Sauvegarder
                  </Button>
                </div>
              )}
            </div>

            {/* Objet */}
            <div style={{ marginBottom: 10 }}>
              <Text style={{ fontSize: 11.5, color: C.textMuted, display: "block", marginBottom: 4 }}>Objet</Text>
              {editMode
                ? <Input value={objet} onChange={(e) => setObjet(e.target.value)} maxLength={500} />
                : <div style={{ background: C.bg, borderRadius: R.md, padding: "8px 12px", fontSize: 13, fontWeight: 600, color: C.navy }}>
                    {lead.objet_email}
                  </div>
              }
            </div>

            {/* Corps */}
            <div>
              <Text style={{ fontSize: 11.5, color: C.textMuted, display: "block", marginBottom: 4 }}>Corps</Text>
              {editMode
                ? <TextArea value={contenu} onChange={(e) => setContenu(e.target.value)} rows={10} style={{ fontSize: 13 }} />
                : <div style={{
                    background: C.bg, borderRadius: R.md, padding: "10px 12px",
                    fontSize: 13, color: C.text, lineHeight: 1.6,
                    whiteSpace: "pre-wrap", maxHeight: 260, overflowY: "auto",
                  }}>
                    {lead.contenu_email}
                  </div>
              }
            </div>

            {lead.email_genere_at && (
              <Text style={{ fontSize: 11, color: C.textFaint, display: "block", marginTop: 8 }}>
                Généré le {new Date(lead.email_genere_at).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
              </Text>
            )}
          </section>
        )}

        {/* ── Actions de validation ────────────────────────────── */}
        {isValidationLead && (
          <div style={{ display: "flex", gap: 10 }}>
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={validating}
              onClick={() => handleValidate("VALIDE")}
              style={{ flex: 1, height: 40, background: C.green, borderColor: C.green, fontWeight: 700 }}
            >
              Valider
            </Button>
            <Button
              danger
              icon={<CloseCircleOutlined />}
              loading={validating}
              onClick={() => handleValidate("REJETE")}
              style={{ flex: 1, height: 40, fontWeight: 700 }}
            >
              Rejeter
            </Button>
          </div>
        )}
      </div>
    </Drawer>
  );
}

function Row({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div>
      <Text style={{ fontSize: 11, color: C.textMuted, display: "block" }}>{label}</Text>
      <Text style={{ fontSize: 12.5, color: valueColor ?? C.text, fontWeight: 500 }}>{value}</Text>
    </div>
  );
}

// ── Types d'onglets ───────────────────────────────────────────────────────────

type FilterTab = "tous" | "EN_ATTENTE_VALIDATION" | "QUALIFIE" | "VALIDE" | "ECARTE" | "REJETE";

// ── Page principale ───────────────────────────────────────────────────────────

export default function CampaignLeadsPage() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<FilterTab>("tous");
  const [updating, setUpdating] = useState<Record<string, boolean>>({});
  const [editThreshold, setEditThreshold] = useState<number>(50);
  const [savingThreshold, setSavingThreshold] = useState(false);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const fetchLeads = useCallback(async (filter: FilterTab) => {
    if (!campaignId) return;
    setLoading(true);
    try {
      const params: Record<string, string | boolean | number> = {
        campaign_id: campaignId,
        sort_by_score: true,
        page_size: 200,
      };
      if (filter !== "tous") params.status = String(filter);
      const res = await api.get<LeadListResponse>("/leads/", { params });
      setLeads(res.data.items);
      setTotal(res.data.total);
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    if (!campaignId) return;
    api.get<Campaign>(`/campaigns/${campaignId}`).then((r) => {
      setCampaign(r.data);
      setEditThreshold(Math.round(r.data.score_minimum * 100));
    });
    fetchLeads("tous");
  }, [campaignId, fetchLeads]);

  // Seuil de qualification
  const applyThreshold = async () => {
    if (!campaignId) return;
    setSavingThreshold(true);
    try {
      const newThreshold = editThreshold / 100;
      await api.patch(`/campaigns/${campaignId}/score-minimum`, { score_minimum: newThreshold });
      const res = await api.post<{ qualifies: number; rejetes: number }>(
        `/campaigns/${campaignId}/requalify`
      );
      setCampaign((c) => c ? { ...c, score_minimum: newThreshold } : c);
      await fetchLeads(tab);
      message.success(`Seuil appliqué : ${res.data.qualifies} qualifié(s), ${res.data.rejetes} écarté(s) automatiquement`);
    } catch {
      message.error("Erreur lors de l'application du seuil");
    } finally {
      setSavingThreshold(false);
    }
  };

  // Changement de statut manuel par le commercial (qualification/rejet humain)
  const changeStatus = async (leadId: string, status: "QUALIFIE" | "REJETE") => {
    setUpdating((u) => ({ ...u, [leadId]: true }));
    try {
      const res = await api.patch<Lead>(`/leads/${leadId}/status`, { status });
      setLeads((prev) => prev.map((l) => (l.id === leadId ? res.data : l)));
    } catch {
      message.error("Erreur lors de la mise à jour");
    } finally {
      setUpdating((u) => ({ ...u, [leadId]: false }));
    }
  };

  // Validation email (Valider / Rejeter)
  const handleValidate = async (leadId: string, status: "VALIDE" | "REJETE") => {
    const res = await api.patch<Lead>(`/leads/${leadId}/status`, { status });
    setLeads((prev) => prev.map((l) => (l.id === leadId ? res.data : l)));
    message.success(status === "VALIDE" ? "Email validé ✓" : "Email rejeté");
  };

  // Sauvegarde email modifié
  const handleSaveEmail = async (leadId: string, objet: string, contenu: string) => {
    const res = await api.patch<Lead>(`/leads/${leadId}/email`, { objet_email: objet, contenu_email: contenu });
    setLeads((prev) => prev.map((l) => (l.id === leadId ? res.data : l)));
    message.success("Email mis à jour");
  };

  const filteredLeads = tab === "tous" ? leads : leads.filter((l) => l.status === tab);

  const counts = {
    tous:                   total,
    EN_ATTENTE_VALIDATION:  leads.filter((l) => l.status === "EN_ATTENTE_VALIDATION").length,
    QUALIFIE:               leads.filter((l) => l.status === "QUALIFIE").length,
    VALIDE:                 leads.filter((l) => l.status === "VALIDE").length,
    ECARTE:                 leads.filter((l) => l.status === "ECARTE").length,
    REJETE:                 leads.filter((l) => l.status === "REJETE").length,
  };

  // Onglets — on n'affiche que ceux qui ont des leads (ou tous/validation)
  const ALL_TABS: { key: FilterTab; label: string; color: string }[] = [
    { key: "tous",                   label: "Tous",            color: C.navy      },
    { key: "EN_ATTENTE_VALIDATION",  label: "À valider",       color: C.amber     },
    { key: "VALIDE",                 label: "Validés",         color: C.green     },
    { key: "QUALIFIE",               label: "Qualifiés",       color: C.green     },
    { key: "ECARTE",                 label: "Écartés",         color: C.textMuted },
    { key: "REJETE",                 label: "Rejetés",         color: C.red       },
  ];
  const TABS = ALL_TABS.filter(
    (t) => t.key === "tous" || t.key === "EN_ATTENTE_VALIDATION" || counts[t.key] > 0
  );

  return (
    <div className="page-root">

      {/* ── Header ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/commercial")} style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <Title level={4} style={{ margin: 0, color: C.navy }}>Leads de la campagne</Title>
          {campaign && (
            <Text style={{ fontSize: 12.5, color: C.textMuted }}>
              {campaign.codes_naf.join(", ")} · {campaign.codes_postaux.join(", ")}
            </Text>
          )}
        </div>

        {/* Seuil éditable */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: R.lg, padding: "8px 14px", boxShadow: S.card,
        }}>
          <Text style={{ fontSize: 12.5, color: C.textMuted, whiteSpace: "nowrap" }}>Seuil</Text>
          <InputNumber
            min={0} max={100} step={5}
            value={editThreshold}
            onChange={(v) => setEditThreshold(v ?? 50)}
            formatter={(v) => `${v}%`}
            parser={(v) => Number(v?.replace("%", "") ?? 50)}
            size="small" style={{ width: 72 }}
          />
          <Popconfirm
            title={`Appliquer le seuil de ${editThreshold}% ?`}
            description={`Score ≥ ${editThreshold}% → Qualifié · Score < ${editThreshold}% → Écarté (auto). Les leads rejetés manuellement ne sont pas modifiés.`}
            onConfirm={applyThreshold}
            okText="Appliquer" cancelText="Annuler"
          >
            <Button size="small" icon={<ReloadOutlined />} loading={savingThreshold} style={{ color: C.indigo, borderColor: C.indigo }}>
              Réappliquer
            </Button>
          </Popconfirm>
        </div>
      </div>

      {/* ── Bannière emails en attente ───────────────────────────── */}
      {counts.EN_ATTENTE_VALIDATION > 0 && (
        <div style={{
          background: C.amberBg, border: `1px solid ${C.amber}40`,
          borderRadius: R.lg, padding: "12px 18px", marginBottom: 16,
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <MailOutlined style={{ color: C.amber, fontSize: 18 }} />
          <div style={{ flex: 1 }}>
            <Text style={{ fontWeight: 700, color: C.amber, fontSize: 13 }}>
              {counts.EN_ATTENTE_VALIDATION} email{counts.EN_ATTENTE_VALIDATION > 1 ? "s" : ""} en attente de validation
            </Text>
            <Text style={{ display: "block", fontSize: 12, color: C.textMuted }}>
              Cliquez sur un lead pour voir l'email généré et le valider ou le modifier.
            </Text>
          </div>
          <Button size="small" onClick={() => setTab("EN_ATTENTE_VALIDATION")} style={{ color: C.amber, borderColor: C.amber }}>
            Voir la file
          </Button>
        </div>
      )}

      {/* ── Onglets ─────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {TABS.map((t) => {
          const isActive = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: "6px 14px", borderRadius: 20,
                border: `1.5px solid ${isActive ? t.color : C.border}`,
                background: isActive ? `${t.color}18` : C.surface,
                color: isActive ? t.color : C.textMuted,
                fontWeight: isActive ? 700 : 400,
                fontSize: 13, cursor: "pointer",
                display: "flex", alignItems: "center", gap: 6,
              }}
            >
              {t.label}
              <span style={{
                background: isActive ? t.color : C.border,
                color: isActive ? "#fff" : C.textMuted,
                borderRadius: 10, padding: "0 6px", fontSize: 11, fontWeight: 700,
              }}>
                {counts[t.key as FilterTab]}
              </span>
            </button>
          );
        })}
      </div>

      {/* ── Table leads ─────────────────────────────────────────── */}
      <div style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, boxShadow: S.card, overflow: "hidden" }}>
        {/* En-tête */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "2fr 1.6fr 1fr 1fr 1fr 120px",
          padding: "10px 18px",
          borderBottom: `1px solid ${C.border}`,
          background: C.bg,
        }}>
          {["Entreprise", "Score", "CA", "Contact", "Statut", "Actions"].map((h) => (
            <Text key={h} style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4 }}>
              {h}
            </Text>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: "48px 0", textAlign: "center" }}><Spin /></div>
        ) : filteredLeads.length === 0 ? (
          <div style={{ padding: "48px 0", textAlign: "center" }}>
            <Text style={{ color: C.textMuted }}>Aucun lead dans cette catégorie</Text>
          </div>
        ) : (
          filteredLeads.map((lead, i) => {
            const isUpdating = updating[lead.id];
            const isValidation = lead.status === "EN_ATTENTE_VALIDATION";
            const dirigeant = [lead.prenom_dirigeant, lead.nom_dirigeant].filter(Boolean).join(" ") || null;

            const rowBg =
              lead.status === "REJETE"                ? `${C.red}06`       // rejet humain — rouge pâle
            : lead.status === "ECARTE"                ? `${C.textMuted}08` // écarté auto — gris pâle
            : lead.status === "VALIDE"                ? `${C.green}08`
            : lead.status === "EN_ATTENTE_VALIDATION"  ? `${C.amber}08`
            : lead.status === "QUALIFIE"               ? `${C.green}06`
            : C.surface;

            return (
              <div
                key={lead.id}
                onClick={() => setSelectedLead(lead)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 1.6fr 1fr 1fr 1fr 120px",
                  padding: "13px 18px",
                  borderBottom: i < filteredLeads.length - 1 ? `1px solid ${C.border}` : "none",
                  alignItems: "center",
                  background: rowBg,
                  cursor: "pointer",
                  transition: "filter 0.1s",
                }}
                onMouseEnter={(e) => (e.currentTarget as HTMLDivElement).style.filter = "brightness(0.97)"}
                onMouseLeave={(e) => (e.currentTarget as HTMLDivElement).style.filter = ""}
              >
                {/* Entreprise */}
                <div>
                  <Text style={{ fontWeight: 600, color: C.navy, fontSize: 13.5, display: "block" }}>
                    {lead.company_name}
                    {isValidation && <MailOutlined style={{ color: C.amber, fontSize: 12, marginLeft: 6 }} />}
                  </Text>
                  <Text style={{ fontSize: 11.5, color: C.textMuted }}>
                    {lead.secteur} · {lead.taille_entreprise ?? "—"}
                  </Text>
                </div>

                {/* Score */}
                <ScoreBadge score={lead.score} label={lead.label_scoring} partial={hasPartialFinancials(lead.ca, lead.resultat_net)} />

                {/* CA */}
                <div>
                  <Text style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>{formatCaOrUnknown(lead.ca)}</Text>
                  {lead.resultat_net !== null && (
                    <Text style={{ fontSize: 11.5, color: lead.resultat_net >= 0 ? C.green : C.red, display: "block" }}>
                      RN {lead.resultat_net >= 0 ? "+" : ""}{formatCA(lead.resultat_net)}
                    </Text>
                  )}
                </div>

                {/* Contact */}
                <div style={{ fontSize: 12, color: C.textMuted, display: "flex", flexDirection: "column", gap: 2 }}>
                  {dirigeant && <span style={{ color: C.text, fontWeight: 500 }}>{dirigeant}</span>}
                  {lead.email && (
                    <Tooltip title={lead.email}>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140 }}>
                        ✉ {lead.email}
                      </span>
                    </Tooltip>
                  )}
                  {lead.telephone && <span>📞 {lead.telephone}</span>}
                  {lead.site_web && (
                    <a
                      href={lead.site_web} target="_blank" rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140, color: C.textMuted }}
                    >
                      🌐 {lead.site_web.replace(/^https?:\/\//, "")}
                    </a>
                  )}
                  {!dirigeant && !lead.email && !lead.telephone && !lead.site_web && (
                    <span style={{ color: C.textFaint }}>—</span>
                  )}
                </div>

                {/* Statut */}
                <StatusTag status={lead.status} />

                {/* Actions (stop propagation pour ne pas ouvrir le drawer) */}
                <div style={{ display: "flex", gap: 5 }} onClick={(e) => e.stopPropagation()}>
                  {/* Fiche détail */}
                  <Tooltip title="Voir la fiche">
                    <Button size="small" type="text" icon={<EyeOutlined />} onClick={() => setSelectedLead(lead)} style={{ color: C.indigo }} />
                  </Tooltip>

                  {/* Qualifier manuellement : ECARTE (auto) ou REJETE (humain) → QUALIFIE */}
                  {(lead.status === "ECARTE" || lead.status === "REJETE") && (
                    <Tooltip title={lead.status === "ECARTE" ? "Qualifier (override auto)" : "Qualifier à nouveau"}>
                      <Button size="small" type="text" icon={<CheckCircleOutlined />} loading={isUpdating}
                        onClick={() => changeStatus(lead.id, "QUALIFIE")} style={{ color: C.green }} />
                    </Tooltip>
                  )}
                  {/* Rejeter manuellement : QUALIFIE → REJETE (rejet humain explicite) */}
                  {lead.status === "QUALIFIE" && (
                    <Tooltip title="Rejeter (décision manuelle)">
                      <Button size="small" type="text" icon={<CloseCircleOutlined />} loading={isUpdating}
                        onClick={() => changeStatus(lead.id, "REJETE")} style={{ color: C.red }} />
                    </Tooltip>
                  )}

                  {/* Actions validation email */}
                  {isValidation && (
                    <>
                      <Tooltip title="Valider l'email">
                        <Button size="small" type="text" icon={<CheckCircleOutlined />} loading={isUpdating}
                          onClick={() => handleValidate(lead.id, "VALIDE")} style={{ color: C.green }} />
                      </Tooltip>
                      <Tooltip title="Rejeter l'email">
                        <Button size="small" type="text" icon={<CloseCircleOutlined />} loading={isUpdating}
                          onClick={() => handleValidate(lead.id, "REJETE")} style={{ color: C.red }} />
                      </Tooltip>
                    </>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ── Pied de page ────────────────────────────────────────── */}
      {!loading && leads.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", gap: 16, flexWrap: "wrap" }}>
          <Text style={{ fontSize: 12, color: C.textMuted }}>
            {counts.EN_ATTENTE_VALIDATION > 0 && `${counts.EN_ATTENTE_VALIDATION} à valider · `}
            {counts.VALIDE > 0 && `${counts.VALIDE} validé${counts.VALIDE > 1 ? "s" : ""} · `}
            {counts.QUALIFIE > 0 && `${counts.QUALIFIE} qualifié${counts.QUALIFIE > 1 ? "s" : ""} · `}
            {counts.ECARTE > 0 && `${counts.ECARTE} écarté${counts.ECARTE > 1 ? "s" : ""} (auto) · `}
            {counts.REJETE > 0 && `${counts.REJETE} rejeté${counts.REJETE > 1 ? "s" : ""} (humain)`}
          </Text>
        </div>
      )}

      {/* ── Drawer fiche lead ────────────────────────────────────── */}
      <LeadDrawer
        lead={selectedLead}
        onClose={() => setSelectedLead(null)}
        onValidate={handleValidate}
        onSaveEmail={handleSaveEmail}
      />
    </div>
  );
}
