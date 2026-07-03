import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AskResponse } from '../api/types';
import ChatThread, { type ChatTurn } from '../components/chat/ChatThread';

const askBase: AskResponse = {
  history_id: 1,
  status: 'ok',
  generated_sql: 'SELECT SUM(amount) FROM payments',
  explanation: 'Sums all payments.',
  clarification_question: null,
  suggested_interpretations: [],
  invalid_identifiers: [],
  retry_count: 0,
  dialect: 'postgres',
  provider: 'anthropic',
  model: 'm',
  warnings: [],
};

const noop = () => {};

function renderThread(turns: ChatTurn[], onRun = vi.fn()) {
  render(
    <ChatThread
      turns={turns}
      connectionId={7}
      onRun={onRun}
      onPickInterpretation={noop}
      onDownloadCsv={noop}
      onSave={noop}
    />,
  );
  return onRun;
}

describe('ChatThread', () => {
  it('renders user bubbles and ok turns with SQL and a Run button', () => {
    const onRun = renderThread([
      { kind: 'user', text: 'total income?' },
      { kind: 'assistant', ask: askBase, question: 'total income?' },
    ]);
    expect(screen.getByText('total income?')).toBeInTheDocument();
    expect(screen.getByText('Sums all payments.')).toBeInTheDocument();
    expect(screen.getByText('SELECT SUM(amount) FROM payments')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Run'));
    expect(onRun).toHaveBeenCalledWith(1, 'SELECT SUM(amount) FROM payments');
  });

  it('renders a clarification card for needs_clarification turns', () => {
    renderThread([
      {
        kind: 'assistant',
        question: 'income?',
        ask: {
          ...askBase,
          status: 'needs_clarification',
          generated_sql: null,
          clarification_question: 'Did you mean payments?',
          suggested_interpretations: [{ label: 'Payments', description: 'Sum payments' }],
        },
      },
    ]);
    expect(screen.getByText('Did you mean payments?')).toBeInTheDocument();
    expect(screen.getByText('Payments')).toBeInTheDocument();
    expect(screen.queryByText('Run')).not.toBeInTheDocument();
  });

  it('shows invalid identifiers and keeps the SQL editable on verification_failed', () => {
    renderThread([
      {
        kind: 'assistant',
        question: 'income?',
        ask: {
          ...askBase,
          status: 'verification_failed',
          invalid_identifiers: ['income', 'income.total'],
        },
      },
    ]);
    expect(screen.getByText(/income, income\.total/)).toBeInTheDocument();
    expect(screen.getByText('SELECT SUM(amount) FROM payments')).toBeInTheDocument();
    expect(screen.getByText('Run')).toBeInTheDocument();
  });

  it('renders results and a save button when a turn has executed', () => {
    const onSave = vi.fn();
    render(
      <ChatThread
        turns={[
          {
            kind: 'assistant',
            ask: askBase,
            question: 'total income?',
            executedSql: askBase.generated_sql as string,
            result: {
              columns: [{ name: 'sum', type: 'numeric' }],
              rows: [[10]],
              row_count: 1,
              truncated: false,
              elapsed_ms: 5,
            },
          },
        ]}
        connectionId={7}
        onRun={noop}
        onPickInterpretation={noop}
        onDownloadCsv={noop}
        onSave={onSave}
      />,
    );
    expect(screen.getByText('1 row')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Save query'));
    expect(onSave).toHaveBeenCalledWith(0);
  });
});
