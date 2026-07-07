import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('admin');
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
      <h2 className="page__title">{t('askSettings.title')}</h2>
      <p className="muted">{t('askSettings.intro')}</p>
      <p className="muted">{t('askSettings.warning')}</p>

      <ErrorBanner message={loadError} />

      {settings === null && !loadError ? (
        <Spinner label={t('askSettings.loading')} />
      ) : settings !== null ? (
        <>
          <label className="field field--checkbox">
            <input
              type="checkbox"
              checked={analysisMode}
              onChange={(e) => setAnalysisMode(e.target.checked)}
              aria-label={t('askSettings.enableAria')}
            />{' '}
            {t('askSettings.enable')}
          </label>

          <label className="field">
            {t('askSettings.rowCapLabel', { min: settings.row_cap_min, max: settings.row_cap_max })}
            <input
              type="number"
              min={settings.row_cap_min}
              max={settings.row_cap_max}
              value={rowCap}
              onChange={(e) => setRowCap(Number(e.target.value))}
              aria-label={t('askSettings.rowCapAria')}
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
              {busy ? t('askSettings.saving') : t('askSettings.save')}
            </button>
          </div>
          {saved && <InfoBanner>{t('askSettings.saved')}</InfoBanner>}
          <ErrorBanner message={saveError} />
        </>
      ) : null}
    </section>
  );
}
