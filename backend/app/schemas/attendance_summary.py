from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class AttendanceDayOut(BaseModel):
    AttendanceDate: date
    DayNumber: int
    DayLabel: str
    Status: str
    StatusLabel: str
    ShiftName: Optional[str] = None
    ShiftTime: Optional[str] = None
    FirstIn: Optional[str] = None
    LastOut: Optional[str] = None
    TotalLogs: int = 0
    ActualWorkMinutes: int = 0
    Remarks: Optional[str] = None


class AttendanceMonthSummaryOut(BaseModel):
    EmployeeCode: str
    EmployeeName: Optional[str] = None
    Department: Optional[str] = None
    CategoryName: Optional[str] = None
    Year: int
    Month: int
    MonthLabel: str
    PresentDays: int
    HalfDays: int
    AbsentDays: int
    LeaveDays: int
    OffDays: int
    days: list[AttendanceDayOut]


class RecalculateRequest(BaseModel):
    from_date: date
    to_date: date
    employee_code: Optional[str] = None


class RecalculateResult(BaseModel):
    employees: int
    days: int
    rows_written: int
    from_date: date
    to_date: date


class ProcessedAttendanceOut(BaseModel):
    EmployeeCode: str
    AttendanceDate: date
    Status: str
    StatusLabel: Optional[str] = None
    ShiftName: Optional[str] = None
    ShiftTime: Optional[str] = None
    FirstIn: Optional[str] = None
    LastOut: Optional[str] = None
    TotalLogs: int = 0
    ActualWorkMinutes: int = 0
    Remarks: Optional[str] = None
    ProcessedAt: Optional[str] = None

