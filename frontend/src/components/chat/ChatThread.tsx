import { useEffect, useRef } from 'react';
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
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  return (
    <div className="chat-thread">
      {turns.map((turn, index) => {
        if (turn.kind === 'user') {
          return (
            <div key={index} className="chat-bubble chat-bubble--user">
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
                    The generated SQL references identifiers that do not exist:{' '}
                    {ask.invalid_identifiers.join(', ')}. You can edit it below or rephrase your
                    question.
                  </div>
                )}
                {ask.explanation && <p className="explanation">{ask.explanation}</p>}
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
                        Save query
                      </button>
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
