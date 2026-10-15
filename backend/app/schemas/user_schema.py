"""Schemas for portal user creation."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    login_name: str = Field(..., min_length=1, max_length=250)
    password: str = Field(..., min_length=1)
    role_name: Optional[str] = Field(default="Employee", max_length=255)
    employee_code: Optional[str] = Field(default=None, max_length=250)


class UserLink(BaseModel):
    login_name: str
    employee_code: Optional[str] = None
    role_name: Optional[str] = None


class UserOut(BaseModel):
    UserId: int
    LoginName: str
    RoleName: Optional[str] = None
    EmployeeCode: Optional[str] = None

    class Config:
        from_attributes = True


class ResetPasswordRequest(BaseModel):
    login_name: str
    new_password: str
