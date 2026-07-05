import { Fragment, useCallback, useEffect, useState } from 'react';
import {
  clarityFetchNow,
  clarityStatus,
  getClaritySettings,
  listClarityRuns,
  updateClaritySettings,
} from '../../api/endpoints';
import type { ClarityRun, ClaritySettings, ClarityStatus } from '../../api/types';
import { errorMessage, formatDate } from '../../utils/format';
import { ErrorBanner, InfoBanner, Spinner, StatusPill } from '../ui';

const DEFAULT_COMBOS: string[][] = [
  [],
  ['URL'],
  ['Device'],
  ['Source'],
  ['Country/Region'],
  ['OS'],
  ['Browser'],
  ['URL', 'Device'],
];

const comboLabel = (combo: string[]) => (combo.length ? combo.join(' + ') : 'overall');

/**
 * Microsoft Clarity integration settings: API token, daily fetch schedule,
 * which dimension combinations to spend the 10-requests/day budget on,
 * a manual "Fetch now" trigger, and the fetch-run history.
 */
export default function AdminClaritySection() {
  const [settings, setSettings] = useState<ClaritySettings | null>(null);
  const [status, setStatus] = useState<ClarityStatus | null>(null);
  const [runs, setRuns] = useState<ClarityRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [token, setToken] = useState('');
  const [projectId, setProjectId] = useState('');
  const [fetchTime, setFetchTime] = useState('00:30');
  const [timezone, setTimezone] = useState('UTC');
  const [combos, setCombos] = useState<string[][]>(DEFAULT_COMBOS);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [expandedRun, setExpandedRun] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [s, st, r] = await Promise.all([
        getClaritySettings(),
        clarityStatus(),
        listClarityRuns(),
      ]);
      setSettings(s);
      setStatus(st);
      setRuns(r);
      setProjectId(s.project_id ?? '');
      setFetchTime(s.fetch_time);
      setTimezone(s.timezone);
      setCombos(s.dimension_combos);
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setSaved(false);
    setSaving(true);
    try {
      const updated = await updateClaritySettings({
        ...(token ? { api_token: token } : {}),
        project_id: projectId,
        fetch_time: fetchTime,
        timezone,
        dimension_combos: combos,
      });
      setSettings(updated);
      setToken('');
      setSaved(true);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleFetchNow = async () => {
    setFetchError(null);
    setFetching(true);
    try {
      await clarityFetchNow();
      await load();
    } catch (err) {
      setFetchError(errorMessage(err));
    } finally {
      setFetching(false);
    }
  };

  const setComboDimension = (comboIndex: number, dimIndex: number, value: string) => {
    setCombos((prev) =>
      prev.map((combo, i) => {
        if (i !== comboIndex) return combo;
        const next = combo.slice(0, 3);
        if (value) {
          next[dimIndex] = value;
        } else {
          next.splice(dimIndex, 1);
        }
        return next.filter(Boolean);
      }),
    );
  };

  const allowedDimensions = settings?.allowed_dimensions ?? [];

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">Microsoft Clarity</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <p className="muted">
        Every day at the configured time, the panel fetches the previous day’s Clarity data.
        Clarity allows only {status?.daily_budget ?? 10} API requests per day; each dimension
        combination below costs one request.
      </p>

      <ErrorBanner message={loadError} />

      {loading ? (
        <Spinner label="Loading Clarity settings…" />
      ) : (
        <>
          {status && (
            <InfoBanner>
              Requests used today: {status.requests_used_today}/{status.daily_budget}
              {' · '}Next scheduled fetch: {status.next_run_at ? formatDate(status.next_run_at) : '—'}
              {' · '}Latest data: {status.latest_data_date ?? 'none yet'} ({status.days_stored} day
              {status.days_stored === 1 ? '' : 's'} stored)
            </InfoBanner>
          )}

          <form className="invite-form" onSubmit={handleSave}>
            <label className="field">
              <span>API token</span>
              <input
                type="password"
                value={token}
                placeholder={
                  settings?.token_set ? 'Token is set — enter a new one to replace it' : 'Paste your Clarity Data Export token'
                }
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>Project ID (optional)</span>
              <input type="text" value={projectId} onChange={(e) => setProjectId(e.target.value)} />
            </label>
            <label className="field">
              <span>Fetch time</span>
              <input
                type="time"
                required
                value={fetchTime}
                onChange={(e) => setFetchTime(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Timezone (IANA)</span>
              <input
                type="text"
                required
                value={timezone}
                placeholder="e.g. UTC or Europe/Berlin"
                onChange={(e) => setTimezone(e.target.value)}
              />
            </label>

            <div className="subsection">
              <h3>Daily dimension combinations ({combos.length}/10)</h3>
              <p className="muted">
                Each row is one API request fetching yesterday’s metrics broken down by up to 3
                dimensions. An empty row fetches overall totals.
              </p>
              {combos.map((combo, i) => (
                <div key={i} className="row-actions" style={{ marginBottom: '0.5rem' }}>
                  {[0, 1, 2].map((d) => (
                    <select
                      key={d}
                      value={combo[d] ?? ''}
                      onChange={(e) => setComboDimension(i, d, e.target.value)}
                      aria-label={`Combination ${i + 1}, dimension ${d + 1}`}
                    >
                      <option value="">—</option>
                      {allowedDimensions.map((dim) => (
                        <option key={dim} value={dim}>
                          {dim}
                        </option>
                      ))}
                    </select>
                  ))}
                  <span className="muted">{comboLabel(combo)}</span>
                  <button
                    type="button"
                    className="btn btn--small btn--danger"
                    onClick={() => setCombos((prev) => prev.filter((_, x) => x !== i))}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <div className="row-actions">
                <button
                  type="button"
                  className="btn btn--small btn--secondary"
                  disabled={combos.length >= 10}
                  onClick={() => setCombos((prev) => [...prev, []])}
                >
                  Add combination
                </button>
                <button
                  type="button"
                  className="btn btn--small btn--ghost"
                  onClick={() => setCombos(DEFAULT_COMBOS)}
                >
                  Restore defaults
                </button>
              </div>
            </div>

            <div className="row-actions">
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Saving…' : 'Save Clarity settings'}
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={fetching || !settings?.token_set}
                title={settings?.token_set ? undefined : 'Save an API token first'}
                onClick={() => void handleFetchNow()}
              >
                {fetching ? 'Fetching…' : 'Fetch now'}
              </button>
            </div>
            {saved && <InfoBanner>Settings saved.</InfoBanner>}
            <ErrorBanner message={saveError} />
            <ErrorBanner message={fetchError} />
          </form>

          <div className="subsection">
            <h3>Fetch history</h3>
            {runs.length === 0 ? (
              <p className="muted">No fetches yet.</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Started</th>
                      <th>Data date</th>
                      <th>Trigger</th>
                      <th>Status</th>
                      <th>Requests</th>
                      <th aria-label="Details" />
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => (
                      <Fragment key={run.id}>
                        <tr>
                          <td>{formatDate(run.created_at)}</td>
                          <td>{run.data_date}</td>
                          <td>{run.trigger}</td>
                          <td>
                            <StatusPill status={run.status} />
                          </td>
                          <td>
                            {run.requests_succeeded}/{run.requests_attempted}
                          </td>
                          <td className="row-actions">
                            <button
                              type="button"
                              className="btn btn--small btn--ghost"
                              onClick={() =>
                                setExpandedRun((prev) => (prev === run.id ? null : run.id))
                              }
                            >
                              {expandedRun === run.id ? 'Hide' : 'Details'}
                            </button>
                          </td>
                        </tr>
                        {expandedRun === run.id && (
                          <tr>
                            <td colSpan={6}>
                              {run.error_summary && (
                                <ErrorBanner message={run.error_summary} />
                              )}
                              <ul>
                                {run.snapshots.map((snap) => (
                                  <li key={snap.combo_key}>
                                    <StatusPill status={snap.status} /> {snap.combo_key}
                                    {snap.error ? ` — ${snap.error}` : ''}
                                  </li>
                                ))}
                              </ul>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
