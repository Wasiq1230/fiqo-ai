/**
 * Authentication context.
 *
 * Replaces the previous insecure approach (which stored the raw password in
 * localStorage). Auth now goes through the backend: register/login return JWT
 * access + refresh tokens (persisted by lib/auth.js), and the current user is
 * loaded from /api/auth/me. Components read `user`, `loading`, and the
 * `login`/`register`/`logout` actions from this context.
 *
 * A global "FiQO:logout" event (dispatched by the axios interceptor when a
 * refresh ultimately fails) is handled here so an expired session cleanly
 * returns the user to the auth screen.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { isAuthenticated } from "../lib/auth";
import * as svc from "../lib/services";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(isAuthenticated());

  const loadMe = useCallback(async () => {
    if (!isAuthenticated()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await svc.fetchMe());
    } catch {
      // Session is already invalid — clear locally, don't call the server.
      svc.clearSession();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();

    const onLogout = () => setUser(null);
    window.addEventListener("FiQO:logout", onLogout);
    return () => window.removeEventListener("FiQO:logout", onLogout);
  }, [loadMe]);

  const login = useCallback(async (credentials) => {
    await svc.login(credentials);
    setUser(await svc.fetchMe());
  }, []);

  /**
   * Create an account.
   *
   * Resolves with the server's result so the caller can tell the two outcomes
   * apart. When `verification_required` is true no session exists yet, so
   * fetching /me here would 401 and bounce the user back to the login screen
   * with a confusing error instead of the "check your inbox" message.
   */
  const register = useCallback(async (payload) => {
    const result = await svc.register(payload);
    if (!result?.verification_required) setUser(await svc.fetchMe());
    return result;
  }, []);

  /** Redeem a confirmation link and start the session it grants. */
  const verifyEmail = useCallback(async (token) => {
    await svc.verifyEmail(token);
    setUser(await svc.fetchMe());
  }, []);

  /** Set a new password from a reset link, then start the new session. */
  const resetPassword = useCallback(async (token, newPassword) => {
    await svc.resetPassword(token, newPassword);
    setUser(await svc.fetchMe());
  }, []);

  const logout = useCallback(async () => {
    await svc.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        logout,
        verifyEmail,
        resetPassword,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
