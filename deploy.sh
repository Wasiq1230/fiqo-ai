#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# FIQO AI — deploy script (Linux / macOS)
#
# Runs a pre-flight check on your configuration BEFORE starting anything, so a
# missing secret or a leftover placeholder is caught in two seconds instead of
# surfacing as a crash loop (or, worse, as a working-but-insecure deployment).
#
#   ./deploy.sh              build and start the whole stack
#   ./deploy.sh --check      run the pre-flight checks only
#   ./deploy.sh --logs       follow the backend logs
#   ./deploy.sh --down       stop the stack (data is preserved)
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
ok()   { echo "${GREEN}  ok${NC}  $1"; }
warn() { echo "${YELLOW}warn${NC}  $1"; }
fail() { echo "${RED}fail${NC}  $1"; FAILURES=$((FAILURES + 1)); }

cd "$(dirname "$0")"
FAILURES=0

# ── Read a KEY=value from an env file ─────────────────────────────────────
getenv() {  # getenv <file> <key>
  [ -f "$1" ] || return 0
  # Strips an unquoted trailing "# comment", surrounding quotes and whitespace,
  # so values copied from .env.example (which has inline comments) read cleanly.
  grep -E "^\s*$2\s*=" "$1" | tail -n1 | cut -d= -f2- \
    | sed -e 's/[[:space:]]\+#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
          -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/" || true
}

preflight() {
  echo
  echo "── Pre-flight checks ─────────────────────────────────────────"

  command -v docker >/dev/null 2>&1 && ok "docker found" \
    || { fail "docker not found — install Docker first"; return; }
  docker compose version >/dev/null 2>&1 && ok "docker compose found" \
    || fail "docker compose plugin not found"

  # ── Compose-level config ───────────────────────────────────────────────
  if [ -f .env ]; then ok ".env present"; else
    fail ".env missing — run: cp .env.example .env"
  fi
  local pg; pg="$(getenv .env POSTGRES_PASSWORD)"
  if [ -z "$pg" ]; then fail "POSTGRES_PASSWORD is empty in .env"
  elif [ "${#pg}" -lt 16 ]; then warn "POSTGRES_PASSWORD is short (<16 chars)"
  else ok "POSTGRES_PASSWORD set"; fi

  # ── Application config ─────────────────────────────────────────────────
  if [ -f backend/.env ]; then ok "backend/.env present"; else
    fail "backend/.env missing — run: cp backend/.env.production backend/.env"
    return
  fi

  local key secret env_mode debug cors hosts admin_pw
  key="$(getenv backend/.env GROQ_API_KEY)"
  secret="$(getenv backend/.env SECRET_KEY)"
  env_mode="$(getenv backend/.env ENVIRONMENT)"
  debug="$(getenv backend/.env DEBUG)"
  cors="$(getenv backend/.env CORS_ORIGINS)"
  hosts="$(getenv backend/.env ALLOWED_HOSTS)"
  admin_pw="$(getenv backend/.env ADMIN_PASSWORD)"

  [ -n "$key" ] && ok "GROQ_API_KEY set" || fail "GROQ_API_KEY is empty"
  case "$key" in *your-groq-api-key*) fail "GROQ_API_KEY is still the placeholder";; esac

  if [ -z "$secret" ]; then
    fail "SECRET_KEY is empty — generate: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
  elif [ "${#secret}" -lt 32 ]; then
    fail "SECRET_KEY is under 32 characters"
  else ok "SECRET_KEY set (${#secret} chars)"; fi
  case "$secret" in change-me*|dev-only*) fail "SECRET_KEY is a placeholder / dev key";; esac

  [ "$env_mode" = "production" ] && ok "ENVIRONMENT=production" \
    || warn "ENVIRONMENT is '$env_mode' (expected 'production')"
  case "$debug" in true|True|1) fail "DEBUG must be false in production";; *) ok "DEBUG off";; esac
  case "$cors" in *"*"*) fail "CORS_ORIGINS contains a wildcard";; *) ok "CORS_ORIGINS has no wildcard";; esac

  if [ -z "$hosts" ] || [ "$hosts" = "*" ]; then
    fail "ALLOWED_HOSTS must name your real domain(s), not '*'"
  elif echo "$hosts" | grep -q "your-domain.com"; then
    warn "ALLOWED_HOSTS still contains 'your-domain.com' — replace it with your"
    warn "  real domain, or every request to that domain returns 'Invalid host header'"
    ok   "(localhost testing will still work)"
  else ok "ALLOWED_HOSTS set"; fi

  if [ -n "$admin_pw" ] && [ "${#admin_pw}" -lt 12 ]; then
    fail "ADMIN_PASSWORD is under 12 characters"
  fi

  local site; site="$(getenv .env SITE_URL)"
  if [ -z "$site" ] || echo "$site" | grep -q "localhost"; then
    warn "SITE_URL is not set — SEO tags will point at localhost"
  else ok "SITE_URL set"; fi

  # ── Secrets must never be committed ────────────────────────────────────
  if command -v git >/dev/null 2>&1 && [ -d .git ]; then
    if git ls-files --error-unmatch backend/.env >/dev/null 2>&1; then
      fail "backend/.env is tracked by git — remove it and ROTATE YOUR GROQ KEY"
    else ok "backend/.env is not tracked by git"; fi
  fi

  echo "──────────────────────────────────────────────────────────────"
  if [ "$FAILURES" -gt 0 ]; then
    echo "${RED}$FAILURES problem(s) found. Fix them before deploying.${NC}"
    echo "See DEPLOYMENT.md for what each setting means."
    return 1
  fi
  echo "${GREEN}All checks passed.${NC}"
}

case "${1:-}" in
  --check) preflight ;;
  --logs)  docker compose logs -f backend ;;
  --down)  docker compose down && echo "Stopped. Data volume preserved." ;;
  *)
    preflight
    echo
    echo "── Building and starting ─────────────────────────────────────"
    docker compose up -d --build
    echo
    docker compose ps
    echo
    echo "Waiting for the API to become ready..."
    for _ in $(seq 1 30); do
      if docker compose exec -T backend python -c \
           "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=3)" \
           >/dev/null 2>&1; then
        echo "${GREEN}Backend is ready.${NC}"; break
      fi
      sleep 2
    done
    port="$(getenv .env WEB_PORT)"; port="${port:-8080}"
    echo
    echo "App:   http://localhost:${port}"
    echo "Logs:  ./deploy.sh --logs"
    echo
    echo "${YELLOW}Next: put HTTPS in front of port ${port} — see DEPLOYMENT.md section 4.${NC}"
    ;;
esac
