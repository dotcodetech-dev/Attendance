"""Presentation tier: Portal user creation (for employees)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import Employee, User
from app.schemas.user_schema import ResetPasswordRequest, UserCreate, UserLink, UserOut
from app.services.auth_service import AuthService

router = APIRouter()


def _get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    service: AuthService = Depends(_get_auth_service),
    _user=Depends(get_current_user),
) -> UserOut:
    user = service.create_user(payload.login_name, payload.password, payload.role_name, payload.employee_code)
    return UserOut(UserId=user.UserId, LoginName=user.LoginName, RoleName=user.RoleName, EmployeeCode=user.EmployeeCode)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> list[UserOut]:
    return [
        UserOut(UserId=u.UserId, LoginName=u.LoginName, RoleName=u.RoleName, EmployeeCode=u.EmployeeCode)
        for u in db.query(User).order_by(User.LoginName).all()
    ]


@router.post("/link", response_model=UserOut)
def link_user(payload: UserLink, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> UserOut:
    """Link an existing login to an employee and/or change its role (used to set up approvers)."""
    from fastapi import HTTPException
    user = db.query(User).filter(User.LoginName == payload.login_name.strip()).first()
    if not user:
        raise HTTPException(404, "User not found")
    code = (payload.employee_code or "").strip() or None
    if code and not db.query(Employee.EmployeeId).filter(Employee.EmployeeCode == code).first():
        raise HTTPException(400, "Employee code not found")
    user.EmployeeCode = code
    if payload.role_name:
        user.RoleName = payload.role_name.strip()
    db.commit()
    return UserOut(UserId=user.UserId, LoginName=user.LoginName, RoleName=user.RoleName, EmployeeCode=user.EmployeeCode)


@router.post("/reset-password", response_model=UserOut)
def reset_password(
    payload: ResetPasswordRequest,
    service: AuthService = Depends(_get_auth_service),
    _user=Depends(get_current_user),
) -> UserOut:
    user = service.reset_password(payload.login_name, payload.new_password)
    return UserOut(UserId=user.UserId, LoginName=user.LoginName, RoleName=user.RoleName)
