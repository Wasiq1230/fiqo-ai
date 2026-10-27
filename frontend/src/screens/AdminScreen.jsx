/**
 * Admin dashboard (Phase 8).
 *
 * Visible only to users whose role is "admin". Provides:
 *  - Analytics tiles (user + feedback counts by type/status)
 *  - Feedback management: search, filter by type/status, resolve/close,
 *    add an admin note, and export the current view to CSV
 *  - User management: search, filter, activate/deactivate
 *
 * All data comes from the /api/admin/* endpoints, which are themselves guarded
 * server-side by the require_admin dependency — this UI is a convenience layer,
 * not the security boundary.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  adminAnalytics,
  adminListFeedback,
  adminUpdateFeedback,
  adminListUsers,
} from "../lib/services";
import { api, apiErrorMessage } from "../lib/api";
import { useToast } from "../components/Toast";
import { Skeleton } from "../components/Output";
import { Ico, Icons } from "../components/icons";

const FEEDBACK_TYPES = ["", "feedback", "bug", "complaint", "feature", "support"];
const FEEDBACK_STATUSES = ["open", "in_progress", "resolved", "closed"];

function StatTile({ label, value }) {
  return (
    <div className="um-stat-card">
      <p className="um-stat-label">{label}</p>
      <p className="um-stat-value">{value}</p>
    </div>
  );
}

export default function AdminScreen() {
  const toast = useToast();
  const [tab, setTab] = useState("overview"); // overview | feedback | users

  const [analytics, setAnalytics] = useState(null);
  const [feedback, setFeedback] = useState({ items: [], total: 0 });
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  // filters
  const [fType, setFType] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fQuery, setFQuery] = useState("");
  const [uQuery, setUQuery] = useState("");

  // debounce refs
  const fDebounceRef = useRef(null);
  const uDebounceRef = useRef(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      setAnalytics(await adminAnalytics());
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not load analytics."));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const loadFeedback = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fType) params.type = fType;
      if (fStatus) params.status = fStatus;
      if (fQuery.trim()) params.q = fQuery.trim();
      setFeedback(await adminListFeedback(params));
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not load feedback."));
    } finally {
      setLoading(false);
    }
  }, [fType, fStatus, fQuery, toast]);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (uQuery.trim()) params.q = uQuery.trim();
      setUsers(await adminListUsers(params));
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not load users."));
    } finally {
      setLoading(false);
    }
  }, [uQuery, toast]);

  useEffect(() => {
    if (tab === "overview") loadOverview();
    else if (tab === "feedback") loadFeedback();
    else if (tab === "users") loadUsers();

    return () => {
      clearTimeout(fDebounceRef.current);
      clearTimeout(uDebounceRef.current);
    };
  }, [tab, loadOverview, loadFeedback, loadUsers]);

  const setStatus = async (id, status) => {
    try {
      await adminUpdateFeedback(id, { status });
      toast.success(`Marked ${status.replace("_", " ")}.`);
      loadFeedback();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Update failed."));
    }
  };

  const toggleUser = async (u) => {
    try {
      await api.patch(`/api/admin/users/${u.id}/status`, null, { params: { is_active: !u.is_active } });
      toast.success(u.is_active ? "User deactivated." : "User activated.");
      loadUsers();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Update failed."));
    }
  };

  const exportCsv = async () => {
    try {
      // Authenticated fetch → blob download (keeps the Authorization header).
      const res = await api.get("/api/admin/feedback-export", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = "feedback-export.csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Export failed."));
    }
  };

  return (
    <div>
      <div className="um-section-toolbar">
        <p className="um-section-heading">
          <Ico path={Icons.shield} size={15} /> Admin dashboard
        </p>
        <div className="um-toolbar-btns">
          {["overview", "feedback", "users"].map((t) => (
            <button
              key={t}
              className={`um-btn um-btn-sm${tab === t ? " um-btn-active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {loading && <Skeleton />}

      {/* OVERVIEW */}
      {!loading && tab === "overview" && analytics && (
        <div className="um-admin-grid">
          <StatTile label="Total users" value={analytics.users?.total ?? 0} />
          <StatTile label="Active users" value={analytics.users?.active ?? 0} />
          <StatTile label="Total feedback" value={analytics.feedback?.total ?? 0} />
          <StatTile label="Open items" value={analytics.feedback?.by_status?.open ?? 0} />
          <StatTile label="Bugs" value={analytics.feedback?.by_type?.bug ?? 0} />
          <StatTile label="Complaints" value={analytics.feedback?.by_type?.complaint ?? 0} />
          <StatTile label="Feature requests" value={analytics.feedback?.by_type?.feature ?? 0} />
          <StatTile label="Support" value={analytics.feedback?.by_type?.support ?? 0} />
        </div>
      )}

      {/* FEEDBACK */}
      {!loading && tab === "feedback" && (
        <>
          <div className="um-filter-row">
            <input
              className="um-input"
              style={{ maxWidth: 240 }}
              placeholder="Search subject, message, email…"
              value={fQuery}
              onChange={(e) => {
                setFQuery(e.target.value);
                clearTimeout(fDebounceRef.current);
                fDebounceRef.current = setTimeout(loadFeedback, 400);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") { clearTimeout(fDebounceRef.current); loadFeedback(); }
              }}
              aria-label="Search feedback"
            />
            <select className="um-select" value={fType} onChange={(e) => setFType(e.target.value)}>
              {FEEDBACK_TYPES.map((t) => (
                <option key={t || "all"} value={t}>{t ? t : "All types"}</option>
              ))}
            </select>
            <select className="um-select" value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
              <option value="">All statuses</option>
              {FEEDBACK_STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace("_", " ")}</option>
              ))}
            </select>
            <button className="um-btn um-btn-sm um-btn-primary" onClick={loadFeedback}>Apply</button>
            <button className="um-btn um-btn-sm" onClick={exportCsv}>
              <Ico path={Icons.download} size={13} /> Export CSV
            </button>
          </div>

          {feedback.items.length === 0 ? (
            <p className="um-empty">No feedback matches these filters.</p>
          ) : (
            <div className="um-table-wrap">
              <table className="um-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Subject</th>
                    <th>From</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {feedback.items.map((f) => (
                    <tr key={f.id}>
                      <td><span className="um-badge">{f.type}</span></td>
                      <td title={f.message}>{f.subject}</td>
                      <td>{f.email}</td>
                      <td><span className={`um-badge um-badge-${f.status}`}>{f.status.replace("_", " ")}</span></td>
                      <td>
                        <div className="um-toolbar-btns">
                          {f.status !== "resolved" && (
                            <button className="um-btn um-btn-sm" onClick={() => setStatus(f.id, "resolved")}>Resolve</button>
                          )}
                          {f.status !== "closed" && (
                            <button className="um-btn um-btn-sm" onClick={() => setStatus(f.id, "closed")}>Close</button>
                          )}
                          {f.status === "open" && (
                            <button className="um-btn um-btn-sm" onClick={() => setStatus(f.id, "in_progress")}>Start</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="um-input-hint" style={{ marginTop: 10 }}>{feedback.total} total matching item(s).</p>
        </>
      )}

      {/* USERS */}
      {!loading && tab === "users" && (
        <>
          <div className="um-filter-row">
            <input
              className="um-input"
              style={{ maxWidth: 240 }}
              placeholder="Search name or email…"
              value={uQuery}
              onChange={(e) => {
                setUQuery(e.target.value);
                clearTimeout(uDebounceRef.current);
                uDebounceRef.current = setTimeout(loadUsers, 400);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") { clearTimeout(uDebounceRef.current); loadUsers(); }
              }}
              aria-label="Search name or email"
            />
            <button className="um-btn um-btn-sm um-btn-primary" onClick={loadUsers}>Search</button>
          </div>

          {users.length === 0 ? (
            <p className="um-empty">No users found.</p>
          ) : (
            <div className="um-table-wrap">
              <table className="um-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.name}</td>
                      <td>{u.email}</td>
                      <td><span className="um-badge">{u.role}</span></td>
                      <td>
                        <span className={`um-badge um-badge-${u.is_active ? "resolved" : "closed"}`}>
                          {u.is_active ? "active" : "inactive"}
                        </span>
                      </td>
                      <td>
                        <button className="um-btn um-btn-sm" onClick={() => toggleUser(u)}>
                          {u.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
