from __future__ import annotations
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.campus_scope import check_device_id, check_transfer, user_org_id
from app.database import get_db
from app.models.entities import Device, DeviceCommand, DeviceEmployee, Employee, EmployeeBio
from app.schemas.command import DeviceCommandCreate, DeviceCommandOut, TransferRequest

router = APIRouter()


COMMAND_MAP = {
    "ClearLogs": "CLEAR LOG",
    "EnrollFace": "ENROLL FACE",
    "EnrollFingerprint": "ENROLL FP",
    "ResetTransactionStamp": "RESET TRANS",
    "ResetOperationStamp": "RESET OP",
    "Reboot": "REBOOT",
    "UnlockDoor": "OPENDOOR",
}


@router.get("", response_model=list[DeviceCommandOut])
def list_commands(db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(DeviceCommand)
    org = user_org_id(db, user)
    if org is not None:   # campus login: commands of its institution's readers only
        q = q.filter(DeviceCommand.DeviceId.in_(db.query(Device.DeviceId).filter(Device.OrganizationId == org)))
    return q.order_by(DeviceCommand.DeviceCommandId.desc()).all()


@router.post("", response_model=DeviceCommandOut)
def create_command(payload: DeviceCommandCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check_device_id(db, user, payload.DeviceId)
    command_text = COMMAND_MAP.get(payload.command, payload.command)
    if payload.payload:
        command_text = f"{command_text} {payload.payload}".strip()

    row = DeviceCommand(
        DeviceId=payload.DeviceId,
        Title=payload.title or payload.command,
        DeviceCommand=command_text,
        Status="Pending",
        Type=payload.type,
        CreationDate=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/transfer")
def transfer_biometric_users(payload: TransferRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check_transfer(db, user, payload)
    queued = 0
    for employee_id in payload.employee_ids:
        employee = db.query(Employee).filter(Employee.EmployeeId == employee_id).first()
        if not employee:
            continue
        # Transfer sends the user record plus the face template this server holds. A user
        # with no stored face gets only the user record - the reader is never asked to
        # enrol the face on its own screen.
        face = (db.query(EmployeeBio)
                .filter(EmployeeBio.EmployeeCode == employee.EmployeeCode, EmployeeBio.BioName == "FACE")
                .order_by(EmployeeBio.EmployeeBioId.desc()).first())
        for device_id in payload.target_device_ids:
            db.add(
                DeviceEmployee(
                    DeviceId=device_id,
                    EmployeeId=employee.EmployeeId,
                    Command="Sync",
                    Status="Pending",
                )
            )
            db.add(
                DeviceCommand(
                    DeviceId=device_id,
                    Title="Sync User",
                    DeviceCommand=f"SYNC USER {employee.EmployeeCode}",
                    Status="Pending",
                    Type="transfer",
                    CreationDate=datetime.utcnow(),
                )
            )
            queued += 1
            if face and face.Bio:
                db.add(
                    DeviceCommand(
                        DeviceId=device_id,
                        Title="Transfer Face",
                        DeviceCommand=f"ENROLL FACE {employee.EmployeeCode}",
                        DeviceCommandFace=face.Bio,
                        Status="Pending",
                        Type="transfer",
                        CreationDate=datetime.utcnow(),
                    )
                )
                queued += 1
    db.commit()
    return {"queued": queued}
