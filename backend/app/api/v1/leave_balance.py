"""Admin API for per-employee leave entitlements (EmployeeLeaveBalance)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.campus_scope import check_employee_code, deny_for_campus, is_custom_role, role_allows, user_org_id
from app.database import get_db
from app.models.entities import Employee, EmployeeLeaveBalance, LeaveConfig
from app.schemas.employee_leave_balance import (
    EmployeeLeaveBalanceOut, EmployeeLeaveBalanceSet, SeedResult,
)

router = APIRouter()


@router.get("/employee/{employee_code}", response_model=List[EmployeeLeaveBalanceOut])
def get_employee_balances(
    employee_code: str,
    year: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    One row per active leave type for the employee/year: the per-employee
    entitlement if set, else the leave type's default MaxPerYear.
    """
    year = year or datetime.utcnow().year
    configs = db.query(LeaveConfig).filter(LeaveConfig.IsActive == "Y").all()
    overrides = {
        row.LeaveConfigId: row
        for row in db.query(EmployeeLeaveBalance)
        .filter(EmployeeLeaveBalance.EmployeeCode == employee_code)
        .filter(EmployeeLeaveBalance.LeaveYear == year)
        .all()
    }
    out = []
    for c in configs:
        row = overrides.get(c.LeaveConfigId)
        allowed = float(row.AllowedLeaves) if row else float(c.MaxPerYear or 0)
        carried = float(row.CarriedForward) if row else 0.0
        out.append(EmployeeLeaveBalanceOut(
            EmployeeLeaveBalanceId=row.EmployeeLeaveBalanceId if row else 0,
            EmployeeCode=employee_code,
            LeaveConfigId=c.LeaveConfigId,
            Code=c.Code,
            Name=c.Name,
            LeaveYear=year,
            AllowedLeaves=allowed,
            CarriedForward=carried,
        ))
    return out


@router.put("/employee", response_model=EmployeeLeaveBalanceOut)
def set_employee_balance(
    payload: EmployeeLeaveBalanceSet,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Set/override an employee's entitlement for one leave type + year."""
    check_employee_code(db, user, payload.EmployeeCode)
    employee = db.query(Employee).filter(Employee.EmployeeCode == payload.EmployeeCode).first()
    if not employee:
        raise HTTPException(404, "Employee not found")
    config = db.query(LeaveConfig).filter(LeaveConfig.LeaveConfigId == payload.LeaveConfigId).first()
    if not config:
        raise HTTPException(404, "Leave type not found")

    row = (
        db.query(EmployeeLeaveBalance)
        .filter(EmployeeLeaveBalance.EmployeeCode == payload.EmployeeCode)
        .filter(EmployeeLeaveBalance.LeaveConfigId == payload.LeaveConfigId)
        .filter(EmployeeLeaveBalance.LeaveYear == payload.LeaveYear)
        .first()
    )
    if row is None:
        row = EmployeeLeaveBalance(
            EmployeeCode=payload.EmployeeCode,
            LeaveConfigId=payload.LeaveConfigId,
            LeaveYear=payload.LeaveYear,
        )
        db.add(row)
    row.AllowedLeaves = payload.AllowedLeaves
    row.CarriedForward = payload.CarriedForward
    db.commit()
    db.refresh(row)
    return EmployeeLeaveBalanceOut(
        EmployeeLeaveBalanceId=row.EmployeeLeaveBalanceId,
        EmployeeCode=row.EmployeeCode,
        LeaveConfigId=row.LeaveConfigId,
        Code=config.Code,
        Name=config.Name,
        LeaveYear=row.LeaveYear,
        AllowedLeaves=float(row.AllowedLeaves),
        CarriedForward=float(row.CarriedForward),
    )


@router.post("/seed", response_model=SeedResult)
def seed_balances(
    year: int = Query(...),
    overwrite: bool = Query(default=False),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # Every employee of every institution: only an Admin, or a custom role for all institutions with "Leave Types".
    if is_custom_role(db, user) and (user_org_id(db, user) is not None or not role_allows(db, user, "config_leaves")):
        deny_for_campus(db, user, "Setting up every employee's balances")
    """
    Initialise per-employee balances for a year from each leave type's MaxPerYear.
    Skips employee/type rows that already exist unless overwrite=true.
    """
    employees = [r[0] for r in db.query(Employee.EmployeeCode).all() if r[0]]
    configs = db.query(LeaveConfig).filter(LeaveConfig.IsActive == "Y").all()
    existing = {
        (r.EmployeeCode, r.LeaveConfigId)
        for r in db.query(EmployeeLeaveBalance).filter(EmployeeLeaveBalance.LeaveYear == year).all()
    }
    written = 0
    for code in employees:
        for c in configs:
            if (code, c.LeaveConfigId) in existing and not overwrite:
                continue
            row = (
                db.query(EmployeeLeaveBalance)
                .filter(EmployeeLeaveBalance.EmployeeCode == code)
                .filter(EmployeeLeaveBalance.LeaveConfigId == c.LeaveConfigId)
                .filter(EmployeeLeaveBalance.LeaveYear == year)
                .first()
            )
            if row is None:
                row = EmployeeLeaveBalance(
                    EmployeeCode=code, LeaveConfigId=c.LeaveConfigId, LeaveYear=year,
                )
                db.add(row)
            row.AllowedLeaves = float(c.MaxPerYear or 0)
            row.CarriedForward = row.CarriedForward or 0
            written += 1
        db.flush()
    db.commit()
    return SeedResult(year=year, employees=len(employees), rows_written=written)
