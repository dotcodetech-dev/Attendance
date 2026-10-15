"""Data access for ShiftRoster."""

from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.models.entities import ShiftRoster
from app.repositories.base import BaseRepository


class RosterRepository(BaseRepository[ShiftRoster]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ShiftRoster)

    def list_all(self, employee_code: str | None = None) -> List[ShiftRoster]:
        q = self._session.query(ShiftRoster).order_by(
            ShiftRoster.EmployeeCode.asc(),
            ShiftRoster.FromDate.asc(),
        )
        if employee_code:
            q = q.filter(ShiftRoster.EmployeeCode == employee_code)
        return q.all()

    def get_by_id(self, roster_id: int) -> ShiftRoster | None:
        return (
            self._session.query(ShiftRoster)
            .filter(ShiftRoster.ShiftRosterId == roster_id)
            .first()
        )

    def add(self, entity: ShiftRoster) -> ShiftRoster:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: ShiftRoster) -> ShiftRoster:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: ShiftRoster) -> None:
        self._session.delete(entity)
        self._session.commit()
