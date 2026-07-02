/**
 * Thin, typed function wrappers around each API endpoint. Components call
 * these instead of building paths and payloads by hand.
 */

import { api } from './client';
import type {
  AskPayload,
  AskResponse,
  AuditItem,
  AuditQuery,
  BootstrapAvailable,
  BootstrapPayload,
  Connection,
  ConnectionCreate,
  ConnectionTestResult,
  ConnectionUpdate,
  DbSchema,
  DescriptionUpsert,
  GlossaryData,
  GlossaryDescription,
  Metric,
  MetricCreate,
  MetricUpdate,
  ExecutePayload,
  ExecuteResponse,
  ExplainPayload,
  ExplainResult,
  HistoryItem,
  InvitePayload,
  InviteResponse,
  LoginPayload,
  RegisterPayload,
  RerunPayload,
  ResultSummary,
  SavedQuery,
  SavedQueryCreate,
  SavedQueryRunPayload,
  SavedQueryUpdate,
  SuggestedQuestionsResponse,
  SummarizePayload,
  SystemStatus,
  TokenResponse,
  User,
} from './types';

/* --------------------------------- Auth ---------------------------------- */

export const login = (body: LoginPayload) => api.post<TokenResponse>('/auth/login', body);

export const bootstrapAvailable = () =>
  api.get<BootstrapAvailable>('/auth/bootstrap-available');

export const bootstrap = (body: BootstrapPayload) =>
  api.post<TokenResponse>('/auth/bootstrap', body);

export const register = (body: RegisterPayload) =>
  api.post<TokenResponse>('/auth/register', body);

export const me = () => api.get<User>('/auth/me');

/* --------------------------------- Users --------------------------------- */

export const listUsers = () => api.get<User[]>('/users');

export const inviteUser = (body: InvitePayload) =>
  api.post<InviteResponse>('/users/invite', body);

export const deleteUser = (id: number) => api.del<void>(`/users/${id}`);

export const listAudit = (params: AuditQuery = {}) => {
  const qs = new URLSearchParams();
  if (params.user_id != null) qs.set('user_id', String(params.user_id));
  if (params.status) qs.set('status', params.status);
  if (params.q) qs.set('q', params.q);
  qs.set('limit', String(params.limit ?? 100));
  qs.set('offset', String(params.offset ?? 0));
  return api.get<AuditItem[]>(`/admin/audit?${qs.toString()}`);
};

/* ------------------------------ Ask / execute ---------------------------- */

export const ask = (body: AskPayload) => api.post<AskResponse>('/ask', body);

export const execute = (body: ExecutePayload) =>
  api.post<ExecuteResponse>('/execute', body);

export const executeCsv = (body: ExecutePayload) =>
  api.download('/execute/csv', body, 'result.csv');

export const summarizeResults = (body: SummarizePayload) =>
  api.post<ResultSummary>('/results/summarize', body);

export const explainPlan = (body: ExplainPayload) =>
  api.post<ExplainResult>('/execute/explain', body);

/* -------------------------------- History -------------------------------- */

export const listHistory = (limit = 50, offset = 0) =>
  api.get<HistoryItem[]>(`/history?limit=${limit}&offset=${offset}`);

export const getHistory = (id: number) => api.get<HistoryItem>(`/history/${id}`);

export const rerunHistory = (id: number, body: RerunPayload) =>
  api.post<ExecuteResponse>(`/history/${id}/rerun`, body);

/* ----------------------------- Saved queries ----------------------------- */

export const listSavedQueries = (limit = 100, offset = 0) =>
  api.get<SavedQuery[]>(`/saved-queries?limit=${limit}&offset=${offset}`);

export const createSavedQuery = (body: SavedQueryCreate) =>
  api.post<SavedQuery>('/saved-queries', body);

export const updateSavedQuery = (id: number, body: SavedQueryUpdate) =>
  api.patch<SavedQuery>(`/saved-queries/${id}`, body);

export const deleteSavedQuery = (id: number) => api.del<void>(`/saved-queries/${id}`);

export const runSavedQuery = (id: number, body: SavedQueryRunPayload = {}) =>
  api.post<ExecuteResponse>(`/saved-queries/${id}/run`, body);

/* ------------------------------ Connections ------------------------------ */

export const listConnections = () => api.get<Connection[]>('/connections');

export const createConnection = (body: ConnectionCreate) =>
  api.post<Connection>('/connections', body);

export const updateConnection = (id: number, body: ConnectionUpdate) =>
  api.patch<Connection>(`/connections/${id}`, body);

export const deleteConnection = (id: number) => api.del<void>(`/connections/${id}`);

export const testConnection = (id: number) =>
  api.post<ConnectionTestResult>(`/connections/${id}/test`);

/** Cached structural schema (tables/columns/keys) for a connection's database. */
export const getSchema = (connectionId: number) =>
  api.get<DbSchema>(`/connections/${connectionId}/schema`);

/** Force a fresh introspection of a connection's schema (e.g. after a DDL change). */
export const refreshSchema = (connectionId: number) =>
  api.post<DbSchema>(`/connections/${connectionId}/schema/refresh`);

/** AI-generated example questions for a connection (cached per schema version). */
export const getSuggestedQuestions = (connectionId: number) =>
  api.get<SuggestedQuestionsResponse>(`/connections/${connectionId}/suggested-questions`);

/* --------------------------- Semantic glossary --------------------------- */

export const getGlossary = (connectionId: number) =>
  api.get<GlossaryData>(`/connections/${connectionId}/glossary`);

export const upsertDescription = (connectionId: number, body: DescriptionUpsert) =>
  api.put<GlossaryDescription>(`/connections/${connectionId}/glossary/descriptions`, body);

export const deleteDescription = (connectionId: number, descriptionId: number) =>
  api.del<void>(`/connections/${connectionId}/glossary/descriptions/${descriptionId}`);

export const createMetric = (connectionId: number, body: MetricCreate) =>
  api.post<Metric>(`/connections/${connectionId}/glossary/metrics`, body);

export const updateMetric = (connectionId: number, metricId: number, body: MetricUpdate) =>
  api.patch<Metric>(`/connections/${connectionId}/glossary/metrics/${metricId}`, body);

export const deleteMetric = (connectionId: number, metricId: number) =>
  api.del<void>(`/connections/${connectionId}/glossary/metrics/${metricId}`);

/* -------------------------------- System --------------------------------- */

export const systemStatus = () => api.get<SystemStatus>('/system/status');
