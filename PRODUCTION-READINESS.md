# Production readiness — audited against the 12-phase checklist

Verdict per phase, with what is done, what is genuinely required before you
deploy, and what I could not verify. Nothing here is marked complete unless I
checked it in the code.

---

## Summary

| | |
|---|---|
| **Blocks deployment** | 3 items — all require you, not code |
| **Should do in week one** | 5 items |
| **Genuinely not applicable** | 6 items — reasons given, not excuses |
| **Cannot be verified from here** | 4 items — no browser, no network in my environment |

The application code is production-ready. The operational and legal scaffolding
around it is not complete, which is normal for a solo project — but you should
choose that knowingly rather than discover it later.

---

## Phase 1 — Full audit

| Checked | Finding |
|---|---|
| Dead code, TODOs, placeholders | None found |
| Duplicate code | Two stray root configs removed (`tailwind.config.js`, `postcss.config.js`) |
| Unused packages | None — every dependency is imported somewhere |
| `console.log` debug leftovers | None. Three `console.error` calls remain; all are legitimate error paths |
| Race conditions | Two fixed: admin seeding across Gunicorn workers, duplicate registration |
| Memory leaks | Event listener in `AuthContext` is cleaned up correctly |
| Loading / error states | Present on all four screens (`WorkspaceScreen` has 40 references) |
| Error handling | `try`/`catch` + `apiErrorMessage` throughout; `ErrorBoundary` with real fallback UI |
| Validation | Pydantic on every endpoint; client-side on every form |

## Phase 2 — Security

Done and verified: bcrypt cost 12, JWT with pinned algorithm + required claims +
type-confusion protection + revocation, RBAC, rate limiting, SQL injection
(bound parameters), XSS (no `dangerouslySetInnerHTML`, no `eval`), path
traversal (uploads never touch disk), CSV injection, request size limits, CORS
allowlist, Host allowlist, CSP/HSTS/nosniff/frame-options/referrer/permissions,
secrets in environment only, no stack traces to clients, sanitised validation
errors.

**Not applicable, with reasons:**

- **CSRF** — the API authenticates via `Authorization: Bearer`, not cookies.
  CSRF requires the browser to attach credentials automatically; it does not do
  that for a header your JavaScript sets. If you ever move to cookie auth, CSRF
  protection becomes mandatory.
- **Cookie security (HttpOnly/Secure/SameSite)** — the app sets no cookies.
- **NoSQL / command injection** — no NoSQL database, no shell execution.
- **SSRF** — the backend makes exactly one outbound call, to a hardcoded Groq
  endpoint. No user-supplied URL is ever fetched.

**Genuinely missing:**

- **Account lockout** — 10 attempts/minute/IP slows brute force but does not
  stop a slow distributed one. Add lockout after N failures per account.
- **Password reset / email verification** — both need an email provider.
- **MFA** — not started. The `token_version` field gives you a clean place to
  force re-authentication when you add it.

## Phase 3 — Performance

Already in place: route-level code splitting (`React.lazy` on Feedback and Admin
screens), vendor chunk separation, gzip, immutable caching on hashed assets,
no-cache on `index.html`, GZip middleware on the API, connection pooling, DB
indexes on every filtered column, async I/O for uploads.

**Not measured.** I cannot run Lighthouse or a browser. Bundle size, Core Web
Vitals and real API latency are unverified. Run Lighthouse in Chrome DevTools
once it is live — five minutes, and it will tell you more than I can.

## Phase 4 & 5 — Bugs and incomplete features

No unfinished logic, no placeholder data, no dead buttons found by inspection.
Every endpoint in `services.js` maps to a real backend route.

**But:** I have never executed this application. "No console errors, no runtime
errors, every button works" is a claim only running it can support. That is what
`pytest` and ten minutes of clicking are for.

## Phase 6 — UX and accessibility

Present: loading and error states, toast notifications, empty states, responsive
media queries, `aria-label` on inputs, semantic tables, keyboard-focusable
controls.

**Unverified:** real screen-reader behaviour, colour contrast ratios, focus
order, mobile layout on actual devices. Accessibility cannot be audited by
grepping — it needs axe DevTools and a keyboard. `AdminScreen` is the most
likely weak spot: large tables with action buttons.

## Phase 7 — Feedback system

Complete. Five submission types, honeypot + rate limiting against spam, works
signed-in or anonymous, immediate confirmation, admin can list/search/filter/
paginate/resolve/annotate/delete/export.

## Phase 8 — Admin

Complete for users, feedback, analytics, search, filter, CSV export.

**Missing:** a persistent audit log. Admin actions are logged to stdout, not
stored queryably, so "who deactivated this account and when" is unanswerable
after log rotation.

## Phase 9 — Code quality

Layered structure (`routers` / `services` / `models` / `schemas`), consistent
naming, docstrings explaining *why* not just *what*, no duplicated logic.

## Phase 10 — Deployment readiness

| Item | Status |
|---|---|
| Environment variables | Documented, validated at startup, refuses unsafe production config |
| Production build | Multi-stage Docker, non-root, OS packages patched |
| HTTPS | **You must add this** — DEPLOYMENT.md §4 |
| Database migration | `create_all` + additive-column patching. No Alembic |
| Backups | **Not set up** — see below |
| Error logging | To stdout. No aggregation, no error tracker |
| Monitoring | **None** |
| Health checks | Liveness + readiness, wired into Docker and compose |
| 404 / 403 / 500 pages | **N/A** — no client-side router, so there are no URLs to 404 on. Every path loads the app; API errors surface as toasts. A 404 page here would be decoration |
| SEO metadata | Fixed this pass — see below |
| robots.txt / sitemap.xml | Fixed this pass — now generated from `SITE_URL` |
| favicon / manifest | Present. **PWA install will not be offered** — the manifest references only an SVG; Chrome and Android require 192×192 and 512×512 PNG icons |

### Fixed this pass: placeholder domain in SEO tags

`index.html`, `robots.txt` and `sitemap.xml` all hard-coded
`https://your-domain.com`. This is not cosmetic — a `<link rel="canonical">`
tells search engines the authoritative copy of your page lives at that URL. You
would have been telling Google that the real FIQO AI is on a domain you do
not own, and handing it your sitemap too. The likely outcome is not getting
indexed at all.

Now: set `SITE_URL` once in the root `.env`. The canonical tag, `og:url`,
`robots.txt` and `sitemap.xml` are all generated from it at build time.

## Phase 11 — Testing

| Type | Status |
|---|---|
| Backend unit/integration | 5 test files, ~50 tests including 14 new security regression tests |
| Test execution | **Never run.** My sandbox has no network to install FastAPI |
| Frontend tests | **None exist** — no Vitest, no Testing Library |
| E2E | **None** |
| Cross-browser / mobile / responsive | **Cannot test** — no browser available to me |
| Load testing | **Not done** — you do not know what breaks first under concurrency |

## Phase 12 — Final checklist

Honestly marked:

- ✅ No build errors (Python compiles, all imports resolve, JS syntax valid)
- ✅ No broken API calls (every frontend call maps to a real route)
- ✅ No missing validations
- ✅ No known security vulnerabilities
- ✅ No placeholder data, dead code, duplicate code, unfinished modules
- ⬜ No console errors — **requires running it**
- ⬜ No runtime errors — **requires running it**
- ⬜ No slow pages — **requires measuring**
- ⬜ No accessibility issues — **requires an audit tool**
- ⬜ Fully responsive — **requires real devices**

---

## Required before you deploy

1. **`cd backend && pytest`** — the suite has never executed
2. **Rotate the Groq API key** — console.groq.com/keys
3. **HTTPS in front of port 8080** — without it, passwords cross the network in plaintext

## Week one

4. **Database backups** — `docker compose down -v` currently deletes every account, permanently
5. **Uptime monitoring** on `/healthz`
6. **Error tracking** — `ErrorBoundary.jsx` already marks the spot
7. **Check git history for the old key** — `git log -S "gsk_"`. Deleting a file does not remove it from history
8. **Account deletion** — users cannot delete their own account or data. If anyone outside Pakistan uses this, that is a legal obligation

## Before public launch

9. Privacy policy and terms — you store names, emails, and process uploads
10. Password reset and email verification
11. PNG icons (192/512) if you want PWA install
12. Run Lighthouse and axe DevTools once

---

## What I could not do, stated plainly

No browser and no network access in my environment. So: the test suite is
unexecuted, no page has been rendered, no bundle measured, no accessibility
tool run, no dependency audit performed against a live advisory database.

Everything I claim as verified, I verified by reading and analysing the code.
Everything above marked ⬜ or "cannot test" needs you or a CI runner. A checklist
that marks those green without running anything is worth less than an honest
one that leaves them open.
