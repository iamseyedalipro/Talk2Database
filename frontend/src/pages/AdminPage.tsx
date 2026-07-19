import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import AdminAskSettingsSection from '../components/admin/AdminAskSettingsSection';
import AdminAuditSection from '../components/admin/AdminAuditSection';
import AdminConnectionAccessSection from '../components/admin/AdminConnectionAccessSection';
import AdminOverviewSection from '../components/admin/AdminOverviewSection';
import AdminPromptsSection from '../components/admin/AdminPromptsSection';
import AdminTokenUsageSection from '../components/admin/AdminTokenUsageSection';
import AdminUsersSection from '../components/admin/AdminUsersSection';
import { Tabs } from '../components/ui';

/** Ordered admin tabs. `overview` is the default landing tab. */
const TAB_IDS = [
  'overview',
  'users',
  'access',
  'usage',
  'audit',
  'askSettings',
  'prompts',
] as const;

type TabId = (typeof TAB_IDS)[number];

/**
 * Admin console: a tabbed shell over the individual admin sections. Only the
 * active tab's section is mounted, so each section fetches its data lazily when
 * first opened. The active tab is mirrored in the URL (`?tab=`) so refresh,
 * back/forward, and shared links all restore it.
 */
export default function AdminPage() {
  const { t } = useTranslation('admin');
  const [searchParams, setSearchParams] = useSearchParams();

  const param = searchParams.get('tab');
  const active: TabId = (TAB_IDS as readonly string[]).includes(param ?? '')
    ? (param as TabId)
    : 'overview';

  const navigate = useCallback(
    (id: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (id === 'overview') next.delete('tab');
          else next.set('tab', id);
          return next;
        },
        { replace: false },
      );
    },
    [setSearchParams],
  );

  const tabs = useMemo(
    () => TAB_IDS.map((id) => ({ id, label: t(`tabs.${id}`) })),
    [t],
  );

  return (
    <div className="page">
      <h1 className="page__title">{t('title')}</h1>

      <Tabs
        tabs={tabs}
        activeId={active}
        onChange={navigate}
        idPrefix="admin-tab"
        ariaLabel={t('title')}
      />

      <div
        role="tabpanel"
        id={`admin-tab-panel-${active}`}
        aria-labelledby={`admin-tab-${active}`}
      >
        {active === 'overview' && <AdminOverviewSection onNavigate={navigate} />}
        {active === 'users' && <AdminUsersSection />}
        {active === 'access' && <AdminConnectionAccessSection />}
        {active === 'usage' && <AdminTokenUsageSection />}
        {active === 'audit' && <AdminAuditSection />}
        {active === 'askSettings' && <AdminAskSettingsSection />}
        {active === 'prompts' && <AdminPromptsSection />}
      </div>
    </div>
  );
}
