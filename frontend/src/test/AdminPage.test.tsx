import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock every endpoint the overview + users sections touch so mounting a tab
// never hits the network.
vi.mock('../api/endpoints', () => ({
  listUsers: vi.fn().mockResolvedValue([]),
  getUsageReport: vi.fn().mockResolvedValue({
    totals: {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      total_tokens: 0,
      call_count: 0,
    },
    by_user: [],
    by_model: [],
    by_provider: [],
    daily: [],
  }),
  listAudit: vi.fn().mockResolvedValue([]),
  getAskSettings: vi
    .fn()
    .mockResolvedValue({ analysis_mode: false, row_cap: 50, row_cap_min: 1, row_cap_max: 500 }),
  clarityStatus: vi.fn().mockResolvedValue({
    configured: false,
    requests_used_today: 0,
    daily_budget: 10,
    latest_data_date: null,
    days_stored: 0,
    next_run_at: null,
  }),
  listPrompts: vi.fn().mockResolvedValue([]),
  inviteUser: vi.fn(),
  deleteUser: vi.fn(),
}));

import AdminPage from '../pages/AdminPage';

const renderAt = (path = '/admin') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AdminPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AdminPage', () => {
  it('renders a tab bar with all admin sections and defaults to Overview', async () => {
    renderAt();

    const tablist = screen.getByRole('tablist');
    // All seven tabs are present.
    expect(within(tablist).getAllByRole('tab')).toHaveLength(7);
    expect(within(tablist).getByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(within(tablist).getByRole('tab', { name: 'Users' })).toBeInTheDocument();

    // Overview is selected by default and its panel content renders.
    expect(within(tablist).getByRole('tab', { name: 'Overview' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(await screen.findByText(/snapshot of your workspace/i)).toBeInTheDocument();
  });

  it('selects the tab named by the ?tab= query param', async () => {
    renderAt('/admin?tab=usage');

    const tablist = screen.getByRole('tablist');
    expect(within(tablist).getByRole('tab', { name: 'Token usage' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    // The token-usage section heading (not the tab) is shown in the panel.
    expect(await screen.findByRole('heading', { name: 'Token usage' })).toBeInTheDocument();
  });

  it('switches the visible section when a tab is clicked', async () => {
    const user = userEvent.setup();
    renderAt();

    await user.click(screen.getByRole('tab', { name: 'Users' }));

    // The Users section renders its invite form heading.
    expect(await screen.findByRole('heading', { name: 'Invite a user' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Users' })).toHaveAttribute('aria-selected', 'true');
  });
});
