import type { KeyboardEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

/** Inline error banner that surfaces server `detail` messages. */
export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="banner banner--error" role="alert">
      {message}
    </div>
  );
}

/** Inline informational banner. */
export function InfoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="banner banner--info" role="status">
      {children}
    </div>
  );
}

/** Small inline loading indicator with optional label. */
export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner" role="status" aria-live="polite">
      <span className="spinner__dot" aria-hidden="true" />
      {label ? <span className="spinner__label">{label}</span> : null}
    </span>
  );
}

/** Status pill used in history/imports tables. */
export function StatusPill({ status }: { status: string }) {
  const { t } = useTranslation('ui');
  const tone =
    status === 'success'
      ? 'ok'
      : status === 'error' || status === 'failed'
        ? 'bad'
        : status === 'running'
          ? 'busy'
          : 'neutral';
  return <span className={`pill pill--${tone}`}>{t(`status.${status}`, { defaultValue: status })}</span>;
}

/** A single tab definition consumed by {@link Tabs}. */
export interface TabItem {
  id: string;
  label: ReactNode;
}

/**
 * Presentational horizontal tab bar (WAI-ARIA `tablist`). Active state and the
 * associated panel are owned by the caller — this only renders the buttons and
 * emits `onChange`. Left/right (and Home/End) arrows move between tabs.
 */
export function Tabs({
  tabs,
  activeId,
  onChange,
  idPrefix = 'tab',
  ariaLabel,
}: {
  tabs: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  /** Prefix for the generated tab/panel element ids (must be unique per tablist). */
  idPrefix?: string;
  ariaLabel?: string;
}) {
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const current = tabs.findIndex((tab) => tab.id === activeId);
    if (current === -1) return;
    let next = current;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (current + 1) % tabs.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (current - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    else return;
    e.preventDefault();
    const target = tabs[next];
    if (target) onChange(target.id);
  };

  return (
    <div className="tabs" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`${idPrefix}-${tab.id}`}
            aria-selected={active}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            className={active ? 'tab tab--active' : 'tab'}
            onClick={() => onChange(tab.id)}
            onKeyDown={onKeyDown}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
