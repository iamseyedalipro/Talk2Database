import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { summarizeResults } from '../api/endpoints';
import type { ExecuteResponse, ResultSummary, WidgetView, WidgetViz } from '../api/types';
import { errorMessage } from '../utils/format';
import { defaultViz, vizFromSummary } from '../utils/viz';
import ResultsChart from './ResultsChart';
import ResultsTable from './ResultsTable';
import { ErrorBanner, Spinner } from './ui';

const VIEWS: WidgetView[] = [
  'table',
  'bar',
  'hbar',
  'line',
  'area',
  'pie',
  'scatter',
  'radar',
  'combo',
];

interface Props {
  result: ExecuteResponse;
  /** Optional CSV export action; when provided a "Download CSV" button shows. */
  onDownloadCsv?: () => void;
  csvBusy?: boolean;
  /** The question that produced these results; sent for a better AI summary. */
  question?: string | null;
}

/** Combines the results table with a Table | Bar | Line … chart toggle. */
export default function ResultsView({ result, onDownloadCsv, csvBusy, question }: Props) {
  const { t } = useTranslation('results');
  const [viz, setViz] = useState<WidgetViz>(() => defaultViz());
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
      // Apply the AI-suggested chart config (type, axes, series, stacking).
      const suggested = vizFromSummary(res);
      if (suggested) setViz(suggested);
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
        <div className="chart-toggle" role="tablist" aria-label={t('resultView')}>
          {VIEWS.map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={viz.view === v}
              className={viz.view === v ? 'chart-toggle__btn is-active' : 'chart-toggle__btn'}
              onClick={() => setViz((prev) => ({ ...prev, view: v }))}
            >
              {t(`views.${v}`)}
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
              {summarizing ? t('explaining') : t('explainResults')}
            </button>
          )}
          {onDownloadCsv && (
            <button
              type="button"
              className="btn btn--secondary"
              onClick={onDownloadCsv}
              disabled={csvBusy}
            >
              {csvBusy ? t('preparing') : t('downloadCsv')}
            </button>
          )}
        </div>
      </div>

      {summarizing && <Spinner label={t('summarizing')} />}
      <ErrorBanner message={summaryError} />
      {summary && (
        <p className="result-summary" role="status">
          {summary.summary}
        </p>
      )}

      {viz.view === 'table' ? (
        <ResultsTable result={result} />
      ) : (
        <ResultsChart result={result} viz={viz} onVizChange={setViz} />
      )}
    </section>
  );
}
