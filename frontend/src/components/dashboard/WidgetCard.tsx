import { useEffect, useRef, useState } from 'react';
import { runWidget } from '../../api/endpoints';
import type { ExecuteResponse, WidgetItem } from '../../api/types';
import { errorMessage } from '../../utils/format';
import ResultsChart from '../ResultsChart';
import ResultsTable from '../ResultsTable';
import { Spinner } from '../ui';

interface Props {
  dashboardId: number;
  widget: WidgetItem;
  editing: boolean;
  /** Bump to re-run the widget ("Refresh all"). */
  refreshToken: number;
  onEdit?: (widget: WidgetItem) => void;
  onDelete?: (widget: WidgetItem) => void;
}

/** Measure the rendered height of the widget body so charts fill the card. */
function useMeasuredHeight(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [height, setHeight] = useState(240);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height;
      if (h && h > 40) setHeight(Math.floor(h));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, height];
}

/**
 * One dashboard window: runs its SQL on mount and on refresh, and renders the
 * result as the configured table/chart. Errors (including "no access to this
 * data source" on shared dashboards) stay local to the card.
 */
export default function WidgetCard({
  dashboardId,
  widget,
  editing,
  refreshToken,
  onEdit,
  onDelete,
}: Props) {
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bodyRef, bodyHeight] = useMeasuredHeight();

  const load = () => {
    setLoading(true);
    setError(null);
    runWidget(dashboardId, widget.id)
      .then(setResult)
      .catch((err) => {
        setResult(null);
        setError(errorMessage(err));
      })
      .finally(() => setLoading(false));
  };

  // Run on mount, when the SQL/connection changes, and on "Refresh all".
  useEffect(load, [dashboardId, widget.id, widget.sql, widget.connection_id, refreshToken]);

  const view = widget.viz.view;

  return (
    <div className="widget-card card">
      <div className={editing ? 'widget-card__head widget-card__head--drag' : 'widget-card__head'}>
        <h3 className="widget-card__title" title={widget.title}>
          {widget.title}
        </h3>
        <div className="widget-card__actions">
          <button
            type="button"
            className="widget-card__btn"
            title="Refresh"
            aria-label={`Refresh ${widget.title}`}
            onClick={load}
            disabled={loading}
          >
            ↻
          </button>
          {editing && onEdit && (
            <button
              type="button"
              className="widget-card__btn"
              title="Edit widget"
              aria-label={`Edit ${widget.title}`}
              onClick={() => onEdit(widget)}
            >
              ✎
            </button>
          )}
          {editing && onDelete && (
            <button
              type="button"
              className="widget-card__btn widget-card__btn--danger"
              title="Delete widget"
              aria-label={`Delete ${widget.title}`}
              onClick={() => onDelete(widget)}
            >
              🗑
            </button>
          )}
        </div>
      </div>

      <div className="widget-card__body" ref={bodyRef}>
        {loading && <Spinner label="Running…" />}
        {!loading && error && <div className="banner banner--error widget-card__error">{error}</div>}
        {!loading && !error && result && (
          view === 'table' ? (
            <ResultsTable result={result} />
          ) : (
            <ResultsChart
              result={result}
              kind={view}
              suggestedX={widget.viz.x_column}
              suggestedY={widget.viz.y_column}
              hideControls
              height={Math.max(bodyHeight - 8, 120)}
            />
          )
        )}
      </div>
    </div>
  );
}
