import messages from './messages.json';

export type Language = 'en' | 'ar';
export const LANGUAGE_KEY = 'alghrest.language';
const catalog: Record<string, string[]> = messages;
let language: Language = 'ar';
let initialized = false;
const listeners = new Set<() => void>();
export function isLanguage(value: unknown): value is Language { return value === 'en' || value === 'ar'; }
export function getLanguage(): Language { return language; }
export function languageDirection(): 'rtl' | 'ltr' { return language === 'ar' ? 'rtl' : 'ltr'; }
export function currentLocale(): string { return language === 'ar' ? 'ar-MA' : 'en-US'; }
export function subscribeLanguage(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
function applyLanguage() {
  if (typeof document !== 'undefined') { document.documentElement.lang = language; document.documentElement.dir = languageDirection(); }
}
export function setLanguage(value: Language) {
  if (!isLanguage(value)) return;
  const changed = language !== value;
  language = value;
  try { window.localStorage.setItem(LANGUAGE_KEY, value); } catch { /* Language still works when storage is unavailable. */ }
  applyLanguage();
  if (changed) for (const listener of listeners) listener();
}
export function initializeLanguage() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;
  try { const saved = window.localStorage.getItem(LANGUAGE_KEY); if (isLanguage(saved)) setLanguage(saved); } catch { /* Use the default. */ }
  applyLanguage();
  window.addEventListener('storage', event => {
    if (event.key === LANGUAGE_KEY && isLanguage(event.newValue)) setLanguage(event.newValue);
  });
}
const patterns = Object.entries(catalog).filter(([key]) => /\{\d+\}/.test(key)).map(([key, pair]) => {
  const positions: number[] = [];
  const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = key.split(/(\{\d+\})/g).map(part => {
    if (/^\{\d+\}$/.test(part)) { positions.push(Number(part.slice(1, -1))); return '(.*?)'; }
    return escape(part);
  });
  // Dot-all captures preserve source newlines; the final guard requires the real end of input.
  return { expression: new RegExp('^' + parts.join('') + '$(?!.)', 'su'), positions, pair };
});
export function translateText(value: string, target: Language = language): string {
  const key = value.replace(/\s+/g, ' ').trim();
  const pair = Object.hasOwn(catalog, key) ? catalog[key] : undefined;
  if (!pair) {
    for (const pattern of patterns) {
      // Match original text so interpolated source values retain spaces and newlines.
      const match = pattern.expression.exec(value);
      if (!match) continue;
      const values = new Map(pattern.positions.map((position, index) => [position, match[index + 1]]));
      return pattern.pair[target === 'en' ? 0 : 1].replace(/\{(\d+)\}/g, (placeholder, index: string) => values.get(Number(index)) ?? placeholder);
    }
    // Joined lists contain independent UI reason labels, each translated separately.
    if (key.includes(' · ')) {
      const parts = value.split(' · ');
      const translated = parts.map(part => translateText(part, target));
      // A mixed unknown source sentence is not an interface-label list.
      if (parts.every((part, index) => translated[index] !== part || Object.hasOwn(catalog, part.replace(/\s+/g, ' ').trim()))) return translated.join(' · ');
    }
    return value;
  }
  // Retain significant spaces around inline labels and values.
  const leading = value.match(/^\s*/)?.[0] ?? '';
  const trailing = value.match(/\s*$/)?.[0] ?? '';
  return leading + pair[target === 'en' ? 0 : 1] + trailing;
}
/** Display-only translation. Objects, React elements, numbers and unknown source text pass through. */
export function tr<T>(value: T): T {
  if (typeof value === 'string') return translateText(value) as T;
  return value;
}
/** Translate a known template without parsing or altering its interpolated values. */
export function formatMessage(key: string, values: readonly unknown[]): string {
  return translateText(key).replace(/\{(\d+)\}/g, (match, index: string) => {
    const position = Number(index);
    return position < values.length ? String(values[position]) : match;
  });
}

/** Language messages contain only a language code, with no extension fields. */
export function languageMessage(data: unknown, type: 'alghrest:language' | 'openterminal:language'): Language | null {
  if (typeof data !== 'object' || data === null || Array.isArray(data)) return null;
  const value = data as Record<string, unknown>;
  return Object.keys(value).length === 2 && value.type === type && isLanguage(value.language) ? value.language : null;
}
