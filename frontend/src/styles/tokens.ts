// Single source of truth — import from here, never hardcode design values

export const C = {
  // ─── Brand ──────────────────────────────────────────────────
  navy:       '#1b3a6b',
  navyDark:   '#122852',
  navyMid:    '#2d5fa6',
  indigo:     '#6366f1',
  indigoDark: '#4f46e5',

  // ─── Semantic status ────────────────────────────────────────
  green:      '#16a34a',
  greenBg:    '#dcfce7',
  red:        '#dc2626',
  redBg:      '#fee2e2',
  amber:      '#d97706',
  amberBg:    '#fef3c7',
  purple:     '#9333ea',
  purpleBg:   '#f3e8ff',
  cyan:       '#0891b2',
  cyanBg:     '#e0f2fe',

  // ─── Surfaces ───────────────────────────────────────────────
  bg:         '#f0f4f8',
  surface:    '#ffffff',

  // ─── Borders ────────────────────────────────────────────────
  border:     '#e8edf5',
  borderMd:   '#d0d9e8',

  // ─── Text ───────────────────────────────────────────────────
  text:       '#1e2d45',
  textSub:    '#6b87b0',
  textMuted:  '#8097b8',
  textFaint:  '#b0bdd4',
} as const

export const S = {
  card:      '0 1px 3px rgba(27,58,107,0.05), 0 4px 16px rgba(27,58,107,0.06)',
  cardHover: '0 4px 24px rgba(27,58,107,0.13)',
  nav:       '0 1px 0 #e8edf5, 0 2px 8px rgba(27,58,107,0.04)',
  btn:       '0 1px 3px rgba(27,58,107,0.12), 0 4px 12px rgba(27,58,107,0.16)',
  sidebar:   '3px 0 20px rgba(0,0,0,0.10)',
  modal:     '0 8px 40px rgba(27,58,107,0.16)',
} as const

export const R = {
  sm:   6,
  md:   8,
  lg:   12,
  card: 14,
  xl:   18,
} as const

// Spacing scale (4px base)
export const SP = {
  1: 4,  2: 8,  3: 12, 4: 16, 5: 20,
  6: 24, 7: 28, 8: 32, 9: 36, 10: 40,
} as const
