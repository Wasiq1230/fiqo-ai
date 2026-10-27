# Hardening pass — what changed and why

This round of work assumed the app is about to face the open internet. Findings
are ordered by how much damage they could actually do, not by how easy they were
to fix.

The codebase was already in decent shape (CORS allowlist, bcrypt, rate limiting,
security headers, startup validation, no hard-coded key). What follows is what
was still left.

---

## Critical

### 1. Unmaintained cryptography dependencies

`python-jose` has had no release since 3.3.0 in 2021 and is flagged by
`pip-audit` and Dependabot (CVE-2024-33663, CVE-2024-33664). To be accurate:
neither CVE was directly exploitable here — this app uses HS256 with a symmetric
key and never touches JWE. But shipping an abandoned crypto library to
production means the next real vulnerability in it never gets patched.

`passlib` 1.7.4 (also 2020, also unmaintained) had a concrete bug: it reads
`bcrypt.__about__.__version__`, which bcrypt removed in 4.1. With the pinned
`bcrypt==4.2.1`, that pairing raises an internal error and logs a traceback on
every password hash.

**Fixed:** `python-jose` → `PyJWT`, `passlib` → the `bcrypt` library directly.
The stored hash format is unchanged (`$2b$...`), so existing accounts keep
working with no migration.

### 2. No way to revoke a session

Tokens were valid until expiry, full stop. Logging out cleared `localStorage`
and nothing else — the tokens themselves stayed valid for their remaining
lifetime, up to 7 days for a refresh token. There was no way to kill a stolen
session, and password changes did not invalidate old sessions.

**Fixed:** a `token_version` column on `users`, embedded in every token as a
`ver` claim and checked on each request. Bumping it invalidates every
outstanding token for that account instantly. It is bumped on logout, password
change, account deactivation, and via a new admin
`POST /api/admin/users/{id}/revoke-sessions` endpoint.

Also added: `/api/auth/logout`, `/api/auth/change-password`, and a `jti` claim
on every token for log correlation and future denylisting.

### 3. Rate limiting silently disabled behind a proxy

The limiter keyed on `request.client.host`. The moment the app sits behind
nginx, Cloudflare, Railway, Render or Fly — which it now does — that value is
the *proxy's* IP. Every visitor shares one bucket, which means per-IP limits
stop working entirely, and one abusive client locks out every legitimate user.

The naive fix (always trust `X-Forwarded-For`) is worse: on a directly-exposed
app, anyone can rotate that header per request and bypass rate limiting
completely.

**Fixed:** a `TRUST_PROXY` setting, defaulting to **false**. Only when it is
explicitly enabled does the limiter read `X-Forwarded-For`. The bundled compose
setup sets it to true because there the app genuinely is behind nginx.

---

## High

### 4. CSV formula injection in the admin export

Feedback is submitted by the public. A message beginning with `=`, `+`, `-` or
`@` is executed as a formula when Excel, LibreOffice or Google Sheets opens the
export — `=HYPERLINK(...)` to phish, or a DDE payload to run commands. The
attack path ran from an anonymous form straight to the admin's own machine.

**Fixed:** `_csv_safe()` prefixes such values with `'`, which renders them inert
while still displaying the original text. Regression test included.

### 5. No Host header allowlist

Nothing validated the `Host` header, leaving the app open to Host-header
injection and DNS rebinding.

**Fixed:** `TrustedHostMiddleware` as the outermost middleware, driven by a new
`ALLOWED_HOSTS` setting. Production refuses to start if it is still `*`.

### 6. Nginx would have rejected almost every upload

The backend accepts PDFs up to 15 MB. Nginx's default `client_max_body_size` is
**1 MB** and was never overridden, so in the Docker deployment every real
lecture PDF would have failed with a 413 before the request even reached the
backend. Its default 60-second read timeout would also have cut long AI
generations off with a 504.

**Fixed:** `client_max_body_size 55m`, proxy timeouts raised to 120s.

### 7. The API was published to the internet

`docker-compose.yml` exposed the backend on host port 8000 and Postgres was on
the same reachable footing, so both could be probed directly, bypassing nginx's
headers and limits.

**Fixed:** the API and database now have no host ports at all. Nginx
reverse-proxies `/api/` to the backend over a private network, so the whole app
is one origin. Side benefits: no cross-origin requests at all (no CORS surface),
and the CSP tightened from `connect-src 'self' https: http://localhost:*` to
`connect-src 'self'`.

---

## Medium

### 8. Denial-of-service surface

- **Failed logins were an amplifier.** For an unknown email the code computed a
  *fresh* bcrypt hash on every attempt purely for timing equalisation — double
  the CPU of a real login, and an attacker controls how often it runs. Now a
  single dummy hash is computed once at import and compared against.
- **PDF bombs.** A few hundred KB of PDF can declare tens of thousands of pages
  and pin a worker for minutes. Now capped by `MAX_PDF_PAGES` (default 500).
- **Multi-file uploads.** Per-file limits still allowed 10 × 15 MB in one
  request. Added `MAX_TOTAL_UPLOAD_MB` (default 50) across the whole request.
- **No AI timeout.** A hung Groq request held a worker open indefinitely; enough
  of those take the API down. Now `AI_TIMEOUT_SECONDS` (default 45) with bounded
  retries.
- Gunicorn gained `--max-requests` with jitter so a slow leak cannot accumulate
  across a worker's whole lifetime.

### 9. Validation errors echoed submitted values

The 422 handler returned `exc.errors()` verbatim, which includes the offending
input — so a bad registration could echo the submitted password back in the
response body and into logs.

**Fixed:** errors are reduced to field name plus message. Regression test
asserts the password never appears in the response.

### 10. Upgrading an existing database would have crashed

`create_all()` creates missing *tables*, never missing *columns*. Adding
`token_version` to an existing deployment would have produced "no such column"
on every query.

**Fixed:** `_apply_additive_columns()` in `database.py` detects and adds missing
additive columns on startup. For anything beyond that, use Alembic.

### 11. Worker startup races

`_seed_admin()` runs in every Gunicorn worker. With 4 workers on a fresh
database, all four could try to insert the same admin. Now the unique index is
treated as the real guard and `IntegrityError` is caught as the expected,
benign outcome of that race.

### 12. Liveness check that never checked anything

`/health` returned `ok` without touching the database, so an instance that was
up but could not serve a single request still reported healthy and kept
receiving traffic.

**Fixed:** `/health/ready` verifies the database connection and returns 503 when
it is down; Docker and compose healthchecks now use it. `/health` remains a
cheap liveness probe. Both are exempt from rate limiting so probes cannot eat a
user's budget.

---

## Low / correctness

- **`RATE_LIMIT_AI` did nothing.** The value was hard-coded in `pdf.py`, so
  changing the environment variable had no effect. Now read from settings.
- **Shadowed names in `admin.py`.** Query parameters named `type` and `status`
  shadowed the builtin and the imported FastAPI `status` module inside those
  functions — harmless today, a confusing bug the first time someone adds an
  `HTTPException` there. Renamed to `type_` / `status_` with `alias=` so the
  public API is unchanged.
- **Silent password truncation.** bcrypt hashes at most 72 bytes and ignores the
  rest, while the schema allowed 128 characters — so the tail of a long password
  quietly stopped mattering. Now rejected explicitly with a clear message.
- **Weak-password list.** `password123` passed the letters-and-digits rule.
  A small common-password blocklist now rejects the obvious ones.
- **Account enumeration.** The "account is disabled" check ran before the
  password check, distinguishing real-but-disabled emails from nonexistent ones.
  Reordered.
- Unused imports removed; `Cache-Control: no-store` added to API responses;
  `form-action 'none'` and `object-src 'none'` added to the CSPs;
  `server_tokens off` in nginx.
- Connection pooling configured (`pool_recycle`, `pool_size`) so idle Postgres
  connections dropped by a cloud provider don't surface as user-facing errors.
- Prompt-injection framing: PDF text is untrusted and can contain "ignore
  previous instructions". A system prompt now fences it as data. Prompting alone
  is not a real defence — what actually contains the risk is that the model has
  no tools, no data access and no privileges, so the worst case is a strange
  study summary.

---

## Second pass — found while re-checking the delivered code

### 13. Security headers were being dropped on the main HTML page

nginx does not merge `add_header` directives: declaring even one inside a
`location` block **discards every header inherited from `server`**. Both
`location = /index.html` and `location /assets/` set their own `Cache-Control`,
which silently stripped the CSP, `X-Frame-Options` and `nosniff` headers from
the HTML document itself and from every JS/CSS asset — exactly the responses
those headers are meant to protect. This was present in the original config too.

**Fixed:** headers moved to `frontend/security-headers.conf` and `include`d in
the server block *and* in each location that declares an `add_header`.

### 14. My own tightened CSP would have broken the site's fonts

Tightening `connect-src` to `'self'`, I also dropped the Google Fonts entries —
but `src/index.css` has an `@import` for Instrument Serif and DM Sans. The app
would have silently fallen back to system fonts.

**Fixed:** `fonts.googleapis.com` restored to `style-src`, `fonts.gstatic.com`
to `font-src`. Self-hosting those two families would let you drop both entries.

### 15. nginx could start before the API existed

nginx resolves the `backend` hostname when it loads its config. `depends_on`
with `condition: service_started` does not wait for the API to be usable.
Changed to `service_healthy`.

### 16. `ALLOWED_HOSTS` placeholder would have blocked the first test run

With the template's `your-domain.com` value, `docker compose up` followed by
visiting `localhost:8080` returns `400 Invalid host header` — a confusing
failure at exactly the wrong moment. The templates now ship with
`localhost,127.0.0.1` included, and `deploy.sh --check` warns when the
placeholder domain is still present.

### 17. Expired sessions fired a doomed request

The frontend called the new `/api/auth/logout` endpoint even when the session
was already known to be dead, guaranteeing a 401. Now clears tokens locally in
that path.

Also: `deploy.sh` now strips inline `# comments` when reading `.env` values, so
a file copied from `.env.example` is validated correctly.

### 18. My own test suite was blocked by my own middleware

Adding `TrustedHostMiddleware` broke every test. Starlette's `TestClient` sends
`Host: testserver`, which was not in `ALLOWED_HOSTS`, so all 39 tests were
rejected with `400 Invalid host header` before reaching a route. I wrote the
tests and the middleware in the same pass and could not execute either, so the
conflict only surfaced when the suite was actually run.

**Fixed:** `conftest.py` now sets its environment unconditionally rather than
with `setdefault`, so a test run is fully isolated from whatever is in the
developer's `.env` — including `ALLOWED_HOSTS`, which now contains
`testserver`. Admin seeding is also disabled during tests; it was costing a
bcrypt hash at cost 12 on every single test's startup.

**Worth stating plainly:** this is the third defect found only by executing the
code, after the Python 3.14 incompatibility and the nginx header inheritance
problem. Static analysis found real issues, but running the thing found a
different class of them.

### 19. The test suite ran against two different databases

`conftest.py` built a second SQLAlchemy engine (in-memory, `StaticPool`) and
pointed `get_db` at it, while the application kept its own. Two databases in one
process: fixtures created tables on one, and anything the app touched outside a
request — startup admin seeding, the `/health/ready` probe — used the other.
Whether a test saw its tables came down to fixture instantiation order, which
produced `no such table: users` in some tests and clean passes in others.

**Fixed:** one engine only — the application's own, pointed at a throwaway
SQLite *file* in a temp directory rather than `:memory:`, so every path sees the
same data. `client` now depends on the schema fixture explicitly instead of
relying on autouse ordering.

### 20. My password blocklist broke the existing fixtures

Adding `password123` to the common-password list rejected the fixtures' own
`Password123`, so every test needing a registered user failed at setup. Fixture
passwords moved to values that are not on the blocklist; the test that asserts
weak passwords *are* rejected still uses a blocklisted one deliberately.

---

## Repository hygiene

The uploaded zip contained **two full virtual environments**
(`backend/venv`, `backend/venv312`) — about 690 MB and roughly 13,000 files, of
which ~70 were actually yours. It also contained `backend/.env`.

That `.env` had no live secrets (a previous pass had already cleaned it), so
nothing leaked here — but shipping `.env` files around in archives is exactly
how keys escape. The delivered zip contains source only; `.gitignore` and both
`.dockerignore` files already exclude these, so this was a zipping artefact
rather than a repo problem.

Also removed: duplicate `tailwind.config.js` and `postcss.config.js` at the
project root (unused — the real ones are in `frontend/`).

---

## Known limitations — deliberately not fixed

Being straight with you about what is still true, so nothing here is a surprise
later:

1. **Tokens live in `localStorage`.** Readable by any JavaScript, so an XSS bug
   would expose them. HttpOnly refresh cookies would be stronger. The mitigation
   is that React escapes all output, `dangerouslySetInnerHTML` is never used,
   and the CSP is strict. The token lifetime (30 minutes) and revocation
   support limit the blast radius. Changing this means CSRF protection and a
   cookie-based flow — a real piece of work, worth doing if this grows.

2. **No Alembic migrations.** `create_all()` plus the additive-column patch
   covers this app's needs today. The first time you change a column *type* or
   rename one, you will need Alembic.

3. **Rate limits are per-process.** With 4 Gunicorn workers and in-memory
   counters, the effective limit is roughly 4× the configured value. Set
   `RATE_LIMIT_STORAGE_URI` to a Redis URL for a single shared limit. Fine as-is
   for expected traffic.

4. **No email verification and no password reset.** Anyone can register with an
   address they do not own, and a forgotten password needs admin help. Both need
   an email provider.

5. **No audit log.** Admin actions are logged to stdout, not stored queryably.

6. **Uploaded PDFs are processed in memory and never stored.** Good for privacy;
   it also means no re-processing without re-uploading.

7. **Dependency versions are pinned as of this pass.** Pins go stale. Run
   `pip-audit -r backend/requirements.txt` and `npm audit` monthly — a pinned
   version is only safe until the next advisory.

---

## Verification performed

- Every Python module compiles; all `app.*` imports resolve to real definitions.
- JWT layer tested directly against PyJWT: 7/7 — round-trip, refresh-as-access
  rejection, `alg=none` rejection, wrong-key rejection, expiry, required claims,
  over-length password rejection.
- CSV sanitiser tested against `=`, `+`, `-`, `@` and tab payloads.
- New `backend/tests/test_security.py` adds 14 regression tests covering
  revocation, token confusion, password policy, CSV injection, error leakage and
  the health probes.

Full-suite execution needs the dependencies installed, which this sandbox has no
network access to fetch. **Run `pytest` in `backend/` once before you deploy** —
that is the last check I could not run for you.
