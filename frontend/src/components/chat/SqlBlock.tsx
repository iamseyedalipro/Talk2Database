import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { explainPlan } from '../../api/endpoints';
import type { ExplainResult } from '../../api/types';
import { errorMessage } from '../../utils/format';

interface Props {
  sql: string;
  /** Connection the SQL runs against; needed for the cost estimate. */
  connectionId: number;
  /** Called with the (possibly edited) SQL when the user clicks Run. */
  onRun: (sql: string) => void;
  busy?: boolean;
  /** Hide the Run button once this turn already produced a result. */
  ran?: boolean;
}

/**
 * Inline SQL card inside a chat turn: view or edit the statement, check its
 * cost estimate, then run it. Review-before-execute is preserved — nothing
 * runs without an explicit click.
 */
export default function SqlBlock({ sql, connectionId, onRun, busy, ran }: Props) {
  const { t } = useTranslation('chat');
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(sql);

  const [estimate, setEstimate] = useState<ExplainResult | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  const handleExplain = async () => {
    setExplainError(null);
    setExplaining(true);
    try {
      setEstimate(await explainPlan({ connection_id: connectionId, sql: value }));
    } catch (err) {
      setExplainError(errorMessage(err));
    } finally {
      setExplaining(false);
    }
  };

  return (
    <div className="sql-block">
      {editing ? (
        <textarea
          className="sql-editor"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          spellCheck={false}
          rows={8}
          aria-label={t('editableSql')}
        />
      ) : (
        <pre className="sql-box">
          <code>{value}</code>
        </pre>
      )}
      {(estimate || explainError) && (
        <p className="explain-estimate" role="status">
          {explainError ? (
            <span className="explain-estimate__error">{explainError}</span>
          ) : (
            <>
              {t('estimatedCost')}{' '}
              <strong>
                {estimate?.cost != null ? estimate.cost.toLocaleString() : t('notAvailable')}
              </strong>
              {' · '}
              {t('estimatedRows')}{' '}
              <strong>
                {estimate?.rows != null ? estimate.rows.toLocaleString() : t('notAvailable')}
              </strong>
            </>
          )}
        </p>
      )}
      <div className="sql-block__actions">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => void handleExplain()}
          disabled={busy || explaining || value.trim().length === 0}
        >
          {explaining ? t('estimating') : t('showCostEstimate')}
        </button>
        {!editing && (
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setEditing(true)}
            disabled={busy}
          >
            {t('edit')}
          </button>
        )}
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => onRun(value)}
          disabled={busy || value.trim().length === 0}
        >
          {busy ? t('running') : ran ? t('runAgain') : t('run')}
        </button>
      </div>
    </div>
  );
}
