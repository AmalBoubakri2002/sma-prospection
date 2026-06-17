import { useEffect, useState } from "react";
import { Typography, Button, Tag, Spin } from "antd";
import {
  TeamOutlined, CalendarOutlined, RiseOutlined,
  PlusOutlined, RocketOutlined, ClockCircleOutlined, LockOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import type { AuthUser } from "@/stores/authStore";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";

function displayFirstName(user: AuthUser | null): string {
  if (!user) return "Commercial";
  const name = user.full_name;
  if (name && !/^\d+$/.test(name.trim())) return name.trim().split(" ")[0];
  return user.email?.split("@")[0] ?? "Commercial";
}

interface Campaign {
  id: string;
  codes_naf: string[];
  codes_postaux: string[];
  quota: number;
  leads_count: number;
  status: "pending" | "running" | "done" | "failed";
  created_at: string;
}

const STATUS_LABEL: Record<Campaign["status"], { label: string; color: string }> = {
  pending: { label: "En attente",  color: "default" },
  running: { label: "En cours",    color: "processing" },
  done:    { label: "Terminée",    color: "success" },
  failed:  { label: "Échouée",     color: "error" },
};

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
  const navigate  = useNavigate();
  const user      = useAuthStore((s) => s.user);
  const isPending = user?.status === "PENDING";

  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);

  useEffect(() => {
    if (isPending) { setLoadingCampaigns(false); return; }
    api.get<Campaign[]>("/campaigns/")
      .then((res) => setCampaigns(res.data))
      .catch(() => {})
      .finally(() => setLoadingCampaigns(false));
  }, [isPending]);

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

      {isPending ? (
        <>
          {/* ── Restricted access banner ───────────────────────── */}
          <div style={{
            background:   C.amberBg,
            border:       `1px solid ${C.amber}40`,
            borderRadius: R.lg,
            padding:      "14px 18px",
            marginBottom: 28,
            display:      "flex",
            gap:          12,
            alignItems:   "flex-start",
          }}>
            <ClockCircleOutlined style={{ color: C.amber, fontSize: 18, marginTop: 2 }} />
            <Text style={{ fontSize: 13.5, color: C.text }}>
              ⏳ Votre compte est en attente d'approbation par un administrateur. Certaines fonctionnalités restent indisponibles.
            </Text>
          </div>

          {/* ── Locked features section ────────────────────────── */}
          <div style={{
            background:   C.surface,
            borderRadius: R.card,
            border:       `1px solid ${C.border}`,
            boxShadow:    S.card,
            padding:      "48px 20px",
            textAlign:    "center",
          }}>
            <div style={{
              width:60, height:60, borderRadius:"50%",
              background:C.bg,
              display:"flex", alignItems:"center", justifyContent:"center",
              margin:"0 auto 16px",
              fontSize:24, color:C.textFaint,
            }}>
              <LockOutlined />
            </div>
            <Text style={{ display:"block", color:C.text, fontSize:15, fontWeight:600, marginBottom:6 }}>
              Fonctionnalités verrouillées
            </Text>
            <Text style={{ display:"block", color:C.textMuted, fontSize:13, maxWidth:380, margin:"0 auto" }}>
              La création de campagnes, le lancement de la prospection et l'accès au CRM seront disponibles dès la validation de votre compte.
              En attendant, vous pouvez consulter et modifier votre profil.
            </Text>
            <Button
              style={{ marginTop: 20 }}
              onClick={() => navigate("/commercial/profil")}
            >
              Voir mon profil
            </Button>
          </div>
        </>
      ) : (
        <>
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

            {loadingCampaigns ? (
              <div style={{ padding: "56px 0", textAlign: "center" }}>
                <Spin />
              </div>
            ) : campaigns.length === 0 ? (
              /* Empty state */
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
            ) : (
              /* Campaign list */
              <div>
                {campaigns.map((c) => (
                  <div
                    key={c.id}
                    style={{
                      padding: "16px 22px",
                      borderBottom: `1px solid ${C.border}`,
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: 12,
                    }}
                  >
                    <div>
                      <Text style={{ fontWeight: 600, color: C.navy, fontSize: 13.5 }}>
                        {c.codes_naf.join(", ")}
                      </Text>
                      <Text style={{ display: "block", fontSize: 12, color: C.textMuted, marginTop: 2 }}>
                        {c.codes_postaux.join(", ")} · {new Date(c.created_at).toLocaleDateString("fr-FR")}
                      </Text>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                      <Text style={{ fontSize: 13, color: C.textMuted }}>
                        <span style={{ fontWeight: 700, color: C.navy }}>{c.leads_count}</span> / {c.quota} leads
                      </Text>
                      <Tag color={STATUS_LABEL[c.status]?.color ?? "default"}>
                        {STATUS_LABEL[c.status]?.label ?? c.status}
                      </Tag>
                    </div>
                  </div>
                ))}
              </div>
            )}

          </div>
        </>
      )}

    </div>
  );
}
