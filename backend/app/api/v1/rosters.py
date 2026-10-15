"""Presentation tier: Roster API delegates to RosterService."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.schemas.roster import RosterAssign, RosterCreate, RosterOut, RosterUpdate
from app.services.roster_service import RosterService

router = APIRouter()


def _get_roster_service(db: Session = Depends(get_db)) -> RosterService:
    return RosterService(db)


@router.get("", response_model=List[RosterOut])
def list_rosters(
    employee_code: Optional[str] = Query(default=None),
    service: RosterService = Depends(_get_roster_service),
    _user=Depends(get_current_user),
) -> List[RosterOut]:
    return service.list_all(employee_code)


@router.post("", response_model=RosterOut, status_code=201)
def create_roster(
    payload: RosterCreate,
    service: RosterService = Depends(_get_roster_service),
    _user=Depends(get_current_user),
) -> RosterOut:
    return service.create(payload)


@router.post("/assign")
def assign_shift(
    payload: RosterAssign,
    service: RosterService = Depends(_get_roster_service),
    _user=Depends(get_current_user),
) -> dict:
    """One shift for one or many employees from a date; earlier assignments end the day before."""
    return service.assign(payload)


@router.put("/{roster_id}", response_model=RosterOut)
def update_roster(
    roster_id: int,
    payload: RosterUpdate,
    service: RosterService = Depends(_get_roster_service),
    _user=Depends(get_current_user),
) -> RosterOut:
    return service.update(roster_id, payload)


@router.delete("/{roster_id}")
def delete_roster(
    roster_id: int,
    service: RosterService = Depends(_get_roster_service),
    _user=Depends(get_current_user),
) -> dict[str, bool]:
    return service.delete(roster_id)
