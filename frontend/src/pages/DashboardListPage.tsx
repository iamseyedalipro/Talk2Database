import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createDashboard, deleteDashboard, listDashboards } from '../api/endpoints';
import type { DashboardItem } from '../api/types';
import { ErrorBanner, Spinner } from '../components/ui';
import { errorMessage, formatDate } from '../utils/format';

/** All dashboards the user may open: their own plus shared ones. */
export default function DashboardListPage() {
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
    if (!window.confirm(`Delete dashboard "${dashboard.name}"? This cannot be undone.`)) return;
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
        <h1 className="page__title">Dashboards</h1>
        <p className="muted">
          Arrange saved SQL as live tables and charts. Private by default; share one to make it
          visible to every panel user.
        </p>

        <form className="dashboard-create" onSubmit={handleCreate}>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New dashboard name…"
            maxLength={200}
            aria-label="Dashboard name"
          />
          <label className="field field--checkbox">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            <span>Share with everyone</span>
          </label>
          <button type="submit" className="btn btn--primary" disabled={creating || !name.trim()}>
            {creating ? 'Creating…' : 'Create dashboard'}
          </button>
        </form>

        <ErrorBanner message={error} />
      </section>

      <section className="card">
        {loading ? (
          <Spinner label="Loading dashboards…" />
        ) : dashboards.length === 0 ? (
          <p className="muted">No dashboards yet. Create your first one above.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Widgets</th>
                  <th>Visibility</th>
                  <th>Owner</th>
                  <th>Updated</th>
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
                        <span className="pill pill--busy">Shared</span>
                      ) : (
                        <span className="pill pill--neutral">Private</span>
                      )}
                    </td>
                    <td>{d.is_owner ? 'You' : (d.owner_email ?? '—')}</td>
                    <td>{formatDate(d.updated_at)}</td>
                    <td>
                      <div className="row-actions">
                        <Link className="btn btn--secondary btn--small" to={`/dashboards/${d.id}`}>
                          Open
                        </Link>
                        {d.is_owner && (
                          <button
                            type="button"
                            className="btn btn--danger btn--small"
                            onClick={() => void handleDelete(d)}
                          >
                            Delete
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
