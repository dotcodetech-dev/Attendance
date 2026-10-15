"""Presentation tier: Auth API delegates to AuthService."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import Organization
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth_service import AuthService
from app.services.campus_scope import campus_role

router = APIRouter()


def _get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    result = service.login(payload.username, payload.password)
    return TokenResponse(access_token=result["access_token"])


@router.get("/me")
def me(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """Who is signed in. For a campus role (User Roles): its institution and the menus it may open; the screens hide
    the rest. Everyone else gets `campus: null` and is not limited here."""
    role = campus_role(db, getattr(user, "RoleName", None))
    org_name = None
    if role and role["organization_id"]:
        org = db.get(Organization, role["organization_id"])
        org_name = org.OrgName if org else None
    return {
        "login": getattr(user, "LoginName", None),
        "role": getattr(user, "RoleName", None),
        "campus": None if role is None else {
            "role": role["name"],
            "organization_id": role["organization_id"],
            "organization_name": org_name,
            "permissions": role["permissions"],
        },
    }
