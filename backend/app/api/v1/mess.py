"""Mess Token Print API."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.feature_flags import (
    absent_on_weekly_off,
    set_absent_on_weekly_off,
    set_student_leaves,
    set_student_module_enabled,
    student_leaves_switch,
    student_module_enabled,
)
from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import MessMeal
from app.services import mess_service

router = APIRouter()


class MealIn(BaseModel):
    MealType: str
    StartTime: str  # HH:MM
    EndTime: str
    IsActive: str = "Y"


class SettingsUpdate(BaseModel):
    enabled: bool
    meals: Optional[List[MealIn]] = None
    mess_device_id: Optional[int] = None  # device whose punches auto-issue tokens (None/0 = off)
    auto_print: Optional[bool] = None
    student_module_enabled: Optional[bool] = None  # provision: Student Attendance module on/off
    student_leaves_enabled: Optional[bool] = None  # sub-option: Student Leaves menu/pages
    student_absent_on_weekly_off: Optional[bool] = None  # sub-option: no punch on weekly off = Absent


class TokenRequest(BaseModel):
    employee_code: str


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    meals = mess_service.list_meals(db)
    return {
        "enabled": mess_service.get_enabled(db),
        "mess_device_id": mess_service.get_mess_device_id(db),
        "auto_print": mess_service.get_auto_print(db),
        "student_module_enabled": student_module_enabled(db),
        "student_leaves_enabled": student_leaves_switch(db),
        "student_absent_on_weekly_off": absent_on_weekly_off(db),
        "meals": [
            {"MessMealId": m.MessMealId, "MealType": m.MealType, "StartTime": m.StartTime,
             "EndTime": m.EndTime, "IsActive": m.IsActive}
            for m in meals
        ],
    }


@router.put("/settings")
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    mess_service.set_enabled(db, payload.enabled)
    if payload.mess_device_id is not None:
        mess_service._set_setting(db, mess_service.DEVICE_KEY, str(payload.mess_device_id) if payload.mess_device_id else "")
    if payload.auto_print is not None:
        mess_service._set_setting(db, mess_service.AUTOPRINT_KEY, "Y" if payload.auto_print else "N")
    if payload.student_module_enabled is not None:
        set_student_module_enabled(db, payload.student_module_enabled)
    if payload.student_leaves_enabled is not None:
        set_student_leaves(db, payload.student_leaves_enabled)
    if payload.student_absent_on_weekly_off is not None:
        if set_absent_on_weekly_off(db, payload.student_absent_on_weekly_off):
            # Stored days were computed under the old rule: drop the automatic ones so they recompute.
            from app.models.entities import StudentAttendanceProcessed as P
            db.query(P).filter(P.Source == "Auto", P.Status.in_(["WeeklyOff", "Absent"])).delete(synchronize_session=False)
    if payload.meals is not None:
        by_type = {m.MealType: m for m in db.query(MessMeal).all()}
        for i, meal in enumerate(payload.meals):
            row = by_type.get(meal.MealType)
            if row is None:
                row = MessMeal(MealType=meal.MealType, SortOrder=i + 1)
                db.add(row)
            row.StartTime = meal.StartTime.strip()
            row.EndTime = meal.EndTime.strip()
            row.IsActive = meal.IsActive if meal.IsActive in ("Y", "N") else "Y"
    db.commit()
    return get_settings(db, _user)


@router.get("/kiosk-feed")
def kiosk_feed(since_id: int = 0, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """New tokens (id > since_id) for a mess kiosk display to auto-print."""
    return {"auto_print": mess_service.get_auto_print(db), "tokens": mess_service.kiosk_feed(db, since_id)}


@router.post("/token")
def generate_token(payload: TokenRequest, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = mess_service.generate_token(db, payload.employee_code)
    if not result.get("ok"):
        # 200 with ok=False so the UI can show the message inline (disabled / no meal / not found)
        return result
    return result


@router.post("/token/{token_id}/reprint")
def reprint_token(token_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = mess_service.reprint(db, token_id)
    if result is None:
        raise HTTPException(404, "Token not found")
    return result


@router.get("/tokens")
def list_tokens(
    on_date: Optional[date] = Query(default=None, alias="date"),
    meal: Optional[str] = Query(default=None),
    employee_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return mess_service.list_tokens(db, on_date, meal, employee_code)
