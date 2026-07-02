import { useEffect, useState } from 'react';
import { explainPlan } from '../api/endpoints';
import type { AskResponse, ExplainResult } from '../api/types';
import { errorMessage } from '../utils/format';

interface Props {
  preview: AskResponse;
  /** Connection the SQL runs against; needed for the cost estimate. */
  connectionId: number;
  /** True while the accepted SQL is executing. */
  busy?: boolean;
  /** Accept the (possibly edited) SQL for execution. */
  onAccept: (sql: string) => void;
  onCancel: () => void;
}

/**
 * Modal showing the AI-generated SQL, its explanation, and any warnings.
 * The user can Accept, switch to Edit mode to tweak the SQL, or Cancel.
 */
export default function SqlPreviewModal({
  preview,
  connectionId,
  busy,
  onAccept,
  onCancel,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [sql, setSql] = useState(preview.generated_sql);

  const [estimate, setEstimate] = useState<ExplainResult | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  // Reset local SQL (and any stale estimate) whenever a fresh preview arrives.
  useEffect(() => {
    setSql(preview.generated_sql);
    setEditing(false);
    setEstimate(null);
    setExplainError(null);
  }, [preview]);

  const handleExplain = async () => {
    setExplainError(null);
    setExplaining(true);
    try {
      setEstimate(await explainPlan({ connection_id: connectionId, sql }));
    } catch (err) {
      setExplainError(errorMessage(err));
    } finally {
      setExplaining(false);
    }
  };

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onCancel();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [busy, onCancel]);

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="SQL preview">
      <div className="modal">
        <header className="modal__header">
          <h2>Review the generated SQL</h2>
          <p className="modal__sub">
            {preview.provider} · {preview.model} · {preview.dialect}
          </p>
        </header>

        <div className="modal__body">
          {preview.explanation && (
            <p className="explanation">{preview.explanation}</p>
          )}

          {preview.warnings.length > 0 && (
            <ul className="warnings">
              {preview.warnings.map((w, i) => (
                <li key={i}>⚠ {w}</li>
              ))}
            </ul>
          )}

          {editing ? (
            <textarea
              className="sql-editor"
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              spellCheck={false}
              rows={10}
              aria-label="Editable SQL"
            />
          ) : (
            <pre className="sql-box">
              <code>{sql}</code>
            </pre>
          )}

          {(estimate || explainError) && (
            <p className="explain-estimate" role="status">
              {explainError ? (
                <span className="explain-estimate__error">{explainError}</span>
              ) : (
                <>
                  Estimated cost:{' '}
                  <strong>{estimate?.cost != null ? estimate.cost.toLocaleString() : 'n/a'}</strong>
                  {' · '}estimated rows:{' '}
                  <strong>{estimate?.rows != null ? estimate.rows.toLocaleString() : 'n/a'}</strong>
                </>
              )}
            </p>
          )}
        </div>

        <footer className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => void handleExplain()}
            disabled={busy || explaining || sql.trim().length === 0}
          >
            {explaining ? 'Estimating…' : 'Show cost estimate'}
          </button>
          {!editing && (
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setEditing(true)}
              disabled={busy}
            >
              Edit
            </button>
          )}
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => onAccept(sql)}
            disabled={busy || sql.trim().length === 0}
          >
            {busy ? 'Running…' : 'Accept & run'}
          </button>
        </footer>
      </div>
    </div>
  );
}
