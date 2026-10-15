"""Leave approval: HOD / Manager, then Principal / Director."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.services import leave_approval_service as svc

router = APIRouter()


class DecisionIn(BaseModel):
    action: str  # Approved | Rejected
    remarks: Optional[str] = None


@router.get("/me")
def me(db: Session = Depends(get_db), user=Depends(get_current_user)):
    emp = svc.employee_of(db, user)
    return {
        "login": user.LoginName,
        "role": user.RoleName,
        "kind": svc.role_kind(user),
        "employee_code": emp.EmployeeCode if emp else None,
        "employee_name": emp.EmployeeName if emp else None,
        "department": emp.Department if emp else None,
        "waiting": svc.waiting_count(db, user),
    }


@router.get("")
def list_requests(
    tab: str = Query(default="waiting", pattern="^(waiting|open|decided|all)$"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return svc.list_requests(db, user, tab)


@router.get("/approvers")
def approvers(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return svc.approvers_overview(db)


@router.post("/{request_id}/decision")
def decision(request_id: int, payload: DecisionIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return svc.decide(db, user, request_id, payload.action, payload.remarks)
