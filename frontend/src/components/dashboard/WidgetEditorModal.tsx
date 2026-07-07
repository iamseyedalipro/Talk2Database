import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import CodeMirror from '@uiw/react-codemirror';
import { sql } from '@codemirror/lang-sql';
import { oneDark } from '@codemirror/theme-one-dark';
import { execute, listConnections, listSavedQueries } from '../../api/endpoints';
import type {
  Connection,
  ExecuteResponse,
  SavedQuery,
  WidgetItem,
  WidgetView,
  WidgetViz,
} from '../../api/types';
import { errorMessage } from '../../utils/format';
import { dialectFor } from '../../utils/sql';
import ResultsChart from '../ResultsChart';
import ResultsTable from '../ResultsTable';
import { ErrorBanner } from '../ui';

const VIEWS: WidgetView[] = ['table', 'bar', 'hbar', 'line', 'area', 'pie', 'scatter'];

export interface WidgetDraft {
  title: string;
  connection_id: number;
  sql: string;
  viz: WidgetViz;
}

interface Props {
  /** The widget being edited, or null when adding a new one. */
  widget: WidgetItem | null;
  onSave: (draft: WidgetDraft) => Promise<void>;
  onCancel: () => void;
}

/**
 * Create/edit a dashboard window: pick a connection, write SQL (or start from
 * a saved query), choose how to display it, and preview before saving.
 */
export default function WidgetEditorModal({ widget, onSave, onCancel }: Props) {
  const { t } = useTranslation('dashboards');
  const [connections, setConnections] = useState<Connection[]>([]);
  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([]);

  const [title, setTitle] = useState(widget?.title ?? '');
  const [connectionId, setConnectionId] = useState<number | null>(widget?.connection_id ?? null);
  const [sqlText, setSqlText] = useState(widget?.sql ?? '');
  const [view, setView] = useState<WidgetView>(widget?.viz.view ?? 'table');
  const [xColumn, setXColumn] = useState<string | null>(widget?.viz.x_column ?? null);
  const [yColumn, setYColumn] = useState<string | null>(widget?.viz.y_column ?? null);

  const [preview, setPreview] = useState<ExecuteResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listConnections()
      .then((list) => {
        setConnections(list);
        setConnectionId((prev) => prev ?? list[0]?.id ?? null);
      })
      .catch((err) => setError(errorMessage(err)));
    listSavedQueries()
      .then(setSavedQueries)
      .catch(() => setSavedQueries([]));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onCancel();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [busy, onCancel]);

  const connection = connections.find((c) => c.id === connectionId) ?? null;
  const extensions = useMemo(
    () => [sql({ dialect: dialectFor(connection?.type ?? 'postgres'), upperCaseKeywords: true })],
    [connection?.type],
  );

  const applySavedQuery = (id: number) => {
    const sq = savedQueries.find((q) => q.id === id);
    if (!sq) return;
    setSqlText(sq.generated_sql);
    if (sq.connection_id !== null) setConnectionId(sq.connection_id);
    if (!title.trim()) setTitle(sq.name);
  };

  const handlePreview = async () => {
    if (connectionId === null || !sqlText.trim()) return;
    setPreviewing(true);
    setError(null);
    try {
      const res = await execute({ connection_id: connectionId, sql: sqlText.trim(), max_rows: 50 });
      setPreview(res);
    } catch (err) {
      setPreview(null);
      setError(errorMessage(err));
    } finally {
      setPreviewing(false);
    }
  };

  const handleSave = async () => {
    if (!title.trim() || connectionId === null || !sqlText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onSave({
        title: title.trim(),
        connection_id: connectionId,
        sql: sqlText.trim(),
        viz: { view, x_column: xColumn, y_column: yColumn },
      });
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  const previewColumns = preview?.columns ?? [];

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={t('widgetEditor')}>
      <div className="modal modal--wide">
        <header className="modal__header">
          <h2>{widget ? t('editWidget') : t('addWidget')}</h2>
          <p className="modal__sub">{t('modalSub')}</p>
        </header>

        <div className="modal__body">
          <label className="field">
            <span>{t('titleLabel')}</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('titlePlaceholder')}
              maxLength={200}
              autoFocus
            />
          </label>

          <div className="widget-editor__row">
            <label className="field">
              <span>{t('dataSource')}</span>
              <select
                value={connectionId ?? ''}
                onChange={(e) => setConnectionId(Number(e.target.value))}
              >
                {connections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.type})
                  </option>
                ))}
              </select>
            </label>

            {savedQueries.length > 0 && (
              <label className="field">
                <span>{t('startFromSaved')}</span>
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) applySavedQuery(Number(e.target.value));
                  }}
                >
                  <option value="">{t('pickSaved')}</option>
                  {savedQueries.map((q) => (
                    <option key={q.id} value={q.id}>
                      {q.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <div className="field">
            <span>SQL</span>
            <div className="browse__editor widget-editor__sql">
              <CodeMirror
                value={sqlText}
                onChange={setSqlText}
                extensions={extensions}
                theme={oneDark}
                height="160px"
                basicSetup={{ lineNumbers: true, foldGutter: false }}
              />
            </div>
          </div>

          <div className="widget-editor__row widget-editor__row--end">
            <label className="field">
              <span>{t('displayAs')}</span>
              <select value={view} onChange={(e) => setView(e.target.value as WidgetView)}>
                {VIEWS.map((v) => (
                  <option key={v} value={v}>
                    {t(`views.${v}`)}
                  </option>
                ))}
              </select>
            </label>

            {view !== 'table' && (
              <>
                <label className="field">
                  <span>{t('xAxis')}</span>
                  <select value={xColumn ?? ''} onChange={(e) => setXColumn(e.target.value || null)}>
                    <option value="">{t('auto')}</option>
                    {previewColumns.map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>{t('yAxis')}</span>
                  <select value={yColumn ?? ''} onChange={(e) => setYColumn(e.target.value || null)}>
                    <option value="">{t('auto')}</option>
                    {previewColumns.map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}

            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => void handlePreview()}
              disabled={previewing || connectionId === null || !sqlText.trim()}
            >
              {previewing ? t('running') : t('preview')}
            </button>
          </div>

          {view !== 'table' && previewColumns.length === 0 && (
            <p className="muted">{t('previewHint')}</p>
          )}

          <ErrorBanner message={error} />

          {preview && (
            <div className="widget-editor__preview">
              {view === 'table' ? (
                <ResultsTable result={preview} />
              ) : (
                <ResultsChart
                  result={preview}
                  kind={view}
                  suggestedX={xColumn}
                  suggestedY={yColumn}
                  hideControls
                  height={220}
                />
              )}
            </div>
          )}
        </div>

        <footer className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            {t('cancel')}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void handleSave()}
            disabled={busy || !title.trim() || connectionId === null || !sqlText.trim()}
          >
            {busy ? t('saving') : t('saveWidget')}
          </button>
        </footer>
      </div>
    </div>
  );
}
