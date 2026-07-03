import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { ExecuteResponse } from '../api/types';
import { cell } from '../utils/format';

export type ChartKind = 'bar' | 'line' | 'area' | 'pie' | 'scatter' | 'hbar';

interface Props {
  result: ExecuteResponse;
  kind: ChartKind;
  /** AI-suggested initial axis columns; applied when they match real columns. */
  suggestedX?: string | null;
  suggestedY?: string | null;
}

interface ChartRow {
  x: string | number;
  y: number;
}

const CHART_COLOR = '#7c3aed';
// A qualitative palette for pie slices; starts at the brand purple.
const PIE_COLORS = [
  '#7c3aed',
  '#2563eb',
  '#059669',
  '#d97706',
  '#dc2626',
  '#0891b2',
  '#db2777',
  '#65a30d',
  '#9333ea',
  '#0d9488',
];

/** Coerce an unknown cell into a finite number, or null when not numeric. */
function toNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/**
 * Renders the result set as a bar, horizontal bar, line, area, pie, or scatter
 * chart. The user picks an X column and a Y column (numeric) from dropdowns built
 * from the result `columns`. Scatter treats X as numeric too.
 */
export default function ResultsChart({ result, kind, suggestedX, suggestedY }: Props) {
  const { columns, rows } = result;

  // Columns whose values are at least partly numeric are eligible for the Y axis
  // (and, for scatter, the X axis).
  const numericCols = useMemo(() => {
    return columns.filter((_col, ci) => rows.some((row) => toNumber(row[ci]) !== null));
  }, [columns, rows]);

  const numericX = kind === 'scatter';
  const xOptions = numericX ? (numericCols.length > 0 ? numericCols : columns) : columns;

  const [xName, setXName] = useState<string>(() => columns[0]?.name ?? '');
  const [yName, setYName] = useState<string>(
    () => numericCols[0]?.name ?? columns[0]?.name ?? '',
  );

  // Keep the X selection valid for the current kind (scatter needs a numeric X).
  useEffect(() => {
    if (numericX && !xOptions.some((c) => c.name === xName)) {
      setXName(xOptions[0]?.name ?? '');
    }
  }, [numericX, xOptions, xName]);

  // Apply an AI suggestion when it names a column that actually exists.
  useEffect(() => {
    if (suggestedX && columns.some((c) => c.name === suggestedX)) setXName(suggestedX);
  }, [suggestedX, columns]);
  useEffect(() => {
    if (suggestedY && columns.some((c) => c.name === suggestedY)) setYName(suggestedY);
  }, [suggestedY, columns]);

  const xIndex = columns.findIndex((c) => c.name === xName);
  const yIndex = columns.findIndex((c) => c.name === yName);

  const data: ChartRow[] = useMemo(() => {
    if (xIndex < 0 || yIndex < 0) return [];
    return rows
      .map((row) => ({
        x: numericX ? toNumber(row[xIndex]) : cell(row[xIndex]),
        y: toNumber(row[yIndex]),
      }))
      .filter((d): d is ChartRow => d.y !== null && d.x !== null);
  }, [rows, xIndex, yIndex, numericX]);

  if (columns.length === 0 || rows.length === 0) {
    return <p className="muted">Nothing to chart.</p>;
  }

  const margin = { top: 8, right: 16, bottom: 8, left: 0 };
  const grid = <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />;

  const renderChart = () => {
    switch (kind) {
      case 'bar':
        return (
          <BarChart data={data} margin={margin}>
            {grid}
            <XAxis dataKey="x" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="y" name={yName} fill={CHART_COLOR} radius={[4, 4, 0, 0]} />
          </BarChart>
        );
      case 'hbar':
        return (
          <BarChart data={data} layout="vertical" margin={{ ...margin, left: 24 }}>
            {grid}
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="x" tick={{ fontSize: 12 }} width={120} />
            <Tooltip />
            <Bar dataKey="y" name={yName} fill={CHART_COLOR} radius={[0, 4, 4, 0]} />
          </BarChart>
        );
      case 'line':
        return (
          <LineChart data={data} margin={margin}>
            {grid}
            <XAxis dataKey="x" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="y"
              name={yName}
              stroke={CHART_COLOR}
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        );
      case 'area':
        return (
          <AreaChart data={data} margin={margin}>
            {grid}
            <XAxis dataKey="x" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Area
              type="monotone"
              dataKey="y"
              name={yName}
              stroke={CHART_COLOR}
              fill={CHART_COLOR}
              fillOpacity={0.2}
              strokeWidth={2}
            />
          </AreaChart>
        );
      case 'pie':
        return (
          <PieChart margin={margin}>
            <Tooltip />
            <Legend />
            <Pie
              data={data}
              dataKey="y"
              nameKey="x"
              cx="50%"
              cy="50%"
              outerRadius={120}
              innerRadius={60}
              paddingAngle={1}
            >
              {data.map((_entry, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        );
      case 'scatter':
        return (
          <ScatterChart margin={{ ...margin, bottom: 16, left: 8 }}>
            {grid}
            <XAxis type="number" dataKey="x" name={xName} tick={{ fontSize: 12 }} />
            <YAxis type="number" dataKey="y" name={yName} tick={{ fontSize: 12 }} />
            <ZAxis range={[60, 60]} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} />
            <Scatter data={data} name={yName} fill={CHART_COLOR} />
          </ScatterChart>
        );
    }
  };

  return (
    <div className="chart">
      <div className="chart__controls">
        <label className="field field--inline">
          <span>{numericX ? 'X axis (numeric)' : 'X axis'}</span>
          <select value={xName} onChange={(e) => setXName(e.target.value)}>
            {xOptions.map((col) => (
              <option key={col.name} value={col.name}>
                {col.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field field--inline">
          <span>Y axis (numeric)</span>
          <select value={yName} onChange={(e) => setYName(e.target.value)}>
            {(numericCols.length > 0 ? numericCols : columns).map((col) => (
              <option key={col.name} value={col.name}>
                {col.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {data.length === 0 ? (
        <p className="muted">
          No numeric values to plot for the selected column{numericX ? 's' : ''}. Pick a
          numeric column.
        </p>
      ) : (
        <div className="chart__canvas">
          <ResponsiveContainer width="100%" height={360}>
            {renderChart()}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
