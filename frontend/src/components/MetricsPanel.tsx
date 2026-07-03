import { useState } from 'react';
import { createMetric, deleteMetric, updateMetric } from '../api/endpoints';
import type { Metric } from '../api/types';
import { errorMessage } from '../utils/format';
import { ErrorBanner } from './ui';

interface Props {
  connectionId: number;
  metrics: Metric[];
  /** Reload the glossary after a change. */
  onChange: () => void;
}

interface Draft {
  id: number | null; // null => creating a new metric
  name: string;
  definition: string;
  expression: string;
}

const EMPTY: Draft = { id: null, name: '', definition: '', expression: '' };

/**
 * Sidebar panel for business metrics ("MRR = …", "active user = …"). Definitions
 * are fed into the AI prompt so questions that mention a metric generate the
 * agreed-upon SQL.
 */
export default function MetricsPanel({ connectionId, metrics, onChange }: Props) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!draft || !draft.name.trim() || !draft.definition.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: draft.name.trim(),
        definition: draft.definition.trim(),
        expression: draft.expression.trim() || null,
      };
      if (draft.id === null) await createMetric(connectionId, body);
      else await updateMetric(connectionId, draft.id, body);
      setDraft(null);
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (metric: Metric) => {
    if (!window.confirm(`Delete metric “${metric.name}”?`)) return;
    setError(null);
    try {
      await deleteMetric(connectionId, metric.id);
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="metrics-panel">
      <div className="metrics-panel__head">
        <h3 className="metrics-panel__title">Metrics</h3>
        {!draft && (
          <button type="button" className="btn btn--small" onClick={() => setDraft({ ...EMPTY })}>
            Add
          </button>
        )}
      </div>

      <ErrorBanner message={error} />

      {draft && (
        <div className="metrics-panel__form">
          <input
            type="text"
            placeholder="Name (e.g. MRR)"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            aria-label="Metric name"
          />
          <textarea
            placeholder="Definition (plain language)"
            value={draft.definition}
            onChange={(e) => setDraft({ ...draft, definition: e.target.value })}
            rows={2}
            aria-label="Metric definition"
          />
          <input
            type="text"
            placeholder="SQL expression (optional)"
            value={draft.expression}
            onChange={(e) => setDraft({ ...draft, expression: e.target.value })}
            aria-label="Metric SQL expression"
          />
          <div className="metrics-panel__form-actions">
            <button
              type="button"
              className="btn btn--small btn--primary"
              onClick={() => void save()}
              disabled={busy || !draft.name.trim() || !draft.definition.trim()}
            >
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              className="btn btn--small btn--ghost"
              onClick={() => setDraft(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {metrics.length === 0 && !draft ? (
        <p className="muted metrics-panel__empty">No metrics defined yet.</p>
      ) : (
        <ul className="metrics-panel__list">
          {metrics.map((m) => (
            <li key={m.id} className="metrics-panel__item">
              <div className="metrics-panel__item-head">
                <strong>{m.name}</strong>
                <span className="metrics-panel__item-actions">
                  <button
                    type="button"
                    className="btn btn--small"
                    onClick={() =>
                      setDraft({
                        id: m.id,
                        name: m.name,
                        definition: m.definition,
                        expression: m.expression ?? '',
                      })
                    }
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn--small btn--danger"
                    onClick={() => void remove(m)}
                  >
                    Delete
                  </button>
                </span>
              </div>
              <p className="metrics-panel__def">{m.definition}</p>
              {m.expression && <code className="metrics-panel__expr">{m.expression}</code>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
