import { useEffect, useState } from "react";
import { Typography, Spin, Button } from "antd";
import {
  TeamOutlined,
  CheckCircleOutlined,
  StopOutlined,
  ClockCircleOutlined,
  TrophyOutlined,
  PlusOutlined,
  ArrowRightOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;

interface Stats { total: number; actifs: number; inactifs: number; en_attente: number; }

interface StatCardProps {
  icon:    React.ReactNode;
  label:   string;
  value:   number | string;
  accent:  string;
  iconBg:  string;
  iconColor: string;
}

function StatCard({ icon, label, value, accent, iconBg, iconColor }: StatCardProps) {
  return (
    <div
      style={{
        background:   C.surface,
        borderRadius: R.card,
        border:       `1px solid ${C.border}`,
        boxShadow:    S.card,
        overflow:     "hidden",
        flex:         1,
        minWidth:     200,
      }}
    >
      {/* Accent bar top */}
      <div style={{ height: 4, background: accent }} />
      <div style={{ padding: "20px 22px", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ width: 48, height: 48, borderRadius: R.lg, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: iconColor, flexShrink: 0 }}>
          {icon}
        </div>
        <div>
          <div style={{ fontSize: 28, fontWeight: 800, color: C.navy, lineHeight: 1.1 }}>{value}</div>
          <div style={{ fontSize: 13, color: C.textMuted, marginTop: 3 }}>{label}</div>
        </div>
      </div>
    </div>
  );
}

export default function AdminDashboardPage() {
  const navigate = useNavigate();
  const [stats,   setStats]   = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<Stats>("/users/stats")
      .then((res) => setStats(res.data))
      .finally(() => setLoading(false));
  }, []);

  const tauxActivite = stats && stats.total > 0 ? Math.round((stats.actifs / stats.total) * 100) : 0;

  return (
    <div className="page-root">

      {/* ── Page header ──────────────────────────────────── */}
      <div style={{ marginBottom: 32, display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0, color: C.navy, fontWeight: 800, lineHeight: 1.2 }}>
            Tableau de bord
          </Title>
          <Text style={{ color: C.textMuted, fontSize: 14, marginTop: 4, display: "block" }}>
            Vue d'ensemble de votre équipe commerciale
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate("/admin/commerciaux")}
        >
          Nouveau commercial
        </Button>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : (
        <>
          {/* ── KPI cards ──────────────────────────────────── */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
            <StatCard
              icon={<TeamOutlined />}
              label="Total commerciaux"
              value={stats?.total ?? 0}
              accent={C.navy}
              iconBg="#e8edf5"
              iconColor={C.navy}
            />
            <StatCard
              icon={<CheckCircleOutlined />}
              label="Comptes actifs"
              value={stats?.actifs ?? 0}
              accent={C.green}
              iconBg={C.greenBg}
              iconColor={C.green}
            />
            <StatCard
              icon={<ClockCircleOutlined />}
              label="En attente de validation"
              value={stats?.en_attente ?? 0}
              accent={C.amber}
              iconBg={C.amberBg}
              iconColor={C.amber}
            />
            <StatCard
              icon={<StopOutlined />}
              label="Comptes inactifs"
              value={stats?.inactifs ?? 0}
              accent={C.red}
              iconBg={C.redBg}
              iconColor={C.red}
            />
            <StatCard
              icon={<TrophyOutlined />}
              label="Taux d'activité"
              value={`${tauxActivite}%`}
              accent={C.purple}
              iconBg={C.purpleBg}
              iconColor={C.purple}
            />
          </div>

          {/* ── Bottom row: progress + quick actions ───────── */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>

            {/* Progress widget */}
            <div
              style={{
                background:   C.surface,
                borderRadius: R.card,
                padding:      "22px 24px",
                border:       `1px solid ${C.border}`,
                boxShadow:    S.card,
                flex:         1,
                minWidth:     240,
                maxWidth:     480,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
                <Text style={{ fontWeight: 700, color: C.navy, fontSize: 14 }}>Taux d'activité</Text>
                <Text style={{ fontWeight: 800, color: C.navy, fontSize: 18 }}>{tauxActivite}%</Text>
              </div>
              <div style={{ height: 8, borderRadius: 99, background: "#e8edf5", overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width:  `${tauxActivite}%`,
                  borderRadius: 99,
                  background: `linear-gradient(90deg, ${C.navy}, ${C.indigo})`,
                  transition: "width 0.7s ease",
                }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>
                <Text style={{ fontSize: 12, color: C.textMuted }}>
                  <span style={{ color: C.green, fontWeight: 600 }}>{stats?.actifs ?? 0}</span> actifs
                </Text>
                <Text style={{ fontSize: 12, color: C.textMuted }}>
                  {stats?.total ?? 0} au total
                </Text>
              </div>
            </div>

           

          </div>
        </>
      )}
    </div>
  );
}
