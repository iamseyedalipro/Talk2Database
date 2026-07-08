import type { ResultSummary, WidgetView, WidgetViz } from '../api/types';

/** A complete viz config with every field at its default. */
export function defaultViz(view: WidgetView = 'table'): WidgetViz {
  return {
    view,
    x_column: null,
    y_columns: [],
    series_column: null,
    stacked: 'none',
    combo_types: {},
    right_axis: [],
    pie_mode: 'category',
    y_column: null,
  };
}

/**
 * Accepts an old `{view, x_column, y_column}` config, a partial config, or
 * nothing, and returns a complete WidgetViz. Legacy `y_column` folds into
 * `y_columns`; a set `series_column` forces a single Y column (the long shape
 * pivots one value column into a series per category value).
 */
export function normalizeViz(raw: Partial<WidgetViz> | null | undefined): WidgetViz {
  const base = defaultViz(raw?.view ?? 'table');
  if (!raw) return base;

  const yColumns =
    raw.y_columns && raw.y_columns.length > 0
      ? [...raw.y_columns]
      : raw.y_column
        ? [raw.y_column]
        : [];
  const seriesColumn = raw.series_column ?? null;

  return {
    ...base,
    x_column: raw.x_column ?? null,
    y_columns: seriesColumn ? yColumns.slice(0, 1) : yColumns,
    series_column: seriesColumn,
    stacked: raw.stacked ?? 'none',
    combo_types: raw.combo_types ? { ...raw.combo_types } : {},
    right_axis: raw.right_axis ? [...raw.right_axis] : [],
    pie_mode: raw.pie_mode ?? 'category',
    y_column: yColumns[0] ?? null,
  };
}

/**
 * Maps an AI result summary onto a viz config, or null when the suggestion is
 * not a renderable chart.
 */
export function vizFromSummary(summary: ResultSummary): WidgetViz | null {
  if (summary.chart_type === 'table' || summary.chart_type === 'none') return null;
  const comboTypes: WidgetViz['combo_types'] = {};
  if (summary.chart_type === 'combo') {
    for (const col of summary.combo_line_columns ?? []) comboTypes[col] = 'line';
  }
  return normalizeViz({
    view: summary.chart_type,
    x_column: summary.x_column,
    y_columns: summary.y_columns ?? undefined,
    y_column: summary.y_column,
    series_column: summary.series_column,
    stacked: summary.stacked ? 'stacked' : 'none',
    combo_types: comboTypes,
  });
}
