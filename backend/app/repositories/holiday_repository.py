"""Data access for Holiday."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import Holiday
from app.repositories.base import BaseRepository


class HolidayRepository(BaseRepository[Holiday]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Holiday)

    def list_all(self, year: int | None = None) -> List[Holiday]:
        q = self._session.query(Holiday)
        if year is not None:
            q = q.filter(Holiday.HolidayDate >= f"{year}-01-01").filter(
                Holiday.HolidayDate <= f"{year}-12-31"
            )
        return q.order_by(Holiday.HolidayDate.asc()).all()

    def find_by_date_and_name(self, holiday_date, holiday_name: str) -> Holiday | None:
        return (
            self._session.query(Holiday)
            .filter(
                Holiday.HolidayDate == holiday_date,
                Holiday.HolidayName == holiday_name,
            )
            .first()
        )

    def get_by_id(self, holiday_id: int) -> Holiday | None:
        return (
            self._session.query(Holiday)
            .filter(Holiday.HolidayId == holiday_id)
            .first()
        )

    def add(self, entity: Holiday) -> Holiday:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: Holiday) -> Holiday:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: Holiday) -> None:
        self._session.delete(entity)
        self._session.commit()
