"""Presentation tier: Role config API delegates to RoleConfigService."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
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
