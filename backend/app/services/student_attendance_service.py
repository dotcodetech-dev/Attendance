"""
Student attendance processing: devicelogs (keyed by StudentCode) + student shift
+ approved student leave -> student_attendance_processed. Kept separate from the
employee engine so student shifts/leave never mix with staff rules.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.feature_flags import absent_on_weekly_off
from app.models.entities import (
    DeviceLog,
    Student,
    StudentAttendanceProcessed,
    StudentLeaveConfig,
    StudentLeaveRequest,
    StudentShift,
)

MAX_RANGE_DAYS = 92


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _default_shift() -> StudentShift:
    return StudentShift(StudentShiftId=0, ShiftName="Default", StartTime="09:00", EndTime="16:00",
                        GraceInMinutes=10, HalfDayMinutes=240, WeeklyOff="Sunday")


def process_range(db: Session, from_date: date, to_date: date,
                  student_codes: Optional[list[str]] = None) -> int:
    """Recompute Auto rows for [from_date, to_date] (capped at today). Manual rows are kept."""
    to_date = min(to_date, date.today())
    if to_date < from_date:
        return 0
    if (to_date - from_date).days > MAX_RANGE_DAYS:
        raise ValueError(f"Range too large (max {MAX_RANGE_DAYS} days)")

    q = db.query(Student).filter(Student.IsActive == "Y")
    if student_codes is not None:
        q = q.filter(Student.StudentCode.in_(student_codes))
    students = q.all()
    if not students:
        return 0
    codes = [s.StudentCode for s in students]

    shifts = {s.StudentShiftId: s for s in db.query(StudentShift).all()}
    fallback = next(iter(shifts.values()), None) or _default_shift()
    leave_cfg = {c.StudentLeaveConfigId: c for c in db.query(StudentLeaveConfig).all()}
    absent_off = absent_on_weekly_off(db)

    leaves = (
        db.query(StudentLeaveRequest)
        .filter(StudentLeaveRequest.Status == "Approved",
                StudentLeaveRequest.StudentCode.in_(codes),
                StudentLeaveRequest.FromDate <= to_date,
                StudentLeaveRequest.ToDate >= from_date)
        .all()
    )
    leave_by_code: dict[str, list[StudentLeaveRequest]] = {}
    for lv in leaves:
        leave_by_code.setdefault(lv.StudentCode, []).append(lv)

    start_dt = datetime.combine(from_date, datetime.min.time())
    end_dt = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
    punches: dict[tuple[str, date], list[datetime]] = {}
    for code, log_dt in (
        db.query(DeviceLog.EmployeeCode, DeviceLog.LogDate)
        .filter(DeviceLog.EmployeeCode.in_(codes), DeviceLog.LogDate >= start_dt, DeviceLog.LogDate < end_dt)
        .all()
    ):
        punches.setdefault((code, log_dt.date()), []).append(log_dt)

    existing = {
        (r.StudentCode, r.AttendanceDate): r
        for r in db.query(StudentAttendanceProcessed).filter(
            StudentAttendanceProcessed.StudentCode.in_(codes),
            StudentAttendanceProcessed.AttendanceDate >= from_date,
            StudentAttendanceProcessed.AttendanceDate <= to_date,
        )
    }

    written = 0
    day = from_date
    while day <= to_date:
        for st in students:
            row = existing.get((st.StudentCode, day))
            if row is not None and row.Source == "Manual":
                continue
            shift = shifts.get(st.StudentShiftId) or fallback
            status, in_t, out_t, late, leave_code = _compute_day(
                day, shift, punches.get((st.StudentCode, day), []),
                leave_by_code.get(st.StudentCode, []), leave_cfg, absent_off,
            )
            if row is None:
                row = StudentAttendanceProcessed(StudentCode=st.StudentCode, AttendanceDate=day, Source="Auto")
                db.add(row)
            row.Status, row.InTime, row.OutTime = status, in_t, out_t
            row.LateMinutes, row.LeaveCode = late, leave_code
            written += 1
        day += timedelta(days=1)
    db.commit()
    return written


def _compute_day(day: date, shift: StudentShift, logs: list[datetime],
                 leaves: list[StudentLeaveRequest], leave_cfg: dict, absent_off: bool = False):
    for lv in leaves:
        if lv.FromDate <= day <= lv.ToDate:
            cfg = leave_cfg.get(lv.StudentLeaveConfigId)
            return "Leave", None, None, 0, (cfg.Code if cfg else None)

    if logs:
        logs = sorted(logs)
        first, last = logs[0], logs[-1]
        in_t, out_t = first.strftime("%H:%M"), (last.strftime("%H:%M") if len(logs) > 1 else None)
        late = max(0, first.hour * 60 + first.minute - (_mins(shift.StartTime) + (shift.GraceInMinutes or 0)))
        if out_t and (last - first).total_seconds() / 60 < (shift.HalfDayMinutes or 0):
            return "HalfDay", in_t, out_t, late, None
        return ("Late" if late > 0 else "Present"), in_t, out_t, late, None

    # No punch: Absent. The weekly off day is the one exception, unless "absent on weekly off" is switched on.
    if not absent_off and shift.WeeklyOff and day.strftime("%A").lower() == shift.WeeklyOff.lower():
        return "WeeklyOff", None, None, 0, None
    return "Absent", None, None, 0, None


def section_filter(q, section: Optional[str]):
    """Students of one Section (e.g. NA, Fellowship). "NA" also matches students whose section was left empty."""
    value = (section or "").strip()
    if not value:
        return q
    if value.lower() in ("na", "n/a"):
        return q.filter((Student.Section.is_(None)) | (Student.Section == "") | (func.lower(Student.Section).in_(("na", "n/a"))))
    return q.filter(func.lower(Student.Section) == value.lower())


def student_rows(db: Session, from_date: date, to_date: date,
                 department_id: Optional[int] = None, year: Optional[int] = None,
                 registered_year: Optional[str] = None, section: Optional[str] = None):
    """Students (filtered) joined with processed rows in range."""
    q = section_filter(db.query(Student).filter(Student.IsActive == "Y"), section)
    if department_id:
        q = q.filter(Student.DepartmentId == department_id)
    if year:
        q = q.filter(Student.YearOfStudy == year)
    if registered_year:
        q = q.filter(Student.RegisteredYear == registered_year)
    return q.order_by(Student.DepartmentId, Student.RegisteredYear, Student.StudentName).all()


def summary_counts(db: Session, from_date: date, to_date: date, codes: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {c: {} for c in codes}
    if not codes:
        return out
    rows = (
        db.query(StudentAttendanceProcessed.StudentCode, StudentAttendanceProcessed.Status,
                 func.count(StudentAttendanceProcessed.StudentAttendanceId))
        .filter(StudentAttendanceProcessed.StudentCode.in_(codes),
                StudentAttendanceProcessed.AttendanceDate >= from_date,
                StudentAttendanceProcessed.AttendanceDate <= to_date)
        .group_by(StudentAttendanceProcessed.StudentCode, StudentAttendanceProcessed.Status)
        .all()
    )
    for code, status, n in rows:
        out[code][status] = n
    return out


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
_STATUSES = ("Present", "Late", "HalfDay", "Absent", "Leave", "WeeklyOff")


def _blank() -> dict[str, int]:
    return {s: 0 for s in _STATUSES}


def _rate(c: dict[str, int]) -> Optional[float]:
    """Attendance % = (Present + Late + half of HalfDay) / working days; weekly offs don't count."""
    working = c["Present"] + c["Late"] + c["HalfDay"] + c["Absent"] + c["Leave"]
    if working == 0:
        return None
    return round((c["Present"] + c["Late"] + 0.5 * c["HalfDay"]) * 100 / working, 1)


def _pack(c: dict[str, int], total: int) -> dict:
    return {
        "total": total, "present": c["Present"], "late": c["Late"], "half_day": c["HalfDay"],
        "absent": c["Absent"], "leave": c["Leave"], "weekly_off": c["WeeklyOff"], "rate": _rate(c),
    }


_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _reg_year_key(label: str) -> tuple:
    """Sort registered-year session labels like 'Jan 2026'; unknown/'—' sort last."""
    parts = (label or "").split()
    if len(parts) == 2 and parts[1].isdigit() and parts[0][:3].lower() in _MONTHS:
        return (0, int(parts[1]), _MONTHS[parts[0][:3].lower()], label)
    return (1, 0, 0, label or "")


def dashboard(db: Session, on_date: date, days: int,
              department_id: Optional[int] = None, year: Optional[int] = None,
              registered_year: Optional[str] = None) -> dict:
    from app.models.entities import DepartmentMaster

    on_date = min(on_date, date.today())
    start = on_date - timedelta(days=days - 1)
    students = student_rows(db, start, on_date, department_id, year, registered_year)
    codes = [s.StudentCode for s in students]
    meta = {s.StudentCode: s for s in students}
    dept_names = {d.DepartmentId: d.DepartmentName for d in db.query(DepartmentMaster).all()}

    empty = {
        "date": on_date.isoformat(), "days": days, "kpis": _pack(_blank(), 0), "prev_rate": None,
        "pending_leaves": 0, "by_department": [], "by_year": [], "reg_years": [], "heatmap": [], "trend": [],
        "arrivals": [], "watchlist": [],
    }
    if not codes:
        return empty

    # Only (re)process days that have no rows yet, plus today (punches keep arriving).
    have = dict(
        db.query(StudentAttendanceProcessed.AttendanceDate, func.count(StudentAttendanceProcessed.StudentAttendanceId))
        .filter(StudentAttendanceProcessed.StudentCode.in_(codes),
                StudentAttendanceProcessed.AttendanceDate >= start,
                StudentAttendanceProcessed.AttendanceDate <= on_date)
        .group_by(StudentAttendanceProcessed.AttendanceDate).all()
    )
    need = [start + timedelta(days=i) for i in range(days)
            if have.get(start + timedelta(days=i), 0) < len(codes) or start + timedelta(days=i) == date.today()]
    if need:
        process_range(db, min(need), max(need), codes)

    rows = (
        db.query(StudentAttendanceProcessed.StudentCode, StudentAttendanceProcessed.AttendanceDate,
                 StudentAttendanceProcessed.Status, StudentAttendanceProcessed.InTime,
                 StudentAttendanceProcessed.LateMinutes)
        .filter(StudentAttendanceProcessed.StudentCode.in_(codes),
                StudentAttendanceProcessed.AttendanceDate >= start,
                StudentAttendanceProcessed.AttendanceDate <= on_date)
        .all()
    )

    def _ry(st) -> str:
        return st.RegisteredYear or "—"

    per_day: dict[date, dict[str, int]] = {}
    today_all = _blank()
    today_dept: dict[int, dict[str, int]] = {}
    today_year: dict[str, dict[str, int]] = {}
    window_cell: dict[tuple[int, str], dict[str, int]] = {}
    per_student: dict[str, dict[str, int]] = {}
    buckets = [0] * 10  # 07:00 .. 11:30 in 30-minute steps; earlier/later punches clamp to the ends

    for code, day, status, in_time, late in rows:
        if status not in _STATUSES:
            continue
        st = meta[code]
        per_day.setdefault(day, _blank())[status] += 1
        window_cell.setdefault((st.DepartmentId, _ry(st)), _blank())[status] += 1
        per_student.setdefault(code, _blank())[status] += 1
        if day == on_date:
            today_all[status] += 1
            today_dept.setdefault(st.DepartmentId, _blank())[status] += 1
            today_year.setdefault(_ry(st), _blank())[status] += 1
            if in_time:
                m = _mins(in_time)
                buckets[max(0, min(9, (m - 420) // 30))] += 1

    dept_total: dict[int, int] = {}
    year_total: dict[str, int] = {}
    for s in students:
        dept_total[s.DepartmentId] = dept_total.get(s.DepartmentId, 0) + 1
        year_total[_ry(s)] = year_total.get(_ry(s), 0) + 1
    reg_years = sorted(year_total, key=_reg_year_key)

    trend = []
    prev_rate = None
    for i in range(days):
        d = start + timedelta(days=i)
        c = per_day.get(d, _blank())
        r = _rate(c)
        trend.append({"date": d.isoformat(), "rate": r, "present": c["Present"] + c["Late"] + c["HalfDay"],
                      "late": c["Late"], "absent": c["Absent"], "leave": c["Leave"], "weekly_off": c["WeeklyOff"]})
        if d < on_date and r is not None:
            prev_rate = r

    by_department = sorted(
        ({"DepartmentId": d, "name": dept_names.get(d, "—"), **_pack(today_dept.get(d, _blank()), n)}
         for d, n in dept_total.items()),
        key=lambda x: x["name"])
    by_year = [{"year": y, **_pack(today_year.get(y, _blank()), year_total.get(y, 0))} for y in reg_years]

    dept_year_total: dict[tuple[int, str], int] = {}
    for s in students:
        dept_year_total[(s.DepartmentId, _ry(s))] = dept_year_total.get((s.DepartmentId, _ry(s)), 0) + 1
    heatmap = []
    for d in sorted(dept_total, key=lambda x: dept_names.get(x, "")):
        cells = {}
        for y in reg_years:
            n = dept_year_total.get((d, y), 0)
            cells[y] = {"students": n, "rate": _rate(window_cell[(d, y)]) if (d, y) in window_cell else None}
        heatmap.append({"DepartmentId": d, "name": dept_names.get(d, "—"), "years": cells})

    watch = []
    for code, c in per_student.items():
        working = c["Present"] + c["Late"] + c["HalfDay"] + c["Absent"] + c["Leave"]
        if working < 3:
            continue
        st = meta[code]
        watch.append({"StudentCode": code, "StudentName": st.StudentName,
                      "DepartmentName": dept_names.get(st.DepartmentId, "—"), "RegisteredYear": _ry(st),
                      "rate": _rate(c), "absent": c["Absent"], "late": c["Late"]})
    watch.sort(key=lambda w: (w["rate"], -w["absent"]))

    from app.core.feature_flags import student_leaves_enabled
    pending = 0
    if student_leaves_enabled(db):
        pending = (
            db.query(func.count(StudentLeaveRequest.StudentLeaveRequestId))
            .filter(StudentLeaveRequest.Status == "Pending", StudentLeaveRequest.StudentCode.in_(codes)).scalar() or 0
        )

    labels = [f"{7 + (i * 30) // 60:02d}:{(i * 30) % 60:02d}" for i in range(10)]
    return {
        "date": on_date.isoformat(), "days": days,
        "kpis": _pack(today_all, len(codes)), "prev_rate": prev_rate, "pending_leaves": pending,
        "by_department": by_department, "by_year": by_year, "reg_years": reg_years,
        "heatmap": heatmap, "trend": trend,
        "arrivals": [{"label": l, "count": n} for l, n in zip(labels, buckets)],
        "watchlist": watch[:8],
    }
