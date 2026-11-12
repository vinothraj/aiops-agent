import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.database.session import get_db
from app.models.models import User
from app.services.auth import (
    check_lockout, clear_failures, get_current_user, issue_token, record_failure, require_admin,
)

router = APIRouter()  # public: register, login
users_router = APIRouter()  # authenticated

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class RoleUpdate(BaseModel):
    role: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    status: str
    created_at: datetime
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    user: UserOut


def _check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail=f"Password must be at least {MIN_PASSWORD} characters.")


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Creates a pending account. It cannot sign in until an administrator approves it."""
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required.")
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    _check_password_strength(payload.password)
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    db.add(User(email=email, name=name, password_hash=hash_password(payload.password), role="user", status="pending"))
    db.commit()
    return {"message": "Registration received. An administrator must approve your account before you can sign in."}


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    check_lockout(email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    clear_failures(email)
    # Only revealed after the password is verified, so it cannot be used to probe for accounts.
    if user.status == "pending":
        raise HTTPException(status_code=403, detail="Your account is awaiting administrator approval.")
    if user.status == "rejected":
        raise HTTPException(status_code=403, detail="Your access request was declined. Contact an administrator.")
    if user.status == "disabled":
        raise HTTPException(status_code=403, detail="Your account has been disabled. Contact an administrator.")
    user.last_login_at = datetime.utcnow()
    db.commit()
    return LoginResponse(access_token=issue_token(user), user=UserOut.model_validate(user))


@users_router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@users_router.post("/change-password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    _check_password_strength(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated."}


# Admin: user management

admin_router = APIRouter()


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@admin_router.get("", response_model=List[UserOut])
def list_users(status: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(User).order_by(User.created_at.desc())
    if status:
        stmt = stmt.where(User.status == status)
    return db.execute(stmt).scalars().all()


def _set_status(db: Session, admin: User, user_id: int, new_status: str) -> User:
    user = _get_user(db, user_id)
    if user.id == admin.id and new_status != "approved":
        raise HTTPException(status_code=400, detail="You cannot revoke your own access.")
    user.status = new_status
    if new_status == "approved":
        user.approved_by = admin.email
        user.approved_at = datetime.utcnow()
    db.commit()
    return user


@admin_router.post("/{user_id}/approve", response_model=UserOut)
def approve(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return _set_status(db, admin, user_id, "approved")


@admin_router.post("/{user_id}/reject", response_model=UserOut)
def reject(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return _set_status(db, admin, user_id, "rejected")


@admin_router.post("/{user_id}/disable", response_model=UserOut)
def disable(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return _set_status(db, admin, user_id, "disabled")


@admin_router.put("/{user_id}/role", response_model=UserOut)
def set_role(user_id: int, payload: RoleUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if payload.role not in ("user", "admin"):
        raise HTTPException(status_code=422, detail="Role must be 'user' or 'admin'.")
    user = _get_user(db, user_id)
    if user.id == admin.id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role.")
    user.role = payload.role
    db.commit()
    return user
