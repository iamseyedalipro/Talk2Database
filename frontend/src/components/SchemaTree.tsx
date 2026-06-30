import { useMemo, useState } from 'react';
import type { DataSourceType, SchemaTable } from '../api/types';
import { quoteIdent, qualifiedTable } from '../utils/sql';
import { Spinner } from './ui';

interface Props {
  tables: SchemaTable[];
  loading: boolean;
  /** The selected connection's type — drives dialect-correct identifier quoting. */
  type: DataSourceType;
  /** Insert a SQL fragment (table/column identifier) into the editor. */
  onInsert: (text: string) => void;
  /** Run a data preview (SELECT * … LIMIT n) for the table. */
  onPreview: (table: SchemaTable) => void;
}

const tableKey = (t: SchemaTable) => `${t.schema}.${t.name}`;

/**
 * DBeaver-style schema sidebar: a filterable list of tables that expand to show
 * their columns (with type and PK/FK badges). Clicking a table or column name
 * inserts the identifier into the editor; the ▦ button previews the table's rows.
 */
export default function SchemaTree({ tables, loading, type, onInsert, onPreview }: Props) {
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return tables;
    return tables.filter((t) => t.name.toLowerCase().includes(needle));
  }, [tables, filter]);

  // Columns referenced by any foreign key, for the FK badge.
  const fkColumns = (table: SchemaTable) => new Set(table.foreign_keys.flatMap((fk) => fk.columns));

  return (
    <div className="schema-tree">
      <input
        className="schema-tree__filter"
        type="search"
        placeholder="Filter tables…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        aria-label="Filter tables"
      />

      {loading ? (
        <div className="schema-tree__status">
          <Spinner label="Loading schema…" />
        </div>
      ) : tables.length === 0 ? (
        <p className="schema-tree__status muted">No tables found. Import a database first.</p>
      ) : filtered.length === 0 ? (
        <p className="schema-tree__status muted">No tables match “{filter}”.</p>
      ) : (
        <ul className="schema-tree__list">
          {filtered.map((table) => {
            const key = tableKey(table);
            const isOpen = expanded.has(key);
            const pk = new Set(table.primary_key);
            const fks = fkColumns(table);
            return (
              <li key={key} className="schema-tree__table">
                <div className="schema-tree__row">
                  <button
                    type="button"
                    className="schema-tree__chevron"
                    onClick={() => toggle(key)}
                    aria-expanded={isOpen}
                    aria-label={isOpen ? `Collapse ${table.name}` : `Expand ${table.name}`}
                  >
                    {isOpen ? '▾' : '▸'}
                  </button>
                  <button
                    type="button"
                    className="schema-tree__name"
                    title={table.comment ?? `Insert ${table.name} into the editor`}
                    onClick={() => onInsert(qualifiedTable(type, table.schema, table.name))}
                  >
                    {table.name}
                  </button>
                  <button
                    type="button"
                    className="schema-tree__preview"
                    title={`Preview rows of ${table.name}`}
                    aria-label={`Preview rows of ${table.name}`}
                    onClick={() => onPreview(table)}
                  >
                    ▦
                  </button>
                </div>

                {isOpen && (
                  <ul className="schema-tree__cols">
                    {table.columns.map((col) => (
                      <li key={col.name} className="schema-tree__col">
                        <button
                          type="button"
                          className="schema-tree__col-name"
                          title={col.comment ?? `Insert ${col.name} into the editor`}
                          onClick={() => onInsert(quoteIdent(type, col.name))}
                        >
                          {col.name}
                        </button>
                        <span className="schema-tree__col-type">{col.type}</span>
                        {pk.has(col.name) && <span className="badge badge--pk">PK</span>}
                        {fks.has(col.name) && <span className="badge badge--fk">FK</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
