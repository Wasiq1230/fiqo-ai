"""
Email-confirmation tokens.

A thin wrapper over `app.services.tokens`, which holds the shared hashing,
single-use and expiry logic. See that module for the security reasoning.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailVerification, User
from app.services import tokens

logger = logging.getLogger("FiQO.verification")
settings = get_settings()


def seconds_since_last_send(db: Session, user_id: int) -> float | None:
    return tokens.seconds_since_last_issue(db, EmailVerification, user_id)


def issue_token(db: Session, user: User) -> str:
    """Create a fresh confirmation token for `user`. Caller commits."""
    return tokens.issue(
        db, EmailVerification, user.id, settings.email_verification_expire_hours
    )


def build_link(raw_token: str) -> str:
    """The URL that goes in the email."""
    return f"{settings.frontend_base}/?verify={quote(raw_token, safe='')}"


def redeem_token(db: Session, raw_token: str) -> User | None:
    """Mark the token used and the user verified. None if it is not usable."""
    user_id = tokens.redeem(db, EmailVerification, raw_token)
    if user_id is None:
        db.rollback()
        return None

    user = db.get(User, user_id)
    if user is None:
        db.rollback()
        return None

    user.is_verified = True
    db.commit()
    logger.info("Email verified for user id=%s", user.id)
    return user


def purge_expired(db: Session) -> int:
    """Delete spent and expired rows. Called at startup; safe to skip."""
    removed = tokens.purge_old(db, EmailVerification)
    db.commit()
    return removed
