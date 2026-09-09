import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';
import ReactGridLayout, {
  useContainerWidth,
  verticalCompactor,
  type Layout,
} from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import {
  createWidget,
  deleteWidget,
  getDashboard,
  saveDashboardLayout,
  updateWidget,
} from '../api/endpoints';
import type { DashboardDetail, WidgetItem } from '../api/types';
import ShareDashboardModal from '../components/dashboard/ShareDashboardModal';
import WidgetCard from '../components/dashboard/WidgetCard';
import WidgetEditorModal, { type WidgetDraft } from '../components/dashboard/WidgetEditorModal';
import { ErrorBanner, Spinner } from '../components/ui';
import { useAuthStore } from '../store/auth';
import { errorMessage } from '../utils/format';

const GRID_COLS = 12;
const ROW_HEIGHT = 60;

/** Track a max-width media query (dashboards stack vertically on phones). */
function useIsNarrow(breakpoint = 900): boolean {
  const [narrow, setNarrow] = useState(
    () => window.matchMedia(`(max-width: ${breakpoint}px)`).matches,
  );
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const onChange = (e: MediaQueryListEvent) => setNarrow(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [breakpoint]);
  return narrow;
}

/**
 * One dashboard: a drag-and-resize grid of SQL widgets (view mode by default,
 * edit mode for the owner). All widgets load on open; refresh is manual.
 */
export default function DashboardPage() {
  const { t } = useTranslation('dashboards');
  const { id } = useParams();
  const dashboardId = Number(id);
  const user = useAuthStore((s) => s.user);

  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editorWidget, setEditorWidget] = useState<WidgetItem | null | 'new'>(null);
  const [sharing, setSharing] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  const isNarrow = useIsNarrow();
  const { width, containerRef, mounted } = useContainerWidth();

  useEffect(() => {
    setLoading(true);
    getDashboard(dashboardId)
      .then(setDashboard)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, [dashboardId]);

  // The owner and edit-grantees can edit; admins can still moderate shared ones.
  const canEdit =
    dashboard !== null &&
    (dashboard.my_access === 'owner' ||
      dashboard.my_access === 'edit' ||
      (user?.role === 'admin' && dashboard.shared));
  // Only the owner (or an admin) manages who a dashboard is shared with.
  const canShare = dashboard !== null && (dashboard.is_owner || user?.role === 'admin');

  const layout: Layout = useMemo(
    () =>
      (dashboard?.widgets ?? []).map((w) => ({
        i: String(w.id),
        x: w.x,
        y: w.y,
        w: w.w,
        h: w.h,
        minW: 2,
        minH: 2,
      })),
    [dashboard?.widgets],
  );

  const persistLayout = (next: Layout) => {
    if (!dashboard || !canEdit) return;
    setDashboard({
      ...dashboard,
      widgets: dashboard.widgets.map((w) => {
        const item = next.find((l) => l.i === String(w.id));
        return item ? { ...w, x: item.x, y: item.y, w: item.w, h: item.h } : w;
      }),
    });
    saveDashboardLayout(
      dashboardId,
      next.map((l) => ({ widget_id: Number(l.i), x: l.x, y: l.y, w: l.w, h: l.h })),
    ).catch((err) => setError(errorMessage(err)));
  };

  const handleSaveWidget = async (draft: WidgetDraft) => {
    if (!dashboard) return;
    if (editorWidget === 'new') {
      const bottom = dashboard.widgets.reduce((max, w) => Math.max(max, w.y + w.h), 0);
      const created = await createWidget(dashboardId, { ...draft, x: 0, y: bottom, w: 6, h: 5 });
      setDashboard({ ...dashboard, widgets: [...dashboard.widgets, created] });
    } else if (editorWidget) {
      const updated = await updateWidget(dashboardId, editorWidget.id, draft);
      setDashboard({
        ...dashboard,
        widgets: dashboard.widgets.map((w) => (w.id === updated.id ? updated : w)),
      });
    }
    setEditorWidget(null);
  };

  const handleDeleteWidget = async (widget: WidgetItem) => {
    if (!dashboard) return;
    if (!window.confirm(t('deleteWidgetConfirm', { title: widget.title }))) return;
    try {
      await deleteWidget(dashboardId, widget.id);
      setDashboard({
        ...dashboard,
        widgets: dashboard.widgets.filter((w) => w.id !== widget.id),
      });
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  if (loading) {
    return (
      <div className="page">
        <Spinner label={t('loadingDashboard')} />
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="page">
        <section className="card">
          <ErrorBanner message={error ?? t('notFound')} />
          <p className="muted">
            <Link to="/dashboards">{t('backToDashboards')}</Link>
          </p>
        </section>
      </div>
    );
  }

  const sortedWidgets = [...dashboard.widgets].sort((a, b) => a.y - b.y || a.x - b.x);

  return (
    <div className="page dashboard-page">
      <section className="card">
        <div className="page__header">
          <div>
            <h1 className="page__title">{dashboard.name}</h1>
            <p className="muted">
              {dashboard.shared
                ? dashboard.is_owner
                  ? t('sharedDashboard')
                  : t('sharedDashboardBy', { owner: dashboard.owner_email ?? t('anotherUser') })
                : t('privateDashboard')}
              {dashboard.description ? ` — ${dashboard.description}` : ''}
            </p>
          </div>
          <div className="detail-actions">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setRefreshToken((n) => n + 1)}
              disabled={dashboard.widgets.length === 0}
            >
              ↻ {t('refreshAll')}
            </button>
            {canShare && (
              <button type="button" className="btn btn--secondary" onClick={() => setSharing(true)}>
                {t('shareButton')}
              </button>
            )}
            {canEdit && (
              <>
                <button
                  type="button"
                  className={editing ? 'btn btn--primary' : 'btn btn--secondary'}
                  onClick={() => setEditing((v) => !v)}
                >
                  {editing ? t('doneEditing') : t('editLayout')}
                </button>
                {editing && (
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => setEditorWidget('new')}
                  >
                    + {t('addWidget')}
                  </button>
                )}
              </>
            )}
          </div>
        </div>
        <ErrorBanner message={error} />
        {editing && !isNarrow && <p className="muted">{t('dragHint')}</p>}
      </section>

      {dashboard.widgets.length === 0 ? (
        <section className="card">
          <p className="muted">
            {t('empty')}
            {canEdit ? ` ${t('emptyEditHint')}` : ''}
          </p>
        </section>
      ) : isNarrow ? (
        /* Phones: a simple vertical stack — no drag, full width. */
        <div className="dashboard-stack">
          {sortedWidgets.map((widget) => (
            <div key={widget.id} className="dashboard-stack__item">
              <WidgetCard
                dashboardId={dashboardId}
                widget={widget}
                editing={editing && canEdit}
                draggable={false}
                refreshToken={refreshToken}
                onEdit={(w) => setEditorWidget(w)}
                onDelete={(w) => void handleDeleteWidget(w)}
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="dashboard-grid" ref={containerRef as React.RefObject<HTMLDivElement>}>
          {mounted && (
            <ReactGridLayout
              layout={layout}
              width={width}
              gridConfig={{ cols: GRID_COLS, rowHeight: ROW_HEIGHT, margin: [16, 16] }}
              dragConfig={{ enabled: editing && canEdit, handle: '.widget-card__head--drag' }}
              resizeConfig={{ enabled: editing && canEdit }}
              compactor={verticalCompactor}
              onDragStop={persistLayout}
              onResizeStop={persistLayout}
            >
              {dashboard.widgets.map((widget) => (
                <div key={String(widget.id)}>
                  <WidgetCard
                    dashboardId={dashboardId}
                    widget={widget}
                    editing={editing && canEdit}
                    refreshToken={refreshToken}
                    onEdit={(w) => setEditorWidget(w)}
                    onDelete={(w) => void handleDeleteWidget(w)}
                  />
                </div>
              ))}
            </ReactGridLayout>
          )}
        </div>
      )}

      {editorWidget !== null && (
        <WidgetEditorModal
          widget={editorWidget === 'new' ? null : editorWidget}
          onSave={handleSaveWidget}
          onCancel={() => setEditorWidget(null)}
        />
      )}

      {sharing && (
        <ShareDashboardModal
          dashboardId={dashboardId}
          shared={dashboard.shared}
          onSharedChange={(next) => setDashboard((d) => (d ? { ...d, shared: next } : d))}
          onClose={() => setSharing(false)}
        />
      )}
    </div>
  );
}
