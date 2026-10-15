"""Data access for ManualEntry."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import ManualEntry
from app.repositories.base import BaseRepository


class ManualEntryRepository(BaseRepository[ManualEntry]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ManualEntry)

    def list_by_employee(
        self,
        employee_code: str,
        from_date=None,
        to_date=None,
    ) -> List[ManualEntry]:
        q = (
            self._session.query(ManualEntry)
            .filter(ManualEntry.EmployeeCode == employee_code)
            .order_by(ManualEntry.LogDate.desc())
        )
        if from_date:
            q = q.filter(ManualEntry.LogDate >= from_date)
        if to_date:
            q = q.filter(ManualEntry.LogDate <= to_date)
        return q.all()

    def get_by_id(self, manual_entry_id: int) -> ManualEntry | None:
        return (
            self._session.query(ManualEntry)
            .filter(ManualEntry.ManualEntryId == manual_entry_id)
            .first()
        )

    def add(self, entity: ManualEntry) -> ManualEntry:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: ManualEntry) -> ManualEntry:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: ManualEntry) -> None:
        self._session.delete(entity)
        self._session.commit()
