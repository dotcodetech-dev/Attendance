"""Business logic for role permission configuration (3-tier: Application tier)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.role_config_repository import RoleConfigRepository
from app.schemas.role_config import RoleConfigOut, RoleConfigUpdate


class RoleConfigService:
    def __init__(self, session: Session) -> None:
        self._repo = RoleConfigRepository(session)

    def get_config(self) -> RoleConfigOut:
        data = self._repo.get_all()
        return RoleConfigOut(
            admin=data.get("admin", {}),
            manager=data.get("manager", {}),
            employee=data.get("employee", {}),
        )

    def update_config(self, payload: RoleConfigUpdate) -> RoleConfigOut:
        self._repo.upsert("admin", payload.admin)
        self._repo.upsert("manager", payload.manager)
        self._repo.upsert("employee", payload.employee)
        return self.get_config()
