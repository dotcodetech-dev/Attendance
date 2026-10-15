"""
Punch hygiene shared by every ingest path (device push, SDK pull, face camera).

  * Duplicate window: a face reader keeps re-recognising a face that lingers in
    front of it and pushes the same punch 5-10 times within seconds. Any new
    punch within `duplicate_seconds` of the last KEPT punch of that employee
    (on any device) is dropped.
  * Direction: readers without an IN/OUT key report no state, so the row ended
    up as the device default "INOUT". In `alternate` mode the punches of one
    employee-day are numbered in time order: 1st IN, 2nd OUT, 3rd IN, ...
    `device` mode keeps whatever the device said.

Settings come from Configuration -> Attendance Rules (attendance_settings.PunchRule).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.entities import DeviceLog
from app.services.attendance_settings import PunchRule, get_punch_rule


def collapse_duplicates(logs: list[DeviceLog], duplicate_seconds: int) -> list[DeviceLog]:
    """Time-ordered logs -> logs with bursts collapsed to the first punch of each burst
    (compared against the last KEPT punch). Used by the attendance calculation so
    duplicates that were stored before this rule existed do not matter either."""
    if duplicate_seconds <= 0 or len(logs) < 2:
        return list(logs)
    window = timedelta(seconds=duplicate_seconds)
    kept: list[DeviceLog] = []
    for row in sorted(logs, key=lambda r: r.LogDate):
        if kept and row.LogDate - kept[-1].LogDate < window:
            continue
        kept.append(row)
    return kept


def filter_new_punches(db: Session, candidates: list[dict], rule: PunchRule | None = None) -> list[dict]:
    """Drop candidate punches (dicts with EmployeeCode + LogDate) that fall inside the
    duplicate window of an already stored punch of the same employee, or of another
    candidate. Returns the survivors in time order."""
    rule = rule or get_punch_rule(db)
    if not candidates:
        return []
    if rule.duplicate_seconds <= 0:
        return list(candidates)
    window = timedelta(seconds=rule.duplicate_seconds)
    codes = {c["EmployeeCode"] for c in candidates}
    lo = min(c["LogDate"] for c in candidates) - window
    hi = max(c["LogDate"] for c in candidates) + window
    existing: dict[str, list[datetime]] = {c: [] for c in codes}
    for code, when in (
        db.query(DeviceLog.EmployeeCode, DeviceLog.LogDate)
        .filter(DeviceLog.EmployeeCode.in_(list(codes)), DeviceLog.LogDate >= lo, DeviceLog.LogDate <= hi)
        .all()
    ):
        existing[code].append(when)

    kept: list[dict] = []
    last_kept: dict[str, datetime] = {}
    for c in sorted(candidates, key=lambda x: x["LogDate"]):
        code, when = c["EmployeeCode"], c["LogDate"]
        # already stored punch close by (before or after) -> this one is a repeat
        if any(abs(when - e) < window for e in existing.get(code, ())):
            continue
        prev = last_kept.get(code)
        if prev is not None and when - prev < window:
            continue
        last_kept[code] = when
        kept.append(c)
    return kept


def assign_directions(db: Session, keys: Iterable[tuple[str, date]], rule: PunchRule | None = None) -> int:
    """Re-number the stored punches of each (employee, day): 1st IN, 2nd OUT, ...
    Call after inserting punches (late-arriving SDK backlog can shift the order).
    Returns the number of rows changed."""
    rule = rule or get_punch_rule(db)
    if rule.direction_mode != "alternate":
        return 0
    changed = 0
    for code, day in set(keys):
        start = datetime.combine(day, datetime.min.time())
        rows = (
            db.query(DeviceLog)
            .filter(DeviceLog.EmployeeCode == code, DeviceLog.LogDate >= start, DeviceLog.LogDate < start + timedelta(days=1))
            .order_by(DeviceLog.LogDate.asc(), DeviceLog.DeviceLogId.asc())
            .all()
        )
        for i, row in enumerate(rows):
            want = "IN" if i % 2 == 0 else "OUT"
            if row.Direction != want:
                row.Direction = want
                changed += 1
    return changed


def day_keys(punches: Iterable[dict]) -> set[tuple[str, date]]:
    return {(p["EmployeeCode"], p["LogDate"].date()) for p in punches}


def repair_stored_punches(db: Session, from_day: date, to_day: date, rule: PunchRule | None = None) -> dict:
    """Apply the rule to history: delete repeats inside the duplicate window (keeping the
    first punch of every burst) and re-number IN/OUT for every employee-day in range."""
    rule = rule or get_punch_rule(db)
    start = datetime.combine(from_day, datetime.min.time())
    end = datetime.combine(to_day, datetime.min.time()) + timedelta(days=1)
    rows = (
        db.query(DeviceLog)
        .filter(DeviceLog.LogDate >= start, DeviceLog.LogDate < end)
        .order_by(DeviceLog.EmployeeCode.asc(), DeviceLog.LogDate.asc(), DeviceLog.DeviceLogId.asc())
        .all()
    )
    deleted = 0
    keys: set[tuple[str, date]] = set()
    by_code: dict[str, list[DeviceLog]] = {}
    for r in rows:
        by_code.setdefault(r.EmployeeCode, []).append(r)
        keys.add((r.EmployeeCode, r.LogDate.date()))
    if rule.duplicate_seconds > 0:
        for code, logs in by_code.items():
            keep_ids = {r.DeviceLogId for r in collapse_duplicates(logs, rule.duplicate_seconds)}
            for r in logs:
                if r.DeviceLogId not in keep_ids:
                    db.delete(r)
                    deleted += 1
        db.flush()
    redirected = assign_directions(db, keys, rule)
    db.commit()
    return {"from": from_day.isoformat(), "to": to_day.isoformat(), "punches": len(rows),
            "duplicates_deleted": deleted, "directions_changed": redirected, "employee_days": len(keys)}
