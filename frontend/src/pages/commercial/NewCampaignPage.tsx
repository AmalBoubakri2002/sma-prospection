import { useState } from "react";
import { Typography, Select, Slider, Button, App } from "antd";
import {
  AimOutlined, SettingOutlined, SearchOutlined,
  CheckOutlined, ArrowLeftOutlined, ThunderboltOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;
const { Option } = Select;

// ─── Static data ──────────────────────────────────────────────────────────────

const SECTORS = [
  { value: "esn",        label: "ESN (Services Numériques)" },
  { value: "industrie",  label: "Industrie" },
  { value: "sante",      label: "Santé" },
  { value: "finance",    label: "Finance / Banque" },
  { value: "retail",     label: "Retail / Commerce" },
  { value: "logistique", label: "Logistique" },
  { value: "btp",        label: "BTP / Construction" },
  { value: "energie",    label: "Énergie" },
];

const COUNTRIES = [
  { value: "france",     label: "France" },
  { value: "belgique",   label: "Belgique" },
  { value: "suisse",     label: "Suisse" },
  { value: "luxembourg", label: "Luxembourg" },
];

const SIZES = [
  { value: "1-10",    label: "1–10"    },
  { value: "11-49",   label: "11–49"   },
  { value: "50-200",  label: "50–200"  },
  { value: "201-500", label: "201–500" },
  { value: "500+",    label: "500+"    },
];

const FUNCTIONS = [
  { value: "ceo",           label: "CEO"            },
  { value: "dsi",           label: "DSI"            },
  { value: "dir-commercial",label: "Dir. Commercial" },
  { value: "drh",           label: "DRH"            },
  { value: "cto",           label: "CTO"            },
];

const SOURCES = [
  { value: "sirene",     label: "API SIRENE", sub: "~3 200 résultats", available: true,  base: 3200 },
  { value: "linkedin",   label: "LinkedIn",   sub: "~6 800 résultats", available: true,  base: 6800 },
  { value: "scraping",   label: "Web scraping", sub: "Désactivé",      available: false, base: 0    },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getSizeLabel(sizes: string[]): string {
  if (sizes.length === 0) return "—";
  const indices = SIZES.map((s, i) => sizes.includes(s.value) ? i : -1).filter(i => i >= 0);
  if (indices.length === 0) return "—";
  const minIdx = indices[0];
  const maxIdx = indices[indices.length - 1];
  if (minIdx === maxIdx) return `${SIZES[minIdx].label} sal.`;
  // Extract lower bound of first selected, upper bound of last selected
  const minLabel = SIZES[minIdx].label;
  const maxLabel = SIZES[maxIdx].label;
  const lowerBound = minLabel.split("–")[0];
  const upperBound = maxLabel.includes("–") ? maxLabel.split("–")[1] : maxLabel;
  return `${lowerBound}–${upperBound} sal.`;
}

function getSourceLabel(sources: string[]): string {
  const short: Record<string, string> = { sirene: "SIRENE", linkedin: "LI", scraping: "Web" };
  return sources.map(s => short[s]).join(" + ") || "—";
}

function computeEstimate(sources: string[], sizes: string[], functions: string[]): number {
  const total = SOURCES.filter(s => sources.includes(s.value)).reduce((acc, s) => acc + s.base, 0);
  if (!total || !sizes.length || !functions.length) return 0;
  const raw = total * (sizes.length / SIZES.length) * (functions.length / FUNCTIONS.length) * 0.2;
  return Math.max(50, Math.round(raw / 50) * 50);
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div style={{ display:"flex", alignItems:"center", gap:9, marginBottom:20 }}>
      <span style={{ fontSize:15, color:C.navy }}>{icon}</span>
      <Text style={{
        fontSize:11, fontWeight:700, letterSpacing:1.3,
        textTransform:"uppercase", color:C.navy,
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
        padding:      "6px 16px",
        borderRadius: 99,
        border:       `2px solid ${selected ? C.indigo : C.border}`,
        background:   selected ? `${C.indigo}12` : "transparent",
        color:        selected ? C.indigo : C.textMuted,
        fontWeight:   selected ? 600 : 400,
        fontSize:     13.5,
        cursor:       "pointer",
        transition:   "all 0.15s",
        outline:      "none",
        fontFamily:   "inherit",
        lineHeight:   1.4,
      }}
    >
      {label}
    </button>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function NewCampaignPage() {
  const navigate       = useNavigate();
  const { message }    = App.useApp();

  const [sector,    setSector]    = useState("esn");
  const [country,   setCountry]   = useState("france");
  const [sizes,     setSizes]     = useState<string[]>(["50-200", "201-500"]);
  const [functions, setFunctions] = useState<string[]>(["ceo", "dsi", "dir-commercial"]);
  const [minScore,  setMinScore]  = useState(70);
  const [sources,   setSources]   = useState<string[]>(["sirene", "linkedin"]);
  const [launching, setLaunching] = useState(false);

  const estimate = computeEstimate(sources, sizes, functions);

  const toggle = (list: string[], val: string, set: (v: string[]) => void) =>
    set(list.includes(val) ? list.filter(v => v !== val) : [...list, val]);

  const handleLaunch = async () => {
    if (!sources.length)   { message.warning("Sélectionnez au moins une source.");   return; }
    if (!sizes.length)     { message.warning("Sélectionnez au moins une taille.");   return; }
    if (!functions.length) { message.warning("Sélectionnez au moins une fonction."); return; }
    setLaunching(true);
    await new Promise(r => setTimeout(r, 1400));
    setLaunching(false);
    message.success("Campagne lancée — l'orchestrateur LangGraph est en cours d'exécution.");
    navigate("/commercial");
  };

  const sectorLabel  = SECTORS.find(s  => s.value === sector)?.label.split(" ")[0] ?? "—";
  const countryLabel = COUNTRIES.find(c => c.value === country)?.label              ?? "—";

  const summaryRows = [
    { key: "Secteur",    value: sectorLabel             },
    { key: "Pays",       value: countryLabel            },
    { key: "Taille",     value: getSizeLabel(sizes)     },
    { key: "Score min.", value: `≥ ${minScore} / 100`   },
    { key: "Sources",    value: getSourceLabel(sources) },
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
            background:"none", border:"none", cursor:"pointer",
            display:"flex", alignItems:"center", gap:6,
            color:C.textMuted, fontSize:13, fontWeight:500,
            padding:0, marginBottom:12, fontFamily:"inherit",
            transition:"color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = C.navy)}
          onMouseLeave={e => (e.currentTarget.style.color = C.textMuted)}
        >
          <ArrowLeftOutlined style={{ fontSize:12 }} />
          Retour au tableau de bord
        </button>
        <Title level={3} style={{ margin:0, color:C.navy, fontWeight:800, lineHeight:1.2 }}>
          Nouvelle campagne
        </Title>
        <Text style={{ color:C.textMuted, fontSize:14, marginTop:4, display:"block" }}>
          Configurez les paramètres de ciblage pour lancer l'agent de prospection.
        </Text>
      </div>

      {/* ── Two-column layout ─────────────────────────────────── */}
      <div style={{ display:"flex", gap:20, alignItems:"flex-start", flexWrap:"wrap" }}>

        {/* ── Left : Form ───────────────────────────────────── */}
        <div style={{ flex:"1 1 540px", minWidth:0 }}>

          {/* Section 1 — Ciblage */}
          <div style={card}>
            <SectionHeader icon={<AimOutlined />} title="Qui cibler ?" />

            <div style={{ display:"flex", gap:14, flexWrap:"wrap", marginBottom:22 }}>
              <div style={{ flex:"1 1 220px" }}>
                <Text style={{ fontSize:13, fontWeight:600, color:C.text, display:"block", marginBottom:7 }}>
                  Secteur d'activité
                </Text>
                <Select value={sector} onChange={setSector} style={{ width:"100%" }} size="large">
                  {SECTORS.map(s => <Option key={s.value} value={s.value}>{s.label}</Option>)}
                </Select>
              </div>
              <div style={{ flex:"1 1 160px" }}>
                <Text style={{ fontSize:13, fontWeight:600, color:C.text, display:"block", marginBottom:7 }}>
                  Pays
                </Text>
                <Select value={country} onChange={setCountry} style={{ width:"100%" }} size="large">
                  {COUNTRIES.map(c => <Option key={c.value} value={c.value}>{c.label}</Option>)}
                </Select>
              </div>
            </div>

            <div style={{ marginBottom:22 }}>
              <Text style={{ fontSize:13, fontWeight:600, color:C.text, display:"block", marginBottom:10 }}>
                Taille de l'entreprise (salariés)
              </Text>
              <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                {SIZES.map(s => (
                  <TogglePill
                    key={s.value}
                    label={s.label}
                    selected={sizes.includes(s.value)}
                    onClick={() => toggle(sizes, s.value, setSizes)}
                  />
                ))}
              </div>
            </div>

            <div>
              <Text style={{ fontSize:13, fontWeight:600, color:C.text, display:"block", marginBottom:10 }}>
                Fonctions visées
              </Text>
              <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                {FUNCTIONS.map(f => (
                  <TogglePill
                    key={f.value}
                    label={f.label}
                    selected={functions.includes(f.value)}
                    onClick={() => toggle(functions, f.value, setFunctions)}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Section 2 — Qualité */}
          <div style={card}>
            <SectionHeader icon={<SettingOutlined />} title="Paramètres de qualité" />

            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10 }}>
              <Text style={{ fontSize:13, fontWeight:600, color:C.text }}>Score minimum requis</Text>
              <div style={{
                background:C.navy, color:"#fff",
                borderRadius:R.md, padding:"3px 14px",
                fontSize:15, fontWeight:700, minWidth:42, textAlign:"center",
              }}>
                {minScore}
              </div>
            </div>

            <Slider
              value={minScore}
              onChange={setMinScore}
              min={0} max={100} step={5}
              styles={{
                track:  { background: C.navy },
                handle: { borderColor: C.navy, boxShadow: `0 0 0 3px ${C.navy}22` },
              }}
            />
            <div style={{ display:"flex", justifyContent:"space-between", marginTop:6 }}>
              <Text style={{ fontSize:11, color:C.textFaint }}>0 — Large</Text>
              <Text style={{ fontSize:11, color:C.textFaint }}>100 — Sélectif</Text>
            </div>
          </div>

          {/* Section 3 — Sources */}
          <div style={card}>
            <SectionHeader icon={<SearchOutlined />} title="Sources — Agent Veille" />

            <div style={{ display:"flex", gap:12, flexWrap:"wrap" }}>
              {SOURCES.map(src => {
                const active = sources.includes(src.value) && src.available;
                return (
                  <div
                    key={src.value}
                    onClick={() => src.available && toggle(sources, src.value, setSources)}
                    style={{
                      flex:         "1 1 140px",
                      border:       `2px solid ${active ? C.navy : C.border}`,
                      borderRadius: R.lg,
                      padding:      "14px 16px",
                      cursor:       src.available ? "pointer" : "not-allowed",
                      background:   active ? `${C.navy}07` : "transparent",
                      opacity:      src.available ? 1 : 0.45,
                      position:     "relative",
                      transition:   "all 0.15s",
                    }}
                    onMouseEnter={e => { if (src.available && !active) (e.currentTarget as HTMLDivElement).style.borderColor = C.borderMd; }}
                    onMouseLeave={e => { if (src.available && !active) (e.currentTarget as HTMLDivElement).style.borderColor = C.border; }}
                  >
                    {active && (
                      <div style={{
                        position:"absolute", top:8, right:8,
                        width:18, height:18, borderRadius:"50%",
                        background:C.navy,
                        display:"flex", alignItems:"center", justifyContent:"center",
                        fontSize:9, color:"#fff",
                      }}>
                        <CheckOutlined />
                      </div>
                    )}
                    <Text style={{ display:"block", fontWeight:700, color:src.available ? C.navy : C.textMuted, fontSize:14, marginBottom:4 }}>
                      {src.label}
                    </Text>
                    <Text style={{ fontSize:12, color:src.available ? C.textMuted : C.textFaint }}>
                      {src.sub}
                    </Text>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* ── Right : Summary panel ─────────────────────────── */}
        <div style={{ flex:"0 0 256px", position:"sticky", top:80, minWidth:220 }}>
          <div style={{
            background: C.navy,
            borderRadius: R.card,
            padding:     "24px 22px",
            boxShadow:   "0 8px 32px rgba(27,58,107,0.28)",
          }}>
            <Text style={{ display:"block", fontWeight:800, color:"#fff", fontSize:16, marginBottom:18 }}>
              Résumé
            </Text>

            {/* Rows */}
            <div style={{ marginBottom:18 }}>
              {summaryRows.map((row, idx) => (
                <div
                  key={row.key}
                  style={{
                    display:       "flex",
                    justifyContent:"space-between",
                    alignItems:    "baseline",
                    paddingBottom:  9,
                    marginBottom:   9,
                    borderBottom:  idx < summaryRows.length - 1 ? "1px solid rgba(255,255,255,0.08)" : "none",
                  }}
                >
                  <Text style={{ fontSize:13, color:"rgba(255,255,255,0.48)" }}>{row.key}</Text>
                  <Text style={{
                    fontSize:13, fontWeight:700, color:"#fff",
                    textAlign:"right", maxWidth:130,
                    overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                  }}>
                    {row.value}
                  </Text>
                </div>
              ))}
            </div>

            {/* Estimate */}
            <div style={{
              background:   "rgba(255,255,255,0.08)",
              borderRadius: R.lg,
              padding:      "16px 12px",
              textAlign:    "center",
              marginBottom: 18,
            }}>
              <div style={{ fontSize:42, fontWeight:900, color:"#fff", lineHeight:1 }}>
                ~{estimate > 0 ? estimate.toLocaleString("fr-FR") : "—"}
              </div>
              <Text style={{ fontSize:12.5, color:"rgba(255,255,255,0.5)", marginTop:5, display:"block" }}>
                prospects estimés
              </Text>
            </div>

            {/* Launch */}
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
                borderRadius:R.lg,
              }}
            >
              Démarrer la prospection
            </Button>

            <Text style={{ display:"block", textAlign:"center", fontSize:11, color:"rgba(255,255,255,0.33)", marginTop:10 }}>
              Lance l'orchestrateur LangGraph
            </Text>
          </div>
        </div>

      </div>
    </div>
  );
}
