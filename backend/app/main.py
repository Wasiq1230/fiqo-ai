"""
FIQO AI — application factory and entrypoint.

This module wires the backend together:
- structured logging (no secrets, no tracebacks leaked to clients)
- configuration validated on startup; production refuses to boot if unsafe
- Host header allowlist (blocks Host-header injection / DNS rebinding)
- CORS locked to an explicit allowlist (never "*")
- security headers on every response (CSP, HSTS, X-Frame-Options, ...)
- GZip compression for large JSON/text responses
- rate limiting, proxy-aware (see app/rate_limit.py)
- global exception handlers returning clean JSON, never a stack trace
- liveness (/health) and readiness (/health/ready, checks the DB) probes
- first-run DB bootstrap + optional admin seeding, safe across workers

Run locally:   uvicorn app.main:app --reload
Run in prod:   gunicorn -k uvicorn.workers.UvicornWorker app.main:app
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.config import get_settings
from app.database import SessionLocal, engine, init_db
from app.models import User, UserRole
from app.rate_limit import limiter
from app.routers import admin, auth, feedback, pdf
from app.security import hash_password
from app.services import password_reset, verification

settings = get_settings()

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("FiQO")


# ── Security headers middleware ──────────────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach a strict set of security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers

        # This is a JSON API serving no HTML or JS of its own, so the tightest
        # possible CSP is safe here.
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'none'",
        )
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        # Authenticated API responses should never sit in a shared cache.
        headers.setdefault("Cache-Control", "no-store")
        # HSTS only makes sense over HTTPS, which we assume in production.
        if settings.is_production:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        return response


# ── Startup / shutdown ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    for warning in getattr(settings, "_warnings", []):
        logger.warning("Config: %s", warning)

    init_db()
    _seed_admin()
    _purge_stale_verifications()
    logger.info(
        "%s v%s started in %s mode (docs: %s).",
        settings.app_name, __version__, settings.environment,
        "disabled" if settings.is_production else "enabled",
    )
    logger.info(
        "Email verification: %s (provider=%s).",
        "ENFORCED" if settings.email_verification_enabled else "off",
        settings.email_provider,
    )
    yield
    logger.info("%s shutting down.", settings.app_name)


def create_app() -> FastAPI:
    # Interactive docs and the OpenAPI schema are a free map of the attack
    # surface, so they are development-only.
    docs_url = None if settings.is_production else "/docs"
    redoc_url = None if settings.is_production else "/redoc"

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="AI-powered study assistant API.",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    # Rate limiting.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Compression for larger payloads (summaries, quizzes, CSV exports).
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Security headers on everything.
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS — explicit allowlist only. Added after the above so it wraps them
    # and error responses still carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Retry-After"],
        max_age=600,
    )

    # Outermost: reject unknown Host headers before anything else runs.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

    _register_exception_handlers(app)
    _register_routes(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # Field-level detail is useful to the client, but the raw error objects
        # can echo submitted values (including passwords) straight back and into
        # logs. Return only the location and the message.
        safe = [
            {"field": ".".join(str(p) for p in err.get("loc", ())[1:]) or "body",
             "message": err.get("msg", "Invalid value.")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Validation failed.", "errors": safe},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Log server-side; never expose internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."},
        )


def _register_routes(app: FastAPI) -> None:
    app.include_router(auth.router)
    app.include_router(pdf.router)
    app.include_router(feedback.router)
    app.include_router(admin.router)

    @app.get("/health", tags=["system"], summary="Liveness probe")
    @limiter.exempt
    def health():
        """Is the process up? Deliberately does no I/O and leaks no detail."""
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready", tags=["system"], summary="Readiness probe")
    @limiter.exempt
    def ready():
        """Can we actually serve traffic? Verifies the database connection.

        A liveness check that never touches the DB will happily report "ok"
        while every real request fails, so orchestrators keep routing traffic
        to a broken instance.
        """
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("Readiness check failed: database unreachable")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable", "database": "down"},
            )
        return {"status": "ready", "database": "up"}

    @app.get("/", tags=["system"], include_in_schema=False)
    def root():
        return {"app": settings.app_name, "version": __version__}


def _seed_admin() -> None:
    """Create the initial admin from env vars if one does not already exist.

    Controlled by ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME. Skipped silently
    when unset. Every gunicorn worker runs this at boot, so the unique index on
    email is the real guard and IntegrityError is an expected, benign outcome
    of that race rather than an error.
    """
    email = settings.admin_email.strip().lower()
    password = settings.admin_password
    if not email or not password:
        return

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            # Keep the seeded account an admin, but never reset its password.
            if existing.role != UserRole.admin:
                existing.role = UserRole.admin
                db.commit()
            return
        db.add(User(
            name=settings.admin_name.strip() or "Administrator",
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.admin,
            # The operator set this address in the environment; there is nobody
            # to email a confirmation link to, and an admin locked out of their
            # own deployment is not a useful safety property.
            is_verified=True,
        ))
        db.commit()
        logger.info("Seeded initial admin account: %s", email)
    except IntegrityError:
        db.rollback()  # another worker won the race; nothing to do
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Admin seeding failed")
    finally:
        db.close()


def _purge_stale_verifications() -> None:
    """Drop spent verification rows so the table does not grow forever.

    Housekeeping, not correctness — redeem_token already rejects anything
    expired or used. A failure here must never stop the app from booting.
    """
    db = SessionLocal()
    try:
        removed = verification.purge_expired(db) + password_reset.purge_expired(db)
        if removed:
            logger.info("Purged %s expired token(s)", removed)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("Token cleanup failed (non-fatal)")
    finally:
        db.close()


app = create_app()
