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
  /** UI language preference ("en" | "fa"); "fa" flips the layout to RTL. */
  language: string;
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
  owner_id: number;
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

/** The set of connection ids an admin has granted a user access to. */
export interface ConnectionAccess {
  connection_ids: number[];
}

export interface ConnectionTestResult {
  ok: boolean;
  message: string | null;
}

/* ----------------------------- Ask / generate ---------------------------- */

export interface AskPayload {
  connection_id: number;
  question: string;
}

export type AskStatus = 'ok' | 'needs_clarification' | 'unanswerable' | 'verification_failed';

export interface SuggestedInterpretation {
  /** Short button text. */
  label: string;
  /** A complete, self-contained question sent back to /ask when clicked. */
  description: string;
}

export interface AskResponse {
  history_id: number;
  status: AskStatus;
  /** Null for clarification/unanswerable turns that produced no SQL. */
  generated_sql: string | null;
  explanation: string | null;
  clarification_question: string | null;
  suggested_interpretations: SuggestedInterpretation[];
  /** Hallucinated tables/columns, populated when status is 'verification_failed'. */
  invalid_identifiers: string[];
  retry_count: number;
  dialect: string;
  provider: string;
  model: string;
  warnings: string[];
}

export interface SuggestedQuestionsResponse {
  questions: string[];
}

/* ----------------------------- Chat sessions ----------------------------- */

export interface ChatSessionItem {
  id: number;
  title: string;
  connection_id: number | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionCreate {
  connection_id: number;
  title?: string;
}

export interface ChatSessionUpdate {
  title?: string;
  archived?: boolean;
}

export interface ChatResultSample {
  columns: ResultColumn[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
}

export interface ChatMessageItem {
  id: number;
  role: 'user' | 'assistant';
  /** The question text (user turns). */
  content: string | null;
  /** The stored AskResponse (assistant turns). */
  ask: AskResponse | null;
  history_id: number | null;
  executed_sql: string | null;
  result_sample: ChatResultSample | null;
  created_at: string;
}

export interface ChatAskPayload {
  question: string;
}

export interface ChatAskResponse extends AskResponse {
  user_message_id: number;
  assistant_message_id: number;
  session_title: string;
}

/* ------------------------------- Dashboards ------------------------------ */

export type WidgetView =
  | 'table'
  | 'bar'
  | 'hbar'
  | 'line'
  | 'area'
  | 'pie'
  | 'scatter'
  | 'radar'
  | 'combo';

/** Chart kinds are every view except 'table'. */
export type ChartKind = Exclude<WidgetView, 'table'>;

export type StackMode = 'none' | 'stacked' | 'percent';
export type ComboSeriesType = 'bar' | 'line';
export type PieMode = 'category' | 'columns';

export interface WidgetViz {
  view: WidgetView;
  x_column: string | null;
  /** Ordered Y columns (wide multi-series). Empty = auto-pick the first numeric. */
  y_columns: string[];
  /** Long-shape pivot: one series per distinct value; uses y_columns[0] as the value. */
  series_column: string | null;
  /** bar / hbar / area only; 'percent' is 100%-stacked. */
  stacked: StackMode;
  /** combo only: per-Y-column mark; columns absent from the map default to 'bar'. */
  combo_types: Record<string, ComboSeriesType>;
  /** combo only: Y columns plotted on the secondary (right) axis. */
  right_axis: string[];
  /** pie only: 'category' = one slice per row; 'columns' = one slice per y column total. */
  pie_mode: PieMode;
  /** Legacy single-Y key, mirrored from y_columns[0] for rollback safety. */
  y_column: string | null;
}

export interface WidgetItem {
  id: number;
  title: string;
  connection_id: number | null;
  sql: string;
  viz: WidgetViz;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface WidgetCreate {
  title: string;
  connection_id: number;
  sql: string;
  viz: WidgetViz;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
}

export interface WidgetUpdate {
  title?: string;
  connection_id?: number;
  sql?: string;
  viz?: WidgetViz;
}

export interface DashboardItem {
  id: number;
  name: string;
  description: string | null;
  shared: boolean;
  owner_email: string | null;
  is_owner: boolean;
  widget_count: number;
  created_at: string;
  updated_at: string;
}

export interface DashboardDetail extends DashboardItem {
  widgets: WidgetItem[];
}

export interface DashboardCreate {
  name: string;
  description?: string | null;
  shared?: boolean;
}

export interface DashboardUpdate {
  name?: string;
  description?: string | null;
  shared?: boolean;
}

export interface LayoutItemUpdate {
  widget_id: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/* --------------------------- Ask over WebSocket --------------------------- */

/** A small sample of an exploratory query's rows, shown in the activity feed. */
export interface QueryResultPreview {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
}

/**
 * Server events streamed by `/api/ask/ws` while a question is being answered.
 * Every event carries a monotonically increasing `seq`.
 */
export type AskProgressEvent =
  | { type: 'run_started'; seq: number; mode: 'standard' | 'analysis'; provider: string; model: string }
  | { type: 'status'; seq: number; stage: string; message: string }
  | { type: 'tables_directory'; seq: number; count: number; tables: string[] }
  | { type: 'tables_requested'; seq: number; round: number; table_names: string[] }
  | { type: 'table_details_sent'; seq: number; round: number; table_names: string[]; unknown: string[] }
  | { type: 'assistant_note'; seq: number; text: string }
  | { type: 'exploratory_query'; seq: number; round: number; sql: string; purpose: string | null }
  | ({ type: 'query_result'; seq: number; sql: string; error?: string | null } & Partial<QueryResultPreview>)
  | { type: 'generating_sql'; seq: number; attempt: number; attempts: number }
  | { type: 'retry'; seq: number; attempt: number; reason: string; detail: string }
  /**
   * The chat bookkeeping fields (`user_message_id`, `assistant_message_id`,
   * `session_title`) are present when the run was started with a `chat_id`.
   */
  | ({ type: 'final_result'; seq: number } & AskResponse &
      Partial<Pick<ChatAskResponse, 'user_message_id' | 'assistant_message_id' | 'session_title'>>)
  | { type: 'error'; seq: number; code: string; detail: string }
  | { type: 'cancelled'; seq: number };

/** The WebSocket `start` payload; `chat_id` binds the run to a chat session. */
export interface AskSocketPayload extends AskPayload {
  chat_id?: number;
}

/** One rendered step in the chat's agent activity feed. */
export type AskActivityStep =
  | { kind: 'status'; text: string }
  | { kind: 'tables_directory'; count: number }
  | { kind: 'tables_requested'; tables: string[] }
  | { kind: 'table_details_sent'; tables: string[]; unknown: string[] }
  | { kind: 'note'; text: string }
  | {
      kind: 'query';
      sql: string;
      purpose: string | null;
      result?: QueryResultPreview;
      error?: string | null;
    }
  | { kind: 'generating'; attempt: number; attempts: number }
  | { kind: 'retry'; reason: string; detail: string };

/* --------------------------- Ask admin settings --------------------------- */

export interface AskSettings {
  analysis_mode: boolean;
  row_cap: number;
  row_cap_min: number;
  row_cap_max: number;
}

export interface AskSettingsUpdate {
  analysis_mode: boolean;
  row_cap: number;
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
  /** Chat turn to attach the executed SQL + a result sample to. */
  chat_message_id?: number;
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
  /** Null for clarification turns that produced no SQL. */
  generated_sql: string | null;
  response_status: AskStatus;
  clarification_json: {
    clarification_question: string | null;
    suggested_interpretations: SuggestedInterpretation[];
  } | null;
  retry_count: number;
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

export type ChartType = WidgetView | 'none';

export interface SummarizePayload {
  question?: string | null;
  columns: ResultColumn[];
  rows: unknown[][];
}

export interface ResultSummary {
  summary: string;
  chart_type: ChartType;
  x_column: string | null;
  /** Legacy single-Y field, still sent by the backend (mirrors y_columns[0]). */
  y_column: string | null;
  y_columns: string[] | null;
  series_column: string | null;
  stacked: boolean;
  combo_line_columns: string[] | null;
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
  /** Null for clarification turns that produced no SQL. */
  generated_sql: string | null;
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

/* ---------------------------- Token usage report ------------------------- */

export interface UsageTotals {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_tokens: number;
  call_count: number;
}

export interface UsageByKey {
  key: string;
  label: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_tokens: number;
  call_count: number;
}

export interface UsageDailyPoint {
  day: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_tokens: number;
}

export interface UsageReport {
  totals: UsageTotals;
  by_user: UsageByKey[];
  by_model: UsageByKey[];
  by_provider: UsageByKey[];
  daily: UsageDailyPoint[];
}

export interface UsageQuery {
  from?: string;
  to?: string;
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
