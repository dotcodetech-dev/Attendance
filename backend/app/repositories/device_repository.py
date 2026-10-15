"""Data access for Device, DeviceCommand, DeviceEmployee, DeviceLog."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import Device, DeviceCommand, DeviceEmployee, DeviceLog
from app.repositories.base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Device)

    def list_all(self) -> List[Device]:
        return self._session.query(Device).order_by(Device.DeviceId.asc()).all()

    def get_by_id(self, device_id: int) -> Device | None:
        return (
            self._session.query(Device)
            .filter(Device.DeviceId == device_id)
            .first()
        )

    def add(self, entity: Device) -> Device:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: Device) -> Device:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: Device) -> None:
        self._session.delete(entity)
        self._session.commit()

    def add_command(self, entity: DeviceCommand) -> DeviceCommand:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def add_device_employee(self, entity: DeviceEmployee) -> DeviceEmployee:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get_device_employee(
        self, device_id: int, employee_id: int
    ) -> DeviceEmployee | None:
        return (
            self._session.query(DeviceEmployee)
            .filter(
                DeviceEmployee.DeviceId == device_id,
                DeviceEmployee.EmployeeId == employee_id,
            )
            .first()
        )
