"""Business logic for attendance categories (3-tier: Application tier)."""

from __future__ import annotations

from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import AttendanceCategory
from app.repositories.category_repository import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


def _normalize(values: dict) -> dict:
    data = dict(values)
    if isinstance(data.get("ShortName"), str):
        value = data["ShortName"].strip()
        data["ShortName"] = value or None
    if not data.get("ShortName") and data.get("CategoryName"):
        data["ShortName"] = str(data["CategoryName"]).strip()[:30]
    return data


class CategoryService:
    def __init__(self, session: Session) -> None:
        self._repo = CategoryRepository(session)

    def list_all(self) -> List[AttendanceCategory]:
        return self._repo.list_all()

    def get_by_id(self, category_id: int) -> AttendanceCategory:
        row = self._repo.get_by_id(category_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )
        return row

    def create(self, payload: CategoryCreate) -> AttendanceCategory:
        values = _normalize(payload.model_dump())
        exists = self._repo.find_by_name_or_short_name(
            values["CategoryName"],
            values.get("ShortName"),
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name or short name already exists",
            )
        row = AttendanceCategory(**values)
        return self._repo.add(row)

    def update(
        self, category_id: int, payload: CategoryUpdate
    ) -> AttendanceCategory:
        row = self._repo.get_by_id(category_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )
        values = _normalize({
            **{k: v for k, v in row.__dict__.items() if not k.startswith("_sa_")},
            **payload.model_dump(exclude_unset=True),
        })
        duplicate = self._repo.find_duplicate_excluding(
            category_id,
            values.get("CategoryName", ""),
            values.get("ShortName"),
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name or short name already exists",
            )
        for key, value in values.items():
            if hasattr(row, key):
                setattr(row, key, value)
        return self._repo.update(row)

    def delete(self, category_id: int) -> dict[str, bool]:
        row = self._repo.get_by_id(category_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )
        self._repo.delete(row)
        return {"deleted": True}
