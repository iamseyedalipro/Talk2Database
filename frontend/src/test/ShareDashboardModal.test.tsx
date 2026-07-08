import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DashboardShareItem, UserDirectoryEntry } from '../api/types';

// Mock the API module the component imports.
vi.mock('../api/endpoints', () => ({
  listUserDirectory: vi.fn(),
  getDashboardShares: vi.fn(),
  setDashboardShares: vi.fn(),
  updateDashboard: vi.fn(),
}));

import {
  getDashboardShares,
  listUserDirectory,
  setDashboardShares,
  updateDashboard,
} from '../api/endpoints';
import ShareDashboardModal from '../components/dashboard/ShareDashboardModal';

const DIRECTORY: UserDirectoryEntry[] = [
  { id: 2, email: 'bob@x.com' },
  { id: 3, email: 'carol@x.com' },
];
const SHARES: DashboardShareItem[] = [{ user_id: 2, email: 'bob@x.com', access_level: 'view' }];

beforeEach(() => {
  vi.mocked(listUserDirectory).mockResolvedValue(DIRECTORY);
  vi.mocked(getDashboardShares).mockResolvedValue(SHARES);
  vi.mocked(setDashboardShares).mockImplementation((_id, shares) =>
    Promise.resolve(
      shares.map((s) => ({
        user_id: s.user_id,
        email: s.user_id === 2 ? 'bob@x.com' : 'carol@x.com',
        access_level: s.access_level,
      })),
    ),
  );
  vi.mocked(updateDashboard).mockResolvedValue({ shared: true } as never);
});

function renderModal() {
  return render(
    <ShareDashboardModal
      dashboardId={7}
      shared={false}
      onSharedChange={vi.fn()}
      onClose={vi.fn()}
    />,
  );
}

describe('ShareDashboardModal', () => {
  it('loads current grants and preselects each user access level', async () => {
    renderModal();
    const bobRow = (await screen.findByText('bob@x.com')).closest('.access-row') as HTMLElement;
    const carolRow = (await screen.findByText('carol@x.com')).closest('.access-row') as HTMLElement;
    // Bob already has view; Carol has no access.
    expect(bobRow.querySelector('select')).toHaveValue('view');
    expect(carolRow.querySelector('select')).toHaveValue('');
    expect(screen.getByText('All changes saved')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save sharing' })).toBeDisabled();
  });

  it('grants a new user edit access and saves the full set', async () => {
    const u = userEvent.setup();
    renderModal();
    const carolRow = (await screen.findByText('carol@x.com')).closest('.access-row') as HTMLElement;

    await u.selectOptions(carolRow.querySelector('select') as HTMLSelectElement, 'edit');
    const save = screen.getByRole('button', { name: 'Save sharing' });
    expect(save).toBeEnabled();

    await u.click(save);
    await waitFor(() => expect(setDashboardShares).toHaveBeenCalled());
    const sent = vi.mocked(setDashboardShares).mock.calls[0]![1];
    expect(new Set(sent.map((s) => `${s.user_id}:${s.access_level}`))).toEqual(
      new Set(['2:view', '3:edit']),
    );
    await screen.findByText('All changes saved');
  });

  it('toggles the global "share with everyone" flag', async () => {
    const u = userEvent.setup();
    renderModal();
    await screen.findByText('bob@x.com');
    await u.click(screen.getByRole('checkbox'));
    await waitFor(() => expect(updateDashboard).toHaveBeenCalledWith(7, { shared: true }));
  });
});
