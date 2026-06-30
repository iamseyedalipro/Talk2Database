/**
 * TypeScript interfaces mirroring the Talk2Database backend API contract.
 * Base path for all endpoints is `/api`.
 */

export type Role = 'admin' | 'user';

export interface User {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export interface BootstrapAvailable {
  available: boolean;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface BootstrapPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  invite_token: string;
  email: string;
  password: string;
}

export interface InvitePayload {
  email: string;
  role: Role;
}

export interface InviteResponse {
  invite_id: number;
  email: string;
  role: Role;
  expires_at: string;
  invite_token: string;
  accept_url: string;
}

/* ----------------------------- Connections ------------------------------- */

export type DataSourceType = 'postgres' | 'mysql' | 'mariadb';

export interface Connection {
  id: number;
  name: string;
  type: DataSourceType;
  host: string;
  port: number;
  database: string;
  username: string;
  options: Record<string, unknown>;
  created_at: string;
}

export interface ConnectionCreate {
  name: string;
  type: DataSourceType;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  options?: Record<string, unknown>;
}

export type ConnectionUpdate = Partial<ConnectionCreate>;

export interface ConnectionTestResult {
  ok: boolean;
  message: string | null;
}

/* ----------------------------- Ask / generate ---------------------------- */

export interface AskPayload {
  connection_id: number;
  question: string;
}

export interface AskResponse {
  history_id: number;
  generated_sql: string;
  explanation: string | null;
  dialect: string;
  provider: string;
  model: string;
  warnings: string[];
}

/* -------------------------------- Execute -------------------------------- */

export interface ResultColumn {
  name: string;
  type: string;
}

export interface ExecutePayload {
  connection_id: number;
  sql: string;
  history_id?: number;
  max_rows?: number;
}

export interface ExecuteResponse {
  columns: ResultColumn[];
  /** Row values are untyped on the wire; render via String(). */
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

/* --------------------------- Schema (browser) ---------------------------- */

export interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
  comment: string | null;
}

export interface SchemaForeignKey {
  columns: string[];
  ref_schema: string;
  ref_table: string;
  ref_columns: string[];
}

export interface SchemaTable {
  schema: string;
  name: string;
  comment: string | null;
  columns: SchemaColumn[];
  primary_key: string[];
  foreign_keys: SchemaForeignKey[];
}

export interface DbSchema {
  tables: SchemaTable[];
}

/* -------------------------------- History -------------------------------- */

export type QueryStatus = 'preview' | 'success' | 'error';

export interface HistoryItem {
  id: number;
  connection_id: number | null;
  question: string;
  generated_sql: string;
  provider: string | null;
  model: string | null;
  last_status: QueryStatus;
  error_message: string | null;
  row_count: number | null;
  executed_at: string | null;
  rerun_of_id: number | null;
  created_at: string;
}

export interface RerunPayload {
  sql?: string;
  max_rows?: number;
}

/* ----------------------------- Saved queries ----------------------------- */

export interface SavedQuery {
  id: number;
  owner_id: number;
  owner_email: string | null;
  connection_id: number | null;
  name: string;
  question: string | null;
  generated_sql: string;
  shared: boolean;
  is_owner: boolean;
  created_at: string;
}

export interface SavedQueryCreate {
  name: string;
  generated_sql: string;
  connection_id?: number | null;
  question?: string | null;
  shared?: boolean;
}

export interface SavedQueryUpdate {
  name?: string;
  generated_sql?: string;
  connection_id?: number | null;
  question?: string | null;
  shared?: boolean;
}

export interface SavedQueryRunPayload {
  max_rows?: number;
}

/* ------------------------- Result summary (AI) --------------------------- */

export type ChartType = 'bar' | 'line' | 'table' | 'none';

export interface SummarizePayload {
  question?: string | null;
  columns: ResultColumn[];
  rows: unknown[][];
}

export interface ResultSummary {
  summary: string;
  chart_type: ChartType;
  x_column: string | null;
  y_column: string | null;
}

/* ----------------------------- EXPLAIN preview --------------------------- */

export interface ExplainPayload {
  connection_id: number;
  sql: string;
}

export interface ExplainResult {
  cost: number | null;
  rows: number | null;
}

/* --------------------------- Semantic glossary --------------------------- */

export interface GlossaryDescription {
  id: number;
  table_name: string;
  /** Empty string means the description applies to the table itself. */
  column_name: string;
  description: string;
}

export interface DescriptionUpsert {
  table_name: string;
  column_name?: string;
  description: string;
}

export interface Metric {
  id: number;
  name: string;
  definition: string;
  expression: string | null;
}

export interface MetricCreate {
  name: string;
  definition: string;
  expression?: string | null;
}

export type MetricUpdate = Partial<MetricCreate>;

export interface GlossaryData {
  descriptions: GlossaryDescription[];
  metrics: Metric[];
}

/* ------------------------------- Audit feed ------------------------------ */

export interface AuditItem {
  id: number;
  user_id: number;
  user_email: string | null;
  connection_id: number | null;
  question: string;
  generated_sql: string;
  provider: string | null;
  model: string | null;
  last_status: QueryStatus;
  error_message: string | null;
  row_count: number | null;
  executed_at: string | null;
  created_at: string;
}

export interface AuditQuery {
  user_id?: number;
  status?: QueryStatus;
  q?: string;
  limit?: number;
  offset?: number;
}

/* -------------------------------- System --------------------------------- */

export interface SystemStatus {
  provider: string;
  model: string;
  connection_count: number;
  supported_types: string[];
}
