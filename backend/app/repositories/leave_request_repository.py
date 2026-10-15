"""Data access for LeaveRequest."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.entities import LeaveRequest
from app.repositories.base import BaseRepository


class LeaveRequestRepository(BaseRepository[LeaveRequest]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, LeaveRequest)

    def list_by_employee(
        self,
        employee_code: str,
        statuses: List[str] | None = None,
        from_date=None,
        to_date=None,
    ) -> List[LeaveRequest]:
        q = (
            self._session.query(LeaveRequest)
            .filter(LeaveRequest.EmployeeCode == employee_code)
            .order_by(LeaveRequest.FromDate.desc())
        )
        if statuses:
            q = q.filter(LeaveRequest.Status.in_(statuses))
        if from_date:
            q = q.filter(LeaveRequest.FromDate >= from_date)
        if to_date:
            q = q.filter(LeaveRequest.ToDate <= to_date)
        return q.all()

    def list_for_balance(
        self,
        employee_code: str,
        leave_config_id: int,
        year: int,
    ) -> List[LeaveRequest]:
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31, 23, 59, 59)
        return (
            self._session.query(LeaveRequest)
            .filter(LeaveRequest.EmployeeCode == employee_code)
            .filter(LeaveRequest.LeaveConfigId == leave_config_id)
            .filter(LeaveRequest.Status.in_(["Pending", "HodApproved", "Approved"]))
            .filter(LeaveRequest.FromDate <= end)
            .filter(LeaveRequest.ToDate >= start)
            .all()
        )

    def find_overlapping(
        self,
        employee_code: str,
        from_date,
        to_date,
    ) -> LeaveRequest | None:
        from sqlalchemy import and_
        return (
            self._session.query(LeaveRequest)
            .filter(LeaveRequest.EmployeeCode == employee_code)
            .filter(LeaveRequest.Status.in_(["Pending", "HodApproved", "Approved"]))
            .filter(
                and_(
                    LeaveRequest.FromDate <= to_date,
                    LeaveRequest.ToDate >= from_date,
                )
            )
            .first()
        )

    def get_by_id(self, leave_request_id: int) -> LeaveRequest | None:
        return (
            self._session.query(LeaveRequest)
            .filter(LeaveRequest.LeaveRequestId == leave_request_id)
            .first()
        )

    def add(self, entity: LeaveRequest) -> LeaveRequest:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: LeaveRequest) -> LeaveRequest:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: LeaveRequest) -> None:
        self._session.delete(entity)
        self._session.commit()
