"""Presentation tier: Manual entries API delegates to ManualEntryService."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.campus_scope import check_employee_code
from app.database import get_db
from app.schemas.manual_entry import ManualEntryCreate, ManualEntryOut, ManualEntryUpdate
from app.services.manual_entry_service import ManualEntryService

router = APIRouter()


def _get_manual_entry_service(db: Session = Depends(get_db)) -> ManualEntryService:
    return ManualEntryService(db)


@router.get("/my", response_model=List[ManualEntryOut])
def list_my_manual_entries(
    employee_code: str = Query(..., min_length=1),
    from_date: Optional[datetime] = Query(default=None),
    to_date: Optional[datetime] = Query(default=None),
    service: ManualEntryService = Depends(_get_manual_entry_service),
    _user=Depends(get_current_user),
) -> List[ManualEntryOut]:
    return service.list_my(employee_code, from_date=from_date, to_date=to_date)


@router.post("/apply", response_model=ManualEntryOut, status_code=201)
def apply_manual_entry(
    payload: ManualEntryCreate,
    service: ManualEntryService = Depends(_get_manual_entry_service),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> ManualEntryOut:
    check_employee_code(db, user, payload.EmployeeCode)
    return service.apply(payload)


@router.put("/{manual_entry_id}", response_model=ManualEntryOut)
def update_manual_entry(
    manual_entry_id: int,
    payload: ManualEntryUpdate,
    service: ManualEntryService = Depends(_get_manual_entry_service),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> ManualEntryOut:
    _check_entry(db, user, manual_entry_id)
    return service.update(manual_entry_id, payload)


@router.delete("/{manual_entry_id}")
def delete_manual_entry(
    manual_entry_id: int,
    service: ManualEntryService = Depends(_get_manual_entry_service),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict[str, bool]:
    _check_entry(db, user, manual_entry_id)
    return service.delete(manual_entry_id)


def _check_entry(db: Session, user, manual_entry_id: int) -> None:
    """A campus login may only change entries of its own institution's staff."""
    from app.models.entities import ManualEntry
    row = db.get(ManualEntry, manual_entry_id)
    if row is not None:
        check_employee_code(db, user, row.EmployeeCode)
