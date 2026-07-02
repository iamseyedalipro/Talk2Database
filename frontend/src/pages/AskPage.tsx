import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ask,
  execute,
  executeCsv,
  getSuggestedQuestions,
  listConnections,
  summarize,
  systemStatus,
} from '../api/endpoints';
import { triggerBlobDownload } from '../api/client';
import type { Connection } from '../api/types';
import ChatThread, { type ChatTurn } from '../components/chat/ChatThread';
import SuggestedQuestions from '../components/chat/SuggestedQuestions';
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
  const [summariesEnabled, setSummariesEnabled] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);

  // The question each assistant turn answered, for /summarize (index-aligned).
  const questionsByTurn = useRef<Map<number, string>>(new Map());

  useEffect(() => {
    listConnections()
      .then((list) => {
        setConnections(list);
        const first = list[0];
        if (first) setConnectionId((prev) => prev ?? first.id);
      })
      .catch((err) => setConnError(errorMessage(err)));
    systemStatus()
      .then((status) => setSummariesEnabled(status.answer_summary_enabled))
      .catch(() => setSummariesEnabled(false));
  }, []);

  // New connection: fresh conversation and fresh example questions.
  useEffect(() => {
    if (connectionId === null) return;
    setTurns([]);
    questionsByTurn.current.clear();
    setAskError(null);
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
      setTurns((prev) => {
        questionsByTurn.current.set(prev.length, trimmed);
        return [...prev, { kind: 'assistant', ask: res }];
      });
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
      if (summariesEnabled) {
        const asked = questionsByTurn.current.get(index);
        if (asked) {
          patchTurn(index, { summarizing: true });
          summarize({
            connection_id: connectionId,
            history_id: turn.ask.history_id,
            question: asked,
            sql,
            columns: result.columns.map((c) => c.name),
            rows: result.rows,
            row_count: result.row_count,
            truncated: result.truncated,
          })
            .then((res) => patchTurn(index, { summarizing: false, summary: res.summary }))
            .catch(() => patchTurn(index, { summarizing: false }));
        }
      }
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

      {!noConnections && (
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
            onRun={handleRun}
            onPickInterpretation={submitQuestion}
            onDownloadCsv={handleDownloadCsv}
            csvBusy={csvBusy}
            busy={asking}
          />

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
        </>
      )}
    </div>
  );
}
