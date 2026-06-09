import { Typography, Tag, Button, Avatar } from "antd";
import {
  TeamOutlined, PhoneOutlined, CalendarOutlined, RiseOutlined,
  PlusOutlined, ClockCircleOutlined, CheckCircleOutlined,
  SyncOutlined, MailOutlined, ArrowRightOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;

// ─── Types ────────────────────────────────────────────────────────────────────

interface KpiCardProps {
  icon:     React.ReactNode;
  label:    string;
  value:    string | number;
  sub:      string;
  accent:   string;
  iconBg:   string;
  iconColor:string;
}

interface PipelineStep {
  key:   string;
  label: string;
  color: string;
  bg:    string;
  icon:  React.ReactNode;
  count: number;
  step:  number;
}

interface Activity {
  id:       number;
  name:     string;
  company:  string;
  action:   string;
  time:     string;
  status:   "done" | "pending" | "inprogress";
  initials: string;
  color:    string;
}

// ─── Static data ──────────────────────────────────────────────────────────────

const pipeline: PipelineStep[] = [
  { key: "new",       step: 1, label: "Nouveaux",     color: C.indigo, bg: "#eef2ff", icon: <TeamOutlined />,        count: 0 },
  { key: "contacted", step: 2, label: "Contactés",    color: C.cyan,   bg: C.cyanBg,  icon: <PhoneOutlined />,       count: 0 },
  { key: "meeting",   step: 3, label: "RDV planifié", color: C.amber,  bg: C.amberBg, icon: <CalendarOutlined />,    count: 0 },
  { key: "won",       step: 4, label: "Convertis",    color: C.green,  bg: C.greenBg, icon: <CheckCircleOutlined />, count: 0 },
];

const recentActivity: Activity[] = [
  { id: 1, name: "Marie Dupont",   company: "TechCorp SA",      action: "Email de suivi envoyé",    time: "Il y a 2h",    status: "done",       initials: "MD", color: C.indigo },
  { id: 2, name: "Lucas Bernard",  company: "Innova Group",     action: "RDV planifié le 12 juin",  time: "Il y a 4h",    status: "pending",    initials: "LB", color: C.cyan },
  { id: 3, name: "Sophie Martin",  company: "DataVision SARL",  action: "Appel en attente",         time: "Hier, 14h30",  status: "inprogress", initials: "SM", color: C.amber },
  { id: 4, name: "Antoine Leroy",  company: "StartUp Factory",  action: "Contrat signé",            time: "Hier, 10h00",  status: "done",       initials: "AL", color: C.green },
  { id: 5, name: "Clara Petit",    company: "MedTech Solutions", action: "Premier contact effectué", time: "Lundi, 09h15", status: "done",       initials: "CP", color: C.purple },
];

const statusConfig = {
  done:       { label: "Effectué",   color: "success",    icon: <CheckCircleOutlined /> },
  pending:    { label: "En attente", color: "warning",    icon: <ClockCircleOutlined /> },
  inprogress: { label: "En cours",   color: "processing", icon: <SyncOutlined spin /> },
} as const;

// ─── Sub-components ───────────────────────────────────────────────────────────

function KpiCard({ icon, label, value, sub, accent, iconBg, iconColor }: KpiCardProps) {
  return (
    <div
      style={{
        background:   C.surface,
        borderRadius: R.card,
        border:       `1px solid ${C.border}`,
        boxShadow:    S.card,
        flex:         1,
        minWidth:     190,
        overflow:     "hidden",
      }}
    >
      <div style={{ height: 3, background: accent }} />
      <div style={{ padding: "18px 20px" }}>
        <div style={{ width: 40, height: 40, borderRadius: R.lg, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, color: iconColor, marginBottom: 14 }}>
          {icon}
        </div>
        <div style={{ fontSize: 28, fontWeight: 800, color: C.navy, lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: 13, color: C.textMuted, marginTop: 4, fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: 11, color: C.textFaint, marginTop: 4 }}>{sub}</div>
      </div>
    </div>
  );
}

function PipelineCard({ step }: { step: PipelineStep }) {
  return (
    <div
      className="card-lift"
      style={{
        flex:         1,
        minWidth:     130,
        background:   C.surface,
        borderRadius: R.lg,
        padding:      "16px 18px",
        border:       `1px solid ${C.border}`,
        boxShadow:    S.card,
        cursor:       "pointer",
        position:     "relative",
        overflow:     "hidden",
      }}
    >
      {/* Step number */}
      <div style={{ position: "absolute", top: 12, right: 14, fontSize: 11, fontWeight: 700, color: `${step.color}50` }}>
        #{step.step}
      </div>
      <div style={{ width: 34, height: 34, borderRadius: R.md, background: step.bg, display: "flex", alignItems: "center", justifyContent: "center", color: step.color, fontSize: 15, marginBottom: 10 }}>
        {step.icon}
      </div>
      <div style={{ fontSize: 24, fontWeight: 800, color: C.navy }}>{step.count}</div>
      <div style={{ fontSize: 12, color: C.textMuted, marginTop: 2, fontWeight: 500 }}>{step.label}</div>
      <div style={{ marginTop: 10, height: 3, borderRadius: 99, background: step.bg }}>
        <div style={{ height: "100%", width: "0%", background: step.color, borderRadius: 99 }} />
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function CommercialDashboardPage() {
  const navigate = useNavigate();
  const user     = useAuthStore((state) => state.user);

  const now      = new Date();
  const hour     = now.getHours();
  const greeting = hour < 12 ? "Bonjour" : hour < 18 ? "Bon après-midi" : "Bonsoir";
  const dateStr  = now.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="page-root" style={{ margin: "0 auto" }}>

      {/* ── Welcome banner ──────────────────────────────────── */}
      <div
        style={{
          background:   `linear-gradient(118deg, ${C.navy} 0%, #1e4d8c 55%, ${C.indigo} 100%)`,
          borderRadius: R.xl,
          padding:      "28px 32px",
          marginBottom: 24,
          display:      "flex",
          justifyContent: "space-between",
          alignItems:   "center",
          boxShadow:    "0 4px 24px rgba(27,58,107,0.22)",
          flexWrap:     "wrap",
          gap:          16,
          position:     "relative",
          overflow:     "hidden",
        }}
      >
        {/* Subtle decorative circles */}
        <div style={{ position: "absolute", top: -40, right: 120, width: 160, height: 160, borderRadius: "50%", background: "rgba(255,255,255,0.04)", pointerEvents: "none" }} />
        <div style={{ position: "absolute", bottom: -50, right: -20, width: 200, height: 200, borderRadius: "50%", background: "rgba(255,255,255,0.03)", pointerEvents: "none" }} />

        <div style={{ position: "relative" }}>
          <Text style={{ color: "rgba(255,255,255,0.55)", fontSize: 12.5, display: "block", textTransform: "capitalize", letterSpacing: 0.3 }}>
            {dateStr}
          </Text>
          <Title level={3} style={{ color: "#fff", margin: "4px 0 6px", fontWeight: 800, lineHeight: 1.2 }}>
            {greeting}, {user?.full_name?.split(" ")[0] ?? "Commercial"} 👋
          </Title>
          <Text style={{ color: "rgba(255,255,255,0.65)", fontSize: 14 }}>
            Voici un aperçu de votre activité commerciale du jour.
          </Text>
        </div>

        <Button
          icon={<PlusOutlined />}
          onClick={() => navigate("/commercial/prospects")}
          style={{
            background:    "rgba(255,255,255,0.14)",
            border:        "1.5px solid rgba(255,255,255,0.28)",
            color:         "#fff",
            borderRadius:  R.md,
            height:        40,
            fontWeight:    600,
            backdropFilter:"blur(4px)",
            flexShrink:    0,
          }}
        >
          Nouveau prospect
        </Button>
      </div>

      {/* ── KPI cards ───────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 24 }}>
        <KpiCard icon={<TeamOutlined />}     label="Total prospects"       value={0}   sub="Aucun prospect pour l'instant"  accent={C.indigo} iconBg="#eef2ff" iconColor={C.indigo} />
        <KpiCard icon={<PhoneOutlined />}    label="Contactés aujourd'hui" value={0}   sub="Objectif : 10 contacts/jour"    accent={C.cyan}   iconBg={C.cyanBg}   iconColor={C.cyan} />
        <KpiCard icon={<CalendarOutlined />} label="RDV cette semaine"     value={0}   sub="Aucun RDV planifié"             accent={C.amber}  iconBg={C.amberBg}  iconColor={C.amber} />
        <KpiCard icon={<RiseOutlined />}     label="Taux de conversion"    value="0%"  sub="Prospects → Clients"            accent={C.green}  iconBg={C.greenBg}  iconColor={C.green} />
      </div>

      {/* ── Pipeline + Activity ─────────────────────────────── */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>

        {/* Left column */}
        <div style={{ flex: "1 1 380px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Pipeline */}
          <div style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, boxShadow: S.card, overflow: "hidden" }}>
            <div style={{ padding: "16px 20px 12px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={{ fontWeight: 700, color: C.navy, fontSize: 14 }}>Pipeline commercial</Text>
              <Button
                type="link"
                size="small"
                icon={<ArrowRightOutlined />}
                style={{ color: C.indigo, padding: 0, fontWeight: 500, fontSize: 13 }}
                onClick={() => navigate("/commercial/prospects")}
              >
                Voir tout
              </Button>
            </div>
            <div style={{ padding: "16px 20px", display: "flex", gap: 10, flexWrap: "wrap" }}>
              {pipeline.map((step) => (
                <PipelineCard key={step.key} step={step} />
              ))}
            </div>
          </div>

          {/* Quick actions */}
          <div style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, boxShadow: S.card, padding: "16px 20px" }}>
            <Text style={{ fontWeight: 700, color: C.navy, fontSize: 14, display: "block", marginBottom: 14 }}>
              Actions rapides
            </Text>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {[
                { label: "Ajouter un prospect", icon: <PlusOutlined />,    path: "/commercial/prospects", color: C.navy },
                { label: "Planifier un RDV",    icon: <CalendarOutlined />, path: "/commercial/agenda",   color: C.cyan },
                { label: "Envoyer un email",    icon: <MailOutlined />,     path: "#",                    color: C.purple },
              ].map((action) => (
                <Button
                  key={action.label}
                  icon={action.icon}
                  onClick={() => action.path !== "#" && navigate(action.path)}
                  style={{
                    borderRadius: R.md,
                    border:       `1.5px solid ${action.color}25`,
                    color:        action.color,
                    background:   `${action.color}08`,
                    fontWeight:   500,
                    fontSize:     13,
                    height:       38,
                  }}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          </div>

        </div>

        {/* Activity feed */}
        <div
          style={{
            flex:         "0 0 320px",
            minWidth:     0,
            background:   C.surface,
            borderRadius: R.card,
            border:       `1px solid ${C.border}`,
            boxShadow:    S.card,
            overflow:     "hidden",
          }}
        >
          <div style={{ padding: "16px 20px 12px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ fontWeight: 700, color: C.navy, fontSize: 14 }}>Activité récente</Text>
            <Button type="link" size="small" style={{ color: C.indigo, padding: 0, fontWeight: 500, fontSize: 13 }}>
              Tout voir
            </Button>
          </div>

          {recentActivity.map((item, idx) => {
            const cfg = statusConfig[item.status];
            return (
              <div
                key={item.id}
                role="button"
                tabIndex={0}
                style={{
                  display:      "flex",
                  gap:          12,
                  padding:      "13px 20px",
                  borderBottom: idx < recentActivity.length - 1 ? `1px solid ${C.bg}` : "none",
                  alignItems:   "flex-start",
                  cursor:       "pointer",
                  transition:   "background 0.12s",
                  outline:      "none",
                }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLDivElement).style.background = "#fafbff")}
                onMouseLeave={(e) => ((e.currentTarget as HTMLDivElement).style.background = "transparent")}
                onFocus={(e)     => ((e.currentTarget as HTMLDivElement).style.background = "#fafbff")}
                onBlur={(e)      => ((e.currentTarget as HTMLDivElement).style.background = "transparent")}
              >
                <Avatar
                  size={34}
                  style={{ background: `${item.color}18`, color: item.color, fontSize: 12, fontWeight: 700, flexShrink: 0, border: `1.5px solid ${item.color}30` }}
                >
                  {item.initials}
                </Avatar>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: C.navy, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {item.name}
                    </span>
                    <Tag icon={cfg.icon} color={cfg.color} style={{ flexShrink: 0, margin: 0 }}>
                      {cfg.label}
                    </Tag>
                  </div>
                  <div style={{ fontSize: 12, color: C.textMuted, marginTop: 1, fontWeight: 500 }}>{item.company}</div>
                  <div style={{ fontSize: 12, color: C.textSub, marginTop: 3 }}>{item.action}</div>
                  <div style={{ fontSize: 11, color: C.textFaint, marginTop: 3 }}>{item.time}</div>
                </div>
              </div>
            );
          })}
        </div>

      </div>
    </div>
  );
}
