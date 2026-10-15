from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RosterBase(BaseModel):
    EmployeeCode: str = Field(..., min_length=1, max_length=250)
    ShiftId: int
    FromDate: datetime
    ToDate: Optional[datetime] = None


class RosterCreate(RosterBase):
    pass


class RosterUpdate(BaseModel):
    EmployeeCode: Optional[str] = Field(default=None, min_length=1, max_length=250)
    ShiftId: Optional[int] = None
    FromDate: Optional[datetime] = None
    ToDate: Optional[datetime] = None


class RosterOut(RosterBase):
    ShiftRosterId: int

    class Config:
        from_attributes = True


class RosterAssign(BaseModel):
    """Assign one shift to many employees from a date (to an optional end date)."""

    EmployeeCodes: List[str] = Field(..., min_length=1)
    ShiftId: int
    FromDate: datetime
    ToDate: Optional[datetime] = None
