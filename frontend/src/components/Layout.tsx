import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { updateMe } from '../api/endpoints';
import { SUPPORTED_LANGUAGES, type Language } from '../i18n';
import { useAuthStore } from '../store/auth';
import { useThemeStore } from '../store/theme';
import AppFooter from './AppFooter';
import ErrorBoundary from './ErrorBoundary';

const LANGUAGE_LABELS: Record<Language, string> = { en: 'EN', fa: 'فا' };

/** App shell: top navigation + routed page content. */
export default function Layout() {
  const { t, i18n } = useTranslation('nav');
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
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

  const handleLanguageChange = (language: Language) => {
    if (language === i18n.language) return;
    void i18n.changeLanguage(language);
    // Persist to the profile so the preference follows the account.
    updateMe({ language })
      .then(setUser)
      .catch(() => undefined);
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'nav-link nav-link--active' : 'nav-link';

  // A single dashboard (/dashboards/:id) is a drag-and-resize grid; let it use
  // the full page width instead of the 1100px reading column so widgets can be
  // arranged across the whole screen.
  const isDashboardDetail = /^\/dashboards\/[^/]+$/.test(location.pathname);

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
              {t('ask')}
            </NavLink>
            <NavLink to="/analysis" className={linkClass}>
              {t('analysis')}
            </NavLink>
            <NavLink to="/browse" className={linkClass}>
              {t('browse')}
            </NavLink>
            <NavLink to="/dashboards" className={linkClass}>
              {t('dashboards')}
            </NavLink>
            <NavLink to="/connections" className={linkClass}>
              {t('connections')}
            </NavLink>
            <NavLink to="/history" className={linkClass}>
              {t('history')}
            </NavLink>
            <NavLink to="/saved" className={linkClass}>
              {t('saved')}
            </NavLink>
            {user?.role === 'admin' && (
              <NavLink to="/admin" className={linkClass}>
                {t('admin')}
              </NavLink>
            )}
            <div className="nav__account">
              <span className="nav__account-email" title={user?.email}>
                {user?.email}
              </span>
              <button type="button" className="btn btn--ghost" onClick={handleLogout}>
                {t('logout')}
              </button>
            </div>
          </nav>
          <div className="nav-user">
            <div className="lang-switch" role="group" aria-label={t('language')}>
              {SUPPORTED_LANGUAGES.map((language) => (
                <button
                  key={language}
                  type="button"
                  className={
                    i18n.language === language
                      ? 'lang-switch__btn is-active'
                      : 'lang-switch__btn'
                  }
                  onClick={() => handleLanguageChange(language)}
                  aria-pressed={i18n.language === language}
                >
                  {LANGUAGE_LABELS[language]}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn btn--ghost theme-toggle"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? t('switchToLight') : t('switchToDark')}
              aria-pressed={theme === 'dark'}
              title={theme === 'dark' ? t('switchToLight') : t('switchToDark')}
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
            <span className="nav-user__email" title={user?.email}>
              {user?.email}
            </span>
            <button type="button" className="btn btn--ghost nav-user__logout" onClick={handleLogout}>
              {t('logout')}
            </button>
            <button
              type="button"
              className="btn btn--ghost nav-toggle"
              onClick={() => setNavOpen((open) => !open)}
              aria-expanded={navOpen}
              aria-label={navOpen ? t('closeMenu') : t('openMenu')}
            >
              {navOpen ? '✕' : '☰'}
            </button>
          </div>
        </div>
      </header>
      <main className={isDashboardDetail ? 'app-main app-main--wide' : 'app-main'}>
        {/* Keyed on the path so navigating to a new page clears a prior crash. */}
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <AppFooter />
    </div>
  );
}
