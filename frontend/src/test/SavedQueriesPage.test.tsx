import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Role, SavedQuery, User } from '../api/types';

vi.mock('../api/endpoints', () => ({
  listSavedQueries: vi.fn(),
  runSavedQuery: vi.fn(),
  updateSavedQuery: vi.fn(),
  deleteSavedQuery: vi.fn(),
}));

import { listSavedQueries, updateSavedQuery } from '../api/endpoints';
import SavedQueriesPage from '../pages/SavedQueriesPage';
import { useAuthStore } from '../store/auth';

const LONG_SQL =
  'SELECT customer_id, count(*) AS orders FROM orders WHERE created_at >= now() - interval 30 day GROUP BY customer_id';

const query = (over: Partial<SavedQuery> = {}): SavedQuery => ({
  id: 1,
  owner_id: 7,
  owner_email: 'me@x.com',
  connection_id: 3,
  name: 'Orders per customer',
  question: 'How many orders per customer?',
  generated_sql: LONG_SQL,
  shared: false,
  is_owner: true,
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});

const asUser = (role: Role) => {
  const user: User = {
    id: 7,
    email: 'me@x.com',
    role,
    is_active: true,
    language: 'en',
    created_at: '2026-01-01T00:00:00Z',
    last_login_at: null,
  };
  useAuthStore.setState({ token: 'tok', user });
};

beforeEach(() => {
  vi.mocked(listSavedQueries).mockReset();
  vi.mocked(updateSavedQuery).mockReset();
  asUser('user');
});

describe('SavedQueriesPage', () => {
  it('shows the full SQL of a saved query in the detail panel', async () => {
    vi.mocked(listSavedQueries).mockResolvedValue([query()]);

    render(<SavedQueriesPage />);

    // The table only has room for a truncated preview…
    expect(await screen.findByText(/SELECT customer_id, count/)).toBeInTheDocument();
    expect(screen.queryByText(LONG_SQL)).not.toBeInTheDocument();

    // …but "View" opens a panel with the complete statement.
    await userEvent.click(screen.getByRole('button', { name: 'View' }));
    expect(screen.getByText(LONG_SQL)).toBeInTheDocument();
  });

  it('lets the owner edit the stored SQL and saves only the changed fields', async () => {
    const updated = query({ generated_sql: 'SELECT 2' });
    vi.mocked(listSavedQueries).mockResolvedValueOnce([query()]).mockResolvedValue([updated]);
    vi.mocked(updateSavedQuery).mockResolvedValue(updated);

    render(<SavedQueriesPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));

    const editor = screen.getByLabelText('Saved query SQL');
    await userEvent.clear(editor);
    await userEvent.type(editor, 'SELECT 2');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(updateSavedQuery).toHaveBeenCalledWith(1, { generated_sql: 'SELECT 2' }),
    );
    // The panel drops back to read-only and shows the SQL that was stored.
    expect((await screen.findAllByText('SELECT 2')).length).toBeGreaterThan(0);
  });

  it("hides editing for someone else's shared query but still shows its SQL", async () => {
    vi.mocked(listSavedQueries).mockResolvedValue([
      query({ id: 2, owner_id: 9, owner_email: 'other@x.com', is_owner: false, shared: true }),
    ]);

    render(<SavedQueriesPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'View' }));

    expect(screen.getByText(LONG_SQL)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy SQL' })).toBeInTheDocument();
  });
});
