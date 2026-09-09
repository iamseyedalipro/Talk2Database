import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  deleteSavedQuery,
  listSavedQueries,
  runSavedQuery,
  updateSavedQuery,
} from '../api/endpoints';
import type { ExecuteResponse, SavedQuery, SavedQueryUpdate } from '../api/types';
import ResultsView from '../components/ResultsView';
import { ErrorBanner, InfoBanner, Spinner } from '../components/ui';
import { useAuthStore } from '../store/auth';
import { errorMessage, formatDate, truncate } from '../utils/format';

/** The editable fields of a saved query, as held while the detail panel is in edit mode. */
interface Draft {
  name: string;
  question: string;
  sql: string;
  shared: boolean;
}

/** The panel shown beneath the table: the full record, optionally in edit mode. */
interface DetailState {
  item: SavedQuery;
  editing: boolean;
  draft: Draft;
}

const draftOf = (item: SavedQuery): Draft => ({
  name: item.name,
  question: item.question ?? '',
  sql: item.generated_sql,
  shared: item.shared,
});

/**
 * The "Questions" library: a user's saved queries plus any shared by others.
 * Open a row to read its full SQL, run it (executes the stored SQL — no AI
 * call), copy it, or, for queries you can manage, edit the name, question,
 * SQL and sharing.
 */
export default function SavedQueriesPage() {
  const { t } = useTranslation('saved');
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin');
  const canManage = (item: SavedQuery) => item.is_owner || (isAdmin && item.shared);

  const [items, setItems] = useState<SavedQuery[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null);
  const [result, setResult] = useState<ExecuteResponse | null>(null);

  const [detail, setDetail] = useState<DetailState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const list = await listSavedQueries(200, 0);
      setItems(list);
      // Keep an open detail panel in sync with the refreshed list; close it if
      // the query is gone (deleted elsewhere, or un-shared by its owner).
      setDetail((prev) => {
        if (!prev) return prev;
        const fresh = list.find((q) => q.id === prev.item.id);
        if (!fresh) return null;
        return prev.editing
          ? { ...prev, item: fresh }
          : { ...prev, item: fresh, draft: draftOf(fresh) };
      });
    } catch (err) {
      setListError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openDetail = (item: SavedQuery, editing = false) => {
    setActionError(null);
    setNotice(null);
    setDetail({ item, editing: editing && canManage(item), draft: draftOf(item) });
  };

  const closeDetail = () => {
    setDetail(null);
    setActionError(null);
    setNotice(null);
  };

  const handleRun = async (item: SavedQuery) => {
    setActionError(null);
    setNotice(null);
    setResult(null);
    setRunningId(item.id);
    setActiveQuestion(item.question);
    try {
      setResult(await runSavedQuery(item.id));
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setRunningId(null);
    }
  };

  const handleDelete = async (item: SavedQuery) => {
    if (!window.confirm(t('deleteConfirm', { name: item.name }))) return;
    setActionError(null);
    setNotice(null);
    try {
      await deleteSavedQuery(item.id);
      if (detail?.item.id === item.id) setDetail(null);
      setResult(null);
      void load();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  };

  const handleCopy = async (sql: string) => {
    setActionError(null);
    try {
      await navigator.clipboard.writeText(sql);
      setNotice(t('copied'));
    } catch {
      setActionError(t('copyFailed'));
    }
  };

  const handleSaveEdit = async () => {
    if (!detail) return;
    const { item, draft } = detail;
    const body: SavedQueryUpdate = {};
    if (draft.name.trim() !== item.name) body.name = draft.name.trim();
    if (draft.sql.trim() !== item.generated_sql) body.generated_sql = draft.sql.trim();
    if (draft.question.trim() !== (item.question ?? ''))
      body.question = draft.question.trim() || null;
    if (draft.shared !== item.shared) body.shared = draft.shared;

    setActionError(null);
    setNotice(null);
    setSaving(true);
    try {
      const updated = Object.keys(body).length > 0 ? await updateSavedQuery(item.id, body) : item;
      setDetail({ item: updated, editing: false, draft: draftOf(updated) });
      setNotice(t('savedNotice'));
      void load();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const detailEditable = detail ? canManage(detail.item) : false;
  const draftValid = detail
    ? detail.draft.name.trim().length > 0 && detail.draft.sql.trim().length > 0
    : false;

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
        <ErrorBanner message={actionError} />
        {notice && <InfoBanner>{notice}</InfoBanner>}

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
                    <td>{item.name}</td>
                    <td title={item.question ?? ''}>{truncate(item.question ?? '—', 50)}</td>
                    <td title={item.generated_sql}>
                      <code className="inline-sql">{truncate(item.generated_sql, 40)}</code>
                    </td>
                    <td>
                      {item.shared ? (
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
                      <button
                        type="button"
                        className="btn btn--small btn--primary"
                        onClick={() => void handleRun(item)}
                        disabled={runningId === item.id}
                      >
                        {runningId === item.id ? t('running') : t('run')}
                      </button>
                      <button
                        type="button"
                        className="btn btn--small"
                        onClick={() => openDetail(item)}
                      >
                        {t('view')}
                      </button>
                      {canManage(item) && (
                        <>
                          <button
                            type="button"
                            className="btn btn--small"
                            onClick={() => openDetail(item, true)}
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {detail && (
        <section className="card">
          <div className="page__header">
            <h2 className="page__title">
              {t('detailTitle')} — {detail.item.name}
            </h2>
            <button type="button" className="btn btn--ghost" onClick={closeDetail}>
              {t('close')}
            </button>
          </div>

          {detail.editing ? (
            <>
              <label className="field">
                <span>{t('nameLabel')}</span>
                <input
                  type="text"
                  value={detail.draft.name}
                  maxLength={200}
                  aria-label={t('nameAria')}
                  onChange={(e) =>
                    setDetail({ ...detail, draft: { ...detail.draft, name: e.target.value } })
                  }
                />
              </label>

              <label className="field">
                <span>{t('questionLabel')}</span>
                <textarea
                  rows={2}
                  value={detail.draft.question}
                  aria-label={t('questionAria')}
                  onChange={(e) =>
                    setDetail({ ...detail, draft: { ...detail.draft, question: e.target.value } })
                  }
                />
              </label>

              <label className="field field--checkbox">
                <input
                  type="checkbox"
                  checked={detail.draft.shared}
                  aria-label={t('sharedAria')}
                  onChange={(e) =>
                    setDetail({ ...detail, draft: { ...detail.draft, shared: e.target.checked } })
                  }
                />
                <span>{t('sharedLabel')}</span>
              </label>
            </>
          ) : (
            <>
              <p className="detail-question">
                <strong>{t('questionLabel')}:</strong>{' '}
                {detail.item.question ?? <span className="muted">{t('noQuestion')}</span>}
              </p>
              <p className="muted">
                {t('ownerLabel')}:{' '}
                {detail.item.is_owner ? t('you') : (detail.item.owner_email ?? '—')}
                {' · '}
                {detail.item.shared ? t('sharedPill') : t('privatePill')}
                {' · '}
                {formatDate(detail.item.created_at)}
              </p>
            </>
          )}

          <h3>{t('sqlLabel')}</h3>
          {detail.editing ? (
            <textarea
              className="sql-editor"
              value={detail.draft.sql}
              spellCheck={false}
              rows={10}
              aria-label={t('sqlAria')}
              onChange={(e) =>
                setDetail({ ...detail, draft: { ...detail.draft, sql: e.target.value } })
              }
            />
          ) : (
            <pre className="sql-box">
              <code>{detail.item.generated_sql}</code>
            </pre>
          )}

          {!detail.editing && !detailEditable && <p className="muted">{t('readOnlyHint')}</p>}

          <div className="detail-actions">
            {detail.editing ? (
              <>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={saving || !draftValid}
                  onClick={() => void handleSaveEdit()}
                >
                  {saving ? t('running') : t('saveChanges')}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={saving}
                  onClick={() =>
                    setDetail({ ...detail, editing: false, draft: draftOf(detail.item) })
                  }
                >
                  {t('cancel')}
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={runningId === detail.item.id}
                  onClick={() => void handleRun(detail.item)}
                >
                  {runningId === detail.item.id ? t('running') : t('run')}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={() => void handleCopy(detail.item.generated_sql)}
                >
                  {t('copySql')}
                </button>
                {detailEditable && (
                  <button
                    type="button"
                    className="btn btn--secondary"
                    onClick={() =>
                      setDetail({ ...detail, editing: true, draft: draftOf(detail.item) })
                    }
                  >
                    {t('editDetails')}
                  </button>
                )}
              </>
            )}
          </div>
        </section>
      )}

      {result && (
        <section className="card">
          <h2 className="page__title">{t('resultTitle')}</h2>
          <ResultsView result={result} question={activeQuestion} />
        </section>
      )}
    </div>
  );
}
