"""
Application configuration.

Every secret and environment-specific value is read from environment variables
(or a local .env file in development). Nothing sensitive is hard-coded, and
nothing sensitive is ever sent to the browser. See .env.example for the full list.

`validate_runtime()` is the deployment safety net: in production the app
*refuses to start* on a dangerous configuration rather than booting into an
insecure state that nobody notices until it is being abused.
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder values that appear in the shipped templates. If one of these is
# still present in production it means the template was deployed unedited.
_PLACEHOLDERS = {
    "your-groq-api-key-here",
    "change-me-to-a-long-random-value-at-least-32-chars",
    "use-a-strong-unique-password",
    "changeme",
    "password",
    "admin",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────────────
    app_name: str = "FIQO AI"
    environment: str = Field(default="development")  # development | production
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # ── Secrets ─────────────────────────────────────────────────────────
    # REQUIRED in production. The app refuses to start without real values.
    groq_api_key: str = Field(default="")
    secret_key: str = Field(default="")  # signs JWTs

    # ── AI ──────────────────────────────────────────────────────────────
    groq_model: str = Field(default="llama-3.1-8b-instant")
    ai_max_input_chars: int = Field(default=8000, ge=500, le=200_000)
    ai_max_input_chars_multi: int = Field(default=12000, ge=500, le=200_000)
    ai_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    ai_max_retries: int = Field(default=1, ge=0, le=5)

    # ── Auth / JWT ──────────────────────────────────────────────────────
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=90)
    jwt_algorithm: str = Field(default="HS256")
    jwt_issuer: str = Field(default="FiQO-ai")

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = Field(default="sqlite:///./FiQO.db")
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=50)

    # ── Public URLs ─────────────────────────────────────────────────────
    # Where the browser-facing app lives. Verification links point here, so it
    # must be the real deployed origin (e.g. https://fiqo.vercel.app) — a wrong
    # value produces links that 404 for every user who clicks one.
    frontend_url: str = Field(default="http://localhost:5173")

    # ── Email verification ──────────────────────────────────────────────
    # Master switch. When true, a new account cannot sign in until the address
    # has been confirmed. Turned off automatically if no mail transport is
    # configured, so a missing SMTP password can never lock everyone out.
    require_email_verification: bool = Field(default=True)
    email_verification_expire_hours: int = Field(default=24, ge=1, le=168)
    # Minimum seconds between two "resend verification" requests per account.
    email_resend_cooldown_seconds: int = Field(default=60, ge=0, le=3600)

    # ── Password reset ──────────────────────────────────────────────────
    # Much shorter than a confirmation link: a reset token is an account
    # takeover if it leaks, and the user is sitting at the screen waiting for
    # it, so there is no reason for a long window.
    password_reset_expire_hours: int = Field(default=1, ge=1, le=24)
    password_reset_cooldown_seconds: int = Field(default=60, ge=0, le=3600)

    # ── Registration email hygiene ──────────────────────────────────────
    # Reject addresses whose domain publishes no MX (and no A) record — i.e.
    # domains that physically cannot receive mail, like "asdf@asdf.com".
    check_email_mx: bool = Field(default=True)
    email_mx_timeout_seconds: float = Field(default=4.0, gt=0, le=30)
    # Reject known throwaway/temp-mail domains (mailinator, 10minutemail, ...).
    block_disposable_email: bool = Field(default=True)
    # Extra domains to refuse, comma-separated. Useful for abuse you see later
    # without needing a redeploy of the blocklist file.
    extra_blocked_email_domains: str = Field(default="")
    # Only allow these domains to register (comma-separated). Empty = allow all.
    # Handy if FiQO is ever restricted to one university's addresses.
    allowed_email_domains: str = Field(default="")

    # ── Outbound mail ───────────────────────────────────────────────────
    # "smtp"    — Gmail, Brevo, Mailgun, any SMTP server (set SMTP_* below)
    # "brevo"   — Brevo HTTP API. Use this when the host blocks outbound SMTP
    #             ports, which Render's free tier and several other PaaS do.
    #             Needs only a verified sender address, not a domain.
    # "resend"  — Resend HTTP API. Also HTTPS, but without a verified domain it
    #             can only deliver to the account owner's own address.
    # "console" — log the message instead of sending it (development only)
    email_provider: str = Field(default="console")
    email_from: str = Field(default="")          # e.g. "FIQO AI <no-reply@…>"
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)     # STARTTLS on 587
    smtp_use_ssl: bool = Field(default=False)    # implicit TLS on 465
    smtp_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    brevo_api_key: str = Field(default="")
    resend_api_key: str = Field(default="")

    # ── CORS / hosts ────────────────────────────────────────────────────
    # Comma-separated exact origins. NEVER "*" in production.
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")
    # Host header allowlist (blocks Host-header injection / DNS rebinding).
    allowed_hosts: str = Field(default="*")
    # Set true ONLY when the app sits behind a proxy you control (nginx, Caddy,
    # Railway, Render, Fly, Cloudflare). It makes the rate limiter read
    # X-Forwarded-For. Leaving it true on a directly-exposed app would let any
    # client forge that header and bypass rate limiting entirely.
    trust_proxy: bool = Field(default=False)

    # ── Uploads ─────────────────────────────────────────────────────────
    max_upload_mb: int = Field(default=15, ge=1, le=200)
    max_files_per_request: int = Field(default=10, ge=1, le=50)
    max_total_upload_mb: int = Field(default=50, ge=1, le=500)
    max_pdf_pages: int = Field(default=500, ge=1, le=10_000)

    # ── Rate limiting ───────────────────────────────────────────────────
    rate_limit_default: str = Field(default="60/minute")
    rate_limit_ai: str = Field(default="15/minute")
    rate_limit_auth: str = Field(default="10/minute")
    rate_limit_feedback: str = Field(default="5/minute")
    # Optional shared store so limits hold across gunicorn workers / replicas.
    # e.g. redis://localhost:6379/0  — falls back to per-process memory if empty.
    rate_limit_storage_uri: str = Field(default="")

    # ── First-run admin seeding ─────────────────────────────────────────
    admin_email: str = Field(default="")
    admin_password: str = Field(default="")
    admin_name: str = Field(default="Administrator")

    # ── Derived helpers ─────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_host_list(self) -> List[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()] or ["*"]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_total_upload_bytes(self) -> int:
        return self.max_total_upload_mb * 1024 * 1024

    @property
    def frontend_base(self) -> str:
        """Frontend origin with any trailing slash removed."""
        return self.frontend_url.strip().rstrip("/")

    @property
    def extra_blocked_domain_set(self) -> set[str]:
        return {
            d.strip().lower().lstrip("@")
            for d in self.extra_blocked_email_domains.split(",")
            if d.strip()
        }

    @property
    def allowed_email_domain_set(self) -> set[str]:
        return {
            d.strip().lower().lstrip("@")
            for d in self.allowed_email_domains.split(",")
            if d.strip()
        }

    @property
    def mail_configured(self) -> bool:
        """Can this process actually deliver a message right now?

        'console' counts: it "delivers" to the log, which is what a developer
        running locally wants. Anything else needs real credentials.
        """
        if self.email_provider == "console":
            return True
        if self.email_provider == "smtp":
            return bool(self.smtp_host and self.smtp_user and self.smtp_password)
        if self.email_provider == "brevo":
            return bool(self.brevo_api_key)
        if self.email_provider == "resend":
            return bool(self.resend_api_key)
        return False

    @property
    def email_verification_enabled(self) -> bool:
        """Verification is only enforced when mail can actually be sent.

        Enforcing it without a working transport would create accounts nobody
        can ever activate — a far worse outcome than letting them in.
        """
        return self.require_email_verification and self.mail_configured

    @property
    def email_sender(self) -> str:
        """From-address, falling back to the SMTP username."""
        return (self.email_from or self.smtp_user).strip()

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Make hosted-Postgres URLs usable by SQLAlchemy 2 + psycopg 3.

        Neon, Render, Railway, Heroku and Supabase all hand out URLs starting
        with `postgres://` or `postgresql://`. SQLAlchemy resolves the bare
        `postgresql://` prefix to psycopg2, which is not installed here — the
        app dies at import with ModuleNotFoundError. `postgres://` is not a
        registered dialect at all. Rewriting the scheme is the difference
        between a boot and a crash loop, so it happens here rather than relying
        on every deploy target's URL being pasted in the right shape.
        """
        v = v.strip()
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("email_provider")
    @classmethod
    def _check_email_provider(cls, v: str) -> str:
        allowed = {"smtp", "brevo", "resend", "console"}
        v = v.strip().lower()
        if v not in allowed:
            raise ValueError(f"EMAIL_PROVIDER must be one of {sorted(allowed)}.")
        return v

    @field_validator("environment")
    @classmethod
    def _normalize_env(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("jwt_algorithm")
    @classmethod
    def _check_alg(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        v = v.strip().upper()
        if v not in allowed:
            raise ValueError(f"JWT_ALGORITHM must be one of {sorted(allowed)}.")
        return v

    def validate_runtime(self) -> None:
        """Fail fast on misconfiguration. Hard failure in production."""
        problems: List[str] = []

        if not self.groq_api_key:
            problems.append("GROQ_API_KEY is not set — AI features cannot work.")
        elif self.groq_api_key.strip() in _PLACEHOLDERS:
            problems.append("GROQ_API_KEY is still the placeholder from .env.example.")

        if self.is_production:
            if not self.secret_key or len(self.secret_key) < 32:
                problems.append(
                    "SECRET_KEY must be a strong random value (>= 32 chars) in "
                    'production. Generate one with: python -c "import secrets; '
                    'print(secrets.token_urlsafe(48))"'
                )
            if self.secret_key.strip() in _PLACEHOLDERS or \
                    self.secret_key.lower().startswith("dev-only"):
                problems.append("SECRET_KEY is a placeholder / dev key — replace it.")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS must not include '*' in production.")
            if any(o.startswith("http://") and "localhost" not in o
                   and "127.0.0.1" not in o for o in self.cors_origin_list):
                problems.append("CORS_ORIGINS contains a plain-http origin — use https.")
            if self.debug:
                problems.append("DEBUG must be false in production.")
            if self.database_url.startswith("sqlite"):
                problems.append(
                    "SQLite is not suitable for production. On Render/Railway/Fly "
                    "the container filesystem is ephemeral, so the .db file — and "
                    "every account in it — is destroyed on each restart or deploy. "
                    "Point DATABASE_URL at managed Postgres (Neon, Supabase, RDS)."
                )
            if self.require_email_verification and not self.mail_configured:
                problems.append(
                    "REQUIRE_EMAIL_VERIFICATION is on but no mail transport is "
                    "configured — set EMAIL_PROVIDER plus its credentials "
                    "(SMTP_HOST/SMTP_USER/SMTP_PASSWORD, or BREVO_API_KEY, or "
                    "RESEND_API_KEY), or "
                    "set REQUIRE_EMAIL_VERIFICATION=false."
                )
            if self.email_provider == "console":
                problems.append(
                    "EMAIL_PROVIDER=console only writes messages to the log — no "
                    "user will ever receive a verification email."
                )
            if not self.frontend_base.startswith("https://"):
                problems.append(
                    "FRONTEND_URL must be your real https:// site — it is what "
                    "verification links point at."
                )
            if self.allowed_hosts.strip() == "*":
                problems.append(
                    "ALLOWED_HOSTS is '*' — set it to your real domain(s) to block "
                    "Host-header injection."
                )
            if self.admin_password and self.admin_password.strip() in _PLACEHOLDERS:
                problems.append("ADMIN_PASSWORD is a placeholder — set a real one.")
            if self.admin_password and len(self.admin_password) < 12:
                problems.append("ADMIN_PASSWORD must be at least 12 characters.")

        if problems and self.is_production:
            raise RuntimeError(
                "Refusing to start — invalid production configuration:\n  - "
                + "\n  - ".join(problems)
            )
        # In development these are surfaced as warnings by the caller.
        self._warnings = problems  # type: ignore[attr-defined]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
