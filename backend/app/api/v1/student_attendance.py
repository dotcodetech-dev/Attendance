"""Student attendance: daily view, processing, manual mark, department/year reports."""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.feature_flags import require_student_module
from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import DepartmentMaster, Student, StudentAttendanceProcessed
from app.services import student_attendance_service as svc

router = APIRouter(dependencies=[Depends(require_student_module)])

STATUSES = ("Present", "Late", "HalfDay", "Absent", "Leave", "WeeklyOff")


class ProcessIn(BaseModel):
    from_date: date
    to_date: date
    student_code: Optional[str] = None


class ManualIn(BaseModel):
    StudentCode: str
    AttendanceDate: date
    Status: str
    InTime: Optional[str] = None
    OutTime: Optional[str] = None


def _dept_names(db: Session) -> dict[int, str]:
    return {d.DepartmentId: d.DepartmentName for d in db.query(DepartmentMaster).all()}


@router.get("/dashboard")
def dashboard(
    on_date: Optional[date] = Query(default=None, alias="date"),
    days: int = Query(default=14, ge=7, le=60),
    department_id: Optional[int] = None,
    year: Optional[int] = Query(default=None, ge=1, le=4),
    registered_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return svc.dashboard(db, on_date or date.today(), days, department_id, year, registered_year)


@router.post("/process")
def process(p: ProcessIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    try:
        n = svc.process_range(db, p.from_date, p.to_date, [p.student_code] if p.student_code else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"processed": n}


@router.get("/daily")
def daily(
    on_date: date = Query(alias="date"),
    department_id: Optional[int] = None,
    year: Optional[int] = Query(default=None, ge=1, le=4),
    registered_year: Optional[str] = None,
    refresh: bool = True,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    students = svc.student_rows(db, on_date, on_date, department_id, year, registered_year)
    codes = [s.StudentCode for s in students]
    if refresh and codes:
        svc.process_range(db, on_date, on_date, codes)
    rows = {}
    if codes:
        rows = {r.StudentCode: r for r in db.query(StudentAttendanceProcessed).filter(
            StudentAttendanceProcessed.AttendanceDate == on_date,
            StudentAttendanceProcessed.StudentCode.in_(codes))}
    names = _dept_names(db)
    out = []
    for s in students:
        r = rows.get(s.StudentCode)
        out.append({
            "StudentCode": s.StudentCode, "StudentName": s.StudentName, "RollNo": s.RollNo,
            "DepartmentName": names.get(s.DepartmentId, ""), "RegisteredYear": s.RegisteredYear,
            "Section": s.Section, "Status": r.Status if r else None,
            "InTime": r.InTime if r else None, "OutTime": r.OutTime if r else None,
            "LateMinutes": r.LateMinutes if r else 0, "LeaveCode": r.LeaveCode if r else None,
            "Source": r.Source if r else None,
        })
    counts = {k: 0 for k in STATUSES}
    for o in out:
        if o["Status"] in counts:
            counts[o["Status"]] += 1
    return {"date": on_date.isoformat(), "total": len(out), "counts": counts, "rows": out}


@router.post("/manual")
def manual_mark(p: ManualIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    if p.Status not in STATUSES:
        raise HTTPException(400, f"Status must be one of {', '.join(STATUSES)}")
    if not db.query(Student.StudentId).filter(Student.StudentCode == p.StudentCode).first():
        raise HTTPException(404, "Student not found")
    row = db.query(StudentAttendanceProcessed).filter(
        StudentAttendanceProcessed.StudentCode == p.StudentCode,
        StudentAttendanceProcessed.AttendanceDate == p.AttendanceDate).first()
    if row is None:
        row = StudentAttendanceProcessed(StudentCode=p.StudentCode, AttendanceDate=p.AttendanceDate)
        db.add(row)
    row.Status, row.InTime, row.OutTime = p.Status, p.InTime, p.OutTime
    row.LateMinutes, row.LeaveCode, row.Source = 0, None, "Manual"
    db.commit()
    return {"ok": True}


@router.delete("/manual")
def clear_manual(student_code: str, on_date: date = Query(alias="date"),
                 db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Remove a manual override so the punch-derived status is recomputed."""
    row = db.query(StudentAttendanceProcessed).filter(
        StudentAttendanceProcessed.StudentCode == student_code,
        StudentAttendanceProcessed.AttendanceDate == on_date,
        StudentAttendanceProcessed.Source == "Manual").first()
    if row:
        db.delete(row)
        db.commit()
    svc.process_range(db, on_date, on_date, [student_code])
    return {"ok": True}


def _report(db: Session, from_date: date, to_date: date, department_id, year, refresh: bool,
            registered_year=None):
    if to_date < from_date:
        raise HTTPException(400, "To date is before from date")
    students = svc.student_rows(db, from_date, to_date, department_id, year, registered_year)
    codes = [s.StudentCode for s in students]
    if refresh and codes:
        try:
            svc.process_range(db, from_date, to_date, codes)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    counts = svc.summary_counts(db, from_date, to_date, codes)
    names = _dept_names(db)
    rows = []
    for s in students:
        c = counts.get(s.StudentCode, {})
        working = sum(c.get(k, 0) for k in ("Present", "Late", "HalfDay", "Absent", "Leave"))
        attended = c.get("Present", 0) + c.get("Late", 0) + 0.5 * c.get("HalfDay", 0)
        rows.append({
            "StudentCode": s.StudentCode, "StudentName": s.StudentName, "RollNo": s.RollNo,
            "DepartmentName": names.get(s.DepartmentId, ""), "RegisteredYear": s.RegisteredYear,
            "Section": s.Section, "Present": c.get("Present", 0), "Late": c.get("Late", 0),
            "HalfDay": c.get("HalfDay", 0), "Leave": c.get("Leave", 0), "Absent": c.get("Absent", 0),
            "Percentage": round(attended * 100 / working, 1) if working else None,
        })
    return rows


# Columns shared by every export format of the student attendance report.
_REPORT_COLS = [
    ("StudentCode", "Code"), ("StudentName", "Name"), ("RollNo", "Roll No"),
    ("DepartmentName", "Department"), ("RegisteredYear", "Registered Year"), ("Section", "Section"),
    ("Present", "Present"), ("Late", "Late"), ("HalfDay", "Half day"),
    ("Leave", "Leave"), ("Absent", "Absent"), ("Percentage", "%"),
]


@router.get("/report")
def report(from_date: date, to_date: date, department_id: Optional[int] = None,
           year: Optional[int] = Query(default=None, ge=1, le=4), registered_year: Optional[str] = None,
           refresh: bool = True, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return _report(db, from_date, to_date, department_id, year, refresh, registered_year)


@router.get("/report/export.csv")
def report_csv(from_date: date, to_date: date, department_id: Optional[int] = None,
               year: Optional[int] = Query(default=None, ge=1, le=4), registered_year: Optional[str] = None,
               db: Session = Depends(get_db), _user=Depends(get_current_user)):
    rows = _report(db, from_date, to_date, department_id, year, True, registered_year)
    buf = io.StringIO()
    keys = [k for k, _ in _REPORT_COLS]
    w = csv.writer(buf)
    w.writerow([label for _, label in _REPORT_COLS])
    for r in rows:
        w.writerow([r[k] if r[k] is not None else "" for k in keys])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="student_attendance_{from_date}_{to_date}.csv"'},
    )


def _report_table(rows: list[dict]) -> tuple[list[str], list[list]]:
    headers = [label for _, label in _REPORT_COLS]
    out = []
    for r in rows:
        line = []
        for k, _ in _REPORT_COLS:
            v = r[k]
            if k == "Percentage":
                v = "" if v is None else f"{v}%"
            line.append("" if v is None else v)
        out.append(line)
    return headers, out


@router.get("/report/export.{fmt}")
def report_export(fmt: str, from_date: date, to_date: date, department_id: Optional[int] = None,
                  year: Optional[int] = Query(default=None, ge=1, le=4), registered_year: Optional[str] = None,
                  db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Excel / PDF export of the student attendance report, styled like the Employee Attendance Report."""
    from fastapi import Response
    from app.api.v1.settings import get_organization_settings
    from app.services import report_export as rx

    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(404, "Unknown format")
    rows = _report(db, from_date, to_date, department_id, year, True, registered_year)
    headers, table = _report_table(rows)
    org = get_organization_settings(db)
    title = "Student Attendance Report"
    subtitle = f"From {from_date} To {to_date}"
    data = rx.simple_table(title, subtitle, headers, table, fmt, org=org)
    fname = f"student_attendance_{from_date}_{to_date}.{fmt}"
    return Response(content=data, media_type=rx.MEDIA_TYPES[fmt],
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
