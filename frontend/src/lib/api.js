/**
 * Central API client.
 *
 * - Base URL comes from an environment variable (VITE_API_URL), never hard-coded.
 *   Falls back to the local dev backend so `npm run dev` works out of the box.
 * - A request interceptor attaches the current access token.
 * - A response interceptor transparently refreshes an expired access token once
 *   (using the refresh token) and retries the original request. Concurrent 401s
 *   share a single in-flight refresh so we never trigger a refresh storm.
 */
import axios from "axios";

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "./auth";

// An empty VITE_API_URL means "same origin" — that is the production setup,
// where nginx proxies /api/ to the backend container, so requests go to the
// page's own origin and the API is never exposed publicly.
// Unset (local `npm run dev`) falls back to the dev backend on port 8000.
const RAW_API_URL = import.meta.env.VITE_API_URL;
const BASE_URL =
  RAW_API_URL === undefined || RAW_API_URL === null
    ? "http://127.0.0.1:8000"
    : String(RAW_API_URL).replace(/\/$/, "");

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000, // AI calls can be slow; 60s is a sane ceiling.
});

// ── Attach access token ──────────────────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Transparent refresh on 401 ─────────────────────────────────────────────
let refreshPromise = null;

async function refreshAccessToken() {
  const refresh_token = getRefreshToken();
  if (!refresh_token) throw new Error("No refresh token");
  // Use a bare axios call so we don't recurse through this interceptor.
  const res = await axios.post(`${BASE_URL}/api/auth/refresh`, {
    refresh_token,
  });
  setTokens(res.data);
  return res.data.access_token;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;

    // Only try to refresh once per request, and never for the refresh call.
    if (
      status === 401 &&
      original &&
      !original._retried &&
      !original.url?.includes("/api/auth/")
    ) {
      original._retried = true;
      try {
        refreshPromise = refreshPromise || refreshAccessToken();
        const newToken = await refreshPromise;
        refreshPromise = null;
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch (refreshErr) {
        refreshPromise = null;
        clearTokens();
        // Broadcast so the app can drop to the login screen.
        window.dispatchEvent(new CustomEvent("FiQO:logout"));
        return Promise.reject(refreshErr);
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Extract a human-friendly message from an axios error without leaking internals.
 */
export function apiErrorMessage(error, fallback = "Something went wrong.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  // Some endpoints return a structured detail ({ code, message }) so the UI can
  // react to *which* error it was, not just display it.
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.message)
    return detail.message;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  // The validation handler in the backend reshapes 422s into { errors: [...] }.
  const errors = error?.response?.data?.errors;
  if (Array.isArray(errors) && errors[0]?.message) return errors[0].message;
  if (error?.code === "ECONNABORTED") return "The request timed out. Please try again.";
  if (error?.message === "Network Error")
    return "Cannot reach the server. Check your connection.";
  return fallback;
}

/**
 * Machine-readable error code, when the backend supplied one.
 *
 * Used to branch on specific failures — e.g. "email_not_verified" needs a
 * resend button, not just a red toast.
 */
export function apiErrorCode(error) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    return detail.code ?? null;
  }
  return null;
}
