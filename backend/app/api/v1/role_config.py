"""Presentation tier: Role config API delegates to RoleConfigService."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.services.campus_scope import (
    DEFAULT_CAMPUS_PERMISSIONS, delete_campus_role, list_campus_roles, save_campus_role,
)
from app.schemas.role_config import RoleConfigOut, RoleConfigUpdate
from app.services.role_config_service import RoleConfigService

router = APIRouter()


def _get_role_config_service(db: Session = Depends(get_db)) -> RoleConfigService:
    return RoleConfigService(db)


@router.get("", response_model=RoleConfigOut)
def get_role_config(
    service: RoleConfigService = Depends(_get_role_config_service),
    _user=Depends(get_current_user),
) -> RoleConfigOut:
    return service.get_config()


@router.put("", response_model=RoleConfigOut)
def update_role_config(
    payload: RoleConfigUpdate,
    service: RoleConfigService = Depends(_get_role_config_service),
    _user=Depends(get_current_user),
) -> RoleConfigOut:
    return service.update_config(payload)


# ---- Campus roles: a role limited to one institution (e.g. "Campus 2" -> Engineering Campus Staff) ----

class CampusRoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    organization_id: Optional[int] = None   # None = all institutions (e.g. Leave Section)
    permissions: dict[str, bool] = Field(default_factory=dict)
    original_name: Optional[str] = None   # set when renaming an existing campus role


@router.get("/campus-roles")
def get_campus_roles(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> dict:
    """Campus roles, plus the menu set a new one starts with."""
    return {"roles": list_campus_roles(db), "default_permissions": DEFAULT_CAMPUS_PERMISSIONS}


@router.put("/campus-roles")
def put_campus_role(payload: CampusRoleIn, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> dict:
    """Create or update a campus role (a rename also moves the logins that use it)."""
    return save_campus_role(db, payload.name, payload.organization_id, payload.permissions, payload.original_name)


@router.delete("/campus-roles/{name}")
def remove_campus_role(name: str, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> dict:
    delete_campus_role(db, name)
    return {"deleted": True}
