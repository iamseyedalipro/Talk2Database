import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { cloneElement, isValidElement } from 'react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { ChartKind, ExecuteResponse } from '../api/types';
import ResultsChart from '../components/ResultsChart';
import { normalizeViz } from '../utils/viz';

// jsdom does no layout, so ResponsiveContainer measures 0x0 and renders
// nothing; give the chart a fixed size instead.
vi.mock('recharts', async (importOriginal) => {
  const mod = await importOriginal<Record<string, unknown>>();
  return {
    ...mod,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div>{isValidElement(children) ? cloneElement(children, { width: 800, height: 400 } as object) : children}</div>
    ),
  };
});

// Recharts still instantiates ResizeObserver internally; jsdom lacks it.
beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

const result: ExecuteResponse = {
  columns: [
    { name: 'month', type: 'text' },
    { name: 'product', type: 'text' },
    { name: 'sales', type: 'int' },
    { name: 'cost', type: 'int' },
  ],
  rows: [
    ['Jan', 'A', 10, 4],
    ['Jan', 'B', 20, 6],
    ['Feb', 'A', 15, 5],
    ['Feb', 'B', 25, 7],
    ['Mar', 'A', 12, 3],
    ['Mar', 'B', 22, 8],
  ],
  row_count: 6,
  truncated: false,
  elapsed_ms: 1,
};

const KINDS: ChartKind[] = ['bar', 'hbar', 'line', 'area', 'pie', 'scatter', 'radar', 'combo'];

describe('ResultsChart', () => {
  it.each(KINDS)('renders a %s chart without crashing', (kind) => {
    const viz = normalizeViz({
      view: kind,
      // Scatter needs a numeric X.
      x_column: kind === 'scatter' ? 'sales' : 'month',
      y_columns: kind === 'scatter' ? ['cost'] : ['sales', 'cost'],
      combo_types: kind === 'combo' ? { cost: 'line' } : {},
      right_axis: kind === 'combo' ? ['cost'] : [],
    });
    const { container } = render(
      <ResultsChart result={result} viz={viz} onVizChange={() => {}} />,
    );
    expect(container.querySelector('.chart__canvas')).not.toBeNull();
  });

  it('renders multi-series controls and toggles a Y column', async () => {
    const onChange = vi.fn();
    const viz = normalizeViz({ view: 'bar', x_column: 'month', y_columns: ['sales'] });
    render(<ResultsChart result={result} viz={viz} onVizChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: 'cost' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ y_columns: ['sales', 'cost'] }),
    );
  });

  it('pivots into one series per category when Group by is set', () => {
    const viz = normalizeViz({
      view: 'line',
      x_column: 'month',
      y_columns: ['sales'],
      series_column: 'product',
    });
    render(<ResultsChart result={result} viz={viz} hideControls />);
    // Legend shows one entry per product series.
    expect(screen.getByText('A')).toBeInTheDocument();
    expect(screen.getByText('B')).toBeInTheDocument();
  });

  it('hides controls for dashboard widgets', () => {
    const viz = normalizeViz({ view: 'bar', x_column: 'month', y_columns: ['sales'] });
    const { container } = render(<ResultsChart result={result} viz={viz} hideControls />);
    expect(container.querySelector('.chart__controls')).toBeNull();
  });
});
