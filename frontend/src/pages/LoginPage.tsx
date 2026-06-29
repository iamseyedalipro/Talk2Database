import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { bootstrap, bootstrapAvailable, login } from '../api/endpoints';
import { ErrorBanner, InfoBanner, Spinner } from '../components/ui';
import { useAuthStore } from '../store/auth';
import { errorMessage } from '../utils/format';

/**
 * Login screen. On mount it asks the backend whether first-run bootstrap is
 * available; if so it renders a "create the first admin" form instead of the
 * normal login form.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());

  const [checking, setChecking] = useState(true);
  const [bootstrapMode, setBootstrapMode] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    let active = true;
    bootstrapAvailable()
      .then((res) => {
        if (active) setBootstrapMode(res.available);
      })
      .catch(() => {
        // If the probe fails, fall back to the normal login form.
        if (active) setBootstrapMode(false);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = bootstrapMode
        ? await bootstrap({ email, password })
        : await login({ email, password });
      setAuth(res.access_token, res.user);
      navigate('/', { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  if (checking) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <Spinner label="Loading…" />
        </div>
      </div>
    );
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand__mark">⌘</span>
          <span className="brand__name">Talk2Database</span>
        </div>

        <h1>{bootstrapMode ? 'Create the first admin account' : 'Sign in'}</h1>
        <p className="muted">
          {bootstrapMode
            ? 'No accounts exist yet. This first account will be the administrator.'
            : 'Ask your database questions in plain language.'}
        </p>

        {bootstrapMode && (
          <InfoBanner>
            You are setting up Talk2Database for the first time. Choose strong credentials.
          </InfoBanner>
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
            <span>Password{bootstrapMode ? ' (min 8 characters)' : ''}</span>
            <input
              type="password"
              autoComplete={bootstrapMode ? 'new-password' : 'current-password'}
              required
              minLength={bootstrapMode ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
            {submitting
              ? 'Please wait…'
              : bootstrapMode
                ? 'Create admin account'
                : 'Sign in'}
          </button>
        </form>

        {!bootstrapMode && (
          <p className="muted auth-footnote">
            New users join via an invite link from an administrator.
          </p>
        )}
      </div>
    </div>
  );
}
