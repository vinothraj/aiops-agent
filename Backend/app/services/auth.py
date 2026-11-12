import logging
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_token, decode_token, hash_password
from app.database.session import SessionLocal, get_db
from app.models.models import AppSetting, User

logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)
_secret_cache: Optional[str] = None


def get_secret() -> str:
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    if settings.AUTH_SECRET_KEY:
        _secret_cache = settings.AUTH_SECRET_KEY
        return _secret_cache
    db = SessionLocal()
    try:
        row = db.execute(select(AppSetting).where(AppSetting.key == "auth_secret")).scalar_one_or_none()
        if not row:
            row = AppSetting(key="auth_secret", value=secrets.token_urlsafe(48))
            db.add(row)
            db.commit()
        _secret_cache = row.value
        return _secret_cache
    finally:
        db.close()


def issue_token(user: User) -> str:
    return create_token(get_secret(), user.id, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not creds:
        raise unauthorized
    user_id = decode_token(get_secret(), creds.credentials)
    user = db.get(User, user_id) if user_id else None
    # Status is re-checked on every request, so disabling a user cuts access at once.
    if not user or user.status != "approved":
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


# Login throttling (per email, in memory)
_MAX_FAILURES = 5
_LOCK_SECONDS = 300
_failures: dict = {}


def check_lockout(email: str) -> None:
    count, first = _failures.get(email, (0, 0.0))
    if count >= _MAX_FAILURES:
        remaining = int(first + _LOCK_SECONDS - time.time())
        if remaining > 0:
            raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {remaining // 60 + 1} minute(s).")
        _failures.pop(email, None)


def record_failure(email: str) -> None:
    count, first = _failures.get(email, (0, time.time()))
    _failures[email] = (count + 1, first)


def clear_failures(email: str) -> None:
    _failures.pop(email, None)


def seed_admin() -> None:
    """Creates the bootstrap admin from ADMIN_EMAIL/ADMIN_PASSWORD if no admin exists."""
    db = SessionLocal()
    try:
        has_admin = db.execute(select(User).where(User.role == "admin", User.status == "approved")).first()
        if has_admin:
            return
        if not settings.ADMIN_PASSWORD:
            logger.warning("No administrator exists and ADMIN_PASSWORD is not set; nobody can approve users. Set ADMIN_EMAIL/ADMIN_PASSWORD in Backend/.env.")
            return
        email = settings.ADMIN_EMAIL.strip().lower()
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user:
            user.role, user.status = "admin", "approved"
            user.password_hash = hash_password(settings.ADMIN_PASSWORD)
        else:
            db.add(User(email=email, name=settings.ADMIN_NAME, password_hash=hash_password(settings.ADMIN_PASSWORD),
                        role="admin", status="approved", approved_by="system"))
        db.commit()
        logger.info("Bootstrap administrator ready: %s", email)
    finally:
        db.close()
