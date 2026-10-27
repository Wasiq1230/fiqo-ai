/**
 * Minimal, dependency-free toast system.
 *
 * Usage:
 *   const toast = useToast();
 *   toast.success("Saved!");
 *   toast.error("Something failed");
 *
 * Toasts are accessible: the container is an aria-live region so screen readers
 * announce new messages, and each toast can be dismissed by keyboard.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const ToastContext = createContext(null);

let idSeq = 0;

function ToastItem({ toast, dismiss, duration = 4000 }) {
  const remaining = useRef(duration);
  const start = useRef(Date.now());
  const timer = useRef(null);

  const clean = () => {
    if (timer.current) clearTimeout(timer.current);
  };

  const initTimer = useCallback(() => {
    clean();
    timer.current = setTimeout(() => dismiss(toast.id), remaining.current);
    start.current = Date.now();
  }, [toast.id, dismiss]);

  useEffect(() => {
    initTimer();
    return clean;
  }, [initTimer]);

  const onEnter = () => {
    clean();
    remaining.current = Math.max(0, remaining.current - (Date.now() - start.current));
  };

  const onLeave = () => {
    if (remaining.current > 0) {
      initTimer();
    }
  };

  return (
    <div
      className={`um-toast um-toast-${toast.type}`}
      role="status"
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      <span className="um-toast-msg">{toast.message}</span>
      <button
        className="um-toast-close"
        onClick={() => dismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (type, message, duration = 4000) => {
      const id = ++idSeq;
      setToasts((list) => [...list, { id, type, message, duration }]);
      return id;
    },
    []
  );

  const api = useMemo(
    () => ({
      success: (m, d) => push("success", m, d),
      error: (m, d) => push("error", m, d),
      info: (m, d) => push("info", m, d),
      dismiss,
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="um-toast-region" role="region" aria-live="polite" aria-label="Notifications">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} dismiss={dismiss} duration={t.duration} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
