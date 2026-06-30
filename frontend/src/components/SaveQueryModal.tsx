import { useEffect, useState } from 'react';
import { createSavedQuery } from '../api/endpoints';
import type { SavedQueryCreate } from '../api/types';
import { errorMessage } from '../utils/format';
import { ErrorBanner } from './ui';

interface Props {
  /** The query to bookmark: SQL plus optional originating question/connection. */
  draft: { generated_sql: string; question?: string | null; connection_id?: number | null };
  onSaved: () => void;
  onCancel: () => void;
}

/**
 * Small modal to name a query and save it to the library. Saving a private
 * query bookmarks it for the owner; checking "Share" makes it visible (and,
 * for a connection you own, runnable) to every panel user.
 */
export default function SaveQueryModal({ draft, onSaved, onCancel }: Props) {
  const [name, setName] = useState(() => (draft.question ?? '').slice(0, 120));
  const [shared, setShared] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onCancel();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [busy, onCancel]);

  const handleSave = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const body: SavedQueryCreate = {
        name: name.trim(),
        generated_sql: draft.generated_sql,
        question: draft.question ?? null,
        connection_id: draft.connection_id ?? null,
        shared,
      };
      await createSavedQuery(body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Save query">
      <div className="modal">
        <header className="modal__header">
          <h2>Save query</h2>
          <p className="modal__sub">Bookmark this query to re-run it later without re-asking the AI.</p>
        </header>

        <div className="modal__body">
          <label className="field">
            <span>Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Orders per day (last 30d)"
              maxLength={200}
              autoFocus
            />
          </label>

          <label className="field field--checkbox">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            <span>Share with everyone (visible to all panel users)</span>
          </label>

          <pre className="sql-box">
            <code>{draft.generated_sql}</code>
          </pre>

          <ErrorBanner message={error} />
        </div>

        <footer className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void handleSave()}
            disabled={busy || !name.trim()}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </footer>
      </div>
    </div>
  );
}
