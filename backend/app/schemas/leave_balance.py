from __future__ import annotations

from pydantic import BaseModel


class LeaveBalanceOut(BaseModel):
    LeaveConfigId: int
    Code: str
    Name: str
    MaxPerYear: int
    UsedDays: int
    AvailableDays: int
    IsPaid: str
    IsActive: str

