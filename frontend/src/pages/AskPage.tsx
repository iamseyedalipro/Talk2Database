import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  askInChat,
  execute,
  executeCsv,
  getSuggestedQuestions,
  listChatMessages,
  listConnections,
} from '../api/endpoints';
import { triggerBlobDownload } from '../api/client';
import type { ChatMessageItem, Connection } from '../api/types';
import ChatSidebar from '../components/chat/ChatSidebar';
import ChatThread, { type ChatTurn } from '../components/chat/ChatThread';
import SuggestedQuestions from '../components/chat/SuggestedQuestions';
import SaveQueryModal from '../components/SaveQueryModal';
import { ErrorBanner } from '../components/ui';
import { errorMessage } from '../utils/format';
import { useChatStore } from '../store/chat';

/** Rebuild the visible conversation from persisted chat messages. */
function turnsFromMessages(messages: ChatMessageItem[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  let lastQuestion = '';
  for (const message of messages) {
    if (message.role === 'user') {
      lastQuestion = message.content ?? '';
      turns.push({ kind: 'user', text: lastQuestion });
    } else if (message.ask) {
      turns.push({
        kind: 'assistant',
        ask: message.ask,
        question: lastQuestion,
        messageId: message.id,
        executedSql: message.executed_sql ?? undefined,
        result: message.result_sample
          ? { ...message.result_sample, elapsed_ms: 0 }
          : undefined,
        restoredSample: message.result_sample !== null,
      });
    }
  }
  return turns;
}

/**
 * Default authed route: persistent, ChatGPT-style conversations with a
 * database. Every question and answer is stored server-side; follow-ups reuse
 * the session history so the AI can refine earlier SQL.
 */
export default function AskPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [connError, setConnError] = useState<string | null>(null);

  const sessions = useChatStore((s) => s.sessions);
  const sessionsLoading = useChatStore((s) => s.sessionsLoading);
  const activeId = useChatStore((s) => s.activeId);
  const loadSessions = useChatStore((s) => s.loadSessions);
  const createSession = useChatStore((s) => s.createSession);
  const selectSession = useChatStore((s) => s.selectSession);
  const renameSession = useChatStore((s) => s.renameSession);
  const setArchived = useChatStore((s) => s.setArchived);
  const removeSession = useChatStore((s) => s.removeSession);
  const applySessionUpdate = useChatStore((s) => s.applySessionUpdate);

  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [threadLoading, setThreadLoading] = useState(false);
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);

  // Index of the turn being bookmarked, or null when the dialog is closed.
  const [saveIndex, setSaveIndex] = useState<number | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId],
  );
  // The connection the conversation is bound to (or the picker value for a new chat).
  const sessionConnectionId = activeSession ? activeSession.connection_id : connectionId;
  const sessionConnection = useMemo(
    () => connections.find((c) => c.id === sessionConnectionId) ?? null,
    [connections, sessionConnectionId],
  );

  useEffect(() => {
    listConnections()
      .then((list) => {
        setConnections(list);
        const first = list[0];
        if (first) setConnectionId((prev) => prev ?? first.id);
      })
      .catch((err) => setConnError(errorMessage(err)));
    loadSessions().catch((err) => setConnError(errorMessage(err)));
  }, [loadSessions]);

  // Load (or clear) the thread when the selected session changes.
  useEffect(() => {
    setAskError(null);
    setSaveIndex(null);
    setSaveNotice(null);
    setSidebarOpen(false);
    if (activeId === null) {
      setTurns([]);
      return;
    }
    let cancelled = false;
    setThreadLoading(true);
    listChatMessages(activeId)
      .then((messages) => {
        if (!cancelled) setTurns(turnsFromMessages(messages));
      })
      .catch((err) => {
        if (!cancelled) setAskError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setThreadLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  // Example questions for the empty state of a new chat.
  useEffect(() => {
    if (connectionId === null || activeId !== null) return;
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
  }, [connectionId, activeId]);

  const submitQuestion = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || asking) return;
    setAskError(null);
    setAsking(true);
    setTurns((prev) => [...prev, { kind: 'user', text: trimmed }]);
    try {
      // First question of a fresh chat creates the session on the fly.
      let chatId = activeId;
      if (chatId === null) {
        if (connectionId === null) return;
        const session = await createSession(connectionId);
        chatId = session.id;
      }
      const res = await askInChat(chatId, { question: trimmed });
      applySessionUpdate(chatId, res.session_title);
      setTurns((prev) => [
        ...prev,
        {
          kind: 'assistant',
          ask: res,
          question: trimmed,
          messageId: res.assistant_message_id,
        },
      ]);
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
    if (!turn || turn.kind !== 'assistant' || sessionConnectionId === null) return;
    patchTurn(index, { executing: true, runError: null });
    try {
      const result = await execute({
        connection_id: sessionConnectionId,
        sql,
        history_id: turn.ask.history_id,
        chat_message_id: turn.messageId,
      });
      patchTurn(index, { executing: false, result, executedSql: sql, restoredSample: false });
    } catch (err) {
      patchTurn(index, { executing: false, runError: errorMessage(err) });
    }
  };

  const handleDownloadCsv = async (index: number, sql: string) => {
    const turn = turns[index];
    if (!turn || turn.kind !== 'assistant' || sessionConnectionId === null) return;
    setCsvBusy(true);
    try {
      const { blob, filename } = await executeCsv({
        connection_id: sessionConnectionId,
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
          connection_id: sessionConnectionId,
        }
      : null;

  const noConnections = connections.length === 0;
  const emptyThread = turns.length === 0;
  const archived = activeSession?.archived ?? false;
  const composerDisabled =
    asking || archived || (activeSession ? activeSession.connection_id === null : connectionId === null);

  return (
    <div className="page ask-page">
      <div className="ask-layout">
        <div className={sidebarOpen ? 'ask-layout__sidebar is-open' : 'ask-layout__sidebar'}>
          <ChatSidebar
            sessions={sessions}
            activeId={activeId}
            loading={sessionsLoading}
            onNewChat={() => {
              selectSession(null);
              setSidebarOpen(false);
            }}
            onSelect={(id) => selectSession(id)}
            onRename={(id, title) => void renameSession(id, title).catch((err) => setAskError(errorMessage(err)))}
            onArchive={(id, value) => void setArchived(id, value).catch((err) => setAskError(errorMessage(err)))}
            onDelete={(id) => void removeSession(id).catch((err) => setAskError(errorMessage(err)))}
          />
        </div>

        <div className="ask-layout__main">
          <section className="card ask-page__header">
            <div className="ask-page__title-row">
              <div className="ask-page__heading">
                <button
                  type="button"
                  className="btn btn--ghost chat-sidebar-toggle"
                  onClick={() => setSidebarOpen((v) => !v)}
                  aria-expanded={sidebarOpen}
                  aria-label={sidebarOpen ? 'Close chat list' : 'Open chat list'}
                >
                  ☰
                </button>
                <div>
                  <h1 className="page__title">
                    {activeSession ? activeSession.title : 'Ask your database'}
                  </h1>
                  <p className="muted">
                    {activeSession
                      ? 'Continue the conversation — follow-ups refine the SQL above.'
                      : 'Describe what you want in plain language. We generate a read-only SQL SELECT for you to review before it runs.'}
                  </p>
                </div>
              </div>
              {!noConnections && !activeSession && (
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
              {activeSession && (
                <span className="ask-page__connection muted">
                  Data source
                  <strong>
                    {sessionConnection
                      ? `${sessionConnection.name} (${sessionConnection.type})`
                      : 'deleted connection'}
                  </strong>
                </span>
              )}
            </div>

            <ErrorBanner message={connError} />
            {noConnections && (
              <p className="muted">
                You have no connections yet. <Link to="/connections">Add a connection</Link> to
                start asking questions.
              </p>
            )}
            {archived && (
              <p className="banner banner--info">
                This chat is archived. Unarchive it from the sidebar to continue the conversation.
              </p>
            )}
          </section>

          {!noConnections && (
            <>
              {emptyThread && !activeSession && connectionId !== null && (
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

              {threadLoading ? (
                <p className="muted chat-pending">Loading conversation…</p>
              ) : (
                <ChatThread
                  turns={turns}
                  connectionId={sessionConnectionId ?? 0}
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
              )}

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
                  disabled={archived}
                  aria-label="Your question"
                />
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={composerDisabled || !question.trim()}
                >
                  {asking ? 'Generating…' : 'Send'}
                </button>
              </form>
            </>
          )}

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
        </div>
      </div>
    </div>
  );
}
