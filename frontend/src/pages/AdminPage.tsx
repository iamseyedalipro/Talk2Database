import AdminUsersSection from '../components/admin/AdminUsersSection';

/** Admin area: user management. Admin-guarded by the router. */
export default function AdminPage() {
  return (
    <div className="page">
      <h1 className="page__title">Administration</h1>
      <AdminUsersSection />
    </div>
  );
}
