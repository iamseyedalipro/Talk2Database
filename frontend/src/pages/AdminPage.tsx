import AdminAuditSection from '../components/admin/AdminAuditSection';
import AdminConnectionAccessSection from '../components/admin/AdminConnectionAccessSection';
import AdminUsersSection from '../components/admin/AdminUsersSection';

/** Admin area: user management + connection access + audit log. Admin-guarded by the router. */
export default function AdminPage() {
  return (
    <div className="page">
      <h1 className="page__title">Administration</h1>
      <AdminUsersSection />
      <AdminConnectionAccessSection />
      <AdminAuditSection />
    </div>
  );
}
