from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ShiftBase(BaseModel):
  ShiftName: str = Field(..., min_length=1, max_length=100)
  ShortName: Optional[str] = Field(default=None, max_length=20)
  StartTime: str = Field(..., pattern=r"^\d{2}:\d{2}$")  # HH:MM
  EndTime: str = Field(..., pattern=r"^\d{2}:\d{2}$")  # HH:MM
  GraceInMinutes: Optional[int] = Field(default=0, ge=0, le=240)
  GraceOutMinutes: Optional[int] = Field(default=0, ge=0, le=240)
  Break1Enabled: Optional[str] = Field(default="N", pattern=r"^[YN]$")
  Break1StartTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  Break1EndTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  Break2Enabled: Optional[str] = Field(default="N", pattern=r"^[YN]$")
  Break2StartTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  Break2EndTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  IsFlexibleShift: Optional[str] = Field(default="N", pattern=r"^[YN]$")
  PunchBeginBeforeMinutes: Optional[int] = Field(default=60, ge=0, le=1440)
  PunchEndAfterMinutes: Optional[int] = Field(default=120, ge=0, le=1440)
  GraceTimeMinutes: Optional[int] = Field(default=10, ge=0, le=240)
  PartialDayEnabled: Optional[str] = Field(default="N", pattern=r"^[YN]$")
  PartialDayWeekday: Optional[str] = Field(
    default=None,
    pattern=r"^(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)$",
  )
  PartialDayStartTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  PartialDayEndTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  IsDefault: Optional[str] = Field(default="N", pattern=r"^[YN]$")
  IsActive: Optional[str] = Field(default="Y", pattern=r"^[YN]$")


class ShiftCreate(ShiftBase):
  pass


class ShiftUpdate(BaseModel):
  ShiftName: Optional[str] = Field(default=None, min_length=1, max_length=100)
  ShortName: Optional[str] = Field(default=None, max_length=20)
  StartTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  EndTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  GraceInMinutes: Optional[int] = Field(default=None, ge=0, le=240)
  GraceOutMinutes: Optional[int] = Field(default=None, ge=0, le=240)
  Break1Enabled: Optional[str] = Field(default=None, pattern=r"^[YN]$")
  Break1StartTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  Break1EndTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  Break2Enabled: Optional[str] = Field(default=None, pattern=r"^[YN]$")
  Break2StartTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  Break2EndTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  IsFlexibleShift: Optional[str] = Field(default=None, pattern=r"^[YN]$")
  PunchBeginBeforeMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
  PunchEndAfterMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
  GraceTimeMinutes: Optional[int] = Field(default=None, ge=0, le=240)
  PartialDayEnabled: Optional[str] = Field(default=None, pattern=r"^[YN]$")
  PartialDayWeekday: Optional[str] = Field(
    default=None,
    pattern=r"^(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)$",
  )
  PartialDayStartTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  PartialDayEndTime: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
  IsDefault: Optional[str] = Field(default=None, pattern=r"^[YN]$")
  IsActive: Optional[str] = Field(default=None, pattern=r"^[YN]$")


class ShiftOut(ShiftBase):
  ShiftId: int

  class Config:
    from_attributes = True

