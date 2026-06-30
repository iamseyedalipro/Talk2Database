import { useCallback, useEffect, useState } from 'react';
import {
  deleteSavedQuery,
  listSavedQueries,
  runSavedQuery,
  updateSavedQuery,
} from '../api/endpoints';
import type { ExecuteResponse, SavedQuery } from '../api/types';
import ResultsView from '../components/ResultsView';
import { ErrorBanner, Spinner } from '../components/ui';
import { useAuthStore } from '../store/auth';
import { errorMessage, formatDate, truncate } from '../utils/format';

/** A row being edited inline (rename + share toggle). */
interface EditState {
  id: number;
  name: string;
  shared: boolean;
}

/**
 * The "Questions" library: a user's saved queries plus any shared by others.
 * Run a saved query (executes its stored SQL — no AI call), or, for queries you
 * can manage, rename / toggle sharing / delete.
 */
export default function SavedQueriesPage() {
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin');
  const canManage = (item: SavedQuery) => item.is_owner || (isAdmin && item.shared);

  const [items, setItems] = useState<SavedQuery[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [runError, setRunError] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null);
  const [result, setResult] = useState<ExecuteResponse | null>(null);

  const [edit, setEdit] = useState<EditState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      setItems(await listSavedQueries(200, 0));
    } catch (err) {
      setListError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRun = async (item: SavedQuery) => {
    setRunError(null);
    setResult(null);
    setRunningId(item.id);
    setActiveId(item.id);
    setActiveQuestion(item.question);
    try {
      setResult(await runSavedQuery(item.id));
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setRunningId(null);
    }
  };

  const handleDelete = async (item: SavedQuery) => {
    if (!window.confirm(`Delete saved query “${item.name}”?`)) return;
    setRunError(null);
    try {
      await deleteSavedQuery(item.id);
      if (activeId === item.id) {
        setActiveId(null);
        setResult(null);
      }
      void load();
    } catch (err) {
      setRunError(errorMessage(err));
    }
  };

  const handleSaveEdit = async () => {
    if (!edit) return;
    try {
      await updateSavedQuery(edit.id, { name: edit.name.trim(), shared: edit.shared });
      setEdit(null);
      void load();
    } catch (err) {
      setRunError(errorMessage(err));
    }
  };

  return (
    <div className="page">
      <section className="card">
        <div className="page__header">
          <h1 className="page__title">Saved queries</h1>
          <button type="button" className="btn btn--ghost" onClick={() => void load()}>
            Refresh
          </button>
        </div>

        <p className="muted">
          Re-run a vetted query without re-asking the AI. Shared queries are visible to everyone.
        </p>

        <ErrorBanner message={listError} />
        <ErrorBanner message={runError} />

        {loading ? (
          <Spinner label="Loading saved queries…" />
        ) : items.length === 0 ? (
          <p className="muted">
            No saved queries yet. Save one from the Ask page or your query history.
          </p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Question</th>
                  <th>SQL</th>
                  <th>Shared</th>
                  <th>Owner</th>
                  <th>Created</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {edit?.id === item.id ? (
                        <input
                          type="text"
                          value={edit.name}
                          onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                          aria-label="Saved query name"
                        />
                      ) : (
                        item.name
                      )}
                    </td>
                    <td title={item.question ?? ''}>{truncate(item.question ?? '—', 50)}</td>
                    <td>
                      <code className="inline-sql">{truncate(item.generated_sql, 40)}</code>
                    </td>
                    <td>
                      {edit?.id === item.id ? (
                        <input
                          type="checkbox"
                          checked={edit.shared}
                          onChange={(e) => setEdit({ ...edit, shared: e.target.checked })}
                          aria-label="Shared"
                        />
                      ) : item.shared ? (
                        <span className="pill pill--ok">shared</span>
                      ) : (
                        <span className="pill pill--neutral">private</span>
                      )}
                    </td>
                    <td title={item.owner_email ?? ''}>
                      {item.is_owner ? 'You' : (item.owner_email ?? '—')}
                    </td>
                    <td>{formatDate(item.created_at)}</td>
                    <td className="row-actions">
                      {edit?.id === item.id ? (
                        <>
                          <button
                            type="button"
                            className="btn btn--small btn--primary"
                            onClick={() => void handleSaveEdit()}
                            disabled={!edit.name.trim()}
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            className="btn btn--small btn--ghost"
                            onClick={() => setEdit(null)}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="btn btn--small btn--primary"
                            onClick={() => void handleRun(item)}
                            disabled={runningId === item.id}
                          >
                            {runningId === item.id ? 'Running…' : 'Run'}
                          </button>
                          {canManage(item) && (
                            <>
                              <button
                                type="button"
                                className="btn btn--small"
                                onClick={() =>
                                  setEdit({ id: item.id, name: item.name, shared: item.shared })
                                }
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="btn btn--small btn--danger"
                                onClick={() => void handleDelete(item)}
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {result && (
        <section className="card">
          <h2 className="page__title">Result</h2>
          <ResultsView result={result} question={activeQuestion} />
        </section>
      )}
    </div>
  );
}
