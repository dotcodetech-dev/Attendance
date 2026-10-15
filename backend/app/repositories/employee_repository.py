"""Data access for Employee and related (EmployeeBio, EmployeePhoto)."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import Employee, EmployeeBio, EmployeePhoto
from app.repositories.base import BaseRepository


class EmployeeRepository(BaseRepository[Employee]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Employee)

    def list_all(self) -> List[Employee]:
        return (
            self._session.query(Employee)
            .order_by(Employee.EmployeeId.desc())
            .all()
        )

    def get_by_id(self, employee_id: int) -> Employee | None:
        return (
            self._session.query(Employee)
            .filter(Employee.EmployeeId == employee_id)
            .first()
        )

    def get_by_code(self, employee_code: str) -> Employee | None:
        return (
            self._session.query(Employee)
            .filter(Employee.EmployeeCode == employee_code)
            .first()
        )

    def resolve(self, employee_ref: str) -> Employee | None:
        if employee_ref.isdigit():
            emp = self.get_by_id(int(employee_ref))
            if emp:
                return emp
        return self.get_by_code(employee_ref)

    def add(self, entity: Employee) -> Employee:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: Employee) -> Employee:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: Employee) -> None:
        self._session.delete(entity)
        self._session.commit()

    # EmployeeBio
    def get_bios_by_code(self, employee_code: str) -> List[EmployeeBio]:
        return (
            self._session.query(EmployeeBio)
            .filter(EmployeeBio.EmployeeCode == employee_code)
            .all()
        )

    def add_bio(self, entity: EmployeeBio) -> EmployeeBio:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get_photo_by_code(self, employee_code: str) -> EmployeePhoto | None:
        return (
            self._session.query(EmployeePhoto)
            .filter(EmployeePhoto.EmployeeCode == employee_code)
            .order_by(EmployeePhoto.EmployeePhotoId.desc())
            .first()
        )

    def add_photo(self, entity: EmployeePhoto) -> EmployeePhoto:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity
