"""Presentation tier: Employee API delegates to EmployeeService."""

from __future__ import annotations

import json
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.campus_scope import check_device_id, check_employee_id, deny_for_campus, user_org_id
from app.database import get_db
from app.schemas.employee import (
    EmployeeBiometricCreate,
    EmployeeChangeCodeRequest,
    EmployeeCreate,
    EmployeeMoveRequest,
    EmployeeOut,
    EmployeePhotoOut,
    EmployeePhotoUpsert,
    EmployeeUpdate,
    ImportInspectResult,
    ImportResult,
)
from app.services import employee_delete
from app.services.employee_import import EmployeeImportService
from app.services.employee_service import EmployeeService
from app.services.roster_service import current_shift_map

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Clean template headers (order matters) offered via the download link.
_TEMPLATE_HEADERS = [
    "Face ID", "Employee Code", "Employee Name", "Access Card No", "Department", "Designation",
    "Employee Type", "School", "Date of Birth", "Joining Date", "Organization", "Status",
]
_TEMPLATE_SAMPLE = [
    "1001", "EMP001", "Jane Doe", "1001", "Mathematics", "Assistant Professor",
    "Teaching", "School of Computer Science", "1990-05-21", "2018-06-01", "My Institute", "Active",
]


def _get_employee_service(db: Session = Depends(get_db)) -> EmployeeService:
    return EmployeeService(db)


def _parse_mapping(mapping: str) -> tuple[dict[str, int], int]:
    """Decode the mapping JSON sent as a multipart form field."""
    try:
        data = json.loads(mapping)
        header_row = int(data.get("header_row", 1))
        columns = {str(k): int(v) for k, v in (data.get("columns") or {}).items()}
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid column mapping.")
    return columns, header_row


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    service: EmployeeService = Depends(_get_employee_service),
    user=Depends(get_current_user),
):
    rows = service.list_all()
    org = user_org_id(service._session, user)
    if org is not None:   # campus login: only its institution's staff
        rows = [r for r in rows if r.OrganizationId == org]
    shifts = current_shift_map(service._session, [r.EmployeeCode for r in rows])
    out = []
    for r in rows:
        item = EmployeeOut.model_validate(r)
        s = shifts.get(r.EmployeeCode)
        if s:
            item.CurrentShiftId, item.CurrentShift = s["ShiftId"], s["ShiftName"]
        out.append(item)
    return out


@router.post("", response_model=EmployeeOut)
def create_employee(
    payload: EmployeeCreate,
    service: EmployeeService = Depends(_get_employee_service),
    user=Depends(get_current_user),
):
    org = user_org_id(service._session, user)
    if org is not None:
        payload.OrganizationId = org   # a campus login adds staff to its own institution only
    return service.create(payload)


class CodesIn(BaseModel):
    codes: list[str]


@router.get("/blocked-pins")
def list_blocked_pins(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Face IDs of deleted people; readers may still send them but no staff record is created."""
    deny_for_campus(db, user, "The blocked-ID list")
    return employee_delete.list_blocked(db)


@router.delete("/blocked-pins/{pin}")
def allow_pin_again(pin: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    deny_for_campus(db, user, "The blocked-ID list")
    removed = employee_delete.unblock_pin(db, pin)
    db.commit()
    return {"removed": removed}


@router.get("/student-duplicates")
def list_student_duplicates(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Staff records that are really students (same ID), for review before a bulk delete."""
    deny_for_campus(db, user, "Clean up student records")
    return employee_delete.student_duplicates(db)


@router.post("/student-duplicates/delete")
def delete_student_duplicates(payload: CodesIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    deny_for_campus(db, user, "Clean up student records")
    return employee_delete.delete_student_duplicates(db, payload.codes)


@router.get("/{employee_id}/delete-preview")
def employee_delete_preview(employee_id: int, service: EmployeeService = Depends(_get_employee_service), _user=Depends(get_current_user)):
    return employee_delete.delete_preview(service._session, service.get_by_id(employee_id))


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int,
    service: EmployeeService = Depends(_get_employee_service),
    _user=Depends(get_current_user),
):
    return service.get_by_id(employee_id)


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    service: EmployeeService = Depends(_get_employee_service),
    user=Depends(get_current_user),
):
    org = user_org_id(service._session, user)
    if org is not None:
        payload.OrganizationId = org   # a campus login cannot move staff to another institution
    return service.update(employee_id, payload)


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    remove_from_readers: bool = True,
    service: EmployeeService = Depends(_get_employee_service),
    _user=Depends(get_current_user),
):
    """Delete the person and everything attached (punches kept); by default also remove them from the readers."""
    return service.delete(employee_id, remove_from_readers=remove_from_readers)


@router.post("/{employee_id}/biometrics")
def add_biometric(
    employee_id: str,
    payload: EmployeeBiometricCreate,
    service: EmployeeService = Depends(_get_employee_service),
    _user=Depends(get_current_user),
):
    return service.add_biometric(employee_id, payload)


@router.get("/{employee_id}/photo", response_model=EmployeePhotoOut)
def get_employee_photo(
    employee_id: str,
    include_data: bool = True,
    service: EmployeeService = Depends(_get_employee_service),
    _user=Depends(get_current_user),
):
    return service.get_photo(employee_id, include_data=include_data)


@router.put("/{employee_id}/photo", response_model=EmployeePhotoOut)
def upsert_employee_photo(
    employee_id: str,
    payload: EmployeePhotoUpsert,
    service: EmployeeService = Depends(_get_employee_service),
    _user=Depends(get_current_user),
):
    return service.upsert_photo(employee_id, payload)


@router.get("/import/template")
def download_import_template(_user=Depends(get_current_user)):
    """A ready-to-fill .xlsx with clean headers and one example row."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append(_TEMPLATE_HEADERS)
    ws.append(_TEMPLATE_SAMPLE)
    buf = BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="employee_import_template.xlsx"'},
    )


@router.post("/import/inspect", response_model=ImportInspectResult)
async def inspect_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    deny_for_campus(db, user, "Import from Excel")   # an import can name any institution
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    return EmployeeImportService(db).inspect(data)


@router.post("/import/preview", response_model=ImportResult)
async def preview_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    deny_for_campus(db, user, "Import from Excel")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    columns, header_row = _parse_mapping(mapping)
    return EmployeeImportService(db).process(data, columns, header_row, commit=False)


@router.post("/import/commit", response_model=ImportResult)
async def commit_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    deny_for_campus(db, user, "Import from Excel")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    columns, header_row = _parse_mapping(mapping)
    return EmployeeImportService(db).process(data, columns, header_row, commit=True)


@router.post("/{employee_id}/change-code")
def change_employee_code(
    employee_id: int,
    payload: EmployeeChangeCodeRequest,
    service: EmployeeService = Depends(_get_employee_service),
    _user=Depends(get_current_user),
):
    return service.change_code(employee_id, payload.new_code)


@router.post("/move")
def move_employees(
    payload: EmployeeMoveRequest,
    service: EmployeeService = Depends(_get_employee_service),
    user=Depends(get_current_user),
):
    db = service._session
    org = user_org_id(db, user)
    if org is not None:
        for eid in payload.employee_ids:
            check_employee_id(db, user, eid)
        payload.OrganizationId = org   # department / school moves only, within the campus
    return service.move(payload)


@router.post("/transfer")
def transfer_to_devices(
    employee_ids: list[int],
    target_device_ids: list[int],
    service: EmployeeService = Depends(_get_employee_service),
    user=Depends(get_current_user),
):
    db = service._session
    for eid in employee_ids:
        check_employee_id(db, user, eid)
    for did in target_device_ids:
        check_device_id(db, user, did)
    return service.transfer_to_devices(employee_ids, target_device_ids)
