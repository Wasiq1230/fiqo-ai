# Deploying FIQO AI

Written to be followed top to bottom. You do not need prior deployment
experience — but do read step 0, because one thing there is not optional.

---

## 0. Before anything else: rotate your Groq key

An earlier version of this project had a Groq API key written directly into
`backend/.env`. That key is gone from the code now, but **removing a key from a
file does not un-leak it.** If that file was ever pushed to GitHub, zipped and
shared, opened on a shared machine, or pasted anywhere, treat the key as public.

1. Go to <https://console.groq.com/keys>
2. Delete the old key
3. Create a new one
4. Put the new one in `backend/.env` on the server only

Anyone holding your key can spend your quota and bill it to you. This takes two
minutes and it is the single highest-value thing in this document.

---

## 1. How the pieces fit together

```
                    ┌─────────────────────────────────────────┐
   Browser ────────►│  web  (nginx, port 8080 → your domain)  │
   (only this is    │  • serves the React bundle              │
   publicly         │  • proxies /api/* to the backend        │
   reachable)       └──────────────────┬──────────────────────┘
                                       │  private network
                    ┌──────────────────▼──────────────────────┐
                    │  backend  (FastAPI, port 8000)          │
                    │  • holds the Groq key                   │
                    │  • auth, rate limits, PDF + AI logic    │
                    └──────────────────┬──────────────────────┘
                                       │  private network
                    ┌──────────────────▼──────────────────────┐
                    │  db  (Postgres)                         │
                    └─────────────────────────────────────────┘
```

The important part: **only the web container is published.** The API and the
database have no host ports at all, so nothing outside the stack can reach them
directly. The browser talks to `/api/...` on the same domain it loaded the page
from, and nginx forwards that internally.

This is also the answer to "the API key must be hidden": the key lives in the
backend container's environment. It is never in the JavaScript bundle, never in
a response body, never in an error message. A user can open DevTools, read every
byte the server sends, and still not see it.

---

## 2. Local run (verify before you deploy)

> **Python 3.11–3.13 only** (3.12 recommended — it is what the Docker image
> runs). Python 3.14 breaks SQLAlchemy 2.0.36. On Windows use `py -3.12`.

```bash
cd backend
py -3.12 -m venv venv          # macOS/Linux: python3.12 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit: GROQ_API_KEY + SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"   # → SECRET_KEY

# For local dev set ENVIRONMENT=development in .env
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Run the tests before you ship anything:

```bash
cd backend && pytest
```

---

## 3. Deploy with Docker (recommended)

On any server with Docker installed:

```bash
# 1. Compose-level variables (database password, port)
cp .env.example .env
nano .env                 # set POSTGRES_PASSWORD

# 2. Application secrets
cp backend/.env.production backend/.env
nano backend/.env         # set GROQ_API_KEY, SECRET_KEY, ALLOWED_HOSTS,
                          # ADMIN_EMAIL, ADMIN_PASSWORD

# 3. Build and start
docker compose up -d --build

# 4. Check
docker compose ps
curl http://localhost:8080/healthz
docker compose logs -f backend
```

`./deploy.sh` runs the same steps with a pre-flight check that catches empty
secrets and placeholder values before the stack starts.

**The app deliberately refuses to boot** if `ENVIRONMENT=production` and
something is unsafe — a missing `SECRET_KEY`, `DEBUG=true`, a wildcard in
`CORS_ORIGINS`, SQLite as the production database. A failed deploy with a clear
error is much cheaper than a quiet breach. If it won't start, read the log; it
names exactly what to fix.

---

## 4. HTTPS — not optional

Everything above serves plain HTTP on port 8080. Without TLS, every password
and every JWT crosses the network in the clear, and the browser will refuse
some security features.

Easiest option, Caddy (automatic Let's Encrypt certificates):

```bash
# /etc/caddy/Caddyfile
your-domain.com {
    reverse_proxy localhost:8080
}
```

```bash
sudo apt install caddy && sudo systemctl restart caddy
```

Then in `backend/.env`:

```
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
TRUST_PROXY=true
```

Cloudflare Tunnel or nginx + certbot work equally well. Any of them; just do
one of them.

---

## 5. Platform-as-a-service alternative

If you would rather not manage a server, split the app in two:

| Piece    | Where                              | Notes                                          |
| -------- | ---------------------------------- | ---------------------------------------------- |
| Backend  | Railway / Render / Fly.io          | Deploy `backend/`, add a managed Postgres addon |
| Frontend | Vercel / Netlify / Cloudflare Pages | Deploy `frontend/`, build command `npm run build` |

With a split deployment the API is on its own domain, so you must set:

- backend `CORS_ORIGINS=https://your-frontend.vercel.app`
- backend `ALLOWED_HOSTS=your-api.up.railway.app`
- backend `TRUST_PROXY=true` (all these platforms sit behind a proxy)
- frontend `VITE_API_URL=https://your-api.up.railway.app`

Set every environment variable in the platform's dashboard. Never commit `.env`.

---

## 6. First login

If you set `ADMIN_EMAIL` and `ADMIN_PASSWORD`, an admin account is created on
first startup. Sign in, then **change that password from inside the app** and
clear `ADMIN_PASSWORD` from the environment.

---

## 7. After it's live

| How often  | Do this                                                                    |
| ---------- | -------------------------------------------------------------------------- |
| Weekly     | `docker compose logs backend \| grep -i error`                              |
| Weekly     | Check the Groq console for unexpected usage — a spike means a leaked key    |
| Monthly    | `pip-audit -r backend/requirements.txt` and `npm audit --prefix frontend`   |
| Monthly    | `docker compose pull && docker compose up -d --build` (base image patches)  |
| Set up now | Database backups: `docker compose exec db pg_dump -U FiQO FiQO > backup.sql` |

Automate that last one with cron. The volume is not a backup — a wrong
`docker compose down -v` deletes everything in it.

---

## 8. When something breaks

| Symptom                        | Cause and fix                                                                     |
| ------------------------------ | --------------------------------------------------------------------------------- |
| Backend exits immediately      | Config validation failed. `docker compose logs backend` names the setting.         |
| 413 on upload                  | File over `MAX_UPLOAD_MB`, or nginx `client_max_body_size` is below it.            |
| 429 on everything              | Rate limit. If it fires for every user at once, `TRUST_PROXY` is wrong.            |
| 503 from the AI endpoints      | Groq key invalid, out of quota, or upstream is down. Check the backend log.        |
| CORS error in the browser      | Split deployment with `CORS_ORIGINS` not matching the frontend origin exactly.     |
| "Invalid host header"          | Your domain is missing from `ALLOWED_HOSTS`.                                       |
| Login works, then 401 instantly | `SECRET_KEY` changed between restarts — set it explicitly, don't regenerate it.    |
