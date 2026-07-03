import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ExecuteResponse } from '../api/types';
import { cell } from '../utils/format';

export type ChartKind = 'bar' | 'line';

interface Props {
  result: ExecuteResponse;
  kind: ChartKind;
  /** AI-suggested initial axis columns; applied when they match real columns. */
  suggestedX?: string | null;
  suggestedY?: string | null;
}

interface ChartRow {
  x: string;
  y: number;
}

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
 * Renders the result set as a bar or line chart. The user picks an X column
 * (any column) and a Y column (must be numeric) from dropdowns built from the
 * result `columns`.
 */
export default function ResultsChart({ result, kind, suggestedX, suggestedY }: Props) {
  const { columns, rows } = result;

  // Columns whose values are at least partly numeric are eligible for the Y axis.
  const numericCols = useMemo(() => {
    return columns.filter((_col, ci) => rows.some((row) => toNumber(row[ci]) !== null));
  }, [columns, rows]);

  const [xName, setXName] = useState<string>(() => columns[0]?.name ?? '');
  const [yName, setYName] = useState<string>(
    () => numericCols[0]?.name ?? columns[0]?.name ?? '',
  );

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
      .map((row) => ({ x: cell(row[xIndex]), y: toNumber(row[yIndex]) }))
      .filter((d): d is ChartRow => d.y !== null);
  }, [rows, xIndex, yIndex]);

  if (columns.length === 0 || rows.length === 0) {
    return <p className="muted">Nothing to chart.</p>;
  }

  return (
    <div className="chart">
      <div className="chart__controls">
        <label className="field field--inline">
          <span>X axis</span>
          <select value={xName} onChange={(e) => setXName(e.target.value)}>
            {columns.map((col) => (
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
          No numeric values to plot for the selected Y column. Pick a numeric column.
        </p>
      ) : (
        <div className="chart__canvas">
          <ResponsiveContainer width="100%" height={360}>
            {kind === 'bar' ? (
              <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="x" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="y" name={yName} fill="#7c3aed" radius={[4, 4, 0, 0]} />
              </BarChart>
            ) : (
              <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="x" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="y"
                  name={yName}
                  stroke="#7c3aed"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
