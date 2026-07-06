import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import SaveQueryModal from '../components/SaveQueryModal';
import { createSavedQuery } from '../api/endpoints';

vi.mock('../api/endpoints', () => ({
  createSavedQuery: vi.fn(() => Promise.resolve({ id: 1 })),
}));

describe('SaveQueryModal', () => {
  it('saves the draft SQL under the entered name', async () => {
    const onSaved = vi.fn();
    render(
      <SaveQueryModal
        draft={{ generated_sql: 'SELECT 1', question: null, connection_id: 3 }}
        onSaved={onSaved}
        onCancel={vi.fn()}
      />,
    );

    // The draft SQL is shown so the user can confirm what they're bookmarking.
    expect(screen.getByText('SELECT 1')).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText(/Orders per day/i), 'My query');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(createSavedQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'My query',
        generated_sql: 'SELECT 1',
        connection_id: 3,
        shared: false,
      }),
    );
  });
});
