from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.feature_flags import student_module_enabled
from app.core.security import get_current_user
from app.services.campus_scope import allowed_employee_codes, check_employee_code, devices_query
from app.database import get_db
from app.models.entities import Device, DeviceLog, Employee, EmployeeFaceEmbedding, EmployeePhoto, Student
from app.services.attendance_settings import PunchRule, get_punch_rule
from app.services.punch_rules import assign_directions, filter_new_punches

router = APIRouter()

# Server-side guard against double-posts (camera_service already debounces
# punches for minutes; this only absorbs its retries after network errors).
PUNCH_DUPLICATE_WINDOW_S = 60


def require_service_key(x_service_key: Optional[str] = Header(None)) -> None:
    """Auth for machine-to-machine calls from camera_service (shared secret)."""
    if not x_service_key or x_service_key != settings.camera_service_api_key:
        raise HTTPException(status_code=401, detail="Invalid service key")


@router.post("/enroll/{employee_code}")
async def enroll_face(
    employee_code: str,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Enroll a face photo for an employee: forwards the photo to camera_service
    for embedding extraction, stores the embedding + the source photo.
    Upload 2-3 photos per employee for robust matching.
    """
    employee = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    data = await photo.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    return await _embed_and_store(
        db, employee, data,
        filename=photo.filename or "face-enroll.jpg",
        content_type=photo.content_type or "image/jpeg",
        source="Enroll",
    )


@router.post("/enroll-from-camera/{employee_code}")
async def enroll_from_camera(
    employee_code: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    Enroll using the entry camera's live frame: the employee stands in front of
    the camera and this captures + enrolls what it sees. Best-quality match
    source, since enrollment then shares the camera's angle and lighting.
    """
    employee = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{settings.camera_service_url}/frame")
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Camera service unreachable at {settings.camera_service_url}: {exc.__class__.__name__}",
        ) from exc
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise HTTPException(status_code=503, detail=detail or "No live camera frame available")

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return await _embed_and_store(
        db, employee, resp.content,
        filename=f"camera-capture-{stamp}.jpg",
        content_type="image/jpeg",
        source="CameraCapture",
    )


async def _embed_only(data: bytes, filename: str, content_type: str) -> dict:
    """Run camera_service /embed on image bytes; return quality without storing."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.camera_service_url}/embed",
                files={"photo": (filename, data, content_type)},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Camera service unreachable at {settings.camera_service_url}: {exc.__class__.__name__}",
        ) from exc
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail or "Embedding failed")
    result = resp.json()
    return {"det_score": result.get("det_score"), "face_count": result.get("face_count")}


@router.get("/preview-camera")
async def preview_camera(_user=Depends(get_current_user)):
    """Grab the live camera frame and report face quality — WITHOUT enrolling.
    Returns the image so the operator can preview before confirming."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{settings.camera_service_url}/frame")
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Camera service unreachable at {settings.camera_service_url}: {exc.__class__.__name__}",
        ) from exc
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise HTTPException(status_code=503, detail=detail or "No live camera frame available")

    data = resp.content
    quality = await _embed_only(data, "camera-preview.jpg", "image/jpeg")
    return {
        "image": f"data:image/jpeg;base64,{base64.b64encode(data).decode('ascii')}",
        "det_score": quality["det_score"],
        "face_count": quality["face_count"],
    }


@router.post("/preview-photo")
async def preview_photo(
    photo: UploadFile = File(...),
    _user=Depends(get_current_user),
):
    """Report face quality for an uploaded photo WITHOUT enrolling."""
    data = await photo.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    return await _embed_only(data, photo.filename or "photo.jpg", photo.content_type or "image/jpeg")


async def _embed_and_store(
    db: Session,
    employee: Employee,
    data: bytes,
    filename: str,
    content_type: str,
    source: str,
) -> dict:
    """Shared enrollment path: extract the embedding via camera_service /embed,
    store photo + embedding, nudge the gallery so it's matchable immediately."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.camera_service_url}/embed",
                files={"photo": (filename, data, content_type)},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Camera service unreachable at {settings.camera_service_url}: {exc.__class__.__name__}",
        ) from exc

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail or "Embedding failed")

    result = resp.json()

    photo_row = EmployeePhoto(
        EmployeeCode=employee.EmployeeCode,
        PhotoName=filename[:50],
        PhotoMimeType=content_type,
        PhotoData=base64.b64encode(data).decode("ascii"),
        Source="FaceEnroll",
        Checksum=hashlib.sha256(data).hexdigest(),
        CreatedAt=datetime.utcnow(),
        UpdatedAt=datetime.utcnow(),
    )
    db.add(photo_row)
    db.flush()

    embedding_row = EmployeeFaceEmbedding(
        EmployeeCode=employee.EmployeeCode,
        Embedding=json.dumps(result["embedding"]),
        DetScore=result.get("det_score"),
        EmployeePhotoId=photo_row.EmployeePhotoId,
        Source=source,
        CreatedAt=datetime.utcnow(),
    )
    db.add(embedding_row)
    db.commit()
    db.refresh(embedding_row)

    # Best-effort nudge so the new face is matchable immediately (the service
    # also re-syncs on its own every 5 minutes).
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{settings.camera_service_url}/gallery/refresh")
    except httpx.HTTPError:
        pass

    return {
        "embedding_id": embedding_row.EmployeeFaceEmbeddingId,
        "employee_code": employee.EmployeeCode,
        "employee_name": employee.EmployeeName,
        "det_score": result.get("det_score"),
        "faces_in_photo": result.get("face_count"),
        "enrolled_count": db.query(EmployeeFaceEmbedding)
        .filter(EmployeeFaceEmbedding.EmployeeCode == employee.EmployeeCode)
        .count(),
    }


@router.get("/camera-status")
async def camera_status(_user=Depends(get_current_user)):
    """Proxy camera_service /status so the browser never needs direct access."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.camera_service_url}/status")
        resp.raise_for_status()
        return {"reachable": True, "service_url": settings.camera_service_url, "status": resp.json()}
    except httpx.HTTPError as exc:
        return {
            "reachable": False,
            "service_url": settings.camera_service_url,
            "error": f"{exc.__class__.__name__}: {exc}",
            "status": None,
        }


@router.get("/punches")
def recent_punches(
    limit: int = 20,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Recent face-recognition punches (camera devices only), with snapshots."""
    limit = max(1, min(limit, 100))
    rows = (
        devices_query(db, user, db.query(DeviceLog, Device.DeviceName, Employee.EmployeeName)
                      .join(Device, Device.DeviceId == DeviceLog.DeviceId))   # campus login: its own cameras
        .outerjoin(Employee, Employee.EmployeeCode == DeviceLog.EmployeeCode)
        .filter(Device.DeviceType == "Camera")
        .order_by(DeviceLog.DeviceLogId.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "log_id": lg.DeviceLogId,
            "employee_code": lg.EmployeeCode,
            "employee_name": name,
            "device_name": device_name,
            "log_date": lg.LogDate.isoformat() if lg.LogDate else None,
            "direction": lg.Direction,
            "similarity": lg.WorkCode,
            "snapshot": f"data:image/jpeg;base64,{lg.AttPhoto}" if lg.AttPhoto else None,
        }
        for lg, device_name, name in rows
    ]


@router.get("/enrollments")
def enrollment_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Enrollment counts per employee, for the enrollment table."""
    from sqlalchemy import func

    rows = (
        db.query(
            EmployeeFaceEmbedding.EmployeeCode,
            func.count(EmployeeFaceEmbedding.EmployeeFaceEmbeddingId),
            func.max(EmployeeFaceEmbedding.CreatedAt),
        )
        .group_by(EmployeeFaceEmbedding.EmployeeCode)
        .all()
    )
    allowed = allowed_employee_codes(db, user)   # campus login: its own staff only
    return [
        {"employee_code": code, "count": count, "last_enrolled_at": last.isoformat() if last else None}
        for code, count, last in rows if allowed is None or code in allowed
    ]


@router.get("/enrollments/{employee_code}")
def list_enrollments(
    employee_code: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    rows = (
        db.query(EmployeeFaceEmbedding)
        .filter(EmployeeFaceEmbedding.EmployeeCode == employee_code)
        .order_by(EmployeeFaceEmbedding.EmployeeFaceEmbeddingId.desc())
        .all()
    )
    return [
        {
            "embedding_id": r.EmployeeFaceEmbeddingId,
            "det_score": r.DetScore,
            "photo_id": r.EmployeePhotoId,
            "source": r.Source,
            "created_at": r.CreatedAt.isoformat() if r.CreatedAt else None,
        }
        for r in rows
    ]


@router.delete("/enrollments/{embedding_id}")
async def delete_enrollment(
    embedding_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    row = (
        db.query(EmployeeFaceEmbedding)
        .filter(EmployeeFaceEmbedding.EmployeeFaceEmbeddingId == embedding_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    check_employee_code(db, user, row.EmployeeCode)
    db.delete(row)
    db.commit()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{settings.camera_service_url}/gallery/refresh")
    except httpx.HTTPError:
        pass

    return {"deleted": embedding_id}


class FacePunchIn(BaseModel):
    employee_code: str
    timestamp: datetime
    similarity: float
    device_serial: str = "CAM-ENTRY-01"
    device_name: str = "Entry Camera"
    snapshot_b64: Optional[str] = None


def _get_or_create_camera_device(db: Session, serial: str, name: str) -> Device:
    device = db.query(Device).filter(Device.SerialNumber == serial).first()
    if device:
        return device
    device = Device(
        DeviceName=name,
        SerialNumber=serial,
        DeviceDirection="IN",
        DeviceType="Camera",
        IsAttendanceDevice="Y",
        TransactionStamp="0",
    )
    db.add(device)
    db.flush()
    return device


AUTO_LEARN_CAP = 3  # live embeddings kept per person (oldest dropped)


class AutoLearnIn(BaseModel):
    employee_code: str
    embedding: list[float]
    det_score: Optional[float] = None


@router.post("/auto-learn")
def auto_learn(
    payload: AutoLearnIn,
    db: Session = Depends(get_db),
    _key=Depends(require_service_key),
):
    """Template adaptation: camera_service feeds back the live embedding of a
    high-confidence confirmed punch, so the gallery learns the camera's own
    angle/lighting. Capped per person; oldest auto-learned rows are dropped."""
    if len(payload.embedding) != 512:
        raise HTTPException(status_code=400, detail="Embedding must be 512 floats")
    employee = db.query(Employee).filter(Employee.EmployeeCode == payload.employee_code).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    row = EmployeeFaceEmbedding(
        EmployeeCode=payload.employee_code,
        Embedding=json.dumps(payload.embedding),
        DetScore=payload.det_score,
        Source="AutoLearn",
        CreatedAt=datetime.utcnow(),
    )
    db.add(row)
    db.flush()

    stale = (
        db.query(EmployeeFaceEmbedding)
        .filter(
            EmployeeFaceEmbedding.EmployeeCode == payload.employee_code,
            EmployeeFaceEmbedding.Source == "AutoLearn",
        )
        .order_by(EmployeeFaceEmbedding.CreatedAt.desc(), EmployeeFaceEmbedding.EmployeeFaceEmbeddingId.desc())
        .offset(AUTO_LEARN_CAP)
        .all()
    )
    for s in stale:
        db.delete(s)
    db.commit()

    return {"embedding_id": row.EmployeeFaceEmbeddingId, "dropped": len(stale)}


class HeartbeatIn(BaseModel):
    device_serial: str = "CAM-ENTRY-01"
    device_name: str = "Entry Camera"
    camera_connected: bool = False


@router.post("/heartbeat")
def heartbeat(
    payload: HeartbeatIn,
    db: Session = Depends(get_db),
    _key=Depends(require_service_key),
):
    """camera_service reports in every minute while its camera stream is up,
    so the virtual device shows Online on the Devices page between punches."""
    device = _get_or_create_camera_device(db, payload.device_serial, payload.device_name)
    if payload.camera_connected:
        device.LastPing = datetime.utcnow()
    db.commit()
    return {"device_id": device.DeviceId, "camera_connected": payload.camera_connected}


@router.post("/punch")
def face_punch(
    payload: FacePunchIn,
    db: Session = Depends(get_db),
    _key=Depends(require_service_key),
):
    """A confirmed face match from camera_service becomes a normal attendance
    punch: a DeviceLog row under a virtual camera device, so processing,
    reports and the logs UI all work unchanged."""
    employee = db.query(Employee).filter(Employee.EmployeeCode == payload.employee_code).first()
    is_student = False
    if not employee:
        student = (
            db.query(Student).filter(Student.StudentCode == payload.employee_code, Student.IsActive == "Y").first()
            if student_module_enabled(db) else None
        )
        if not student:
            raise HTTPException(status_code=404, detail="Employee not found")
        employee = SimpleNamespace(EmployeeCode=student.StudentCode, EmployeeName=student.StudentName)
        is_student = True

    device = _get_or_create_camera_device(db, payload.device_serial, payload.device_name)
    log_dt = payload.timestamp.replace(microsecond=0, tzinfo=None)

    # Same duplicate window + IN/OUT numbering as device pushes (Attendance Rules);
    # the camera's own 60 s floor still applies when the rule is set lower.
    punch_rule = get_punch_rule(db)
    rule = punch_rule if punch_rule.duplicate_seconds >= PUNCH_DUPLICATE_WINDOW_S else \
        PunchRule(duplicate_seconds=PUNCH_DUPLICATE_WINDOW_S, direction_mode=punch_rule.direction_mode)
    candidate = {"EmployeeCode": payload.employee_code, "LogDate": log_dt}
    if not filter_new_punches(db, [candidate], rule):
        db.commit()  # keep the device row if it was just created
        return {"stored": False, "duplicate": True, "device_id": device.DeviceId}

    log = DeviceLog(
        DeviceId=device.DeviceId,
        EmployeeCode=payload.employee_code,
        LogDate=log_dt,
        VerificationType="FA",
        Direction=device.DeviceDirection or "IN",
        WorkCode=f"sim={payload.similarity:.3f}"[:50],
        AttPhoto=payload.snapshot_b64,
    )
    db.add(log)
    device.LastPing = datetime.utcnow()
    db.flush()
    assign_directions(db, {(payload.employee_code, log_dt.date())}, rule)
    db.commit()
    db.refresh(log)

    # Same side effects as an iclock ATTLOG push: mess tokens + webhook.
    # (Mess tokens are employee-only; student punches skip them.)
    if not is_student:
        try:
            from app.services.mess_service import process_punches_for_mess
            process_punches_for_mess(
                db, device.DeviceId,
                [{"EmployeeCode": payload.employee_code, "LogDate": log_dt}],
            )
        except Exception:  # noqa: BLE001
            pass

    if settings.webhook_url:
        try:
            from app.services.webhook import post_logs
            post_logs(
                settings.webhook_url,
                {
                    "serial_number": payload.device_serial,
                    "table": "ATTLOG",
                    "stamp": None,
                    "logs": [{
                        "EmployeeCode": payload.employee_code,
                        "LogDate": log_dt.isoformat(),
                        "VerificationType": "FA",
                        "Direction": device.DeviceDirection or "IN",
                    }],
                },
            )
        except Exception:  # noqa: BLE001
            pass

    return {
        "stored": True,
        "duplicate": False,
        "device_id": device.DeviceId,
        "log_id": log.DeviceLogId,
        "employee_name": employee.EmployeeName,
    }


@router.get("/gallery")
def get_gallery(
    db: Session = Depends(get_db),
    _key=Depends(require_service_key),
):
    """Full embedding gallery, pulled by camera_service on start/refresh."""
    rows = (
        db.query(EmployeeFaceEmbedding, Employee.EmployeeName)
        .join(Employee, Employee.EmployeeCode == EmployeeFaceEmbedding.EmployeeCode)
        .all()
    )
    if student_module_enabled(db):
        rows += (
            db.query(EmployeeFaceEmbedding, Student.StudentName)
            .join(Student, Student.StudentCode == EmployeeFaceEmbedding.EmployeeCode)
            .filter(Student.IsActive == "Y")
            .all()
        )
    return {
        "count": len(rows),
        "entries": [
            {
                "embedding_id": r.EmployeeFaceEmbeddingId,
                "employee_code": r.EmployeeCode,
                "employee_name": name,
                "embedding": json.loads(r.Embedding),
            }
            for r, name in rows
        ],
    }
