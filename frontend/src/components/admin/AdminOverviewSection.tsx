import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../../api/client';
import {
  clarityStatus,
  getAskSettings,
  getUsageReport,
  listAudit,
  listPrompts,
  listUsers,
} from '../../api/endpoints';
import type {
  AskSettings,
  AuditItem,
  ClarityStatus,
  PromptTemplate,
  UsageReport,
  User,
} from '../../api/types';
import { errorMessage, formatDate, truncate } from '../../utils/format';
import { ErrorBanner, Spinner, StatusPill } from '../ui';

const numberFormat = new Intl.NumberFormat();

/** Human-friendly token count: 1.2M / 34.5K / 812. */
function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/** How many days of token usage the summary window covers. */
const USAGE_WINDOW_DAYS = 14;

interface OverviewData {
  users: User[] | null;
  usage: UsageReport | null;
  /** null = audit log disabled server-side (404); [] = enabled but empty. */
  audit: AuditItem[] | null;
  auditDisabled: boolean;
  ask: AskSettings | null;
  clarity: ClarityStatus | null;
  prompts: PromptTemplate[] | null;
}

/**
 * Admin landing tab: an at-a-glance summary that pulls together user counts,
 * recent token usage, recent audit activity, and configuration status from the
 * existing admin endpoints. Each summary card deep-links to its full tab.
 */
export default function AdminOverviewSection({
  onNavigate,
}: {
  onNavigate: (tabId: string) => void;
}) {
  const { t } = useTranslation('admin');
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    const from = new Date();
    from.setDate(from.getDate() - USAGE_WINDOW_DAYS);

    const [users, usage, audit, ask, clarity, prompts] = await Promise.allSettled([
      listUsers(),
      getUsageReport({ from: from.toISOString() }),
      listAudit({ limit: 5 }),
      getAskSettings(),
      clarityStatus(),
      listPrompts(),
    ]);

    // Audit returns 404 when the audit log is disabled — treat that as "hidden",
    // not an error, mirroring AdminAuditSection.
    const auditDisabled =
      audit.status === 'rejected' &&
      audit.reason instanceof ApiError &&
      audit.reason.status === 404;

    // Surface a single banner only if *everything* fell over; partial failures
    // just leave the affected tile blank so one bad call can't blank the page.
    const settled = [users, usage, audit, ask, clarity, prompts];
    const firstError = settled.find(
      (r): r is PromiseRejectedResult => r.status === 'rejected',
    );
    if (firstError && settled.every((r) => r.status === 'rejected')) {
      setError(errorMessage(firstError.reason));
    }

    const value = <T,>(r: PromiseSettledResult<T>): T | null =>
      r.status === 'fulfilled' ? r.value : null;

    setData({
      users: value(users),
      usage: value(usage),
      audit: auditDisabled ? null : value(audit),
      auditDisabled,
      ask: value(ask),
      clarity: value(clarity),
      prompts: value(prompts),
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <section className="card">
        <Spinner label={t('overview.loading')} />
      </section>
    );
  }

  const users = data?.users ?? [];
  const adminCount = users.filter((u) => u.role === 'admin').length;
  const activeCount = users.filter((u) => u.is_active).length;
  const lastLogin = users
    .map((u) => u.last_login_at)
    .filter((v): v is string => Boolean(v))
    .sort()
    .at(-1);

  const totals = data?.usage?.totals;
  const audit = data?.audit;
  const ask = data?.ask;
  const clarity = data?.clarity;
  const customizedPrompts = data?.prompts?.filter((p) => p.is_customized).length ?? 0;

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">{t('overview.title')}</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          {t('refresh')}
        </button>
      </div>
      <p className="muted">{t('overview.description')}</p>

      <ErrorBanner message={error} />

      {/* ------------------------------ Users ------------------------------ */}
      <OverviewCard
        title={t('overview.usersTitle')}
        onView={() => onNavigate('users')}
        viewLabel={t('overview.viewUsers')}
      >
        <dl className="status-grid">
          <Stat label={t('overview.totalUsers')} value={numberFormat.format(users.length)} />
          <Stat label={t('overview.admins')} value={numberFormat.format(adminCount)} />
          <Stat label={t('overview.activeUsers')} value={numberFormat.format(activeCount)} />
          <Stat label={t('overview.lastLogin')} value={lastLogin ? formatDate(lastLogin) : '—'} />
        </dl>
      </OverviewCard>

      {/* --------------------------- Token usage --------------------------- */}
      <OverviewCard
        title={t('overview.usageTitle', { days: USAGE_WINDOW_DAYS })}
        onView={() => onNavigate('usage')}
        viewLabel={t('overview.viewUsage')}
      >
        {totals ? (
          <dl className="status-grid">
            <Stat
              label={t('overview.totalTokens')}
              value={formatTokens(totals.total_tokens)}
              title={numberFormat.format(totals.total_tokens)}
            />
            <Stat
              label={t('overview.apiCalls')}
              value={numberFormat.format(totals.call_count)}
            />
          </dl>
        ) : (
          <p className="muted">{t('overview.usageEmpty')}</p>
        )}
      </OverviewCard>

      {/* --------------------------- Recent audit -------------------------- */}
      {!data?.auditDisabled && (
        <OverviewCard
          title={t('overview.auditTitle')}
          onView={() => onNavigate('audit')}
          viewLabel={t('overview.viewAudit')}
        >
          {audit && audit.length > 0 ? (
            <ul className="overview-activity">
              {audit.map((item) => (
                <li key={item.id}>
                  <span className="overview-activity__q" title={item.question}>
                    {truncate(item.question, 70)}
                  </span>
                  <span className="overview-activity__meta">
                    <StatusPill status={item.last_status} />
                    <span className="muted">{formatDate(item.created_at)}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t('overview.auditEmpty')}</p>
          )}
        </OverviewCard>
      )}

      {/* --------------------------- Config status ------------------------- */}
      <OverviewCard title={t('overview.configTitle')}>
        <div className="overview-config">
          <ConfigRow
            label={t('overview.askMode')}
            tab="askSettings"
            onNavigate={onNavigate}
            viewLabel={t('overview.configure')}
            pill={
              ask == null ? null : ask.analysis_mode ? (
                <span className="pill pill--ok">{t('overview.on')}</span>
              ) : (
                <span className="pill pill--neutral">{t('overview.off')}</span>
              )
            }
          />
          <ConfigRow
            label={t('overview.clarity')}
            tab="clarity"
            onNavigate={onNavigate}
            viewLabel={t('overview.configure')}
            pill={
              clarity == null ? null : clarity.configured ? (
                <span className="pill pill--ok">{t('overview.configured')}</span>
              ) : (
                <span className="pill pill--neutral">{t('overview.notConfigured')}</span>
              )
            }
          />
          <ConfigRow
            label={t('overview.prompts')}
            tab="prompts"
            onNavigate={onNavigate}
            viewLabel={t('overview.configure')}
            pill={
              customizedPrompts > 0 ? (
                <span className="pill pill--busy">
                  {t('overview.customizedCount', { count: customizedPrompts })}
                </span>
              ) : (
                <span className="pill pill--neutral">{t('overview.allDefault')}</span>
              )
            }
          />
        </div>
      </OverviewCard>
    </section>
  );
}

/** A stat tile inside a `.status-grid`. */
function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd title={title}>{value}</dd>
    </div>
  );
}

/** A titled block within the overview with an optional "view full tab" button. */
function OverviewCard({
  title,
  onView,
  viewLabel,
  children,
}: {
  title: string;
  onView?: () => void;
  viewLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overview-block">
      <div className="overview-block__head">
        <h3>{title}</h3>
        {onView && viewLabel ? (
          <button type="button" className="btn btn--ghost btn--small" onClick={onView}>
            {viewLabel}
          </button>
        ) : null}
      </div>
      {children}
    </div>
  );
}

/** One label + status pill + "configure" link row in the config-status block. */
function ConfigRow({
  label,
  pill,
  tab,
  onNavigate,
  viewLabel,
}: {
  label: string;
  pill: React.ReactNode;
  tab: string;
  onNavigate: (tabId: string) => void;
  viewLabel: string;
}) {
  return (
    <div className="overview-config__row">
      <span className="overview-config__label">{label}</span>
      <span className="overview-config__value">
        {pill}
        <button
          type="button"
          className="btn btn--ghost btn--small"
          onClick={() => onNavigate(tab)}
        >
          {viewLabel}
        </button>
      </span>
    </div>
  );
}
