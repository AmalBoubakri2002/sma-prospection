import { useState } from "react";
import { Typography, Select, InputNumber, Button, App, Tag } from "antd";
import {
  AimOutlined, SearchOutlined,
  ArrowLeftOutlined, ThunderboltOutlined, PlusOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;

// ─── Static data ──────────────────────────────────────────────────────────────

const NAF_CODES = [
  { value: "62.01Z", label: "62.01Z — Programmation informatique" },
  { value: "62.02A", label: "62.02A — Conseil en systèmes informatiques" },
  { value: "62.03Z", label: "62.03Z — Exploitation de systèmes informatiques" },
  { value: "62.09Z", label: "62.09Z — Autres activités informatiques" },
  { value: "70.22Z", label: "70.22Z — Conseil pour les affaires" },
  { value: "73.20Z", label: "73.20Z — Études de marché" },
  { value: "64.19Z", label: "64.19Z — Banque et crédit" },
  { value: "66.22Z", label: "66.22Z — Agents d'assurance" },
  { value: "86.10Z", label: "86.10Z — Activités hospitalières" },
  { value: "86.21Z", label: "86.21Z — Médecine générale" },
  { value: "47.11B", label: "47.11B — Supermarchés" },
  { value: "49.41A", label: "49.41A — Transport routier de marchandises" },
  { value: "41.20A", label: "41.20A — Construction de maisons individuelles" },
  { value: "43.21A", label: "43.21A — Travaux d'installation électrique" },
  { value: "35.11Z", label: "35.11Z — Production d'électricité" },
  { value: "28.11Z", label: "28.11Z — Fabrication de moteurs" },
];

const TRANCHES = [
  { value: "11", label: "10–19" },
  { value: "12", label: "20–49" },
  { value: "21", label: "50–99" },
  { value: "22", label: "100–199" },
  { value: "31", label: "200–249" },
  { value: "32", label: "250–499" },
  { value: "41", label: "500–999" },
  { value: "42", label: "1 000–1 999" },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getTranchesLabel(selected: string[]): string {
  if (!selected.length) return "—";
  const ordered = TRANCHES.filter(t => selected.includes(t.value));
  if (!ordered.length) return "—";
  if (ordered.length === 1) return `${ordered[0].label} sal.`;
  return `${ordered[0].label} – ${ordered[ordered.length - 1].label} sal.`;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 20 }}>
      <span style={{ fontSize: 15, color: C.navy }}>{icon}</span>
      <Text style={{
        fontSize: 11, fontWeight: 700, letterSpacing: 1.3,
        textTransform: "uppercase", color: C.navy,
      }}>
        {title}
      </Text>
    </div>
  );
}

function TogglePill({
  label, selected, onClick,
}: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 16px",
        borderRadius: 99,
        border: `2px solid ${selected ? C.indigo : C.border}`,
        background: selected ? `${C.indigo}12` : "transparent",
        color: selected ? C.indigo : C.textMuted,
        fontWeight: selected ? 600 : 400,
        fontSize: 13.5,
        cursor: "pointer",
        transition: "all 0.15s",
        outline: "none",
        fontFamily: "inherit",
        lineHeight: 1.4,
      }}
    >
      {label}
    </button>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function NewCampaignPage() {
  const navigate    = useNavigate();
  const { message } = App.useApp();

  const [codesNaf,          setCodesNaf]          = useState<string[]>(["62.01Z", "62.02A"]);
  const [codesPostaux,      setCodesPostaux]       = useState<string[]>([]);
  const [cpInput,           setCpInput]            = useState("");
  const [tranchesEffectifs, setTranchesEffectifs]  = useState<string[]>(["12", "21"]);
  const [quota,             setQuota]              = useState(50);
  const [scoreMinimum,      setScoreMinimum]       = useState(0);
  const [launching,         setLaunching]          = useState(false);

  const toggle = (list: string[], val: string, set: (v: string[]) => void) =>
    set(list.includes(val) ? list.filter(v => v !== val) : [...list, val]);

  const addCodePostal = () => {
    const cp = cpInput.trim();
    if (/^\d{5}$/.test(cp) && !codesPostaux.includes(cp)) {
      setCodesPostaux([...codesPostaux, cp]);
    }
    setCpInput("");
  };

  const handleLaunch = async () => {
    if (!codesNaf.length)          { message.warning("Sélectionnez au moins un code NAF.");         return; }
    if (!codesPostaux.length)      { message.warning("Ajoutez au moins un code postal.");           return; }
    if (!tranchesEffectifs.length) { message.warning("Sélectionnez au moins une tranche d'effectif."); return; }
    setLaunching(true);
    try {
      await api.post("/campaigns/", {
        codes_naf:          codesNaf,
        codes_postaux:      codesPostaux,
        tranches_effectifs: tranchesEffectifs,
        quota,
        score_minimum:      scoreMinimum,
        estimated_prospects: 0,
      });
      message.success("Campagne créée avec succès !");
      navigate("/commercial");
    } catch {
      message.error("Erreur lors de la création de la campagne.");
    } finally {
      setLaunching(false);
    }
  };

  const summaryRows = [
    { key: "Codes NAF",     value: codesNaf.length ? `${codesNaf.length} code(s)` : "—" },
    { key: "Zones",         value: codesPostaux.length ? codesPostaux.slice(0, 3).join(", ") + (codesPostaux.length > 3 ? "…" : "") : "—" },
    { key: "Effectifs",     value: getTranchesLabel(tranchesEffectifs) },
    { key: "Quota",         value: `${quota} prospects max` },
    { key: "Score minimum", value: `${scoreMinimum} / 100` },
  ];

  const card: React.CSSProperties = {
    background:   C.surface,
    borderRadius: R.card,
    border:       `1px solid ${C.border}`,
    boxShadow:    S.card,
    padding:      "26px 28px",
    marginBottom: 16,
  };

  return (
    <div className="page-root">

      {/* ── Page header ──────────────────────────────────────── */}
      <div style={{ marginBottom: 28 }}>
        <button
          onClick={() => navigate("/commercial")}
          style={{
            background: "none", border: "none", cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6,
            color: C.textMuted, fontSize: 13, fontWeight: 500,
            padding: 0, marginBottom: 12, fontFamily: "inherit",
            transition: "color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = C.navy)}
          onMouseLeave={e => (e.currentTarget.style.color = C.textMuted)}
        >
          <ArrowLeftOutlined style={{ fontSize: 12 }} />
          Retour au tableau de bord
        </button>
        <Title level={3} style={{ margin: 0, color: C.navy, fontWeight: 800, lineHeight: 1.2 }}>
          Nouvelle campagne
        </Title>
        <Text style={{ color: C.textMuted, fontSize: 14, marginTop: 4, display: "block" }}>
          Configurez les critères de ciblage SIRENE pour lancer la prospection.
        </Text>
      </div>

      {/* ── Two-column layout ─────────────────────────────────── */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>

        {/* ── Left : Form ───────────────────────────────────── */}
        <div style={{ flex: "1 1 540px", minWidth: 0 }}>

          {/* Section 1 — Secteur d'activité */}
          <div style={card}>
            <SectionHeader icon={<AimOutlined />} title="Secteur d'activité (codes NAF)" />

            <Text style={{ fontSize: 13, fontWeight: 600, color: C.text, display: "block", marginBottom: 7 }}>
              Codes NAF / APE
            </Text>
            <Select
              mode="multiple"
              allowClear
              style={{ width: "100%" }}
              size="large"
              placeholder="Rechercher un code NAF…"
              value={codesNaf}
              onChange={setCodesNaf}
              options={NAF_CODES}
              optionFilterProp="label"
              showSearch
            />
            <Text style={{ fontSize: 12, color: C.textFaint, marginTop: 6, display: "block" }}>
              Source : champ <code>activitePrincipaleUniteLegale</code> — API SIRENE
            </Text>
          </div>

          {/* Section 2 — Zone géographique */}
          <div style={card}>
            <SectionHeader icon={<SearchOutlined />} title="Zone géographique (codes postaux)" />

            <Text style={{ fontSize: 13, fontWeight: 600, color: C.text, display: "block", marginBottom: 7 }}>
              Codes postaux (5 chiffres)
            </Text>
            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              <input
                value={cpInput}
                onChange={e => setCpInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addCodePostal()}
                placeholder="ex : 75008"
                maxLength={5}
                style={{
                  flex: 1, height: 40, borderRadius: R.md,
                  border: `1px solid ${C.border}`, padding: "0 12px",
                  fontSize: 14, fontFamily: "inherit", outline: "none",
                  color: C.text, background: C.surface,
                }}
              />
              <Button icon={<PlusOutlined />} onClick={addCodePostal} size="large">
                Ajouter
              </Button>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {codesPostaux.map(cp => (
                <Tag
                  key={cp}
                  closable
                  onClose={() => setCodesPostaux(codesPostaux.filter(c => c !== cp))}
                  style={{ fontSize: 13, padding: "3px 10px" }}
                >
                  {cp}
                </Tag>
              ))}
              {!codesPostaux.length && (
                <Text style={{ fontSize: 12, color: C.textFaint }}>Aucun code postal ajouté</Text>
              )}
            </div>
            <Text style={{ fontSize: 12, color: C.textFaint, marginTop: 8, display: "block" }}>
              Source : champ <code>codePostalEtablissement</code> — API SIRENE
            </Text>
          </div>

          {/* Section 3 — Taille */}
          <div style={card}>
            <SectionHeader icon={<AimOutlined />} title="Taille de l'entreprise (salariés)" />

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
              {TRANCHES.map(t => (
                <TogglePill
                  key={t.value}
                  label={t.label}
                  selected={tranchesEffectifs.includes(t.value)}
                  onClick={() => toggle(tranchesEffectifs, t.value, setTranchesEffectifs)}
                />
              ))}
            </div>
            <Text style={{ fontSize: 12, color: C.textFaint, marginTop: 4, display: "block" }}>
              Source : champ <code>trancheEffectifsEtablissement</code> — API SIRENE
            </Text>
          </div>

          {/* Section 4 — Quota */}
          <div style={card}>
            <SectionHeader icon={<SearchOutlined />} title="Quota de prospects" />

            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <Text style={{ fontSize: 13, fontWeight: 600, color: C.text }}>
                Nombre maximum de prospects à collecter
              </Text>
              <InputNumber
                min={1} max={500} step={10}
                value={quota}
                onChange={v => setQuota(v ?? 50)}
                size="large"
                style={{ width: 110 }}
              />
            </div>
          </div>

          {/* Section 5 — Score minimum */}
          <div style={card}>
            <SectionHeader icon={<AimOutlined />} title="Score minimum de qualification" />

            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <Text style={{ fontSize: 13, fontWeight: 600, color: C.text }}>
                Score minimum requis pour retenir un prospect
              </Text>
              <InputNumber
                min={0} max={100} step={5}
                value={scoreMinimum}
                onChange={v => setScoreMinimum(v ?? 0)}
                size="large"
                style={{ width: 110 }}
                formatter={v => `${v} / 100`}
                parser={v => Number(v?.replace(" / 100", "") ?? 0)}
              />
            </div>
            <Text style={{ fontSize: 12, color: C.textFaint, marginTop: 8, display: "block" }}>
              Seuls les prospects avec un score ≥ à cette valeur seront conservés.
            </Text>
          </div>

        </div>

        {/* ── Right : Summary panel ─────────────────────────── */}
        <div style={{ flex: "0 0 256px", position: "sticky", top: 80, minWidth: 220 }}>
          <div style={{
            background:   C.navy,
            borderRadius: R.card,
            padding:      "24px 22px",
            boxShadow:    "0 8px 32px rgba(27,58,107,0.28)",
          }}>
            <Text style={{ display: "block", fontWeight: 800, color: "#fff", fontSize: 16, marginBottom: 18 }}>
              Résumé
            </Text>

            <div style={{ marginBottom: 18 }}>
              {summaryRows.map((row, idx) => (
                <div
                  key={row.key}
                  style={{
                    display:        "flex",
                    justifyContent: "space-between",
                    alignItems:     "baseline",
                    paddingBottom:   9,
                    marginBottom:    9,
                    borderBottom:   idx < summaryRows.length - 1 ? "1px solid rgba(255,255,255,0.08)" : "none",
                  }}
                >
                  <Text style={{ fontSize: 13, color: "rgba(255,255,255,0.48)" }}>{row.key}</Text>
                  <Text style={{
                    fontSize: 13, fontWeight: 700, color: "#fff",
                    textAlign: "right", maxWidth: 130,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {row.value}
                  </Text>
                </div>
              ))}
            </div>

            {/* Quota visual */}
            <div style={{
              background:   "rgba(255,255,255,0.08)",
              borderRadius: R.lg,
              padding:      "16px 12px",
              textAlign:    "center",
              marginBottom: 18,
            }}>
              <div style={{ fontSize: 42, fontWeight: 900, color: "#fff", lineHeight: 1 }}>
                {quota}
              </div>
              <Text style={{ fontSize: 12.5, color: "rgba(255,255,255,0.5)", marginTop: 5, display: "block" }}>
                prospects max
              </Text>
            </div>

            <Button
              block
              size="large"
              loading={launching}
              onClick={handleLaunch}
              icon={!launching && <ThunderboltOutlined />}
              style={{
                background:  "#fff",
                borderColor: "#fff",
                color:       C.navy,
                fontWeight:  700,
                fontSize:    15,
                height:      48,
                borderRadius: R.lg,
              }}
            >
              Démarrer la prospection
            </Button>

            <Text style={{ display: "block", textAlign: "center", fontSize: 11, color: "rgba(255,255,255,0.33)", marginTop: 10 }}>
              Collecte via API SIRENE INSEE
            </Text>
          </div>
        </div>

      </div>
    </div>
  );
}
