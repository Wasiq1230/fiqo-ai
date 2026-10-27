/**
 * Token storage helpers.
 *
 * Tokens live in localStorage. This is a deliberate, documented tradeoff for a
 * pure SPA talking to a token-based API:
 *   + simple, works across tabs, survives reloads
 *   − readable by JS, so XSS could exfiltrate them
 * We mitigate the XSS risk at the source: React escapes all rendered content,
 * we never use dangerouslySetInnerHTML, and the API sets a strict CSP. For an
 * even stronger posture the backend can be switched to HttpOnly refresh cookies
 * later without changing the component code (only this module).
 */
const ACCESS_KEY = "FiQO_access";
const REFRESH_KEY = "FiQO_refresh";

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens({ access_token, refresh_token }) {
  if (access_token) localStorage.setItem(ACCESS_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function isAuthenticated() {
  return !!getAccessToken();
}
