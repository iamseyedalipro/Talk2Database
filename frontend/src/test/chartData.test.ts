import { describe, expect, it } from 'vitest';
import type { ExecuteResponse } from '../api/types';
import {
  MAX_SERIES,
  X_KEY,
  buildChartData,
  buildPieData,
  buildPivotData,
  buildWideData,
  numericColumns,
  toNumber,
} from '../utils/chartData';
import { compactNumber, fullNumber, percent } from '../utils/format';
import { defaultViz, normalizeViz, vizFromSummary } from '../utils/viz';
import type { ResultSummary } from '../api/types';

const result = (columns: string[], rows: unknown[][]): ExecuteResponse => ({
  columns: columns.map((name) => ({ name, type: 'text' })),
  rows,
  row_count: rows.length,
  truncated: false,
  elapsed_ms: 1,
});

describe('toNumber / numericColumns', () => {
  it('coerces numeric strings and rejects the rest', () => {
    expect(toNumber('42')).toBe(42);
    expect(toNumber(3.5)).toBe(3.5);
    expect(toNumber('abc')).toBeNull();
    expect(toNumber('')).toBeNull();
    expect(toNumber(null)).toBeNull();
    expect(toNumber(Infinity)).toBeNull();
  });

  it('finds partly-numeric columns', () => {
    const r = result(['name', 'total'], [['a', 1], ['b', 'x']]);
    expect(numericColumns(r)).toEqual(['total']);
  });
});

describe('buildWideData', () => {
  const r = result(
    ['month', 'a_sales', 'b_sales'],
    [
      ['Jan', 10, 20],
      ['Feb', '15', 25],
      ['Mar', null, null],
    ],
  );

  it('builds one series per Y column, in order', () => {
    const data = buildWideData(r, 'month', ['a_sales', 'b_sales']);
    expect(data.series).toEqual([
      { key: 's0', label: 'a_sales' },
      { key: 's1', label: 'b_sales' },
    ]);
    expect(data.rows).toEqual([
      { [X_KEY]: 'Jan', s0: 10, s1: 20 },
      { [X_KEY]: 'Feb', s0: 15, s1: 25 },
    ]);
  });

  it('drops unknown Y columns and returns empty when none remain', () => {
    expect(buildWideData(r, 'month', ['nope']).rows).toEqual([]);
  });

  it('forces numeric X when asked (scatter)', () => {
    const rn = result(['x', 'y'], [['1', 2], ['oops', 3]]);
    const data = buildWideData(rn, 'x', ['y'], { numericX: true });
    expect(data.rows).toEqual([{ [X_KEY]: 1, s0: 2 }]);
  });
});

describe('buildPivotData', () => {
  it('pivots long data into one series per category, first-seen order', () => {
    const r = result(
      ['month', 'product', 'sales'],
      [
        ['Jan', 'A', 1],
        ['Jan', 'B', 2],
        ['Feb', 'A', 3],
        ['Feb', 'B', 4],
      ],
    );
    const data = buildPivotData(r, 'month', 'sales', 'product');
    expect(data.series).toEqual([
      { key: 's0', label: 'A' },
      { key: 's1', label: 'B' },
    ]);
    expect(data.rows).toEqual([
      { [X_KEY]: 'Jan', s0: 1, s1: 2 },
      { [X_KEY]: 'Feb', s0: 3, s1: 4 },
    ]);
  });

  it('sums duplicate (x, series) cells', () => {
    const r = result(
      ['month', 'product', 'sales'],
      [
        ['Jan', 'A', 1],
        ['Jan', 'A', 2],
      ],
    );
    const data = buildPivotData(r, 'month', 'sales', 'product');
    expect(data.rows).toEqual([{ [X_KEY]: 'Jan', s0: 3 }]);
  });

  it('caps series at MAX_SERIES and flags truncation', () => {
    const rows = Array.from({ length: MAX_SERIES + 3 }, (_v, i) => ['Jan', `p${i}`, i]);
    const data = buildPivotData(result(['month', 'product', 'sales'], rows), 'month', 'sales', 'product');
    expect(data.series).toHaveLength(MAX_SERIES);
    expect(data.truncatedSeries).toBe(true);
  });
});

describe('buildPieData', () => {
  const r = result(
    ['category', 'sales', 'cost'],
    [
      ['A', 10, 4],
      ['B', 20, 6],
    ],
  );

  it('category mode: one slice per row', () => {
    const viz = normalizeViz({ view: 'pie', x_column: 'category', y_columns: ['sales'] });
    expect(buildPieData(r, viz)).toEqual([
      { name: 'A', value: 10 },
      { name: 'B', value: 20 },
    ]);
  });

  it('columns mode: one slice per Y column, summed', () => {
    const viz = normalizeViz({
      view: 'pie',
      pie_mode: 'columns',
      y_columns: ['sales', 'cost'],
    });
    expect(buildPieData(r, viz)).toEqual([
      { name: 'sales', value: 30 },
      { name: 'cost', value: 10 },
    ]);
  });
});

describe('buildChartData dispatcher', () => {
  it('applies auto-defaults: first column X, first numeric Y', () => {
    const r = result(['name', 'total'], [['a', 5]]);
    const data = buildChartData(r, defaultViz('bar'));
    expect(data.series).toEqual([{ key: 's0', label: 'total' }]);
    expect(data.rows).toEqual([{ [X_KEY]: 'a', s0: 5 }]);
  });

  it('routes to the pivot when series_column is set', () => {
    const r = result(
      ['month', 'product', 'sales'],
      [
        ['Jan', 'A', 1],
        ['Jan', 'B', 2],
      ],
    );
    const viz = normalizeViz({
      view: 'line',
      x_column: 'month',
      y_columns: ['sales'],
      series_column: 'product',
    });
    expect(buildChartData(r, viz).series.map((s) => s.label)).toEqual(['A', 'B']);
  });
});

describe('normalizeViz / vizFromSummary', () => {
  it('folds legacy y_column into y_columns', () => {
    const viz = normalizeViz({ view: 'bar', x_column: 'day', y_column: 'orders' });
    expect(viz.y_columns).toEqual(['orders']);
    expect(viz.y_column).toBe('orders');
    expect(viz.stacked).toBe('none');
  });

  it('forces a single Y column when series_column is set', () => {
    const viz = normalizeViz({
      view: 'line',
      y_columns: ['a', 'b'],
      series_column: 'product',
    });
    expect(viz.y_columns).toEqual(['a']);
  });

  const summary = (over: Partial<ResultSummary>): ResultSummary => ({
    summary: 's',
    chart_type: 'line',
    x_column: 'month',
    y_column: null,
    y_columns: ['sales'],
    series_column: null,
    stacked: false,
    combo_line_columns: null,
    ...over,
  });

  it('maps an AI summary onto a viz', () => {
    const viz = vizFromSummary(summary({ series_column: 'product', stacked: true }));
    expect(viz).not.toBeNull();
    expect(viz?.view).toBe('line');
    expect(viz?.series_column).toBe('product');
    expect(viz?.stacked).toBe('stacked');
  });

  it('maps combo_line_columns onto combo_types', () => {
    const viz = vizFromSummary(
      summary({ chart_type: 'combo', y_columns: ['revenue', 'growth'], combo_line_columns: ['growth'] }),
    );
    expect(viz?.combo_types).toEqual({ growth: 'line' });
  });

  it('returns null for table/none', () => {
    expect(vizFromSummary(summary({ chart_type: 'none' }))).toBeNull();
    expect(vizFromSummary(summary({ chart_type: 'table' }))).toBeNull();
  });
});

describe('number formatters', () => {
  it('compacts large numbers', () => {
    expect(compactNumber(950)).toBe('950');
    expect(compactNumber(1200)).toBe('1.2K');
    expect(compactNumber(3400000)).toBe('3.4M');
  });

  it('groups full numbers and formats percents', () => {
    expect(fullNumber(1234567.891)).toBe('1,234,567.89');
    expect(percent(0.4567)).toBe('45.7%');
  });
});
