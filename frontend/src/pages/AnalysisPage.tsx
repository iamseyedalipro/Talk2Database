import { useEffect, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { clarityAvailability, listConnections, runAnalysis } from '../api/endpoints';
import type { AnalysisResponse, ClarityAvailability, Connection } from '../api/types';
import { ErrorBanner, Spinner } from '../components/ui';
import { errorMessage } from '../utils/format';

/**
 * Data analysis: the user asks an analytical question ("why don't users click
 * on any podcast?"), selects which data sources the AI may use (stored Clarity
 * metrics and/or their database connections), and gets an answer grounded in
 * that data — along with every SQL query the AI ran to reach it.
 */
export default function AnalysisPage() {
  const { t } = useTranslation('analysis');
  const [connections, setConnections] = useState<Connection[]>([]);
  const [clarity, setClarity] = useState<ClarityAvailability | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [useClarity, setUseClarity] = useState(false);
  const [question, setQuestion] = useState('');

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [showSteps, setShowSteps] = useState(false);

  useEffect(() => {
    listConnections()
      .then(setConnections)
      .catch((err) => setLoadError(errorMessage(err)));
    clarityAvailability()
      .then((availability) => {
        setClarity(availability);
        if (availability.available) setUseClarity(true);
      })
      .catch((err) => setLoadError(errorMessage(err)));
  }, []);

  const toggleConnection = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const noSources = selectedIds.length === 0 && !useClarity;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || noSources) return;
    setRunError(null);
    setResult(null);
    setShowSteps(false);
    setRunning(true);
    try {
      const res = await runAnalysis({
        question: question.trim(),
        connection_ids: selectedIds,
        include_clarity: useClarity,
      });
      setResult(res);
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="page">
      <section className="card">
        <h1 className="page__title">{t('title')}</h1>
        <p className="muted">{t('intro')}</p>

        <ErrorBanner message={loadError} />

        <form className="ask-form" onSubmit={handleSubmit}>
          <fieldset className="analysis-sources">
            <legend>{t('dataSources')}</legend>
            <label className="analysis-source">
              <input
                type="checkbox"
                checked={useClarity}
                disabled={!clarity?.available}
                onChange={(e) => setUseClarity(e.target.checked)}
              />
              <span>
                Microsoft Clarity{' '}
                {clarity?.available ? (
                  <span className="muted">
                    {t('clarityStored', {
                      date: clarity.latest_data_date,
                      count: clarity.days_stored,
                    })}
                  </span>
                ) : (
                  <span className="muted">{t('clarityUnavailable')}</span>
                )}
              </span>
            </label>
            {connections.map((c) => (
              <label key={c.id} className="analysis-source">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(c.id)}
                  onChange={() => toggleConnection(c.id)}
                />
                <span>
                  {c.name} <span className="muted">({c.type})</span>
                </span>
              </label>
            ))}
            {connections.length === 0 && (
              <p className="muted">
                <Trans
                  t={t}
                  i18nKey="noConnections"
                  components={{ link: <Link to="/connections" /> }}
                />
              </p>
            )}
          </fieldset>

          <textarea
            className="ask-input"
            placeholder={t('questionPlaceholder')}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={4}
            aria-label={t('questionAria')}
          />
          <div className="ask-form__actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={running || !question.trim() || noSources}
              title={noSources ? t('selectSource') : undefined}
            >
              {running ? t('analyzing') : t('analyze')}
            </button>
            {running && <Spinner label={t('gathering')} />}
          </div>
        </form>

        <ErrorBanner message={runError} />
      </section>

      {result && (
        <section className="card">
          <h2 className="page__title">{t('answer')}</h2>
          {result.warnings.map((w) => (
            <p key={w} className="muted">
              ⚠ {w}
            </p>
          ))}
          <p style={{ whiteSpace: 'pre-wrap' }}>{result.answer}</p>
          <p className="muted">
            {result.provider} · {result.model}
          </p>

          {result.steps.length > 0 && (
            <div className="subsection">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setShowSteps((s) => !s)}
              >
                {t(showSteps ? 'hideSteps' : 'showSteps', { count: result.steps.length })}
              </button>
              {showSteps && (
                <ol className="analysis-steps">
                  {result.steps.map((step, i) => (
                    <li key={i} className="analysis-step">
                      <div className="muted">
                        {step.connection_name ?? t('unknownConnection')}
                        {step.purpose ? ` — ${step.purpose}` : ''}
                      </div>
                      <pre className="analysis-step__sql">{step.sql}</pre>
                      {step.error ? (
                        <div className="banner banner--error">{step.error}</div>
                      ) : (
                        <div className="muted">{t('rows', { count: step.row_count ?? 0 })}</div>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
