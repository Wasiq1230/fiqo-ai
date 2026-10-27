# ─────────────────────────────────────────────────────────────
# FIQO AI — frontend production image
# Multi-stage: build with Node 20 → serve static assets via Nginx.
# ─────────────────────────────────────────────────────────────

# ── Stage 1: build ──────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Cache npm layer.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

# Build the bundle.
ARG VITE_API_URL
ARG VITE_SITE_URL=http://localhost:8080
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_SITE_URL=${VITE_SITE_URL}
COPY . .
RUN npm run build

# ── Stage 2: serve ──────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Hardened Nginx config (security headers, gzip, SPA fallback, /api proxy).
COPY nginx.conf             /etc/nginx/conf.d/default.conf
COPY security-headers.conf  /etc/nginx/security-headers.conf

# Static bundle.
COPY --from=builder /app/dist /usr/share/nginx/html

# Healthcheck through Nginx.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
