import { useCallback, useEffect, useState } from 'react';
import { deleteUser, inviteUser, listUsers } from '../../api/endpoints';
import type { InviteResponse, Role, User } from '../../api/types';
import { useAuthStore } from '../../store/auth';
import { errorMessage, formatDate } from '../../utils/format';
import { ErrorBanner, InfoBanner, Spinner } from '../ui';

/** Users table with delete buttons and an invite form. */
export default function AdminUsersSection() {
  const currentUser = useAuthStore((s) => s.user);

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<Role>('user');
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [invite, setInvite] = useState<InviteResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      setUsers(await listUsers());
    } catch (err) {
      setListError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteError(null);
    setInvite(null);
    setCopied(false);
    setInviting(true);
    try {
      const res = await inviteUser({ email: inviteEmail.trim(), role: inviteRole });
      setInvite(res);
      setInviteEmail('');
      setInviteRole('user');
    } catch (err) {
      setInviteError(errorMessage(err));
    } finally {
      setInviting(false);
    }
  };

  const handleDelete = async (user: User) => {
    setRowError(null);
    if (!window.confirm(`Delete ${user.email}? This cannot be undone.`)) return;
    setDeletingId(user.id);
    try {
      await deleteUser(user.id);
      await load();
    } catch (err) {
      setRowError(errorMessage(err));
    } finally {
      setDeletingId(null);
    }
  };

  const copyAcceptUrl = async () => {
    if (!invite) return;
    try {
      await navigator.clipboard.writeText(invite.accept_url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">Users</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      <ErrorBanner message={listError} />
      <ErrorBanner message={rowError} />

      {loading ? (
        <Spinner label="Loading users…" />
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Active</th>
                <th>Created</th>
                <th>Last login</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.email}</td>
                  <td>
                    <span className={`pill pill--${user.role === 'admin' ? 'busy' : 'neutral'}`}>
                      {user.role}
                    </span>
                  </td>
                  <td>{user.is_active ? 'yes' : 'no'}</td>
                  <td>{formatDate(user.created_at)}</td>
                  <td>{formatDate(user.last_login_at)}</td>
                  <td className="row-actions">
                    <button
                      type="button"
                      className="btn btn--small btn--danger"
                      disabled={deletingId === user.id || user.id === currentUser?.id}
                      title={
                        user.id === currentUser?.id ? 'You cannot delete your own account' : 'Delete user'
                      }
                      onClick={() => void handleDelete(user)}
                    >
                      {deletingId === user.id ? '…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="subsection">
        <h3>Invite a user</h3>
        <form className="invite-form" onSubmit={handleInvite}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Role</span>
            <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Role)}>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button type="submit" className="btn btn--primary" disabled={inviting}>
            {inviting ? 'Creating…' : 'Create invite'}
          </button>
        </form>

        <ErrorBanner message={inviteError} />

        {invite && (
          <InfoBanner>
            <div className="invite-result">
              <p>
                Invite created for <strong>{invite.email}</strong> ({invite.role}). Share this link
                so they can register — it expires {formatDate(invite.expires_at)}.
              </p>
              <div className="invite-result__url">
                <input type="text" readOnly value={invite.accept_url} onFocus={(e) => e.target.select()} />
                <button type="button" className="btn btn--secondary" onClick={() => void copyAcceptUrl()}>
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          </InfoBanner>
        )}
      </div>
    </section>
  );
}
