"""Business logic for leave configuration (3-tier: Application tier)."""

from __future__ import annotations

from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import LeaveConfig
from app.repositories.leave_config_repository import LeaveConfigRepository
from app.schemas.leave_config import LeaveConfigCreate, LeaveConfigUpdate


class LeaveConfigService:
    def __init__(self, session: Session) -> None:
        self._repo = LeaveConfigRepository(session)

    def list_all(self) -> List[LeaveConfig]:
        return self._repo.list_all()

    def create(self, payload: LeaveConfigCreate) -> LeaveConfig:
        exists = self._repo.find_by_code(payload.Code)
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leave code already exists",
            )
        row = LeaveConfig(**payload.model_dump())
        return self._repo.add(row)

    def update(self, config_id: int, payload: LeaveConfigUpdate) -> LeaveConfig:
        row = self._repo.get_by_id(config_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave configuration not found",
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        return self._repo.update(row)

    def delete(self, config_id: int) -> dict[str, bool]:
        row = self._repo.get_by_id(config_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave configuration not found",
            )
        self._repo.delete(row)
        return {"deleted": True}
