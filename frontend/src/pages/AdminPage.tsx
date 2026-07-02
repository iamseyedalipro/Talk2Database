import AdminClaritySection from '../components/admin/AdminClaritySection';
import AdminPromptsSection from '../components/admin/AdminPromptsSection';
import AdminUsersSection from '../components/admin/AdminUsersSection';

/** Admin area: user management, Clarity integration, AI prompts. Admin-guarded by the router. */
export default function AdminPage() {
  return (
    <div className="page">
      <h1 className="page__title">Administration</h1>
      <AdminUsersSection />
      <AdminClaritySection />
      <AdminPromptsSection />
    </div>
  );
}
