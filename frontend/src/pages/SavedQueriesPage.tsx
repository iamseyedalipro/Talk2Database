import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('saved');
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
    if (!window.confirm(t('deleteConfirm', { name: item.name }))) return;
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
          <h1 className="page__title">{t('title')}</h1>
          <button type="button" className="btn btn--ghost" onClick={() => void load()}>
            {t('refresh')}
          </button>
        </div>

        <p className="muted">{t('subtitle')}</p>

        <ErrorBanner message={listError} />
        <ErrorBanner message={runError} />

        {loading ? (
          <Spinner label={t('loading')} />
        ) : items.length === 0 ? (
          <p className="muted">{t('emptyState')}</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('colName')}</th>
                  <th>{t('colQuestion')}</th>
                  <th>{t('colSql')}</th>
                  <th>{t('colShared')}</th>
                  <th>{t('colOwner')}</th>
                  <th>{t('colCreated')}</th>
                  <th aria-label={t('actions')} />
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
                          aria-label={t('nameAria')}
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
                          aria-label={t('sharedAria')}
                        />
                      ) : item.shared ? (
                        <span className="pill pill--ok">{t('sharedPill')}</span>
                      ) : (
                        <span className="pill pill--neutral">{t('privatePill')}</span>
                      )}
                    </td>
                    <td title={item.owner_email ?? ''}>
                      {item.is_owner ? t('you') : (item.owner_email ?? '—')}
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
                            {t('save')}
                          </button>
                          <button
                            type="button"
                            className="btn btn--small btn--ghost"
                            onClick={() => setEdit(null)}
                          >
                            {t('cancel')}
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
                            {runningId === item.id ? t('running') : t('run')}
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
                                {t('edit')}
                              </button>
                              <button
                                type="button"
                                className="btn btn--small btn--danger"
                                onClick={() => void handleDelete(item)}
                              >
                                {t('delete')}
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
          <h2 className="page__title">{t('resultTitle')}</h2>
          <ResultsView result={result} question={activeQuestion} />
        </section>
      )}
    </div>
  );
}
