import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ResultsTable from '../components/ResultsTable';
import type { ExecuteResponse } from '../api/types';

const result: ExecuteResponse = {
  columns: [
    { name: 'id', type: 'int' },
    { name: 'name', type: 'text' },
  ],
  rows: [
    [1, 'Ada'],
    [2, null],
  ],
  row_count: 2,
  truncated: false,
  elapsed_ms: 12,
};

describe('ResultsTable', () => {
  it('renders headers, row count, and cell values (null as em dash)', () => {
    render(<ResultsTable result={result} />);

    expect(screen.getByText('id')).toBeInTheDocument();
    expect(screen.getByText('name')).toBeInTheDocument();
    expect(screen.getByText('2 rows')).toBeInTheDocument();
    expect(screen.getByText('Ada')).toBeInTheDocument();
    // null is rendered as an em dash.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
