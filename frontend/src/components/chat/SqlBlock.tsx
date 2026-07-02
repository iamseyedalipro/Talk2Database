import { useState } from 'react';

interface Props {
  sql: string;
  /** Called with the (possibly edited) SQL when the user clicks Run. */
  onRun: (sql: string) => void;
  busy?: boolean;
  /** Hide the Run button once this turn already produced a result. */
  ran?: boolean;
}

/**
 * Inline SQL card inside a chat turn: view or edit the statement, then run it.
 * Review-before-execute is preserved — nothing runs without an explicit click.
 */
export default function SqlBlock({ sql, onRun, busy, ran }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(sql);

  return (
    <div className="sql-block">
      {editing ? (
        <textarea
          className="sql-editor"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          spellCheck={false}
          rows={8}
          aria-label="Editable SQL"
        />
      ) : (
        <pre className="sql-box">
          <code>{value}</code>
        </pre>
      )}
      <div className="sql-block__actions">
        {!editing && (
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setEditing(true)}
            disabled={busy}
          >
            Edit
          </button>
        )}
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => onRun(value)}
          disabled={busy || value.trim().length === 0}
        >
          {busy ? 'Running…' : ran ? 'Run again' : 'Run'}
        </button>
      </div>
    </div>
  );
}
