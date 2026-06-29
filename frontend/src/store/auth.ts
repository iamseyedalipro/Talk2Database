/**
 * Zustand auth store. Holds the JWT and the current user, persists the token
 * (and a snapshot of the user) to localStorage, and rehydrates on load.
 */

import { create } from 'zustand';
import type { User } from '../api/types';

const TOKEN_KEY = 't2db.token';
const USER_KEY = 't2db.user';

function readUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: () => boolean;
  setAuth: (token: string, user: User) => void;
  setUser: (user: User) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem(TOKEN_KEY),
  user: readUser(),

  isAuthenticated: () => Boolean(get().token),

  setAuth: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    set({ token, user });
  },

  setUser: (user) => {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    set({ user });
  },

  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    set({ token: null, user: null });
  },
}));

/** Non-reactive token read, used by the API client. */
export const getStoredToken = (): string | null => useAuthStore.getState().token;
