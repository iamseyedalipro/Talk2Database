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
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('admin');
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
        { label: t('usage.totalTokens'), value: totals.total_tokens },
        { label: t('usage.input'), value: totals.input_tokens },
        { label: t('usage.output'), value: totals.output_tokens },
        { label: t('usage.cacheRead'), value: totals.cache_read_tokens },
        { label: t('usage.cacheWrite'), value: totals.cache_write_tokens },
        { label: t('usage.apiCalls'), value: totals.call_count },
      ]
    : [];

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">{t('usage.title')}</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          {t('refresh')}
        </button>
      </div>
      <p className="muted">{t('usage.description')}</p>

      <div className="audit-filters">
        <label className="field field--inline">
          <span>{t('usage.from')}</span>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field field--inline">
          <span>{t('usage.to')}</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <Spinner label={t('usage.loading')} />
      ) : !report || report.totals.call_count === 0 ? (
        <p className="muted">{t('usage.empty')}</p>
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

          <h3 className="usage-subhead">{t('usage.tokensPerDay')}</h3>
          <div className="usage-chart">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={report.daily} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={formatTokens} />
                <Tooltip formatter={(v: number) => numberFormat.format(v)} />
                <Bar
                  dataKey="total_tokens"
                  name={t('usage.totalTokens')}
                  fill={CHART_COLOR}
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <UsageBreakdown title={t('usage.byUser')} head={t('usage.headUser')} rows={report.by_user} />
          <UsageBreakdown title={t('usage.byModel')} head={t('usage.headModel')} rows={report.by_model} />
          <UsageBreakdown
            title={t('usage.byProvider')}
            head={t('usage.headProvider')}
            rows={report.by_provider}
          />
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
  const { t } = useTranslation('admin');
  if (rows.length === 0) return null;
  return (
    <>
      <h3 className="usage-subhead">{title}</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{head}</th>
              <th>{t('usage.colInput')}</th>
              <th>{t('usage.colOutput')}</th>
              <th>{t('usage.colCacheRead')}</th>
              <th>{t('usage.colCacheWrite')}</th>
              <th>{t('usage.colTotal')}</th>
              <th>{t('usage.colCalls')}</th>
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
