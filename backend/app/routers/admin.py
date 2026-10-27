"""
Admin routes (Phase 8). All endpoints require an admin token via `require_admin`.

Capabilities:
- Users:    list / search / filter, activate-deactivate, change role
- Feedback: list / search / filter / paginate, view one, update status + note, delete
- Analytics: totals by type and status, user counts
- Export:   CSV download of feedback (respects the same filters as the list)

Everything is parameterised through SQLAlchemy's expression API (bound
parameters), so there is no SQL string interpolation and thus no SQL-injection
surface even on the free-text search box.
"""
import csv
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import Feedback, FeedbackStatus, FeedbackType, User, UserRole
from app.schemas import (
    FeedbackList,
    FeedbackOut,
    FeedbackUpdate,
    Message,
    UserOut,
)

logger = logging.getLogger("FiQO.admin")

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ── Users ───────────────────────────────────────────────────────────────────


@router.get("/users", response_model=list[UserOut], summary="List / search users")
def list_users(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=200, description="Search name or email"),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    return query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()


@router.patch("/users/{user_id}/status", response_model=UserOut, summary="Enable/disable a user")
def set_user_active(
    user_id: int,
    is_active: bool,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == admin.id and not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )
    user.is_active = is_active
    if not is_active:
        # Blocking future logins is not enough — revoke live tokens too.
        user.token_version += 1
    db.commit()
    db.refresh(user)
    logger.info("Admin %s set user %s active=%s", admin.id, user_id, is_active)
    return user


@router.patch("/users/{user_id}/role", response_model=UserOut, summary="Change a user's role")
def set_user_role(
    user_id: int,
    role: UserRole,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == admin.id and role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role.",
        )
    user.role = role
    db.commit()
    db.refresh(user)
    logger.info("Admin %s set user %s role=%s", admin.id, user_id, role.value)
    return user


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=Message,
    summary="Force-logout a user on every device",
)
def revoke_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Invalidate all of a user's tokens right now.

    Deactivating an account already blocks new requests, but this also kills
    outstanding refresh tokens so a compromised session cannot be resumed if
    the account is re-enabled.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.token_version += 1
    db.commit()
    logger.info("Admin %s revoked all sessions for user %s", admin.id, user_id)
    return Message(message="All sessions for this user have been revoked.")


# ── Feedback query helper ─────────────────────────────────────────────────


def _feedback_query(
    db: Session,
    q: str | None,
    type_: FeedbackType | None,
    status_: FeedbackStatus | None,
):
    query = db.query(Feedback)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Feedback.subject.ilike(like),
                Feedback.message.ilike(like),
                Feedback.name.ilike(like),
                Feedback.email.ilike(like),
            )
        )
    if type_ is not None:
        query = query.filter(Feedback.type == type_)
    if status_ is not None:
        query = query.filter(Feedback.status == status_)
    return query


# ── Feedback ────────────────────────────────────────────────────────────────


@router.get("/feedback", response_model=FeedbackList, summary="List / search / filter feedback")
def list_feedback(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=200),
    type_: FeedbackType | None = Query(default=None, alias="type"),
    status_: FeedbackStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = _feedback_query(db, q, type_, status_)
    total = query.with_entities(func.count(Feedback.id)).scalar() or 0
    items = query.order_by(Feedback.created_at.desc()).limit(limit).offset(offset).all()
    return FeedbackList(total=total, items=items)


@router.get("/feedback/{feedback_id}", response_model=FeedbackOut, summary="View one submission")
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    entry = db.get(Feedback, feedback_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found.")
    return entry


@router.patch(
    "/feedback/{feedback_id}",
    response_model=FeedbackOut,
    summary="Update status / add an admin note (resolve a complaint)",
)
def update_feedback(
    feedback_id: int,
    payload: FeedbackUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    entry = db.get(Feedback, feedback_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found.")

    if payload.status is not None:
        entry.status = payload.status
        # Stamp resolution time when moving into a terminal state.
        if payload.status in (FeedbackStatus.resolved, FeedbackStatus.closed):
            entry.resolved_at = datetime.now(timezone.utc)
        else:
            entry.resolved_at = None
    if payload.admin_note is not None:
        entry.admin_note = payload.admin_note.strip() or None

    db.commit()
    db.refresh(entry)
    logger.info("Admin %s updated feedback %s status=%s", admin.id, feedback_id, entry.status.value)
    return entry


@router.delete("/feedback/{feedback_id}", response_model=Message, summary="Delete a submission")
def delete_feedback(feedback_id: int, db: Session = Depends(get_db)):
    entry = db.get(Feedback, feedback_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found.")
    db.delete(entry)
    db.commit()
    return Message(message="Feedback deleted.")


# ── Analytics ───────────────────────────────────────────────────────────────


@router.get("/analytics", summary="Dashboard metrics")
def analytics(db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    total_feedback = db.query(func.count(Feedback.id)).scalar() or 0

    by_type = dict(
        db.query(Feedback.type, func.count(Feedback.id)).group_by(Feedback.type).all()
    )
    by_status = dict(
        db.query(Feedback.status, func.count(Feedback.id)).group_by(Feedback.status).all()
    )

    return {
        "users": {"total": total_users, "active": active_users},
        "feedback": {
            "total": total_feedback,
            "by_type": {t.value: by_type.get(t, 0) for t in FeedbackType},
            "by_status": {s.value: by_status.get(s, 0) for s in FeedbackStatus},
        },
    }


# ── Export ──────────────────────────────────────────────────────────────────

# Excel, LibreOffice and Google Sheets execute any cell that begins with one of
# these characters. Feedback is submitted by the public, so an attacker could
# send a message like  =HYPERLINK("http://evil","click")  or a DDE payload and
# have it run on the machine of whichever admin opens the export. Prefixing with
# a single quote makes the cell inert while still displaying the original text.
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str | None) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_CSV_INJECTION_PREFIXES):
        return "'" + text
    return text



@router.get("/feedback-export", summary="Export feedback as CSV (respects filters)")
def export_feedback(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=200),
    type_: FeedbackType | None = Query(default=None, alias="type"),
    status_: FeedbackStatus | None = Query(default=None, alias="status"),
):
    rows = (
        _feedback_query(db, q, type_, status_)
        .order_by(Feedback.created_at.desc())
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "type", "status", "name", "email", "subject", "message",
         "admin_note", "user_id", "created_at", "resolved_at"]
    )
    for r in rows:
        writer.writerow([
            r.id, r.type.value, r.status.value,
            _csv_safe(r.name), _csv_safe(r.email), _csv_safe(r.subject),
            _csv_safe(r.message), _csv_safe(r.admin_note or ""), r.user_id or "",
            r.created_at.isoformat() if r.created_at else "",
            r.resolved_at.isoformat() if r.resolved_at else "",
        ])

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="feedback-{stamp}.csv"'},
    )
