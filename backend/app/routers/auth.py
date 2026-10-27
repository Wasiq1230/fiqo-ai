"""Authentication routes: register, verify, login, refresh, logout, password change, me."""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from jwt import InvalidTokenError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, UserRole
from app.rate_limit import limiter
from app.schemas import (
    EmailVerifyRequest,
    ForgotPasswordRequest,
    Message,
    PasswordChange,
    PasswordResetRequest,
    RefreshRequest,
    RegisterResult,
    ResendVerificationRequest,
    TokenPair,
    UserLogin,
    UserOut,
    UserRegister,
)
from app.security import (
    REFRESH,
    burn_dummy_verify,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services import password_reset, verification
from app.services.email_service import (
    send_password_reset_email,
    send_verification_email,
)
from app.services.email_validation import EmailNotAcceptable, validate_registration_email

logger = logging.getLogger("FiQO.auth")
settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password.",
)
_INVALID_REFRESH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired refresh token.",
)

_CHECK_INBOX = (
    "Account created. Check your inbox and click the confirmation link to "
    "activate it. If it is not there in a minute, look in spam."
)


def _issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, user.role.value, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
    )


def _queue_verification_email(
    background: BackgroundTasks, db: Session, user: User
) -> None:
    """Mint a token and hand the send-off to the background.

    The send is deliberately outside the request/response cycle: SMTP can take
    seconds, and a user should not stare at a spinner while a mail server
    negotiates TLS. The token is committed before the email goes out, so the
    link is already valid when it lands.
    """
    raw_token = verification.issue_token(db, user)
    db.commit()
    background.add_task(
        send_verification_email,
        user.email,
        user.name,
        verification.build_link(raw_token),
        settings.email_verification_expire_hours,
    )


@router.post("/register", response_model=RegisterResult,
             status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
def register(
    request: Request,
    payload: UserRegister,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Syntax was already checked by EmailStr; this rejects addresses that are
    # well-formed but cannot receive mail (made-up domains, temp-mail services).
    try:
        email = validate_registration_email(payload.email)
    except EmailNotAcceptable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    verification_on = settings.email_verification_enabled
    existing = db.query(User).filter(User.email == email).first()

    if existing is not None:
        # An unverified account is a signup that never finished. Treating it as
        # a hard conflict strands the user: they cannot sign in (not verified)
        # and cannot register again (email taken). Re-sending the link is the
        # only exit, so do that instead of refusing.
        if verification_on and not existing.is_verified:
            elapsed = verification.seconds_since_last_send(db, existing.id)
            if elapsed is not None and elapsed < settings.email_resend_cooldown_seconds:
                wait = int(settings.email_resend_cooldown_seconds - elapsed) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"A confirmation email was just sent. "
                           f"Try again in {wait} seconds.",
                    headers={"Retry-After": str(wait)},
                )
            _queue_verification_email(background, db, existing)
            return RegisterResult(
                verification_required=True, message=_CHECK_INBOX, email=email
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Sign in instead.",
        )

    user = User(
        name=payload.name,
        email=email,
        hashed_password=hash_password(payload.password),
        role=UserRole.user,
        # With no mail transport there is no way to ever confirm the address,
        # so requiring confirmation would create a dead account.
        is_verified=not verification_on,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent registrations for the same email: the unique index is
        # the real guard, the check above is just for a friendly message.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Sign in instead.",
        )
    db.refresh(user)
    logger.info("New user registered id=%s verified=%s", user.id, user.is_verified)

    if verification_on:
        _queue_verification_email(background, db, user)
        return RegisterResult(
            verification_required=True, message=_CHECK_INBOX, email=email
        )

    tokens = _issue_tokens(user)
    return RegisterResult(
        verification_required=False,
        message="Account created.",
        email=email,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.post("/verify-email", response_model=TokenPair)
@limiter.limit(settings.rate_limit_auth)
def verify_email(
    request: Request, payload: EmailVerifyRequest, db: Session = Depends(get_db)
):
    """Redeem a link from a confirmation email and sign the user straight in."""
    user = verification.redeem_token(db, payload.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This confirmation link is invalid or has expired. "
                   "Request a new one from the sign-in page.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled."
        )
    return _issue_tokens(user)


@router.post("/resend-verification", response_model=Message)
@limiter.limit(settings.rate_limit_auth)
def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Send a fresh confirmation link.

    Always reports success. Saying "no such account" here would turn this
    endpoint into a free membership oracle for any address an attacker cares
    to try — the same reason /login has one error message for both failures.
    """
    generic = Message(
        message="If that address needs confirming, a new link is on its way."
    )
    if not settings.email_verification_enabled:
        return generic

    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.is_verified or not user.is_active:
        return generic

    elapsed = verification.seconds_since_last_send(db, user.id)
    if elapsed is not None and elapsed < settings.email_resend_cooldown_seconds:
        # Rate-limited, but still a generic response — the cooldown must not
        # become the tell that distinguishes a real account from a fake one.
        return generic

    _queue_verification_email(background, db, user)
    return generic


@router.post("/login", response_model=TokenPair)
@limiter.limit(settings.rate_limit_auth)
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None:
        # Spend the same CPU as a real bcrypt check so response time does not
        # reveal whether the email is registered.
        burn_dummy_verify(payload.password)
        raise _INVALID_CREDENTIALS
    if not verify_password(payload.password, user.hashed_password):
        raise _INVALID_CREDENTIALS
    if not user.is_active:
        # Checked *after* the password so a disabled-account response cannot be
        # used to enumerate which emails exist.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled."
        )
    if settings.email_verification_enabled and not user.is_verified:
        # Also after the password check, for the same reason. The structured
        # detail lets the frontend show a "resend link" button instead of a
        # dead-end error.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "email_not_verified",
                "message": "Confirm your email address before signing in. "
                           "Check your inbox for the link we sent.",
            },
        )
    return _issue_tokens(user)


@router.post("/forgot-password", response_model=Message)
@limiter.limit(settings.rate_limit_auth)
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Email a reset link.

    Always reports the same thing. A "no account with that email" response
    would turn this into a membership oracle for any address an attacker cares
    to try — and password-reset forms are the classic place people forget that,
    because the honest error feels more helpful.
    """
    generic = Message(
        message="If an account exists for that address, a reset link is on its way. "
                "Check your inbox, and your spam folder."
    )
    if not settings.mail_configured:
        # Nothing can be delivered, so promising a link would be a lie. The
        # response stays generic — the caller still learns nothing about
        # whether the account exists.
        logger.error("Password reset requested but no mail transport is configured")
        return generic

    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        return generic

    elapsed = password_reset.seconds_since_last_send(db, user.id)
    if elapsed is not None and elapsed < settings.password_reset_cooldown_seconds:
        # Rate-limited, but still a generic response — the cooldown must not
        # become the tell that distinguishes a real account from a fake one.
        return generic

    raw_token = password_reset.issue_token(db, user)
    db.commit()
    background.add_task(
        send_password_reset_email,
        user.email,
        user.name,
        password_reset.build_link(raw_token),
        settings.password_reset_expire_hours,
    )
    logger.info("Password reset link sent for user id=%s", user.id)
    return generic


@router.post("/reset-password", response_model=TokenPair)
@limiter.limit(settings.rate_limit_auth)
def reset_password(
    request: Request, payload: PasswordResetRequest, db: Session = Depends(get_db)
):
    """Set a new password from a reset link, and sign the user in.

    Signing them in is safe: holding the link already proves control of the
    inbox, which is the same bar the confirmation flow uses. Making them type
    the password they just chose adds friction without adding a check.
    """
    user = password_reset.redeem_token(db, payload.token, payload.new_password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid, already used, or has expired. "
                   "Request a new one from the sign-in page.",
        )
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
def refresh(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token, expected_type=REFRESH)
        user_id = int(data["sub"])
        token_version = int(data.get("ver", 0))
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise _INVALID_REFRESH

    user = db.get(User, user_id)
    if user is None or not user.is_active or token_version != user.token_version:
        raise _INVALID_REFRESH
    return _issue_tokens(user)


@router.post("/logout", response_model=Message)
def logout(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Invalidate every token issued to this account, on every device.

    Clearing localStorage in the browser is not logout — the tokens stay valid
    until they expire. Bumping token_version makes them unusable immediately.
    """
    current.token_version += 1
    db.commit()
    logger.info("User %s logged out (all sessions revoked)", current.id)
    return Message(message="Signed out on all devices.")


@router.post("/change-password", response_model=TokenPair)
@limiter.limit(settings.rate_limit_auth)
def change_password(
    request: Request,
    payload: PasswordChange,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current one.",
        )
    current.hashed_password = hash_password(payload.new_password)
    # Old sessions must not survive a password change.
    current.token_version += 1
    db.commit()
    db.refresh(current)
    logger.info("User %s changed password", current.id)
    return _issue_tokens(current)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current
