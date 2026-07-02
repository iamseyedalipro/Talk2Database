import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ask,
  execute,
  executeCsv,
  getSuggestedQuestions,
  listConnections,
} from '../api/endpoints';
import { triggerBlobDownload } from '../api/client';
import type { Connection } from '../api/types';
import ChatThread, { type ChatTurn } from '../components/chat/ChatThread';
import SuggestedQuestions from '../components/chat/SuggestedQuestions';
import SaveQueryModal from '../components/SaveQueryModal';
import { ErrorBanner } from '../components/ui';
import { errorMessage } from '../utils/format';

/**
 * Default authed route: a conversation with the selected database. Each
 * question becomes a turn; the assistant answers with SQL to review and run,
 * or asks a clarifying question with clickable interpretations when the
 * question doesn't map onto the schema.
 */
export default function AskPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [connError, setConnError] = useState<string | null>(null);

  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);

  // Index of the turn being bookmarked, or null when the dialog is closed.
  const [saveIndex, setSaveIndex] = useState<number | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);

  useEffect(() => {
    listConnections()
      .then((list) => {
        setConnections(list);
        const first = list[0];
        if (first) setConnectionId((prev) => prev ?? first.id);
      })
      .catch((err) => setConnError(errorMessage(err)));
  }, []);

  // New connection: fresh conversation and fresh example questions.
  useEffect(() => {
    if (connectionId === null) return;
    setTurns([]);
    setAskError(null);
    setSaveIndex(null);
    setSaveNotice(null);
    setSuggestions([]);
    setSuggestionsLoading(true);
    let cancelled = false;
    getSuggestedQuestions(connectionId)
      .then((res) => {
        if (!cancelled) setSuggestions(res.questions);
      })
      .catch(() => {
        if (!cancelled) setSuggestions([]);
      })
      .finally(() => {
        if (!cancelled) setSuggestionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [connectionId]);

  const submitQuestion = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || connectionId === null || asking) return;
    setAskError(null);
    setAsking(true);
    setTurns((prev) => [...prev, { kind: 'user', text: trimmed }]);
    try {
      const res = await ask({ connection_id: connectionId, question: trimmed });
      setTurns((prev) => [...prev, { kind: 'assistant', ask: res, question: trimmed }]);
    } catch (err) {
      setAskError(errorMessage(err));
    } finally {
      setAsking(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = question;
    setQuestion('');
    await submitQuestion(text);
  };

  const patchTurn = (index: number, patch: Partial<Extract<ChatTurn, { kind: 'assistant' }>>) => {
    setTurns((prev) =>
      prev.map((turn, i) => (i === index && turn.kind === 'assistant' ? { ...turn, ...patch } : turn)),
    );
  };

  const handleRun = async (index: number, sql: string) => {
    const turn = turns[index];
    if (!turn || turn.kind !== 'assistant' || connectionId === null) return;
    patchTurn(index, { executing: true, runError: null });
    try {
      const result = await execute({
        connection_id: connectionId,
        sql,
        history_id: turn.ask.history_id,
      });
      patchTurn(index, { executing: false, result, executedSql: sql });
    } catch (err) {
      patchTurn(index, { executing: false, runError: errorMessage(err) });
    }
  };

  const handleDownloadCsv = async (index: number, sql: string) => {
    const turn = turns[index];
    if (!turn || turn.kind !== 'assistant' || connectionId === null) return;
    setCsvBusy(true);
    try {
      const { blob, filename } = await executeCsv({
        connection_id: connectionId,
        sql,
        history_id: turn.ask.history_id,
      });
      triggerBlobDownload(blob, filename);
    } catch (err) {
      patchTurn(index, { runError: errorMessage(err) });
    } finally {
      setCsvBusy(false);
    }
  };

  const saveTurn = saveIndex !== null ? turns[saveIndex] : null;
  const saveDraft =
    saveTurn && saveTurn.kind === 'assistant' && saveTurn.executedSql
      ? {
          generated_sql: saveTurn.executedSql,
          question: saveTurn.question,
          connection_id: connectionId,
        }
      : null;

  const noConnections = connections.length === 0;
  const emptyThread = turns.length === 0;

  return (
    <div className="page ask-page">
      <section className="card ask-page__header">
        <div className="ask-page__title-row">
          <div>
            <h1 className="page__title">Ask your database</h1>
            <p className="muted">
              Describe what you want in plain language. We generate a read-only SQL SELECT for you
              to review before it runs.
            </p>
          </div>
          {!noConnections && (
            <label className="ask-page__connection">
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
          )}
        </div>

        <ErrorBanner message={connError} />
        {noConnections && (
          <p className="muted">
            You have no connections yet. <Link to="/connections">Add a connection</Link> to start
            asking questions.
          </p>
        )}
      </section>

      {!noConnections && connectionId !== null && (
        <>
          {emptyThread && (
            <section className="card">
              <p className="muted">Not sure where to start? Try one of these:</p>
              <SuggestedQuestions
                questions={suggestions}
                loading={suggestionsLoading}
                onPick={submitQuestion}
                disabled={asking}
              />
            </section>
          )}

          <ChatThread
            turns={turns}
            connectionId={connectionId}
            onRun={handleRun}
            onPickInterpretation={submitQuestion}
            onDownloadCsv={handleDownloadCsv}
            onSave={(index) => {
              setSaveNotice(null);
              setSaveIndex(index);
            }}
            csvBusy={csvBusy}
            busy={asking}
          />

          {saveNotice && <p className="muted">{saveNotice}</p>}
          {asking && <p className="muted chat-pending">Thinking…</p>}
          <ErrorBanner message={askError} />

          <form className="chat-composer" onSubmit={handleSubmit}>
            <textarea
              className="ask-input"
              placeholder={
                emptyThread
                  ? 'e.g. How many orders were placed in the last 30 days, by day?'
                  : 'Ask a follow-up question…'
              }
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  const text = question;
                  setQuestion('');
                  void submitQuestion(text);
                }
              }}
              rows={2}
              aria-label="Your question"
            />
            <button
              type="submit"
              className="btn btn--primary"
              disabled={asking || !question.trim() || connectionId === null}
            >
              {asking ? 'Generating…' : 'Send'}
            </button>
          </form>

          {saveDraft && (
            <SaveQueryModal
              draft={saveDraft}
              onSaved={() => {
                setSaveIndex(null);
                setSaveNotice('Saved to your query library.');
              }}
              onCancel={() => setSaveIndex(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
