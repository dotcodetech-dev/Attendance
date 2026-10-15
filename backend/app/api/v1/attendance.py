from __future__ import annotations
import calendar
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.campus_scope import check_employee_code, deny_for_campus, user_org_id
from app.database import get_db
from app.models.entities import AttendanceProcessed, DeviceLog, Employee
from app.schemas.attendance import AttendanceLogOut
from app.schemas.attendance_summary import (
    AttendanceDayOut, AttendanceMonthSummaryOut,
    ProcessedAttendanceOut, RecalculateRequest, RecalculateResult,
)
from app.services.attendance_export import build_attendance_csv, export_attendance
from app.services.attendance_processing import (
    LATE_PENALTY_REMARK, build_employee_context, compute_range, process_range,
)
from app.services.attendance_settings import (
    DIRECTION_MODES, MODES, get_late_rule, get_punch_rule, set_late_rule, set_punch_rule,
)

router = APIRouter()

_STATUS_COUNTER = {"P": "present", "H": "half", "A": "absent", "L": "leave", "O": "off", "W": "off"}


@router.get("/logs", response_model=list[AttendanceLogOut])
def get_logs(
    device_id: Optional[int] = None,
    employee_code: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(DeviceLog)
    org = user_org_id(db, user)
    if org is not None:   # campus login: punches of its institution's staff only
        query = query.filter(DeviceLog.EmployeeCode.in_(
            db.query(Employee.EmployeeCode).filter(Employee.OrganizationId == org)))
    if device_id is not None:
        query = query.filter(DeviceLog.DeviceId == device_id)
    if employee_code:
        query = query.filter(DeviceLog.EmployeeCode == employee_code)
    if from_date:
        query = query.filter(DeviceLog.LogDate >= from_date)
    if to_date:
        query = query.filter(DeviceLog.LogDate <= to_date)
    rows = query.order_by(DeviceLog.LogDate.desc()).limit(limit).all()
    return [
        AttendanceLogOut(
            DeviceLogId=row.DeviceLogId,
            DeviceId=row.DeviceId,
            EmployeeCode=row.EmployeeCode,
            LogDate=row.LogDate,
            VerificationType=row.VerificationType,
            Direction=row.Direction,
            HasPhoto=bool(row.AttPhoto),
        )
        for row in rows
    ]


@router.get("/employee-summary", response_model=AttendanceMonthSummaryOut)
def get_employee_month_summary(
    employee_code: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    employee = (
        db.query(Employee)
        .filter(Employee.EmployeeCode == employee_code)
        .first()
    )
    month = max(1, min(month, 12))
    year = max(2000, min(year, 2100))
    _, days_in_month = calendar.monthrange(year, month)
    month_start = datetime(year, month, 1)
    month_end = datetime(year, month, days_in_month, 23, 59, 59)

    # Shared computation, identical to the recalc processor (including the sandwich and
    # late-count rules), so the live view and attendance_processed can never diverge.
    ctx = build_employee_context(db, employee_code, month_start, month_end)
    results = compute_range(db, employee_code, month_start.date(), month_end.date())

    day_rows: list[AttendanceDayOut] = []
    counts = {"present": 0, "half": 0, "absent": 0, "leave": 0, "off": 0}

    for result in results:
        current_date = result.attendance_date
        day_num = current_date.day
        counts[_STATUS_COUNTER[result.status]] += 1
        day_rows.append(
            AttendanceDayOut(
                AttendanceDate=current_date,
                DayNumber=day_num,
                DayLabel=current_date.strftime("%a"),
                Status=result.status,
                StatusLabel=result.status_label,
                ShiftName=result.shift_name,
                ShiftTime=result.shift_time,
                FirstIn=result.first_in,
                LastOut=result.last_out,
                TotalLogs=result.total_logs,
                ActualWorkMinutes=result.actual_work_minutes,
                Remarks=result.remarks,
            )
        )

    category = ctx.category
    return AttendanceMonthSummaryOut(
        EmployeeCode=employee_code,
        EmployeeName=employee.EmployeeName if employee else None,
        Department=employee.Department if employee else None,
        CategoryName=category.CategoryName if category else None,
        Year=year,
        Month=month,
        MonthLabel=f"{calendar.month_name[month]} {year}",
        PresentDays=counts["present"],
        HalfDays=counts["half"],
        AbsentDays=counts["absent"],
        LeaveDays=counts["leave"],
        OffDays=counts["off"],
        days=day_rows,
    )


class LateRuleIn(BaseModel):
    enabled: bool
    days: int
    mode: str
    # Punch handling (optional so older clients keep working)
    duplicate_seconds: Optional[int] = None
    direction_mode: Optional[str] = None


def _rule_out(rule) -> dict:
    return {"enabled": rule.enabled, "days": rule.days, "mode": rule.mode}


def _punch_out(rule) -> dict:
    return {"duplicate_seconds": rule.duplicate_seconds, "direction_mode": rule.direction_mode}


@router.get("/rules")
def get_rules(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Attendance calculation settings shared by everyone."""
    return {"late_rule": _rule_out(get_late_rule(db)), "punch_rule": _punch_out(get_punch_rule(db))}


@router.put("/rules")
def update_rules(payload: LateRuleIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    if payload.mode not in MODES:
        raise HTTPException(400, "mode must be one of: " + ", ".join(MODES))
    if not (1 <= payload.days <= 31):
        raise HTTPException(400, "days must be between 1 and 31.")
    rule = set_late_rule(db, payload.enabled, payload.days, payload.mode)
    punch = get_punch_rule(db)
    if payload.duplicate_seconds is not None or payload.direction_mode is not None:
        mode = payload.direction_mode or punch.direction_mode
        if mode not in DIRECTION_MODES:
            raise HTTPException(400, "direction_mode must be one of: " + ", ".join(DIRECTION_MODES))
        secs = payload.duplicate_seconds if payload.duplicate_seconds is not None else punch.duplicate_seconds
        if not (0 <= secs <= 3600):
            raise HTTPException(400, "duplicate_seconds must be between 0 and 3600.")
        punch = set_punch_rule(db, secs, mode)
    # Bring the stored attendance for this month in line with the new rule straight away.
    today = date.today()
    recalculated = process_range(db, today.replace(day=1), today)
    return {"late_rule": _rule_out(rule), "punch_rule": _punch_out(punch), "recalculated": recalculated}


@router.post("/punches/repair")
def repair_punches(
    from_date: date = Query(...),
    to_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    deny_for_campus(db, user, "Repairing stored punches (all institutions)")
    """Apply the punch rule to punches already stored: delete repeats inside the
    duplicate window, re-number IN/OUT per employee-day, then recalculate attendance."""
    from app.services.punch_rules import repair_stored_punches
    result = repair_stored_punches(db, from_date, to_date or date.today())
    result["recalculated"] = process_range(db, from_date, to_date or date.today())
    return result


@router.get("/late-review")
def late_review(
    employee_code: str = Query(..., min_length=1),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Late days of one employee in a month, in order, and which ones the late-count rule turned into half days."""
    year = max(2000, min(year, 2100))
    last = calendar.monthrange(year, month)[1]
    rule = get_late_rule(db)
    results = compute_range(db, employee_code, date(year, month, 1), date(year, month, last), rule)

    late_days = []
    for r in results:
        if r.status in ("P", "H", "A") and r.late_minutes > 0 and r.total_logs > 0:
            late_days.append({
                "date": r.attendance_date.isoformat(),
                "weekday": r.attendance_date.strftime("%a"),
                "first_in": r.first_in,
                "late_minutes": r.late_minutes,
                "status": r.status,
                "status_label": r.status_label,
                "penalised": bool(r.remarks and r.remarks.startswith(LATE_PENALTY_REMARK)),
                "remarks": r.remarks,
            })
    for i, d in enumerate(late_days, start=1):
        d["number"] = i
    counts = {"P": 0, "H": 0, "A": 0, "L": 0, "O": 0, "W": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {
        "late_rule": _rule_out(rule),
        "late_days": late_days,
        "penalised_days": sum(1 for d in late_days if d["penalised"]),
        "totals": counts,
    }


@router.post("/recalculate", response_model=RecalculateResult)
def recalculate_attendance(
    payload: RecalculateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_employee_code(db, user, payload.employee_code)   # campus login: only its own staff
    """
    Recompute materialized daily attendance for a date range (all employees, or
    one if employee_code is given). Idempotent. This is what the nightly
    scheduler calls; also exposed for on-demand 'Recalculate' from the UI.
    """
    if payload.to_date < payload.from_date:
        raise HTTPException(400, "to_date must be on or after from_date.")
    if (payload.to_date - payload.from_date).days > 366:
        raise HTTPException(400, "Range too large; recalculate at most one year at a time.")
    result = process_range(db, payload.from_date, payload.to_date, payload.employee_code)
    return RecalculateResult(
        from_date=payload.from_date,
        to_date=payload.to_date,
        **result,
    )


@router.get("/processed", response_model=list[ProcessedAttendanceOut])
def get_processed_attendance(
    from_date: date,
    to_date: date,
    employee_code: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 2000,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Fast read of pre-computed daily attendance (for reports/exports)."""
    query = (
        db.query(AttendanceProcessed)
        .filter(AttendanceProcessed.AttendanceDate >= from_date)
        .filter(AttendanceProcessed.AttendanceDate <= to_date)
    )
    org = user_org_id(db, user)
    if org is not None:   # campus login: its institution's staff only
        query = query.filter(AttendanceProcessed.EmployeeCode.in_(
            db.query(Employee.EmployeeCode).filter(Employee.OrganizationId == org)))
    if employee_code:
        query = query.filter(AttendanceProcessed.EmployeeCode == employee_code)
    if status:
        query = query.filter(AttendanceProcessed.Status == status.upper())
    rows = (
        query.order_by(AttendanceProcessed.EmployeeCode, AttendanceProcessed.AttendanceDate)
        .limit(max(1, min(limit, 20000)))
        .all()
    )
    return [
        ProcessedAttendanceOut(
            EmployeeCode=r.EmployeeCode,
            AttendanceDate=r.AttendanceDate,
            Status=r.Status,
            StatusLabel=r.StatusLabel,
            ShiftName=r.ShiftName,
            ShiftTime=r.ShiftTime,
            FirstIn=r.FirstIn,
            LastOut=r.LastOut,
            TotalLogs=r.TotalLogs,
            ActualWorkMinutes=r.ActualWorkMinutes,
            Remarks=r.Remarks,
            ProcessedAt=r.ProcessedAt.isoformat() if r.ProcessedAt else None,
        )
        for r in rows
    ]


@router.get("/processed/export.csv")
def download_processed_csv(
    from_date: date,
    to_date: date,
    employee_code: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Download the computed daily attendance for a range as a CSV file."""
    if not employee_code:
        deny_for_campus(db, user, "The all-staff attendance CSV")   # use the reports (limited to the campus)
    if to_date < from_date:
        raise HTTPException(400, "to_date must be on or after from_date.")
    csv_text, _ = build_attendance_csv(db, from_date, to_date, employee_code)
    filename = f"attendance_{from_date.isoformat()}_{to_date.isoformat()}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export")
def export_processed_attendance(
    payload: RecalculateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    deny_for_campus(db, user, "The attendance export to folder / FTP")
    """
    Deliver computed attendance for a range to the configured targets
    (local folder and/or FTP). Reads from attendance_processed — run
    /recalculate first if the range hasn't been processed.
    """
    if payload.to_date < payload.from_date:
        raise HTTPException(400, "to_date must be on or after from_date.")
    return export_attendance(db, payload.from_date, payload.to_date, payload.employee_code)
