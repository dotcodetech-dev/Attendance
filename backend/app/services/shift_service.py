"""Business logic for shifts (3-tier: Application tier)."""

from __future__ import annotations

from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import Shift
from app.repositories.shift_repository import ShiftRepository
from app.schemas.shift import ShiftCreate, ShiftUpdate


def _to_minutes(value: str) -> int:
    parts = (value or "0:0").split(":")
    return int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 0


def _normalize_shift_payload(values: dict) -> dict:
    data = dict(values)
    if isinstance(data.get("ShortName"), str):
        short_name = data["ShortName"].strip()
        data["ShortName"] = short_name or None
    for key in (
        "Break1StartTime", "Break1EndTime", "Break2StartTime", "Break2EndTime",
        "PartialDayStartTime", "PartialDayEndTime",
    ):
        if isinstance(data.get(key), str):
            value = data[key].strip()
            data[key] = value or None
    if not data.get("ShortName") and data.get("ShiftName"):
        data["ShortName"] = str(data["ShiftName"]).strip()[:20]
    if data.get("Break1Enabled") != "Y":
        data["Break1Enabled"] = "N"
        data["Break1StartTime"] = data["Break1EndTime"] = None
    if data.get("Break2Enabled") != "Y":
        data["Break2Enabled"] = "N"
        data["Break2StartTime"] = data["Break2EndTime"] = None
    if data.get("PartialDayEnabled") != "Y":
        data["PartialDayEnabled"] = "N"
        data["PartialDayWeekday"] = data["PartialDayStartTime"] = data["PartialDayEndTime"] = None
    if data.get("IsFlexibleShift") != "Y":
        data["IsFlexibleShift"] = "N"
    if data.get("IsDefault") != "Y":
        data["IsDefault"] = "N"
    if data.get("GraceTimeMinutes") is not None:
        data["GraceInMinutes"] = data["GraceTimeMinutes"]
    if data.get("GraceOutMinutes") is None:
        data["GraceOutMinutes"] = 0
    return data


def _validate_shift_payload(values: dict) -> None:
    start, end = values.get("StartTime"), values.get("EndTime")
    if start and end and start == end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shift begin and end time cannot be the same",
        )
    for label in ("Break1", "Break2"):
        enabled = values.get(f"{label}Enabled") == "Y"
        s, e = values.get(f"{label}StartTime"), values.get(f"{label}EndTime")
        if enabled and (not s or not e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} start and end time are required when enabled",
            )
        if enabled and s == e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} start and end time cannot be the same",
            )
    if values.get("PartialDayEnabled") == "Y":
        if not values.get("PartialDayWeekday"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Partial day weekday is required when partial day is enabled",
            )
        ps, pe = values.get("PartialDayStartTime"), values.get("PartialDayEndTime")
        if not ps or not pe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Partial day start and end time are required",
            )
        if ps == pe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Partial day start and end time cannot be the same",
            )
    if (
        values.get("Break1Enabled") == "Y"
        and values.get("Break2Enabled") == "Y"
        and values.get("Break1StartTime")
        and values.get("Break1EndTime")
        and values.get("Break2StartTime")
        and values.get("Break2EndTime")
    ):
        b1s, b1e = _to_minutes(values["Break1StartTime"]), _to_minutes(values["Break1EndTime"])
        b2s, b2e = _to_minutes(values["Break2StartTime"]), _to_minutes(values["Break2EndTime"])
        if max(b1s, b2s) < min(b1e, b2e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Break 1 and Break 2 cannot overlap",
            )


class ShiftService:
    def __init__(self, session: Session) -> None:
        self._repo = ShiftRepository(session)

    def list_all(self) -> List[Shift]:
        return self._repo.list_all()

    def get_by_id(self, shift_id: int) -> Shift:
        row = self._repo.get_by_id(shift_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift not found",
            )
        return row

    def create(self, payload: ShiftCreate) -> Shift:
        exists = self._repo.find_by_name_or_short_name(
            payload.ShiftName,
            payload.ShortName,
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift name or short name already exists",
            )
        values = _normalize_shift_payload(payload.model_dump())
        _validate_shift_payload(values)
        if values.get("IsDefault") == "Y":
            self._repo.clear_default_except(None)
        row = Shift(**values)
        return self._repo.add(row)

    def update(self, shift_id: int, payload: ShiftUpdate) -> Shift:
        row = self._repo.get_by_id(shift_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift not found",
            )
        values = _normalize_shift_payload({
            **{k: v for k, v in row.__dict__.items() if not k.startswith("_sa_")},
            **payload.model_dump(exclude_unset=True),
        })
        duplicate = self._repo.find_duplicate_excluding(
            shift_id,
            values.get("ShiftName", ""),
            values.get("ShortName"),
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift name or short name already exists",
            )
        _validate_shift_payload(values)
        if values.get("IsDefault") == "Y":
            self._repo.clear_default_except(shift_id)
        for field, value in values.items():
            if not field.startswith("_sa_") and hasattr(row, field):
                setattr(row, field, value)
        return self._repo.update(row)

    def delete(self, shift_id: int) -> dict[str, bool]:
        row = self._repo.get_by_id(shift_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shift not found",
            )
        self._repo.delete(row)
        return {"deleted": True}
