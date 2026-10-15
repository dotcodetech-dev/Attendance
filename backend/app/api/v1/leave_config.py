"""Presentation tier: Leave config API delegates to LeaveConfigService."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.schemas.leave_config import (
    LeaveConfigCreate,
    LeaveConfigOut,
    LeaveConfigUpdate,
)
from app.services.leave_config_service import LeaveConfigService

router = APIRouter()


def _get_leave_config_service(db: Session = Depends(get_db)) -> LeaveConfigService:
    return LeaveConfigService(db)


@router.get("", response_model=List[LeaveConfigOut])
def list_leave_configs(
    service: LeaveConfigService = Depends(_get_leave_config_service),
    _user=Depends(get_current_user),
) -> List[LeaveConfigOut]:
    return service.list_all()


@router.post("", response_model=LeaveConfigOut, status_code=201)
def create_leave_config(
    payload: LeaveConfigCreate,
    service: LeaveConfigService = Depends(_get_leave_config_service),
    _user=Depends(get_current_user),
) -> LeaveConfigOut:
    return service.create(payload)


@router.put("/{config_id}", response_model=LeaveConfigOut)
def update_leave_config(
    config_id: int,
    payload: LeaveConfigUpdate,
    service: LeaveConfigService = Depends(_get_leave_config_service),
    _user=Depends(get_current_user),
) -> LeaveConfigOut:
    return service.update(config_id, payload)


@router.delete("/{config_id}")
def delete_leave_config(
    config_id: int,
    service: LeaveConfigService = Depends(_get_leave_config_service),
    _user=Depends(get_current_user),
) -> dict[str, bool]:
    return service.delete(config_id)
