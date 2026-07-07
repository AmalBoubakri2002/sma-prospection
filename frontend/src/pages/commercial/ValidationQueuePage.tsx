import { useEffect, useState, useCallback, useRef } from "react";
import { Typography, Button, Spin, Drawer, Input, Progress, message, Tooltip } from "antd";
import {
  CheckCircleOutlined, CloseCircleOutlined, EditOutlined,
  SaveOutlined, CloseOutlined, MailOutlined,
} from "@ant-design/icons";
import api from "@/utils/api";
import { useNotifications } from "@/hooks/useNotifications";
import type { NotificationItem } from "@/hooks/useNotifications";
import { C, S, R } from "@/styles/tokens";
import { ScoreBadge, LABEL_CONFIG, formatCA, hasPartialFinancials, type ShapFeature } from "@/components/LeadScoreBadge";

const { Text, Title } = Typography;
const { TextArea } = Input;

// ── Types ─────────────────────────────────────────────────────────────────────

interface Lead {
  id:                  string;
  campaign_id:         string;
  company_name:        string;
  siret:               string;
  secteur:             string | null;
  taille_entreprise:   string | null;
  adresse:             string | null;
  telephone:           string | null;
  site_web:            string | null;
  email:               string | null;
  prenom_dirigeant:    string | null;
  nom_dirigeant:       string | null;
  titre_dirigeant:     string | null;
  ca:                  number | null;
  resultat_net:        number | null;
  score:               number | null;
  label_scoring:       "CHAUD" | "TIEDE" | "FROID" | "HORS_CIBLE" | null;
  objet_email:         string | null;
  contenu_email:       string | null;
  email_genere_at:     string | null;
  shap_explication:    string | null;
  status:              string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseShap(json: string | null): ShapFeature[] {
  if (!json) return [];
  try { return JSON.parse(json); } catch { return []; }
}

// ── Composant : chips SHAP inline (liste) ─────────────────────────────────────

function ShapChips({ shapJson, max = 3 }: { shapJson: string | null; max?: number }) {
  const features = parseShap(shapJson).slice(0, max);
  if (!features.length) return <Text style={{ color: C.textFaint, fontSize: 12 }}>—</Text>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {features.map((f) => (
        <Tooltip key={f.feature} title={`Contribution : ${f.contribution > 0 ? "+" : ""}${f.contribution.toFixed(3)}`}>
          <span style={{
            padding: "3px 9px", borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: "default",
            background: f.direction === "positif" ? "#dcfce7" : "#fee2e2",
            color:      f.direction === "positif" ? C.green   : C.red,
            border: `1px solid ${f.direction === "positif" ? "#bbf7d0" : "#fecaca"}`,
          }}>
            {f.direction === "positif" ? "↑" : "↓"} {f.label_fr}
          </span>
        </Tooltip>
      ))}
    </div>
  );
}

// ── Composant : barres SHAP dans le drawer (top 5) ────────────────────────────

function ShapBars({ shapJson }: { shapJson: string | null }) {
  const features = parseShap(shapJson);
  if (!features.length) return <Text style={{ color: C.textFaint, fontSize: 12 }}>Non disponible</Text>;
  const maxAbs = Math.max(...features.map((f) => Math.abs(f.contribution)));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {features.map((f) => {
        const pct = maxAbs > 0 ? (Math.abs(f.contribution) / maxAbs) * 100 : 0;
        const color = f.direction === "positif" ? C.green : C.red;
        return (
          <div key={f.feature}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
              <Text style={{ fontSize: 12, color: C.text }}>{f.label_fr}</Text>
              <Text style={{ fontSize: 12, color, fontWeight: 700 }}>
                {f.direction === "positif" ? "+" : "−"}{Math.abs(f.contribution).toFixed(3)}
              </Text>
            </div>
            <Progress percent={pct} showInfo={false} strokeColor={color} trailColor={C.border} size="small" />
          </div>
        );
      })}
      <Text style={{ fontSize: 11, color: C.textFaint, marginTop: 2 }}>
        Vert = facteur favorable · Rouge = facteur limitant
      </Text>
    </div>
  );
}

// ── Drawer : fiche lead détaillée ─────────────────────────────────────────────

interface DrawerState {
  lead:     Lead;
  editMode: boolean;
}

function LeadDetailDrawer({
  state,
  onClose,
  onValidate,
  onSaveEmail,
}: {
  state:       DrawerState | null;
  onClose:     () => void;
  onValidate:  (id: string, status: "VALIDE" | "REJETE") => Promise<void>;
  onSaveEmail: (id: string, objet: string, contenu: string) => Promise<void>;
}) {
  const [editMode, setEditMode] = useState(false);
  const [objet,    setObjet]    = useState("");
  const [contenu,  setContenu]  = useState("");
  const [saving,   setSaving]   = useState(false);
  const [acting,   setActing]   = useState(false);

  useEffect(() => {
    if (!state) return;
    setObjet(state.lead.objet_email ?? "");
    setContenu(state.lead.contenu_email ?? "");
    setEditMode(state.editMode);
  }, [state?.lead.id, state?.editMode]);

  if (!state) return null;
  const { lead } = state;
  // Arrondi comme LeadScoreBadge.tsx — peut sembler incohérent avec le badge près des seuils.
  const pct = lead.score !== null ? Math.round(lead.score * 100) : null;
  const dirigeant = [lead.titre_dirigeant, lead.prenom_dirigeant, lead.nom_dirigeant].filter(Boolean).join(" ");

  const handleValidate = async (status: "VALIDE" | "REJETE") => {
    setActing(true);
    try { await onValidate(lead.id, status); onClose(); }
    finally { setActing(false); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSaveEmail(lead.id, objet, contenu);
      setEditMode(false);
      message.success("Email mis à jour");
    } finally { setSaving(false); }
  };

  return (
    <Drawer
      open
      onClose={onClose}
      width={540}
      styles={{ body: { padding: 0, background: C.bg }, header: { borderBottom: `1px solid ${C.border}` } }}
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 34, height: 34, borderRadius: R.md, background: "#eef2ff",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: C.indigo, fontSize: 15,
          }}>
            <MailOutlined />
          </div>
          <div>
            <Text style={{ fontWeight: 700, color: C.navy, fontSize: 14, display: "block" }}>
              {lead.company_name}
            </Text>
            {pct !== null && lead.label_scoring && (
              <Text style={{ fontSize: 11.5, color: LABEL_CONFIG[lead.label_scoring].color, fontWeight: 600 }}>
                Score {pct}% — {LABEL_CONFIG[lead.label_scoring].label}
              </Text>
            )}
          </div>
        </div>
      }
    >
      <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14 }}>

        {/* ── Score + SHAP ─────────────────────────────────── */}
        <section style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, padding: "16px 18px" }}>

          {/* Score bar large */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4 }}>
                Score XGBoost
              </Text>
              {pct !== null && lead.label_scoring && (
                <span style={{
                  padding: "3px 10px", borderRadius: 20,
                  background: LABEL_CONFIG[lead.label_scoring].bg,
                  color: LABEL_CONFIG[lead.label_scoring].color,
                  fontSize: 12, fontWeight: 700,
                  display: "flex", alignItems: "center", gap: 5,
                }}>
                  {LABEL_CONFIG[lead.label_scoring].icon}
                  {LABEL_CONFIG[lead.label_scoring].label}
                </span>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1, height: 10, background: C.border, borderRadius: 5, overflow: "hidden" }}>
                <div style={{
                  width: `${pct ?? 0}%`, height: "100%", borderRadius: 5,
                  background: lead.label_scoring ? LABEL_CONFIG[lead.label_scoring].color : C.indigo,
                  transition: "width 0.4s ease",
                }} />
              </div>
              <Text style={{ fontWeight: 800, fontSize: 22, color: C.navy, minWidth: 48, textAlign: "right" }}>
                {pct ?? "—"}%
              </Text>
            </div>
          </div>

          {/* SHAP */}
          <div>
            <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4, display: "block", marginBottom: 10 }}>
              Facteurs explicatifs
            </Text>
            <ShapBars shapJson={lead.shap_explication} />
          </div>
        </section>

        {/* ── Infos entreprise ─────────────────────────────── */}
        <section style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, padding: "14px 18px" }}>
          <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4, display: "block", marginBottom: 10 }}>
            Entreprise
          </Text>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 20px" }}>
            {lead.secteur          && <InfoRow label="Secteur NAF" value={lead.secteur} />}
            {lead.taille_entreprise && <InfoRow label="Taille"      value={lead.taille_entreprise} />}
            {dirigeant             && <InfoRow label="Dirigeant"   value={dirigeant} />}
            {lead.email            && <InfoRow label="Email"        value={lead.email} />}
            {lead.telephone        && <InfoRow label="Téléphone"    value={lead.telephone} />}
            {lead.site_web         && <InfoRow label="Site web"     value={lead.site_web} />}
            {lead.ca !== null && lead.ca !== 0 && <InfoRow label="CA" value={formatCA(lead.ca)} />}
            {lead.resultat_net !== null && (
              <InfoRow label="Résultat net" value={formatCA(lead.resultat_net)} valueColor={lead.resultat_net >= 0 ? C.green : C.red} />
            )}
            {lead.adresse && <InfoRow label="Localisation" value={lead.adresse} />}
          </div>
        </section>

        {/* ── Email généré ─────────────────────────────────── */}
        <section style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, padding: "14px 18px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <Text style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.4 }}>
              Email généré
            </Text>
            {!editMode ? (
              <Button size="small" icon={<EditOutlined />}
                onClick={() => setEditMode(true)}
                style={{ color: C.amber, borderColor: C.amber, fontWeight: 600 }}>
                Modifier
              </Button>
            ) : (
              <div style={{ display: "flex", gap: 6 }}>
                <Button size="small" icon={<CloseOutlined />}
                  onClick={() => { setEditMode(false); setObjet(lead.objet_email ?? ""); setContenu(lead.contenu_email ?? ""); }}>
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
            <Text style={{ fontSize: 11.5, color: C.textMuted, display: "block", marginBottom: 5 }}>Objet</Text>
            {editMode ? (
              <Input value={objet} onChange={(e) => setObjet(e.target.value)} maxLength={500} placeholder="Objet de l'email" />
            ) : (
              <div style={{ background: C.bg, borderRadius: R.md, padding: "9px 13px", fontSize: 13, fontWeight: 600, color: C.navy, lineHeight: 1.4 }}>
                {lead.objet_email ?? <span style={{ color: C.textFaint }}>—</span>}
              </div>
            )}
          </div>

          {/* Corps */}
          <div>
            <Text style={{ fontSize: 11.5, color: C.textMuted, display: "block", marginBottom: 5 }}>Corps</Text>
            {editMode ? (
              <TextArea value={contenu} onChange={(e) => setContenu(e.target.value)} rows={11} style={{ fontSize: 13, lineHeight: 1.6 }} />
            ) : (
              <div style={{
                background: C.bg, borderRadius: R.md, padding: "10px 13px",
                fontSize: 13, color: C.text, lineHeight: 1.7,
                whiteSpace: "pre-wrap", maxHeight: 280, overflowY: "auto",
              }}>
                {lead.contenu_email ?? <span style={{ color: C.textFaint }}>—</span>}
              </div>
            )}
          </div>

          {lead.email_genere_at && (
            <Text style={{ fontSize: 11, color: C.textFaint, display: "block", marginTop: 8 }}>
              Généré le {new Date(lead.email_genere_at).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
            </Text>
          )}
        </section>

        {/* ── Boutons validation ───────────────────────────── */}
        <div style={{ display: "flex", gap: 10 }}>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            loading={acting}
            onClick={() => handleValidate("VALIDE")}
            style={{ flex: 1, height: 42, background: C.green, borderColor: C.green, fontWeight: 700, fontSize: 14 }}
          >
            Valider l'email
          </Button>
          <Button
            danger
            icon={<CloseCircleOutlined />}
            loading={acting}
            onClick={() => handleValidate("REJETE")}
            style={{ flex: 1, height: 42, fontWeight: 700, fontSize: 14 }}
          >
            Rejeter
          </Button>
        </div>

      </div>
    </Drawer>
  );
}

function InfoRow({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div>
      <Text style={{ fontSize: 11, color: C.textMuted, display: "block" }}>{label}</Text>
      <Text style={{ fontSize: 12.5, color: valueColor ?? C.text, fontWeight: 500 }}>{value}</Text>
    </div>
  );
}

// ── Page principale ───────────────────────────────────────────────────────────

export default function ValidationQueuePage() {
  const [leads,   setLeads]   = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawer,  setDrawer]  = useState<DrawerState | null>(null);
  // Ref pour éviter un double-fetch si la page se monte pendant une notification
  const fetchingRef = useRef(false);

  const fetchLeads = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setLoading(true);
    try {
      const res = await api.get<{ items: Lead[]; total: number }>(
        "/leads/",
        { params: { status: "EN_ATTENTE_VALIDATION", sort_by_score: true, page_size: 200 } }
      );
      setLeads(res.data.items);
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, []);

  useEffect(() => { fetchLeads(); }, [fetchLeads]);

  // Quand de nouveaux emails arrivent via WebSocket, on rafraîchit la liste
  // sans attendre que l'utilisateur recharge la page manuellement.
  const handleNotification = useCallback((notif: NotificationItem) => {
    if (notif.type === "EMAILS_PRETS") fetchLeads();
  }, [fetchLeads]);

  useNotifications(handleNotification);

  const handleValidate = async (id: string, status: "VALIDE" | "REJETE") => {
    await api.patch(`/leads/${id}/status`, { status });
    setLeads((prev) => prev.filter((l) => l.id !== id));
    message.success(status === "VALIDE" ? "Email validé ✓" : "Email rejeté");
  };

  const handleSaveEmail = async (id: string, objet: string, contenu: string) => {
    const res = await api.patch<Lead>(`/leads/${id}/email`, { objet_email: objet, contenu_email: contenu });
    setLeads((prev) => prev.map((l) => (l.id === id ? res.data : l)));
    // Mettre à jour le drawer si ouvert sur ce lead
    setDrawer((d) => d && d.lead.id === id ? { ...d, lead: res.data } : d);
  };

  return (
    <div className="page-root">

      {/* ── En-tête ─────────────────────────────────────────── */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <div style={{
            width: 40, height: 40, borderRadius: R.lg, background: C.amberBg,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, color: C.amber,
          }}>
            <MailOutlined />
          </div>
          <div>
            <Title level={4} style={{ margin: 0, color: C.navy }}>
              File de validation
            </Title>
            <Text style={{ fontSize: 12.5, color: C.textMuted }}>
              Emails générés en attente de votre approbation
            </Text>
          </div>
          {!loading && (
            <span style={{
              marginLeft: 8,
              padding: "3px 12px", borderRadius: 20,
              background: leads.length > 0 ? C.amberBg : C.bg,
              color: leads.length > 0 ? C.amber : C.textMuted,
              fontWeight: 700, fontSize: 13,
              border: `1px solid ${leads.length > 0 ? C.amber + "40" : C.border}`,
            }}>
              {leads.length} en attente
            </span>
          )}
        </div>
      </div>

      {/* ── Table ───────────────────────────────────────────── */}
      <div style={{
        background: C.surface, borderRadius: R.card,
        border: `1px solid ${C.border}`, boxShadow: S.card, overflow: "hidden",
      }}>

        {/* En-tête colonnes */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "2fr 1.8fr 2.5fr 200px",
          padding: "11px 20px",
          borderBottom: `1px solid ${C.border}`,
          background: C.bg,
        }}>
          {["Entreprise", "Score", "Facteurs clés (SHAP)", "Actions"].map((h) => (
            <Text key={h} style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 0.5 }}>
              {h}
            </Text>
          ))}
        </div>

        {/* Corps */}
        {loading ? (
          <div style={{ padding: "64px 0", textAlign: "center" }}><Spin size="large" /></div>
        ) : leads.length === 0 ? (
          <div style={{ padding: "64px 20px", textAlign: "center" }}>
            <div style={{
              width: 56, height: 56, borderRadius: "50%", background: C.bg,
              display: "flex", alignItems: "center", justifyContent: "center",
              margin: "0 auto 16px", fontSize: 24, color: C.textFaint,
            }}>
              <CheckCircleOutlined />
            </div>
            <Text style={{ display: "block", fontWeight: 700, color: C.text, fontSize: 15, marginBottom: 6 }}>
              Tout est validé !
            </Text>
            <Text style={{ display: "block", color: C.textMuted, fontSize: 13 }}>
              Aucun email en attente de validation pour l'instant.
            </Text>
          </div>
        ) : (
          leads.map((lead, i) => {
            const pct = lead.score !== null ? Math.round(lead.score * 100) : null;
            return (
              <div
                key={lead.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 1.8fr 2.5fr 200px",
                  padding: "14px 20px",
                  borderBottom: i < leads.length - 1 ? `1px solid ${C.border}` : "none",
                  alignItems: "center",
                  background: C.surface,
                  transition: "background 0.12s",
                  cursor: "default",
                }}
                onMouseEnter={(e) => (e.currentTarget as HTMLDivElement).style.background = `${C.amber}06`}
                onMouseLeave={(e) => (e.currentTarget as HTMLDivElement).style.background = C.surface}
              >
                {/* Colonne 1 : Entreprise */}
                <div
                  onClick={() => setDrawer({ lead, editMode: false })}
                  style={{ cursor: "pointer" }}
                >
                  <Text style={{ fontWeight: 700, color: C.navy, fontSize: 13.5, display: "block" }}>
                    {lead.company_name}
                  </Text>
                  <Text style={{ fontSize: 11.5, color: C.textMuted }}>
                    {lead.secteur ?? "—"} · SIRET {lead.siret}
                  </Text>
                </div>

                {/* Colonne 2 : Score */}
                <div onClick={() => setDrawer({ lead, editMode: false })} style={{ cursor: "pointer" }}>
                  <ScoreBadge score={lead.score} label={lead.label_scoring} variant="queue" partial={hasPartialFinancials(lead.ca, lead.resultat_net)} />
                  {pct !== null && (
                    <Text style={{ fontSize: 11, color: C.textFaint, display: "block", marginTop: 3 }}>
                      Score {pct}/100
                    </Text>
                  )}
                </div>

                {/* Colonne 3 : SHAP top 3 */}
                <div onClick={() => setDrawer({ lead, editMode: false })} style={{ cursor: "pointer" }}>
                  <ShapChips shapJson={lead.shap_explication} max={3} />
                </div>

                {/* Colonne 4 : Actions */}
                <div style={{ display: "flex", gap: 6 }} onClick={(e) => e.stopPropagation()}>
                  {/* Valider */}
                  <Tooltip title="Valider l'email">
                    <Button
                      size="small"
                      icon={<CheckCircleOutlined />}
                      onClick={() => handleValidate(lead.id, "VALIDE")}
                      style={{
                        color: C.green, borderColor: C.green,
                        background: "#f0fdf4", fontWeight: 600,
                      }}
                    >
                      Valider
                    </Button>
                  </Tooltip>

                  {/* Modifier */}
                  <Tooltip title="Modifier l'email">
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => setDrawer({ lead, editMode: true })}
                      style={{
                        color: C.amber, borderColor: C.amber,
                        background: C.amberBg, fontWeight: 600,
                      }}
                    >
                      Modifier
                    </Button>
                  </Tooltip>

                  {/* Rejeter */}
                  <Tooltip title="Rejeter l'email">
                    <Button
                      size="small"
                      icon={<CloseCircleOutlined />}
                      onClick={() => handleValidate(lead.id, "REJETE")}
                      danger
                      style={{ fontWeight: 600 }}
                    >
                      Rejeter
                    </Button>
                  </Tooltip>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ── Drawer fiche lead ────────────────────────────────── */}
      <LeadDetailDrawer
        state={drawer}
        onClose={() => setDrawer(null)}
        onValidate={handleValidate}
        onSaveEmail={handleSaveEmail}
      />
    </div>
  );
}
