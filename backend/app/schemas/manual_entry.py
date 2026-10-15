from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ManualEntryBase(BaseModel):
    EmployeeCode: str = Field(..., min_length=1, max_length=250)
    LogDate: datetime
    EntryType: str = Field(default="Manual", pattern=r"^(Manual|OD)$")
    InTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    OutTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    Reason: Optional[str] = Field(default=None, max_length=500)


class ManualEntryCreate(ManualEntryBase):
    pass


class ManualEntryUpdate(BaseModel):
    EmployeeCode: Optional[str] = Field(default=None, min_length=1, max_length=250)
    LogDate: Optional[datetime] = None
    EntryType: Optional[str] = Field(default=None, pattern=r"^(Manual|OD)$")
    InTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    OutTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    Reason: Optional[str] = Field(default=None, max_length=500)


class ManualEntryOut(ManualEntryBase):
    ManualEntryId: int
    Status: str
    AppliedAt: datetime

    class Config:
        from_attributes = True

