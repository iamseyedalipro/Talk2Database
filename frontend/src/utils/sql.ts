/** Helpers for building safe SQL fragments in the browse / query editor.
 *
 * Identifier quoting is dialect-aware: Postgres uses double quotes, while
 * MySQL/MariaDB use backticks. Getting this wrong turns an identifier into a
 * string literal (or a syntax error) on the other engine.
 */

import type { DataSourceType } from '../api/types';

/** The identifier quote character for a data-source type. */
function quoteChar(type: DataSourceType): '"' | '`' {
  return type === 'mysql' || type === 'mariadb' ? '`' : '"';
}

/** Quote a SQL identifier for the given dialect, escaping any embedded quote. */
export function quoteIdent(type: DataSourceType, name: string): string {
  const q = quoteChar(type);
  return `${q}${name.split(q).join(q + q)}${q}`;
}

/**
 * Fully-qualified, quoted table reference. The default `public` schema (Postgres)
 * is left off for readability; MySQL's "schema" is the database itself, so it is
 * never qualified here.
 */
export function qualifiedTable(type: DataSourceType, schema: string, table: string): string {
  const qualify = type === 'postgres' && schema && schema !== 'public';
  return qualify
    ? `${quoteIdent(type, schema)}.${quoteIdent(type, table)}`
    : quoteIdent(type, table);
}

/** Build a read-only data-preview query for a table. */
export function buildPreviewSql(
  type: DataSourceType,
  schema: string,
  table: string,
  limit = 100,
): string {
  return `SELECT * FROM ${qualifiedTable(type, schema, table)} LIMIT ${limit};`;
}
