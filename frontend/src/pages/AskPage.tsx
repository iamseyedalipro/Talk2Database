import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ask,
  execute,
  executeCsv,
  getSuggestedQuestions,
  listConnections,
} from '../api/endpoints';
import { askViaSocket, type AskSocketHandle } from '../api/askSocket';
import { triggerBlobDownload } from '../api/client';
import type { AskActivityStep, AskProgressEvent, Connection } from '../api/types';
import { useAuthStore } from '../store/auth';
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

  const socketRef = useRef<AskSocketHandle | null>(null);
  // Mirrors socketRef for rendering: refs don't trigger re-renders, state does.
  const [stoppable, setStoppable] = useState(false);

  /** Patch the streaming assistant turn (always the last turn while asking). */
  const patchLastAssistant = (
    patch:
      | Partial<Extract<ChatTurn, { kind: 'assistant' }>>
      | ((turn: Extract<ChatTurn, { kind: 'assistant' }>) => Partial<Extract<ChatTurn, { kind: 'assistant' }>>),
  ) => {
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.kind !== 'assistant') return prev;
      const applied = typeof patch === 'function' ? patch(last) : patch;
      return [...prev.slice(0, -1), { ...last, ...applied }];
    });
  };

  const appendStep = (step: AskActivityStep) => {
    patchLastAssistant((turn) => ({ steps: [...(turn.steps ?? []), step] }));
  };

  const finishRun = () => {
    socketRef.current = null;
    setStoppable(false);
    setAsking(false);
  };

  const handleProgressEvent = (event: AskProgressEvent) => {
    switch (event.type) {
      case 'run_started':
        break; // the pending turn is already on screen
      case 'status':
        appendStep({ kind: 'status', text: event.message });
        break;
      case 'tables_directory':
        appendStep({ kind: 'tables_directory', count: event.count });
        break;
      case 'tables_requested':
        appendStep({ kind: 'tables_requested', tables: event.table_names });
        break;
      case 'table_details_sent':
        appendStep({ kind: 'table_details_sent', tables: event.table_names, unknown: event.unknown });
        break;
      case 'assistant_note':
        appendStep({ kind: 'note', text: event.text });
        break;
      case 'exploratory_query':
        appendStep({ kind: 'query', sql: event.sql, purpose: event.purpose });
        break;
      case 'query_result':
        // Attach the result to the newest query step still waiting for one.
        patchLastAssistant((turn) => {
          const steps = [...(turn.steps ?? [])];
          for (let i = steps.length - 1; i >= 0; i -= 1) {
            const step = steps[i];
            if (!step || step.kind !== 'query') continue;
            if (step.result !== undefined || (step.error !== undefined && step.error !== null)) {
              continue;
            }
            steps[i] = {
              ...step,
              error: event.error ?? null,
              result:
                event.columns !== undefined
                  ? {
                      columns: event.columns,
                      rows: event.rows ?? [],
                      row_count: event.row_count ?? 0,
                      truncated: event.truncated ?? false,
                    }
                  : undefined,
            };
            break;
          }
          return { steps };
        });
        break;
      case 'generating_sql':
        appendStep({ kind: 'generating', attempt: event.attempt, attempts: event.attempts });
        break;
      case 'retry':
        appendStep({ kind: 'retry', reason: event.reason, detail: event.detail });
        break;
      case 'final_result': {
        const { type: _type, seq: _seq, ...askResponse } = event;
        patchLastAssistant({ ask: askResponse, pending: false });
        finishRun();
        break;
      }
      case 'error':
        patchLastAssistant({ pending: false });
        setAskError(event.detail);
        finishRun();
        break;
      case 'cancelled':
        patchLastAssistant({ pending: false, cancelled: true });
        finishRun();
        break;
    }
  };

  const submitQuestion = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || connectionId === null || asking) return;
    setAskError(null);
    setAsking(true);
    setTurns((prev) => [
      ...prev,
      { kind: 'user', text: trimmed },
      { kind: 'assistant', question: trimmed, steps: [], pending: true },
    ]);

    const payload = { connection_id: connectionId, question: trimmed };
    const token = useAuthStore.getState().token ?? '';

    try {
      // Preferred transport: WebSocket with live progress. Once the run has
      // started, terminal events arrive via handleProgressEvent.
      socketRef.current = await askViaSocket(payload, token, { onEvent: handleProgressEvent });
      setStoppable(true);
      return;
    } catch {
      // The socket never started a run — safe to fall back to plain HTTP.
    }

    try {
      const res = await ask(payload);
      patchLastAssistant({ ask: res, pending: false });
    } catch (err) {
      patchLastAssistant({ pending: false });
      setAskError(errorMessage(err));
    } finally {
      finishRun();
    }
  };

  const handleStop = () => {
    socketRef.current?.cancel();
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
    if (!turn || turn.kind !== 'assistant' || !turn.ask || connectionId === null) return;
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
    if (!turn || turn.kind !== 'assistant' || !turn.ask || connectionId === null) return;
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
            {asking && stoppable ? (
              <button type="button" className="btn btn--secondary" onClick={handleStop}>
                Stop
              </button>
            ) : (
              <button
                type="submit"
                className="btn btn--primary"
                disabled={asking || !question.trim() || connectionId === null}
              >
                {asking ? 'Generating…' : 'Send'}
              </button>
            )}
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
