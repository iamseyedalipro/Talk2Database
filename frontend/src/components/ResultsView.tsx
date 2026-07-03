import { useState } from 'react';
import { summarizeResults } from '../api/endpoints';
import type { ExecuteResponse, ResultSummary } from '../api/types';
import { errorMessage } from '../utils/format';
import ResultsChart from './ResultsChart';
import ResultsTable from './ResultsTable';
import { ErrorBanner, Spinner } from './ui';

type View = 'table' | 'bar' | 'line';

interface Props {
  result: ExecuteResponse;
  /** Optional CSV export action; when provided a "Download CSV" button shows. */
  onDownloadCsv?: () => void;
  csvBusy?: boolean;
  /** The question that produced these results; sent for a better AI summary. */
  question?: string | null;
}

/** Combines the results table with a Table | Bar | Line chart toggle. */
export default function ResultsView({ result, onDownloadCsv, csvBusy, question }: Props) {
  const [view, setView] = useState<View>('table');
  const [summary, setSummary] = useState<ResultSummary | null>(null);
  const [summarizing, setSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const handleExplain = async () => {
    setSummaryError(null);
    setSummarizing(true);
    try {
      const res = await summarizeResults({
        question: question ?? null,
        columns: result.columns,
        rows: result.rows,
      });
      setSummary(res);
      if (res.chart_type === 'bar' || res.chart_type === 'line') setView(res.chart_type);
    } catch (err) {
      setSummaryError(errorMessage(err));
    } finally {
      setSummarizing(false);
    }
  };

  const hasRows = result.rows.length > 0;

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
        <div className="results-view__actions">
          {hasRows && (
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => void handleExplain()}
              disabled={summarizing}
            >
              {summarizing ? 'Explaining…' : 'Explain results'}
            </button>
          )}
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
      </div>

      {summarizing && <Spinner label="Summarizing results…" />}
      <ErrorBanner message={summaryError} />
      {summary && (
        <p className="result-summary" role="status">
          {summary.summary}
        </p>
      )}

      {view === 'table' ? (
        <ResultsTable result={result} />
      ) : (
        <ResultsChart
          result={result}
          kind={view}
          suggestedX={summary?.x_column}
          suggestedY={summary?.y_column}
        />
      )}
    </section>
  );
}
