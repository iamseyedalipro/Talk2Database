import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ask, execute, executeCsv, listConnections } from '../api/endpoints';
import { triggerBlobDownload } from '../api/client';
import type { AskResponse, Connection, ExecuteResponse } from '../api/types';
import ResultsView from '../components/ResultsView';
import SaveQueryModal from '../components/SaveQueryModal';
import SqlPreviewModal from '../components/SqlPreviewModal';
import { ErrorBanner } from '../components/ui';
import { errorMessage } from '../utils/format';

/**
 * Default authed route. The user picks a connection, types a question, we ask
 * the backend for SQL, preview it, then execute the accepted SQL against that
 * connection and show results with CSV export and chart toggle.
 */
export default function AskPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [connError, setConnError] = useState<string | null>(null);

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
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  // The question that produced the active result (stored when we run).
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null);

  useEffect(() => {
    listConnections()
      .then((list) => {
        setConnections(list);
        const first = list[0];
        if (first) setConnectionId((prev) => prev ?? first.id);
      })
      .catch((err) => setConnError(errorMessage(err)));
  }, []);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || connectionId === null) return;
    setAskError(null);
    setRunError(null);
    setAsking(true);
    try {
      const res = await ask({ connection_id: connectionId, question: question.trim() });
      setPreview(res);
    } catch (err) {
      setAskError(errorMessage(err));
    } finally {
      setAsking(false);
    }
  };

  const handleAccept = async (sql: string) => {
    if (!preview || connectionId === null) return;
    setRunError(null);
    setExecuting(true);
    try {
      const res = await execute({
        connection_id: connectionId,
        sql,
        history_id: preview.history_id,
      });
      setResult(res);
      setActiveSql(sql);
      setActiveHistoryId(preview.history_id);
      setActiveQuestion(question.trim() || null);
      setSaveNotice(null);
      setPreview(null);
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setExecuting(false);
    }
  };

  const handleDownloadCsv = async () => {
    if (!activeSql || connectionId === null) return;
    setRunError(null);
    setCsvBusy(true);
    try {
      const { blob, filename } = await executeCsv({
        connection_id: connectionId,
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

  const noConnections = connections.length === 0;

  return (
    <div className="page">
      <section className="card">
        <h1 className="page__title">Ask your database</h1>
        <p className="muted">
          Describe what you want in plain language. We generate a read-only SQL SELECT for you to
          review before it runs.
        </p>

        <ErrorBanner message={connError} />

        {noConnections ? (
          <p className="muted">
            You have no connections yet. <Link to="/connections">Add a connection</Link> to start
            asking questions.
          </p>
        ) : (
          <form className="ask-form" onSubmit={handleAsk}>
            <label className="ask-form__field">
              Data source
              <select
                value={connectionId ?? ''}
                onChange={(e) => setConnectionId(Number(e.target.value))}
                aria-label="Data source"
              >
                {connections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.type})
                  </option>
                ))}
              </select>
            </label>
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
                disabled={asking || !question.trim() || connectionId === null}
              >
                {asking ? 'Generating SQL…' : 'Generate SQL'}
              </button>
            </div>
          </form>
        )}

        <ErrorBanner message={askError} />
      </section>

      <ErrorBanner message={runError} />

      {result && (
        <>
          <div className="result-actions">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setSaveOpen(true)}
              disabled={!activeSql}
            >
              Save query
            </button>
            {saveNotice && <span className="muted">{saveNotice}</span>}
          </div>
          <ResultsView
            result={result}
            onDownloadCsv={handleDownloadCsv}
            csvBusy={csvBusy}
            question={activeQuestion}
          />
        </>
      )}

      {preview && (
        <SqlPreviewModal
          preview={preview}
          busy={executing}
          onAccept={handleAccept}
          onCancel={() => setPreview(null)}
        />
      )}

      {saveOpen && activeSql && (
        <SaveQueryModal
          draft={{
            generated_sql: activeSql,
            question: activeQuestion,
            connection_id: connectionId,
          }}
          onSaved={() => {
            setSaveOpen(false);
            setSaveNotice('Saved to your library.');
          }}
          onCancel={() => setSaveOpen(false)}
        />
      )}
    </div>
  );
}
