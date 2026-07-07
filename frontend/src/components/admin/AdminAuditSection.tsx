import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('admin');
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
        <h2 className="page__title">{t('audit.title')}</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          {t('refresh')}
        </button>
      </div>
      <p className="muted">{t('audit.description')}</p>

      <div className="audit-filters">
        <label className="field field--inline">
          <span>{t('audit.statusLabel')}</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
            <option value="all">{t('audit.statusAll')}</option>
            <option value="preview">{t('audit.statusPreview')}</option>
            <option value="success">{t('audit.statusSuccess')}</option>
            <option value="error">{t('audit.statusError')}</option>
          </select>
        </label>
        <input
          type="search"
          placeholder={t('audit.searchPlaceholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={t('audit.searchAria')}
        />
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <Spinner label={t('audit.loading')} />
      ) : items.length === 0 ? (
        <p className="muted">{t('audit.empty')}</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('audit.colUser')}</th>
                <th>{t('audit.colQuestion')}</th>
                <th>{t('audit.colSql')}</th>
                <th>{t('audit.colStatus')}</th>
                <th>{t('audit.colRows')}</th>
                <th>{t('audit.colWhen')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td title={item.user_email ?? ''}>{item.user_email ?? `#${item.user_id}`}</td>
                  <td title={item.question}>{truncate(item.question, 50)}</td>
                  <td>
                    {item.generated_sql ? (
                      <code className="inline-sql">{truncate(item.generated_sql, 40)}</code>
                    ) : (
                      <span className="muted">{t('audit.clarificationAsked')}</span>
                    )}
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
