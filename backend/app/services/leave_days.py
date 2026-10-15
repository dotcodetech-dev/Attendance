"""
How many days a leave really takes, honouring the leave type's switches:
  ConsiderWeeklyOff = Y -> weekly offs inside the leave are deducted too (N: skipped)
  ConsiderHoliday   = Y -> holidays inside the leave are deducted too   (N: skipped)
The attendance engine uses the same rule (see compute_day), so balances and the
attendance register always agree.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import AttendanceCategory, Employee, Holiday, LeaveConfig


@dataclass
class LeaveDays:
    counted: int
    calendar_days: int
    skipped_weekly_off: int
    skipped_holidays: int


def leave_applies_on(config: Optional[LeaveConfig], *, is_holiday: bool, is_weekly_off: bool) -> bool:
    """Does this leave type cover a day that is a holiday / weekly off?"""
    if config is None:
        return True
    if is_holiday and (config.ConsiderHoliday or "N") != "Y":
        return False
    if is_weekly_off and (config.ConsiderWeeklyOff or "N") != "Y":
        return False
    return True


def _category_for(db: Session, employee_code: str) -> Optional[AttendanceCategory]:
    emp = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
    if not emp or emp.CategoryId is None:
        return None
    return (
        db.query(AttendanceCategory)
        .filter(AttendanceCategory.CategoryId == emp.CategoryId)
        .filter((AttendanceCategory.IsActive.is_(None)) | (AttendanceCategory.IsActive == "Y"))
        .first()
    )


def count_leave_days(
    db: Session, employee_code: str, config: Optional[LeaveConfig], from_date: date, to_date: date,
    *, clip_from: Optional[date] = None, clip_to: Optional[date] = None,
) -> LeaveDays:
    """Days deducted for a leave from `from_date` to `to_date` (inclusive), optionally clipped to a window."""
    from app.services.attendance_processing import _is_weekly_off  # local import: avoids a cycle

    start = max(from_date, clip_from) if clip_from else from_date
    end = min(to_date, clip_to) if clip_to else to_date
    if end < start:
        return LeaveDays(0, 0, 0, 0)

    category = _category_for(db, employee_code)
    holidays = {
        h.HolidayDate.date()
        for h in db.query(Holiday)
        .filter(Holiday.HolidayDate >= datetime(start.year, start.month, start.day))
        .filter(Holiday.HolidayDate <= datetime(end.year, end.month, end.day, 23, 59, 59))
        .filter(Holiday.IsActive == "Y")
        .all()
    }

    counted = skipped_wo = skipped_h = 0
    day = start
    while day <= end:
        is_h = day in holidays
        is_wo = _is_weekly_off(category, day)
        if leave_applies_on(config, is_holiday=is_h, is_weekly_off=is_wo):
            counted += 1
        elif is_h:
            skipped_h += 1
        else:
            skipped_wo += 1
        day += timedelta(days=1)
    return LeaveDays(counted, (end - start).days + 1, skipped_wo, skipped_h)
