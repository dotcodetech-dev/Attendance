"""Business logic for employees (3-tier: Application tier)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.entities import (
    DepartmentMaster,
    DeviceCommand,
    DeviceEmployee,
    Employee,
    EmployeeBio,
    EmployeePhoto,
    Organization,
    School,
)
from app.repositories.category_repository import CategoryRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.employee import (
    EmployeeBiometricCreate,
    EmployeeCreate,
    EmployeeMoveRequest,
    EmployeePhotoUpsert,
    EmployeeUpdate,
)


def _clean_photo_data(photo_data: str) -> str:
    value = (photo_data or "").strip()
    if value.startswith("data:"):
        marker = ";base64,"
        idx = value.find(marker)
        if idx >= 0:
            return value[idx + len(marker) :].strip()
    return value


class EmployeeService:
    def __init__(self, session: Session) -> None:
        self._repo = EmployeeRepository(session)
        self._category_repo = CategoryRepository(session)
        self._session = session

    def list_all(self):
        return self._repo.list_all()

    def get_by_id(self, employee_id: int) -> Employee:
        row = self._repo.get_by_id(employee_id)
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")
        return row

    def resolve(self, employee_ref: str) -> Employee | None:
        return self._repo.resolve(employee_ref)

    def _assert_rfid_unique(self, rfid: str | None, exclude_employee_id: int | None = None) -> None:
        """No two employees may share the same RFID card number. Blank and '0'
        mean 'no card', so any number of employees may have them."""
        val = (rfid or "").strip()
        if val in ("", "0"):
            return
        q = self._session.query(Employee).filter(Employee.EmployeeRFIDNumber == val)
        if exclude_employee_id is not None:
            q = q.filter(Employee.EmployeeId != exclude_employee_id)
        other = q.first()
        if other:
            raise HTTPException(
                status_code=400,
                detail=f"RFID card number {val} is already assigned to {other.EmployeeName} ({other.EmployeeCode}).",
            )

    def _assert_hr_code_unique(self, hr_code: str, exclude_employee_id: int | None = None) -> None:
        """The HR 'Employee Code' (StringCode) is what people see in lists and reports, so two
        employees must not share it. (EmployeeCode is the Face ID: the unique device/camera key.)"""
        q = self._session.query(Employee).filter(Employee.StringCode == hr_code)
        if exclude_employee_id is not None:
            q = q.filter(Employee.EmployeeId != exclude_employee_id)
        other = q.first()
        if other:
            raise HTTPException(
                status_code=400,
                detail=f"Employee code {hr_code} is already used by {other.EmployeeName} (Face ID {other.EmployeeCode}).",
            )

    def create(self, payload: EmployeeCreate) -> Employee:
        exists = self._repo.get_by_code(payload.EmployeeCode)
        if exists:
            raise HTTPException(status_code=400, detail="Face ID already exists")
        payload.StringCode = (payload.StringCode or "").strip() or payload.EmployeeCode  # blank HR code = Face ID
        self._assert_hr_code_unique(payload.StringCode)
        self._assert_rfid_unique(payload.EmployeeRFIDNumber)
        if payload.CategoryId is not None:
            cat = self._category_repo.get_by_id(payload.CategoryId)
            if not cat:
                raise HTTPException(status_code=400, detail="Category not found")
        payload.ShortNo = (payload.ShortNo or "").strip()[:20] or None   # blank short number = none
        from app.services.employee_delete import unblock_pin
        unblock_pin(self._session, payload.EmployeeCode)   # adding the person again lifts a block from an earlier delete
        row = Employee(**payload.model_dump())
        return self._repo.add(row)

    def update(self, employee_id: int, payload: EmployeeUpdate) -> Employee:
        row = self._repo.get_by_id(employee_id)
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")
        values = payload.model_dump(exclude_none=True)
        if "StringCode" in values:
            values["StringCode"] = values["StringCode"].strip() or row.EmployeeCode  # blank HR code = Face ID
            if values["StringCode"] != row.StringCode:
                self._assert_hr_code_unique(values["StringCode"], exclude_employee_id=employee_id)
        if "ShortNo" in values:
            values["ShortNo"] = values["ShortNo"].strip()[:20] or None   # clearing the box removes it
        if "EmployeeRFIDNumber" in values:
            self._assert_rfid_unique(values["EmployeeRFIDNumber"], exclude_employee_id=employee_id)
        if "CategoryId" in values and values["CategoryId"] is not None:
            cat = self._category_repo.get_by_id(values["CategoryId"])
            if not cat:
                raise HTTPException(status_code=400, detail="Category not found")
        for key, value in values.items():
            setattr(row, key, value)
        return self._repo.update(row)

    def change_code(self, employee_id: int, new_code: str) -> dict:
        """Re-point an employee's EmployeeCode everywhere it is stored (bio, photos,
        face embeddings, punches, attendance, leaves, manual entries, mess, portal
        login, rosters). Runs in one transaction, temporarily relaxing any physical
        FKs so the parent key and all children move together."""
        new = (new_code or "").strip()
        if not new:
            raise HTTPException(status_code=400, detail="Enter the new employee code.")
        if len(new) > 250:
            raise HTTPException(status_code=400, detail="Employee code is too long (max 250 characters).")
        emp = self._repo.get_by_id(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        old = emp.EmployeeCode
        if new == old:
            raise HTTPException(status_code=400, detail="The new code is the same as the current one.")
        if self._repo.get_by_code(new):
            raise HTTPException(status_code=400, detail=f"Employee code {new} is already in use.")

        conn = self._session
        # Discover, at run time, the physical FKs pointing at employees and every
        # table that actually carries an EmployeeCode column, so this adapts to any
        # deployment (some installs have no FKs at all).
        fks = conn.execute(text(
            "SELECT fk.name, OBJECT_SCHEMA_NAME(fk.parent_object_id), OBJECT_NAME(fk.parent_object_id) "
            "FROM sys.foreign_keys fk WHERE fk.referenced_object_id = OBJECT_ID('dbo.employees')"
        )).fetchall()
        child_tables = [r[0] for r in conn.execute(text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE COLUMN_NAME = 'EmployeeCode' AND TABLE_NAME <> 'employees'"
        )).fetchall()]

        params = {"new": new, "old": old, "id": employee_id}
        try:
            for name, sch, tbl in fks:
                conn.execute(text(f"ALTER TABLE [{sch}].[{tbl}] NOCHECK CONSTRAINT [{name}]"))
            # StringCode is the device string id; move it too when it mirrors the code.
            conn.execute(text(
                "UPDATE employees SET EmployeeCode = :new, "
                "StringCode = CASE WHEN StringCode = :old THEN :new ELSE StringCode END "
                "WHERE EmployeeId = :id"
            ), params)
            for tbl in child_tables:
                conn.execute(text(f"UPDATE [{tbl}] SET EmployeeCode = :new WHERE EmployeeCode = :old"), params)
            for name, sch, tbl in fks:
                conn.execute(text(f"ALTER TABLE [{sch}].[{tbl}] CHECK CONSTRAINT [{name}]"))
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return {"EmployeeId": employee_id, "old_code": old, "new_code": new, "tables_updated": len(child_tables) + 1}

    def delete(self, employee_id: int, remove_from_readers: bool = True) -> dict:
        """Remove the person with everything attached (punches kept), tell the readers, block the ID."""
        from app.services.employee_delete import delete_employee
        row = self._repo.get_by_id(employee_id)
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")
        return delete_employee(self._session, row, remove_from_readers=remove_from_readers)

    def add_biometric(
        self, employee_ref: str, payload: EmployeeBiometricCreate
    ) -> dict:
        employee = self._repo.resolve(employee_ref)
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        biometric_payload = payload.model_dump()
        if not biometric_payload.get("Bio"):
            biometric_payload["Bio"] = f"AUTO_{payload.BioName}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        if not biometric_payload.get("BioDescription"):
            biometric_payload["BioDescription"] = "Uploaded from dashboard"
        bio = EmployeeBio(EmployeeCode=employee.EmployeeCode, **biometric_payload)
        self._repo.add_bio(bio)
        return {"EmployeeBioId": bio.EmployeeBioId, "EmployeeCode": bio.EmployeeCode}

    def get_photo(self, employee_ref: str, include_data: bool = True):
        employee = self._repo.resolve(employee_ref)
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        row = self._repo.get_photo_by_code(employee.EmployeeCode)
        if not row:
            return {"EmployeeCode": employee.EmployeeCode, "HasPhoto": False}
        return {
            "EmployeeCode": employee.EmployeeCode,
            "HasPhoto": True,
            "PhotoMimeType": row.PhotoMimeType,
            "Source": row.Source,
            "DeviceId": row.DeviceId,
            "PhotoName": row.PhotoName,
            "UpdatedAt": row.UpdatedAt,
            "PhotoData": row.PhotoData if include_data else None,
        }

    def upsert_photo(
        self, employee_ref: str, payload: EmployeePhotoUpsert
    ) -> dict:
        employee = self._repo.resolve(employee_ref)
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        cleaned = _clean_photo_data(payload.PhotoData)
        if not cleaned:
            raise HTTPException(status_code=400, detail="PhotoData is required")
        row = self._repo.get_photo_by_code(employee.EmployeeCode)
        if not row:
            row = EmployeePhoto(
                EmployeeCode=employee.EmployeeCode,
                PhotoData=cleaned,
                PhotoMimeType=payload.PhotoMimeType,
                Source=payload.Source or "manual",
                PhotoName=payload.PhotoName or "PROFILE",
                DeviceId=payload.DeviceId,
                CreatedAt=datetime.utcnow(),
                UpdatedAt=datetime.utcnow(),
            )
            self._repo.add_photo(row)
        else:
            row.PhotoData = cleaned
            row.PhotoMimeType = payload.PhotoMimeType
            row.Source = payload.Source or row.Source or "manual"
            row.PhotoName = payload.PhotoName or row.PhotoName
            row.DeviceId = payload.DeviceId if payload.DeviceId is not None else row.DeviceId
            row.UpdatedAt = datetime.utcnow()
            self._session.commit()
            self._session.refresh(row)
        return {
            "EmployeeCode": employee.EmployeeCode,
            "HasPhoto": True,
            "PhotoMimeType": row.PhotoMimeType,
            "Source": row.Source,
            "DeviceId": row.DeviceId,
            "PhotoName": row.PhotoName,
            "UpdatedAt": row.UpdatedAt,
            "PhotoData": row.PhotoData,
        }

    def move(self, payload: EmployeeMoveRequest) -> dict[str, int]:
        """Bulk-reassign employees to a target Organization, Department and/or School."""
        if not payload.employee_ids:
            return {"moved": 0}
        org_id = payload.OrganizationId
        if org_id is not None:
            org = self._session.query(Organization).filter(Organization.OrganizationId == org_id).first()
            if not org:
                raise HTTPException(status_code=400, detail="Organization not found")
        dept = (payload.Department or "").strip() or None
        school_id = payload.SchoolId
        if school_id is not None and not self._session.query(School).filter(School.SchoolId == school_id).first():
            raise HTTPException(status_code=400, detail="School not found")
        if org_id is None and dept is None and school_id is None:
            raise HTTPException(status_code=400, detail="Pick a target organization, department or school")
        # Keep the department master in sync so it shows in dropdowns / reports.
        if dept and org_id is not None:
            exists = (
                self._session.query(DepartmentMaster)
                .filter(DepartmentMaster.OrganizationId == org_id)
                .filter(DepartmentMaster.DepartmentName == dept)
                .first()
            )
            if not exists:
                self._session.add(DepartmentMaster(OrganizationId=org_id, DepartmentName=dept, IsActive="Y"))
        moved = 0
        for employee_id in payload.employee_ids:
            emp = self._repo.get_by_id(employee_id)
            if not emp:
                continue
            if org_id is not None:
                emp.OrganizationId = org_id
            if dept is not None:
                emp.Department = dept
            if school_id is not None:
                emp.SchoolId = school_id
            moved += 1
        self._session.commit()
        return {"moved": moved}

    def transfer_to_devices(
        self, employee_ids: list[int], target_device_ids: list[int]
    ) -> dict[str, int]:
        created = 0
        for employee_id in employee_ids:
            employee = self._repo.get_by_id(employee_id)
            if not employee:
                continue
            for device_id in target_device_ids:
                link = DeviceEmployee(
                    DeviceId=device_id,
                    EmployeeId=employee.EmployeeId,
                    Command="Sync",
                    Status="Pending",
                )
                self._session.add(link)
                # User record first; then the face template if this server holds one.
                # Never an on-device enrolment: that is the reader's own Enroll screen.
                self._session.add(DeviceCommand(
                    DeviceId=device_id,
                    Title="Sync User",
                    DeviceCommand=f"SYNC USER {employee.EmployeeCode}",
                    Status="Pending",
                    Type="transfer",
                    CreationDate=datetime.utcnow(),
                ))
                created += 1
                face = (self._session.query(EmployeeBio)
                        .filter(EmployeeBio.EmployeeCode == employee.EmployeeCode, EmployeeBio.BioName == "FACE")
                        .order_by(EmployeeBio.EmployeeBioId.desc()).first())
                if face and face.Bio:
                    self._session.add(DeviceCommand(
                        DeviceId=device_id,
                        Title="Transfer Face",
                        DeviceCommand=f"ENROLL FACE {employee.EmployeeCode}",
                        DeviceCommandFace=face.Bio,
                        Status="Pending",
                        Type="transfer",
                        CreationDate=datetime.utcnow(),
                    ))
                    created += 1
        self._session.commit()
        return {"queued": created}
