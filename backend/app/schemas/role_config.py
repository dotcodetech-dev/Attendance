"""Schemas for role permission configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoleConfigOut(BaseModel):
    """Full role config: one dict per role (admin, manager, employee) of permission key -> bool."""

    admin: dict[str, bool] = Field(default_factory=dict)
    manager: dict[str, bool] = Field(default_factory=dict)
    employee: dict[str, bool] = Field(default_factory=dict)


class RoleConfigUpdate(BaseModel):
    admin: dict[str, bool] = Field(default_factory=dict)
    manager: dict[str, bool] = Field(default_factory=dict)
    employee: dict[str, bool] = Field(default_factory=dict)
