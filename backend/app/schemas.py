"""Pydantic request/response schemas (validation + serialization)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import FeedbackStatus, FeedbackType, UserRole

# ── Auth ────────────────────────────────────────────────────────────────


# bcrypt hashes at most 72 *bytes* and silently ignores the rest, so a 128-char
# limit is not the real limit. We enforce the true one up front with a clear
# message instead of letting the tail of a long password quietly stop mattering.
BCRYPT_MAX_BYTES = 72

# Passwords that pass a "letters + numbers" rule but are still the first thing
# an attacker tries.
_COMMON_PASSWORDS = {
    "password1", "password123", "abc12345", "12345678", "qwerty123",
    "admin123", "letmein1", "welcome1", "iloveyou1", "FiQO123",
}


def _validate_password(v: str) -> str:
    if len(v.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password must be at most {BCRYPT_MAX_BYTES} bytes "
            "(accented or non-Latin characters count as more than one)."
        )
    if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError("Password must contain both letters and numbers.")
    if v.lower() in _COMMON_PASSWORDS:
        raise ValueError("That password is too common. Please choose another.")
    return v


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _validate_password(v)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterResult(BaseModel):
    """Registration outcome.

    When verification is enforced the account exists but cannot be used yet, so
    there are no tokens to hand back. The frontend branches on
    `verification_required` rather than on the presence of `access_token`,
    which keeps the two states explicit instead of inferred.
    """

    verification_required: bool
    message: str
    email: EmailStr
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"


class EmailVerifyRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _validate_password(v)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=4096)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _validate_password(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime


# ── AI responses ────────────────────────────────────────────────────────


class TextResult(BaseModel):
    filename: str | None = None
    files: list[str] | None = None
    result: str


class QuizOption(BaseModel):
    A: str
    B: str
    C: str
    D: str


class ScoredQuizQuestion(BaseModel):
    question: str
    options: QuizOption
    correct_answer: str


class ScoredQuizResult(BaseModel):
    filename: str
    quiz: list[ScoredQuizQuestion]


# ── Feedback ────────────────────────────────────────────────────────────


class FeedbackCreate(BaseModel):
    type: FeedbackType = FeedbackType.feedback
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=5000)
    # Honeypot field: must remain empty. Bots tend to fill every field.
    website: str = Field(default="", max_length=0)

    @field_validator("name", "subject", "message")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None
    type: FeedbackType
    status: FeedbackStatus
    name: str
    email: EmailStr
    subject: str
    message: str
    admin_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class FeedbackUpdate(BaseModel):
    status: FeedbackStatus | None = None
    admin_note: str | None = Field(default=None, max_length=5000)


class FeedbackList(BaseModel):
    total: int
    items: list[FeedbackOut]


# ── Generic ─────────────────────────────────────────────────────────────


class Message(BaseModel):
    message: str
