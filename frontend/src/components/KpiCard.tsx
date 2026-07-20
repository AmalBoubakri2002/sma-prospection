import { C, S, R } from "@/styles/tokens";

interface KpiCardProps {
  icon:       React.ReactNode;
  label:      string;
  value:      string | number;
  accent:     string;
  iconBg:     string;
  iconColor:  string;
}

export function KpiCard({ icon, label, value, accent, iconBg, iconColor }: KpiCardProps) {
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
