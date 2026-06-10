import { Typography, Button } from "antd";
import {
  TeamOutlined, CalendarOutlined, RiseOutlined,
  PlusOutlined, RocketOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import type { AuthUser } from "@/stores/authStore";
import { C, S, R } from "@/styles/tokens";

function displayFirstName(user: AuthUser | null): string {
  if (!user) return "Commercial";
  const name = user.full_name;
  if (name && !/^\d+$/.test(name.trim())) return name.trim().split(" ")[0];
  return user.email?.split("@")[0] ?? "Commercial";
}

const { Title, Text } = Typography;

interface KpiCardProps {
  icon:       React.ReactNode;
  label:      string;
  value:      string | number;
  accent:     string;
  iconBg:     string;
  iconColor:  string;
}

function KpiCard({ icon, label, value, accent, iconBg, iconColor }: KpiCardProps) {
  return (
    <div style={{
      background:   C.surface,
      borderRadius: R.card,
      border:       `1px solid ${C.border}`,
      boxShadow:    S.card,
      flex:         1,
      minWidth:     160,
      overflow:     "hidden",
    }}>
      <div style={{ height: 3, background: accent }} />
      <div style={{ padding: "18px 20px", display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{
          width: 42, height: 42, borderRadius: R.lg,
          background: iconBg, display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 18, color: iconColor, flexShrink: 0,
        }}>
          {icon}
        </div>
        <div>
          <div style={{ fontSize: 26, fontWeight: 800, color: C.navy, lineHeight: 1 }}>{value}</div>
          <div style={{ fontSize: 13, color: C.textMuted, marginTop: 3 }}>{label}</div>
        </div>
      </div>
    </div>
  );
}

export default function CommercialDashboardPage() {
  const navigate = useNavigate();
  const user     = useAuthStore((s) => s.user);

  const now      = new Date();
  const hour     = now.getHours();
  const greeting = hour < 12 ? "Bonjour" : hour < 18 ? "Bon après-midi" : "Bonsoir";
  const dateStr  = now.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="page-root">

      {/* ── Welcome banner ────────────────────────────────────── */}
      <div style={{
        background:     `linear-gradient(118deg, ${C.navy} 0%, #1e4d8c 55%, ${C.indigo} 100%)`,
        borderRadius:   R.xl,
        padding:        "28px 32px",
        marginBottom:   28,
        display:        "flex",
        justifyContent: "space-between",
        alignItems:     "center",
        boxShadow:      "0 4px 24px rgba(27,58,107,0.22)",
        flexWrap:       "wrap",
        gap:            16,
        position:       "relative",
        overflow:       "hidden",
      }}>
        <div style={{ position:"absolute", top:-40, right:120, width:160, height:160, borderRadius:"50%", background:"rgba(255,255,255,0.04)", pointerEvents:"none" }} />
        <div style={{ position:"absolute", bottom:-50, right:-20, width:200, height:200, borderRadius:"50%", background:"rgba(255,255,255,0.03)", pointerEvents:"none" }} />

        <div style={{ position: "relative" }}>
          <Text style={{ color:"rgba(255,255,255,0.55)", fontSize:12.5, display:"block", textTransform:"capitalize", letterSpacing:0.3 }}>
            {dateStr}
          </Text>
          <Title level={3} style={{ color:"#fff", margin:"4px 0 6px", fontWeight:800, lineHeight:1.2 }}>
            {greeting}, {displayFirstName(user)} 👋
          </Title>
          <Text style={{ color:"rgba(255,255,255,0.65)", fontSize:14 }}>
            Voici votre activité commerciale du jour.
          </Text>
        </div>

      </div>

      {/* ── KPI cards ─────────────────────────────────────────── */}
      <div style={{ display:"flex", gap:14, flexWrap:"wrap", marginBottom:28 }}>
        <KpiCard
          icon={<TeamOutlined />}     label="Prospects actifs"    value={0}
          accent={C.indigo} iconBg="#eef2ff" iconColor={C.indigo}
        />
        <KpiCard
          icon={<CalendarOutlined />} label="RDV cette semaine"   value={0}
          accent={C.amber}  iconBg={C.amberBg} iconColor={C.amber}
        />
        <KpiCard
          icon={<RiseOutlined />}     label="Taux de conversion"  value="0%"
          accent={C.green}  iconBg={C.greenBg} iconColor={C.green}
        />
      </div>

      {/* ── Campaigns section ─────────────────────────────────── */}
      <div style={{
        background:   C.surface,
        borderRadius: R.card,
        border:       `1px solid ${C.border}`,
        boxShadow:    S.card,
        overflow:     "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding:       "16px 22px",
          borderBottom:  `1px solid ${C.border}`,
          display:       "flex",
          justifyContent:"space-between",
          alignItems:    "center",
          flexWrap:      "wrap",
          gap:           12,
        }}>
          <div style={{ display:"flex", alignItems:"center", gap:12 }}>
            <div style={{
              width:32, height:32, borderRadius:R.md,
              background:"#eef2ff",
              display:"flex", alignItems:"center", justifyContent:"center",
              color:C.indigo, fontSize:16,
            }}>
              <RocketOutlined />
            </div>
            <div>
              <Text style={{ fontWeight:700, color:C.navy, fontSize:14 }}>Campagnes de prospection</Text>
              <Text style={{ display:"block", fontSize:12, color:C.textMuted, marginTop:1 }}>
                Lancez et suivez vos campagnes automatisées
              </Text>
            </div>
          </div>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate("/commercial/campagnes/nouvelle")}
          >
            Nouvelle campagne
          </Button>
        </div>

        {/* Empty state */}
        <div style={{ padding:"56px 20px", textAlign:"center" }}>
          <div style={{
            width:60, height:60, borderRadius:"50%",
            background:C.bg,
            display:"flex", alignItems:"center", justifyContent:"center",
            margin:"0 auto 16px",
            fontSize:26, color:C.textFaint,
          }}>
            <RocketOutlined />
          </div>
          <Text style={{ display:"block", color:C.text, fontSize:15, fontWeight:600, marginBottom:6 }}>
            Aucune campagne pour l'instant
          </Text>
          <Text style={{ display:"block", color:C.textMuted, fontSize:13, marginBottom:22, maxWidth:340, margin:"0 auto 22px" }}>
            Créez votre première campagne pour démarrer la prospection automatisée via l'agent LangGraph.
          </Text>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate("/commercial/campagnes/nouvelle")}
          >
            Créer une campagne
          </Button>
        </div>

      </div>

    </div>
  );
}
