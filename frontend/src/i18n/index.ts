/**
 * i18next setup: English (default) + Persian with RTL.
 *
 * Namespaces are the JSON files under ./locales/<lang>/ — adding a new
 * namespace is just adding a file to both language folders. The language is
 * remembered in localStorage and mirrored to <html lang/dir> so Persian flips
 * the whole layout to RTL; the per-user preference from the profile is applied
 * on login (see store/auth.ts).
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const LANG_KEY = 't2db.lang';

export const SUPPORTED_LANGUAGES = ['en', 'fa'] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

const isSupported = (value: string | null): value is Language =>
  value === 'en' || value === 'fa';

function loadNamespaces(modules: Record<string, unknown>): Record<string, object> {
  const resources: Record<string, object> = {};
  for (const [path, mod] of Object.entries(modules)) {
    const name = /\/([^/]+)\.json$/.exec(path)?.[1];
    if (name) resources[name] = (mod as { default: object }).default;
  }
  return resources;
}

const en = loadNamespaces(import.meta.glob('./locales/en/*.json', { eager: true }));
const fa = loadNamespaces(import.meta.glob('./locales/fa/*.json', { eager: true }));

const stored = localStorage.getItem(LANG_KEY);
const initialLanguage: Language = isSupported(stored) ? stored : 'en';

export function applyDocumentLanguage(lng: string): void {
  document.documentElement.lang = lng;
  document.documentElement.dir = lng === 'fa' ? 'rtl' : 'ltr';
}

void i18n.use(initReactI18next).init({
  resources: { en, fa },
  ns: Object.keys(en),
  defaultNS: 'common',
  lng: initialLanguage,
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React already escapes
  returnEmptyString: false,
});

i18n.on('languageChanged', (lng) => {
  applyDocumentLanguage(lng);
  localStorage.setItem(LANG_KEY, lng);
});
applyDocumentLanguage(initialLanguage);

export default i18n;
