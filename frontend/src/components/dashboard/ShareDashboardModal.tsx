import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getDashboardShares,
  listUserDirectory,
  setDashboardShares,
  updateDashboard,
} from '../../api/endpoints';
import type { ShareAccess, UserDirectoryEntry } from '../../api/types';
import { errorMessage } from '../../utils/format';
import { ErrorBanner, Spinner } from '../ui';

/** No access is represented by the absence of a map entry. */
type AccessMap = Map<number, ShareAccess>;

const sameAccess = (a: AccessMap, b: AccessMap): boolean => {
  if (a.size !== b.size) return false;
  for (const [k, v] of a) if (b.get(k) !== v) return false;
  return true;
};

interface Props {
  dashboardId: number;
  /** Current "share with everyone" state; kept in sync via onSharedChange. */
  shared: boolean;
  onSharedChange: (shared: boolean) => void;
  onClose: () => void;
}

/**
 * Owner-facing dialog to share a dashboard with specific people. Each user can
 * be given No access / View / Edit, on top of the global "share with everyone"
 * toggle. Modeled on the admin connection-access manager.
 */
export default function ShareDashboardModal({
  dashboardId,
  shared,
  onSharedChange,
  onClose,
}: Props) {
  const { t } = useTranslation('dashboards');
  const [users, setUsers] = useState<UserDirectoryEntry[]>([]);
  const [access, setAccess] = useState<AccessMap>(new Map());
  const [savedAccess, setSavedAccess] = useState<AccessMap>(new Map());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sharedBusy, setSharedBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([listUserDirectory(), getDashboardShares(dashboardId)])
      .then(([dir, shares]) => {
        if (cancelled) return;
        setUsers(dir);
        const map: AccessMap = new Map(shares.map((s) => [s.user_id, s.access_level]));
        setAccess(new Map(map));
        setSavedAccess(new Map(map));
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dashboardId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !saving) onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [saving, onClose]);

  const dirty = !sameAccess(access, savedAccess);

  const visibleUsers = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? users.filter((u) => u.email.toLowerCase().includes(q)) : users;
  }, [users, query]);

  const grantedCount = access.size;

  const setUserAccess = (userId: number, value: '' | ShareAccess) => {
    setAccess((prev) => {
      const next = new Map(prev);
      if (value === '') next.delete(userId);
      else next.set(userId, value);
      return next;
    });
  };

  const clearAll = () => setAccess(new Map());

  const handleToggleShared = async () => {
    setSharedBusy(true);
    setError(null);
    try {
      const updated = await updateDashboard(dashboardId, { shared: !shared });
      onSharedChange(updated.shared);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSharedBusy(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const shares = Array.from(access, ([user_id, access_level]) => ({ user_id, access_level }));
      const result = await setDashboardShares(dashboardId, shares);
      const map: AccessMap = new Map(result.map((s) => [s.user_id, s.access_level]));
      setAccess(new Map(map));
      setSavedAccess(new Map(map));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={t('share.title')}>
      <div className="modal modal--wide">
        <header className="modal__header">
          <h2>{t('share.title')}</h2>
          <p className="modal__sub">{t('share.description')}</p>
        </header>

        <div className="modal__body">
          <ErrorBanner message={error} />

          <label className="access-row">
            <input
              type="checkbox"
              className="access-row__check"
              checked={shared}
              disabled={sharedBusy}
              onChange={() => void handleToggleShared()}
            />
            <span className="access-row__info">
              <span className="access-row__name">{t('share.everyoneLabel')}</span>
              <span className="access-row__meta">{t('share.everyoneHint')}</span>
            </span>
          </label>

          {loading ? (
            <Spinner label={t('share.loading')} />
          ) : users.length === 0 ? (
            <p className="muted">{t('share.noUsers')}</p>
          ) : (
            <>
              <div className="access-toolbar">
                <input
                  type="search"
                  className="access-search"
                  placeholder={t('share.searchPlaceholder')}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <div className="access-toolbar__right">
                  <span className="access-count muted">
                    {t('share.grantedCount', { granted: grantedCount, total: users.length })}
                  </span>
                  <button
                    type="button"
                    className="btn btn--ghost btn--small"
                    onClick={clearAll}
                    disabled={saving || grantedCount === 0}
                  >
                    {t('share.clearAll')}
                  </button>
                </div>
              </div>

              <div className="access-group">
                {visibleUsers.length === 0 ? (
                  <p className="muted access-empty">{t('share.noSearchMatch')}</p>
                ) : (
                  visibleUsers.map((u) => (
                    <div key={u.id} className="access-row">
                      <span className="access-row__info">
                        <span className="access-row__name">{u.email}</span>
                      </span>
                      <select
                        className="access-row__select"
                        value={access.get(u.id) ?? ''}
                        disabled={saving}
                        onChange={(e) => setUserAccess(u.id, e.target.value as '' | ShareAccess)}
                      >
                        <option value="">{t('share.accessNone')}</option>
                        <option value="view">{t('share.accessView')}</option>
                        <option value="edit">{t('share.accessEdit')}</option>
                      </select>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>

        <footer className="modal__footer">
          <span className={dirty ? 'access-dirty' : 'access-dirty muted'}>
            {dirty ? t('share.unsavedChanges') : t('share.allSaved')}
          </span>
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={saving}>
            {t('share.close')}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void handleSave()}
            disabled={saving || loading || !dirty}
          >
            {saving ? t('share.saving') : t('share.save')}
          </button>
        </footer>
      </div>
    </div>
  );
}
