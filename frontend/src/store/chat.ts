/**
 * Zustand store for persistent Ask chat sessions: the sidebar list and the
 * active selection. Message threads are loaded per-session by the Ask page.
 */

import { create } from 'zustand';
import { createChat, deleteChat, listChats, updateChat } from '../api/endpoints';
import type { ChatSessionItem } from '../api/types';

interface ChatState {
  sessions: ChatSessionItem[];
  sessionsLoading: boolean;
  activeId: number | null;
  loadSessions: () => Promise<void>;
  /** Create a session bound to a connection and make it active. */
  createSession: (connectionId: number) => Promise<ChatSessionItem>;
  selectSession: (id: number | null) => void;
  renameSession: (id: number, title: string) => Promise<void>;
  setArchived: (id: number, archived: boolean) => Promise<void>;
  removeSession: (id: number) => Promise<void>;
  /** Sync a session's title/recency after the server auto-names it. */
  applySessionUpdate: (id: number, title: string) => void;
  clear: () => void;
}

const byRecency = (a: ChatSessionItem, b: ChatSessionItem) =>
  b.updated_at.localeCompare(a.updated_at);

export const useChatStore = create<ChatState>((set) => ({
  sessions: [],
  sessionsLoading: false,
  activeId: null,

  loadSessions: async () => {
    set({ sessionsLoading: true });
    try {
      const sessions = await listChats(true);
      set({ sessions });
    } finally {
      set({ sessionsLoading: false });
    }
  },

  createSession: async (connectionId) => {
    const session = await createChat({ connection_id: connectionId });
    set((s) => ({ sessions: [session, ...s.sessions], activeId: session.id }));
    return session;
  },

  selectSession: (id) => set({ activeId: id }),

  renameSession: async (id, title) => {
    const updated = await updateChat(id, { title });
    set((s) => ({ sessions: s.sessions.map((c) => (c.id === id ? updated : c)) }));
  },

  setArchived: async (id, archived) => {
    const updated = await updateChat(id, { archived });
    set((s) => ({ sessions: s.sessions.map((c) => (c.id === id ? updated : c)) }));
  },

  removeSession: async (id) => {
    await deleteChat(id);
    set((s) => ({
      sessions: s.sessions.filter((c) => c.id !== id),
      activeId: s.activeId === id ? null : s.activeId,
    }));
  },

  applySessionUpdate: (id, title) => {
    const now = new Date().toISOString();
    set((s) => ({
      sessions: s.sessions
        .map((c) => (c.id === id ? { ...c, title, updated_at: now } : c))
        .sort(byRecency),
    }));
  },

  clear: () => set({ sessions: [], activeId: null, sessionsLoading: false }),
}));
