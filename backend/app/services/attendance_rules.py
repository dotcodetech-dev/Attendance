from __future__ import annotations

from typing import Optional

from app.models.entities import AttendanceCategory


def classify_workday(
    *,
    category: Optional[AttendanceCategory],
    actual_work_minutes: int,
    has_logs: bool,
    is_leave: bool,
    is_off_day: bool,
    is_weekly_off: bool = False,
    is_partial_day: bool = False,
    late_minutes: int = 0,
    early_minutes: int = 0,
) -> tuple[str, str]:
    """
    Determine attendance status based on category thresholds.

    Returns status code and label:
    - P: Present
    - H: Half Day
    - A: Absent
    - L: Leave
    - O: Off Day (holiday)
    - W: Weekly Off
    """
    if is_leave:
        return "L", "Leave"
    if is_off_day:
        return "O", "Off Day"
    if is_weekly_off and not has_logs:
        return "W", "Weekly Off"
    if not has_logs:
        return "A", "Absent"

    # Pick thresholds — partial-day overrides when configured and > 0.
    if is_partial_day and category:
        pd_half = int(category.PartialDayCalculateHalfDayIfWorkDurationLessThanMinutes or 0)
        pd_absent = int(category.PartialDayCalculateAbsentIfWorkDurationLessThanMinutes or 0)
        half_day_threshold = pd_half if pd_half > 0 else int(category.HalfDayIfWorkDurationLessThanMinutes or 240)
        absent_threshold = pd_absent if pd_absent > 0 else int(category.AbsentIfWorkDurationLessThanMinutes or 120)
    else:
        half_day_threshold = (
            int(category.HalfDayIfWorkDurationLessThanMinutes)
            if category and category.HalfDayIfWorkDurationLessThanMinutes is not None
            else 240
        )
        absent_threshold = (
            int(category.AbsentIfWorkDurationLessThanMinutes)
            if category and category.AbsentIfWorkDurationLessThanMinutes is not None
            else 120
        )

    if actual_work_minutes < absent_threshold:
        return "A", "Absent"
    if actual_work_minutes < half_day_threshold:
        return "H", "Half Day"

    # Single-day late / early-going penalty → Half Day override
    if category:
        late_pen = int(category.MarkHalfDayIfLateByMinutes or 0)
        early_pen = int(category.MarkHalfDayIfEarlyGoingByMinutes or 0)
        if late_pen > 0 and late_minutes >= late_pen:
            return "H", "Half Day"
        if early_pen > 0 and early_minutes >= early_pen:
            return "H", "Half Day"

    return "P", "Present"
