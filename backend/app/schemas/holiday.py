from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class HolidayBase(BaseModel):
    HolidayDate: date
    HolidayName: str = Field(..., min_length=1, max_length=200)
    Category: str = Field(
        default="Public",
        pattern=r"^(Public|WeeklyOff|Company)$",
        description="Type of holiday: Public, WeeklyOff, or Company",
    )
    IsActive: Optional[str] = Field(default="Y", pattern=r"^[YN]$")


class HolidayCreate(HolidayBase):
    pass


class HolidayUpdate(BaseModel):
    HolidayDate: Optional[date] = None
    HolidayName: Optional[str] = Field(default=None, min_length=1, max_length=200)
    Category: Optional[str] = Field(
        default=None,
        pattern=r"^(Public|WeeklyOff|Company)$",
    )
    IsActive: Optional[str] = Field(default=None, pattern=r"^[YN]$")


class HolidayOut(HolidayBase):
    HolidayId: int

    class Config:
        from_attributes = True

