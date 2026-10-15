from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


WEEKDAY_PATTERN = r"^(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)$"
YN_PATTERN = r"^[YN]$"
OT_FORMULA_PATTERN = r"^(Total Duration - Shift Hours|In Out Punch - Shift End Time|Early Coming \+ Late Going|OT Not Applicable)$"


class CategoryBase(BaseModel):
    CategoryName: str = Field(..., min_length=1, max_length=120)
    ShortName: Optional[str] = Field(default=None, max_length=30)
    OTFormula: Optional[str] = Field(default="Total Duration - Shift Hours", pattern=OT_FORMULA_PATTERN)
    MinOTMinutes: Optional[int] = Field(default=30, ge=0, le=1440)
    MaxOTMinutes: Optional[int] = Field(default=0, ge=0, le=1440)
    GraceLateComingMinutes: Optional[int] = Field(default=15, ge=0, le=240)
    GraceEarlyGoingMinutes: Optional[int] = Field(default=15, ge=0, le=240)
    WeeklyOff1Enabled: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    WeeklyOff1Weekday: Optional[str] = Field(default="Sunday", pattern=WEEKDAY_PATTERN)
    WeeklyOff2Enabled: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    WeeklyOff2Weekday: Optional[str] = Field(default="Saturday", pattern=WEEKDAY_PATTERN)
    WeeklyOff2Occurrence1: Optional[str] = Field(default="Y", pattern=YN_PATTERN)
    WeeklyOff2Occurrence2: Optional[str] = Field(default="Y", pattern=YN_PATTERN)
    WeeklyOff2Occurrence3: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    WeeklyOff2Occurrence4: Optional[str] = Field(default="Y", pattern=YN_PATTERN)
    WeeklyOff2Occurrence5: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    ConsiderEarlyComingPunch: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    ConsiderOnlyFirstLastPunch: Optional[str] = Field(default="Y", pattern=YN_PATTERN)
    ConsiderLateGoingPunch: Optional[str] = Field(default="Y", pattern=YN_PATTERN)
    DeductBreakHours: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    NeglectLastInPunch: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    HalfDayIfWorkDurationLessThanMinutes: Optional[int] = Field(default=240, ge=0, le=1440)
    AbsentIfWorkDurationLessThanMinutes: Optional[int] = Field(default=120, ge=0, le=1440)
    PartialDayCalculateHalfDayIfWorkDurationLessThanMinutes: Optional[int] = Field(default=0, ge=0, le=1440)
    PartialDayCalculateAbsentIfWorkDurationLessThanMinutes: Optional[int] = Field(default=0, ge=0, le=1440)
    MarkWeeklyOffHolidayAsAbsentPrefixAbsent: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    MarkWeeklyOffHolidayAsAbsentSuffixAbsent: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    MarkWeeklyOffHolidayAsAbsentBothSidesAbsent: Optional[str] = Field(default="N", pattern=YN_PATTERN)
    MarkHalfDayWhenLateForDays: Optional[int] = Field(default=0, ge=0, le=365)
    MarkHalfDayIfLateByMinutes: Optional[int] = Field(default=0, ge=0, le=1440)
    MarkHalfDayIfEarlyGoingByMinutes: Optional[int] = Field(default=0, ge=0, le=1440)
    IsActive: Optional[str] = Field(default="Y", pattern=YN_PATTERN)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    CategoryName: Optional[str] = Field(default=None, min_length=1, max_length=120)
    ShortName: Optional[str] = Field(default=None, max_length=30)
    OTFormula: Optional[str] = Field(default=None, pattern=OT_FORMULA_PATTERN)
    MinOTMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    MaxOTMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    GraceLateComingMinutes: Optional[int] = Field(default=None, ge=0, le=240)
    GraceEarlyGoingMinutes: Optional[int] = Field(default=None, ge=0, le=240)
    WeeklyOff1Enabled: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    WeeklyOff1Weekday: Optional[str] = Field(default=None, pattern=WEEKDAY_PATTERN)
    WeeklyOff2Enabled: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    WeeklyOff2Weekday: Optional[str] = Field(default=None, pattern=WEEKDAY_PATTERN)
    WeeklyOff2Occurrence1: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    WeeklyOff2Occurrence2: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    WeeklyOff2Occurrence3: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    WeeklyOff2Occurrence4: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    WeeklyOff2Occurrence5: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    ConsiderEarlyComingPunch: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    ConsiderOnlyFirstLastPunch: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    ConsiderLateGoingPunch: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    DeductBreakHours: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    NeglectLastInPunch: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    HalfDayIfWorkDurationLessThanMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    AbsentIfWorkDurationLessThanMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    PartialDayCalculateHalfDayIfWorkDurationLessThanMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    PartialDayCalculateAbsentIfWorkDurationLessThanMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    MarkWeeklyOffHolidayAsAbsentPrefixAbsent: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    MarkWeeklyOffHolidayAsAbsentSuffixAbsent: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    MarkWeeklyOffHolidayAsAbsentBothSidesAbsent: Optional[str] = Field(default=None, pattern=YN_PATTERN)
    MarkHalfDayWhenLateForDays: Optional[int] = Field(default=None, ge=0, le=365)
    MarkHalfDayIfLateByMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    MarkHalfDayIfEarlyGoingByMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    IsActive: Optional[str] = Field(default=None, pattern=YN_PATTERN)


class CategoryOut(CategoryBase):
    CategoryId: int

    class Config:
        from_attributes = True

