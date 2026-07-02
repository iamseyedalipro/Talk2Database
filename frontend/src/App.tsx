import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import RequireAuth from './components/RequireAuth';
import RequireAdmin from './components/RequireAdmin';
import { Spinner } from './components/ui';
import AdminPage from './pages/AdminPage';
import AnalysisPage from './pages/AnalysisPage';
import AskPage from './pages/AskPage';
import ConnectionsPage from './pages/ConnectionsPage';
import HistoryPage from './pages/HistoryPage';
import LoginPage from './pages/LoginPage';
import RegisterInvitePage from './pages/RegisterInvitePage';

// The browse page pulls in the CodeMirror editor; code-split it so that weight
// only loads when the user actually opens it.
const BrowsePage = lazy(() => import('./pages/BrowsePage'));

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterInvitePage />} />

      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<AskPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route
          path="/browse"
          element={
            <Suspense fallback={<Spinner label="Loading editor…" />}>
              <BrowsePage />
            </Suspense>
          }
        />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminPage />
            </RequireAdmin>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
