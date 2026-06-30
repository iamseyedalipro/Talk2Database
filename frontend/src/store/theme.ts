/**
 * Zustand theme store. Holds the active color theme, persists the explicit
 * user choice to localStorage, and applies it to the document by setting
 * `data-theme` on <html>. Defaults to the OS-level color-scheme preference
 * when the user has never chosen explicitly.
 */

import { create } from 'zustand';

const THEME_KEY = 't2db.theme';

export type Theme = 'light' | 'dark';

function prefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

function readStoredTheme(): Theme | null {
  const raw = localStorage.getItem(THEME_KEY);
  return raw === 'light' || raw === 'dark' ? raw : null;
}

function resolveInitialTheme(): Theme {
  return readStoredTheme() ?? (prefersDark() ? 'dark' : 'light');
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: resolveInitialTheme(),

  setTheme: (theme) => {
    localStorage.setItem(THEME_KEY, theme);
    applyTheme(theme);
    set({ theme });
  },

  toggle: () => {
    get().setTheme(get().theme === 'dark' ? 'light' : 'dark');
  },
}));

/**
 * Synchronously applies the resolved theme to <html> before React mounts, to
 * avoid a flash of the wrong theme. Call once at the top of main.tsx, before
 * ReactDOM.createRoot(...).render(...).
 */
export function initTheme(): void {
  applyTheme(useThemeStore.getState().theme);
}
