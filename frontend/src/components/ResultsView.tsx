import { useState } from 'react';
import type { ExecuteResponse } from '../api/types';
import ResultsChart from './ResultsChart';
import ResultsTable from './ResultsTable';

type View = 'table' | 'bar' | 'line';

interface Props {
  result: ExecuteResponse;
  /** Optional CSV export action; when provided a "Download CSV" button shows. */
  onDownloadCsv?: () => void;
  csvBusy?: boolean;
}

/** Combines the results table with a Table | Bar | Line chart toggle. */
export default function ResultsView({ result, onDownloadCsv, csvBusy }: Props) {
  const [view, setView] = useState<View>('table');

  return (
    <section className="card results-view">
      <div className="results-view__toolbar">
        <div className="chart-toggle" role="tablist" aria-label="Result view">
          {(['table', 'bar', 'line'] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              className={view === v ? 'chart-toggle__btn is-active' : 'chart-toggle__btn'}
              onClick={() => setView(v)}
            >
              {v === 'table' ? 'Table' : v === 'bar' ? 'Bar' : 'Line'}
            </button>
          ))}
        </div>
        {onDownloadCsv && (
          <button
            type="button"
            className="btn btn--secondary"
            onClick={onDownloadCsv}
            disabled={csvBusy}
          >
            {csvBusy ? 'Preparing…' : 'Download CSV'}
          </button>
        )}
      </div>

      {view === 'table' ? (
        <ResultsTable result={result} />
      ) : (
        <ResultsChart result={result} kind={view} />
      )}
    </section>
  );
}
