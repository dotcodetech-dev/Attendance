"""
Attendance calculation settings shared by every employee (Configuration -> Attendance Rules).
Stored as key/value rows in `mastersettings`, like the other module switches.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.entities import MasterSetting

LATE_ENABLED_KEY = "LateRuleEnabled"   # Y / N
LATE_DAYS_KEY = "LateRuleDays"         # N: the Nth late day in a month is penalised
LATE_MODE_KEY = "LateRuleMode"         # every | from | only

MODES = ("every", "from", "only")


@dataclass(frozen=True)
class LateRule:
    enabled: bool = True
    days: int = 3
    mode: str = "every"

    def penalises(self, late_day_number: int) -> bool:
        """Should the Nth late day of the month become a half day?"""
        if not self.enabled or self.days <= 0:
            return False
        if self.mode == "from":
            return late_day_number >= self.days
        if self.mode == "only":
            return late_day_number == self.days
        return late_day_number % self.days == 0  # every


def _get(db: Session, key: str):
    row = db.query(MasterSetting).filter(MasterSetting.Name == key).first()
    return row.Value if row and row.Value not in (None, "") else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(MasterSetting).filter(MasterSetting.Name == key).first()
    if row is None:
        row = MasterSetting(Name=key)
        db.add(row)
    row.Value = value


def get_late_rule(db: Session) -> LateRule:
    """Defaults apply until someone saves the page: on, every 3rd late day."""
    enabled = _get(db, LATE_ENABLED_KEY)
    days = _get(db, LATE_DAYS_KEY)
    mode = _get(db, LATE_MODE_KEY)
    try:
        n = int(days) if days is not None else 3
    except ValueError:
        n = 3
    return LateRule(
        enabled=(enabled != "N"),
        days=max(1, min(n, 31)),
        mode=mode if mode in MODES else "every",
    )


# ---------------------------------------------------------------- punch rule
PUNCH_DUP_KEY = "PunchDuplicateSeconds"   # punches closer than this (same employee) are one punch
PUNCH_DIR_KEY = "PunchDirectionMode"      # alternate | device

DIRECTION_MODES = ("alternate", "device")


@dataclass(frozen=True)
class PunchRule:
    duplicate_seconds: int = 60
    direction_mode: str = "alternate"   # alternate: 1st punch of the day IN, 2nd OUT, 3rd IN ...


def get_punch_rule(db: Session) -> PunchRule:
    secs = _get(db, PUNCH_DUP_KEY)
    mode = _get(db, PUNCH_DIR_KEY)
    try:
        n = int(secs) if secs is not None else 60
    except ValueError:
        n = 60
    return PunchRule(duplicate_seconds=max(0, min(n, 3600)), direction_mode=mode if mode in DIRECTION_MODES else "alternate")


def set_punch_rule(db: Session, duplicate_seconds: int, direction_mode: str) -> PunchRule:
    if direction_mode not in DIRECTION_MODES:
        raise ValueError("direction_mode must be one of: " + ", ".join(DIRECTION_MODES))
    _set(db, PUNCH_DUP_KEY, str(max(0, min(int(duplicate_seconds), 3600))))
    _set(db, PUNCH_DIR_KEY, direction_mode)
    db.commit()
    return get_punch_rule(db)


def set_late_rule(db: Session, enabled: bool, days: int, mode: str) -> LateRule:
    if mode not in MODES:
        raise ValueError("mode must be one of: " + ", ".join(MODES))
    days = max(1, min(int(days), 31))
    _set(db, LATE_ENABLED_KEY, "Y" if enabled else "N")
    _set(db, LATE_DAYS_KEY, str(days))
    _set(db, LATE_MODE_KEY, mode)
    db.commit()
    return get_late_rule(db)
