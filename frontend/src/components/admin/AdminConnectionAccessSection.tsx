import { useCallback, useEffect, useState } from 'react';
import {
  getUserConnectionAccess,
  listConnections,
  listUsers,
  setUserConnectionAccess,
} from '../../api/endpoints';
import type { Connection, User } from '../../api/types';
import { errorMessage } from '../../utils/format';
import { ErrorBanner, InfoBanner, Spinner } from '../ui';

/**
 * User-first connection sharing: pick a user, then check which connections they
 * can access. Connections the user owns are always accessible (shown checked and
 * disabled); the rest are grants an admin can toggle and save.
 */
export default function AdminConnectionAccessSection() {
  const [users, setUsers] = useState<User[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [granted, setGranted] = useState<Set<number>>(new Set());
  const [accessLoading, setAccessLoading] = useState(false);
  const [accessError, setAccessError] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const loadBase = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [u, c] = await Promise.all([listUsers(), listConnections()]);
      setUsers(u);
      setConnections(c);
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBase();
  }, [loadBase]);

  // Load the selected user's current grants whenever the selection changes.
  useEffect(() => {
    if (selectedUserId == null) {
      setGranted(new Set());
      return;
    }
    let cancelled = false;
    setAccessLoading(true);
    setAccessError(null);
    setSaved(false);
    getUserConnectionAccess(selectedUserId)
      .then((res) => {
        if (!cancelled) setGranted(new Set(res.connection_ids));
      })
      .catch((err) => {
        if (!cancelled) setAccessError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setAccessLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedUserId]);

  const toggle = (connectionId: number) => {
    setSaved(false);
    setGranted((prev) => {
      const next = new Set(prev);
      if (next.has(connectionId)) next.delete(connectionId);
      else next.add(connectionId);
      return next;
    });
  };

  const handleSave = async () => {
    if (selectedUserId == null) return;
    setSaving(true);
    setAccessError(null);
    setSaved(false);
    try {
      const res = await setUserConnectionAccess(selectedUserId, Array.from(granted));
      setGranted(new Set(res.connection_ids));
      setSaved(true);
    } catch (err) {
      setAccessError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">Connection access</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void loadBase()}>
          Refresh
        </button>
      </div>

      <p className="muted">
        Grant a user access to connections they don&apos;t own. Granted users can ask
        questions, run read-only queries, browse the schema, and edit the glossary — but
        cannot change or delete the connection.
      </p>

      <ErrorBanner message={loadError} />

      {loading ? (
        <Spinner label="Loading…" />
      ) : (
        <>
          <label className="field">
            <span>User</span>
            <select
              value={selectedUserId ?? ''}
              onChange={(e) =>
                setSelectedUserId(e.target.value === '' ? null : Number(e.target.value))
              }
            >
              <option value="">Select a user…</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.email}
                  {u.role === 'admin' ? ' (admin)' : ''}
                </option>
              ))}
            </select>
          </label>

          {selectedUserId != null && (
            <div className="subsection">
              <ErrorBanner message={accessError} />
              {accessLoading ? (
                <Spinner label="Loading access…" />
              ) : connections.length === 0 ? (
                <p className="muted">There are no connections to share yet.</p>
              ) : (
                <>
                  <ul className="access-list">
                    {connections.map((conn) => {
                      const owned = conn.owner_id === selectedUserId;
                      return (
                        <li key={conn.id} className="access-list__item">
                          <label className="field field--inline">
                            <input
                              type="checkbox"
                              checked={owned || granted.has(conn.id)}
                              disabled={owned || saving}
                              onChange={() => toggle(conn.id)}
                            />
                            <span>
                              {conn.name}{' '}
                              <span className="muted">
                                ({conn.type} · {conn.host})
                              </span>
                              {owned && <span className="pill pill--neutral">owner</span>}
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>

                  <div className="results-view__actions">
                    <button
                      type="button"
                      className="btn btn--primary"
                      onClick={() => void handleSave()}
                      disabled={saving}
                    >
                      {saving ? 'Saving…' : 'Save access'}
                    </button>
                  </div>

                  {saved && <InfoBanner>Access updated.</InfoBanner>}
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
