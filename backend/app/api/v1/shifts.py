"""Presentation tier: Shift API delegates to ShiftService."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.schemas.shift import ShiftCreate, ShiftOut, ShiftUpdate
from app.services.shift_service import ShiftService

router = APIRouter()


def _get_shift_service(db: Session = Depends(get_db)) -> ShiftService:
    return ShiftService(db)


@router.get("", response_model=List[ShiftOut])
def list_shifts(
    service: ShiftService = Depends(_get_shift_service),
    _user=Depends(get_current_user),
) -> List[ShiftOut]:
    return service.list_all()


@router.post("", response_model=ShiftOut, status_code=201)
def create_shift(
    payload: ShiftCreate,
    service: ShiftService = Depends(_get_shift_service),
    _user=Depends(get_current_user),
) -> ShiftOut:
    return service.create(payload)


@router.put("/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int,
    payload: ShiftUpdate,
    service: ShiftService = Depends(_get_shift_service),
    _user=Depends(get_current_user),
) -> ShiftOut:
    return service.update(shift_id, payload)


@router.delete("/{shift_id}")
def delete_shift(
    shift_id: int,
    service: ShiftService = Depends(_get_shift_service),
    _user=Depends(get_current_user),
) -> dict[str, bool]:
    return service.delete(shift_id)
