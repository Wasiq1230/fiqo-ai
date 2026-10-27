"""Reusable FastAPI dependencies for authentication and authorization."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.security import ACCESS, decode_token

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_EXC
    try:
        payload = decode_token(credentials.credentials, expected_type=ACCESS)
        user_id = int(payload["sub"])
        token_version = int(payload.get("ver", 0))
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise _CREDENTIALS_EXC

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXC
    # Reject tokens minted before the last logout / password change / ban.
    if token_version != user.token_version:
        raise _CREDENTIALS_EXC
    return user


def require_admin(current: User = Depends(get_current_user)) -> User:
    if current.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )
    return current
