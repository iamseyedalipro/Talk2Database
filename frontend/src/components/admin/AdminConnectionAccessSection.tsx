import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getUserConnectionAccess,
  listConnections,
  listUsers,
  setUserConnectionAccess,
} from '../../api/endpoints';
import type { Connection, User } from '../../api/types';
import { errorMessage } from '../../utils/format';
import { ErrorBanner, InfoBanner, Spinner } from '../ui';

const setsEqual = (a: Set<number>, b: Set<number>): boolean =>
  a.size === b.size && [...a].every((x) => b.has(x));

/**
 * User-first connection sharing: pick a user, then choose which connections they
 * can access. Connections the user owns are always accessible (shown grouped and
 * locked); the rest are grants an admin can toggle, search, bulk-select, and save.
 */
export default function AdminConnectionAccessSection() {
  const { t } = useTranslation('admin');
  const [users, setUsers] = useState<User[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [granted, setGranted] = useState<Set<number>>(new Set());
  const [savedGranted, setSavedGranted] = useState<Set<number>>(new Set());
  const [accessLoading, setAccessLoading] = useState(false);
  const [accessError, setAccessError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [query, setQuery] = useState('');

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
      setSavedGranted(new Set());
      return;
    }
    let cancelled = false;
    setAccessLoading(true);
    setAccessError(null);
    setQuery('');
    getUserConnectionAccess(selectedUserId)
      .then((res) => {
        if (cancelled) return;
        setGranted(new Set(res.connection_ids));
        setSavedGranted(new Set(res.connection_ids));
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

  const selectedUser = users.find((u) => u.id === selectedUserId) ?? null;
  const isAdminUser = selectedUser?.role === 'admin';
  const dirty = !setsEqual(granted, savedGranted);

  // Split the selected user's view into connections they own (implicit access)
  // and connections that can be shared with them, honoring the search filter.
  const { owned, shareable } = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = (c: Connection) =>
      !q ||
      c.name.toLowerCase().includes(q) ||
      c.type.toLowerCase().includes(q) ||
      c.host.toLowerCase().includes(q) ||
      c.database.toLowerCase().includes(q);
    const ownedRows: Connection[] = [];
    const shareableRows: Connection[] = [];
    for (const c of connections) {
      if (!matches(c)) continue;
      if (c.owner_id === selectedUserId) ownedRows.push(c);
      else shareableRows.push(c);
    }
    return { owned: ownedRows, shareable: shareableRows };
  }, [connections, selectedUserId, query]);

  // Totals are across ALL shareable connections, not just the filtered view.
  const totalShareable = useMemo(
    () => connections.filter((c) => c.owner_id !== selectedUserId).length,
    [connections, selectedUserId],
  );
  const grantedCount = useMemo(
    () =>
      connections.filter((c) => c.owner_id !== selectedUserId && granted.has(c.id)).length,
    [connections, selectedUserId, granted],
  );

  const toggle = (connectionId: number) => {
    setGranted((prev) => {
      const next = new Set(prev);
      if (next.has(connectionId)) next.delete(connectionId);
      else next.add(connectionId);
      return next;
    });
  };

  // Bulk actions operate on the currently visible (filtered) shareable rows.
  const selectAllVisible = () =>
    setGranted((prev) => {
      const next = new Set(prev);
      shareable.forEach((c) => next.add(c.id));
      return next;
    });
  const clearAllVisible = () =>
    setGranted((prev) => {
      const next = new Set(prev);
      shareable.forEach((c) => next.delete(c.id));
      return next;
    });

  const chooseUser = (value: string) => {
    if (dirty && !window.confirm(t('access.confirmDiscard'))) return;
    setSelectedUserId(value === '' ? null : Number(value));
  };

  const handleSave = async () => {
    if (selectedUserId == null) return;
    setSaving(true);
    setAccessError(null);
    try {
      const res = await setUserConnectionAccess(selectedUserId, Array.from(granted));
      setGranted(new Set(res.connection_ids));
      setSavedGranted(new Set(res.connection_ids));
    } catch (err) {
      setAccessError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const renderRow = (conn: Connection, locked: boolean) => (
    <label
      key={conn.id}
      className={locked ? 'access-row access-row--locked' : 'access-row'}
    >
      <input
        type="checkbox"
        className="access-row__check"
        checked={locked || granted.has(conn.id)}
        disabled={locked || saving}
        onChange={() => toggle(conn.id)}
      />
      <span className="access-row__info">
        <span className="access-row__name">{conn.name}</span>
        <span className="access-row__meta">
          {conn.type} · {conn.host} · {conn.database}
        </span>
      </span>
      {locked && <span className="pill pill--neutral">{t('access.ownerPill')}</span>}
    </label>
  );

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">{t('access.title')}</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void loadBase()}>
          {t('refresh')}
        </button>
      </div>

      <p className="muted">{t('access.description')}</p>

      <ErrorBanner message={loadError} />

      {loading ? (
        <Spinner label={t('access.loading')} />
      ) : (
        <>
          <label className="field">
            <span>{t('access.userLabel')}</span>
            <select value={selectedUserId ?? ''} onChange={(e) => chooseUser(e.target.value)}>
              <option value="">{t('access.selectUser')}</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.email}
                  {u.role === 'admin' ? t('access.adminSuffix') : ''}
                </option>
              ))}
            </select>
          </label>

          {selectedUserId != null && (
            <div className="access-panel">
              <ErrorBanner message={accessError} />

              {accessLoading ? (
                <Spinner label={t('access.loadingAccess')} />
              ) : isAdminUser ? (
                <InfoBanner>{t('access.adminHasAccess', { email: selectedUser?.email })}</InfoBanner>
              ) : connections.length === 0 ? (
                <p className="muted">{t('access.noConnectionsYet')}</p>
              ) : (
                <>
                  <div className="access-toolbar">
                    <input
                      type="search"
                      className="access-search"
                      placeholder={t('access.searchPlaceholder')}
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                    <div className="access-toolbar__right">
                      <span className="access-count muted">
                        {t('access.grantedCount', { granted: grantedCount, total: totalShareable })}
                      </span>
                      <button
                        type="button"
                        className="btn btn--ghost btn--small"
                        onClick={selectAllVisible}
                        disabled={saving || shareable.length === 0}
                      >
                        {t('access.selectAll')}
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost btn--small"
                        onClick={clearAllVisible}
                        disabled={saving || shareable.length === 0}
                      >
                        {t('access.clearAll')}
                      </button>
                    </div>
                  </div>

                  <div className="access-groups">
                    {owned.length > 0 && (
                      <div className="access-group">
                        <div className="access-group__title">{t('access.ownedByUser')}</div>
                        {owned.map((c) => renderRow(c, true))}
                      </div>
                    )}

                    <div className="access-group">
                      <div className="access-group__title">{t('access.availableConnections')}</div>
                      {shareable.length === 0 ? (
                        <p className="muted access-empty">
                          {query.trim() ? t('access.noSearchMatch') : t('access.noOtherConnections')}
                        </p>
                      ) : (
                        shareable.map((c) => renderRow(c, false))
                      )}
                    </div>
                  </div>

                  <div className="access-actions">
                    <span className={dirty ? 'access-dirty' : 'access-dirty muted'}>
                      {dirty ? t('access.unsavedChanges') : t('access.allSaved')}
                    </span>
                    <button
                      type="button"
                      className="btn btn--primary"
                      onClick={() => void handleSave()}
                      disabled={saving || !dirty}
                    >
                      {saving ? t('access.saving') : t('access.saveAccess')}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
