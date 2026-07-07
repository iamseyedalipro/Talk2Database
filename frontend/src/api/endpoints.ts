/**
 * Thin, typed function wrappers around each API endpoint. Components call
 * these instead of building paths and payloads by hand.
 */

import { api } from './client';
import type {
  AnalysisPayload,
  AnalysisResponse,
  AskPayload,
  AskResponse,
  AuditItem,
  AuditQuery,
  BootstrapAvailable,
  BootstrapPayload,
  ChatAskPayload,
  ChatAskResponse,
  ChatMessageItem,
  ChatSessionCreate,
  ChatSessionItem,
  ChatSessionUpdate,
  ClarityAvailability,
  ClarityRun,
  ClaritySettings,
  ClaritySettingsUpdate,
  ClarityStatus,
  Connection,
  ConnectionAccess,
  ConnectionCreate,
  ConnectionTestResult,
  ConnectionUpdate,
  DashboardCreate,
  DashboardDetail,
  DashboardItem,
  DashboardUpdate,
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
  LayoutItemUpdate,
  LoginPayload,
  PromptTemplate,
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
  UsageQuery,
  UsageReport,
  User,
  WidgetCreate,
  WidgetItem,
  WidgetUpdate,
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

/** Self-service account preferences (currently: UI language). */
export const updateMe = (body: { language: string }) => api.patch<User>('/users/me', body);

export const getUserConnectionAccess = (userId: number) =>
  api.get<ConnectionAccess>(`/admin/users/${userId}/connection-access`);

export const setUserConnectionAccess = (userId: number, connectionIds: number[]) =>
  api.put<ConnectionAccess>(`/admin/users/${userId}/connection-access`, {
    connection_ids: connectionIds,
  });

export const listAudit = (params: AuditQuery = {}) => {
  const qs = new URLSearchParams();
  if (params.user_id != null) qs.set('user_id', String(params.user_id));
  if (params.status) qs.set('status', params.status);
  if (params.q) qs.set('q', params.q);
  qs.set('limit', String(params.limit ?? 100));
  qs.set('offset', String(params.offset ?? 0));
  return api.get<AuditItem[]>(`/admin/audit?${qs.toString()}`);
};

export const getUsageReport = (params: UsageQuery = {}) => {
  const qs = new URLSearchParams();
  if (params.from) qs.set('from', params.from);
  if (params.to) qs.set('to', params.to);
  const query = qs.toString();
  return api.get<UsageReport>(`/admin/usage${query ? `?${query}` : ''}`);
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

/* ------------------------------- Dashboards ------------------------------ */

export const listDashboards = () => api.get<DashboardItem[]>('/dashboards');

export const createDashboard = (body: DashboardCreate) =>
  api.post<DashboardItem>('/dashboards', body);

export const getDashboard = (id: number) => api.get<DashboardDetail>(`/dashboards/${id}`);

export const updateDashboard = (id: number, body: DashboardUpdate) =>
  api.patch<DashboardItem>(`/dashboards/${id}`, body);

export const deleteDashboard = (id: number) => api.del<void>(`/dashboards/${id}`);

export const createWidget = (dashboardId: number, body: WidgetCreate) =>
  api.post<WidgetItem>(`/dashboards/${dashboardId}/widgets`, body);

export const updateWidget = (dashboardId: number, widgetId: number, body: WidgetUpdate) =>
  api.patch<WidgetItem>(`/dashboards/${dashboardId}/widgets/${widgetId}`, body);

export const deleteWidget = (dashboardId: number, widgetId: number) =>
  api.del<void>(`/dashboards/${dashboardId}/widgets/${widgetId}`);

export const saveDashboardLayout = (dashboardId: number, items: LayoutItemUpdate[]) =>
  api.put<void>(`/dashboards/${dashboardId}/layout`, { items });

export const runWidget = (dashboardId: number, widgetId: number) =>
  api.post<ExecuteResponse>(`/dashboards/${dashboardId}/widgets/${widgetId}/run`, {});

/* ----------------------------- Chat sessions ----------------------------- */

export const listChats = (includeArchived = false) =>
  api.get<ChatSessionItem[]>(`/chats?include_archived=${includeArchived}`);

export const createChat = (body: ChatSessionCreate) =>
  api.post<ChatSessionItem>('/chats', body);

export const updateChat = (id: number, body: ChatSessionUpdate) =>
  api.patch<ChatSessionItem>(`/chats/${id}`, body);

export const deleteChat = (id: number) => api.del<void>(`/chats/${id}`);

export const listChatMessages = (id: number) =>
  api.get<ChatMessageItem[]>(`/chats/${id}/messages`);

export const askInChat = (id: number, body: ChatAskPayload) =>
  api.post<ChatAskResponse>(`/chats/${id}/ask`, body);

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

/* ------------------------------- Analysis -------------------------------- */

export const runAnalysis = (body: AnalysisPayload) =>
  api.post<AnalysisResponse>('/analysis', body);

/* -------------------------------- Clarity -------------------------------- */

export const clarityAvailability = () =>
  api.get<ClarityAvailability>('/clarity/availability');

export const getClaritySettings = () => api.get<ClaritySettings>('/clarity/settings');

export const updateClaritySettings = (body: ClaritySettingsUpdate) =>
  api.put<ClaritySettings>('/clarity/settings', body);

export const clarityFetchNow = () => api.post<ClarityRun>('/clarity/fetch-now');

export const listClarityRuns = (limit = 20) =>
  api.get<ClarityRun[]>(`/clarity/runs?limit=${limit}`);

export const clarityStatus = () => api.get<ClarityStatus>('/clarity/status');

/* -------------------------------- Prompts -------------------------------- */

export const listPrompts = () => api.get<PromptTemplate[]>('/prompts');

export const updatePrompt = (key: string, content: string) =>
  api.put<PromptTemplate>(`/prompts/${key}`, { content });

export const resetPrompt = (key: string) => api.post<PromptTemplate>(`/prompts/${key}/reset`);

/* -------------------------------- System --------------------------------- */

export const systemStatus = () => api.get<SystemStatus>('/system/status');
