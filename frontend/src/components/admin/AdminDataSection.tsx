import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getImport,
  listImports,
  systemStatus,
  uploadImport,
} from '../../api/endpoints';
import type { ImportRun, SystemStatus } from '../../api/types';
import { errorMessage, formatBytes, formatDate } from '../../utils/format';
import { ErrorBanner, InfoBanner, Spinner, StatusPill } from '../ui';

const POLL_INTERVAL_MS = 2000;

/** System status, data import upload (manual mode), and recent import runs. */
export default function AdminDataSection() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [imports, setImports] = useState<ImportRun[]>([]);
  const [importsError, setImportsError] = useState<string | null>(null);

  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [activeRun, setActiveRun] = useState<ImportRun | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    setStatusError(null);
    try {
      setStatus(await systemStatus());
    } catch (err) {
      setStatusError(errorMessage(err));
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const loadImports = useCallback(async () => {
    setImportsError(null);
    try {
      setImports(await listImports());
    } catch (err) {
      setImportsError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    void loadImports();
  }, [loadStatus, loadImports]);

  // Clean up the poller on unmount.
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = useCallback(
    (runId: number) => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const run = await getImport(runId);
          setActiveRun(run);
          if (run.status !== 'running') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            void loadImports();
            void loadStatus();
          }
        } catch (err) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setUploadError(errorMessage(err));
        }
      }, POLL_INTERVAL_MS);
    },
    [loadImports, loadStatus],
  );

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploading(true);
    setActiveRun(null);
    try {
      const accepted = await uploadImport(file);
      setActiveRun({
        id: accepted.import_run_id,
        kind: 'manual',
        status: accepted.status,
        filename: file.name,
        bytes: file.size,
        message: null,
        started_at: new Date().toISOString(),
        finished_at: null,
      });
      startPolling(accepted.import_run_id);
      if (fileInputRef.current) fileInputRef.current.value = '';
      void loadImports();
    } catch (err) {
      setUploadError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">Data</h2>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => {
            void loadStatus();
            void loadImports();
          }}
        >
          Refresh
        </button>
      </div>

      <ErrorBanner message={statusError} />

      {statusLoading ? (
        <Spinner label="Loading status…" />
      ) : status ? (
        <>
          <dl className="status-grid">
            <div>
              <dt>Import mode</dt>
              <dd>{status.import_mode}</dd>
            </div>
            <div>
              <dt>AI provider</dt>
              <dd>
                {status.provider} · {status.model}
              </dd>
            </div>
            <div>
              <dt>Data source</dt>
              <dd>{status.userdata_connected ? 'connected' : 'not connected'}</dd>
            </div>
            <div>
              <dt>Tables in schema</dt>
              <dd>{status.schema_table_count}</dd>
            </div>
            <div>
              <dt>Schema version</dt>
              <dd>{status.schema_version ?? '—'}</dd>
            </div>
          </dl>

          {status.import_mode === 'manual' ? (
            <div className="subsection">
              <h3>Upload a database dump</h3>
              <p className="muted">
                Upload a <code>.sql</code> file or pg_dump backup. The import runs in the background.
              </p>
              <form className="upload-form" onSubmit={handleUpload}>
                <input ref={fileInputRef} type="file" accept=".sql,.dump,.gz,.tar" required />
                <button type="submit" className="btn btn--primary" disabled={uploading}>
                  {uploading ? 'Uploading…' : 'Upload & import'}
                </button>
              </form>
              <ErrorBanner message={uploadError} />

              {activeRun && (
                <InfoBanner>
                  <div className="run-progress">
                    <span>
                      Import #{activeRun.id} ({activeRun.filename ?? 'file'}):
                    </span>
                    <StatusPill status={activeRun.status} />
                    {activeRun.status === 'running' && <Spinner />}
                    {activeRun.message && <span className="muted">{activeRun.message}</span>}
                  </div>
                </InfoBanner>
              )}
            </div>
          ) : (
            <div className="subsection">
              <h3>Scheduled sync</h3>
              <p className="muted">
                This deployment refreshes data automatically on a schedule. Manual uploads are
                disabled.
              </p>
              {status.last_import ? (
                <div className="run-progress">
                  <span>Last sync:</span>
                  <StatusPill status={status.last_import.status} />
                  <span className="muted">
                    started {formatDate(status.last_import.started_at)}
                    {status.last_import.finished_at
                      ? ` · finished ${formatDate(status.last_import.finished_at)}`
                      : ''}
                  </span>
                </div>
              ) : (
                <p className="muted">No syncs recorded yet.</p>
              )}
            </div>
          )}
        </>
      ) : null}

      <div className="subsection">
        <h3>Recent imports</h3>
        <ErrorBanner message={importsError} />
        {imports.length === 0 ? (
          <p className="muted">No import runs yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Kind</th>
                  <th>Status</th>
                  <th>File</th>
                  <th>Size</th>
                  <th>Started</th>
                  <th>Finished</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {imports.map((run) => (
                  <tr key={run.id}>
                    <td>{run.id}</td>
                    <td>{run.kind}</td>
                    <td>
                      <StatusPill status={run.status} />
                    </td>
                    <td>{run.filename ?? '—'}</td>
                    <td>{formatBytes(run.bytes)}</td>
                    <td>{formatDate(run.started_at)}</td>
                    <td>{formatDate(run.finished_at)}</td>
                    <td className="msg-cell" title={run.message ?? ''}>
                      {run.message ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
