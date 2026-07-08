/** Pure transforms from SQL result sets to Recharts-ready multi-series rows. */

import type { ExecuteResponse, WidgetViz } from '../api/types';
import { cell } from './format';

/**
 * Reserved key for the X value in chart rows. Series use synthetic keys
 * ('s0', 's1', ...) so column names (dots, collisions with 'x') can never
 * clash with Recharts dataKey parsing.
 */
export const X_KEY = '__x';

/**
 * Cap on distinct series. Equals the palette length (components/chartTheme.ts)
 * so every series keeps a unique, fixed color — colors are never cycled.
 */
export const MAX_SERIES = 9;

export interface ChartSeries {
  /** dataKey in the row objects: 's0', 's1', ... */
  key: string;
  /** Legend/tooltip label: the column name or the series value. */
  label: string;
}

export interface ChartData {
  rows: Array<Record<string, string | number | null>>;
  series: ChartSeries[];
  /** True when distinct series values exceeded MAX_SERIES and were dropped. */
  truncatedSeries: boolean;
}

export interface PieSlice {
  name: string;
  value: number;
}

/** Coerce an unknown cell into a finite number, or null when not numeric. */
export function toNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/** Names of columns whose values are at least partly numeric. */
export function numericColumns(result: ExecuteResponse): string[] {
  return result.columns
    .filter((_col, ci) => result.rows.some((row) => toNumber(row[ci]) !== null))
    .map((col) => col.name);
}

function columnIndex(result: ExecuteResponse, name: string | null): number {
  if (!name) return -1;
  return result.columns.findIndex((c) => c.name === name);
}

const EMPTY: ChartData = { rows: [], series: [], truncatedSeries: false };

/** Wide shape: one series per selected Y column. */
export function buildWideData(
  result: ExecuteResponse,
  xColumn: string,
  yColumns: string[],
  opts?: { numericX?: boolean },
): ChartData {
  const xi = columnIndex(result, xColumn);
  const yIndexes = yColumns
    .map((name) => ({ name, index: columnIndex(result, name) }))
    .filter((c) => c.index >= 0);
  if (xi < 0 || yIndexes.length === 0) return EMPTY;

  const series = yIndexes.map((c, i) => ({ key: `s${i}`, label: c.name }));
  const rows: ChartData['rows'] = [];
  for (const row of result.rows) {
    const x = opts?.numericX ? toNumber(row[xi]) : cell(row[xi]);
    if (x === null) continue;
    const out: Record<string, string | number | null> = { [X_KEY]: x };
    let hasValue = false;
    yIndexes.forEach((c, i) => {
      const y = toNumber(row[c.index]);
      out[`s${i}`] = y;
      if (y !== null) hasValue = true;
    });
    if (hasValue) rows.push(out);
  }
  return { rows, series, truncatedSeries: false };
}

/**
 * Long shape: pivot rows into one series per distinct `seriesColumn` value.
 * X groups keep first-seen order; duplicate (x, series) cells are summed;
 * series are capped at MAX_SERIES (extras dropped, `truncatedSeries` set).
 */
export function buildPivotData(
  result: ExecuteResponse,
  xColumn: string,
  yColumn: string,
  seriesColumn: string,
): ChartData {
  const xi = columnIndex(result, xColumn);
  const yi = columnIndex(result, yColumn);
  const si = columnIndex(result, seriesColumn);
  if (xi < 0 || yi < 0 || si < 0) return EMPTY;

  const seriesKeys = new Map<string, string>(); // series value -> synthetic key
  const rowsByX = new Map<string, Record<string, string | number | null>>();
  let truncated = false;

  for (const row of result.rows) {
    const y = toNumber(row[yi]);
    if (y === null) continue;
    const seriesValue = cell(row[si]);
    let key = seriesKeys.get(seriesValue);
    if (!key) {
      if (seriesKeys.size >= MAX_SERIES) {
        truncated = true;
        continue;
      }
      key = `s${seriesKeys.size}`;
      seriesKeys.set(seriesValue, key);
    }
    const x = cell(row[xi]);
    let out = rowsByX.get(x);
    if (!out) {
      out = { [X_KEY]: x };
      rowsByX.set(x, out);
    }
    const prev = out[key];
    out[key] = typeof prev === 'number' ? prev + y : y;
  }

  const series = [...seriesKeys.entries()].map(([label, key]) => ({ key, label }));
  return { rows: [...rowsByX.values()], series, truncatedSeries: truncated };
}

/**
 * Pie slices. 'category' mode: one slice per row (x = name, first Y = value).
 * 'columns' mode: one slice per Y column, value = the column's sum over all rows.
 */
export function buildPieData(result: ExecuteResponse, viz: WidgetViz): PieSlice[] {
  const { xColumn, yColumns } = withDefaults(result, viz);
  if (viz.pie_mode === 'columns') {
    const slices: PieSlice[] = [];
    for (const name of yColumns) {
      const ci = columnIndex(result, name);
      if (ci < 0) continue;
      let sum = 0;
      let seen = false;
      for (const row of result.rows) {
        const n = toNumber(row[ci]);
        if (n !== null) {
          sum += n;
          seen = true;
        }
      }
      if (seen) slices.push({ name, value: sum });
    }
    return slices;
  }

  const xi = columnIndex(result, xColumn);
  const yi = columnIndex(result, yColumns[0] ?? null);
  if (xi < 0 || yi < 0) return [];
  const slices: PieSlice[] = [];
  for (const row of result.rows) {
    const value = toNumber(row[yi]);
    if (value !== null) slices.push({ name: cell(row[xi]), value });
  }
  return slices;
}

/** Fill unset x/y selections: x = first column, y = first numeric column. */
function withDefaults(
  result: ExecuteResponse,
  viz: WidgetViz,
): { xColumn: string | null; yColumns: string[] } {
  const numeric = numericColumns(result);
  const xColumn = viz.x_column ?? result.columns[0]?.name ?? null;
  const yColumns =
    viz.y_columns.length > 0
      ? viz.y_columns
      : numeric[0]
        ? [numeric[0]]
        : result.columns[0]
          ? [result.columns[0].name]
          : [];
  return { xColumn, yColumns };
}

/** Dispatcher: picks wide vs pivot from the viz, applying auto-defaults. */
export function buildChartData(result: ExecuteResponse, viz: WidgetViz): ChartData {
  const { xColumn, yColumns } = withDefaults(result, viz);
  const firstY = yColumns[0];
  if (!xColumn || !firstY) return EMPTY;
  if (viz.series_column && columnIndex(result, viz.series_column) >= 0) {
    return buildPivotData(result, xColumn, firstY, viz.series_column);
  }
  return buildWideData(result, xColumn, yColumns, {
    numericX: viz.view === 'scatter',
  });
}
