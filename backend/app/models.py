"""SQLAlchemy ORM models."""
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, PyEnum):
    user = "user"
    admin = "admin"


class FeedbackType(str, PyEnum):
    feedback = "feedback"
    bug = "bug"
    complaint = "complaint"
    feature = "feature"
    support = "support"


class FeedbackStatus(str, PyEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.user, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Has the owner of this address proved they can read mail sent to it?
    # Without this, "asdf@asdf.com" is a perfectly good account: the address
    # never has to exist, so signups cost an abuser nothing and there is no way
    # to reach a user for a password reset.
    #
    # Defaults to False for new rows. Rows that predate this column are
    # backfilled to True by the migration in database.py, so switching
    # verification on does not lock out existing users.
    # `false()` renders as FALSE on Postgres and 0 on SQLite; a literal "0"
    # string would be rejected by one of the two.
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # Bumped on logout / password change / admin force-logout. Every token
    # carries the version it was minted with, so raising this instantly
    # invalidates all outstanding access AND refresh tokens for this user.
    # Without it, a stolen refresh token stays valid for its full lifetime and
    # there is no way to revoke it.
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class EmailVerification(Base):
    """A single-use token proving control of an email address.

    Only the SHA-256 of the token is stored. The raw value exists in the user's
    inbox and nowhere else, so a leaked database dump does not hand an attacker
    a set of working activation links. Same reasoning as password hashing.
    """

    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Hex SHA-256 is always 64 chars.
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Set the moment the link is used, so a forwarded or replayed link fails.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class PasswordReset(Base):
    """A single-use token authorising one password change.

    Deliberately a separate table from EmailVerification rather than one table
    with a `purpose` column: a bug that let a confirmation token be redeemed as
    a reset token would hand account takeover to anyone who ever received a
    signup email. Separate tables make that class of mix-up impossible rather
    than merely unlikely.

    Same storage rules as EmailVerification — only the SHA-256 is kept.
    """

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Nullable so anonymous / contact-support submissions are allowed.
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType), default=FeedbackType.feedback, nullable=False, index=True
    )
    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(FeedbackStatus), default=FeedbackStatus.open, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
