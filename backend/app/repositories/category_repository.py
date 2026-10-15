"""Data access for AttendanceCategory."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import AttendanceCategory
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[AttendanceCategory]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AttendanceCategory)

    def list_all(self) -> List[AttendanceCategory]:
        return (
            self._session.query(AttendanceCategory)
            .order_by(AttendanceCategory.CategoryName.asc())
            .all()
        )

    def get_by_id(self, category_id: int) -> AttendanceCategory | None:
        return (
            self._session.query(AttendanceCategory)
            .filter(AttendanceCategory.CategoryId == category_id)
            .first()
        )

    def find_by_name_or_short_name(
        self, category_name: str, short_name: str | None
    ) -> AttendanceCategory | None:
        q = self._session.query(AttendanceCategory).filter(
            (AttendanceCategory.CategoryName == category_name)
            | (AttendanceCategory.ShortName == short_name)
        )
        return q.first()

    def find_duplicate_excluding(
        self, category_id: int, category_name: str, short_name: str | None
    ) -> AttendanceCategory | None:
        return (
            self._session.query(AttendanceCategory)
            .filter(AttendanceCategory.CategoryId != category_id)
            .filter(
                (AttendanceCategory.CategoryName == category_name)
                | (AttendanceCategory.ShortName == short_name)
            )
            .first()
        )

    def add(self, entity: AttendanceCategory) -> AttendanceCategory:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: AttendanceCategory) -> AttendanceCategory:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: AttendanceCategory) -> None:
        self._session.delete(entity)
        self._session.commit()
