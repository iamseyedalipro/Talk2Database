import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Connection, User } from '../api/types';

// Mock the API module the component imports.
vi.mock('../api/endpoints', () => ({
  listUsers: vi.fn(),
  listConnections: vi.fn(),
  getUserConnectionAccess: vi.fn(),
  setUserConnectionAccess: vi.fn(),
}));

import {
  getUserConnectionAccess,
  listConnections,
  listUsers,
  setUserConnectionAccess,
} from '../api/endpoints';
import AdminConnectionAccessSection from '../components/admin/AdminConnectionAccessSection';

const conn = (id: number, name: string, ownerId: number): Connection => ({
  id,
  owner_id: ownerId,
  name,
  type: 'postgres',
  host: `${name}.db`,
  port: 5432,
  database: 'app',
  username: 'ro',
  options: {},
  created_at: '2026-01-01T00:00:00Z',
});

const user = (id: number, email: string, role: 'admin' | 'user'): User => ({
  id,
  email,
  role,
  is_active: true,
  language: 'en',
  created_at: '2026-01-01T00:00:00Z',
  last_login_at: null,
});

const USERS = [user(1, 'owner@x.com', 'user'), user(2, 'bob@x.com', 'user'), user(3, 'admin@x.com', 'admin')];
// conn 10 owned by user 1; conns 11/12 owned by user 1 too -> shareable to bob(2).
const CONNS = [conn(10, 'sales', 1), conn(11, 'billing', 1), conn(12, 'analytics', 1)];

beforeEach(() => {
  vi.mocked(listUsers).mockResolvedValue(USERS);
  vi.mocked(listConnections).mockResolvedValue(CONNS);
  vi.mocked(getUserConnectionAccess).mockResolvedValue({ connection_ids: [11] });
  vi.mocked(setUserConnectionAccess).mockImplementation((_id, ids) =>
    Promise.resolve({ connection_ids: ids }),
  );
});

async function selectBob() {
  const u = userEvent.setup();
  render(<AdminConnectionAccessSection />);
  await screen.findByRole('combobox');
  await u.selectOptions(screen.getByRole('combobox'), '2');
  await screen.findByText('Available connections');
  return u;
}

describe('AdminConnectionAccessSection', () => {
  it('loads grants, starts clean, and enables Save only after a change', async () => {
    const u = await selectBob();

    // Pre-checked grant loaded from the server (conn 11).
    expect(screen.getByText('1 of 3 granted')).toBeInTheDocument();
    expect(screen.getByText('All changes saved')).toBeInTheDocument();
    const save = screen.getByRole('button', { name: 'Save access' });
    expect(save).toBeDisabled();

    // Toggle a connection -> dirty + Save enabled.
    await u.click(screen.getByText('analytics'));
    expect(screen.getByText('● Unsaved changes')).toBeInTheDocument();
    expect(save).toBeEnabled();
    expect(screen.getByText('2 of 3 granted')).toBeInTheDocument();

    // Save persists and returns to a clean state.
    await u.click(save);
    await waitFor(() => expect(setUserConnectionAccess).toHaveBeenCalled());
    const savedIds = vi.mocked(setUserConnectionAccess).mock.calls[0]![1];
    expect(new Set(savedIds)).toEqual(new Set([11, 12]));
    await screen.findByText('All changes saved');
    expect(screen.getByRole('button', { name: 'Save access' })).toBeDisabled();
  });

  it('filters with the search box and bulk-selects only visible rows', async () => {
    const u = await selectBob();

    await u.type(screen.getByPlaceholderText('Search connections…'), 'analy');
    expect(screen.getByText('analytics')).toBeInTheDocument();
    expect(screen.queryByText('billing')).not.toBeInTheDocument();

    // "Select all" affects only the filtered row (analytics); billing stays as-is.
    await u.click(screen.getByRole('button', { name: 'Select all' }));
    expect(screen.getByText('2 of 3 granted')).toBeInTheDocument(); // 11 (billing) + 12 (analytics)
  });

  it('shows a read-only note for admin users', async () => {
    const u = userEvent.setup();
    render(<AdminConnectionAccessSection />);
    await screen.findByRole('combobox');
    await u.selectOptions(screen.getByRole('combobox'), '3');
    expect(await screen.findByText(/already has access to every connection/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save access' })).not.toBeInTheDocument();
  });

  it('groups and locks connections the selected user owns', async () => {
    const u = userEvent.setup();
    render(<AdminConnectionAccessSection />);
    await screen.findByRole('combobox');
    await u.selectOptions(screen.getByRole('combobox'), '1'); // owner sees all 3 as owned
    const ownedGroup = (await screen.findByText('Owned by this user')).parentElement as HTMLElement;
    expect(within(ownedGroup).getAllByText('owner')).toHaveLength(3);
  });
});
