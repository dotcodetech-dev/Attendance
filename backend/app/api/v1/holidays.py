"""Presentation tier: Holiday API delegates to HolidayService."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.schemas.holiday import HolidayCreate, HolidayOut, HolidayUpdate
from app.services.holiday_service import HolidayService

router = APIRouter()


def _get_holiday_service(db: Session = Depends(get_db)) -> HolidayService:
    return HolidayService(db)


@router.get("", response_model=List[HolidayOut])
def list_holidays(
    year: Optional[int] = Query(default=None),
    service: HolidayService = Depends(_get_holiday_service),
    _user=Depends(get_current_user),
) -> List[HolidayOut]:
    return service.list_all(year)


@router.post("", response_model=HolidayOut, status_code=201)
def create_holiday(
    payload: HolidayCreate,
    service: HolidayService = Depends(_get_holiday_service),
    _user=Depends(get_current_user),
) -> HolidayOut:
    return service.create(payload)


@router.put("/{holiday_id}", response_model=HolidayOut)
def update_holiday(
    holiday_id: int,
    payload: HolidayUpdate,
    service: HolidayService = Depends(_get_holiday_service),
    _user=Depends(get_current_user),
) -> HolidayOut:
    return service.update(holiday_id, payload)


@router.delete("/{holiday_id}")
def delete_holiday(
    holiday_id: int,
    service: HolidayService = Depends(_get_holiday_service),
    _user=Depends(get_current_user),
) -> dict[str, bool]:
    return service.delete(holiday_id)
