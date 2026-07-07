import { useTranslation } from 'react-i18next';
import AdminAskSettingsSection from '../components/admin/AdminAskSettingsSection';
import AdminAuditSection from '../components/admin/AdminAuditSection';
import AdminClaritySection from '../components/admin/AdminClaritySection';
import AdminConnectionAccessSection from '../components/admin/AdminConnectionAccessSection';
import AdminPromptsSection from '../components/admin/AdminPromptsSection';
import AdminTokenUsageSection from '../components/admin/AdminTokenUsageSection';
import AdminUsersSection from '../components/admin/AdminUsersSection';

/**
 * Admin area: user management, connection access, token usage, Clarity
 * integration, AI prompts, and the audit log. Admin-guarded by the router.
 */
export default function AdminPage() {
  const { t } = useTranslation('admin');
  return (
    <div className="page">
      <h1 className="page__title">{t('title')}</h1>
      <AdminUsersSection />
      <AdminConnectionAccessSection />
      <AdminTokenUsageSection />
      <AdminAuditSection />
      <AdminAskSettingsSection />
      <AdminClaritySection />
      <AdminPromptsSection />
    </div>
  );
}
