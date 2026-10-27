# ── FIQO AI backend image ──────────────────────────────────────────────
# Multi-stage: build wheels with a toolchain, run on a clean slim base so no
# compiler or build cache ships to production.
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Patch OS packages, then drop apt lists to keep the image small.
RUN apt-get update && apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/*

# Never run as root in production.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# Copy application code with non-root ownership. .dockerignore keeps .env,
# venv/, tests and the local database out of the image.
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Readiness (not just liveness): this verifies the database is reachable, so a
# container that is up but cannot serve traffic is reported unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).status==200 else sys.exit(1)"

# WEB_CONCURRENCY tunes worker count; (2 x CPU cores) + 1 is a good start.
# --forwarded-allow-ips is set from the env so X-Forwarded-* is honoured only
# when the app really is behind a proxy you control.
CMD ["sh", "-c", "exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000 \
  -w ${WEB_CONCURRENCY:-4} \
  --timeout 120 \
  --graceful-timeout 30 \
  --max-requests 1000 --max-requests-jitter 100 \
  --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" \
  --access-logfile - --error-logfile -"]
