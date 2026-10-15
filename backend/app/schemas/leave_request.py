from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LeaveRequestBase(BaseModel):
    EmployeeCode: str = Field(..., min_length=1, max_length=250)
    LeaveConfigId: int
    FromDate: datetime
    ToDate: datetime
    Reason: Optional[str] = Field(default=None, max_length=500)


class LeaveRequestCreate(LeaveRequestBase):
    pass


class LeaveRequestOut(LeaveRequestBase):
    LeaveRequestId: int
    Status: str
    AppliedAt: datetime

    class Config:
        from_attributes = True

