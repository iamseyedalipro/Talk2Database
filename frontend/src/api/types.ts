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

/* ----------------------------- Ask / generate ---------------------------- */

export interface AskPayload {
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

/* -------------------------------- History -------------------------------- */

export type QueryStatus = 'preview' | 'success' | 'error';

export interface HistoryItem {
  id: number;
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

/* ------------------------------- Imports --------------------------------- */

export type ImportKind = 'manual' | 'scheduled';
export type ImportStatus = 'running' | 'success' | 'failed';

export interface ImportRun {
  id: number;
  kind: ImportKind;
  status: ImportStatus;
  filename: string | null;
  bytes: number | null;
  message: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface UploadAccepted {
  import_run_id: number;
  status: ImportStatus;
}

/* -------------------------------- System --------------------------------- */

export type ImportMode = 'manual' | 'scheduled';

export interface SystemStatus {
  import_mode: ImportMode;
  provider: string;
  model: string;
  userdata_connected: boolean;
  schema_table_count: number;
  schema_version: number | null;
  last_import: ImportRun | null;
}
