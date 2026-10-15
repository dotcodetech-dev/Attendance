"""Business logic for holidays (3-tier: Application tier)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import Holiday
from app.repositories.holiday_repository import HolidayRepository
from app.schemas.holiday import HolidayCreate, HolidayUpdate


def _as_datetime(value: date) -> datetime:
    """holidays.HolidayDate is a DATETIME column; the API accepts a plain date."""
    return value if isinstance(value, datetime) else datetime.combine(value, time.min)


class HolidayService:
    def __init__(self, session: Session) -> None:
        self._repo = HolidayRepository(session)

    def list_all(self, year: Optional[int] = None) -> List[Holiday]:
        return self._repo.list_all(year)

    def create(self, payload: HolidayCreate) -> Holiday:
        exists = self._repo.find_by_date_and_name(
            _as_datetime(payload.HolidayDate),
            payload.HolidayName,
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Holiday with same date and name already exists",
            )
        data = payload.model_dump()
        data["HolidayDate"] = _as_datetime(data["HolidayDate"])
        row = Holiday(**data)
        return self._repo.add(row)

    def update(self, holiday_id: int, payload: HolidayUpdate) -> Holiday:
        row = self._repo.get_by_id(holiday_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Holiday not found",
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "HolidayDate" and value is not None:
                value = _as_datetime(value)
            setattr(row, field, value)
        return self._repo.update(row)

    def delete(self, holiday_id: int) -> dict[str, bool]:
        row = self._repo.get_by_id(holiday_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Holiday not found",
            )
        self._repo.delete(row)
        return {"deleted": True}
