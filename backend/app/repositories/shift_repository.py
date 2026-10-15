"""Data access for Shift."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import Shift
from app.repositories.base import BaseRepository


class ShiftRepository(BaseRepository[Shift]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Shift)

    def list_all(self) -> List[Shift]:
        return self._session.query(Shift).order_by(Shift.ShiftName.asc()).all()

    def get_by_id(self, shift_id: int) -> Shift | None:
        return (
            self._session.query(Shift)
            .filter(Shift.ShiftId == shift_id)
            .first()
        )

    def find_by_name_or_short_name(
        self, shift_name: str, short_name: str | None
    ) -> Shift | None:
        q = self._session.query(Shift).filter(
            (Shift.ShiftName == shift_name) | (Shift.ShortName == short_name)
        )
        return q.first()

    def find_duplicate_excluding(
        self, shift_id: int, shift_name: str, short_name: str | None
    ) -> Shift | None:
        return (
            self._session.query(Shift)
            .filter(Shift.ShiftId != shift_id)
            .filter(
                (Shift.ShiftName == shift_name) | (Shift.ShortName == short_name)
            )
            .first()
        )

    def clear_default_except(self, shift_id: int | None = None) -> None:
        """Unset IsDefault on every shift except the given one (single-default invariant)."""
        q = self._session.query(Shift).filter(Shift.IsDefault == "Y")
        if shift_id is not None:
            q = q.filter(Shift.ShiftId != shift_id)
        for row in q.all():
            row.IsDefault = "N"

    def add(self, entity: Shift) -> Shift:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: Shift) -> Shift:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: Shift) -> None:
        self._session.delete(entity)
        self._session.commit()
