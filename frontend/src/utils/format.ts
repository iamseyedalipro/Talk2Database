/** Small formatting helpers shared across pages. */

/** Render any cell value as a display string; null/undefined become an em dash. */
export function cell(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** Format an ISO timestamp into a readable local string. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

/** Truncate a string to `max` characters with an ellipsis. */
export function truncate(text: string | null | undefined, max = 80): string {
  if (!text) return '';
  const collapsed = text.replace(/\s+/g, ' ').trim();
  return collapsed.length > max ? `${collapsed.slice(0, max)}…` : collapsed;
}

/** Human-readable byte size. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

const COMPACT = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
});
const GROUPED = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
const PERCENT = new Intl.NumberFormat('en-US', {
  style: 'percent',
  maximumFractionDigits: 1,
});

/** Compact axis numbers: 950, 1.2K, 3.4M, 1.1B. */
export function compactNumber(value: number): string {
  return COMPACT.format(value);
}

/** Full-precision grouped number for tooltips: 1,234,567.89. */
export function fullNumber(value: number): string {
  return GROUPED.format(value);
}

/** A 0..1 ratio as a percentage (for 100%-stacked axes/tooltips). */
export function percent(value: number): string {
  return PERCENT.format(value);
}

/** Extract a user-facing message from an unknown thrown value. */
export function errorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'detail' in err) {
    const { detail } = err as { detail: unknown };
    if (typeof detail === 'string') return detail;
  }
  if (err instanceof Error) return err.message;
  return 'Something went wrong. Please try again.';
}
