import { useCallback, useEffect, useState } from 'react';
import {
  createConnection,
  deleteConnection,
  listConnections,
  testConnection,
  updateConnection,
} from '../api/endpoints';
import type { Connection, ConnectionCreate, DataSourceType } from '../api/types';
import { ErrorBanner } from '../components/ui';
import { errorMessage, formatDate } from '../utils/format';

const TYPES: DataSourceType[] = ['postgres', 'mysql', 'mariadb'];
const DEFAULT_PORT: Record<DataSourceType, number> = {
  postgres: 5432,
  mysql: 3306,
  mariadb: 3306,
};

type FormState = ConnectionCreate;

const emptyForm = (): FormState => ({
  name: '',
  type: 'postgres',
  host: '',
  port: DEFAULT_PORT.postgres,
  database: '',
  username: '',
  password: '',
});

/**
 * Manage data-source connections. A user registers connections to their own
 * databases here; the Ask page then queries the selected one live and read-only.
 */
export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [form, setForm] = useState<FormState>(emptyForm());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [testResult, setTestResult] = useState<Record<number, string>>({});
  const [testingId, setTestingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setConnections(await listConnections());
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const resetForm = () => {
    setForm(emptyForm());
    setEditingId(null);
    setFormError(null);
  };

  const startEdit = (c: Connection) => {
    setEditingId(c.id);
    setFormError(null);
    setForm({
      name: c.name,
      type: c.type,
      host: c.host,
      port: c.port,
      database: c.database,
      username: c.username,
      password: '', // blank = keep existing
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      if (editingId !== null) {
        // Omit password when left blank so the stored secret is kept.
        const { password, ...rest } = form;
        await updateConnection(editingId, password ? form : rest);
      } else {
        await createConnection(form);
      }
      resetForm();
      await load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (id: number) => {
    setTestingId(id);
    setTestResult((prev) => ({ ...prev, [id]: 'Testing…' }));
    try {
      const res = await testConnection(id);
      setTestResult((prev) => ({
        ...prev,
        [id]: res.ok ? '✓ Reachable' : `✗ ${res.message ?? 'Unreachable'}`,
      }));
    } catch (err) {
      setTestResult((prev) => ({ ...prev, [id]: `✗ ${errorMessage(err)}` }));
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Delete this connection? Its cached schema is removed too.')) return;
    try {
      await deleteConnection(id);
      if (editingId === id) resetForm();
      await load();
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  };

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="page">
      <section className="card">
        <h1 className="page__title">Connections</h1>
        <p className="muted">
          Connect to your own databases. Queries run live and read-only — for the strongest
          safety, point each connection at a read-only database user.
        </p>

        <ErrorBanner message={loadError} />

        {connections.length === 0 ? (
          <p className="muted">No connections yet. Add one below to start asking questions.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Host</th>
                  <th>Database</th>
                  <th>User</th>
                  <th>Created</th>
                  <th>Test</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {connections.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td>{c.type}</td>
                    <td>
                      {c.host}:{c.port}
                    </td>
                    <td>{c.database}</td>
                    <td>{c.username}</td>
                    <td>{formatDate(c.created_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => handleTest(c.id)}
                        disabled={testingId === c.id}
                      >
                        Test
                      </button>
                      {testResult[c.id] && (
                        <span className="muted" style={{ marginLeft: 8 }}>
                          {testResult[c.id]}
                        </span>
                      )}
                    </td>
                    <td>
                      <button type="button" className="btn btn--ghost" onClick={() => startEdit(c)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => handleDelete(c.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="page__title">{editingId !== null ? 'Edit connection' : 'Add a connection'}</h2>
        <form className="connection-form" onSubmit={handleSubmit}>
          <label>
            Name
            <input
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              required
              placeholder="Production analytics"
            />
          </label>
          <label>
            Type
            <select
              value={form.type}
              onChange={(e) => {
                const type = e.target.value as DataSourceType;
                update('type', type);
                // Snap to the default port for the chosen engine if untouched.
                if (Object.values(DEFAULT_PORT).includes(form.port)) update('port', DEFAULT_PORT[type]);
              }}
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label>
            Host
            <input
              value={form.host}
              onChange={(e) => update('host', e.target.value)}
              required
              placeholder="db.example.com"
            />
          </label>
          <label>
            Port
            <input
              type="number"
              value={form.port}
              onChange={(e) => update('port', Number(e.target.value))}
              required
              min={1}
              max={65535}
            />
          </label>
          <label>
            Database
            <input
              value={form.database}
              onChange={(e) => update('database', e.target.value)}
              required
            />
          </label>
          <label>
            Username
            <input
              value={form.username}
              onChange={(e) => update('username', e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={form.password}
              onChange={(e) => update('password', e.target.value)}
              placeholder={editingId !== null ? 'leave blank to keep current' : ''}
            />
          </label>

          <ErrorBanner message={formError} />

          <div className="ask-form__actions">
            <button type="submit" className="btn btn--primary" disabled={saving}>
              {saving ? 'Saving…' : editingId !== null ? 'Save changes' : 'Add connection'}
            </button>
            {editingId !== null && (
              <button type="button" className="btn btn--ghost" onClick={resetForm}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </section>
    </div>
  );
}
