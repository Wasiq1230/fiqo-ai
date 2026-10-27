/**
 * App shell — auth gate, sidebar navigation (with mobile drawer), and routing
 * between the workspace, feedback, and admin screens.
 *
 * Auth state comes from AuthContext (real JWT-backed sessions). The Admin nav
 * item only renders for users whose role is "admin"; the backend enforces the
 * same rule, so hiding it here is purely cosmetic.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { useAuth } from "./context/AuthContext";
import { Ico, Icons, getInitials } from "./components/icons";
import AuthScreen from "./screens/AuthScreen";
import WorkspaceScreen from "./screens/WorkspaceScreen";

// Admin + Feedback are split into their own chunks — they aren't needed for the
// primary study workflow, so we don't pay for them on the initial load.
const FeedbackScreen = lazy(() => import("./screens/FeedbackScreen"));
const AdminScreen = lazy(() => import("./screens/AdminScreen"));

const WORKSPACE_SECTIONS = [
  { name: "Dashboard", icon: Icons.dashboard },
  { name: "Summary", icon: Icons.summary },
  { name: "Quiz", icon: Icons.quiz },
  { name: "Flashcards", icon: Icons.flashcard },
  { name: "Notes", icon: Icons.notes },
  { name: "Viva", icon: Icons.viva },
  { name: "Study Plan", icon: Icons.plan },
  { name: "Chat", icon: Icons.chat },
  { name: "Search", icon: Icons.search },
  { name: "History", icon: Icons.history },
];

const WORKSPACE_NAMES = WORKSPACE_SECTIONS.map((s) => s.name);

export default function App() {
  const { user, loading, logout } = useAuth();
  const [section, setSection] = useState("Dashboard");
  const [navOpen, setNavOpen] = useState(false);

  // While the mobile drawer is open: freeze the page behind it, and let Escape
  // close it. Without the freeze, a drag anywhere on the drawer scrolls the
  // feed underneath — the single thing that makes a slide-over feel broken.
  useEffect(() => {
    if (!navOpen) return undefined;
    document.body.classList.add("um-nav-locked");
    const onKey = (e) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.classList.remove("um-nav-locked");
      window.removeEventListener("keydown", onKey);
    };
  }, [navOpen]);

  if (loading) {
    return (
      <div className="um-auth-bg">
        <div className="um-loader um-loader-lg" role="status" aria-label="Loading" />
      </div>
    );
  }

  if (!user) return <AuthScreen />;

  const go = (name) => {
    setSection(name);
    setNavOpen(false);
  };

  const isAdmin = user.role === "admin";

  return (
    <div className="um-layout">
      {/* Mobile top bar */}
      <div className="um-mobile-topbar">
        <button className="um-hamburger" onClick={() => setNavOpen(true)} aria-label="Open navigation">
          <Ico path={Icons.menu} size={18} />
        </button>
        <span className="um-brand-text">FIQO<span>.</span></span>
      </div>

      {navOpen && (
        <div
          className="um-scrim"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar — a permanent rail on desktop, a slide-over drawer on phones */}
      <aside className={`um-sidebar${navOpen ? " um-sidebar-open" : ""}`}>
        <div className="um-sidebar-brand">
          <div className="um-brand-mark"><Ico path={Icons.sparkle} size={15} /></div>
          <span className="um-brand-text">FIQO<span>.</span></span>
        </div>

        <nav className="um-nav" aria-label="Main navigation">
          <p className="um-nav-label">Workspace</p>
          {WORKSPACE_SECTIONS.map((m) => (
            <button key={m.name} className={`um-nav-item${section === m.name ? " active" : ""}`} onClick={() => go(m.name)}>
              <Ico path={m.icon} size={15} /><span>{m.name}</span>
            </button>
          ))}

          <p className="um-nav-label" style={{ marginTop: 14 }}>Account</p>
          <button className={`um-nav-item${section === "Feedback" ? " active" : ""}`} onClick={() => go("Feedback")}>
            <Ico path={Icons.message} size={15} /><span>Feedback</span>
          </button>
          {isAdmin && (
            <button className={`um-nav-item${section === "Admin" ? " active" : ""}`} onClick={() => go("Admin")}>
              <Ico path={Icons.shield} size={15} /><span>Admin</span>
            </button>
          )}
        </nav>

        <div className="um-sidebar-footer">
          <div className="um-user-row">
            <div className="um-avatar">{getInitials(user.name)}</div>
            <div className="um-user-info">
              <p className="um-user-name">{user.name || "Student"}</p>
              <p className="um-user-plan">{isAdmin ? "Administrator" : "Student"}</p>
            </div>
            <button className="um-icon-btn" onClick={logout} title="Sign out" aria-label="Sign out">
              <Ico path={Icons.logout} size={14} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="um-main">
        {WORKSPACE_NAMES.includes(section) && (
          <WorkspaceScreen section={section} setSection={setSection} userName={user.name} />
        )}
        <Suspense fallback={<div className="um-feed"><div className="um-loader um-loader-lg" role="status" aria-label="Loading" /></div>}>
          {section === "Feedback" && <div className="um-feed"><FeedbackScreen /></div>}
          {section === "Admin" && isAdmin && <div className="um-feed"><AdminScreen /></div>}
        </Suspense>
      </main>
    </div>
  );
}
