"""Module provisions (on/off switches) stored in `mastersettings`."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import MasterSetting

STUDENT_MODULE_KEY = "StudentModuleEnabled"


def student_module_enabled(db: Session) -> bool:
    row = db.query(MasterSetting).filter(MasterSetting.Name == STUDENT_MODULE_KEY).first()
    return bool(row and row.Value == "Y")


def set_student_module_enabled(db: Session, enabled: bool) -> None:
    row = db.query(MasterSetting).filter(MasterSetting.Name == STUDENT_MODULE_KEY).first()
    if row is None:
        row = MasterSetting(Name=STUDENT_MODULE_KEY)
        db.add(row)
    row.Value = "Y" if enabled else "N"


def require_student_module(db: Session = Depends(get_db)) -> None:
    if not student_module_enabled(db):
        raise HTTPException(
            status_code=403,
            detail="Student Attendance module is disabled. Enable it in Module Configuration.",
        )


# ---- Student Attendance sub-options (Module Configuration, nested under the module switch) ----
STUDENT_LEAVES_KEY = "StudentLeavesEnabled"            # default on: anything but "N"
STUDENT_ABSENT_WEEKLY_OFF_KEY = "StudentAbsentOnWeeklyOff"  # default off: only "Y" turns it on


def _get(db: Session, key: str) -> str | None:
    row = db.query(MasterSetting).filter(MasterSetting.Name == key).first()
    return row.Value if row else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(MasterSetting).filter(MasterSetting.Name == key).first()
    if row is None:
        row = MasterSetting(Name=key)
        db.add(row)
    row.Value = value


def student_leaves_enabled(db: Session) -> bool:
    """Leaves need the student module itself to be on too."""
    return student_module_enabled(db) and _get(db, STUDENT_LEAVES_KEY) != "N"


def student_leaves_switch(db: Session) -> bool:
    """The switch's own value (ignores the parent module), for the settings page."""
    return _get(db, STUDENT_LEAVES_KEY) != "N"


def set_student_leaves(db: Session, enabled: bool) -> None:
    _set(db, STUDENT_LEAVES_KEY, "Y" if enabled else "N")


def absent_on_weekly_off(db: Session) -> bool:
    return _get(db, STUDENT_ABSENT_WEEKLY_OFF_KEY) == "Y"


def set_absent_on_weekly_off(db: Session, enabled: bool) -> bool:
    """Returns True when the value changed (callers then recompute stored days)."""
    changed = absent_on_weekly_off(db) != enabled
    _set(db, STUDENT_ABSENT_WEEKLY_OFF_KEY, "Y" if enabled else "N")
    return changed


def require_student_leaves(db: Session = Depends(get_db)) -> None:
    if not student_leaves_enabled(db):
        raise HTTPException(
            status_code=403,
            detail="Student Leaves is turned off. Enable it in Module Configuration.",
        )
