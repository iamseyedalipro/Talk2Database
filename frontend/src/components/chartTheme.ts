/** Shared chart chrome: the series palette and Recharts style constants. */

/**
 * Qualitative series palette, brand purple first. The ORDER is the
 * colorblind-safety mechanism (validated: worst adjacent deutan ΔE 14.5 on
 * light #ffffff and dark #1e293b surfaces) — assign slots in order, never
 * shuffle or cycle. `MAX_SERIES` in utils/chartData.ts equals this length so
 * a series count never wraps the palette.
 */
export const CHART_COLORS = [
  '#7c3aed', // brand purple
  '#d97706', // amber
  '#2563eb', // blue
  '#dc2626', // red
  '#0d9488', // teal
  '#db2777', // pink
  '#65a30d', // lime
  '#0891b2', // cyan
  '#059669', // green
] as const;

export function seriesColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length] ?? CHART_COLORS[0];
}

/* Theme-aware chrome (CSS vars resolve against the light/dark theme). */
export const GRID_STROKE = 'var(--border)';
export const AXIS_TICK = { fontSize: 12, fill: 'var(--muted)' } as const;
export const AXIS_LINE = { stroke: 'var(--border)' } as const;

export const TOOLTIP_CONTENT_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text)',
  fontSize: 12,
} as const;
export const TOOLTIP_LABEL_STYLE = { color: 'var(--text)', fontWeight: 600 } as const;
export const TOOLTIP_ITEM_STYLE = { color: 'var(--text)' } as const;

export const LEGEND_STYLE = { fontSize: 12 } as const;

/** Truncate long category tick labels; the tooltip shows the full value. */
export function tickLabel(value: unknown, max = 16): string {
  const s = String(value ?? '');
  return s.length > max ? `${s.slice(0, max)}…` : s;
}
