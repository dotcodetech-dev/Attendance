from __future__ import annotations
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import Device, DeviceCommand, DeviceEmployee, DeviceLog, Employee, EmployeeBio, EmployeePhoto
from app.schemas.command import DeviceCommandCreate, DeviceCommandOut
from app.schemas.device import (
    DeviceEnrollRequest,
    DeviceEnrollResponse,
    DeviceEnrollStatusResponse,
    DeviceEmployeeImportRequest,
    DeviceEmployeeImportResponse,
    DeviceEmployeeSyncRequest,
    DeviceEmployeeSyncResponse,
    DeviceMachineUserPhotoPullResponse,
    DeviceMachineUserDeleteResponse,
    DeviceConnectResponse,
    DeviceConnectionTestRequest,
    DeviceConnectionTestResponse,
    DeviceUpdate,
    DeviceCreate,
    DeviceMachineUserOut,
    DeviceOut,
    DeviceUserOut,
    DeviceUpdate,
)
from app.services.attendance_ingest import fetch_and_store
from app.services.employee_delete import blocked_pins, not_a_staff_pin, student_codes
from app.services.bio_store import template_counts, upsert_template
from app.services.campus_scope import allowed_device_ids, devices_query, link_new_device, user_org_id
from app.services.push_channel import (
    PUSH_ONLINE_SECONDS, channel_for, is_ai_reader, is_push_online, push_delete_user, push_reader_status,
    last_polled_text, push_status_message, push_users, queue_commands, queue_photo_upload, queue_user_refresh, queued_note,
    reader_channel, sdk_reachable,
    send_names_to_reader,
)
from app.services.device_sdk import (
    check_enrollment_status,
    delete_device_user,
    read_device_user_photo,
    read_device_users,
    test_device_connection,
    trigger_device_enrollment,
)

router = APIRouter()


_VERIFY_MODE = {0: "PW", 1: "FP", 2: "PN", 3: "PW", 4: "CD", 15: "FA"}  # DeviceLog.VerificationType is 2 chars


@router.get("/comm-log")
def device_comm_log(
    serial: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Recent device HTTP activity (ping / handshake / poll / PUSH) — lets an
    admin watch whether a device is actually pushing attendance in real time."""
    from app.iclock.routes import get_recent_comm
    rows = get_recent_comm(sn=serial, limit=max(1, min(limit, 300)))
    if allowed_device_ids(db, user) is not None:   # campus login: only its own readers
        mine = {sn for (sn,) in devices_query(db, user, db.query(Device.SerialNumber))}
        rows = [r for r in rows if (r.get("sn") or r.get("SN") or r.get("serial")) in mine]
    return rows


@router.post("/{device_id}/fetch-attendance")
def fetch_device_attendance(
    device_id: int,
    port: int = 4370,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Manually pull attendance punches from a device over the SDK (TCP 4370) and
    store new ones in devicelogs. Use when the device is online but not pushing
    ATTLOG automatically. Deduplicates against existing logs.
    """
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if not row.DeviceIPAddress:
        raise HTTPException(status_code=400, detail="Device IP Address is missing")
    return fetch_and_store(db, row, port)
ONLINE_WINDOW_SECONDS = PUSH_ONLINE_SECONDS   # one window: the card's Online and the channel choice agree

COMMAND_MAP = {
    "ClearLogs": "CLEAR LOG",
    "EnrollFace": "ENROLL FACE",
    "EnrollFingerprint": "ENROLL FP",
    "ResetTransactionStamp": "RESET TRANS",
    "ResetOperationStamp": "RESET OP",
    "Reboot": "REBOOT",
    "UnlockDoor": "OPENDOOR",
}


def _device_status(last_ping: Optional[datetime]) -> str:
    if last_ping is None:
        return "Offline"
    age_seconds = (datetime.utcnow() - last_ping).total_seconds()
    return "Online" if age_seconds <= ONLINE_WINDOW_SECONDS else "Offline"


def _attach_status(device: Device) -> Device:
    setattr(device, "DeviceStatus", _device_status(device.LastPing))
    return device


def _clean_photo_data(photo_data: Optional[str]) -> str:
    value = (photo_data or "").strip()
    if value.startswith("data:"):
        marker = ";base64,"
        idx = value.find(marker)
        if idx >= 0:
            value = value[idx + len(marker) :]
    return value.strip()


def _codes_equal(left: Optional[str], right: Optional[str]) -> bool:
    a = str(left or "").strip()
    b = str(right or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    if a.isdigit() and b.isdigit():
        return int(a) == int(b)
    return False


def _map_device_role(role_raw: Optional[str]) -> str:
    value = str(role_raw or "").strip()
    if value in {"14", "3", "2", "1"}:
        return "Admin"
    return "Employee"


def _upsert_bio(
    db: Session,
    employee_code: str,
    bio_name: str,
    bio_payload: str,
    description: str,
) -> bool:
    payload = (bio_payload or "").strip()
    if not payload:
        return False
    upsert_template(db, employee_code, bio_name, payload, description)
    return True


def _with_template_counts(db: Session, users: list) -> list:
    """Add FaceCount / FingerCount / HasPhoto: what this server holds for each person (what readers have sent),
    and their HR Employee Code, so the Users panel can show and search it next to the Face ID."""
    codes = [u.EmployeeCode for u in users]
    counts, photos, face_photos = template_counts(db, codes)
    hr_codes: dict[str, str] = {}
    for i in range(0, len(codes), 1000):   # SQL Server parameter limit
        part = codes[i:i + 1000]
        hr_codes.update({c: s for c, s in db.query(Employee.EmployeeCode, Employee.StringCode)
                         .filter(Employee.EmployeeCode.in_(part))})
    for u in users:
        u.StringCode = hr_codes.get(u.EmployeeCode) or None
        c = counts.get(u.EmployeeCode, {})
        u.FaceCount = c.get("FACE", 0)
        u.FingerCount = c.get("FINGER", 0)
        u.HasPhoto = u.EmployeeCode in photos
        u.HasFacePhoto = u.EmployeeCode in face_photos
    return users


@router.get("", response_model=list[DeviceOut])
def list_devices(
    status: Optional[str] = None,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = devices_query(db, user)   # campus login: only its institution's readers
    if location_id is not None:
        query = query.filter(Device.LocationId == location_id)
    rows = query.order_by(Device.DeviceId.desc()).all()
    if status == "online":
        threshold = datetime.utcnow().timestamp() - 300
        rows = [d for d in rows if d.LastPing and d.LastPing.timestamp() >= threshold]
    elif status == "offline":
        threshold = datetime.utcnow().timestamp() - 300
        rows = [d for d in rows if (not d.LastPing) or d.LastPing.timestamp() < threshold]
    return [_attach_status(row) for row in rows]


@router.post("", response_model=DeviceOut)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    exists = db.query(Device).filter(Device.SerialNumber == payload.SerialNumber).first()
    if exists:
        raise HTTPException(status_code=400, detail="Serial number already exists")

    row = Device(**payload.model_dump())
    org = user_org_id(db, user)
    if org is not None:
        row.OrganizationId = org   # a campus login's readers always belong to its institution
    db.add(row)
    db.commit()
    db.refresh(row)
    link_new_device(db, user, row.DeviceId)
    return _attach_status(row)


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    org = user_org_id(db, user)
    if org is not None:
        row.OrganizationId = org   # a campus login cannot move a reader to another institution
    db.commit()
    db.refresh(row)
    return _attach_status(row)


@router.post("/test-connection", response_model=DeviceConnectionTestResponse)
def test_connection(
    payload: DeviceConnectionTestRequest,
    _user=Depends(get_current_user),
):
    result = test_device_connection(payload.DeviceIPAddress, payload.Port, comm_key=payload.CommKey)
    return DeviceConnectionTestResponse(**result)


@router.post("/{device_id}/connect", response_model=DeviceConnectResponse)
def connect_device(
    device_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if not row.DeviceIPAddress:
        raise HTTPException(status_code=400, detail="Device IP Address is missing")

    result = test_device_connection(row.DeviceIPAddress, 4370, comm_key=row.CommKey)
    if result.get("connected"):
        row.LastPing = datetime.utcnow()
        db.commit()
        db.refresh(row)
    elif is_push_online(row):
        # Remote reader: no SDK path, but it is talking to us over Cloud/ADMS push - that is "connected".
        result = {"connected": True, "error_code": None, "prog_id": "push", "message": push_status_message(row)}

    return DeviceConnectResponse(
        DeviceId=row.DeviceId,
        DeviceStatus=_device_status(row.LastPing),
        LastPing=row.LastPing,
        connected=bool(result.get("connected")),
        error_code=result.get("error_code"),
        message=result.get("message"),
        prog_id=result.get("prog_id"),
    )


@router.post("/{device_id}/enroll", response_model=DeviceEnrollResponse)
def enroll_on_device(
    device_id: int,
    payload: DeviceEnrollRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if not row.DeviceIPAddress:
        raise HTTPException(status_code=400, detail="Device IP Address is missing")

    employee_ref = payload.EmployeeRef.strip()
    if not employee_ref:
        raise HTTPException(status_code=400, detail="Employee ID or code is required")

    bio_type = payload.BioType.upper().strip()
    if bio_type not in {"FINGER", "FACE"}:
        raise HTTPException(status_code=400, detail="BioType must be FINGER or FACE")

    # Fast path: avoid expensive biometric scans before triggering enrollment popup.
    existing = False
    users_result = read_device_users(row.DeviceIPAddress, payload.Port, 5, False, comm_key=row.CommKey)
    if users_result.get("connected"):
        existing = any(_codes_equal(user.get("EmployeeCode"), employee_ref) for user in (users_result.get("users") or []))

    auto_update_mode = existing and not payload.AllowUpdate

    enroll_result = trigger_device_enrollment(
        row.DeviceIPAddress,
        employee_ref=employee_ref,
        bio_type=bio_type,
        port=payload.Port,
        timeout_seconds=8,
        comm_key=row.CommKey,
    )

    if enroll_result.get("connected"):
        row.LastPing = datetime.utcnow()
        if enroll_result.get("enrollment_started") and row.SerialNumber:
            enroll_command = f"ENROLL {'FACE' if bio_type == 'FACE' else 'FP'} {employee_ref}"
            db.add(
                DeviceCommand(
                    DeviceId=row.DeviceId,
                    Title=f"Enroll {bio_type.title()}",
                    DeviceCommand=enroll_command,
                    Status="Pending",
                    Type="enroll",
                    CreationDate=datetime.utcnow(),
                )
            )
        db.commit()
        db.refresh(row)

    return DeviceEnrollResponse(
        DeviceId=row.DeviceId,
        DeviceStatus=_device_status(row.LastPing),
        LastPing=row.LastPing,
        EmployeeRef=employee_ref,
        BioType=bio_type,
        already_exists=existing,
        connected=bool(enroll_result.get("connected")),
        enrollment_started=bool(enroll_result.get("enrollment_started")),
        error_code=enroll_result.get("error_code"),
        message=(
            "Employee exists on device; enrollment trigger sent."
            if enroll_result.get("enrollment_started") and auto_update_mode
            else enroll_result.get("message")
        ),
        prog_id=enroll_result.get("prog_id"),
        method_used=enroll_result.get("method_used"),
    )


@router.get("/{device_id}/enroll-status", response_model=DeviceEnrollStatusResponse)
def enrollment_status(
    device_id: int,
    employee_ref: str,
    bio_type: str = "FINGER",
    port: int = 4370,
    update_mode: bool = False,
    allow_fallback_user_presence: bool = False,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if not row.DeviceIPAddress:
        raise HTTPException(status_code=400, detail="Device IP Address is missing")

    employee_ref = employee_ref.strip()
    if not employee_ref:
        raise HTTPException(status_code=400, detail="Employee ID or code is required")

    bio_type = bio_type.upper().strip()
    if bio_type not in {"FINGER", "FACE"}:
        raise HTTPException(status_code=400, detail="bio_type must be FINGER or FACE")

    result = check_enrollment_status(
        row.DeviceIPAddress,
        employee_ref=employee_ref,
        bio_type=bio_type,
        port=port,
        timeout_seconds=6,
        comm_key=row.CommKey,
    )

    detected_by = "template" if result.get("completed") else None
    completed = bool(result.get("completed"))

    # Optional fallback: user presence can be used for older devices when explicitly enabled.
    # Keep disabled by default to avoid false success without biometric template capture.
    if not completed and allow_fallback_user_presence and not update_mode:
        users_result = read_device_users(row.DeviceIPAddress, port, comm_key=row.CommKey)
        if users_result.get("connected"):
            result["connected"] = True
            exists = any(
                str(user.get("EmployeeCode", "")).strip() == employee_ref
                for user in (users_result.get("users") or [])
            )
            if exists:
                completed = True
                detected_by = "user_presence"
                result["message"] = "Enrollment likely completed: user is present on device."

    if result.get("connected"):
        row.LastPing = datetime.utcnow()
        db.commit()
        db.refresh(row)

    return DeviceEnrollStatusResponse(
        DeviceId=row.DeviceId,
        EmployeeRef=employee_ref,
        BioType=bio_type,
        connected=bool(result.get("connected")),
        completed=completed,
        detected_by=detected_by,
        error_code=result.get("error_code"),
        message=result.get("message"),
        prog_id=result.get("prog_id"),
    )


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return _attach_status(row)


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    org = user_org_id(db, user)
    if org is not None:
        row.OrganizationId = org   # a campus login cannot move a reader to another institution
    db.commit()
    db.refresh(row)
    return _attach_status(row)


@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.get("/{device_id}/users", response_model=list[DeviceUserOut])
def get_device_users(device_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    device = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    rows = (
        db.query(DeviceEmployee, Employee)
        .join(Employee, DeviceEmployee.EmployeeId == Employee.EmployeeId)
        .filter(DeviceEmployee.DeviceId == device_id)
        .order_by(Employee.EmployeeName.asc())
        .all()
    )

    return [
        DeviceUserOut(
            EmployeeId=employee.EmployeeId,
            EmployeeCode=employee.EmployeeCode,
            EmployeeName=employee.EmployeeName,
            Role=device_employee.Role,
            Status=device_employee.Status,
            SyncDate=device_employee.SyncDate,
        )
        for device_employee, employee in rows
    ]


@router.get("/{device_id}/machine-users", response_model=list[DeviceMachineUserOut])
def get_machine_users(device_id: int, response: Response, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Users on the reader. LAN readers are read live over the SDK; readers that only
    reach us by Cloud/ADMS push (remote sites) are answered from what they pushed."""
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    t0 = time.perf_counter()
    # A reader that is polling this server is answered from what it has pushed (its user table and templates):
    # instant, and the only way to see an AI-face reader's faces (the SDK cannot read those). The SDK live read is
    # kept for readers that are not pushing. (Trying the SDK first cost 20-25 s on a reader that accepts TCP 4370
    # but refuses the SDK login, before falling back to the same push copy.) An AI reader is ALWAYS answered from
    # the push copy, even during a quiet spell: the SDK can only fail on it.
    channel = reader_channel(row)
    t_probe = time.perf_counter() - t0
    if channel == "sdk":
        result = read_device_users(row.DeviceIPAddress, 4370, comm_key=row.CommKey)
        if result.get("connected"):
            row.LastPing = datetime.utcnow()
            db.commit()
            return _with_template_counts(db, [
                DeviceMachineUserOut(
                    EmployeeCode=str(user.get("EmployeeCode", "")),
                    EmployeeName=user.get("EmployeeName"),
                    Role=str(user.get("Role")) if user.get("Role") is not None else None,
                    Enabled=user.get("Enabled"),
                    Source="sdk",
                )
                for user in (result.get("users") or [])
                if str(user.get("EmployeeCode", "")).strip()
            ])
        raise HTTPException(status_code=400, detail=result.get("message") or "Unable to read users from device")
    elif channel == "offline":
        raise HTTPException(status_code=400, detail=(
            f"Device is not reachable over the SDK ({row.DeviceIPAddress or 'no IP'}:4370) and has not polled this "
            f"server recently. Check that its Cloud Server / ADMS setting points at this server (port 80)."))

    t1 = time.perf_counter()
    users = [DeviceMachineUserOut(**u) for u in push_users(db, row)]
    t_users = time.perf_counter() - t1
    t2 = time.perf_counter()
    out = _with_template_counts(db, users)
    # Where the time goes (browser dev tools > Network > Timing > Server Timing), for slow-server diagnosis.
    response.headers["Server-Timing"] = (
        f"probe;dur={t_probe * 1000:.0f}, users;dur={t_users * 1000:.0f}, counts;dur={(time.perf_counter() - t2) * 1000:.0f}")
    return out


@router.post("/{device_id}/machine-users/refresh")
def refresh_machine_users(device_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Push-channel readers: ask the reader to re-send its users and templates.
    They arrive on its next polls (OPERLOG), usually within 10-60 seconds."""
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if reader_channel(row) != "push":
        raise HTTPException(status_code=400, detail="The reader is not polling this server right now.")
    n = queue_user_refresh(db, row)
    return {"queued": n, "polling": is_push_online(row),
            "message": f"Refresh queued; {queued_note(row)} Its users arrive over the next minute or two."}


@router.post("/{device_id}/machine-users/send-names")
def send_names(device_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Push-channel readers: send the server's employee names to the reader (shown on it at punch time)."""
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if reader_channel(row) != "push":
        raise HTTPException(status_code=400, detail="The reader is not polling this server right now.")
    r = send_names_to_reader(db, row)
    parts = [f"{r['queued']} name(s) queued; {queued_note(row)}"]
    if r["already_waiting"]:
        parts.append(f"{r['already_waiting']} already waiting to be sent.")
    if r["no_name"]:
        parts.append(f"{r['no_name']} have no name on the server yet (name = code) - set them on the Employees page.")
    if r["unknown_privilege"]:
        parts.append(f"{r['unknown_privilege']} skipped until their admin/user rights on this reader are known - "
                     f"press Refresh from device, wait for the reload, then Send names again.")
    return {**r, "message": " ".join(parts)}


@router.get("/{device_id}/reader-status")
def reader_status(device_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """For the Users panel: when the reader last polled and what the server holds for it (explains an empty list)."""
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return push_reader_status(db, row)


class DiagnosticsIn(BaseModel):
    pin: Optional[str] = None  # optional: also ask for this one person's face / fingerprint templates


@router.get("/{device_id}/adms-log")
def device_adms_log(device_id: int, limit: int = 200, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """What this push reader has sent to the server and what the server sent back (newest first):
    handshake parameters, commands with their exact text, acknowledgement codes and uploaded tables.
    Template and photo values are shortened."""
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    from app.services import adms_log
    return adms_log.recent(row.SerialNumber, limit)


@router.post("/{device_id}/diagnostics")
def device_diagnostics(
    device_id: int, payload: DiagnosticsIn, db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    """Ask a push reader to describe itself (INFO) and send its user table; with a user ID, also that
    person's templates in the newer table names. The replies land in the reader log."""
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if reader_channel(row) != "push":
        raise HTTPException(status_code=400, detail="The reader is not polling this server right now.")
    commands = ["INFO", "CHECK", "DATA QUERY tablename=user,fielddesc=*,filter=*"]
    pin = (payload.pin or "").strip()
    if pin:
        commands += [
            f"DATA QUERY tablename=templatev10,fielddesc=*,filter=Pin={pin}",
            f"DATA QUERY tablename=biodata,fielddesc=*,filter=Pin={pin}",
        ]
    n = queue_commands(db, row, commands, "Reader diagnostics")
    return {"queued": n, "message": f"{n} command(s) queued; replies appear in the reader log within 10-60 seconds."}


@router.post("/{device_id}/import-employees", response_model=DeviceEmployeeImportResponse)
def import_employees_from_device(
    device_id: int,
    payload: DeviceEmployeeImportRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if not row.DeviceIPAddress:
        raise HTTPException(status_code=400, detail="Device IP Address is missing")

    include_templates = bool(payload.include_face or payload.include_finger)
    result = read_device_users(
        row.DeviceIPAddress,
        payload.port,
        timeout_seconds=120 if include_templates else 45,
        include_biometrics=include_templates,
        comm_key=row.CommKey,
    )
    fallback_note = ""
    templates_available = include_templates
    if not result.get("connected"):
        raw_message = str(result.get("message") or "Unable to read users from device").strip()
        message_lower = raw_message.lower()
        sdk_error = raw_message if ("sdk" in message_lower or "timed out" in message_lower or "zkemkeeper" in message_lower) else f"SDK failed: {raw_message}"
        # Fallback mode: if deep template read is slow, import base user data first.
        if include_templates and "timed out" in message_lower:
            retry = read_device_users(
                row.DeviceIPAddress,
                payload.port,
                timeout_seconds=60,
                include_biometrics=False,
                comm_key=row.CommKey,
            )
            if retry.get("connected"):
                result = retry
                templates_available = False
                fallback_note = " Template import skipped due SDK timeout; core users imported."
            else:
                retry_msg = str(retry.get("message") or "Unable to read users from device").strip()
                raise HTTPException(status_code=400, detail=retry_msg if "sdk" in retry_msg.lower() or "timed out" in retry_msg.lower() else f"SDK failed: {retry_msg}")
        else:
            raise HTTPException(status_code=400, detail=sdk_error)

    imported = 0
    updated = 0
    biometric_upserts = 0
    photos_upserts = 0
    users = result.get("users") or []
    blocked, students = blocked_pins(db), student_codes(db)
    for user in users:
        employee_code = str(user.get("EmployeeCode", "")).strip()
        if not employee_code:
            continue
        if not_a_staff_pin(db, employee_code, blocked, students) and not db.query(Employee.EmployeeId).filter(Employee.EmployeeCode == employee_code).first():
            continue   # deleted here or a student: not imported as staff
        employee_name = str(user.get("EmployeeName") or employee_code).strip() or employee_code
        department = (str(user.get("Department")).strip() if user.get("Department") is not None else None) or None
        role = _map_device_role(user.get("Role"))
        rfid = (str(user.get("RFIDNumber")).strip() if user.get("RFIDNumber") is not None else None) or None

        employee = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
        if not employee:
            numeric_code = int(employee_code) if employee_code.isdigit() else int(datetime.utcnow().timestamp())
            employee = Employee(
                EmployeeName=employee_name,
                EmployeeCode=employee_code,
                StringCode=employee_code,
                NumericCode=numeric_code,
                EmployeeRFIDNumber=rfid,
                Role=role,
                Department=department,
            )
            db.add(employee)
            imported += 1
        else:
            employee.EmployeeName = employee_name
            if rfid:
                employee.EmployeeRFIDNumber = rfid
            if department:
                employee.Department = department
            employee.Role = role
            updated += 1

        if payload.include_face and templates_available:
            if _upsert_bio(
                db=db,
                employee_code=employee_code,
                bio_name="FACE",
                bio_payload=str(user.get("FaceTemplate") or "").strip(),
                description="Imported from device",
            ):
                biometric_upserts += 1
        if payload.include_finger and templates_available:
            if _upsert_bio(
                db=db,
                employee_code=employee_code,
                bio_name="FINGER",
                bio_payload=str(user.get("FingerTemplate") or "").strip(),
                description="Imported from device",
            ):
                biometric_upserts += 1
        if payload.include_card and rfid:
            pass
        if payload.include_photo:
            photo_result = read_device_user_photo(
                row.DeviceIPAddress,
                employee_ref=employee_code,
                port=payload.port,
                comm_key=row.CommKey,
            )
            photo_data = _clean_photo_data(photo_result.get("photo_data"))
            if photo_data:
                photo_row = (
                    db.query(EmployeePhoto)
                    .filter(EmployeePhoto.EmployeeCode == employee_code)
                    .order_by(EmployeePhoto.EmployeePhotoId.desc())
                    .first()
                )
                if not photo_row:
                    db.add(
                        EmployeePhoto(
                            EmployeeCode=employee_code,
                            DeviceId=row.DeviceId,
                            PhotoName="PROFILE",
                            PhotoMimeType=photo_result.get("photo_mime_type") or "image/jpeg",
                            PhotoData=photo_data,
                            Source="sdk_import",
                            CreatedAt=datetime.utcnow(),
                            UpdatedAt=datetime.utcnow(),
                        )
                    )
                else:
                    photo_row.PhotoData = photo_data
                    photo_row.PhotoMimeType = photo_result.get("photo_mime_type") or photo_row.PhotoMimeType or "image/jpeg"
                    photo_row.Source = "sdk_import"
                    photo_row.DeviceId = row.DeviceId
                    photo_row.UpdatedAt = datetime.utcnow()
                photos_upserts += 1

    row.LastPing = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return DeviceEmployeeImportResponse(
        DeviceId=row.DeviceId,
        imported=imported,
        updated=updated,
        biometric_upserts=biometric_upserts,
        photos_upserts=photos_upserts,
        total_device_users=len(users),
        message=f"Employee data imported from device into database.{fallback_note}",
    )


@router.post("/{device_id}/sync-employees", response_model=DeviceEmployeeSyncResponse)
def sync_employees_to_device(
    device_id: int,
    payload: DeviceEmployeeSyncRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    query = db.query(Employee)
    selected_codes = [code.strip() for code in payload.employee_codes if code and code.strip()]
    if selected_codes:
        query = query.filter(Employee.EmployeeCode.in_(selected_codes))
    employees = query.order_by(Employee.EmployeeId.asc()).all()
    if not employees:
        raise HTTPException(status_code=400, detail="No employees found to sync.")

    queued_commands = 0
    synced_users = 0
    for employee in employees:
        mapping = (
            db.query(DeviceEmployee)
            .filter(DeviceEmployee.DeviceId == device_id, DeviceEmployee.EmployeeId == employee.EmployeeId)
            .first()
        )
        if not mapping:
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
                Title="Sync Employee Profile",
                DeviceCommand=f"SYNC USER {employee.EmployeeCode} {employee.EmployeeName}",
                Status="Pending",
                Type="sync",
                CreationDate=datetime.utcnow(),
            )
        )
        queued_commands += 1

        bio_rows = (
            db.query(EmployeeBio).filter(EmployeeBio.EmployeeCode == employee.EmployeeCode)
            .order_by(EmployeeBio.FingerIndex.asc(), EmployeeBio.EmployeeBioId.asc()).all()  # first finger = lowest number
        )
        face_bio = next((item for item in bio_rows if (item.BioName or "").upper() == "FACE"), None)
        finger_bio = next((item for item in bio_rows if (item.BioName or "").upper() == "FINGER"), None)
        photo_row = (
            db.query(EmployeePhoto)
            .filter(EmployeePhoto.EmployeeCode == employee.EmployeeCode)
            .order_by(EmployeePhoto.EmployeePhotoId.desc())
            .first()
        )

        if payload.include_face and face_bio and face_bio.Bio:
            db.add(
                DeviceCommand(
                    DeviceId=device_id,
                    Title="Sync Face",
                    DeviceCommand=f"ENROLL FACE {employee.EmployeeCode}",
                    DeviceCommandFace=face_bio.Bio,
                    Status="Pending",
                    Type="sync",
                    CreationDate=datetime.utcnow(),
                )
            )
            queued_commands += 1

        if payload.include_finger and finger_bio and finger_bio.Bio:
            db.add(
                DeviceCommand(
                    DeviceId=device_id,
                    Title="Sync Finger",
                    DeviceCommand=f"ENROLL FP {employee.EmployeeCode} {finger_bio.Bio}",
                    Status="Pending",
                    Type="sync",
                    CreationDate=datetime.utcnow(),
                )
            )
            queued_commands += 1

        if payload.include_card and employee.EmployeeRFIDNumber:
            db.add(
                DeviceCommand(
                    DeviceId=device_id,
                    Title="Sync Card",
                    DeviceCommand=f"ENROLL CARD {employee.EmployeeCode} {employee.EmployeeRFIDNumber}",
                    Status="Pending",
                    Type="sync",
                    CreationDate=datetime.utcnow(),
                )
            )
            queued_commands += 1

        if payload.include_photo and photo_row and photo_row.PhotoData:
            db.add(
                DeviceCommand(
                    DeviceId=device_id,
                    Title="Sync Photo",
                    DeviceCommand=f"ENROLL PHOTO {employee.EmployeeCode}",
                    DeviceCommandFace=photo_row.PhotoData,
                    Status="Pending",
                    Type="sync",
                    CreationDate=datetime.utcnow(),
                )
            )
            queued_commands += 1

        synced_users += 1

    db.commit()
    return DeviceEmployeeSyncResponse(
        DeviceId=device_id,
        synced_users=synced_users,
        queued_commands=queued_commands,
        message="Employee data queued for device sync.",
    )


@router.post("/{device_id}/machine-users/{employee_code}/photo/pull", response_model=DeviceMachineUserPhotoPullResponse)
def pull_machine_user_photo(
    device_id: int,
    employee_code: str,
    port: int = 4370,
    allow_create_employee: bool = True,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if is_ai_reader(row):
        # The SDK cannot log in to an AI-face reader: it uploads its photos itself when asked (push protocol).
        code = employee_code.strip()
        have = db.query(EmployeePhoto.EmployeePhotoId).filter(EmployeePhoto.EmployeeCode == code).first() is not None
        queued = 0 if have else queue_photo_upload(db, row)
        return DeviceMachineUserPhotoPullResponse(
            DeviceId=device_id, EmployeeCode=code, connected=True, photo_found=have, stored=have, source="push",
            message=("Photo is on the server: press View photo." if have else
                     ("Asked the reader to upload its photos. " if queued else "The reader was already asked to upload its photos. ")
                     + f"It sends them when it next polls ({last_polled_text(row)}); press View photo in a minute."))
    if not row.DeviceIPAddress:
        raise HTTPException(status_code=400, detail="Device IP Address is missing")

    employee_code = employee_code.strip()
    if not employee_code:
        raise HTTPException(status_code=400, detail="Employee code is required")

    employee = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
    if not employee and not_a_staff_pin(db, employee_code):
        raise HTTPException(status_code=400, detail="This ID was deleted here or belongs to a student; no staff record is created for it.")
    if not employee and allow_create_employee:
        numeric_code = int(employee_code) if employee_code.isdigit() else int(datetime.utcnow().timestamp())
        employee = Employee(
            EmployeeName=employee_code,
            EmployeeCode=employee_code,
            StringCode=employee_code,
            NumericCode=numeric_code,
            Role="Employee",
        )
        db.add(employee)
        db.flush()
    if not employee and not allow_create_employee:
        raise HTTPException(status_code=404, detail="Employee not found for photo storage.")

    result = read_device_user_photo(
        row.DeviceIPAddress,
        employee_ref=employee_code,
        port=port,
        comm_key=row.CommKey,
    )
    photo_data = _clean_photo_data(result.get("photo_data"))
    source = "sdk_pull"
    message = result.get("message")

    if not photo_data:
        log_row = (
            db.query(DeviceLog)
            .filter(
                DeviceLog.DeviceId == row.DeviceId,
                DeviceLog.EmployeeCode == employee_code,
                DeviceLog.AttPhoto.isnot(None),
            )
            .order_by(DeviceLog.DeviceLogId.desc())
            .first()
        )
        if log_row and log_row.AttPhoto:
            photo_data = _clean_photo_data(log_row.AttPhoto)
            source = "attendance_log"
            message = "Photo pulled from latest attendance photo fallback."

    stored = False
    if photo_data:
        photo_row = (
            db.query(EmployeePhoto)
            .filter(EmployeePhoto.EmployeeCode == employee_code)
            .order_by(EmployeePhoto.EmployeePhotoId.desc())
            .first()
        )
        if not photo_row:
            photo_row = EmployeePhoto(
                EmployeeCode=employee_code,
                DeviceId=row.DeviceId,
                PhotoName="PROFILE",
                PhotoMimeType=result.get("photo_mime_type") or "image/jpeg",
                PhotoData=photo_data,
                Source=source,
                CreatedAt=datetime.utcnow(),
                UpdatedAt=datetime.utcnow(),
            )
            db.add(photo_row)
        else:
            photo_row.PhotoData = photo_data
            photo_row.PhotoMimeType = result.get("photo_mime_type") or photo_row.PhotoMimeType or "image/jpeg"
            photo_row.Source = source
            photo_row.DeviceId = row.DeviceId
            photo_row.UpdatedAt = datetime.utcnow()
        stored = True

    if result.get("connected"):
        row.LastPing = datetime.utcnow()

    db.commit()
    if result.get("connected"):
        db.refresh(row)

    attempts = [a for a in (result.get("attempts") or []) if isinstance(a, dict)]
    if not photo_data:
        base_message = message or "Photo not found on device."
        detail_parts = []
        attempt_summary = "; ".join(
            f"{a.get('method')}: {a.get('detail')}" for a in attempts if a.get("method")
        )
        if attempt_summary:
            detail_parts.append(f"SDK attempts — {attempt_summary}")
        if result.get("available_photo_methods"):
            detail_parts.append(f"SDK exposes: {result['available_photo_methods']}")
        detail_parts.append("No attendance-photo fallback found in device logs.")
        message = f"{base_message} [{' | '.join(detail_parts)}]"

    return DeviceMachineUserPhotoPullResponse(
        DeviceId=row.DeviceId,
        EmployeeCode=employee_code,
        connected=bool(result.get("connected")),
        photo_found=bool(photo_data),
        stored=stored,
        source=source if photo_data else None,
        photo_mime_type=(result.get("photo_mime_type") or "image/jpeg") if photo_data else None,
        error_code=result.get("error_code"),
        message=message or ("Photo synced successfully." if photo_data else "Photo not found on device."),
        prog_id=result.get("prog_id"),
        method_used=result.get("method_used") or None,
        attempts=attempts,
        available_photo_methods=result.get("available_photo_methods"),
    )


@router.delete("/{device_id}/machine-users/{employee_code}", response_model=DeviceMachineUserDeleteResponse)
def delete_machine_user(
    device_id: int,
    employee_code: str,
    port: int = 4370,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = db.query(Device).filter(Device.DeviceId == device_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    employee_code = employee_code.strip()
    if not employee_code:
        raise HTTPException(status_code=400, detail="Employee code is required")

    # A reader that is polling this server is deleted through the push channel - the same channel its Users
    # list is read from. (Deleting over the SDK only when port 4370 was unreachable sent AI-face readers, which
    # answer on 4370 but refuse the SDK login, down the SDK path: the delete failed and the user stayed.)
    if reader_channel(row, port) == "push":
        push_delete_user(db, row, employee_code)
        db.commit()
        return DeviceMachineUserDeleteResponse(
            DeviceId=row.DeviceId, EmployeeCode=employee_code, connected=True, deleted=True,
            message=f"Delete queued; {queued_note(row)}")

    if not row.DeviceIPAddress:
        raise HTTPException(status_code=400, detail="Device IP Address is missing")

    result = delete_device_user(row.DeviceIPAddress, employee_code, port, comm_key=row.CommKey)
    verify_result = read_device_users(row.DeviceIPAddress, port, comm_key=row.CommKey)
    if verify_result.get("connected"):
        still_exists = any(
            _codes_equal(user.get("EmployeeCode"), employee_code)
            for user in (verify_result.get("users") or [])
        )
        result["deleted"] = not still_exists
        if still_exists:
            result["message"] = "Delete request sent, but user still exists on device."
        elif not result.get("message"):
            result["message"] = "User deleted from device."
        result["connected"] = True

    if result.get("connected"):
        row.LastPing = datetime.utcnow()
        db.commit()
        db.refresh(row)

    return DeviceMachineUserDeleteResponse(
        DeviceId=row.DeviceId,
        EmployeeCode=employee_code,
        connected=bool(result.get("connected")),
        deleted=bool(result.get("deleted")),
        error_code=result.get("error_code"),
        message=result.get("message"),
        prog_id=result.get("prog_id"),
    )


@router.post("/{device_id}/commands", response_model=DeviceCommandOut)
def create_device_command(
    device_id: int,
    payload: DeviceCommandCreate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    if device_id != payload.DeviceId:
        raise HTTPException(status_code=400, detail="DeviceId in path and body must match")

    command_text = COMMAND_MAP.get(payload.command, payload.command)
    if payload.payload:
        command_text = f"{command_text} {payload.payload}".strip()

    row = DeviceCommand(
        DeviceId=device_id,
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
