from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import (
    Device, DeviceCommand, DeviceEmployee,
    Employee, EmployeeBio, EmployeePhoto, TransferJob,
)
from app.schemas.command import TransferJobOut, TransferRequest
from app.services.bio_store import FACE_PHOTO_NAME
from app.services.employee_delete import not_a_staff_pin
from app.services.device_sdk import push_operations_via_sdk, read_device_users
from app.services.push_channel import auto_sync_enabled, set_auto_sync
from pydantic import BaseModel

router = APIRouter()

MAX_RETRY = 3
SENT_TIMEOUT_MINUTES = 10   # reset "Sent" commands after this many minutes without ACK
STALL_TIMEOUT_MINUTES = 10  # fail the job if the device never fetches any command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phase_order(job: TransferJob) -> list[str]:
    """Return ordered list of phases this job needs to process."""
    phases: list[str] = []
    if job.SequentialBiometrics == "Y":
        if job.IncludeFace == "Y":
            phases.append("face")
        if job.IncludeFinger == "Y":
            phases.append("finger")
    else:
        # Non-sequential: face and finger queued as one "face" phase together
        if job.IncludeFace == "Y" or job.IncludeFinger == "Y":
            phases.append("face")
    if job.IncludeCard == "Y":
        phases.append("card")
    if job.IncludePhoto == "Y":
        phases.append("photo")
    return phases


def _next_phase(job: TransferJob, current: str) -> str | None:
    order = _phase_order(job)
    try:
        idx = order.index(current)
        return order[idx + 1] if idx + 1 < len(order) else None
    except ValueError:
        return None


def _face_photo_row(db: Session, code: str) -> EmployeePhoto | None:
    """The photo an AI-face reader enrolled this person from (OPERLOG BIOPHOTO)."""
    return (db.query(EmployeePhoto)
            .filter(EmployeePhoto.EmployeeCode == code, EmployeePhoto.PhotoName == FACE_PHOTO_NAME)
            .order_by(EmployeePhoto.EmployeePhotoId.desc()).first())


def _profile_photo_row(db: Session, code: str) -> EmployeePhoto | None:
    """The display picture (USERPIC / SDK / uploaded), never the reader's enrolment photo."""
    return (db.query(EmployeePhoto)
            .filter(EmployeePhoto.EmployeeCode == code,
                    (EmployeePhoto.PhotoName != FACE_PHOTO_NAME) | (EmployeePhoto.PhotoName.is_(None)))
            .order_by(EmployeePhoto.EmployeePhotoId.desc()).first())


def _accepts_face_photo(device: Device | None) -> bool:
    """AI-face readers build their own template from a BIOPHOTO. Unknown types are tried too (an old
    reader just rejects the command); cameras are never readers."""
    return device is not None and (device.DeviceType or "").strip().lower() != "camera"


def _templates_missing(db: Session, job: TransferJob, employee_codes: list[str]) -> dict[str, list[str]]:
    """Codes (in selection order) that have no FACE / no FINGER template stored on this server.
    A face counts as held when either a face template or an AI-face reader's enrolment photo
    (BIOPHOTO) is stored - eBioServer transfers AI faces as that photo. Transfer can only send
    what the server holds; a user without anything is skipped, never enrolled on the reader's screen."""
    held: dict[str, set[str]] = {}
    if employee_codes:
        for code, name in (
            db.query(EmployeeBio.EmployeeCode, EmployeeBio.BioName)
            .filter(EmployeeBio.EmployeeCode.in_(employee_codes), EmployeeBio.Bio.isnot(None))
            .distinct().all()
        ):
            held.setdefault(code, set()).add((name or "").upper())
        for (code,) in (
            db.query(EmployeePhoto.EmployeeCode)
            .filter(EmployeePhoto.EmployeeCode.in_(employee_codes), EmployeePhoto.PhotoName == FACE_PHOTO_NAME)
            .distinct().all()
        ):
            held.setdefault(code, set()).add("FACE")
    return {
        "face": [c for c in employee_codes if job.IncludeFace == "Y" and "FACE" not in held.get(c, set())],
        "finger": [c for c in employee_codes if job.IncludeFinger == "Y" and "FINGER" not in held.get(c, set())],
    }


def _queue_phase_commands(
    db: Session,
    job: TransferJob,
    phase: str,
    employee_codes: list[str],
    target_device_ids: list[int],
    source_device_id: int | None,
) -> dict[str, int]:
    """
    Queue DeviceCommand rows for *phase* for every employee × device combination.
    In non-sequential mode phase=="face" queues BOTH face and finger commands.
    A face / finger command is only queued when the server holds that template:
    with nothing to send, the reader would otherwise be told to enrol the person
    on its own screen (ENROLL_BIO), which is not a transfer.
    Returns {"total", "face", "finger", "face_skipped", "finger_skipped"} counts.
    """
    queued = 0
    face_queued = finger_queued = face_skipped = finger_skipped = 0
    now = datetime.utcnow()

    for code in employee_codes:
        employee = db.query(Employee).filter(Employee.EmployeeCode == code).first()
        if not employee:
            continue

        bio_rows = (
            db.query(EmployeeBio).filter(EmployeeBio.EmployeeCode == code)
            .order_by(EmployeeBio.FingerIndex.asc(), EmployeeBio.EmployeeBioId.asc()).all()  # first finger = lowest number
        )
        # The newest face: a person re-enrolled on an AI reader has a BIODATA face beside an old near-infrared one,
        # and the transfer must carry the one the reader uploaded last (the list is ordered for fingers, not faces).
        face_bio = max((r for r in bio_rows if (r.BioName or "").upper() == "FACE"), key=lambda r: r.EmployeeBioId, default=None)
        finger_bio = next((r for r in bio_rows if (r.BioName or "").upper() == "FINGER"), None)
        face_photo = _face_photo_row(db, code)
        photo_row = _profile_photo_row(db, code)

        for device_id in target_device_ids:
            if source_device_id and source_device_id == device_id:
                continue
            target = db.query(Device).filter(Device.DeviceId == device_id).first()

            # Ensure DeviceEmployee mapping exists
            if not db.query(DeviceEmployee).filter(
                DeviceEmployee.DeviceId == device_id,
                DeviceEmployee.EmployeeId == employee.EmployeeId,
            ).first():
                db.add(DeviceEmployee(
                    DeviceId=device_id,
                    EmployeeId=employee.EmployeeId,
                    Command="Sync",
                    Status="Pending",
                ))

            def _add(title: str, command: str, face_data: str | None = None, cmd_phase: str = phase) -> None:
                nonlocal queued
                db.add(DeviceCommand(
                    DeviceId=device_id,
                    Title=title,
                    DeviceCommand=command,
                    DeviceCommandFace=face_data,
                    Status="Pending",
                    Type="transfer",
                    CreationDate=now,
                    TransferJobId=job.TransferJobId,
                    Phase=cmd_phase,
                    RetryCount=0,
                ))
                queued += 1

            # On the job's first phase, sync the user record ahead of any
            # biometric data — devices reject data for an unknown PIN.
            phase_order = _phase_order(job)
            if phase_order and phase == phase_order[0]:
                _add("Sync User", f"SYNC USER {code}", None, phase)

            def _add_face() -> None:
                # Same order of preference as eTimeTrackLite for AI readers: the face template when
                # the server holds one; otherwise the photo the source reader enrolled from
                # (DATA UPDATE BIOPHOTO - the target reader builds its own template, exactly how
                # eBioServer transfers "AI Face"). Nothing stored -> skipped, never an on-screen enrol.
                nonlocal face_queued, face_skipped
                if face_bio and face_bio.Bio:
                    _add("Transfer Face", f"ENROLL FACE {code}", face_bio.Bio, "face")
                    face_queued += 1
                elif face_photo and face_photo.PhotoData and _accepts_face_photo(target):
                    _add("Transfer Face photo", f"ENROLL BIOPHOTO {code}", face_photo.PhotoData, "face")
                    face_queued += 1
                else:
                    face_skipped += 1

            def _add_fingers() -> None:
                # Every stored finger (one command per finger), not just the first.
                nonlocal finger_queued, finger_skipped
                fingers = [r for r in bio_rows if (r.BioName or "").upper() == "FINGER" and r.Bio]
                if not fingers:
                    finger_skipped += 1
                    return
                for row in fingers:
                    _add("Transfer Finger", f"ENROLL FP {code} {row.Bio}", None, "finger")
                    finger_queued += 1

            if phase == "face":
                if job.IncludeFace == "Y":
                    _add_face()
                # In non-sequential mode also queue finger here
                if job.SequentialBiometrics == "N" and job.IncludeFinger == "Y":
                    _add_fingers()

            elif phase == "finger":
                _add_fingers()

            elif phase == "card":
                if employee.EmployeeRFIDNumber:
                    _add("Transfer Card", f"ENROLL CARD {code} {employee.EmployeeRFIDNumber}")

            elif phase == "photo":
                if photo_row and photo_row.PhotoData:
                    _add("Transfer Photo", f"ENROLL PHOTO {code}", photo_row.PhotoData)
                    # No face of any kind stored, but a photo is: let an AI reader enrol the face
                    # from it (eTimeTrackLite "Upload Bio Photo"). The reader checks the photo
                    # quality itself and answers with an error code when it is unusable.
                    if (job.IncludeFace == "Y" and not (face_bio and face_bio.Bio) and face_photo is None
                            and _accepts_face_photo(target)):
                        _add("Transfer Face photo", f"ENROLL BIOPHOTO {code}", photo_row.PhotoData)

        db.flush()

    return {
        "total": queued, "face": face_queued, "finger": finger_queued,
        "face_skipped": face_skipped, "finger_skipped": finger_skipped,
    }


def _advance_job(job: TransferJob, db: Session) -> None:
    """
    Called on every status poll.
    1. Reset "Sent" commands that timed out  → back to Pending  (communication drop recovery)
    2. Auto-retry "Failed" commands under MAX_RETRY
    3. If current phase is fully done → queue next phase (or mark complete)
    """
    now = datetime.utcnow()
    job_id = job.TransferJobId

    # 0. Stall detection: if the device has never fetched a single command for
    # this job, retrying is pointless — the device isn't polling the server.
    if job.Status not in ("completed", "failed") and job.StartDate:
        job_cmds = db.query(DeviceCommand).filter(
            DeviceCommand.TransferJobId == job_id,
        ).all()
        never_fetched = bool(job_cmds) and all(c.SentDate is None for c in job_cmds)
        if never_fetched and now - job.StartDate > timedelta(minutes=STALL_TIMEOUT_MINUTES):
            job.Status = "failed"
            job.CompletionDate = now
            job.ErrorMessage = (
                "Target device never fetched any command from the server. "
                "Either configure the device to push to this server (Comm. > Cloud Server / "
                "ADMS = this server's address, port 80), or use 'Push via SDK' to send the data "
                "directly to the device over the LAN."
            )
            db.flush()
            return

    # 1. Communication-drop recovery: Sent but no ACK within timeout
    timed_out = db.query(DeviceCommand).filter(
        DeviceCommand.TransferJobId == job_id,
        DeviceCommand.Status == "Sent",
        DeviceCommand.SentDate <= now - timedelta(minutes=SENT_TIMEOUT_MINUTES),
    ).all()
    for cmd in timed_out:
        if (cmd.RetryCount or 0) >= MAX_RETRY:
            cmd.Status = "Failed"
        else:
            cmd.Status = "Pending"
            cmd.RetryCount = (cmd.RetryCount or 0) + 1

    # 2. Auto-retry failed commands (under MAX_RETRY threshold)
    auto_retry = db.query(DeviceCommand).filter(
        DeviceCommand.TransferJobId == job_id,
        DeviceCommand.Status == "Failed",
        DeviceCommand.RetryCount < MAX_RETRY,
    ).all()
    for cmd in auto_retry:
        cmd.Status = "Pending"
        cmd.RetryCount = (cmd.RetryCount or 0) + 1

    db.flush()

    # 3. Count commands for current phase
    current_phase = job.Phase
    if not current_phase or job.Status in ("completed", "failed"):
        return

    cmds = db.query(DeviceCommand).filter(
        DeviceCommand.TransferJobId == job_id,
        DeviceCommand.Phase == current_phase,
    ).all()

    if not cmds:
        return

    pending = sum(1 for c in cmds if c.Status == "Pending")
    sent    = sum(1 for c in cmds if c.Status == "Sent")

    # Update job progress counters (face / finger commands only, not the user-sync lines)
    def _count(title: str, status: str) -> int:
        return sum(1 for c in cmds if (c.Title or "") in (title, title + " photo") and c.Status == status)
    if current_phase == "face":
        job.FaceExecuted = _count("Transfer Face", "Executed")
        job.FaceFailed   = _count("Transfer Face", "Failed")
        if job.SequentialBiometrics == "N":
            job.FingerExecuted = _count("Transfer Finger", "Executed")
            job.FingerFailed   = _count("Transfer Finger", "Failed")
    elif current_phase == "finger":
        job.FingerExecuted = _count("Transfer Finger", "Executed")
        job.FingerFailed   = _count("Transfer Finger", "Failed")

    # Phase complete when nothing is pending or in-flight
    if pending == 0 and sent == 0:
        next_phase = _next_phase(job, current_phase)
        if next_phase:
            all_codes   = json.loads(job.EmployeeCodes or "[]")
            target_ids  = json.loads(job.TargetDeviceIds or "[]")
            counts = _queue_phase_commands(db, job, next_phase, all_codes, target_ids, job.SourceDeviceId)
            if next_phase == "finger":
                job.FingerQueued = counts["finger"]
            elif next_phase == "face":
                job.FaceQueued = counts["face"]
            job.Phase   = next_phase
            job.Status  = f"running_{next_phase}"
            db.flush()
        else:
            all_job_cmds = db.query(DeviceCommand).filter(
                DeviceCommand.TransferJobId == job_id,
            ).all()
            total_executed = sum(1 for c in all_job_cmds if c.Status == "Executed")
            total_failed = sum(1 for c in all_job_cmds if c.Status == "Failed")
            if total_executed == 0 and total_failed > 0:
                job.Status = "failed"
                job.ErrorMessage = (
                    "All commands failed or were never acknowledged by the device. "
                    "Check that the device is online and pushing to this server."
                )
            else:
                job.Status = "completed"
            job.CompletionDate = now


def _skipped_note(missing: dict[str, list[str]], source_device_id: int | None, db: Session) -> str | None:
    parts = []
    for kind, label in (("face", "face"), ("finger", "fingerprint")):
        codes = missing.get(kind) or []
        if codes:
            shown = ", ".join(codes[:8]) + (f" and {len(codes) - 8} more" if len(codes) > 8 else "")
            parts.append(f"{len(codes)} user(s) have no {label} template on this server and were skipped: {shown}")
    if not parts:
        return None
    src = db.query(Device).filter(Device.DeviceId == source_device_id).first() if source_device_id else None
    src_name = src.DeviceName if src else "the source reader"
    return (
        "; ".join(parts) + ". Transfer only sends what this server already holds (a face template or the "
        "photo the reader enrolled from); it never asks the target reader to enrol on its screen. Read them "
        f"from {src_name} first (Devices > Users > Refresh from reader, or enrol on that reader so it pushes "
        "them here), then run the transfer again. Including Photo lets an AI-face reader build the face "
        "from the person's profile photo."
    )


def _job_to_dict(job: TransferJob, db: Session) -> dict:
    cmds = db.query(DeviceCommand).filter(DeviceCommand.TransferJobId == job.TransferJobId).all()
    missing = _templates_missing(db, job, json.loads(job.EmployeeCodes or "[]"))
    return {
        "face_skipped":         len(missing["face"]),
        "finger_skipped":       len(missing["finger"]),
        "skipped_note":         _skipped_note(missing, job.SourceDeviceId, db),
        "job_id":               job.TransferJobId,
        "status":               job.Status,
        "phase":                job.Phase,
        "total_users":          job.TotalUsers,
        "batch_size":           job.BatchSize,
        "total_batches":        job.TotalBatches,
        "include_face":         job.IncludeFace == "Y",
        "include_finger":       job.IncludeFinger == "Y",
        "include_card":         job.IncludeCard == "Y",
        "include_photo":        job.IncludePhoto == "Y",
        "sequential_biometrics": job.SequentialBiometrics == "Y",
        "face_queued":          job.FaceQueued or 0,
        "face_executed":        job.FaceExecuted or 0,
        "face_failed":          job.FaceFailed or 0,
        "finger_queued":        job.FingerQueued or 0,
        "finger_executed":      job.FingerExecuted or 0,
        "finger_failed":        job.FingerFailed or 0,
        "total_commands":       len(cmds),
        "pending_commands":     sum(1 for c in cmds if c.Status == "Pending"),
        "sent_commands":        sum(1 for c in cmds if c.Status == "Sent"),
        "executed_commands":    sum(1 for c in cmds if c.Status == "Executed"),
        "failed_commands":      sum(1 for c in cmds if c.Status == "Failed"),
        "created_at":           job.CreationDate.isoformat() if job.CreationDate else None,
        "completed_at":         job.CompletionDate.isoformat() if job.CompletionDate else None,
        "error_message":        job.ErrorMessage,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/transfer")
def transfer_biometrics(
    payload: TransferRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Create a TransferJob and queue the first phase of biometric commands.
    When sequential_biometrics=True (default): face commands are queued first;
    finger commands are queued automatically once ALL face commands are executed.
    This prevents face + finger being sent to the device simultaneously.
    """
    if not payload.target_device_ids:
        raise HTTPException(400, "Please select at least one target device.")
    if not any([payload.include_face, payload.include_finger, payload.include_card, payload.include_photo]):
        raise HTTPException(400, "Please select at least one data type (Face/Finger/Card/Photo).")

    employee_codes = [c.strip() for c in payload.employee_codes if c and c.strip()]

    if payload.source_device_id and not employee_codes and not payload.employee_ids:
        source_device = db.query(Device).filter(Device.DeviceId == payload.source_device_id).first()
        if not source_device:
            raise HTTPException(404, "Source device not found.")
        if not source_device.DeviceIPAddress:
            raise HTTPException(400, "Source device IP address is missing.")
        users_result = read_device_users(source_device.DeviceIPAddress, 4370, comm_key=source_device.CommKey)
        if not users_result.get("connected"):
            raise HTTPException(400, users_result.get("message") or "Unable to read users from source device.")
        employee_codes = [
            str(u.get("EmployeeCode", "")).strip()
            for u in (users_result.get("users") or [])
            if str(u.get("EmployeeCode", "")).strip()
        ]

    employees: list[Employee] = []
    if payload.employee_ids:
        employees.extend(db.query(Employee).filter(Employee.EmployeeId.in_(payload.employee_ids)).all())
    if employee_codes:
        existing = {r.EmployeeCode: r for r in db.query(Employee).filter(Employee.EmployeeCode.in_(employee_codes)).all()}
        for code in employee_codes:
            row = existing.get(code)
            if row:
                employees.append(row)
            elif payload.allow_create_missing_employees and not not_a_staff_pin(db, code):
                numeric = int(code) if code.isdigit() else int(datetime.utcnow().timestamp())
                row = Employee(EmployeeName=code, EmployeeCode=code, StringCode=code, NumericCode=numeric, Role="Employee")
                db.add(row)
                db.flush()
                employees.append(row)

    unique = list({e.EmployeeId: e for e in employees}.values())
    if not unique:
        raise HTTPException(400, "No valid users selected for transfer.")

    all_codes   = [e.EmployeeCode for e in unique]
    batch_size  = max(1, min(payload.batch_size, 1000))
    total_batches = (len(all_codes) + batch_size - 1) // batch_size

    # Determine which phase to start with
    if payload.sequential_biometrics:
        first_phase = (
            "face"   if payload.include_face   else
            "finger" if payload.include_finger else
            "card"   if payload.include_card   else
            "photo"
        )
    else:
        first_phase = "face"   # non-sequential: face phase queues both face+finger

    job = TransferJob(
        Status=f"running_{first_phase}",
        Phase=first_phase,
        TotalUsers=len(all_codes),
        BatchSize=batch_size,
        TotalBatches=total_batches,
        FaceQueued=0, FaceExecuted=0, FaceFailed=0,
        FingerQueued=0, FingerExecuted=0, FingerFailed=0,
        IncludeFace="Y"  if payload.include_face   else "N",
        IncludeFinger="Y" if payload.include_finger else "N",
        IncludeCard="Y"  if payload.include_card   else "N",
        IncludePhoto="Y" if payload.include_photo  else "N",
        SequentialBiometrics="Y" if payload.sequential_biometrics else "N",
        EmployeeCodes=json.dumps(all_codes),
        TargetDeviceIds=json.dumps(payload.target_device_ids),
        SourceDeviceId=payload.source_device_id,
        CreationDate=datetime.utcnow(),
        StartDate=datetime.utcnow(),
    )
    # Refuse a transfer that has nothing to send: Transfer copies the templates this
    # server holds (what the readers pushed / the SDK read). With no face or finger
    # stored for any selected user and no card / photo to send either, the only thing
    # the old code could do was ask the target reader to enrol the person on its own
    # screen - which is enrolment, not transfer.
    missing = _templates_missing(db, job, all_codes)
    has_face = payload.include_face and len(missing["face"]) < len(all_codes)
    has_finger = payload.include_finger and len(missing["finger"]) < len(all_codes)
    has_card = payload.include_card and any(e.EmployeeRFIDNumber for e in unique)
    has_photo = payload.include_photo and db.query(EmployeePhoto.EmployeePhotoId).filter(
        EmployeePhoto.EmployeeCode.in_(all_codes)).first() is not None
    if not (has_face or has_finger or has_card or has_photo):
        db.rollback()
        wanted = ", ".join(t for t, on in (("face", payload.include_face), ("fingerprint", payload.include_finger),
                                           ("card", payload.include_card), ("photo", payload.include_photo)) if on)
        src = db.query(Device).filter(Device.DeviceId == payload.source_device_id).first() if payload.source_device_id else None
        raise HTTPException(400, (
            f"Nothing to transfer: this server holds no {wanted} data for the selected user(s). Transfer only "
            "sends templates already stored here; it never asks the target reader to enrol on its screen. "
            f"Read the templates from {src.DeviceName if src else 'the source reader'} first (Devices > Users > "
            "Refresh from reader, or enrol on that reader so it pushes them here), then run the transfer again."
        ))

    db.add(job)
    db.flush()

    counts = _queue_phase_commands(
        db, job, first_phase,
        all_codes, payload.target_device_ids, payload.source_device_id,
    )
    job.FaceQueued = counts["face"]
    job.FingerQueued = counts["finger"]

    db.commit()
    db.refresh(job)

    note = _skipped_note(missing, payload.source_device_id, db)
    message = (
        "Face data queued. Finger data will be queued automatically once face transfer completes."
        if payload.sequential_biometrics and payload.include_face and payload.include_finger
        else "Transfer job started."
    )
    return {
        "job_id":           job.TransferJobId,
        "status":           job.Status,
        "total_users":      job.TotalUsers,
        "total_batches":    job.TotalBatches,
        "queued_commands":  counts["total"],
        "face_skipped":     len(missing["face"]),
        "finger_skipped":   len(missing["finger"]),
        "skipped_note":     note,
        "message":          message + (f" {note}" if note else ""),
    }


class AutoSyncIn(BaseModel):
    enabled: bool


@router.get("/auto-sync")
def get_auto_sync(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Whether a template / face photo one reader uploads is queued automatically for every
    other reader that already holds that person (how eBioServer keeps its readers in step)."""
    return {"enabled": auto_sync_enabled(db)}


@router.put("/auto-sync")
def put_auto_sync(payload: AutoSyncIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    set_auto_sync(db, payload.enabled)
    db.commit()
    return {"enabled": payload.enabled}


def _command_to_sdk_op(cmd: DeviceCommand, db: Session) -> dict | None:
    """Translate a queued DeviceCommand into a zkemkeeper SDK write operation.
    Returns None when the command can't be delivered over the SDK channel."""
    raw = (cmd.DeviceCommand or "").strip()
    payload = (cmd.DeviceCommandFace or "").strip()
    parts = raw.split()
    upper = raw.upper()

    def _employee(code: str) -> Employee | None:
        return db.query(Employee).filter(Employee.EmployeeCode == code).first()

    if upper.startswith("SYNC USER") and len(parts) >= 3:
        code = parts[2]
        emp = _employee(code)
        return {
            "id": cmd.DeviceCommandId, "kind": "user", "code": code,
            "name": (emp.EmployeeName if emp else None) or code,
            "card": (emp.EmployeeRFIDNumber if emp else None) or "",
        }
    if upper.startswith("ENROLL CARD") and len(parts) >= 4:
        code = parts[2]
        emp = _employee(code)
        return {
            "id": cmd.DeviceCommandId, "kind": "user", "code": code,
            "name": (emp.EmployeeName if emp else None) or code,
            "card": parts[3],
        }
    if upper.startswith("ENROLL FACE") and len(parts) >= 3 and payload:
        return {
            "id": cmd.DeviceCommandId, "kind": "face", "code": parts[2],
            "tmp": payload, "len": len(payload),
        }
    if upper.startswith("ENROLL FP") and len(parts) >= 4:
        return {
            "id": cmd.DeviceCommandId, "kind": "fp", "code": parts[2],
            "tmp": parts[3],
        }
    return None


@router.post("/transfer-jobs/{job_id}/execute-sdk")
def execute_transfer_job_via_sdk(
    job_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Deliver this job's queued commands directly to the target devices over the
    zkemkeeper SDK (TCP 4370) instead of waiting for the devices to poll the
    /iclock push endpoints. Runs phase by phase until the job completes.
    """
    job = db.query(TransferJob).filter(TransferJob.TransferJobId == job_id).first()
    if not job:
        raise HTTPException(404, "Transfer job not found")

    if job.Status == "failed":
        # Allow re-driving a stalled/failed job.
        job.Status = f"running_{job.Phase or 'face'}"
        job.ErrorMessage = None
        job.CompletionDate = None

    connection_error: str | None = None
    for _ in range(8):  # phases + retries safety bound
        pending = db.query(DeviceCommand).filter(
            DeviceCommand.TransferJobId == job_id,
            DeviceCommand.Status == "Pending",
        ).all()
        if not pending:
            _advance_job(job, db)
            db.commit()
            if job.Status in ("completed", "failed"):
                break
            pending = db.query(DeviceCommand).filter(
                DeviceCommand.TransferJobId == job_id,
                DeviceCommand.Status == "Pending",
            ).all()
            if not pending:
                break

        now = datetime.utcnow()
        by_device: dict[int, list[DeviceCommand]] = {}
        for cmd in pending:
            by_device.setdefault(cmd.DeviceId, []).append(cmd)

        for device_id, cmds in by_device.items():
            device = db.query(Device).filter(Device.DeviceId == device_id).first()
            if not device or not device.DeviceIPAddress:
                for cmd in cmds:
                    cmd.Status = "Failed"
                    cmd.ExecutionDate = now
                continue

            ops = []
            for cmd in cmds:
                op = _command_to_sdk_op(cmd, db)
                if op is None:
                    cmd.Status = "Failed"
                    cmd.ExecutionDate = now
                else:
                    ops.append(op)
            if not ops:
                continue

            result = push_operations_via_sdk(device.DeviceIPAddress, ops, comm_key=device.CommKey)
            if not result.get("connected"):
                connection_error = (
                    f"SDK push to device '{device.DeviceName}' ({device.DeviceIPAddress}) failed: "
                    f"{result.get('message')}"
                )
                continue

            device.LastPing = now
            result_map = {int(r.get("id", -1)): r for r in result.get("results", []) if isinstance(r, dict)}
            for cmd in cmds:
                r = result_map.get(cmd.DeviceCommandId)
                if r is None:
                    continue
                cmd.SentDate = now
                cmd.ExecutionDate = now
                cmd.Status = "Executed" if r.get("ok") else "Failed"

        db.flush()
        if connection_error:
            job.ErrorMessage = connection_error
            db.commit()
            break
        _advance_job(job, db)
        db.commit()
        if job.Status in ("completed", "failed"):
            break

    if job.Status == "completed":
        job.ErrorMessage = None
    db.commit()
    db.refresh(job)
    out = _job_to_dict(job, db)
    if connection_error:
        out["error_message"] = connection_error
    return out


@router.get("/transfer-jobs")
def list_transfer_jobs(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Return the 20 most recent transfer jobs."""
    jobs = db.query(TransferJob).order_by(TransferJob.TransferJobId.desc()).limit(20).all()
    return [_job_to_dict(j, db) for j in jobs]


@router.get("/transfer-jobs/{job_id}")
def get_transfer_job(
    job_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Poll this endpoint every 5 seconds from the frontend.
    It handles:
      - Resetting timed-out "Sent" commands (communication drop recovery)
      - Auto-retrying "Failed" commands up to MAX_RETRY times
      - Advancing to the next phase when current phase is fully done
        (this is the gate that prevents face + finger running simultaneously)
    """
    job = db.query(TransferJob).filter(TransferJob.TransferJobId == job_id).first()
    if not job:
        raise HTTPException(404, "Transfer job not found.")

    _advance_job(job, db)
    db.commit()

    return _job_to_dict(job, db)


@router.post("/transfer-jobs/{job_id}/retry")
def retry_transfer_job(
    job_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Reset all permanently-failed commands back to Pending so the device
    can retry them. Use this after a prolonged communication outage.
    """
    job = db.query(TransferJob).filter(TransferJob.TransferJobId == job_id).first()
    if not job:
        raise HTTPException(404, "Transfer job not found.")

    failed_cmds = db.query(DeviceCommand).filter(
        DeviceCommand.TransferJobId == job_id,
        DeviceCommand.Status == "Failed",
    ).all()
    for cmd in failed_cmds:
        cmd.Status     = "Pending"
        cmd.RetryCount = 0

    if job.Status in ("failed", "completed"):
        job.Status = f"running_{job.Phase}"

    db.commit()
    return {"reset": len(failed_cmds), "job_id": job_id}
