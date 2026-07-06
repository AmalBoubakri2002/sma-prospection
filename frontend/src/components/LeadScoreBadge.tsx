import { Tooltip, Typography } from "antd";
import {
  FireOutlined, RiseOutlined, MinusCircleOutlined, StopOutlined, QuestionCircleOutlined,
} from "@ant-design/icons";
import { C } from "@/styles/tokens";

const { Text } = Typography;

// Partagé entre CampaignLeadsPage et ValidationQueuePage pour éviter que les deux dérivent.

export interface ShapFeature {
  feature: string;
  label_fr: string;
  contribution: number;
  direction: "positif" | "négatif";
}

export type ScoreLabel = "CHAUD" | "TIEDE" | "FROID" | "HORS_CIBLE";

export const LABEL_CONFIG: Record<ScoreLabel, { color: string; bg: string; icon: JSX.Element; label: string }> = {
  CHAUD:      { color: C.red,       bg: C.redBg,   icon: <FireOutlined />,        label: "Chaud"      },
  TIEDE:      { color: C.amber,     bg: C.amberBg, icon: <RiseOutlined />,        label: "Tiède"      },
  FROID:      { color: C.cyan,      bg: C.cyanBg,  icon: <MinusCircleOutlined />, label: "Froid"      },
  HORS_CIBLE: { color: C.textMuted, bg: C.bg,      icon: <StopOutlined />,        label: "Hors cible" },
};

export function formatCA(ca: number | null): string {
  if (ca === null) return "—";
  if (ca >= 1_000_000) return `${(ca / 1_000_000).toFixed(1)} M€`;
  if (ca >= 1_000) return `${Math.round(ca / 1_000)} k€`;
  return `${ca} €`;
}

// ca=0 traité comme "inconnu" (même convention que feature_spec.clean_financial_value
// côté backend) ; ne s'applique pas à resultat_net, où 0 est une vraie valeur.
export function formatCaOrUnknown(ca: number | null): string {
  return formatCA(ca === 0 ? null : ca);
}

// Signale un score calculé sur imputation médiane plutôt que des données financières confirmées.
export function hasPartialFinancials(ca: number | null, resultatNet: number | null): boolean {
  return ca === null || ca === 0 || resultatNet === null;
}

type ScoreBadgeVariant = "default" | "queue";

const SCORE_BADGE_STYLES: Record<
  ScoreBadgeVariant,
  { barWidth: number; pctSize: number; pctWeight: number; badgePad: string; badgeWeight: number }
> = {
  default: { barWidth: 56, pctSize: 13, pctWeight: 700, badgePad: "2px 8px",  badgeWeight: 600 },
  queue:   { barWidth: 52, pctSize: 14, pctWeight: 800, badgePad: "3px 10px", badgeWeight: 700 },
};

export function ScoreBadge({
  score, label, variant = "default", partial = false,
}: {
  score: number | null;
  label: ScoreLabel | null;
  variant?: ScoreBadgeVariant;
  /** true si le score a été calculé sans CA/résultat net (imputation médiane) — voir hasPartialFinancials */
  partial?: boolean;
}) {
  if (score === null || !label) return <Text style={{ color: C.textFaint }}>—</Text>;
  const cfg = LABEL_CONFIG[label];
  // Arrondi (pas floor) : le label est décidé sur le score non arrondi (predictor.py),
  // donc un % affiché peut occasionnellement sembler contredire le badge près d'un seuil.
  const pct = Math.round(score * 100);
  const s = SCORE_BADGE_STYLES[variant];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: s.barWidth, height: 6, background: C.border, borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: cfg.color, borderRadius: 3 }} />
      </div>
      <Text style={{ fontWeight: s.pctWeight, color: cfg.color, fontSize: s.pctSize, minWidth: 32 }}>{pct}%</Text>
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: s.badgePad, borderRadius: 20,
        background: cfg.bg, color: cfg.color, fontSize: 11.5, fontWeight: s.badgeWeight,
      }}>
        {cfg.icon} {cfg.label}
      </span>
      {partial && (
        <Tooltip title="CA et/ou résultat net indisponibles à la source : ce score repose en partie sur une valeur estimée, pas sur des données financières confirmées.">
          <QuestionCircleOutlined style={{ color: C.textMuted, fontSize: 13 }} />
        </Tooltip>
      )}
    </div>
  );
}
