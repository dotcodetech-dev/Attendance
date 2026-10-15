from __future__ import annotations
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AttendanceLogOut(BaseModel):
    DeviceLogId: int
    DeviceId: int
    EmployeeCode: str
    LogDate: datetime
    VerificationType: Optional[str] = None
    Direction: Optional[str] = None
    HasPhoto: bool = False

    class Config:
        from_attributes = True
