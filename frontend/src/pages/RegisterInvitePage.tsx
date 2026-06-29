import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { register } from '../api/endpoints';
import { ErrorBanner } from '../components/ui';
import { useAuthStore } from '../store/auth';
import { errorMessage } from '../utils/format';

/**
 * Invite acceptance page. Reads `token` from the query string, collects email
 * and password, registers the account, and logs the user in.
 */
export default function RegisterInvitePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const setAuth = useAuthStore((s) => s.setAuth);

  const inviteToken = params.get('token') ?? '';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await register({ invite_token: inviteToken, email, password });
      setAuth(res.access_token, res.user);
      navigate('/', { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand__mark">⌘</span>
          <span className="brand__name">Talk2Database</span>
        </div>

        <h1>Accept your invitation</h1>
        <p className="muted">Create your account to start asking questions.</p>

        {!inviteToken && (
          <ErrorBanner message="This invite link is missing its token. Ask your administrator for a new one." />
        )}
        <ErrorBanner message={error} />

        <form className="form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Password (min 8 characters)</span>
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button
            type="submit"
            className="btn btn--primary btn--block"
            disabled={submitting || !inviteToken}
          >
            {submitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="muted auth-footnote">
          Already have an account?{' '}
          <button type="button" className="linklike" onClick={() => navigate('/login')}>
            Sign in
          </button>
        </p>
      </div>
    </div>
  );
}
