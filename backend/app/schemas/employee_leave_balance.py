from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class EmployeeLeaveBalanceOut(BaseModel):
    EmployeeLeaveBalanceId: int
    EmployeeCode: str
    LeaveConfigId: int
    Code: str
    Name: str
    LeaveYear: int
    AllowedLeaves: float
    CarriedForward: float


class EmployeeLeaveBalanceSet(BaseModel):
    EmployeeCode: str
    LeaveConfigId: int
    LeaveYear: int
    AllowedLeaves: float
    CarriedForward: float = 0


class SeedResult(BaseModel):
    year: int
    employees: int
    rows_written: int
