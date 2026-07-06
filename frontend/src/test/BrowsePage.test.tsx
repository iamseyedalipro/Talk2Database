import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { Connection } from '../api/types';
import BrowsePage from '../pages/BrowsePage';

const connection: Connection = {
  id: 1,
  owner_id: 1,
  name: 'shop',
  type: 'postgres',
  host: 'h',
  port: 5432,
  database: 'd',
  username: 'u',
  options: {},
  created_at: '2024-01-01T00:00:00Z',
};

vi.mock('../api/endpoints', () => ({
  listConnections: vi.fn(() => Promise.resolve([connection])),
  getSchema: vi.fn(() => Promise.resolve({ tables: [] })),
  refreshSchema: vi.fn(() => Promise.resolve({ tables: [] })),
  getGlossary: vi.fn(() => Promise.resolve({ descriptions: [], metrics: [] })),
  execute: vi.fn(),
  executeCsv: vi.fn(),
  createSavedQuery: vi.fn(),
  upsertDescription: vi.fn(),
  deleteDescription: vi.fn(),
  createMetric: vi.fn(),
  updateMetric: vi.fn(),
  deleteMetric: vi.fn(),
}));

describe('BrowsePage', () => {
  it('shows a Save query button that is disabled until SQL is entered', async () => {
    render(
      <MemoryRouter>
        <BrowsePage />
      </MemoryRouter>,
    );

    // Wait for the connection to load and the editor to render.
    const saveButton = await screen.findByRole('button', { name: 'Save query' });
    // No SQL yet, so saving is disabled and no modal is shown.
    expect(saveButton).toBeDisabled();
    expect(screen.queryByRole('dialog', { name: /save query/i })).not.toBeInTheDocument();
  });
});
