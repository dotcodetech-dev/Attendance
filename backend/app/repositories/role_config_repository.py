"""Data access for RoleConfig."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import RoleConfig
from app.repositories.base import BaseRepository


class RoleConfigRepository(BaseRepository[RoleConfig]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, RoleConfig)

    def get_by_role(self, role_name: str) -> RoleConfig | None:
        return (
            self._session.query(RoleConfig)
            .filter(RoleConfig.RoleName == role_name)
            .first()
        )

    def get_all(self) -> dict[str, dict[str, bool]]:
        rows = self._session.query(RoleConfig).all()
        out: dict[str, dict[str, bool]] = {
            "admin": {},
            "manager": {},
            "employee": {},
        }
        for row in rows:
            name = row.RoleName.lower()
            if name in out and row.PermissionsJson:
                try:
                    out[name] = json.loads(row.PermissionsJson)
                except (json.JSONDecodeError, TypeError):
                    out[name] = {}
        return out

    def upsert(self, role_name: str, permissions: dict[str, bool]) -> None:
        row = self.get_by_role(role_name)
        payload = json.dumps(permissions)
        if row:
            row.PermissionsJson = payload
            self._session.commit()
        else:
            self._session.add(RoleConfig(RoleName=role_name, PermissionsJson=payload))
            self._session.commit()
