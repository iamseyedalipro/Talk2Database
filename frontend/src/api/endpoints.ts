/**
 * Thin, typed function wrappers around each API endpoint. Components call
 * these instead of building paths and payloads by hand.
 */

import { api } from './client';
import type {
  AskPayload,
  AskResponse,
  BootstrapAvailable,
  BootstrapPayload,
  Connection,
  ConnectionCreate,
  ConnectionTestResult,
  ConnectionUpdate,
  DbSchema,
  ExecutePayload,
  ExecuteResponse,
  HistoryItem,
  InvitePayload,
  InviteResponse,
  LoginPayload,
  RegisterPayload,
  RerunPayload,
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

/* ------------------------------ Ask / execute ---------------------------- */

export const ask = (body: AskPayload) => api.post<AskResponse>('/ask', body);

export const execute = (body: ExecutePayload) =>
  api.post<ExecuteResponse>('/execute', body);

export const executeCsv = (body: ExecutePayload) =>
  api.download('/execute/csv', body, 'result.csv');

/* -------------------------------- History -------------------------------- */

export const listHistory = (limit = 50, offset = 0) =>
  api.get<HistoryItem[]>(`/history?limit=${limit}&offset=${offset}`);

export const getHistory = (id: number) => api.get<HistoryItem>(`/history/${id}`);

export const rerunHistory = (id: number, body: RerunPayload) =>
  api.post<ExecuteResponse>(`/history/${id}/rerun`, body);

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

/* -------------------------------- System --------------------------------- */

export const systemStatus = () => api.get<SystemStatus>('/system/status');
