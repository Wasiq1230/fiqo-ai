# FIQO AI — Production Readiness Audit

**Scope:** Full-stack audit and hardening of the FIQO AI codebase (FastAPI backend + React 19/Vite frontend) to bring it to enterprise-grade, deployment-ready standard.

**Format:** Every finding is reported as — *File affected · Issue found · Severity · Why it matters · Fix implemented · Testing performed.*

**Honesty note on testing:** The automated test suite and Docker/build configuration were **written but could not be executed in this environment** (the Linux sandbox reported "not enough disk space" so `pip`, `npm`, `pytest`, and `docker build` could not run). Every entry below marked "static verification" means the code was read and cross-checked by hand against callers/endpoints; entries marked "test written" mean an executable pytest exists but you must run it yourself. Exact commands are in the final section.

---

## Phase 1 & 2 — Audit + Security Hardening

### SEC-1 — Live secret committed to source
1. **File:** `backend` source / prior config
2. **Issue:** A real Groq API key (`gsk_…zul`) was hard-coded/committed.
3. **Severity:** Critical
4. **Why it matters:** Anyone with repo access (or git history) can spend against your Groq account; committed secrets are the single most common cause of production breaches.
5. **Fix:** All secrets moved to environment variables loaded via `pydantic-settings` (`config.py`). Nothing sensitive remains in source. `.env` is git-ignored; `.env.example` documents the keys with no values.
6. **Testing:** Static verification — grepped the tree for the key and for `gsk_`; none remain in tracked files. **Action required from you:** the exposed key must be **rotated** in the Groq console — removing it from the working tree does not undo the exposure in history.

### SEC-2 — Fail-fast configuration validation
1. **File:** `backend/app/config.py`
2. **Issue:** No guard against starting with an unsafe production config (missing secret, weak key, wildcard CORS, SQLite, debug on).
3. **Severity:** High
4. **Why it matters:** Misconfiguration in prod is silent and dangerous; a weak `SECRET_KEY` lets attackers forge JWTs.
5. **Fix:** `Settings.validate_runtime()` raises `RuntimeError` in production if `GROQ_API_KEY` is missing, `SECRET_KEY` < 32 chars, CORS contains `*`, `DEBUG=true`, or `DATABASE_URL` is SQLite. In development these downgrade to logged warnings.
6. **Testing:** Static verification of each branch; the dev-mode path is exercised by the test suite (conftest sets a long dummy secret so validation passes).

### SEC-3 — Password hashing & password policy
1. **File:** `backend/app/security.py`, `schemas.py`
2. **Issue:** Needed strong hashing and an enforced password policy.
3. **Severity:** High
4. **Why it matters:** Plaintext or weak hashing turns any DB leak into a full account compromise.
5. **Fix:** bcrypt via passlib; the hash is never serialized to the client (verified against the `UserOut` schema). Registration requires ≥ 8 chars with letters and digits, enforced server-side (Pydantic) and mirrored client-side in `AuthScreen.jsx`.
6. **Testing:** `test_auth.py::test_weak_password_rejected` (422) and `test_register_and_me` (asserts no `hashed_password`/`password` in the response body). Test written.

### SEC-4 — JWT access/refresh separation
1. **File:** `backend/app/security.py`, `routers/auth.py`, `dependencies.py`
2. **Issue:** Refresh and access tokens must not be interchangeable.
3. **Severity:** High
4. **Why it matters:** If an access token could be used to refresh (or vice-versa), token lifetimes become meaningless.
5. **Fix:** Tokens carry a `type` claim validated on use; `/api/auth/refresh` rejects a token that isn't a refresh token. Lifetimes are env-configurable (`ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`).
6. **Testing:** `test_auth.py::test_login_and_refresh` and `test_refresh_rejects_garbage` (401). Test written.

### SEC-5 — RBAC on admin endpoints
1. **File:** `backend/app/dependencies.py`, `routers/admin.py`
2. **Issue:** Admin capability must be enforced server-side, not by hiding UI.
3. **Severity:** Critical
4. **Why it matters:** Client-side nav hiding is cosmetic; a normal user can call the API directly.
5. **Fix:** Every `/api/admin/*` route depends on `require_admin`, which checks `UserRole.admin` on the authenticated user.
6. **Testing:** `test_auth.py::test_admin_route_forbidden_for_normal_user` (403). Test written.

### SEC-6 — SQL injection surface (admin free-text search)
1. **File:** `backend/app/routers/admin.py`
2. **Issue:** Free-text feedback search is the highest-risk injection point.
3. **Severity:** High
4. **Why it matters:** String-interpolated SQL would allow data exfiltration or table drops.
5. **Fix:** All queries use SQLAlchemy's bound-parameter expression API (`.filter(...ilike(f"%{q}%"))` binds `q` as a parameter — no string interpolation into SQL).
6. **Testing:** `test_admin.py::test_search_is_injection_safe` submits `'; DROP TABLE feedback;--`, asserts it's treated as a literal (0 results) and the table still works afterward. Test written.

### SEC-7 — Security headers on every response
1. **File:** `backend/app/main.py` (`SecurityHeadersMiddleware`), `frontend/nginx.conf`
2. **Issue:** Missing browser-hardening headers.
3. **Severity:** Medium
4. **Why it matters:** Defends against clickjacking, MIME sniffing, referrer leakage, and downgrade attacks.
5. **Fix:** API sets `Content-Security-Policy` (strict `default-src 'none'` — safe for a JSON API), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, COOP/CORP, and `Strict-Transport-Security` (production only, over HTTPS). The nginx frontend sets its own CSP + headers for the HTML/JS bundle.
6. **Testing:** `test_auth.py::test_security_headers_present`. Test written.

### SEC-8 — CORS locked to an allowlist
1. **File:** `backend/app/main.py`, `config.py`
2. **Issue:** Wildcard CORS with credentials is unsafe.
3. **Severity:** High
4. **Why it matters:** `*` + credentials would let any origin make authenticated calls.
5. **Fix:** Explicit `cors_origin_list` from env; production validation forbids `*`; methods/headers restricted to what the app uses.
6. **Testing:** Static verification against `create_app()`.

### SEC-9 — Rate limiting
1. **File:** `backend/app/rate_limit.py`, `main.py`, routers
2. **Issue:** Auth/AI/feedback endpoints are abuse-prone (credential stuffing, cost-draining AI spam).
3. **Severity:** Medium
4. **Why it matters:** Without limits, brute-force and denial-of-wallet are trivial.
5. **Fix:** SlowAPI per-IP limits, separately tunable (`RATE_LIMIT_AUTH/AI/FEEDBACK/DEFAULT`).
6. **Testing:** Limiter disabled in tests (process-wide singleton would cause false 429s); limits verified statically.

### SEC-10 — Error handling never leaks internals
1. **File:** `backend/app/main.py`
2. **Issue:** Unhandled exceptions can leak stack traces / internal detail.
3. **Severity:** Medium
4. **Why it matters:** Traces reveal file paths, library versions, and logic useful to attackers.
5. **Fix:** Global handler logs the real error server-side and returns a generic `{"detail": "An internal server error occurred."}` with 500; validation errors return field info without internals.
6. **Testing:** Static verification of all three handlers.

### SEC-11 — Upload safety
1. **File:** `backend/app/routers/pdf.py`, `services/pdf_service.py`, `config.py`
2. **Issue:** Uploads must be bounded and validated.
3. **Severity:** Medium
4. **Why it matters:** Unbounded uploads and encrypted/malformed PDFs cause DoS or 500s.
5. **Fix:** Type, size (`MAX_UPLOAD_MB`), file-count, and encryption checks; unauthenticated upload rejected before any processing.
6. **Testing:** `test_pdf.py::test_pdf_requires_auth` (401/403) and `test_pdf_rejects_missing_file_when_authenticated` (422, not 500). Test written.

### SEC-12 — Spam protection on feedback
1. **File:** `backend/app/schemas.py`, `frontend/src/screens/FeedbackScreen.jsx`
2. **Issue:** Public feedback form invites bot spam.
3. **Severity:** Low
4. **Why it matters:** Spam pollutes the admin queue and can be an injection vector.
5. **Fix:** Hidden honeypot field `website` (`max_length=0`) + rate limiting. Bots that fill it are rejected.
6. **Testing:** `test_feedback.py::test_honeypot_blocks_spam`. Test written.

---

## Phase 3 — Performance

### PERF-1 — Frontend code splitting
1. **File:** `frontend/src/App.jsx`, `vite.config.js`
2. **Issue:** Monolithic bundle; admin/feedback code shipped to every user.
3. **Severity:** Medium
4. **Why it matters:** Larger initial bundle = slower first paint, worse Lighthouse.
5. **Fix:** `React.lazy` + `Suspense` for Admin and Feedback screens; Rollup `manualChunks` split React and the PDF library into separate vendor chunks; `chunkSizeWarningLimit` tuned.
6. **Testing:** Static verification (`build` not runnable here — run `npm run build` to confirm chunking).

### PERF-2 — Dependency pruning
1. **File:** `frontend/package.json`
2. **Issue:** Many unused packages (radix, framer-motion, lucide, confetti, clsx, tailwind-merge, etc.).
3. **Severity:** Medium
4. **Why it matters:** Dead deps bloat install time, bundle size, and attack surface.
5. **Fix:** Removed all packages with zero imports (verified by grep); kept only `axios`, `jspdf`, `react`, `react-dom`.
6. **Testing:** Grep confirmed no import references remain. Run `npm install && npm run build` to confirm.

### PERF-3 — Backend compression & response size
1. **File:** `backend/app/main.py`, `frontend/nginx.conf`
2. **Issue:** Large AI/JSON payloads sent uncompressed.
3. **Severity:** Low
4. **Why it matters:** Wastes bandwidth and slows large summaries/exports.
5. **Fix:** GZip middleware (min 1KB) on the API; gzip in nginx for static assets, with long-cache headers on hashed assets and no-cache on `index.html`.
6. **Testing:** Static verification.

---

## Phases 4–6 — Bugs, Feature Completion, UX

### BUG-1 — Mobile sidebar disappeared with no replacement
1. **File:** `frontend/src/index.css`, `App.jsx`
2. **Issue:** The 768px media query set the sidebar to `display:none` with no alternative nav.
3. **Severity:** High
4. **Why it matters:** The app was effectively unusable on phones — no navigation at all.
5. **Fix:** Added a mobile topbar with a hamburger button, a slide-in drawer (`um-sidebar-open`), and a scrim overlay; nav closes on selection.
6. **Testing:** Static/visual verification of CSS + JSX. Manual device testing recommended.

### BUG-2 — Insecure localStorage plaintext-password "auth"
1. **File:** `frontend/src/context/AuthContext.jsx`, `lib/`
2. **Issue:** Prior auth stored credentials/plaintext in localStorage.
3. **Severity:** Critical
4. **Why it matters:** Anyone with device/XSS access reads passwords; no real server auth.
5. **Fix:** Replaced with real JWT auth via `AuthContext`; axios interceptor does single-flight refresh-and-retry on 401; a `FiQO:logout` window event coordinates logout across the app. localStorage token storage tradeoff (vs XSS) is documented.
6. **Testing:** Static verification against backend auth endpoints; backend flows covered by `test_auth.py`.

### FEAT-1 — Feedback & support system (Phase 7)
1. **File:** `frontend/src/screens/FeedbackScreen.jsx`, `backend/routers/feedback.py`, `schemas.py`, `models.py`
2. **Issue:** No feedback/support capability existed.
3. **Severity:** Medium (required feature)
4. **Why it matters:** Users need a channel; the business needs bug/complaint tracking.
5. **Fix:** Five types (feedback/bug/complaint/feature/support) persisted to the DB; validated inputs; success confirmation; honeypot spam guard; name/email prefilled for logged-in users. `/api/feedback` + `/api/feedback/mine`.
6. **Testing:** `test_feedback.py` covers submission, all types, invalid email, short message, auth-required `/mine`. Test written.

### FEAT-2 — Admin dashboard (Phase 8)
1. **File:** `frontend/src/screens/AdminScreen.jsx`, `backend/routers/admin.py`
2. **Issue:** No admin management/analytics.
3. **Severity:** Medium (required feature)
4. **Why it matters:** Operators must triage feedback, manage users, and export data.
5. **Fix:** Tabs for overview/feedback/users; analytics; filter by type/status + free-text search; resolve/close/start status changes; activate/deactivate users (with a self-deactivation guard); authenticated CSV export via blob download.
6. **Testing:** `test_admin.py` covers analytics shape, list/filter/search, resolve (`resolved_at` set), CSV export (`text/csv`), and self-deactivation block (400). Test written.

### UX-1 — Loading / skeleton / empty / error states + a11y
1. **File:** `frontend/src/components/Output.jsx`, `Toast`, `ErrorBoundary`, `index.css`
2. **Issue:** Missing feedback states; `alert()` used for errors; limited accessibility.
3. **Severity:** Medium
4. **Why it matters:** Users need to know what's happening; a11y is table-stakes and often a legal requirement.
5. **Fix:** Skeleton shimmer loaders, empty states, a toast system (success/error/info) replacing `alert()`, an ErrorBoundary fallback, `:focus-visible` rings, `aria-hidden` on decorative icons, `role="dialog"`/`aria-modal` on modals, and `prefers-reduced-motion` support.
6. **Testing:** Static/visual verification.

---

## Phases 9–10 — Code Quality & Deployment Readiness

### QUAL-1 — Monolith broken into modules
1. **File:** `frontend/src/` (was a 1357-line `App.jsx`)
2. **Issue:** One giant component; hard to maintain.
3. **Severity:** Medium
4. **Why it matters:** Maintainability/scalability; large files hurt review and reuse.
5. **Fix:** Split into `icons.jsx`, `context/AuthContext.jsx`, `components/Output.jsx`, and `screens/` (Auth/Workspace/Feedback/Admin) behind a slim App shell.
6. **Testing:** Static verification that imports resolve and no dead code remains.

### DEP-1 — Deprecated startup hook
1. **File:** `backend/app/main.py`
2. **Issue:** `@app.on_event("startup")` is deprecated in modern FastAPI.
3. **Severity:** Low
4. **Why it matters:** Emits warnings and will eventually break.
5. **Fix:** Migrated to an `asynccontextmanager` `lifespan` handler (config warnings → `init_db()` → `_seed_admin()` → logs).
6. **Testing:** Static verification; startup path exercised by every test via `TestClient(app)`.

### DEP-2 — Containerization & compose
1. **File:** `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `.dockerignore`s
2. **Issue:** No reproducible production build/run.
3. **Severity:** Medium
4. **Why it matters:** Deployment must be repeatable and least-privilege.
5. **Fix:** Backend image runs gunicorn+uvicorn as a **non-root** user (uid 10001) with a container `HEALTHCHECK`; frontend is a multi-stage build (node build → nginx serve); compose wires Postgres + backend + frontend with a DB healthcheck and a `pgdata` volume.
6. **Testing:** Static verification (`docker build` not runnable here — run `docker compose up -d --build`).

### DEP-3 — SEO / PWA / crawler assets & health check
1. **File:** `frontend/index.html`, `public/site.webmanifest`, `robots.txt`, `sitemap.xml`; backend `/health`
2. **Issue:** Missing metadata, manifest, crawler files, and a probe endpoint.
3. **Severity:** Low
4. **Why it matters:** SEO, installability, and load-balancer/uptime health checks.
5. **Fix:** Full meta (title/description/OG/twitter/canonical/theme-color), favicon/apple-touch/manifest links, `noscript`, a PWA manifest, `robots.txt` (disallows `/api/`), `sitemap.xml`, and `GET /health` returning `{"status":"ok",...}`.
6. **Testing:** Static verification.

### DEP-4 — Documentation
1. **File:** `README.md` (root)
2. **Issue:** No run/deploy documentation.
3. **Severity:** Low
4. **Why it matters:** Onboarding and correct deployment depend on it.
5. **Fix:** README covering architecture, local dev (backend + frontend), env-var reference, running tests, Docker Compose and separate-service deploys, health checks, migrations (Alembic guidance), backups, security notes, and project layout.
6. **Testing:** Static verification.

---

## Phase 11 — Testing (written; not executed here)

A hermetic pytest suite runs against in-memory SQLite (StaticPool, schema recreated per test, rate limiter disabled), with no external services or real secrets:

- `test_auth.py` — health, security headers, register/me (no password leak), duplicate email (409), weak password (422), wrong password (401), login+refresh, garbage refresh (401), `/me` requires auth (401), admin route forbidden for normal user (403).
- `test_feedback.py` — anonymous submit (201), all types, honeypot blocks spam, invalid email (422), short message (422), `/mine` requires auth (401).
- `test_admin.py` — analytics shape, list/filter/search, resolve (`resolved_at` set), CSV export (`text/csv`), self-deactivation blocked (400), SQL-injection-safe search.
- `test_pdf.py` — auth required, missing file → 422 (not 500).

---

## Phase 12 — Final checklist status

| Item | Status |
|---|---|
| Secrets removed from source | ✅ (rotate the exposed key) |
| RBAC enforced server-side | ✅ |
| Injection-safe queries | ✅ |
| Security headers + HSTS/CSP | ✅ |
| CORS allowlist, no `*` in prod | ✅ |
| Rate limiting | ✅ |
| No leaked stack traces | ✅ |
| Feedback + admin features complete | ✅ |
| Loading/empty/error states + a11y | ✅ |
| Code split + deps pruned | ✅ |
| Docker/compose + health checks | ✅ |
| SEO/PWA/robots/sitemap | ✅ |
| README | ✅ |
| Test suite | ✅ written — **run locally to confirm green** |
| Build passes | ⏳ **run `npm run build` / `docker build` to confirm** |

---

## What you must run (couldn't be executed in this environment)

```bash
# Backend tests
cd backend && pip install -r requirements.txt && pytest

# Frontend build (confirms deps + code splitting)
cd frontend && npm install && npm run build

# Full stack via Docker
export POSTGRES_PASSWORD=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
export VITE_API_URL=https://api.your-domain.com
docker compose up -d --build
```

**Before going live:** rotate the exposed Groq API key in the Groq console, set a strong `SECRET_KEY` (≥ 32 random chars), point `DATABASE_URL` at managed Postgres, set `ENVIRONMENT=production`, and put HTTPS termination in front.
