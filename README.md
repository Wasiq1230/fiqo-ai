# FIQO AI

> **What's left before deploying?** [PRODUCTION-READINESS.md](PRODUCTION-READINESS.md)
> — phase-by-phase verdict, including what has *not* been verified.
>
> **Deploying?** Start with [DEPLOYMENT.md](DEPLOYMENT.md) — step by step, no
> prior experience assumed. [SECURITY-FIXES.md](SECURITY-FIXES.md) records what
> was hardened in the latest pass, and the known limitations.
>
> **Before you deploy: rotate your Groq API key.** See DEPLOYMENT.md section 0.


An AI-powered study workspace. Upload course PDFs and generate summaries,
quizzes (including scored, auto-graded quizzes), flashcards, viva questions,
study plans, and structured notes — plus chat and keyword search over one or
many documents. Includes a full feedback/support system and an admin dashboard.

- **Backend:** FastAPI (Python), SQLAlchemy 2.0, JWT auth, SlowAPI rate
  limiting, Groq LLM API.
- **Frontend:** React 19 + Vite, axios, a light custom design system.

---

## Table of contents

1. [Architecture](#architecture)
2. [Local development](#local-development)
3. [Environment variables](#environment-variables)
4. [Running the tests](#running-the-tests)
5. [Production deployment](#production-deployment)
6. [Security notes](#security-notes)
7. [Project layout](#project-layout)

---

## Architecture

```
Browser ──HTTPS──> Frontend (nginx static bundle)
                        │  XHR/fetch (VITE_API_URL)
                        ▼
                   Backend (FastAPI / gunicorn+uvicorn)
                        │
                        ▼
                   PostgreSQL          Groq LLM API
```

The frontend is a pure SPA that talks to the backend over a token-based API.
Access + refresh JWTs are issued on login; the axios client transparently
refreshes an expired access token once and retries the request.

---

## Local development

### Prerequisites

- Python 3.12+
- Node.js 20+
- A Groq API key (https://console.groq.com)

### Backend

```bash
cd backend
python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then edit .env and set GROQ_API_KEY + SECRET_KEY
uvicorn app.main:app --reload
```

The API runs at http://127.0.0.1:8000. Interactive docs are at `/docs`
(disabled automatically in production).

Generate a strong secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env       # optional; defaults to the local backend
npm run dev
```

The app runs at http://localhost:5173.

### Creating the first admin

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `backend/.env`. On startup the app
seeds that admin account if it does not already exist. Afterwards, admins can
promote other users from the Admin dashboard.

---

## Environment variables

All backend configuration is via environment variables (see
`backend/.env.example` for the annotated list). Highlights:

| Variable | Purpose | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` or `production` | Prod enables strict validation + HSTS, disables `/docs`. |
| `GROQ_API_KEY` | Groq LLM access | **Required.** Never commit this. |
| `SECRET_KEY` | Signs JWTs | Must be ≥ 32 random chars in production. |
| `DATABASE_URL` | DB connection string | SQLite for dev; Postgres for prod. |
| `CORS_ORIGINS` | Allowed browser origins | Comma-separated; never `*` in prod. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes | |
| `RATE_LIMIT_*` | Per-endpoint limits | e.g. `15/minute` for AI calls. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` | First-run admin seed | Optional. |
| `WEB_CONCURRENCY` | gunicorn worker count | Defaults to 4. |

Frontend (build-time only, exposed to the browser — no secrets):

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Base URL of the backend API. |

In production, the app **refuses to start** if the config is unsafe (missing
Groq key, weak secret, `*` in CORS, `DEBUG=true`, or SQLite). This is deliberate
fail-fast behavior.

---

## Running the tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

The suite runs against an in-memory SQLite database (no external services) and
covers auth flows, RBAC guards, feedback submission + honeypot spam blocking,
admin analytics/CRUD/CSV export, SQL-injection safety of the search box, and
security-header presence.

---

## Production deployment

### Option A — Docker Compose (all-in-one)

```bash
cp backend/.env.example backend/.env     # fill in real secrets
export POSTGRES_PASSWORD=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
export VITE_API_URL=https://api.your-domain.com

docker compose up -d --build
```

This starts Postgres, the backend (gunicorn), and the nginx-served frontend.
Put a TLS-terminating reverse proxy (Caddy, Traefik, nginx, or a cloud load
balancer) in front so all traffic is HTTPS.

### Option B — separate services

- **Backend:** build `backend/Dockerfile` and run it on any container host
  (Fly.io, Render, ECS, Cloud Run). Point `DATABASE_URL` at a managed Postgres.
- **Frontend:** `npm run build` produces a static `dist/` you can host on any
  CDN/static host (Netlify, Vercel, Cloudflare Pages, S3+CloudFront), or use
  `frontend/Dockerfile` for the nginx image.

### Health checks

`GET /health` returns `{"status":"ok",...}` for load balancers and uptime
monitors. Both Docker images define container-level `HEALTHCHECK`s.

### Database migrations

The app calls `init_db()` on startup to create tables, which is sufficient for
first deploy. For evolving schemas in production, introduce Alembic:

```bash
pip install alembic
alembic init migrations
# configure sqlalchemy.url from DATABASE_URL, then:
alembic revision --autogenerate -m "message"
alembic upgrade head
```

### Backups

For managed Postgres, enable automated snapshots with your provider. For
self-hosted, schedule `pg_dump`:

```bash
pg_dump "$DATABASE_URL" | gzip > backup-$(date +%F).sql.gz
```

---

## Security notes

- **Secrets** are only read from environment variables; nothing sensitive is
  committed. `.env` files are git-ignored.
- **Passwords** are hashed with bcrypt (passlib). The hash is never serialized
  to the client.
- **JWT** access + refresh tokens; refresh tokens are validated by type so an
  access token can't be used to refresh, and vice-versa.
- **RBAC:** admin endpoints are guarded server-side by a `require_admin`
  dependency. Hiding the Admin nav item in the UI is cosmetic only.
- **Rate limiting** (SlowAPI) protects auth, AI, and feedback endpoints.
- **Input validation** via Pydantic on every request; uploads are checked for
  type, size, and encryption.
- **SQL injection:** all queries use SQLAlchemy's bound-parameter expression
  API — no string interpolation, even in the free-text admin search.
- **Security headers** on every API response (CSP, X-Frame-Options,
  X-Content-Type-Options, Referrer-Policy, Permissions-Policy, COOP/CORP, and
  HSTS in production). The nginx frontend adds its own CSP + headers.
- **Error handling:** a global handler logs the real error server-side and
  returns a generic message — stack traces are never exposed to clients.
- **Spam protection** on the feedback form: a hidden honeypot field plus rate
  limiting.

> **If a Groq API key was ever committed to git history, rotate it immediately**
> in the Groq console — removing it from the working tree is not enough.

---

## Project layout

```
FiQO-ai/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py            # app factory, middleware, lifespan, error handlers
│   │   ├── config.py          # env-driven settings + fail-fast validation
│   │   ├── database.py        # engine, session, Base, init_db
│   │   ├── models.py          # User, Feedback + enums
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── security.py        # hashing + JWT create/decode
│   │   ├── dependencies.py    # get_current_user, require_admin
│   │   ├── rate_limit.py      # SlowAPI limiter
│   │   ├── routers/           # auth, pdf, feedback, admin
│   │   └── services/          # pdf_service, ai_service
│   └── tests/                 # pytest suite
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── index.html             # SEO meta + manifest
    ├── public/                # favicon, robots.txt, sitemap.xml, webmanifest
    └── src/
        ├── main.jsx           # ErrorBoundary + Toast + Auth providers
        ├── App.jsx            # shell, nav, routing
        ├── context/AuthContext.jsx
        ├── lib/               # api (axios + refresh), auth (tokens), services
        ├── components/        # icons, Toast, ErrorBoundary, Output
        └── screens/           # Auth, Workspace, Feedback, Admin
```
