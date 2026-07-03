import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import CodeMirror, { type EditorView, Prec, keymap, placeholder } from '@uiw/react-codemirror';
import { MariaSQL, MySQL, PostgreSQL, type SQLDialect, sql } from '@codemirror/lang-sql';
import { oneDark } from '@codemirror/theme-one-dark';
import {
  deleteDescription,
  execute,
  executeCsv,
  getGlossary,
  getSchema,
  listConnections,
  refreshSchema,
  upsertDescription,
} from '../api/endpoints';
import { triggerBlobDownload } from '../api/client';
import type {
  Connection,
  DataSourceType,
  DbSchema,
  ExecuteResponse,
  GlossaryData,
  SchemaTable,
} from '../api/types';
import MetricsPanel from '../components/MetricsPanel';
import ResultsView from '../components/ResultsView';
import SchemaTree from '../components/SchemaTree';
import { ErrorBanner } from '../components/ui';
import { errorMessage } from '../utils/format';
import { buildPreviewSql } from '../utils/sql';

const PREVIEW_LIMIT = 100;
const PLACEHOLDER = 'Write a read-only SELECT, then press Run (Ctrl/⌘ + Enter).';

/** CodeMirror SQL dialect for a data-source type (drives highlighting + autocomplete). */
function dialectFor(type: DataSourceType): SQLDialect {
  if (type === 'mysql') return MySQL;
  if (type === 'mariadb') return MariaSQL;
  return PostgreSQL;
}

/**
 * DBeaver-style workspace: pick a connection, browse its structure on the left,
 * and write your own read-only SQL on the right. Queries run through the same
 * validated, read-only `/execute` endpoint as the Ask flow.
 */
export default function BrowsePage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [connError, setConnError] = useState<string | null>(null);

  const [schema, setSchema] = useState<DbSchema | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [glossary, setGlossary] = useState<GlossaryData>({ descriptions: [], metrics: [] });

  const [sqlText, setSqlText] = useState('');
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [activeSql, setActiveSql] = useState<string | null>(null);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [csvBusy, setCsvBusy] = useState(false);

  const viewRef = useRef<EditorView | null>(null);
  // Live refs so the editor keymap always sees the latest handler and text
  // without forcing the extensions array to be rebuilt on every keystroke.
  const runRef = useRef<(text: string) => void>(() => undefined);
  const sqlTextRef = useRef(sqlText);
  sqlTextRef.current = sqlText;

  const connection = useMemo(
    () => connections.find((c) => c.id === connectionId) ?? null,
    [connections, connectionId],
  );
  const type: DataSourceType = connection?.type ?? 'postgres';

  // Load connections once; default to the first (mirrors AskPage).
  useEffect(() => {
    listConnections()
      .then((list) => {
        setConnections(list);
        const first = list[0];
        if (first) setConnectionId((prev) => prev ?? first.id);
      })
      .catch((err) => setConnError(errorMessage(err)));
  }, []);

  // (Re)load the schema whenever the selected connection changes.
  useEffect(() => {
    if (connectionId === null) return;
    let cancelled = false;
    setSchema(null);
    setSchemaError(null);
    setSchemaLoading(true);
    getSchema(connectionId)
      .then((data) => {
        if (!cancelled) setSchema(data);
      })
      .catch((err) => {
        if (!cancelled) setSchemaError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setSchemaLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [connectionId]);

  // Load the connection's glossary (descriptions + metrics) alongside the schema.
  const loadGlossary = (id: number) => {
    getGlossary(id)
      .then(setGlossary)
      .catch(() => setGlossary({ descriptions: [], metrics: [] }));
  };

  useEffect(() => {
    if (connectionId === null) return;
    setGlossary({ descriptions: [], metrics: [] });
    loadGlossary(connectionId);
  }, [connectionId]);

  const handleSaveDescription = async (
    tableName: string,
    columnName: string,
    description: string,
  ) => {
    if (connectionId === null) return;
    await upsertDescription(connectionId, {
      table_name: tableName,
      column_name: columnName,
      description,
    });
    loadGlossary(connectionId);
  };

  const handleDeleteDescription = async (id: number) => {
    if (connectionId === null) return;
    await deleteDescription(connectionId, id);
    loadGlossary(connectionId);
  };

  // Schema-aware autocomplete: { tableName: [col, col, …] }.
  const completionSchema = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const table of schema?.tables ?? []) {
      map[table.name] = table.columns.map((c) => c.name);
    }
    return map;
  }, [schema]);

  const runQuery = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || running || connectionId === null) return;
    setRunError(null);
    setRunning(true);
    // Preview queries carry their own LIMIT; free-form queries fall back to the
    // server-side row cap (query_max_rows).
    execute({ connection_id: connectionId, sql: trimmed })
      .then((res) => {
        setResult(res);
        setActiveSql(trimmed);
      })
      .catch((err) => setRunError(errorMessage(err)))
      .finally(() => setRunning(false));
  };
  runRef.current = runQuery;

  const insertAtCursor = (text: string) => {
    const view = viewRef.current;
    if (!view) {
      setSqlText((prev) => prev + text);
      return;
    }
    const { from, to } = view.state.selection.main;
    view.dispatch({
      changes: { from, to, insert: text },
      selection: { anchor: from + text.length },
    });
    view.focus();
  };

  const handlePreview = (table: SchemaTable) => {
    const previewSql = buildPreviewSql(type, table.schema, table.name, PREVIEW_LIMIT);
    setSqlText(previewSql);
    runQuery(previewSql);
  };

  const handleRefresh = () => {
    if (connectionId === null || refreshing) return;
    setSchemaError(null);
    setRefreshing(true);
    refreshSchema(connectionId)
      .then((data) => setSchema(data))
      .catch((err) => setSchemaError(errorMessage(err)))
      .finally(() => setRefreshing(false));
  };

  const handleDownloadCsv = async () => {
    if (!activeSql || connectionId === null) return;
    setRunError(null);
    setCsvBusy(true);
    try {
      const { blob, filename } = await executeCsv({ connection_id: connectionId, sql: activeSql });
      triggerBlobDownload(blob, filename);
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setCsvBusy(false);
    }
  };

  const extensions = useMemo(
    () => [
      sql({ dialect: dialectFor(type), schema: completionSchema, upperCaseKeywords: true }),
      placeholder(PLACEHOLDER),
      Prec.highest(
        keymap.of([
          {
            key: 'Mod-Enter',
            run: () => {
              runRef.current(sqlTextRef.current);
              return true;
            },
          },
        ]),
      ),
    ],
    [completionSchema, type],
  );

  if (connections.length === 0) {
    return (
      <div className="page">
        <section className="card">
          <h1 className="page__title">Browse &amp; query</h1>
          <ErrorBanner message={connError} />
          <p className="muted">
            You have no connections yet. <Link to="/connections">Add a connection</Link> to browse
            its tables and run queries.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="browse">
      <aside className="browse__sidebar card">
        <div className="browse__sidebar-head">
          <h2 className="browse__sidebar-title">Tables</h2>
          <button
            type="button"
            className="btn btn--secondary btn--small"
            onClick={handleRefresh}
            disabled={refreshing || schemaLoading || connectionId === null}
            title="Re-introspect the schema"
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
        <label className="ask-form__field browse__conn">
          Data source
          <select
            value={connectionId ?? ''}
            onChange={(e) => setConnectionId(Number(e.target.value))}
            aria-label="Data source"
          >
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.type})
              </option>
            ))}
          </select>
        </label>
        <ErrorBanner message={connError} />
        <ErrorBanner message={schemaError} />
        <SchemaTree
          tables={schema?.tables ?? []}
          loading={schemaLoading}
          type={type}
          onInsert={insertAtCursor}
          onPreview={handlePreview}
          descriptions={glossary.descriptions}
          onSaveDescription={handleSaveDescription}
          onDeleteDescription={handleDeleteDescription}
        />
        {connectionId !== null && (
          <MetricsPanel
            connectionId={connectionId}
            metrics={glossary.metrics}
            onChange={() => loadGlossary(connectionId)}
          />
        )}
      </aside>

      <section className="browse__main">
        <div className="card">
          <div className="browse__editor-head">
            <h1 className="page__title">SQL editor</h1>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => runQuery(sqlText)}
              disabled={running || !sqlText.trim() || connectionId === null}
            >
              {running ? 'Running…' : 'Run ▸'}
            </button>
          </div>
          <p className="muted">
            Write your own read-only <code>SELECT</code>. Only single read-only queries run.
          </p>

          <div className="browse__editor">
            <CodeMirror
              value={sqlText}
              onChange={setSqlText}
              onCreateEditor={(view) => {
                viewRef.current = view;
              }}
              extensions={extensions}
              theme={oneDark}
              height="240px"
              basicSetup={{ lineNumbers: true, foldGutter: false }}
            />
          </div>

          <ErrorBanner message={runError} />
        </div>

        {result && (
          <ResultsView result={result} onDownloadCsv={handleDownloadCsv} csvBusy={csvBusy} />
        )}
      </section>
    </div>
  );
}
