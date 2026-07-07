import { Fragment, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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


/**
 * Microsoft Clarity integration settings: API token, daily fetch schedule,
 * which dimension combinations to spend the 10-requests/day budget on,
 * a manual "Fetch now" trigger, and the fetch-run history.
 */
export default function AdminClaritySection() {
  const { t } = useTranslation('admin');
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

  const comboLabel = (combo: string[]) =>
    combo.length ? combo.join(' + ') : t('clarity.overall');

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">Microsoft Clarity</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          {t('refresh')}
        </button>
      </div>
      <p className="muted">{t('clarity.description', { budget: status?.daily_budget ?? 10 })}</p>

      <ErrorBanner message={loadError} />

      {loading ? (
        <Spinner label={t('clarity.loading')} />
      ) : (
        <>
          {status && (
            <InfoBanner>
              {t('clarity.requestsUsedToday', {
                used: status.requests_used_today,
                budget: status.daily_budget,
              })}
              {' · '}
              {t('clarity.nextFetch', {
                next: status.next_run_at ? formatDate(status.next_run_at) : '—',
              })}
              {' · '}
              {t('clarity.latestData', {
                latest: status.latest_data_date ?? t('clarity.noneYet'),
              })}{' '}
              ({t('clarity.daysStored', { count: status.days_stored })})
            </InfoBanner>
          )}

          <form className="invite-form" onSubmit={handleSave}>
            <label className="field">
              <span>{t('clarity.apiToken')}</span>
              <input
                type="password"
                value={token}
                placeholder={
                  settings?.token_set
                    ? t('clarity.tokenSetPlaceholder')
                    : t('clarity.tokenPlaceholder')
                }
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>{t('clarity.projectId')}</span>
              <input type="text" value={projectId} onChange={(e) => setProjectId(e.target.value)} />
            </label>
            <label className="field">
              <span>{t('clarity.fetchTime')}</span>
              <input
                type="time"
                required
                value={fetchTime}
                onChange={(e) => setFetchTime(e.target.value)}
              />
            </label>
            <label className="field">
              <span>{t('clarity.timezone')}</span>
              <input
                type="text"
                required
                value={timezone}
                placeholder={t('clarity.timezonePlaceholder')}
                onChange={(e) => setTimezone(e.target.value)}
              />
            </label>

            <div className="subsection">
              <h3>{t('clarity.combosTitle', { count: combos.length, max: 10 })}</h3>
              <p className="muted">{t('clarity.combosDescription')}</p>
              {combos.map((combo, i) => (
                <div key={i} className="row-actions" style={{ marginBottom: '0.5rem' }}>
                  {[0, 1, 2].map((d) => (
                    <select
                      key={d}
                      value={combo[d] ?? ''}
                      onChange={(e) => setComboDimension(i, d, e.target.value)}
                      aria-label={t('clarity.comboAria', { combo: i + 1, dimension: d + 1 })}
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
                    {t('clarity.remove')}
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
                  {t('clarity.addCombination')}
                </button>
                <button
                  type="button"
                  className="btn btn--small btn--ghost"
                  onClick={() => setCombos(DEFAULT_COMBOS)}
                >
                  {t('clarity.restoreDefaults')}
                </button>
              </div>
            </div>

            <div className="row-actions">
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? t('clarity.saving') : t('clarity.saveSettings')}
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={fetching || !settings?.token_set}
                title={settings?.token_set ? undefined : t('clarity.saveTokenFirst')}
                onClick={() => void handleFetchNow()}
              >
                {fetching ? t('clarity.fetching') : t('clarity.fetchNow')}
              </button>
            </div>
            {saved && <InfoBanner>{t('clarity.settingsSaved')}</InfoBanner>}
            <ErrorBanner message={saveError} />
            <ErrorBanner message={fetchError} />
          </form>

          <div className="subsection">
            <h3>{t('clarity.historyTitle')}</h3>
            {runs.length === 0 ? (
              <p className="muted">{t('clarity.noFetches')}</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t('clarity.colStarted')}</th>
                      <th>{t('clarity.colDataDate')}</th>
                      <th>{t('clarity.colTrigger')}</th>
                      <th>{t('clarity.colStatus')}</th>
                      <th>{t('clarity.colRequests')}</th>
                      <th aria-label={t('clarity.colDetails')} />
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
                              {expandedRun === run.id ? t('clarity.hide') : t('clarity.details')}
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
