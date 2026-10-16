"""Presentation tier: Portal user creation (for employees) and the Admin's Users & Logins page."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import Employee, Organization, User
from app.schemas.user_schema import ResetPasswordRequest, UserCreate, UserLink, UserOut
from app.services.auth_service import AuthService
from app.services.campus_scope import campus_role, deny_for_campus, is_custom_role
from app.services.employee_status import login_block_reason

router = APIRouter()

_BLOCKED = "Blocked"


def _get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def _is_admin(user: Optional[User]) -> bool:
    if user is None:
        return False
    role = (user.RoleName or "").strip().lower()
    return role == "admin" or (user.LoginName or "").strip().lower() == settings.admin_username.lower()


def _require_admin(user: Optional[User]) -> None:
    if not _is_admin(user):
        raise HTTPException(403, "Only an Admin can manage logins.")


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    service: AuthService = Depends(_get_auth_service),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> UserOut:
    deny_for_campus(db, user, "Creating logins")
    if (payload.role_name or "").strip().lower() == "admin" and not _is_admin(user):
        raise HTTPException(403, "Only an Admin can create another Admin login.")
    created = service.create_user(payload.login_name, payload.password, payload.role_name, payload.employee_code)
    return UserOut(UserId=created.UserId, LoginName=created.LoginName, RoleName=created.RoleName,
                   EmployeeCode=created.EmployeeCode)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> list[UserOut]:
    return [
        UserOut(UserId=u.UserId, LoginName=u.LoginName, RoleName=u.RoleName, EmployeeCode=u.EmployeeCode)
        for u in db.query(User).order_by(User.LoginName).all()
    ]


@router.get("/logins")
def list_logins(db: Session = Depends(get_db), user=Depends(get_current_user)) -> list[dict]:
    """Every login with its role, institution (custom roles), linked employee and whether it can sign in.
    Passwords are stored hashed, so they are never shown; the Admin resets them instead."""
    _require_admin(user)
    users = db.query(User).order_by(User.LoginName).all()
    codes = {u.EmployeeCode for u in users if u.EmployeeCode}
    employees = {e.EmployeeCode: e for e in db.query(Employee).filter(Employee.EmployeeCode.in_(codes))} if codes else {}
    org_names = {o.OrganizationId: o.OrgName for o in db.query(Organization)}
    rows = []
    for u in users:
        emp = employees.get(u.EmployeeCode) if u.EmployeeCode else None
        role = campus_role(db, u.RoleName)
        org_id = role["organization_id"] if role else (emp.OrganizationId if emp is not None else None)
        reason = login_block_reason(db, u)
        rows.append({
            "UserId": u.UserId,
            "LoginName": u.LoginName,
            "RoleName": u.RoleName or "Employee",
            "CustomRole": role is not None,
            "Institution": ("All institutions" if role and org_id is None else org_names.get(org_id)) if (role or org_id) else None,
            "EmployeeCode": u.EmployeeCode,
            "EmployeeName": emp.EmployeeName if emp is not None else None,
            "StringCode": emp.StringCode if emp is not None else None,
            "Department": emp.Department if emp is not None else None,
            "Blocked": (u.Blocked or "").strip().lower() in ("1", "y", "yes", "true", "blocked"),
            "CanSignIn": reason is None,
            "BlockReason": reason,
        })
    if not any((r["LoginName"] or "").lower() == settings.admin_username.lower() for r in rows):
        # The built-in admin lives only in the config until its password is first changed.
        rows.insert(0, {"UserId": 0, "LoginName": settings.admin_username, "RoleName": "Admin", "CustomRole": False,
                        "Institution": None, "EmployeeCode": None, "EmployeeName": None, "StringCode": None,
                        "Department": None, "Blocked": False, "CanSignIn": True, "BlockReason": None})
    return rows


class BlockRequest(BaseModel):
    login_name: str
    blocked: bool


@router.post("/block")
def block_login(payload: BlockRequest, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    _require_admin(user)
    name = payload.login_name.strip()
    if name.lower() == (user.LoginName or "").lower():
        raise HTTPException(400, "You cannot block your own login.")
    target = db.query(User).filter(User.LoginName == name).first()
    if not target:
        raise HTTPException(404, "User not found")
    target.Blocked = _BLOCKED if payload.blocked else None
    if payload.blocked:
        target.AuthToken = None
    db.commit()
    return {"LoginName": target.LoginName, "Blocked": payload.blocked}


@router.post("/link", response_model=UserOut)
def link_user(payload: UserLink, db: Session = Depends(get_db), user=Depends(get_current_user)) -> UserOut:
    """Link an existing login to an employee and/or change its role (used to set up approvers)."""
    deny_for_campus(db, user, "Changing logins")
    target = db.query(User).filter(User.LoginName == payload.login_name.strip()).first()
    if not target:
        raise HTTPException(404, "User not found")
    new_role = (payload.role_name or "").strip()
    if not _is_admin(user) and ("admin" in ((target.RoleName or "").lower(), new_role.lower())):
        raise HTTPException(403, "Only an Admin can change an Admin login.")
    code = (payload.employee_code or "").strip() or None
    if code and not db.query(Employee.EmployeeId).filter(Employee.EmployeeCode == code).first():
        raise HTTPException(400, "Employee code not found")
    target.EmployeeCode = code
    if new_role:
        target.RoleName = new_role
    db.commit()
    return UserOut(UserId=target.UserId, LoginName=target.LoginName, RoleName=target.RoleName, EmployeeCode=target.EmployeeCode)


@router.post("/reset-password", response_model=UserOut)
def reset_password(
    payload: ResetPasswordRequest,
    service: AuthService = Depends(_get_auth_service),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> UserOut:
    """Anyone may change their own password. Changing another login's: an Admin always; other built-in roles
    (Employees page) only for non-Admin logins; custom roles (User Roles) never."""
    name = payload.login_name.strip()
    if not (payload.new_password or "").strip():
        raise HTTPException(400, "Enter the new password.")
    own = name.lower() == (user.LoginName or "").lower()
    if not own and not _is_admin(user):
        if is_custom_role(db, user):
            raise HTTPException(403, "You can change only your own password.")
        target = db.query(User).filter(User.LoginName == name).first()
        if name.lower() == settings.admin_username.lower() or (target and (target.RoleName or "").strip().lower() == "admin"):
            raise HTTPException(403, "Only an Admin can reset an Admin's password.")
    updated = service.reset_password(name, payload.new_password)
    return UserOut(UserId=updated.UserId, LoginName=updated.LoginName, RoleName=updated.RoleName)
