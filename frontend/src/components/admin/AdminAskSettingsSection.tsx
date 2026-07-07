import { useEffect, useState } from 'react';
import { getAskSettings, updateAskSettings } from '../../api/endpoints';
import type { AskSettings } from '../../api/types';
import { errorMessage } from '../../utils/format';
import { ErrorBanner, InfoBanner, Spinner } from '../ui';

/**
 * Toggle "Ask analysis mode" and set the exploratory-query row cap.
 *
 * When the mode is ON, every Ask runs an investigation loop: the AI requests
 * table details on demand and may run small read-only queries whose sampled
 * rows are sent to the AI provider — a deliberate exception to the
 * schema-only default, opted into here.
 */
export default function AdminAskSettingsSection() {
  const [settings, setSettings] = useState<AskSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [analysisMode, setAnalysisMode] = useState(false);
  const [rowCap, setRowCap] = useState(10);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    getAskSettings()
      .then((res) => {
        setSettings(res);
        setAnalysisMode(res.analysis_mode);
        setRowCap(res.row_cap);
      })
      .catch((err) => setLoadError(errorMessage(err)));
  }, []);

  const handleSave = async () => {
    setSaved(false);
    setSaveError(null);
    setBusy(true);
    try {
      const res = await updateAskSettings({ analysis_mode: analysisMode, row_cap: rowCap });
      setSettings(res);
      setAnalysisMode(res.analysis_mode);
      setRowCap(res.row_cap);
      setSaved(true);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const dirty =
    settings !== null && (analysisMode !== settings.analysis_mode || rowCap !== settings.row_cap);

  return (
    <section className="card">
      <h2 className="page__title">Ask analysis mode</h2>
      <p className="muted">
        When enabled, every Ask question runs a deeper investigation: the AI scans the table
        list, requests details for the tables it needs, and runs small read-only exploratory
        queries to understand the data before writing the final SQL. Users watch each step live.
      </p>
      <p className="muted">
        ⚠ Exploratory queries send a small sample of row data (capped below) to the AI provider —
        an exception to the schema-only default that applies only while this mode is on.
      </p>

      <ErrorBanner message={loadError} />

      {settings === null && !loadError ? (
        <Spinner label="Loading Ask settings…" />
      ) : settings !== null ? (
        <>
          <label className="field field--checkbox">
            <input
              type="checkbox"
              checked={analysisMode}
              onChange={(e) => setAnalysisMode(e.target.checked)}
              aria-label="Enable Ask analysis mode"
            />{' '}
            Enable Ask analysis mode for all users
          </label>

          <label className="field">
            Max rows per exploratory query ({settings.row_cap_min}–{settings.row_cap_max})
            <input
              type="number"
              min={settings.row_cap_min}
              max={settings.row_cap_max}
              value={rowCap}
              onChange={(e) => setRowCap(Number(e.target.value))}
              aria-label="Exploratory query row cap"
            />
          </label>

          <div className="row-actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={
                busy ||
                !dirty ||
                Number.isNaN(rowCap) ||
                rowCap < settings.row_cap_min ||
                rowCap > settings.row_cap_max
              }
              onClick={() => void handleSave()}
            >
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
          {saved && <InfoBanner>Ask settings saved.</InfoBanner>}
          <ErrorBanner message={saveError} />
        </>
      ) : null}
    </section>
  );
}
