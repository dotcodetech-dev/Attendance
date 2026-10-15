"""Business logic for leave requests and balance (3-tier: Application tier)."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import EmployeeLeaveBalance, LeaveRequest, User
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.leave_config_repository import LeaveConfigRepository
from app.repositories.leave_request_repository import LeaveRequestRepository
from app.schemas.leave_request import LeaveRequestCreate
from app.services.leave_approval_service import (
    APPROVED, CANCELLED, REJECTED, RESERVING_STATUSES, initial_status, record as record_approval, role_kind,
)
from app.services.campus_scope import check_employee_code, is_custom_role, role_allows
from app.services.leave_days import count_leave_days


def _inclusive_days(from_date: datetime, to_date: datetime) -> int:
    return (to_date.date() - from_date.date()).days + 1


def _used_days_from_requests(session: Session, requests: List[LeaveRequest], year: int, config) -> int:
    """Days used in `year`. Weekly offs / holidays inside a leave are skipped unless the
    leave type counts them (same rule the attendance register applies)."""
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    total = 0
    for row in requests:
        total += count_leave_days(
            session, row.EmployeeCode, config, row.FromDate.date(), row.ToDate.date(),
            clip_from=start, clip_to=end,
        ).counted
    return total


def _may_enter_leave(db: Session, user: User) -> bool:
    """Leave Entry is for an Admin, or a custom role (User Roles) with its Leave Entry switch on - a campus role
    only for its own institution's staff (checked by the caller)."""
    if role_kind(user) == "admin":
        return True
    return is_custom_role(db, user) and role_allows(db, user, "leave_entry")


def _unlimited(config) -> bool:
    """A leave type with 0 days per year has no yearly limit (OD, LOP ...), as the Leave Types page says."""
    return not int(config.MaxPerYear or 0)


class LeaveRequestService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = LeaveRequestRepository(session)
        self._config_repo = LeaveConfigRepository(session)
        self._employee_repo = EmployeeRepository(session)

    def _entitlement(self, employee_code: str, leave_config_id: int, year: int, default_max: int) -> int:
        """Per-employee entitlement (AllowedLeaves + CarriedForward) if a balance row
        exists for the employee/type/year, else the leave type's default MaxPerYear."""
        row = (
            self._session.query(EmployeeLeaveBalance)
            .filter(EmployeeLeaveBalance.EmployeeCode == employee_code)
            .filter(EmployeeLeaveBalance.LeaveConfigId == leave_config_id)
            .filter(EmployeeLeaveBalance.LeaveYear == year)
            .first()
        )
        if row is not None:
            return int(round((row.AllowedLeaves or 0) + (row.CarriedForward or 0)))
        return default_max

    def get_balance(
        self,
        employee_code: str,
        year: Optional[int] = None,
    ) -> List[dict]:
        year = year or datetime.utcnow().year
        configs = self._config_repo.list_active()
        balances = []
        for config in configs:
            entitlement = self._entitlement(
                employee_code, config.LeaveConfigId, year, int(config.MaxPerYear or 0)
            )
            rows = self._repo.list_for_balance(
                employee_code,
                config.LeaveConfigId,
                year,
            )
            used_days = _used_days_from_requests(self._session, rows, year, config)
            balances.append({
                "LeaveConfigId": config.LeaveConfigId,
                "Code": config.Code,
                "Name": config.Name,
                "MaxPerYear": entitlement,
                "UsedDays": used_days,
                "AvailableDays": max(entitlement - used_days, 0),
                "IsPaid": config.IsPaid or "Y",
                "IsActive": config.IsActive or "Y",
                "Unlimited": _unlimited(config),
            })
        return balances

    def preview_days(self, employee_code: str, leave_config_id: int, from_date: date, to_date: date) -> dict:
        """What a leave over these dates would deduct (for the apply form)."""
        config = self._config_repo.get_by_id(leave_config_id)
        result = count_leave_days(self._session, employee_code, config, from_date, to_date)
        return {
            "days": result.counted,
            "calendar_days": result.calendar_days,
            "skipped_weekly_off": result.skipped_weekly_off,
            "skipped_holidays": result.skipped_holidays,
        }

    def list_my(
        self,
        employee_code: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[LeaveRequest]:
        return self._repo.list_by_employee(
            employee_code,
            from_date=from_date,
            to_date=to_date,
        )

    def _validate(self, payload: LeaveRequestCreate) -> None:
        """Checks shared by an employee's application and an admin's direct entry: known employee, active
        type, sane dates, at least one counted day, enough balance (unless unlimited), no overlapping leave."""
        employee = self._employee_repo.get_by_code(payload.EmployeeCode)
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee code not found. Use EmployeeCode, not EmployeeId.",
            )
        config = self._config_repo.get_by_id(payload.LeaveConfigId)
        if not config or (config.IsActive or "Y") != "Y":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive leave type",
            )
        if payload.ToDate < payload.FromDate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="To date must be greater than or equal to from date",
            )
        requested = count_leave_days(
            self._session, payload.EmployeeCode, config, payload.FromDate.date(), payload.ToDate.date(),
        )
        requested_days = requested.counted
        if requested_days == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Those dates are all weekly offs or holidays, which this leave type does not count.",
            )
        if not _unlimited(config):
            used_rows = self._repo.list_for_balance(
                payload.EmployeeCode,
                payload.LeaveConfigId,
                payload.FromDate.year,
            )
            used_days = _used_days_from_requests(self._session, used_rows, payload.FromDate.year, config)
            entitlement = self._entitlement(
                payload.EmployeeCode, config.LeaveConfigId, payload.FromDate.year, int(config.MaxPerYear or 0)
            )
            available_days = max(entitlement - used_days, 0)
            if requested_days > available_days:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient leave balance. Available days: {available_days}",
                )
        overlap = self._repo.find_overlapping(
            payload.EmployeeCode,
            payload.FromDate,
            payload.ToDate,
        )
        if overlap:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A leave request already exists for the selected date range",
            )

    def apply_leave(self, payload: LeaveRequestCreate) -> LeaveRequest:
        self._validate(payload)
        first_status, skipped_because = initial_status(self._session, payload.EmployeeCode)
        row = LeaveRequest(
            EmployeeCode=payload.EmployeeCode,
            LeaveConfigId=payload.LeaveConfigId,
            FromDate=payload.FromDate,
            ToDate=payload.ToDate,
            Reason=payload.Reason,
            Status=first_status,
        )
        row = self._repo.add(row)
        if skipped_because:
            record_approval(self._session, row.LeaveRequestId, 1, "Skipped", "system", "System", skipped_because)
            self._session.commit()
        return row

    def admin_entry(self, payload: LeaveRequestCreate, user: User) -> LeaveRequest:
        """Leave entered by an admin: same checks as an application, but saved straight as Approved
        (no HOD / Principal step) and the attendance of those days is recalculated at once."""
        if not _may_enter_leave(self._session, user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can enter leave directly.")
        self._validate(payload)
        row = self._repo.add(LeaveRequest(
            EmployeeCode=payload.EmployeeCode,
            LeaveConfigId=payload.LeaveConfigId,
            FromDate=payload.FromDate,
            ToDate=payload.ToDate,
            Reason=payload.Reason,
            Status=APPROVED,
        ))
        record_approval(self._session, row.LeaveRequestId, 2, APPROVED, user.LoginName, "Admin",
                        "Entered by admin; no approval needed")
        self._session.commit()
        self._recalc(row)
        return row

    def admin_cancel(self, leave_request_id: int, user: User) -> LeaveRequest:
        """Undo a leave (e.g. one entered by mistake): marked Cancelled, kept for the record, the balance is
        given back and those days are recalculated."""
        if not _may_enter_leave(self._session, user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can cancel a leave.")
        row = self._session.get(LeaveRequest, leave_request_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave not found")
        check_employee_code(self._session, user, row.EmployeeCode)   # campus login: its own staff only
        if row.Status in (REJECTED, CANCELLED):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This leave is already {row.Status.lower()}.")
        row.Status = CANCELLED
        record_approval(self._session, row.LeaveRequestId, 2, CANCELLED, user.LoginName, "Admin", "Cancelled by admin")
        self._session.commit()
        self._recalc(row)
        return row

    def _recalc(self, row: LeaveRequest) -> None:
        from app.services.attendance_processing import process_range
        try:
            process_range(self._session, row.FromDate.date(), row.ToDate.date(), row.EmployeeCode)
        except Exception:  # noqa: BLE001 - the leave itself is saved; the nightly recalc catches up
            self._session.rollback()
