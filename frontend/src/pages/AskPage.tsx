import { useState } from 'react';
import { ask, execute, executeCsv } from '../api/endpoints';
import { triggerBlobDownload } from '../api/client';
import type { AskResponse, ExecuteResponse } from '../api/types';
import ResultsView from '../components/ResultsView';
import SqlPreviewModal from '../components/SqlPreviewModal';
import { ErrorBanner } from '../components/ui';
import { errorMessage } from '../utils/format';

/**
 * Default authed route. The user types a question, we ask the backend for SQL,
 * preview it, then execute the accepted SQL and show results with CSV export
 * and chart toggle.
 */
export default function AskPage() {
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  const [preview, setPreview] = useState<AskResponse | null>(null);
  const [executing, setExecuting] = useState(false);

  // The SQL that produced the currently displayed result (needed for CSV + history link).
  const [activeSql, setActiveSql] = useState<string | null>(null);
  const [activeHistoryId, setActiveHistoryId] = useState<number | null>(null);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const [csvBusy, setCsvBusy] = useState(false);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setAskError(null);
    setRunError(null);
    setAsking(true);
    try {
      const res = await ask({ question: question.trim() });
      setPreview(res);
    } catch (err) {
      setAskError(errorMessage(err));
    } finally {
      setAsking(false);
    }
  };

  const handleAccept = async (sql: string) => {
    if (!preview) return;
    setRunError(null);
    setExecuting(true);
    try {
      const res = await execute({ sql, history_id: preview.history_id });
      setResult(res);
      setActiveSql(sql);
      setActiveHistoryId(preview.history_id);
      setPreview(null);
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setExecuting(false);
    }
  };

  const handleDownloadCsv = async () => {
    if (!activeSql) return;
    setRunError(null);
    setCsvBusy(true);
    try {
      const { blob, filename } = await executeCsv({
        sql: activeSql,
        history_id: activeHistoryId ?? undefined,
      });
      triggerBlobDownload(blob, filename);
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setCsvBusy(false);
    }
  };

  return (
    <div className="page">
      <section className="card">
        <h1 className="page__title">Ask your database</h1>
        <p className="muted">
          Describe what you want in plain language. We generate a read-only SQL SELECT for you to
          review before it runs.
        </p>

        <form className="ask-form" onSubmit={handleAsk}>
          <textarea
            className="ask-input"
            placeholder="e.g. How many orders were placed in the last 30 days, by day?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={4}
            aria-label="Your question"
          />
          <div className="ask-form__actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={asking || !question.trim()}
            >
              {asking ? 'Generating SQL…' : 'Generate SQL'}
            </button>
          </div>
        </form>

        <ErrorBanner message={askError} />
      </section>

      <ErrorBanner message={runError} />

      {result && (
        <ResultsView result={result} onDownloadCsv={handleDownloadCsv} csvBusy={csvBusy} />
      )}

      {preview && (
        <SqlPreviewModal
          preview={preview}
          busy={executing}
          onAccept={handleAccept}
          onCancel={() => setPreview(null)}
        />
      )}
    </div>
  );
}
