"""
Feedback & support routes.

Covers Phase 7 (feedback / bug / complaint / feature-request / contact-support).

Design decisions:
- Submission is allowed for anonymous visitors AND signed-in users. If a valid
  Bearer token is present we attach the user id so admins can trace it; if not,
  the submission is stored anonymously. This is why we use an *optional* auth
  dependency here rather than `get_current_user`.
- Spam protection is layered: a hidden honeypot field (`website`, enforced by the
  schema to be empty) plus IP-based rate limiting.
- Users get an immediate confirmation payload back so the frontend can show a
  success state without a second round-trip.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Feedback, User
from app.rate_limit import limiter
from app.schemas import FeedbackCreate, FeedbackOut
from app.security import ACCESS, decode_token

logger = logging.getLogger("FiQO.feedback")
settings = get_settings()

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# Optional auth: we do not want to *require* a token here, but we do want to
# capture the user id when one is supplied.
_optional_bearer = HTTPBearer(auto_error=False)


def _optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: Session = Depends(get_db),
) -> int | None:
    """Return the user id if a valid access token is present, else None."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_token(credentials.credentials, expected_type=ACCESS)
        user_id = int(payload["sub"])
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        return None
    user = db.get(User, user_id)
    return user.id if user and user.is_active else None


@router.post(
    "",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback, a bug report, a complaint, a feature request, or a support request",
)
@limiter.limit(settings.rate_limit_feedback)
def submit_feedback(
    request: Request,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    user_id: int | None = Depends(_optional_user_id),
):
    # Honeypot: the schema enforces `website` must be empty (max_length=0), so a
    # populated value never reaches here. This second check is defence in depth
    # in case the schema constraint is ever relaxed.
    if payload.website:
        logger.warning("Honeypot triggered on feedback submission — dropping.")
        # Pretend success so bots get no signal that they were filtered.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submission rejected.",
        )

    entry = Feedback(
        user_id=user_id,
        type=payload.type,
        name=payload.name,
        email=payload.email.lower(),
        subject=payload.subject,
        message=payload.message,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info(
        "Feedback stored id=%s type=%s user_id=%s", entry.id, entry.type.value, user_id
    )
    return entry


@router.get(
    "/mine",
    response_model=list[FeedbackOut],
    summary="List the signed-in user's own submissions",
)
def my_feedback(
    db: Session = Depends(get_db),
    user_id: int | None = Depends(_optional_user_id),
):
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to view your submissions.",
        )
    return (
        db.query(Feedback)
        .filter(Feedback.user_id == user_id)
        .order_by(Feedback.created_at.desc())
        .all()
    )
