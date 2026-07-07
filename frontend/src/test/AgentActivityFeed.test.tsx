import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AskActivityStep } from '../api/types';
import AgentActivityFeed from '../components/chat/AgentActivityFeed';

const steps: AskActivityStep[] = [
  { kind: 'status', text: 'Reading the database schema…' },
  { kind: 'tables_directory', count: 12 },
  { kind: 'tables_requested', tables: ['payments', 'users'] },
  {
    kind: 'query',
    sql: 'SELECT DISTINCT status FROM payments LIMIT 5',
    purpose: 'Check status values',
    result: {
      columns: ['status'],
      rows: [['successful'], ['failed']],
      row_count: 2,
      truncated: false,
    },
  },
  { kind: 'generating', attempt: 1, attempts: 3 },
];

describe('AgentActivityFeed', () => {
  it('renders each step with details', () => {
    render(<AgentActivityFeed steps={steps} pending />);

    expect(screen.getByText('Reading the database schema…')).toBeInTheDocument();
    expect(screen.getByText(/Scanned the table list \(12 tables\)/)).toBeInTheDocument();
    expect(screen.getByText(/payments, users/)).toBeInTheDocument();
    expect(screen.getByText('Check status values')).toBeInTheDocument();
    expect(screen.getByText('SELECT DISTINCT status FROM payments LIMIT 5')).toBeInTheDocument();
    expect(screen.getByText('successful')).toBeInTheDocument();
    expect(screen.getByText(/2 rows/)).toBeInTheDocument();
    expect(screen.getByText('Writing the SQL…')).toBeInTheDocument();
  });

  it('shows the cancelled note and keeps the steps', () => {
    render(<AgentActivityFeed steps={steps.slice(0, 2)} cancelled />);
    expect(screen.getByText('Stopped by you.')).toBeInTheDocument();
    expect(screen.getByText('Reading the database schema…')).toBeInTheDocument();
  });

  it('renders a query error', () => {
    render(
      <AgentActivityFeed
        steps={[
          {
            kind: 'query',
            sql: 'DELETE FROM payments',
            purpose: null,
            error: 'Rejected by the read-only guard',
          },
        ]}
      />,
    );
    expect(screen.getByText(/Rejected by the read-only guard/)).toBeInTheDocument();
  });

  it('renders nothing when idle and empty', () => {
    const { container } = render(<AgentActivityFeed steps={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
