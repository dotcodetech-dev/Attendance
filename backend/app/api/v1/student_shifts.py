"""Student shifts (separate from employee shifts)."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.feature_flags import require_student_module
from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import Student, StudentShift

router = APIRouter(dependencies=[Depends(require_student_module)])
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DAYS = {"", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


class ShiftIn(BaseModel):
    ShiftName: str = Field(min_length=1, max_length=100)
    StartTime: str
    EndTime: str
    GraceInMinutes: int = Field(default=10, ge=0, le=240)
    HalfDayMinutes: int = Field(default=240, ge=0, le=1440)
    WeeklyOff: Optional[str] = "Sunday"
    IsActive: str = "Y"

    @field_validator("StartTime", "EndTime")
    @classmethod
    def _t(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("Time must be HH:MM (24h)")
        return v

    @field_validator("WeeklyOff")
    @classmethod
    def _d(cls, v: Optional[str]) -> Optional[str]:
        if (v or "").lower() not in _DAYS:
            raise ValueError("WeeklyOff must be a weekday name or blank")
        return v or None


def _dto(s: StudentShift) -> dict:
    return {c: getattr(s, c) for c in ("StudentShiftId", "ShiftName", "StartTime", "EndTime",
                                        "GraceInMinutes", "HalfDayMinutes", "WeeklyOff", "IsActive")}


@router.get("")
def list_shifts(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return [_dto(s) for s in db.query(StudentShift).order_by(StudentShift.StudentShiftId).all()]


@router.post("")
def create_shift(p: ShiftIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    s = StudentShift(**p.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return _dto(s)


@router.put("/{shift_id}")
def update_shift(shift_id: int, p: ShiftIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    s = db.get(StudentShift, shift_id)
    if not s:
        raise HTTPException(404, "Shift not found")
    for k, v in p.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return _dto(s)


@router.delete("/{shift_id}")
def delete_shift(shift_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    s = db.get(StudentShift, shift_id)
    if not s:
        raise HTTPException(404, "Shift not found")
    if db.query(Student.StudentId).filter(Student.StudentShiftId == shift_id).first():
        raise HTTPException(409, "Shift is assigned to students")
    db.delete(s)
    db.commit()
    return {"ok": True}
