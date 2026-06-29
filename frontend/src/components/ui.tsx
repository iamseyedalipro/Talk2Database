import type { ReactNode } from 'react';

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
  const tone =
    status === 'success'
      ? 'ok'
      : status === 'error' || status === 'failed'
        ? 'bad'
        : status === 'running'
          ? 'busy'
          : 'neutral';
  return <span className={`pill pill--${tone}`}>{status}</span>;
}
