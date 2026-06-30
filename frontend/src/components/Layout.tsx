import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/auth';

/** App shell: top navigation + routed page content. */
export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

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
          <nav className="nav">
            <NavLink to="/" end className={linkClass}>
              Ask
            </NavLink>
            <NavLink to="/browse" className={linkClass}>
              Browse
            </NavLink>
            <NavLink to="/connections" className={linkClass}>
              Connections
            </NavLink>
            <NavLink to="/history" className={linkClass}>
              History
            </NavLink>
            {user?.role === 'admin' && (
              <NavLink to="/admin" className={linkClass}>
                Admin
              </NavLink>
            )}
          </nav>
          <div className="nav-user">
            <span className="nav-user__email" title={user?.email}>
              {user?.email}
            </span>
            <button type="button" className="btn btn--ghost" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
