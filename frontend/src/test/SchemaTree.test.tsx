import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import SchemaTree from '../components/SchemaTree';
import type { SchemaTable } from '../api/types';

const tables: SchemaTable[] = [
  {
    schema: 'public',
    name: 'orders',
    comment: null,
    columns: [
      { name: 'id', type: 'integer', nullable: false, comment: null },
      { name: 'customer_id', type: 'integer', nullable: false, comment: null },
    ],
    primary_key: ['id'],
    foreign_keys: [
      { columns: ['customer_id'], ref_schema: 'public', ref_table: 'customers', ref_columns: ['id'] },
    ],
  },
  {
    schema: 'public',
    name: 'customers',
    comment: null,
    columns: [{ name: 'id', type: 'integer', nullable: false, comment: null }],
    primary_key: ['id'],
    foreign_keys: [],
  },
];

describe('SchemaTree', () => {
  it('lists tables and inserts a quoted table name on click (postgres)', async () => {
    const onInsert = vi.fn();
    const onPreview = vi.fn();
    render(
      <SchemaTree
        tables={tables}
        loading={false}
        type="postgres"
        onInsert={onInsert}
        onPreview={onPreview}
      />,
    );

    expect(screen.getByText('orders')).toBeInTheDocument();
    expect(screen.getByText('customers')).toBeInTheDocument();

    await userEvent.click(screen.getByText('orders'));
    expect(onInsert).toHaveBeenCalledWith('"orders"');
  });

  it('quotes identifiers with backticks for mysql', async () => {
    const onInsert = vi.fn();
    render(
      <SchemaTree
        tables={tables}
        loading={false}
        type="mysql"
        onInsert={onInsert}
        onPreview={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByText('orders'));
    expect(onInsert).toHaveBeenCalledWith('`orders`');
  });

  it('expands a table to reveal columns with PK/FK badges and inserts a column', async () => {
    const onInsert = vi.fn();
    render(
      <SchemaTree
        tables={tables}
        loading={false}
        type="postgres"
        onInsert={onInsert}
        onPreview={vi.fn()}
      />,
    );

    // Columns are hidden until expanded.
    expect(screen.queryByText('customer_id')).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Expand orders'));

    expect(screen.getByText('customer_id')).toBeInTheDocument();
    expect(screen.getByText('PK')).toBeInTheDocument();
    expect(screen.getByText('FK')).toBeInTheDocument();

    await userEvent.click(screen.getByText('customer_id'));
    expect(onInsert).toHaveBeenCalledWith('"customer_id"');
  });

  it('fires onPreview for a table', async () => {
    const onPreview = vi.fn();
    render(
      <SchemaTree
        tables={tables}
        loading={false}
        type="postgres"
        onInsert={vi.fn()}
        onPreview={onPreview}
      />,
    );

    await userEvent.click(screen.getByLabelText('Preview rows of orders'));
    expect(onPreview).toHaveBeenCalledWith(tables[0]);
  });

  it('filters tables by name', async () => {
    render(
      <SchemaTree
        tables={tables}
        loading={false}
        type="postgres"
        onInsert={vi.fn()}
        onPreview={vi.fn()}
      />,
    );

    await userEvent.type(screen.getByLabelText('Filter tables'), 'cust');

    expect(screen.getByText('customers')).toBeInTheDocument();
    expect(screen.queryByText('orders')).not.toBeInTheDocument();
  });
});
