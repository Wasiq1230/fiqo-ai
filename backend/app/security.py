"""
Security primitives: password hashing and JWT creation/verification.

Changes vs the previous version (both were flagged by dependency auditing):

* `python-jose` -> `PyJWT`.  python-jose has had no release since 3.3.0 (2021),
  is effectively unmaintained, and is flagged by `pip-audit` / GitHub Dependabot
  (CVE-2024-33663, CVE-2024-33664).  Our usage (HS256, symmetric key, no JWE)
  was not directly exploitable, but shipping an unmaintained crypto dependency
  to production is not a defensible position.  PyJWT is actively maintained.

* `passlib` -> `bcrypt` directly.  passlib 1.7.4 (2020, unmaintained) reads
  `bcrypt.__about__.__version__`, which bcrypt removed in 4.1 — that
  combination raises an internal error and spams the logs on every hash.
  bcrypt's own API is small enough that the wrapper bought us nothing.
  Hash format is unchanged ($2b$...), so existing accounts keep working.

Tokens carry:
  sub  - user id
  type - "access" | "refresh"  (a refresh token can never be used as access)
  ver  - the user's token_version, so revocation/force-logout is possible
  jti  - unique id, for future denylisting and for log correlation
  iat / exp / nbf
"""
from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.config import get_settings

settings = get_settings()

ACCESS = "access"
REFRESH = "refresh"

# bcrypt hashes at most 72 bytes; anything beyond that is silently ignored,
# which would make "correct horse battery staple..."[:72] == the full password.
# We reject instead of truncating so the limit is never a silent surprise.
BCRYPT_MAX_BYTES = 72

# Pre-computed hash of a value nobody can log in with. Used to burn a constant
# amount of CPU when an email does not exist, so response timing does not leak
# which emails are registered. Computed once at import — the previous code
# hashed a dummy password on *every* failed login, which doubled bcrypt cost
# and handed attackers a cheap CPU-exhaustion lever.
_DUMMY_HASH = bcrypt.hashpw(b"FiQO-timing-equaliser", bcrypt.gensalt())


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds bcrypt's 72-byte input limit."""


def _encode(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        raise PasswordTooLongError(
            f"Password must be at most {BCRYPT_MAX_BYTES} bytes "
            "(note: accented and non-Latin characters use more than one byte)."
        )
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time password check. Never raises on malformed input."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:BCRYPT_MAX_BYTES],
                              hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def burn_dummy_verify(plain: str) -> None:
    """Spend the same CPU as a real check, for unknown-email login attempts."""
    try:
        bcrypt.checkpw(plain.encode("utf-8")[:BCRYPT_MAX_BYTES], _DUMMY_HASH)
    except (ValueError, TypeError):
        pass


# ── JWT ──────────────────────────────────────────────────────────────────────


def _create_token(subject: str, token_type: str, expires_delta: timedelta,
                  token_version: int = 0,
                  extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "ver": token_version,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "nbf": now,
        "exp": now + expires_delta,
        "iss": settings.jwt_issuer,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key,
                      algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str, token_version: int = 0) -> str:
    return _create_token(
        subject=str(user_id),
        token_type=ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_version=token_version,
        extra={"role": role},
    )


def create_refresh_token(user_id: int, token_version: int = 0) -> str:
    return _create_token(
        subject=str(user_id),
        token_type=REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        token_version=token_version,
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises InvalidTokenError on any problem.

    `algorithms` is pinned to a single algorithm, so an attacker cannot swap in
    `none` or downgrade to something weaker via the header.
    """
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "type"],
                 "verify_signature": True,
                 "verify_exp": True},
    )
    # hmac.compare_digest keeps the type check constant-time; more importantly
    # it makes "refresh token used as an access token" impossible.
    if not hmac.compare_digest(str(payload.get("type", "")), expected_type):
        raise InvalidTokenError("Wrong token type.")
    return payload
