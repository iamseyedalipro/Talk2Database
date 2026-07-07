import type { AskActivityStep } from '../../api/types';

interface Props {
  steps: AskActivityStep[];
  /** True while the run is still going: the last step gets a spinner. */
  pending?: boolean;
  /** True when the user stopped the run; the feed stays as a record. */
  cancelled?: boolean;
}

function stepLabel(step: AskActivityStep): string {
  switch (step.kind) {
    case 'status':
      return step.text;
    case 'tables_directory':
      return `Scanned the table list (${step.count} table${step.count === 1 ? '' : 's'})`;
    case 'tables_requested':
      return `Requested details for: ${step.tables.join(', ') || '(none)'}`;
    case 'table_details_sent':
      return `Read table details: ${step.tables.join(', ') || '(none)'}`;
    case 'note':
      return step.text;
    case 'query':
      return step.purpose || 'Ran an exploratory query';
    case 'generating':
      return step.attempt > 1
        ? `Writing the SQL (attempt ${step.attempt} of ${step.attempts})…`
        : 'Writing the SQL…';
    case 'retry':
      return step.reason === 'guard_rejected'
        ? 'The draft was not a single read-only SELECT — retrying'
        : 'The draft referenced unknown tables/columns — retrying';
  }
}

/** One exploratory query with collapsible SQL and a small result preview. */
function QueryStep({ step }: { step: Extract<AskActivityStep, { kind: 'query' }> }) {
  return (
    <>
      <details className="activity-feed__query">
        <summary>View SQL</summary>
        <pre className="activity-feed__sql">{step.sql}</pre>
      </details>
      {step.error && <p className="activity-feed__error">⚠ {step.error}</p>}
      {step.result && (
        <div className="activity-feed__preview">
          <table>
            <thead>
              <tr>
                {step.result.columns.map((col, i) => (
                  <th key={i}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {step.result.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci}>{cell === null || cell === undefined ? '∅' : String(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            {step.result.row_count} row{step.result.row_count === 1 ? '' : 's'}
            {step.result.truncated ? ' (sample)' : ''}
          </p>
        </div>
      )}
    </>
  );
}

/**
 * Live record of what the AI is doing while answering: tables it requested,
 * exploratory queries it ran (with row samples), and generation retries.
 */
export default function AgentActivityFeed({ steps, pending, cancelled }: Props) {
  if (steps.length === 0 && !pending && !cancelled) return null;

  return (
    <div className="activity-feed" aria-live="polite">
      <ol className="activity-feed__list">
        {steps.map((step, index) => {
          const isLast = index === steps.length - 1;
          return (
            <li key={index} className={`activity-feed__step activity-feed__step--${step.kind}`}>
              <span className="activity-feed__marker">
                {pending && isLast ? <span className="activity-feed__spinner" /> : '✓'}
              </span>
              <div className="activity-feed__body">
                <span className={step.kind === 'note' ? 'activity-feed__note' : undefined}>
                  {stepLabel(step)}
                </span>
                {step.kind === 'query' && <QueryStep step={step} />}
                {step.kind === 'retry' && <p className="muted">{step.detail}</p>}
              </div>
            </li>
          );
        })}
        {pending && steps.length === 0 && (
          <li className="activity-feed__step">
            <span className="activity-feed__marker">
              <span className="activity-feed__spinner" />
            </span>
            <div className="activity-feed__body">Starting…</div>
          </li>
        )}
      </ol>
      {cancelled && <p className="activity-feed__cancelled">Stopped by you.</p>}
    </div>
  );
}
