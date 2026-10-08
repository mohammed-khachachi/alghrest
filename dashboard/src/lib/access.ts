// Tokens are kept in memory only, never in URLs, Vite variables or browser storage.
export type AccessScope = 'api' | 'advisory';
const tokens: Record<AccessScope, string> = { api: '', advisory: '' };
export function setAccessToken(scope: AccessScope, value: string): void { tokens[scope] = value; }
export function getAccessToken(scope: AccessScope): string { return tokens[scope]; }
export function accessHeaders(scope: AccessScope): Record<string, string> {
  return tokens[scope] ? { Authorization: `Bearer ${tokens[scope]}` } : {};
}
