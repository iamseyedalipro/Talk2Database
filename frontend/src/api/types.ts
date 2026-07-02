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

/* -------------------------------- System --------------------------------- */

export interface SystemStatus {
  provider: string;
  model: string;
  connection_count: number;
  supported_types: string[];
}

/* ------------------------------- Analysis -------------------------------- */

export interface AnalysisPayload {
  question: string;
  connection_ids: number[];
  include_clarity: boolean;
}

export interface AnalysisStep {
  connection_id: number | null;
  connection_name: string | null;
  purpose: string | null;
  sql: string;
  row_count: number | null;
  error: string | null;
}

export interface AnalysisResponse {
  answer: string;
  steps: AnalysisStep[];
  provider: string;
  model: string;
  warnings: string[];
}

/* -------------------------------- Clarity -------------------------------- */

export interface ClaritySettings {
  token_set: boolean;
  project_id: string | null;
  fetch_time: string;
  timezone: string;
  dimension_combos: string[][];
  allowed_dimensions: string[];
  next_run_at: string | null;
}

export interface ClaritySettingsUpdate {
  api_token?: string;
  project_id?: string;
  fetch_time?: string;
  timezone?: string;
  dimension_combos?: string[][];
}

export interface ClaritySnapshotInfo {
  combo_key: string;
  dimensions: string[];
  status: string;
  error: string | null;
}

export interface ClarityRun {
  id: number;
  trigger: string;
  data_date: string;
  status: string;
  requests_attempted: number;
  requests_succeeded: number;
  created_at: string;
  finished_at: string | null;
  error_summary: string | null;
  snapshots: ClaritySnapshotInfo[];
}

export interface ClarityStatus {
  configured: boolean;
  requests_used_today: number;
  daily_budget: number;
  latest_data_date: string | null;
  days_stored: number;
  next_run_at: string | null;
}

export interface ClarityAvailability {
  available: boolean;
  latest_data_date: string | null;
  days_stored: number;
}

/* -------------------------------- Prompts -------------------------------- */

export interface PromptTemplate {
  key: string;
  title: string;
  description: string;
  content: string;
  default_content: string;
  is_customized: boolean;
}
