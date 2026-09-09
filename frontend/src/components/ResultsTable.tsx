import { useTranslation } from 'react-i18next';
import type { ExecuteResponse } from '../api/types';
import { cell } from '../utils/format';

interface Props {
  result: ExecuteResponse;
}

/** Renders an execute/rerun result set as a scrollable table. */
export default function ResultsTable({ result }: Props) {
  const { t } = useTranslation('results');
  const { columns, rows, row_count, truncated, elapsed_ms } = result;

  return (
    <div className="results">
      <div className="results__meta">
        <span>{t('rows', { count: row_count })}</span>
        <span>·</span>
        <span>{t('elapsedMs', { value: elapsed_ms })}</span>
        {truncated && (
          <span className="results__truncated" title={t('truncatedTitle')}>
            · {t('truncated')}
          </span>
        )}
      </div>

      {rows.length === 0 ? (
        <p className="muted">{t('noRows')}</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col.name} title={col.type}>
                    {col.name}
                    <span className="col-type">{col.type}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri}>
                  {columns.map((col, ci) => (
                    <td key={col.name}>{cell(row[ci])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
