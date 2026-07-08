import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { createDashboard, deleteDashboard, listDashboards } from '../api/endpoints';
import type { DashboardItem } from '../api/types';
import { ErrorBanner, Spinner } from '../components/ui';
import { errorMessage, formatDate } from '../utils/format';

/** All dashboards the user may open: their own plus shared ones. */
export default function DashboardListPage() {
  const { t } = useTranslation('dashboards');
  const navigate = useNavigate();
  const [dashboards, setDashboards] = useState<DashboardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [shared, setShared] = useState(false);
  const [creating, setCreating] = useState(false);

  const load = () => {
    setLoading(true);
    listDashboards()
      .then(setDashboards)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      const dashboard = await createDashboard({ name: name.trim(), shared });
      navigate(`/dashboards/${dashboard.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setCreating(false);
    }
  };

  const handleDelete = async (dashboard: DashboardItem) => {
    if (!window.confirm(t('deleteConfirm', { name: dashboard.name }))) return;
    setError(null);
    try {
      await deleteDashboard(dashboard.id);
      setDashboards((prev) => prev.filter((d) => d.id !== dashboard.id));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="page">
      <section className="card">
        <h1 className="page__title">{t('title')}</h1>
        <p className="muted">{t('intro')}</p>

        <form className="dashboard-create" onSubmit={handleCreate}>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('newNamePlaceholder')}
            maxLength={200}
            aria-label={t('dashboardName')}
          />
          <label className="field field--checkbox">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            <span>{t('shareWithEveryone')}</span>
          </label>
          <button type="submit" className="btn btn--primary" disabled={creating || !name.trim()}>
            {creating ? t('creating') : t('createDashboard')}
          </button>
        </form>

        <ErrorBanner message={error} />
      </section>

      <section className="card">
        {loading ? (
          <Spinner label={t('loadingDashboards')} />
        ) : dashboards.length === 0 ? (
          <p className="muted">{t('noDashboards')}</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('colName')}</th>
                  <th>{t('colWidgets')}</th>
                  <th>{t('colVisibility')}</th>
                  <th>{t('colOwner')}</th>
                  <th>{t('colUpdated')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {dashboards.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/dashboards/${d.id}`}>{d.name}</Link>
                      {d.description && <div className="muted">{d.description}</div>}
                    </td>
                    <td>{d.widget_count}</td>
                    <td>
                      {d.shared ? (
                        <span className="pill pill--busy">{t('shared')}</span>
                      ) : (
                        <span className="pill pill--neutral">{t('private')}</span>
                      )}
                      {!d.is_owner && (
                        <span className="pill pill--neutral">
                          {d.my_access === 'edit' ? t('accessCanEdit') : t('accessCanView')}
                        </span>
                      )}
                    </td>
                    <td>{d.is_owner ? t('you') : (d.owner_email ?? '—')}</td>
                    <td>{formatDate(d.updated_at)}</td>
                    <td>
                      <div className="row-actions">
                        <Link className="btn btn--secondary btn--small" to={`/dashboards/${d.id}`}>
                          {t('open')}
                        </Link>
                        {d.is_owner && (
                          <button
                            type="button"
                            className="btn btn--danger btn--small"
                            onClick={() => void handleDelete(d)}
                          >
                            {t('delete')}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
