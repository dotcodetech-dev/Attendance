"""
Attendance processing engine.

Folds raw `devicelogs` punches into shift/holiday/leave-aware daily attendance,
mirroring eTimeTrackLite's DEVICELOGS -> ATTENDANCELOGS pipeline. The per-day
computation here is the SINGLE source of truth: both the live month-summary
endpoint and the materialized `attendance_processed` table are built from
`compute_day`, so they can never diverge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    AttendanceCategory, AttendanceProcessed, DeviceLog, Employee, Holiday,
    LeaveConfig, LeaveRequest, Shift, ShiftRoster,
)
from app.services.attendance_rules import classify_workday
from app.services.attendance_settings import LateRule, get_late_rule, get_punch_rule
from app.services.employee_status import EXIT_STATUSES, exit_cutoff  # noqa: F401 (re-exported)
from app.services.leave_days import leave_applies_on
from app.services.punch_rules import collapse_duplicates


@dataclass
class DayResult:
    attendance_date: date
    status: str
    status_label: str
    shift_id: Optional[int]
    shift_name: Optional[str]
    shift_time: Optional[str]
    first_in: Optional[str]
    last_out: Optional[str]
    total_logs: int
    actual_work_minutes: int
    remarks: Optional[str]
    leave_code: Optional[str] = None
    late_minutes: int = 0
    early_minutes: int = 0
    ot_minutes: int = 0


def _hhmm_to_minutes(value: Optional[str]) -> Optional[int]:
    """Parse 'HH:MM' into minutes-since-midnight; None if unparseable."""
    if not value:
        return None
    try:
        h, m = value.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _break_overlap_minutes(shift: Shift, in_min: int, out_min: int) -> int:
    """Minutes of the shift's enabled break windows that fall inside the worked span."""
    total = 0
    for label in ("Break1", "Break2"):
        if (getattr(shift, f"{label}Enabled", "N") or "N") != "Y":
            continue
        b_start = _hhmm_to_minutes(getattr(shift, f"{label}StartTime", None))
        b_end = _hhmm_to_minutes(getattr(shift, f"{label}EndTime", None))
        if b_start is None or b_end is None or b_end <= b_start:
            continue
        total += max(min(b_end, out_min) - max(b_start, in_min), 0)
    return total


def _is_weekly_off(category: Optional[AttendanceCategory], current_date: date) -> bool:
    if category is None:
        return False
    weekday = current_date.strftime("%A")
    if (category.WeeklyOff1Enabled or "N") == "Y" and (category.WeeklyOff1Weekday or "") == weekday:
        return True
    if (category.WeeklyOff2Enabled or "N") == "Y" and (category.WeeklyOff2Weekday or "") == weekday:
        occurrence = (current_date.day - 1) // 7 + 1
        occ_flag = getattr(category, f"WeeklyOff2Occurrence{occurrence}", "N")
        if (occ_flag or "N") == "Y":
            return True
    return False


def _is_partial_day(shift: Optional[Shift], current_date: date) -> bool:
    """True if the shift has a partial-day rule that matches the current weekday."""
    if shift is None:
        return False
    if (shift.PartialDayEnabled or "N") != "Y":
        return False
    return current_date.strftime("%A") == (shift.PartialDayWeekday or "")


def _effective_shift_times(shift: Shift, current_date: date) -> tuple[str, str]:
    """Return (start, end) using partial-day times when applicable."""
    if _is_partial_day(shift, current_date):
        start = shift.PartialDayStartTime or shift.StartTime
        end = shift.PartialDayEndTime or shift.EndTime
        return start, end
    return shift.StartTime, shift.EndTime


def _apply_punch_rules(
    day_logs: list[DeviceLog],
    category: Optional[AttendanceCategory],
    shift: Optional[Shift],
) -> tuple[Optional[str], Optional[str], int]:
    """
    Apply category punch rules and return (first_in, last_out, actual_work_minutes).

    Rules applied:
    - NeglectLastInPunch: drop trailing unpaired IN when odd punch count
    - ConsiderOnlyFirstLastPunch: Y = last-first, N = paired-punch sum
    - ConsiderEarlyComingPunch: N = clamp first_in to shift start
    - ConsiderLateGoingPunch: N = clamp last_out to shift end
    """
    if not day_logs:
        return None, None, 0

    logs = list(day_logs)

    # NeglectLastInPunch: if odd count and flag is Y, drop trailing IN
    if category and (category.NeglectLastInPunch or "N") == "Y" and len(logs) % 2 == 1:
        logs = logs[:-1]
    if not logs:
        return None, None, 0

    first_dt = logs[0].LogDate
    last_dt = logs[-1].LogDate
    first_in = first_dt.strftime("%H:%M")
    last_out = last_dt.strftime("%H:%M")

    # Work duration calculation
    use_paired = category and (category.ConsiderOnlyFirstLastPunch or "Y") == "N"
    if use_paired and len(logs) >= 2:
        # Pair consecutive punches: (IN1,OUT1), (IN2,OUT2), ...
        total_minutes = 0
        i = 0
        while i + 1 < len(logs):
            span = max(int((logs[i + 1].LogDate - logs[i].LogDate).total_seconds() // 60), 0)
            total_minutes += span
            i += 2
        actual_work_minutes = total_minutes
    else:
        # Default: last - first
        if len(logs) > 1:
            actual_work_minutes = max(int((last_dt - first_dt).total_seconds() // 60), 0)
        else:
            actual_work_minutes = 0

    # Clamp punch times when early-coming / late-going not considered
    if shift is not None and category is not None:
        shift_start = _hhmm_to_minutes(shift.StartTime)
        shift_end = _hhmm_to_minutes(shift.EndTime)
        in_min = _hhmm_to_minutes(first_in)
        out_min = _hhmm_to_minutes(last_out)

        if (category.ConsiderEarlyComingPunch or "N") == "N" and shift_start is not None and in_min is not None:
            if in_min < shift_start:
                first_in = shift.StartTime
                # Recalculate work minutes with clamped start
                clamped_in = shift_start
                effective_out = out_min if out_min is not None else clamped_in
                if not use_paired:
                    actual_work_minutes = max(effective_out - clamped_in, 0)

        if (category.ConsiderLateGoingPunch or "Y") == "N" and shift_end is not None and out_min is not None:
            if out_min > shift_end:
                last_out = shift.EndTime
                # Recalculate work minutes with clamped end
                effective_in = _hhmm_to_minutes(first_in) or 0
                if not use_paired:
                    actual_work_minutes = max(shift_end - effective_in, 0)

    return first_in, last_out, actual_work_minutes


@dataclass
class EmployeeContext:
    employee: Optional[Employee]
    category: Optional[AttendanceCategory]
    logs_by_date: dict[date, list[DeviceLog]]
    holiday_by_date: dict[date, Holiday]
    roster_by_date: dict[date, tuple[ShiftRoster, Shift]]
    leave_by_date: dict[date, tuple[LeaveRequest, LeaveConfig]]
    default_shift: Optional[Shift] = None
    punch_duplicate_seconds: int = 60   # bursts closer than this count as one punch


def build_employee_context(
    db: Session,
    employee_code: str,
    range_start: datetime,
    range_end: datetime,
) -> EmployeeContext:
    """Load everything needed to classify each day in [range_start, range_end]."""
    employee = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()

    logs = (
        db.query(DeviceLog)
        .filter(DeviceLog.EmployeeCode == employee_code)
        .filter(DeviceLog.LogDate >= range_start)
        .filter(DeviceLog.LogDate <= range_end)
        .order_by(DeviceLog.LogDate.asc())
        .all()
    )
    holidays = (
        db.query(Holiday)
        .filter(Holiday.HolidayDate >= range_start)
        .filter(Holiday.HolidayDate <= range_end)
        .filter(Holiday.IsActive == "Y")
        .all()
    )
    rosters = (
        db.query(ShiftRoster, Shift)
        .join(Shift, ShiftRoster.ShiftId == Shift.ShiftId)
        .filter(ShiftRoster.EmployeeCode == employee_code)
        .filter(ShiftRoster.FromDate <= range_end)
        .filter((ShiftRoster.ToDate.is_(None)) | (ShiftRoster.ToDate >= range_start))
        .all()
    )
    leaves = (
        db.query(LeaveRequest, LeaveConfig)
        .join(LeaveConfig, LeaveRequest.LeaveConfigId == LeaveConfig.LeaveConfigId)
        .filter(LeaveRequest.EmployeeCode == employee_code)
        .filter(LeaveRequest.Status == "Approved")  # only fully approved leave counts in attendance
        .filter(LeaveRequest.FromDate <= range_end)
        .filter(LeaveRequest.ToDate >= range_start)
        .all()
    )

    logs_by_date: dict[date, list[DeviceLog]] = {}
    for row in logs:
        logs_by_date.setdefault(row.LogDate.date(), []).append(row)

    holiday_by_date = {row.HolidayDate.date(): row for row in holidays}

    roster_by_date: dict[date, tuple[ShiftRoster, Shift]] = {}
    for roster, shift in rosters:
        current = max(roster.FromDate.date(), range_start.date())
        last = min((roster.ToDate or range_end).date(), range_end.date())
        while current <= last:
            roster_by_date[current] = (roster, shift)
            current += timedelta(days=1)

    leave_by_date: dict[date, tuple[LeaveRequest, LeaveConfig]] = {}
    for leave, config in leaves:
        current = max(leave.FromDate.date(), range_start.date())
        last = min(leave.ToDate.date(), range_end.date())
        while current <= last:
            leave_by_date[current] = (leave, config)
            current += timedelta(days=1)

    category = None
    if employee and employee.CategoryId is not None:
        category = (
            db.query(AttendanceCategory)
            .filter(AttendanceCategory.CategoryId == employee.CategoryId)
            .filter((AttendanceCategory.IsActive.is_(None)) | (AttendanceCategory.IsActive == "Y"))
            .first()
        )

    default_shift = (
        db.query(Shift)
        .filter(Shift.IsDefault == "Y")
        .filter((Shift.IsActive.is_(None)) | (Shift.IsActive == "Y"))
        .first()
    )

    return EmployeeContext(
        employee=employee,
        category=category,
        logs_by_date=logs_by_date,
        holiday_by_date=holiday_by_date,
        roster_by_date=roster_by_date,
        leave_by_date=leave_by_date,
        default_shift=default_shift,
        punch_duplicate_seconds=get_punch_rule(db).duplicate_seconds,
    )


def compute_day(ctx: EmployeeContext, current_date: date) -> DayResult:
    """Classify a single day for one employee. The one source of truth."""
    # Collapse repeated reads of the same face/finger so a burst never becomes a
    # fake OUT punch (matters for paired-punch hours and for Direction display).
    day_logs = collapse_duplicates(ctx.logs_by_date.get(current_date, []), ctx.punch_duplicate_seconds)
    holiday = ctx.holiday_by_date.get(current_date)
    roster_item = ctx.roster_by_date.get(current_date)
    leave_item = ctx.leave_by_date.get(current_date)

    shift: Optional[Shift] = roster_item[1] if roster_item else ctx.default_shift

    shift_id = shift_name = shift_time = None
    partial_day = False
    if shift:
        shift_id = shift.ShiftId
        shift_name = shift.ShiftName
        eff_start, eff_end = _effective_shift_times(shift, current_date)
        shift_time = f"{eff_start} to {eff_end}"
        partial_day = _is_partial_day(shift, current_date)

    # Apply punch rules (paired punch, neglect last in, clamp early/late)
    first_in, last_out, actual_work_minutes = _apply_punch_rules(day_logs, ctx.category, shift)

    # Deduct shift break windows when category says so
    if (
        actual_work_minutes > 0
        and shift is not None
        and ctx.category is not None
        and (ctx.category.DeductBreakHours or "N") == "Y"
    ):
        in_min = _hhmm_to_minutes(first_in)
        out_min = _hhmm_to_minutes(last_out)
        if in_min is not None and out_min is not None and out_min > in_min:
            actual_work_minutes = max(
                actual_work_minutes - _break_overlap_minutes(shift, in_min, out_min), 0
            )

    # Late / early / OT — only meaningful on a worked day against a shift
    late_minutes = early_minutes = ot_minutes = 0
    # Lateness only needs the IN punch. Early leaving and overtime need a real OUT punch as well
    # (with a single punch, first_in and last_out are the same moment).
    has_out = bool(last_out) and len(day_logs) >= 2
    if shift is not None and day_logs and first_in:
        is_flexible = (shift.IsFlexibleShift or "N") == "Y"
        eff_start, eff_end = _effective_shift_times(shift, current_date)
        shift_start = _hhmm_to_minutes(eff_start)
        shift_end = _hhmm_to_minutes(eff_end)
        in_min = _hhmm_to_minutes(first_in)
        out_min = _hhmm_to_minutes(last_out)
        cat = ctx.category

        if not is_flexible:
            # Grace: shift-level overrides category-level when > 0
            cat_late_grace = int(cat.GraceLateComingMinutes) if cat and cat.GraceLateComingMinutes is not None else 0
            cat_early_grace = int(cat.GraceEarlyGoingMinutes) if cat and cat.GraceEarlyGoingMinutes is not None else 0
            shift_late_grace = int(shift.GraceInMinutes or 0)
            shift_early_grace = int(shift.GraceOutMinutes or 0)
            late_grace = shift_late_grace if shift_late_grace > 0 else cat_late_grace
            early_grace = shift_early_grace if shift_early_grace > 0 else cat_early_grace

            if shift_start is not None and in_min is not None:
                late_minutes = max(in_min - shift_start - late_grace, 0)
            if has_out and shift_end is not None and out_min is not None:
                early_minutes = max(shift_end - out_min - early_grace, 0)

        # OT calculation (respects OTFormula)
        ot_formula = (cat.OTFormula or "Total Duration - Shift Hours") if cat else "Total Duration - Shift Hours"
        min_ot = int(cat.MinOTMinutes) if cat and cat.MinOTMinutes is not None else 0
        max_ot = int(cat.MaxOTMinutes) if cat and cat.MaxOTMinutes is not None else 0

        if ot_formula == "OT Not Applicable" or not has_out:
            ot_minutes = 0
        elif shift_start is not None and shift_end is not None:
            shift_minutes = shift_end - shift_start
            if shift_minutes < 0:
                shift_minutes += 24 * 60

            if ot_formula == "Early Coming + Late Going":
                early_ot = max(shift_start - in_min, 0) if in_min is not None and shift_start is not None else 0
                late_ot = max(out_min - shift_end, 0) if out_min is not None and shift_end is not None else 0
                candidate_ot = early_ot + late_ot
            elif ot_formula == "In Out Punch - Shift End Time":
                candidate_ot = max(out_min - shift_end, 0) if out_min is not None and shift_end is not None else 0
            else:
                # Default: Total Duration - Shift Hours
                candidate_ot = actual_work_minutes - shift_minutes

            if candidate_ot >= min_ot and candidate_ot > 0:
                ot_minutes = candidate_ot if max_ot <= 0 else min(candidate_ot, max_ot)

    weekly_off = _is_weekly_off(ctx.category, current_date)
    # A leave only covers a holiday / weekly off when its leave type says to count them
    # (Leave Types -> "Count weekly offs / holidays inside a leave"); otherwise the day stays an off day.
    leave_covers_day = leave_item is not None and leave_applies_on(
        leave_item[1], is_holiday=holiday is not None, is_weekly_off=weekly_off,
    )

    status, status_label = classify_workday(
        category=ctx.category,
        actual_work_minutes=actual_work_minutes,
        has_logs=bool(day_logs),
        is_leave=leave_covers_day,
        is_off_day=holiday is not None,
        is_weekly_off=weekly_off,
        is_partial_day=partial_day,
        late_minutes=late_minutes,
        early_minutes=early_minutes,
    )

    remarks = None
    leave_code = None
    if status == "L" and leave_item:
        remarks = leave_item[1].Name
        leave_code = leave_item[1].Code
    elif status == "O" and holiday:
        remarks = holiday.HolidayName

    return DayResult(
        attendance_date=current_date,
        status=status,
        status_label=status_label,
        shift_id=shift_id,
        shift_name=shift_name,
        shift_time=shift_time,
        first_in=first_in,
        last_out=last_out,
        total_logs=len(day_logs),
        actual_work_minutes=actual_work_minutes,
        remarks=remarks,
        leave_code=leave_code,
        late_minutes=late_minutes,
        early_minutes=early_minutes,
        ot_minutes=ot_minutes,
    )


def _apply_sandwich_rules(
    results: list[DayResult],
    category: Optional[AttendanceCategory],
) -> None:
    """
    Second pass: mark weekly-off/holiday as Absent when adjacent workdays are absent.
    Prefix = day before is absent, Suffix = day after is absent, BothSides = both.
    Modifies results in place.
    """
    if category is None:
        return
    prefix = (category.MarkWeeklyOffHolidayAsAbsentPrefixAbsent or "N") == "Y"
    suffix = (category.MarkWeeklyOffHolidayAsAbsentSuffixAbsent or "N") == "Y"
    both = (category.MarkWeeklyOffHolidayAsAbsentBothSidesAbsent or "N") == "Y"
    if not prefix and not suffix and not both:
        return

    for i, r in enumerate(results):
        if r.status not in ("W", "O"):
            continue
        prev_absent = i > 0 and results[i - 1].status == "A"
        next_absent = i < len(results) - 1 and results[i + 1].status == "A"

        should_mark = False
        if both and prev_absent and next_absent:
            should_mark = True
        elif prefix and not both and prev_absent:
            should_mark = True
        elif suffix and not both and next_absent:
            should_mark = True

        if should_mark:
            r.status = "A"
            r.status_label = "Absent"
            r.remarks = "Sandwich rule"


LATE_PENALTY_REMARK = "Late penalty"


def _apply_cumulative_late_penalty(results: list[DayResult], rule: LateRule) -> None:
    """
    Late-count rule (Configuration -> Attendance Rules), applied per calendar month.

    Every day with a late IN punch counts (Present, Half Day, or a day with too few hours; days on
    leave, off days and days with no punch never count). The Nth late day is turned into a Half Day according to the
    rule mode: every Nth (3rd, 6th, 9th ...), the Nth and all later, or only the Nth.
    A day that is already a Half Day stays one, but still counts towards the total.
    """
    if not rule.enabled or rule.days <= 0:
        return

    month_key = None
    late_count = 0
    for r in results:
        key = (r.attendance_date.year, r.attendance_date.month)
        if key != month_key:
            month_key, late_count = key, 0
        # Any day with a late IN punch counts, even if the OUT punch is missing (that day
        # may be Absent for too few hours; it is counted but cannot be lowered further).
        if r.status not in ("P", "H", "A") or r.late_minutes <= 0 or r.total_logs <= 0:
            continue
        late_count += 1
        if not rule.penalises(late_count):
            continue
        if r.status == "P":
            r.status = "H"
            r.status_label = "Half Day"
            r.remarks = f"{LATE_PENALTY_REMARK}: late day {late_count} this month"
        else:
            r.remarks = ((r.remarks + "; ") if r.remarks else "") + f"late day {late_count} this month"


def compute_range(
    db: Session, code: str, from_date: date, to_date: date, rule: Optional[LateRule] = None,
) -> list[DayResult]:
    """
    Every rule, in order, for one employee over [from_date, to_date]. The single entry point
    used by the stored recalculation, the live month summary and the late-review tool.

    The late-count rule is monthly, so when it is on the calculation starts at the 1st of the
    month even if only a few days were asked for; only the requested days are returned.
    """
    rule = rule or get_late_rule(db)
    calc_from = from_date.replace(day=1) if rule.enabled else from_date
    range_start = datetime(calc_from.year, calc_from.month, calc_from.day)
    range_end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59)

    ctx = build_employee_context(db, code, range_start, range_end)

    results: list[DayResult] = []
    current = calc_from
    while current <= to_date:
        results.append(compute_day(ctx, current))
        current += timedelta(days=1)

    _apply_sandwich_rules(results, ctx.category)
    _apply_cumulative_late_penalty(results, rule)
    # Nothing after the last working day is attendance: no Absent days for someone who has left.
    cutoff = exit_cutoff(ctx.employee)
    return [r for r in results if r.attendance_date >= from_date and (cutoff is None or r.attendance_date <= cutoff)]


def _employee_codes_to_process(
    db: Session, range_start: datetime, range_end: datetime, employee_code: Optional[str]
) -> list[str]:
    if employee_code:
        return [employee_code]
    return [row[0] for row in db.query(Employee.EmployeeCode).all() if row[0]]


def process_range(
    db: Session,
    from_date: date,
    to_date: date,
    employee_code: Optional[str] = None,
) -> dict:
    """
    Recompute and upsert daily attendance for every employee across
    [from_date, to_date] inclusive. Idempotent — safe to re-run on any window.
    Returns {"employees": n, "days": n, "rows_written": n}.
    """
    range_start = datetime(from_date.year, from_date.month, from_date.day)
    range_end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59)

    codes = _employee_codes_to_process(db, range_start, range_end, employee_code)
    rule = get_late_rule(db)
    now = datetime.utcnow()
    rows_written = 0
    total_days = (to_date - from_date).days + 1

    for code in codes:
        cutoff = exit_cutoff(db.query(Employee).filter(Employee.EmployeeCode == code).first())
        if cutoff is not None and cutoff < to_date:
            # Days after the last working day are not attendance days: clear anything stored for them.
            db.query(AttendanceProcessed).filter(
                AttendanceProcessed.EmployeeCode == code,
                AttendanceProcessed.AttendanceDate >= max(cutoff + timedelta(days=1), from_date),
                AttendanceProcessed.AttendanceDate <= to_date,
            ).delete(synchronize_session=False)
        if cutoff is not None and cutoff < from_date:
            continue
        day_results = compute_range(db, code, from_date, to_date, rule)

        # Upsert into attendance_processed
        existing = {
            row.AttendanceDate: row
            for row in db.query(AttendanceProcessed)
            .filter(AttendanceProcessed.EmployeeCode == code)
            .filter(AttendanceProcessed.AttendanceDate >= from_date)
            .filter(AttendanceProcessed.AttendanceDate <= to_date)
            .all()
        }

        for result in day_results:
            row = existing.get(result.attendance_date)
            if row is None:
                row = AttendanceProcessed(EmployeeCode=code, AttendanceDate=result.attendance_date)
                db.add(row)
            row.Status = result.status
            row.StatusLabel = result.status_label
            row.ShiftId = result.shift_id
            row.ShiftName = result.shift_name
            row.ShiftTime = result.shift_time
            row.FirstIn = result.first_in
            row.LastOut = result.last_out
            row.TotalLogs = result.total_logs
            row.ActualWorkMinutes = result.actual_work_minutes
            row.LeaveCode = result.leave_code
            row.LateMinutes = result.late_minutes
            row.EarlyMinutes = result.early_minutes
            row.OTMinutes = result.ot_minutes
            row.Remarks = result.remarks
            row.ProcessedAt = now
            rows_written += 1

        db.flush()

    db.commit()
    return {"employees": len(codes), "days": total_days, "rows_written": rows_written}
