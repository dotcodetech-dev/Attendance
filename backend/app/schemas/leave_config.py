from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LeaveConfigBase(BaseModel):
    Code: str = Field(..., min_length=1, max_length=50)
    Name: str = Field(..., min_length=1, max_length=200)
    MaxPerYear: Optional[int] = Field(default=None, ge=0, le=365)
    IsPaid: Optional[str] = Field(default="Y", pattern=r"^[YN]$")
    ConsiderWeeklyOff: Optional[str] = Field(default="N", pattern=r"^[YN]$")
    ConsiderHoliday: Optional[str] = Field(default="N", pattern=r"^[YN]$")
    CarryForwardLimit: Optional[int] = Field(default=0, ge=0, le=365)
    IsActive: Optional[str] = Field(default="Y", pattern=r"^[YN]$")


class LeaveConfigCreate(LeaveConfigBase):
    pass


class LeaveConfigUpdate(BaseModel):
    Code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    Name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    MaxPerYear: Optional[int] = Field(default=None, ge=0, le=365)
    IsPaid: Optional[str] = Field(default=None, pattern=r"^[YN]$")
    ConsiderWeeklyOff: Optional[str] = Field(default=None, pattern=r"^[YN]$")
    ConsiderHoliday: Optional[str] = Field(default=None, pattern=r"^[YN]$")
    CarryForwardLimit: Optional[int] = Field(default=None, ge=0, le=365)
    IsActive: Optional[str] = Field(default=None, pattern=r"^[YN]$")


class LeaveConfigOut(LeaveConfigBase):
    LeaveConfigId: int

    class Config:
        from_attributes = True

