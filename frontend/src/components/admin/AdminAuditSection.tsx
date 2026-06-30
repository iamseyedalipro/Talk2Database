import { useCallback, useEffect, useState } from 'react';
import { listAudit } from '../../api/endpoints';
import { ApiError } from '../../api/client';
import type { AuditItem, QueryStatus } from '../../api/types';
import { errorMessage, formatDate, truncate } from '../../utils/format';
import { ErrorBanner, Spinner, StatusPill } from '../ui';

type StatusFilter = QueryStatus | 'all';

/**
 * Admin-only feed over query history: who asked what. No row data is shown
 * (none is stored). Hides itself entirely when the feature is disabled
 * server-side (ADMIN_AUDIT_ENABLED=false → 404).
 */
export default function AdminAuditSection() {
  const [items, setItems] = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);

  const [status, setStatus] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAudit({
        status: status === 'all' ? undefined : status,
        q: search.trim() || undefined,
        limit: 200,
      });
      setItems(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setDisabled(true);
        return;
      }
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [status, search]);

  useEffect(() => {
    void load();
  }, [load]);

  if (disabled) return null;

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">Audit log</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <p className="muted">Every user's questions and generated SQL. Result rows are never stored.</p>

      <div className="audit-filters">
        <label className="field field--inline">
          <span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
            <option value="all">all</option>
            <option value="preview">preview</option>
            <option value="success">success</option>
            <option value="error">error</option>
          </select>
        </label>
        <input
          type="search"
          placeholder="Search questions…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search questions"
        />
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <Spinner label="Loading audit log…" />
      ) : items.length === 0 ? (
        <p className="muted">No matching queries.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Question</th>
                <th>SQL</th>
                <th>Status</th>
                <th>Rows</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td title={item.user_email ?? ''}>{item.user_email ?? `#${item.user_id}`}</td>
                  <td title={item.question}>{truncate(item.question, 50)}</td>
                  <td>
                    <code className="inline-sql">{truncate(item.generated_sql, 40)}</code>
                  </td>
                  <td>
                    <StatusPill status={item.last_status} />
                  </td>
                  <td>{item.row_count ?? '—'}</td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
