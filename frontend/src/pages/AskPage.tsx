import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  askInChat,
  execute,
  executeCsv,
  getSuggestedQuestions,
  listChatMessages,
  listConnections,
} from '../api/endpoints';
import { askViaSocket, type AskSocketHandle } from '../api/askSocket';
import { triggerBlobDownload } from '../api/client';
import type {
  AskActivityStep,
  AskProgressEvent,
  ChatMessageItem,
  Connection,
} from '../api/types';
import ChatSidebar from '../components/chat/ChatSidebar';
import ChatThread, { type ChatTurn } from '../components/chat/ChatThread';
import SuggestedQuestions from '../components/chat/SuggestedQuestions';
import SaveQueryModal from '../components/SaveQueryModal';
import { ErrorBanner } from '../components/ui';
import { errorMessage } from '../utils/format';
import { useAuthStore } from '../store/auth';
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
 * the session history so the AI can refine earlier SQL. Questions stream live
 * progress over the WebSocket (with a plain-HTTP fallback).
 */
export default function AskPage() {
  const { t } = useTranslation('ask');
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

  const socketRef = useRef<AskSocketHandle | null>(null);
  // Mirrors socketRef for rendering: refs don't trigger re-renders, state does.
  const [stoppable, setStoppable] = useState(false);
  // True while a question is in flight — the thread must not be reloaded from
  // the server then (submitting the first question selects the just-created
  // session, which would otherwise wipe the optimistic turns).
  const askingRef = useRef(false);

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
    if (askingRef.current) return; // keep the optimistic in-flight turns
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
    askingRef.current = false;
  };

  const handleProgressEvent = (event: AskProgressEvent, chatId: number) => {
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
        const {
          type: _type,
          seq: _seq,
          user_message_id: _userMessageId,
          assistant_message_id: assistantMessageId,
          session_title: sessionTitle,
          ...askResponse
        } = event;
        patchLastAssistant({
          ask: askResponse,
          pending: false,
          messageId: assistantMessageId,
        });
        if (sessionTitle) applySessionUpdate(chatId, sessionTitle);
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
    if (!trimmed || asking) return;
    setAskError(null);
    setAsking(true);
    askingRef.current = true;
    setTurns((prev) => [
      ...prev,
      { kind: 'user', text: trimmed },
      { kind: 'assistant', question: trimmed, steps: [], pending: true },
    ]);

    let chatId = activeId;
    let chatConnectionId = sessionConnectionId;
    try {
      // First question of a fresh chat creates the session on the fly.
      if (chatId === null) {
        if (connectionId === null) {
          finishRun();
          return;
        }
        const session = await createSession(connectionId);
        chatId = session.id;
        chatConnectionId = session.connection_id;
      }
    } catch (err) {
      patchLastAssistant({ pending: false });
      setAskError(errorMessage(err));
      finishRun();
      return;
    }

    const token = useAuthStore.getState().token ?? '';
    const boundChatId = chatId;

    try {
      // Preferred transport: WebSocket with live progress. Once the run has
      // started, terminal events arrive via handleProgressEvent.
      socketRef.current = await askViaSocket(
        { connection_id: chatConnectionId ?? 0, question: trimmed, chat_id: boundChatId },
        token,
        { onEvent: (event) => handleProgressEvent(event, boundChatId) },
      );
      setStoppable(true);
      return;
    } catch {
      // The socket never started a run — safe to fall back to plain HTTP.
    }

    try {
      const res = await askInChat(boundChatId, { question: trimmed });
      applySessionUpdate(boundChatId, res.session_title);
      patchLastAssistant({ ask: res, pending: false, messageId: res.assistant_message_id });
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
    if (!turn || turn.kind !== 'assistant' || !turn.ask || sessionConnectionId === null) return;
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
    if (!turn || turn.kind !== 'assistant' || !turn.ask || sessionConnectionId === null) return;
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
                  aria-label={sidebarOpen ? t('closeChatList') : t('openChatList')}
                >
                  ☰
                </button>
                <div>
                  <h1 className="page__title">
                    {activeSession ? activeSession.title : t('title')}
                  </h1>
                  <p className="muted">
                    {activeSession ? t('continueSubtitle') : t('newSubtitle')}
                  </p>
                </div>
              </div>
              {!noConnections && !activeSession && (
                <label className="ask-page__connection">
                  {t('dataSource')}
                  <select
                    value={connectionId ?? ''}
                    onChange={(e) => setConnectionId(Number(e.target.value))}
                    aria-label={t('dataSource')}
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
                  {t('dataSource')}
                  <strong>
                    {sessionConnection
                      ? `${sessionConnection.name} (${sessionConnection.type})`
                      : t('deletedConnection')}
                  </strong>
                </span>
              )}
            </div>

            <ErrorBanner message={connError} />
            {noConnections && (
              <p className="muted">
                {t('noConnections')} <Link to="/connections">{t('addConnectionLink')}</Link>{' '}
                {t('noConnectionsSuffix')}
              </p>
            )}
            {archived && (
              <p className="banner banner--info">{t('archivedNote')}</p>
            )}
          </section>

          {!noConnections && (
            <>
              {emptyThread && !activeSession && connectionId !== null && (
                <section className="card">
                  <p className="muted">{t('tryOne')}</p>
                  <SuggestedQuestions
                    questions={suggestions}
                    loading={suggestionsLoading}
                    onPick={submitQuestion}
                    disabled={asking}
                  />
                </section>
              )}

              {threadLoading ? (
                <p className="muted chat-pending">{t('loadingConversation')}</p>
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
              <ErrorBanner message={askError} />

              <form className="chat-composer" onSubmit={handleSubmit}>
                <textarea
                  className="ask-input"
                  placeholder={emptyThread ? t('placeholderNew') : t('placeholderFollowUp')}
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
                  aria-label={t('yourQuestion')}
                />
                {asking && stoppable ? (
                  <button type="button" className="btn btn--secondary" onClick={handleStop}>
                    {t('stop')}
                  </button>
                ) : (
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={composerDisabled || !question.trim()}
                  >
                    {asking ? t('generating') : t('send')}
                  </button>
                )}
              </form>
            </>
          )}

          {saveDraft && (
            <SaveQueryModal
              draft={saveDraft}
              onSaved={() => {
                setSaveIndex(null);
                setSaveNotice(t('savedNotice'));
              }}
              onCancel={() => setSaveIndex(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
