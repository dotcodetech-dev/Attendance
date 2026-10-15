"""Presentation tier: Leaves API delegates to LeaveRequestService."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.campus_scope import check_employee_code
from app.database import get_db
from app.schemas.leave_balance import LeaveBalanceOut
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestOut
from app.services.leave_request_service import LeaveRequestService

router = APIRouter()


def _get_leave_request_service(db: Session = Depends(get_db)) -> LeaveRequestService:
    return LeaveRequestService(db)


@router.get("/balance", response_model=List[LeaveBalanceOut])
def get_leave_balance(
    employee_code: str = Query(..., min_length=1),
    year: Optional[int] = Query(default=None),
    service: LeaveRequestService = Depends(_get_leave_request_service),
    _user=Depends(get_current_user),
) -> List[LeaveBalanceOut]:
    balances = service.get_balance(employee_code, year)
    return [LeaveBalanceOut(**b) for b in balances]


@router.get("/days")
def preview_leave_days(
    employee_code: str = Query(..., min_length=1),
    leave_config_id: int = Query(...),
    from_date: date = Query(...),
    to_date: date = Query(...),
    service: LeaveRequestService = Depends(_get_leave_request_service),
    _user=Depends(get_current_user),
):
    """Days a leave over these dates would deduct, after skipping weekly offs / holidays it does not count."""
    return service.preview_days(employee_code, leave_config_id, from_date, to_date)


@router.get("/my", response_model=List[LeaveRequestOut])
def list_my_leaves(
    employee_code: str = Query(..., min_length=1),
    from_date: Optional[datetime] = Query(default=None),
    to_date: Optional[datetime] = Query(default=None),
    service: LeaveRequestService = Depends(_get_leave_request_service),
    _user=Depends(get_current_user),
) -> List[LeaveRequestOut]:
    return service.list_my(employee_code, from_date=from_date, to_date=to_date)


@router.post("/apply", response_model=LeaveRequestOut, status_code=201)
def apply_leave(
    payload: LeaveRequestCreate,
    service: LeaveRequestService = Depends(_get_leave_request_service),
    user=Depends(get_current_user),
) -> LeaveRequestOut:
    check_employee_code(service._session, user, payload.EmployeeCode)
    return service.apply_leave(payload)


@router.post("/admin-entry", response_model=LeaveRequestOut, status_code=201)
def admin_leave_entry(
    payload: LeaveRequestCreate,
    service: LeaveRequestService = Depends(_get_leave_request_service),
    user=Depends(get_current_user),
) -> LeaveRequestOut:
    """Admin enters a leave for an employee: saved as Approved straight away, no approval steps."""
    check_employee_code(service._session, user, payload.EmployeeCode)   # campus login: its own staff only
    return service.admin_entry(payload, user)


@router.post("/{leave_request_id}/cancel", response_model=LeaveRequestOut)
def admin_cancel_leave(
    leave_request_id: int,
    service: LeaveRequestService = Depends(_get_leave_request_service),
    user=Depends(get_current_user),
) -> LeaveRequestOut:
    """Admin undoes a leave (e.g. entered by mistake); its days return to the balance."""
    return service.admin_cancel(leave_request_id, user)
