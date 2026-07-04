import { useCallback, useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getUsageReport } from '../../api/endpoints';
import type { UsageByKey, UsageReport } from '../../api/types';
import { errorMessage } from '../../utils/format';
import { ErrorBanner, Spinner } from '../ui';

const CHART_COLOR = '#7c3aed';

const numberFormat = new Intl.NumberFormat();

/** Human-friendly token count: 1.2M / 34.5K / 812. */
function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

interface Tile {
  label: string;
  value: number;
}

/**
 * Admin-only LLM token-usage monitor. Shows summed totals, a per-day chart, and
 * per-user / per-model / per-provider breakdowns over a date window (default:
 * the last 30 days). Usage is captured on every provider call server-side.
 */
export default function AdminTokenUsageSection() {
  const [report, setReport] = useState<UsageReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getUsageReport({
        from: from ? new Date(from).toISOString() : undefined,
        to: to ? new Date(to).toISOString() : undefined,
      });
      setReport(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  const totals = report?.totals;
  const tiles: Tile[] = totals
    ? [
        { label: 'Total tokens', value: totals.total_tokens },
        { label: 'Input', value: totals.input_tokens },
        { label: 'Output', value: totals.output_tokens },
        { label: 'Cache read', value: totals.cache_read_tokens },
        { label: 'Cache write', value: totals.cache_write_tokens },
        { label: 'API calls', value: totals.call_count },
      ]
    : [];

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">Token usage</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <p className="muted">
        LLM token usage across all users. Captured on every provider call (SQL generation,
        result summaries, and suggested questions).
      </p>

      <div className="audit-filters">
        <label className="field field--inline">
          <span>From</span>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field field--inline">
          <span>To</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <Spinner label="Loading token usage…" />
      ) : !report || report.totals.call_count === 0 ? (
        <p className="muted">No token usage recorded for this period yet.</p>
      ) : (
        <>
          <dl className="status-grid">
            {tiles.map((t) => (
              <div key={t.label}>
                <dt>{t.label}</dt>
                <dd title={numberFormat.format(t.value)}>{formatTokens(t.value)}</dd>
              </div>
            ))}
          </dl>

          <h3 className="usage-subhead">Tokens per day</h3>
          <div className="usage-chart">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={report.daily} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={formatTokens} />
                <Tooltip formatter={(v: number) => numberFormat.format(v)} />
                <Bar
                  dataKey="total_tokens"
                  name="Total tokens"
                  fill={CHART_COLOR}
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <UsageBreakdown title="By user" head="User" rows={report.by_user} />
          <UsageBreakdown title="By model" head="Model" rows={report.by_model} />
          <UsageBreakdown title="By provider" head="Provider" rows={report.by_provider} />
        </>
      )}
    </section>
  );
}

function UsageBreakdown({
  title,
  head,
  rows,
}: {
  title: string;
  head: string;
  rows: UsageByKey[];
}) {
  if (rows.length === 0) return null;
  return (
    <>
      <h3 className="usage-subhead">{title}</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{head}</th>
              <th>Input</th>
              <th>Output</th>
              <th>Cache read</th>
              <th>Cache write</th>
              <th>Total</th>
              <th>Calls</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td title={r.label}>{r.label}</td>
                <td>{numberFormat.format(r.input_tokens)}</td>
                <td>{numberFormat.format(r.output_tokens)}</td>
                <td>{numberFormat.format(r.cache_read_tokens)}</td>
                <td>{numberFormat.format(r.cache_write_tokens)}</td>
                <td>{numberFormat.format(r.total_tokens)}</td>
                <td>{numberFormat.format(r.call_count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
