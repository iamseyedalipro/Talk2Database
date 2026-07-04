import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AuditItem } from '../api/types';

// Mock the API module the component imports.
vi.mock('../api/endpoints', () => ({
  listAudit: vi.fn(),
}));

import { listAudit } from '../api/endpoints';
import AdminAuditSection from '../components/admin/AdminAuditSection';

const item = (over: Partial<AuditItem>): AuditItem => ({
  id: 1,
  user_id: 1,
  user_email: 'user@x.com',
  connection_id: 1,
  question: 'How many orders?',
  generated_sql: 'SELECT count(*) FROM orders',
  provider: 'anthropic',
  model: 'claude',
  last_status: 'success',
  error_message: null,
  row_count: 1,
  executed_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});

beforeEach(() => {
  vi.mocked(listAudit).mockReset();
});

describe('AdminAuditSection', () => {
  it('renders a clarification row (null generated_sql) without crashing', async () => {
    // A clarification turn stores no SQL; the backend returns generated_sql: null.
    vi.mocked(listAudit).mockResolvedValue([
      item({ id: 1, question: 'ambiguous?', generated_sql: null, last_status: 'preview', row_count: null }),
      item({ id: 2 }),
    ]);

    render(<AdminAuditSection />);

    // Both rows render; the null-SQL row shows the placeholder instead of throwing.
    expect(await screen.findByText('ambiguous?')).toBeInTheDocument();
    expect(screen.getByText('clarification asked')).toBeInTheDocument();
    expect(screen.getByText(/SELECT count/)).toBeInTheDocument();
  });

  it('hides the section entirely when the audit feed is disabled (404)', async () => {
    const { ApiError } = await import('../api/client');
    vi.mocked(listAudit).mockRejectedValue(new ApiError(404, 'The audit feed is disabled.'));

    const { container } = render(<AdminAuditSection />);
    // Wait a tick for the effect to run and the disabled state to hide the section.
    await screen.findByText('Audit log').catch(() => null);
    // Once disabled it renders nothing.
    await vi.waitFor(() => expect(container.querySelector('section')).toBeNull());
  });
});
