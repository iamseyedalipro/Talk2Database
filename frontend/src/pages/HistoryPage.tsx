import { useCallback, useEffect, useState } from 'react';
import { getHistory, listHistory, rerunHistory } from '../api/endpoints';
import type { ExecuteResponse, HistoryItem } from '../api/types';
import ResultsView from '../components/ResultsView';
import SaveQueryModal from '../components/SaveQueryModal';
import { ErrorBanner, Spinner, StatusPill } from '../components/ui';
import { errorMessage, formatDate, truncate } from '../utils/format';

/** A panel shown beneath the selected history row: full SQL + actions + results. */
interface DetailState {
  item: HistoryItem;
  editing: boolean;
  sql: string;
}

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [detail, setDetail] = useState<DetailState | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const data = await listHistory(100, 0);
      setItems(data);
    } catch (err) {
      setListError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openDetail = async (item: HistoryItem) => {
    setDetailError(null);
    setResult(null);
    setSaveNotice(null);
    // Fetch the full item to guarantee we have the latest SQL/explanation.
    try {
      const full = await getHistory(item.id);
      setDetail({ item: full, editing: false, sql: full.generated_sql });
    } catch {
      setDetail({ item, editing: false, sql: item.generated_sql });
    }
  };

  const closeDetail = () => {
    setDetail(null);
    setResult(null);
    setDetailError(null);
  };

  const handleRerun = async (sql?: string) => {
    if (!detail) return;
    setDetailError(null);
    setRunning(true);
    try {
      const res = await rerunHistory(detail.item.id, sql ? { sql } : {});
      setResult(res);
      // Refresh the list so the row's status/row_count reflect the rerun.
      void load();
    } catch (err) {
      setDetailError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="page">
      <section className="card">
        <div className="page__header">
          <h1 className="page__title">Query history</h1>
          <button type="button" className="btn btn--ghost" onClick={() => void load()}>
            Refresh
          </button>
        </div>

        <ErrorBanner message={listError} />

        {loading ? (
          <Spinner label="Loading history…" />
        ) : items.length === 0 ? (
          <p className="muted">No queries yet. Ask your first question on the Ask page.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table data-table--history">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>SQL</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Created</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td title={item.question}>{truncate(item.question, 60)}</td>
                    <td>
                      <code className="inline-sql">{truncate(item.generated_sql, 50)}</code>
                    </td>
                    <td>
                      <StatusPill status={item.last_status} />
                    </td>
                    <td>{item.row_count ?? '—'}</td>
                    <td>{formatDate(item.created_at)}</td>
                    <td className="row-actions">
                      <button
                        type="button"
                        className="btn btn--small"
                        onClick={() => void openDetail(item)}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {detail && (
        <section className="card">
          <div className="page__header">
            <h2 className="page__title">Query #{detail.item.id}</h2>
            <button type="button" className="btn btn--ghost" onClick={closeDetail}>
              Close
            </button>
          </div>

          <p className="detail-question">
            <strong>Question:</strong> {detail.item.question}
          </p>
          {detail.item.error_message && (
            <ErrorBanner message={detail.item.error_message} />
          )}

          {detail.editing ? (
            <textarea
              className="sql-editor"
              value={detail.sql}
              spellCheck={false}
              rows={8}
              aria-label="Editable SQL"
              onChange={(e) => setDetail({ ...detail, sql: e.target.value })}
            />
          ) : (
            <pre className="sql-box">
              <code>{detail.item.generated_sql}</code>
            </pre>
          )}

          <div className="detail-actions">
            {detail.editing ? (
              <>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={running || detail.sql.trim().length === 0}
                  onClick={() => void handleRerun(detail.sql)}
                >
                  {running ? 'Running…' : 'Run edited SQL'}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={running}
                  onClick={() =>
                    setDetail({ ...detail, editing: false, sql: detail.item.generated_sql })
                  }
                >
                  Cancel edit
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={running}
                  onClick={() => void handleRerun()}
                >
                  {running ? 'Running…' : 'Re-run'}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={running}
                  onClick={() => setDetail({ ...detail, editing: true })}
                >
                  Edit &amp; run
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={running}
                  onClick={() => setSaveOpen(true)}
                >
                  Save query
                </button>
                {saveNotice && <span className="muted">{saveNotice}</span>}
              </>
            )}
          </div>

          <ErrorBanner message={detailError} />

          {result && <ResultsView result={result} question={detail.item.question} />}
        </section>
      )}

      {saveOpen && detail && (
        <SaveQueryModal
          draft={{
            generated_sql: detail.item.generated_sql,
            question: detail.item.question,
            connection_id: detail.item.connection_id,
          }}
          onSaved={() => {
            setSaveOpen(false);
            setSaveNotice('Saved to your library.');
          }}
          onCancel={() => setSaveOpen(false)}
        />
      )}
    </div>
  );
}
