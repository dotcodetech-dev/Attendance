"""Business logic for manual entries / OD (3-tier: Application tier)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import ManualEntry
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.manual_entry_repository import ManualEntryRepository
from app.schemas.manual_entry import ManualEntryCreate, ManualEntryUpdate


class ManualEntryService:
    def __init__(self, session: Session) -> None:
        self._repo = ManualEntryRepository(session)
        self._employee_repo = EmployeeRepository(session)

    def list_my(
        self,
        employee_code: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[ManualEntry]:
        return self._repo.list_by_employee(
            employee_code,
            from_date=from_date,
            to_date=to_date,
        )

    def apply(self, payload: ManualEntryCreate) -> ManualEntry:
        employee = self._employee_repo.get_by_code(payload.EmployeeCode)
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee code not found. Use EmployeeCode, not EmployeeId.",
            )
        row = ManualEntry(
            EmployeeCode=payload.EmployeeCode,
            LogDate=payload.LogDate,
            EntryType=payload.EntryType,
            InTime=payload.InTime,
            OutTime=payload.OutTime,
            Reason=payload.Reason,
        )
        return self._repo.add(row)

    def update(
        self, manual_entry_id: int, payload: ManualEntryUpdate
    ) -> ManualEntry:
        row = self._repo.get_by_id(manual_entry_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manual entry not found",
            )
        update_values = payload.model_dump(exclude_unset=True)
        if update_values.get("EmployeeCode"):
            emp = self._employee_repo.get_by_code(update_values["EmployeeCode"])
            if not emp:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Employee code not found. Use EmployeeCode, not EmployeeId.",
                )
        for field, value in update_values.items():
            setattr(row, field, value)
        return self._repo.update(row)

    def delete(self, manual_entry_id: int) -> dict[str, bool]:
        row = self._repo.get_by_id(manual_entry_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Manual entry not found",
            )
        self._repo.delete(row)
        return {"deleted": True}
