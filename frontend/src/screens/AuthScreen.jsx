/**
 * Auth screen — sign in, create account, confirm email, reset password.
 *
 * Stages:
 *   "form"    — the sign-in or sign-up form
 *   "sent"    — account created, waiting on the confirmation link
 *   "verify"  — a ?verify=<token> link was opened; redeeming it
 *   "forgot"  — asking which address to send a reset link to
 *   "reset"   — a ?reset=<token> link was opened; choosing a new password
 *
 * The "sent" stage exists because registering no longer signs you in. Dropping
 * the user back on an empty login form after signup — with no explanation —
 * reads as a failure, and they retry until they hit the rate limiter.
 *
 * Client-side validation mirrors the server's rules (name required, valid
 * email, password >= 8 chars with letters and digits) for instant feedback,
 * while the server stays the source of truth.
 */
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../components/Toast";
import { apiErrorCode, apiErrorMessage } from "../lib/api";
import { forgotPassword, resendVerification } from "../lib/services";
import { Ico, Icons, Spinner } from "../components/icons";

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Pull a one-time token out of the URL and strip it from the address bar.
 *
 * Returns { kind, token } where kind is "verify" or "reset", or null.
 */
function readUrlToken() {
  const params = new URLSearchParams(window.location.search);
  const kind = params.has("verify") ? "verify" : params.has("reset") ? "reset" : null;
  if (!kind) return null;
  const token = params.get(kind);
  if (!token) return null;
  // Remove it immediately: a single-use token sitting in the URL ends up in
  // browser history, and gets leaked wholesale via the Referer header on the
  // next outbound link.
  params.delete(kind);
  const qs = params.toString();
  window.history.replaceState(
    {},
    "",
    window.location.pathname + (qs ? `?${qs}` : "")
  );
  return { kind, token };
}

// Memoised because the read is destructive — it rewrites the URL. StrictMode
// double-invokes state initialisers in development, and a second raw call
// would find the token already stripped and return null, silently skipping the
// flow in exactly the environment where it is being tested.
let cachedUrlToken;
function consumeUrlToken() {
  if (cachedUrlToken === undefined) cachedUrlToken = readUrlToken();
  return cachedUrlToken;
}

/** Shared password rule, matching the backend's. */
function passwordProblem(value) {
  if (value.length < 8) return "At least 8 characters.";
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value))
    return "Include both letters and numbers.";
  return null;
}

export default function AuthScreen() {
  const { login, register, verifyEmail, resetPassword } = useAuth();
  const toast = useToast();

  // Read during initialisation rather than in an effect, so the first paint is
  // already the right screen instead of a login form that flashes and vanishes.
  const [urlToken] = useState(consumeUrlToken);
  const [stage, setStage] = useState(() => {
    if (urlToken?.kind === "verify") return "verify";
    if (urlToken?.kind === "reset") return "reset";
    return "form";
  });

  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [pendingEmail, setPendingEmail] = useState("");
  const [notice, setNotice] = useState("");
  const [cooldown, setCooldown] = useState(0);

  // ── Redeem a confirmation link, if we arrived from one ─────────────────
  useEffect(() => {
    if (urlToken?.kind !== "verify") return undefined;
    let cancelled = false;
    (async () => {
      try {
        await verifyEmail(urlToken.token);
        if (!cancelled) toast.success("Email confirmed — you're signed in.");
      } catch (err) {
        if (cancelled) return;
        toast.error(
          apiErrorMessage(err, "That confirmation link is no longer valid.")
        );
        setStage("form");
        setMode("login");
      }
    })();
    return () => {
      cancelled = true;
    };
    // toast is recreated on every provider render; including it would re-run
    // the redemption and burn the single-use token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlToken, verifyEmail]);

  // ── Resend / resend-reset cooldown ticker ──────────────────────────────
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const id = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  const validate = () => {
    const e = {};
    if (mode === "signup" && name.trim().length < 2)
      e.name = "Please enter your name.";
    if (!emailRe.test(email)) e.email = "Enter a valid email address.";
    const pw = passwordProblem(password);
    if (pw) e.password = pw;
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async (ev) => {
    ev?.preventDefault();
    if (busy || !validate()) return;
    setBusy(true);
    setNotice("");
    try {
      if (mode === "login") {
        await login({ email, password });
        toast.success("Welcome back!");
      } else {
        const result = await register({ name: name.trim(), email, password });
        if (result?.verification_required) {
          setPendingEmail(result.email || email);
          setNotice(result.message || "");
          setCooldown(60);
          setStage("sent");
        } else {
          toast.success("Account created — welcome!");
        }
      }
    } catch (err) {
      // An unverified account trying to sign in is not a dead end: show the
      // same "check your inbox" panel with a working resend button.
      if (apiErrorCode(err) === "email_not_verified") {
        setPendingEmail(email);
        setNotice(apiErrorMessage(err, ""));
        setCooldown(0);
        setStage("sent");
      } else {
        toast.error(
          apiErrorMessage(err, "Authentication failed. Please try again.")
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const resend = useCallback(async () => {
    if (busy || cooldown > 0 || !pendingEmail) return;
    setBusy(true);
    try {
      await resendVerification(pendingEmail);
      toast.success("Sent. Check your inbox (and the spam folder).");
      setCooldown(60);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not send the email right now."));
    } finally {
      setBusy(false);
    }
  }, [busy, cooldown, pendingEmail, toast]);

  // ── Forgot password: request the link ──────────────────────────────────
  const requestReset = async (ev) => {
    ev?.preventDefault();
    if (busy) return;
    if (!emailRe.test(email)) {
      setErrors({ email: "Enter a valid email address." });
      return;
    }
    setBusy(true);
    setErrors({});
    try {
      const result = await forgotPassword(email);
      // Deliberately shown whether or not the account exists — the server does
      // not say, and neither should the UI.
      setPendingEmail(email);
      setNotice(result?.message || "");
      setCooldown(60);
      setStage("resetSent");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not send the email right now."));
    } finally {
      setBusy(false);
    }
  };

  // ── Reset password: submit the new one ─────────────────────────────────
  const submitNewPassword = async (ev) => {
    ev?.preventDefault();
    if (busy) return;
    const problem = passwordProblem(newPassword);
    if (problem) {
      setErrors({ newPassword: problem });
      return;
    }
    setBusy(true);
    setErrors({});
    try {
      await resetPassword(urlToken.token, newPassword);
      toast.success("Password changed — you're signed in.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "That reset link is no longer valid."));
      setStage("form");
      setMode("login");
    } finally {
      setBusy(false);
    }
  };

  const backToLogin = () => {
    setStage("form");
    setMode("login");
    setPassword("");
    setErrors({});
    setNotice("");
  };

  const header = (
    <>
      <div className="um-auth-logo">
        <div className="um-auth-logomark">
          <Ico path={Icons.sparkle} size={20} />
        </div>
        <h1>
          FIQO<span>.</span>
        </h1>
      </div>
      <p className="um-auth-sub">Your AI-powered university study workspace</p>
    </>
  );

  const passwordToggle = (
    <button
      type="button"
      className="um-password-toggle"
      onClick={() => setShowPassword(!showPassword)}
      aria-label={showPassword ? "Hide password" : "Show password"}
    >
      <Ico path={showPassword ? Icons.eyeOff : Icons.eye} size={16} />
    </button>
  );

  // ── Redeeming a confirmation link ──────────────────────────────────────
  if (stage === "verify") {
    return (
      <div className="um-auth-bg">
        <div className="um-auth-card" style={{ textAlign: "center" }}>
          {header}
          <Spinner />
          <p className="um-auth-sub" style={{ marginTop: 12 }}>
            Confirming your email address…
          </p>
        </div>
      </div>
    );
  }

  // ── Choosing a new password ────────────────────────────────────────────
  if (stage === "reset") {
    return (
      <div className="um-auth-bg">
        <form className="um-auth-card" onSubmit={submitNewPassword} noValidate>
          {header}
          <h2 style={{ fontSize: 18, margin: "8px 0 4px" }}>
            Choose a new password
          </h2>
          <p className="um-auth-sub" style={{ marginBottom: 16 }}>
            At least 8 characters, with letters and numbers. This also signs you
            out on every other device.
          </p>

          <div className="um-field um-password-field">
            <input
              className="um-input"
              type={showPassword ? "text" : "password"}
              placeholder="New password"
              autoComplete="new-password"
              autoFocus
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              aria-invalid={!!errors.newPassword}
              aria-label="New password"
            />
            {passwordToggle}
            {errors.newPassword && (
              <p className="um-field-error">{errors.newPassword}</p>
            )}
          </div>

          <button
            className="um-btn um-btn-primary um-btn-full"
            type="submit"
            disabled={busy}
          >
            {busy ? <Spinner /> : "Set new password"}
          </button>

          <p className="um-auth-switch">
            <button type="button" className="um-link-btn" onClick={backToLogin}>
              Back to sign in
            </button>
          </p>
        </form>
      </div>
    );
  }

  // ── Asking where to send the reset link ────────────────────────────────
  if (stage === "forgot") {
    return (
      <div className="um-auth-bg">
        <form className="um-auth-card" onSubmit={requestReset} noValidate>
          {header}
          <h2 style={{ fontSize: 18, margin: "8px 0 4px" }}>
            Reset your password
          </h2>
          <p className="um-auth-sub" style={{ marginBottom: 16 }}>
            Enter your email and we'll send you a link to choose a new password.
          </p>

          <div className="um-field">
            <input
              className="um-input"
              type="email"
              placeholder="Email address"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={!!errors.email}
              aria-label="Email address"
            />
            {errors.email && <p className="um-field-error">{errors.email}</p>}
          </div>

          <button
            className="um-btn um-btn-primary um-btn-full"
            type="submit"
            disabled={busy}
          >
            {busy ? <Spinner /> : "Send reset link"}
          </button>

          <p className="um-auth-switch">
            <button type="button" className="um-link-btn" onClick={backToLogin}>
              Back to sign in
            </button>
          </p>
        </form>
      </div>
    );
  }

  // ── Waiting on the inbox (signup confirmation or reset link) ───────────
  if (stage === "sent" || stage === "resetSent") {
    const isReset = stage === "resetSent";
    return (
      <div className="um-auth-bg">
        <div className="um-auth-card">
          {header}
          <h2 style={{ fontSize: 18, margin: "8px 0 8px" }}>Check your email</h2>
          <p className="um-auth-sub" style={{ marginBottom: 4 }}>
            {notice ||
              (isReset
                ? "If an account exists for that address, a reset link is on its way."
                : "We sent a confirmation link. Click it to activate your account.")}
          </p>
          {pendingEmail && (
            <p style={{ fontWeight: 600, wordBreak: "break-all", margin: "0 0 16px" }}>
              {pendingEmail}
            </p>
          )}

          <button
            type="button"
            className="um-btn um-btn-primary um-btn-full"
            onClick={isReset ? requestReset : resend}
            disabled={busy || cooldown > 0}
          >
            {busy ? (
              <Spinner />
            ) : cooldown > 0 ? (
              `Resend in ${cooldown}s`
            ) : (
              "Resend email"
            )}
          </button>

          <p className="um-auth-switch">
            <button type="button" className="um-link-btn" onClick={backToLogin}>
              Back to sign in
            </button>
          </p>
        </div>
      </div>
    );
  }

  // ── Sign in / sign up ──────────────────────────────────────────────────
  return (
    <div className="um-auth-bg">
      <form className="um-auth-card" onSubmit={submit} noValidate>
        {header}

        {mode === "signup" && (
          <div className="um-field">
            <input
              className="um-input"
              type="text"
              placeholder="Full name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={!!errors.name}
              aria-label="Full name"
            />
            {errors.name && <p className="um-field-error">{errors.name}</p>}
          </div>
        )}

        <div className="um-field">
          <input
            className="um-input"
            type="email"
            placeholder="Email address"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={!!errors.email}
            aria-label="Email address"
          />
          {errors.email && <p className="um-field-error">{errors.email}</p>}
        </div>

        <div className="um-field um-password-field">
          <input
            className="um-input"
            type={showPassword ? "text" : "password"}
            placeholder="Password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
            aria-label="Password"
          />
          {passwordToggle}
          {errors.password && <p className="um-field-error">{errors.password}</p>}
        </div>

        {mode === "login" && (
          <p style={{ textAlign: "right", margin: "-4px 0 4px" }}>
            <button
              type="button"
              className="um-link-btn"
              onClick={() => {
                setStage("forgot");
                setErrors({});
                setNotice("");
              }}
            >
              Forgot password?
            </button>
          </p>
        )}

        {mode === "signup" && (
          <p className="um-auth-sub" style={{ fontSize: 12, marginTop: -4 }}>
            Use an address you can open — we'll email you a confirmation link.
          </p>
        )}

        <button
          className="um-btn um-btn-primary um-btn-full"
          type="submit"
          disabled={busy}
        >
          {busy ? <Spinner /> : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <p className="um-auth-switch">
          {mode === "login" ? "Don't have an account? " : "Already have an account? "}
          <button
            type="button"
            className="um-link-btn"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setErrors({});
            }}
          >
            {mode === "login" ? "Sign up" : "Sign in"}
          </button>
        </p>
      </form>
    </div>
  );
}
