import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/auth';
import { useThemeStore } from '../store/theme';
import AppFooter from './AppFooter';
import ErrorBoundary from './ErrorBoundary';

/** App shell: top navigation + routed page content. */
export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggle);
  const navigate = useNavigate();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  // The mobile nav panel covers the page; close it whenever the route changes.
  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  const handleLogout = () => {
    clear();
    navigate('/login', { replace: true });
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'nav-link nav-link--active' : 'nav-link';

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <div className="brand">
            <span className="brand__mark">⌘</span>
            <span className="brand__name">Talk2Database</span>
          </div>
          <nav className={navOpen ? 'nav nav--open' : 'nav'} aria-label="Main">
            <NavLink to="/" end className={linkClass}>
              Ask
            </NavLink>
            <NavLink to="/analysis" className={linkClass}>
              Analysis
            </NavLink>
            <NavLink to="/browse" className={linkClass}>
              Browse
            </NavLink>
            <NavLink to="/dashboards" className={linkClass}>
              Dashboards
            </NavLink>
            <NavLink to="/connections" className={linkClass}>
              Connections
            </NavLink>
            <NavLink to="/history" className={linkClass}>
              History
            </NavLink>
            <NavLink to="/saved" className={linkClass}>
              Saved
            </NavLink>
            {user?.role === 'admin' && (
              <NavLink to="/admin" className={linkClass}>
                Admin
              </NavLink>
            )}
            <div className="nav__account">
              <span className="nav__account-email" title={user?.email}>
                {user?.email}
              </span>
              <button type="button" className="btn btn--ghost" onClick={handleLogout}>
                Logout
              </button>
            </div>
          </nav>
          <div className="nav-user">
            <button
              type="button"
              className="btn btn--ghost theme-toggle"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              aria-pressed={theme === 'dark'}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
            <span className="nav-user__email" title={user?.email}>
              {user?.email}
            </span>
            <button type="button" className="btn btn--ghost nav-user__logout" onClick={handleLogout}>
              Logout
            </button>
            <button
              type="button"
              className="btn btn--ghost nav-toggle"
              onClick={() => setNavOpen((open) => !open)}
              aria-expanded={navOpen}
              aria-label={navOpen ? 'Close menu' : 'Open menu'}
            >
              {navOpen ? '✕' : '☰'}
            </button>
          </div>
        </div>
      </header>
      <main className="app-main">
        {/* Keyed on the path so navigating to a new page clears a prior crash. */}
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <AppFooter />
    </div>
  );
}
