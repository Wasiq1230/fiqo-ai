/**
 * Feature service — every backend endpoint the UI uses, in one place.
 *
 * All PDF tools return `{ result }` (or `{ quiz }` for the scored quiz) from the
 * new backend, so the components can rely on a single, consistent shape instead
 * of the old per-endpoint field names (summary / quiz / notes / answer / ...).
 */
import { api } from "./api";
import { clearTokens, setTokens } from "./auth";

// ── Auth ───────────────────────────────────────────────────────────────────

/**
 * Create an account.
 *
 * Returns the raw result rather than a session, because registering no longer
 * always signs you in: when the server enforces email verification it responds
 * with `verification_required: true` and no tokens. Storing that response
 * blindly used to leave the app in a half-signed-in state where every
 * subsequent request 401'd.
 */
export async function register({ name, email, password }) {
  const { data } = await api.post("/api/auth/register", { name, email, password });
  if (!data.verification_required && data.access_token) setTokens(data);
  return data;
}

/** Redeem the token from a confirmation email. Signs the user in on success. */
export async function verifyEmail(token) {
  const { data } = await api.post("/api/auth/verify-email", { token });
  setTokens(data);
  return data;
}

/** Ask for a fresh confirmation link. Always resolves — the server is deliberately vague. */
export async function resendVerification(email) {
  const { data } = await api.post("/api/auth/resend-verification", { email });
  return data;
}

/**
 * Request a password-reset link.
 *
 * Succeeds whether or not the address has an account — the server refuses to
 * reveal which, so the UI must not treat "success" as proof the account exists.
 */
export async function forgotPassword(email) {
  const { data } = await api.post("/api/auth/forgot-password", { email });
  return data;
}

/** Set a new password from a reset link. Signs the user in on success. */
export async function resetPassword(token, new_password) {
  const { data } = await api.post("/api/auth/reset-password", {
    token,
    new_password,
  });
  setTokens(data);
  return data;
}

export async function login({ email, password }) {
  const { data } = await api.post("/api/auth/login", { email, password });
  setTokens(data);
  return data;
}

export async function fetchMe() {
  const { data } = await api.get("/api/auth/me");
  return data;
}

/**
 * Sign out.
 *
 * Clearing localStorage only hides the tokens from this browser — they stay
 * valid until they expire, so anything that captured them (shared computer,
 * browser extension, earlier XSS) can keep using the account. The backend call
 * bumps the account's token version, which invalidates every outstanding
 * access and refresh token immediately, on every device.
 *
 * Best-effort: if the request fails (offline, token already expired) we still
 * clear local state so the user is not stuck on a signed-in screen.
 */
export async function logout() {
  try {
    await api.post("/api/auth/logout");
  } catch {
    /* ignore — local sign-out must always succeed */
  } finally {
    clearTokens();
  }
}

/**
 * Drop local tokens without calling the server.
 *
 * Used when the session is already known to be dead (a refresh just failed, or
 * /me returned 401). Calling the logout endpoint there would only produce
 * another guaranteed 401.
 */
export function clearSession() {
  clearTokens();
}

export async function changePassword({ current_password, new_password }) {
  const { data } = await api.post("/api/auth/change-password", {
    current_password,
    new_password,
  });
  setTokens(data);
  return data;
}

// ── Single-PDF helpers ───────────────────────────────────────────────────

function singleForm(file, extra = {}) {
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  return fd;
}

function multiForm(files, extra = {}) {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  return fd;
}

async function postText(url, form) {
  const { data } = await api.post(url, form);
  return data.result;
}

// ── Single-PDF features ────────────────────────────────────────────────────

export const summarize = (file) => postText("/api/pdf/summarize", singleForm(file));
export const quiz = (file) => postText("/api/pdf/quiz", singleForm(file));
export const quizByDifficulty = (file, difficulty) =>
  postText("/api/pdf/quiz-difficulty", singleForm(file, { difficulty }));
export const flashcards = (file) => postText("/api/pdf/flashcards", singleForm(file));
export const viva = (file) => postText("/api/pdf/viva", singleForm(file));
export const studyPlan = (file) => postText("/api/pdf/study-plan", singleForm(file));
export const notes = (file, note_type) =>
  postText("/api/pdf/notes", singleForm(file, { note_type }));
export const chat = (file, question) =>
  postText("/api/pdf/chat", singleForm(file, { question }));
export const search = (file, keyword) =>
  postText("/api/pdf/search", singleForm(file, { keyword }));

export async function scoredQuiz(file) {
  const { data } = await api.post("/api/pdf/scored-quiz", singleForm(file));
  return data.quiz;
}

// ── Multi-PDF features ─────────────────────────────────────────────────────

export const multiSummarize = (files) =>
  postText("/api/pdf/multi/summarize", multiForm(files));
export const multiQuiz = (files) => postText("/api/pdf/multi/quiz", multiForm(files));
export const multiChat = (files, question) =>
  postText("/api/pdf/multi/chat", multiForm(files, { question }));
export const multiSearch = (files, keyword) =>
  postText("/api/pdf/multi/search", multiForm(files, { keyword }));

// ── Feedback ────────────────────────────────────────────────────────────────

export async function submitFeedback(payload) {
  // `website` is the honeypot; always send it empty.
  const { data } = await api.post("/api/feedback", { website: "", ...payload });
  return data;
}

// ── Admin ────────────────────────────────────────────────────────────────

export async function adminAnalytics() {
  const { data } = await api.get("/api/admin/analytics");
  return data;
}

export async function adminListFeedback(params = {}) {
  const { data } = await api.get("/api/admin/feedback", { params });
  return data;
}

export async function adminUpdateFeedback(id, payload) {
  const { data } = await api.patch(`/api/admin/feedback/${id}`, payload);
  return data;
}

export async function adminListUsers(params = {}) {
  const { data } = await api.get("/api/admin/users", { params });
  return data;
}
