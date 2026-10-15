"""Data access for LeaveConfig."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import LeaveConfig
from app.repositories.base import BaseRepository


class LeaveConfigRepository(BaseRepository[LeaveConfig]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, LeaveConfig)

    def list_all(self) -> List[LeaveConfig]:
        return (
            self._session.query(LeaveConfig)
            .order_by(LeaveConfig.Code.asc())
            .all()
        )

    def list_active(self) -> List[LeaveConfig]:
        return (
            self._session.query(LeaveConfig)
            .filter(LeaveConfig.IsActive == "Y")
            .order_by(LeaveConfig.Code.asc())
            .all()
        )

    def find_by_code(self, code: str) -> LeaveConfig | None:
        return (
            self._session.query(LeaveConfig)
            .filter(LeaveConfig.Code == code)
            .first()
        )

    def get_by_id(self, leave_config_id: int) -> LeaveConfig | None:
        return (
            self._session.query(LeaveConfig)
            .filter(LeaveConfig.LeaveConfigId == leave_config_id)
            .first()
        )

    def add(self, entity: LeaveConfig) -> LeaveConfig:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: LeaveConfig) -> LeaveConfig:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: LeaveConfig) -> None:
        self._session.delete(entity)
        self._session.commit()
