"""
HR reporting service. All reports read from the materialized `attendance_processed`
table (kept fresh by process_range / the nightly recalc). Reports:
  - monthly_register: employees x days muster grid + totals
  - leave_balance_report: per employee x leave type entitlement/taken/balance
  - late_ot_report: per employee x day late/early/OT + totals
  - individual_sheet: one employee's month timesheet
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    AttendanceCategory, AttendanceProcessed, DeviceLog, Employee, EmployeeType,
    LeaveConfig, School, Shift, ShiftRoster,
)
from app.services.report_scope import ReportScope
from app.services.attendance_processing import exit_cutoff, process_range
from app.services.leave_request_service import LeaveRequestService


def _month_bounds(year: int, month: int) -> tuple[date, date, int]:
    month = max(1, min(month, 12))
    year = max(2000, min(year, 2100))
    days = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, days), days


def _range_bounds(from_date: Optional[date], to_date: Optional[date]) -> tuple[date, date]:
    """Normalise an arbitrary from/to range (date-wise / weekly / yearly). Defaults
    to the current month; swaps if reversed."""
    if from_date is None and to_date is None:
        today = date.today()
        return date(today.year, today.month, 1), today
    from_date = from_date or to_date
    to_date = to_date or from_date
    if to_date < from_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date


def _date_list(from_date: date, to_date: date) -> list[date]:
    out: list[date] = []
    d = from_date
    while d <= to_date:
        out.append(d)
        d += timedelta(days=1)
    return out


def _hr_code(e: Employee) -> str:
    """The HR "Employee Code" a report shows for a person (e.g. CSC26018). Employee.EmployeeCode is the Face ID
    (the reader's PIN); the HR code is StringCode, and only when none is set does the Face ID stand in."""
    return (e.StringCode or "").strip() or e.EmployeeCode


def _hhmm(minutes: Optional[int]) -> str:
    """Minutes -> HH:MM (used for worked hours, Late Hrs)."""
    m = max(0, int(minutes or 0))
    return f"{m // 60:02d}:{m % 60:02d}"


def _num(x: float) -> float | int:
    """Whole numbers as int, otherwise a 1-decimal float (for day-count columns)."""
    return int(x) if float(x).is_integer() else round(float(x), 1)


# Academic designation order for grouped reports (anything else follows alphabetically).
_DESIGNATION_RANK = {
    "hod": 0, "head of department": 0, "head of the department": 0,
    "principal": 0, "director": 0,
    "professor": 1,
    "associate professor": 2, "assosiate professor": 2,
    "assistant professor": 3, "asst professor": 3, "asst. professor": 3,
    "non-teaching": 9, "non teaching": 9, "non - teaching": 9,
}
UNASSIGNED = "Unassigned"


def _designation_rank(name: Optional[str]) -> tuple[int, str]:
    key = (name or "").strip().lower()
    if not key:
        return (99, "")
    return (_DESIGNATION_RANK.get(key, 5), key)


def short_no_key(short_no: Optional[str]) -> tuple:
    """Order people by their Short No: numbers by value (1, 2, 10 - not 1, 10, 2), other text after them
    alphabetically, and those without one last. The office numbers its staff this way to fix the report order."""
    s = (short_no or "").strip()
    if not s:
        return (2, 0, "")
    return (0, int(s), "") if s.isdigit() else (1, 0, s.lower())


def _employee_sort_key(e: Employee) -> tuple:
    # Within a department: Short No first (the office's own order), then designation rank, then name.
    return ((e.Department or "").strip().lower() or "~", short_no_key(e.ShortNo),
            _designation_rank(e.Designation), (e.EmployeeName or "").lower())


def _employees(db: Session, scope: Optional[ReportScope] = None, active_from: Optional[date] = None) -> list[Employee]:
    """Employees matching the report filters. EVERY report filter is applied here, and only here."""
    scope = scope or ReportScope()
    q = db.query(Employee)
    if scope.department:
        q = q.filter(Employee.Department == scope.department)
    if scope.designation:
        q = q.filter(Employee.Designation == scope.designation)
    if scope.organization_id is not None:
        q = q.filter(Employee.OrganizationId == scope.organization_id)
    if scope.employee_type_id is not None:
        q = q.filter(Employee.EmployeeTypeId == scope.employee_type_id)
    if scope.school_id is not None:
        q = q.filter(Employee.SchoolId == scope.school_id)
    if scope.category_id is not None:   # attendance category; 0 = employees that have none
        q = q.filter(Employee.CategoryId.is_(None) if scope.category_id == 0 else Employee.CategoryId == scope.category_id)
    # Department -> designation rank -> name, so grouped reports come out in order.
    rows = sorted(q.all(), key=_employee_sort_key)
    if active_from is not None:
        # Left the organization before this period: nothing to report.
        rows = [e for e in rows if (exit_cutoff(e) or active_from) >= active_from]
    return rows


def _number(rows: list[dict]) -> list[dict]:
    """Give every row a running serial number (SNo) unless the report already did."""
    for i, r in enumerate(rows, 1):
        r.setdefault("SNo", i)
    return rows


def group_rows(rows: list[dict]) -> list[dict]:
    """Group already-sorted report rows (dicts with a Department) into department sections, each with
    its row count. Within a department the order is the report's own (designation rank, then name);
    there is no separate designation sub-heading."""
    groups: list[dict] = []
    for r in rows:
        dept = (r.get("Department") or "").strip() or UNASSIGNED
        if not groups or groups[-1]["Department"] != dept:
            groups.append({"Department": dept, "Count": 0, "employees": []})
        groups[-1]["employees"].append(r)
        groups[-1]["Count"] += 1
        r["SNo"] = groups[-1]["Count"]   # S.No restarts at 1 in every department
    return groups


def _processed_by_emp(
    db: Session, from_date: date, to_date: date, codes: list[str]
) -> dict[str, dict[date, AttendanceProcessed]]:
    out: dict[str, dict[date, AttendanceProcessed]] = {c: {} for c in codes}
    if not codes:
        return out
    rows = (
        db.query(AttendanceProcessed)
        .filter(AttendanceProcessed.AttendanceDate >= from_date)
        .filter(AttendanceProcessed.AttendanceDate <= to_date)
        .filter(AttendanceProcessed.EmployeeCode.in_(codes))
        .all()
    )
    for r in rows:
        out.setdefault(r.EmployeeCode, {})[r.AttendanceDate] = r
    return out


def _symbol(row: Optional[AttendanceProcessed]) -> str:
    """Register cell symbol from a processed row. Late arrivals show as PL so
    the muster grid exposes lateness without opening the Late/OT report."""
    if row is None:
        return "-"
    if row.Status == "L":
        return row.LeaveCode or "L"
    if row.Status == "P" and (row.LateMinutes or 0) > 0:
        return "PL"
    if row.Status == "H" and (row.Remarks or "").startswith("Late penalty"):
        return "HL"  # half day given by the late-count rule
    return {"P": "P", "A": "A", "H": "H", "O": "H*", "W": "WO"}.get(row.Status, row.Status)


def muster_columns(leave_codes: list[str]) -> list[str]:
    """Count columns of the Time & Leave muster, in print order: the leave types, with A (absent) sitting
    before CoL when that leave type exists (as on the college's printed muster), then WO and P."""
    cols = list(leave_codes)
    cols.insert(cols.index("CoL") if "CoL" in cols else len(cols), "A")
    return cols + ["WO", "P"]


def _muster_cell(row: Optional[AttendanceProcessed]) -> str:
    """One day cell for the time muster: IN / OUT / worked-hours stacked (3 lines) when the person punched,
    blank otherwise. Absence, weekly-offs and leave are counted in the summary columns, as on the printed muster."""
    if row is None or not row.FirstIn:
        return ""
    worked = _hhmm(row.ActualWorkMinutes) if (row.ActualWorkMinutes or 0) > 0 else ""
    return f"{row.FirstIn}\n{row.LastOut or ''}\n{worked}"


def _summarize_counts(
    day_map: dict[date, AttendanceProcessed], dates: list[date], leave_codes: list[str]
) -> dict:
    """Period totals for one employee (mirrors monthly_register's counting)."""
    present = absent = half = weeklyoff = holiday = latedays = late_minutes = 0
    leave_totals = {c: 0 for c in leave_codes}
    for d in dates:
        row = day_map.get(d)
        if row is None:
            continue
        if (row.LateMinutes or 0) > 0 and (row.TotalLogs or 0) > 0 and row.Status in ("P", "H", "A"):
            latedays += 1
        late_minutes += int(row.LateMinutes or 0)
        s = row.Status
        if s == "P":
            present += 1
        elif s == "A":
            absent += 1
        elif s == "H":
            half += 1
        elif s == "W":
            weeklyoff += 1
        elif s == "O":
            holiday += 1
        elif s == "L":
            code = row.LeaveCode or "L"
            leave_totals[code] = leave_totals.get(code, 0) + 1
    return {
        "present": present, "absent": absent, "half": half, "weeklyoff": weeklyoff,
        "holiday": holiday, "latedays": latedays, "late_minutes": late_minutes,
        "leave_totals": leave_totals,
    }


def scope_labels(db: Session, scope: Optional[ReportScope]) -> dict:
    """Header text for the chosen filters: 'Category' is the composite (School - Department - Employee Type) and
    'AttendanceCategory' the chosen attendance category (None when not filtered). Every report puts this in its data."""
    scope = scope or ReportScope()
    type_name = None
    if scope.employee_type_id is not None:
        et = db.query(EmployeeType).filter(EmployeeType.EmployeeTypeId == scope.employee_type_id).first()
        type_name = et.TypeName if et else None
    school_name = None
    if scope.school_id is not None:
        sc = db.query(School).filter(School.SchoolId == scope.school_id).first()
        school_name = sc.SchoolName if sc else None
    attendance_category = None
    if scope.category_id == 0:
        attendance_category = "Not assigned"
    elif scope.category_id is not None:
        ac = db.query(AttendanceCategory).filter(AttendanceCategory.CategoryId == scope.category_id).first()
        attendance_category = ac.CategoryName if ac else None
    category = " - ".join(p for p in [school_name, scope.department, type_name] if p) or "All"
    return {"Category": category, "AttendanceCategory": attendance_category}


def _range_meta(db: Session, from_date: date, to_date: date, scope: Optional[ReportScope] = None) -> dict:
    """Header fields shared by the formatted reports: date-range labels plus the filter labels."""
    return {
        "FromDate": from_date.isoformat(), "ToDate": to_date.isoformat(),
        "FromLabel": from_date.strftime("%d-%b-%Y"), "ToLabel": to_date.strftime("%d-%b-%Y"),
        **scope_labels(db, scope),
    }


def _current_shift_names(db: Session, codes: list[str]) -> dict[str, str]:
    """EmployeeCode -> shift name applicable today (roster row, else the default shift)."""
    if not codes:
        return {}
    shift_names = {s.ShiftId: s.ShiftName for s in db.query(Shift).all()}
    default = db.query(Shift).filter(Shift.IsDefault == "Y").first()
    out: dict[str, str] = {}
    today = datetime.combine(date.today(), time.min)
    for r in db.query(ShiftRoster).filter(ShiftRoster.EmployeeCode.in_(codes)).all():
        if r.FromDate <= today and (r.ToDate is None or r.ToDate >= today):
            out[r.EmployeeCode] = shift_names.get(r.ShiftId, "")
    for c in codes:
        out.setdefault(c, default.ShiftName if default else "")
    return out


def muster_time_report(
    db: Session, from_date: Optional[date], to_date: Optional[date],
    scope: Optional[ReportScope] = None, refresh: bool = True,
) -> dict:
    """Attendance Report (time only): per-day IN/OUT/worked-hours grid + Late Hrs."""
    from_date, to_date = _range_bounds(from_date, to_date)
    if refresh:
        process_range(db, from_date, to_date)
    employees = _employees(db, scope, active_from=from_date)
    codes = [e.EmployeeCode for e in employees]
    by_emp = _processed_by_emp(db, from_date, to_date, codes)
    dates = _date_list(from_date, to_date)

    rows = []
    for i, e in enumerate(employees, 1):
        day_map = by_emp.get(e.EmployeeCode, {})
        late_minutes = sum(int((day_map.get(d).LateMinutes if day_map.get(d) else 0) or 0) for d in dates)
        rows.append({
            "SNo": i, "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode, "EmployeeName": e.EmployeeName,
            "Department": e.Department, "Designation": e.Designation,
            "days": [_muster_cell(day_map.get(d)) for d in dates],
            "LateHrs": _hhmm(late_minutes) if late_minutes else "",
        })
    return {
        **_range_meta(db, from_date, to_date, scope),
        "DateHeaders": [d.strftime("%d") for d in dates],
        "employees": rows, "groups": group_rows(rows),
    }


def muster_time_leave_report(
    db: Session, from_date: Optional[date], to_date: Optional[date],
    scope: Optional[ReportScope] = None, refresh: bool = True,
) -> dict:
    """Attendance Report with Time & Leave: the time grid plus dynamic leave-code
    totals and A / WO / P / Total / Late Hrs / Late Cl summary columns."""
    from_date, to_date = _range_bounds(from_date, to_date)
    if refresh:
        process_range(db, from_date, to_date)
    employees = _employees(db, scope, active_from=from_date)
    codes = [e.EmployeeCode for e in employees]
    by_emp = _processed_by_emp(db, from_date, to_date, codes)
    dates = _date_list(from_date, to_date)
    leave_codes = [c.Code for c in db.query(LeaveConfig).filter(LeaveConfig.IsActive == "Y").all()]

    columns = muster_columns(leave_codes)
    rows = []
    for i, e in enumerate(employees, 1):
        day_map = by_emp.get(e.EmployeeCode, {})
        c = _summarize_counts(day_map, dates, leave_codes)
        # A half day counts half present and half absent; a public holiday is a day off (WO).
        present_eq = c["present"] + 0.5 * c["half"]
        absent_eq = c["absent"] + 0.5 * c["half"]
        off = c["weeklyoff"] + c["holiday"]
        counts = {code: _num(n) for code, n in c["leave_totals"].items()}
        counts.update({"A": _num(absent_eq), "WO": _num(off), "P": _num(present_eq)})
        # Total = every day of the period, i.e. the sum of all the count columns.
        total = sum(c["leave_totals"].values()) + absent_eq + off + present_eq
        rows.append({
            "SNo": i, "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode, "EmployeeName": e.EmployeeName,
            "Department": e.Department, "Designation": e.Designation,
            "days": [_muster_cell(day_map.get(d)) for d in dates],
            "Counts": counts,
            "LeaveByCode": c["leave_totals"], "AbsentDays": _num(absent_eq),
            "WeeklyOffDays": _num(off), "PresentDays": _num(present_eq),
            "Total": _num(total), "LateHrs": _hhmm(c["late_minutes"]) if c["late_minutes"] else "", "LateCl": c["latedays"],
        })
    return {
        **_range_meta(db, from_date, to_date, scope),
        "DateHeaders": [d.strftime("%d") for d in dates], "LeaveCodes": leave_codes, "Columns": columns,
        "employees": rows, "groups": group_rows(rows),
    }


def _exception_report(
    db: Session, from_date: Optional[date], to_date: Optional[date], field: str,
    scope: Optional[ReportScope], refresh: bool,
) -> dict:
    """Shared body for Late Arrival (field='LateMinutes') and Early Departure
    (field='EarlyMinutes'): one row per employee-day exceeding the threshold."""
    from_date, to_date = _range_bounds(from_date, to_date)
    if refresh:
        process_range(db, from_date, to_date)
    employees = _employees(db, scope, active_from=from_date)
    by_emp = _processed_by_emp(db, from_date, to_date, [e.EmployeeCode for e in employees])
    dates = _date_list(from_date, to_date)

    rows = []
    i = 0
    for e in employees:
        day_map = by_emp.get(e.EmployeeCode, {})
        for d in dates:
            row = day_map.get(d)
            if row is None or (row.TotalLogs or 0) == 0 or int(getattr(row, field) or 0) <= 0:
                continue
            i += 1
            rows.append({
                "SNo": i, "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode, "EmployeeName": e.EmployeeName,
                "Department": e.Department, "Designation": e.Designation,
                "Date": d.strftime("%d-%b-%Y"), "ShiftTime": row.ShiftTime or "",
                "FirstIn": row.FirstIn or "", "LastOut": row.LastOut or "",
                "Minutes": _hhmm(getattr(row, field)),
            })
    return {**_range_meta(db, from_date, to_date, scope),
            "employees": rows, "groups": group_rows(rows)}


def late_arrival_report(db, from_date=None, to_date=None, scope=None, refresh=True) -> dict:
    return _exception_report(db, from_date, to_date, "LateMinutes", scope, refresh)


def early_departure_report(db, from_date=None, to_date=None, scope=None, refresh=True) -> dict:
    return _exception_report(db, from_date, to_date, "EarlyMinutes", scope, refresh)


def in_out_list_report(
    db: Session, from_date: Optional[date], to_date: Optional[date], scope: Optional[ReportScope] = None,
) -> dict:
    """Raw punch list from devicelogs: one row per employee-day with all punches. Everyone in the filter is
    listed (under their department): someone with no punches in the range gets a single "No punches" row."""
    from_date, to_date = _range_bounds(from_date, to_date)
    employees = _employees(db, scope, active_from=from_date)
    codes = [e.EmployeeCode for e in employees]
    by_key: dict[tuple[str, date], list[DeviceLog]] = {}
    if codes:
        end = datetime.combine(to_date, time.max)
        start = datetime.combine(from_date, time.min)
        logs = (db.query(DeviceLog)
                .filter(DeviceLog.EmployeeCode.in_(codes))
                .filter(DeviceLog.LogDate >= start, DeviceLog.LogDate <= end)
                .order_by(DeviceLog.LogDate).all())
        for lg in logs:
            by_key.setdefault((lg.EmployeeCode, lg.LogDate.date()), []).append(lg)
    dates = _date_list(from_date, to_date)

    rows = []
    i = 0
    for e in employees:
        listed = False
        for d in dates:
            punches = by_key.get((e.EmployeeCode, d))
            if not punches:
                continue
            listed = True
            i += 1
            txt = ", ".join(
                p.LogDate.strftime("%H:%M") + (f" {p.Direction}" if p.Direction else "")
                for p in punches
            )
            rows.append({
                "SNo": i, "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode, "EmployeeName": e.EmployeeName,
                "Department": e.Department, "Designation": e.Designation,
                "Date": d.strftime("%d-%b-%Y"), "Count": len(punches), "Punches": txt,
            })
        if not listed:
            i += 1
            rows.append({
                "SNo": i, "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode, "EmployeeName": e.EmployeeName,
                "Department": e.Department, "Designation": e.Designation,
                "Date": "—", "Count": 0, "Punches": "No punches in this period",
            })
    return {**_range_meta(db, from_date, to_date, scope),
            "employees": rows, "groups": group_rows(rows)}


def employee_list_report(db: Session, scope: Optional[ReportScope] = None) -> dict:
    """Employee master list (no date range)."""
    employees = _employees(db, scope)
    codes = [e.EmployeeCode for e in employees]
    type_map = {t.EmployeeTypeId: t.TypeName for t in db.query(EmployeeType).all()}
    cat_map = {c.CategoryId: c.CategoryName for c in db.query(AttendanceCategory).all()}
    shift_map = _current_shift_names(db, codes)

    rows = []
    for i, e in enumerate(employees, 1):
        rows.append({
            "SNo": i, "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode, "EmployeeName": e.EmployeeName,
            "Department": e.Department, "Designation": e.Designation,
            "Type": type_map.get(e.EmployeeTypeId, "") or "",
            "CategoryName": cat_map.get(e.CategoryId, "") or "",
            "Shift": shift_map.get(e.EmployeeCode, ""),
            "Status": e.CurrentStatus or "", "JoiningDate": e.JoiningDate or "",
        })
    labels = scope_labels(db, scope)
    school_dept = " - ".join(p for p in [labels["Category"] if labels["Category"] != "All" else None] if p) or "All"
    return {"Category": school_dept, "AttendanceCategory": labels["AttendanceCategory"], "Count": len(rows),
            "GeneratedLabel": date.today().strftime("%d-%b-%Y"),
            "employees": rows, "groups": group_rows(rows)}


def monthly_register(
    db: Session, year: int, month: int, scope: Optional[ReportScope] = None, refresh: bool = True,
) -> dict:
    from_date, to_date, days_in_month = _month_bounds(year, month)
    if refresh:
        process_range(db, from_date, to_date)

    employees = _employees(db, scope, active_from=from_date)
    codes = [e.EmployeeCode for e in employees]
    by_emp = _processed_by_emp(db, from_date, to_date, codes)
    leave_codes = [c.Code for c in db.query(LeaveConfig).filter(LeaveConfig.IsActive == "Y").all()]

    rows = []
    for e in employees:
        day_map = by_emp.get(e.EmployeeCode, {})
        cells = []
        totals = {"present": 0, "absent": 0, "half": 0, "weeklyoff": 0, "holiday": 0, "late": 0, "latehalf": 0}
        leave_totals = {code: 0 for code in leave_codes}
        for d in range(1, days_in_month + 1):
            row = day_map.get(date(year, month, d))
            cells.append(_symbol(row))
            if row is None:
                continue
            # A late day still counts as late when the late-count rule turned it into a half day.
            if (row.LateMinutes or 0) > 0 and (row.TotalLogs or 0) > 0 and row.Status in ("P", "H", "A"):
                totals["late"] += 1
            if row.Status == "H" and (row.Remarks or "").startswith("Late penalty"):
                totals["latehalf"] += 1
            if row.Status == "P":
                totals["present"] += 1
            elif row.Status == "A":
                totals["absent"] += 1
            elif row.Status == "H":
                totals["half"] += 1
            elif row.Status == "W":
                totals["weeklyoff"] += 1
            elif row.Status == "O":
                totals["holiday"] += 1
            elif row.Status == "L":
                code = row.LeaveCode or "L"
                leave_totals[code] = leave_totals.get(code, 0) + 1
        rows.append({
            "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode,
            "EmployeeName": e.EmployeeName,
            "Department": e.Department,
            "Designation": e.Designation,
            "days": cells,
            "PresentDays": totals["present"],
            "AbsentDays": totals["absent"],
            "HalfDays": totals["half"],
            "WeeklyOffDays": totals["weeklyoff"],
            "HolidayDays": totals["holiday"],
            "LateDays": totals["late"],
            "LatePenaltyHalfDays": totals["latehalf"],
            "LeaveByCode": leave_totals,
        })

    return {
        "Year": year, "Month": month, "MonthLabel": f"{calendar.month_name[month]} {year}",
        "DaysInMonth": days_in_month, "LeaveCodes": leave_codes, "employees": _number(rows),
        "groups": group_rows(rows), **scope_labels(db, scope),
    }


def daily_status_report(
    db: Session, day: date, kind: str = "all", scope: Optional[ReportScope] = None, refresh: bool = False,
) -> dict:
    """Present / Absent list for one day, grouped Department -> Designation.
    kind: 'present' (P/H), 'absent' (A), 'leave' (L) or 'all'.

    The day is (re)processed first so punches that arrived since the nightly
    recalc are counted. For the CURRENT day the shift is still in progress, so
    the work-duration thresholds (which would call a lone IN punch 'Absent')
    do not apply: any punch = Present, and a late IN shows as 'Late'."""
    if refresh:
        process_range(db, day, day)
    employees = _employees(db, scope, active_from=day)
    codes = [e.EmployeeCode for e in employees]
    by_emp = _processed_by_emp(db, day, day, codes)
    in_progress = day >= date.today()

    def classify(row: Optional[AttendanceProcessed]) -> tuple[str, str, str]:
        """-> (bucket, status code, label)"""
        if row is None:
            return "absent", "A", "Absent"
        late = int(row.LateMinutes or 0)
        if row.Status == "L":
            return "leave", "L", row.LeaveCode or "Leave"
        if row.Status in ("O", "W"):
            return "off", row.Status, row.StatusLabel or "Off"
        punched = int(row.TotalLogs or 0) > 0 and bool(row.FirstIn)
        if row.Status in ("P", "H") or (in_progress and punched):
            if late > 0:
                return "present", row.Status if row.Status in ("P", "H") else "P", f"Late ({late} min)"
            if row.Status == "H" and not in_progress:
                return "present", "H", row.StatusLabel or "Half Day"
            return "present", "P", "Present"
        return "absent", "A", "Absent"

    totals = {"present": 0, "absent": 0, "leave": 0, "off": 0, "late": 0, "total": 0}
    rows = []
    for e in employees:
        row = by_emp.get(e.EmployeeCode, {}).get(day)
        b, status, label = classify(row)
        totals[b] += 1
        totals["total"] += 1
        if b == "present" and row is not None and int(row.LateMinutes or 0) > 0:
            totals["late"] += 1
        if kind != "all" and b != kind:
            continue
        rows.append({
            "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode,
            "EmployeeName": e.EmployeeName,
            "Department": e.Department,
            "Designation": e.Designation,
            "Status": status,
            "StatusLabel": label,
            "Bucket": b,
            "LeaveCode": row.LeaveCode if row else None,
            "ShiftName": row.ShiftName if row else None,
            "FirstIn": row.FirstIn if row else None,
            # A single punch is only an IN; don't echo it as the OUT time.
            "LastOut": row.LastOut if row and int(row.TotalLogs or 0) >= 2 else None,
            "LateMinutes": row.LateMinutes if row else 0,
            "Remarks": row.Remarks if row else None,
        })
    return {
        "Date": day.isoformat(), "DayLabel": day.strftime("%A, %d %B %Y"), "Kind": kind,
        "Totals": totals, "employees": _number(rows), "groups": group_rows(rows), **scope_labels(db, scope),
    }


def leave_balance_report(db: Session, year: int, scope: Optional[ReportScope] = None) -> dict:
    service = LeaveRequestService(db)
    employees = _employees(db, scope)
    rows = []
    for e in employees:
        balances = service.get_balance(e.EmployeeCode, year)
        rows.append({
            "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode,
            "EmployeeName": e.EmployeeName,
            "Department": e.Department,
            "Designation": e.Designation,
            "balances": [
                {"Code": b["Code"], "Name": b["Name"], "Entitled": b["MaxPerYear"],
                 "Taken": b["UsedDays"], "Balance": b["AvailableDays"]}
                for b in balances
            ],
        })
    types = [{"Code": c.Code, "Name": c.Name}
             for c in db.query(LeaveConfig).filter(LeaveConfig.IsActive == "Y").all()]
    return {"Year": year, "LeaveTypes": types, "employees": _number(rows), "groups": group_rows(rows), **scope_labels(db, scope)}


def late_ot_report(
    db: Session, year: int, month: int, scope: Optional[ReportScope] = None, refresh: bool = True,
) -> dict:
    from_date, to_date, days_in_month = _month_bounds(year, month)
    if refresh:
        process_range(db, from_date, to_date)
    employees = _employees(db, scope, active_from=from_date)
    codes = [e.EmployeeCode for e in employees]
    by_emp = _processed_by_emp(db, from_date, to_date, codes)

    rows = []
    for e in employees:
        day_map = by_emp.get(e.EmployeeCode, {})
        days = []
        t_late = t_early = t_ot = late_days = 0
        for d in range(1, days_in_month + 1):
            row = day_map.get(date(year, month, d))
            late = row.LateMinutes if row else 0
            early = row.EarlyMinutes if row else 0
            ot = row.OTMinutes if row else 0
            days.append({"Day": d, "Late": late, "Early": early, "OT": ot})
            t_late += late; t_early += early; t_ot += ot
            if late > 0:
                late_days += 1
        rows.append({
            "EmployeeCode": _hr_code(e), "FaceId": e.EmployeeCode, "EmployeeName": e.EmployeeName, "Department": e.Department,
            "days": days, "TotalLateMinutes": t_late, "TotalEarlyMinutes": t_early,
            "TotalOTMinutes": t_ot, "LateDays": late_days,
        })
    return {
        "Year": year, "Month": month, "MonthLabel": f"{calendar.month_name[month]} {year}",
        "DaysInMonth": days_in_month, "employees": _number(rows), **scope_labels(db, scope),
    }


def individual_sheet(
    db: Session, employee_code: str, year: int, month: int, refresh: bool = True
) -> dict:
    from_date, to_date, days_in_month = _month_bounds(year, month)
    # The box accepts the HR Employee Code (what the reports show) or the Face ID; attendance is keyed by Face ID.
    code = (employee_code or "").strip()
    employee = (db.query(Employee).filter(Employee.StringCode == code).first()
                or db.query(Employee).filter(Employee.EmployeeCode == code).first())
    face_id = employee.EmployeeCode if employee else code
    if refresh:
        process_range(db, from_date, to_date, face_id)
    day_map = _processed_by_emp(db, from_date, to_date, [face_id]).get(face_id, {})
    left_after = exit_cutoff(employee)

    days = []
    for d in range(1, days_in_month + 1):
        cd = date(year, month, d)
        row = day_map.get(cd)
        days.append({
            "Date": cd.isoformat(), "Day": d, "DayLabel": cd.strftime("%a"),
            "Status": row.Status if row else ("X" if left_after and cd > left_after else "A"),
            "StatusLabel": (row.StatusLabel if row else ("Left" if left_after and cd > left_after else "Absent")),
            "LeaveCode": row.LeaveCode if row else None,
            "ShiftName": row.ShiftName if row else None,
            "FirstIn": row.FirstIn if row else None,
            "LastOut": row.LastOut if row else None,
            "WorkedMinutes": row.ActualWorkMinutes if row else 0,
            "Late": row.LateMinutes if row else 0,
            "Early": row.EarlyMinutes if row else 0,
            "OT": row.OTMinutes if row else 0,
            "Remarks": row.Remarks if row else None,
        })
    return {
        "EmployeeCode": _hr_code(employee) if employee else code, "FaceId": face_id,
        "EmployeeName": employee.EmployeeName if employee else None,
        "Department": employee.Department if employee else None,
        "Year": year, "Month": month, "MonthLabel": f"{calendar.month_name[month]} {year}",
        "days": days,
    }
