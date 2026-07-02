import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AskResponse } from '../api/types';
import ClarificationCard from '../components/chat/ClarificationCard';

const base: AskResponse = {
  history_id: 1,
  status: 'needs_clarification',
  generated_sql: null,
  explanation: null,
  clarification_question: 'There is no income table — did you mean payments?',
  suggested_interpretations: [
    { label: 'Total payments', description: 'What is the total of payments.amount for 2025?' },
    { label: 'Total invoices', description: 'What is the total of invoices.total for 2025?' },
  ],
  invalid_identifiers: [],
  retry_count: 0,
  dialect: 'postgres',
  provider: 'anthropic',
  model: 'm',
  warnings: [],
};

describe('ClarificationCard', () => {
  it('shows the clarifying question and one button per interpretation', () => {
    render(<ClarificationCard ask={base} onPick={() => {}} />);
    expect(
      screen.getByText('There is no income table — did you mean payments?'),
    ).toBeInTheDocument();
    expect(screen.getByText('Total payments')).toBeInTheDocument();
    expect(screen.getByText('Total invoices')).toBeInTheDocument();
  });

  it('sends the full interpretation question when an option is clicked', () => {
    const onPick = vi.fn();
    render(<ClarificationCard ask={base} onPick={onPick} />);
    fireEvent.click(screen.getByText('Total payments'));
    expect(onPick).toHaveBeenCalledWith('What is the total of payments.amount for 2025?');
  });

  it('renders the explanation for unanswerable questions', () => {
    const ask: AskResponse = {
      ...base,
      status: 'unanswerable',
      clarification_question: null,
      suggested_interpretations: [],
      explanation: 'This database has no financial data.',
    };
    render(<ClarificationCard ask={ask} onPick={() => {}} />);
    expect(screen.getByText('This database has no financial data.')).toBeInTheDocument();
  });
});
