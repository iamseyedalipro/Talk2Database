import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { AskResponse, ExecuteResponse } from '../../api/types';
import { ErrorBanner } from '../ui';
import ResultsView from '../ResultsView';
import ClarificationCard from './ClarificationCard';
import SqlBlock from './SqlBlock';

export type ChatTurn =
  | { kind: 'user'; text: string }
  | {
      kind: 'assistant';
      ask: AskResponse;
      /** The question this turn answered (for summaries and saved queries). */
      question: string;
      result?: ExecuteResponse;
      /** The exact (possibly user-edited) SQL that produced `result`. */
      executedSql?: string;
      executing?: boolean;
      runError?: string | null;
      /** Persisted chat message id (chat sessions); runs attach results to it. */
      messageId?: number;
      /** True when `result` is a stored sample restored from a past session. */
      restoredSample?: boolean;
    };

interface Props {
  turns: ChatTurn[];
  connectionId: number;
  /** Run (possibly edited) SQL for the assistant turn at `index`. */
  onRun: (index: number, sql: string) => void;
  /** Re-ask with a clarification interpretation's full question. */
  onPickInterpretation: (question: string) => void;
  onDownloadCsv: (index: number, sql: string) => void;
  /** Open the save-query dialog for an executed turn. */
  onSave: (index: number) => void;
  csvBusy?: boolean;
  busy?: boolean;
}

/** The conversation: user bubbles and assistant cards with SQL, results, charts. */
export default function ChatThread({
  turns,
  connectionId,
  onRun,
  onPickInterpretation,
  onDownloadCsv,
  onSave,
  csvBusy,
  busy,
}: Props) {
  const { t } = useTranslation('chat');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  return (
    <div className="chat-thread">
      {turns.map((turn, index) => {
        if (turn.kind === 'user') {
          return (
            <div key={index} className="chat-bubble chat-bubble--user" dir="auto">
              {turn.text}
            </div>
          );
        }

        const { ask } = turn;
        const needsInput = ask.status === 'needs_clarification' || ask.status === 'unanswerable';
        return (
          <div key={index} className="chat-bubble chat-bubble--assistant">
            {needsInput ? (
              <ClarificationCard ask={ask} onPick={onPickInterpretation} disabled={busy} />
            ) : (
              <>
                {ask.status === 'verification_failed' && (
                  <div className="banner banner--error">
                    {t('invalidIdentifiers', { list: ask.invalid_identifiers.join(', ') })}
                  </div>
                )}
                {ask.explanation && (
                  <p className="explanation" dir="auto">
                    {ask.explanation}
                  </p>
                )}
                {ask.warnings.length > 0 && (
                  <ul className="warnings">
                    {ask.warnings.map((warning, i) => (
                      <li key={i}>⚠ {warning}</li>
                    ))}
                  </ul>
                )}
                {ask.generated_sql && (
                  <SqlBlock
                    sql={ask.generated_sql}
                    connectionId={connectionId}
                    onRun={(sql) => onRun(index, sql)}
                    busy={turn.executing}
                    ran={turn.result !== undefined}
                  />
                )}
                <ErrorBanner message={turn.runError ?? null} />
                {turn.result && (
                  <>
                    <div className="result-actions">
                      <button
                        type="button"
                        className="btn btn--secondary"
                        onClick={() => onSave(index)}
                        disabled={!turn.executedSql}
                      >
                        {t('saveQuery')}
                      </button>
                      {turn.restoredSample && (
                        <span className="muted chat-restored-note">{t('restoredSample')}</span>
                      )}
                    </div>
                    <ResultsView
                      result={turn.result}
                      onDownloadCsv={
                        turn.executedSql
                          ? () => onDownloadCsv(index, turn.executedSql as string)
                          : undefined
                      }
                      csvBusy={csvBusy}
                      question={turn.question}
                    />
                  </>
                )}
              </>
            )}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
