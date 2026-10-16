from __future__ import annotations
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import gzip
import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.entities import Device, DeviceCommand, DeviceEmployee, DeviceLog, Employee, EmployeeBio, EmployeePhoto
from app.services import adms_log
from app.services.bio_store import parse_finger_index, upsert_template
from app.services.employee_delete import blocked_pins, not_a_staff_pin, student_codes
from app.services.attendance_settings import get_punch_rule
from app.services.iclock_parser import parse_attlog_lines, parse_operlog_lines, parse_photo_lines
from app.services.punch_rules import assign_directions, day_keys, filter_new_punches
from app.services.push_channel import (
    PRI_ADMIN, ROLE_DEVICE_ADMIN, ROLE_DEVICE_USER, note_user_on_device, propagate_template, restore_after_failed_delete,
)
from app.services.webhook import post_logs

iclock_router = APIRouter()

# Commands served to a device per getrequest poll. Multiple C:<id>:<cmd> lines
# per response are allowed by the push protocol; keep the batch small so a
# device that chokes on one command doesn't stall a large backlog.
GETREQUEST_BATCH_SIZE = 5

# A command nobody has fetched for this long is stale (eTimeTrackLite marks such commands
# "Time Expired" instead of sending them): a template queued weeks ago must not land on a
# reader when it finally comes back online.
COMMAND_TTL_HOURS = 24

# In-memory ring buffer of recent device requests, so admins can watch whether a
# device is actually pushing attendance (POST cdata ATTLOG) vs only polling.
_COMM_LOG: deque = deque(maxlen=300)


def _log_comm(sn: str, action: str, detail: str = "") -> None:
    _COMM_LOG.appendleft({
        "at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "sn": sn,
        "action": action,
        "detail": detail,
    })


def get_recent_comm(sn: Optional[str] = None, limit: int = 100) -> list[dict]:
    items = [e for e in _COMM_LOG if not sn or e["sn"] == sn]
    return items[:limit]


def _get_db() -> Session:
    return SessionLocal()


def _get_or_register_device(db: Session, sn: str) -> Optional[Device]:
    """
    Look up a device by serial; auto-register it when unknown — mirroring
    production eBioServer, which inserts a Devices row on first contact so a
    device pointed at the server starts syncing without manual registration.
    Returns None only for a blank serial.
    """
    sn = (sn or "").strip()
    if not sn:
        return None
    device = db.query(Device).filter(Device.SerialNumber == sn).first()
    if device:
        return device
    device = Device(
        DeviceName=sn,
        SerialNumber=sn,
        DeviceDirection="IN",
        TransactionStamp="0",
        IsAttendanceDevice="Y",
    )
    db.add(device)
    try:
        db.commit()
    except Exception:
        # Concurrent first-contact from the same device: another request won
        # the insert race on the unique SerialNumber — reuse that row.
        db.rollback()
        device = db.query(Device).filter(Device.SerialNumber == sn).first()
        if device:
            return device
        raise
    db.refresh(device)
    _log_comm(sn, "register", "device auto-registered on first contact")
    return device


def _decode_push_body(raw: bytes, content_encoding: Optional[str]) -> str:
    if content_encoding and "gzip" in content_encoding.lower():
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    return raw.decode("utf-8", errors="ignore")


def _user_data_line(code: str, db: Session, card_override: str | None = None, device_id: int | None = None) -> str:
    """
    Build a production-eBioServer "DATA USER" line for one employee. This is
    the classic eSSL dialect (DATA USER / DATA FP), not the newer ZKTeco
    "DATA UPDATE USERINFO" dialect — eSSL firmwares in the field only reliably
    accept the classic form (verified against the compiled eBioServer library).
    The privilege is the one the person has on THAT reader when it is known, so
    re-sending a user (new name, transfer back) never removes a device admin.
    """
    emp = db.query(Employee).filter(Employee.EmployeeCode == code).first()
    name = (emp.EmployeeName if emp else None) or code
    card = card_override if card_override is not None else ((emp.EmployeeRFIDNumber if emp else None) or "")
    on_reader = None
    if emp is not None and device_id is not None:
        on_reader = (db.query(DeviceEmployee.Role)
                     .filter(DeviceEmployee.DeviceId == device_id, DeviceEmployee.EmployeeId == emp.EmployeeId)
                     .scalar())
    if on_reader in (ROLE_DEVICE_ADMIN, ROLE_DEVICE_USER):
        pri = PRI_ADMIN if on_reader == ROLE_DEVICE_ADMIN else "0"
    else:
        pri = PRI_ADMIN if emp and (emp.Role or "").strip().lower() == "admin" else "0"
    verify = "0"  # 0 = any of finger/face/card/password
    return (
        f"DATA USER PIN={code}\tName={name}\tPri={pri}\tVerify={verify}"
        f"\tCard={card}\tPasswd="
        f"\tExpires=0\tStartDatetime=2000-01-01\tEndDatetime=3000-01-01"
    )


# A transfer / sync command that cannot be delivered (no template stored on the
# server) is failed with this retry count so the job's auto-retry never resends it.
NO_RETRY = 99


def _bio_type_from_desc(description: str | None, default: str) -> str:
    """Templates uploaded as BIODATA are described as "BIODATA t<Type> v<Major>.<Minor> f<Format>"."""
    m = re.match(r"BIODATA t(\d+)", description or "")
    return m.group(1) if m else default


def _biodata_line(code: str, row: EmployeeBio, template: str, bio_type: str, number: int) -> str:
    """
    "DATA UPDATE BIODATA" is the push-protocol 2.x table that AI-face readers keep
    their visible-light face (Type=9) and fingerprint (Type=1) templates in. This
    is the exact line eTimeTrackLite / eBioServer send when they transfer such a
    template: No = finger number (0 for a face), Index = 0, Format = 0, and the
    MajorVer / MinorVer the reader reported when it uploaded the template.
    """
    major = (row.MajorVer or "").strip()
    minor = (row.MinorVer or "").strip() or "0"
    return (
        f"DATA UPDATE BIODATA Pin={code}\tNo={number}\tIndex=0\tValid=1\tDuress=0"
        f"\tType={bio_type}\tMajorVer={major}\tMinorVer={minor}\tFormat=0\tTmp={template}"
    )


def _face_push_line(code: str, template: str, db: Session) -> str:
    """Face template -> push line in the dialect the template came in."""
    rows = (
        db.query(EmployeeBio)
        .filter(EmployeeBio.EmployeeCode == code, EmployeeBio.BioName == "FACE")
        .order_by(EmployeeBio.EmployeeBioId.desc())
        .all()
    )
    # The row the template came from decides the dialect; the newest face is only a fallback.
    row = next((r for r in rows if (r.Bio or "") == template), rows[0] if rows else None)
    if row is not None and (row.MajorVer or "").strip():
        # Came from a BIODATA upload (AI-face reader): must go back as BIODATA. A
        # "DATA UPDATE FACE" line carries the old near-infrared Face 7.0 format and
        # an AI-face reader rejects it.
        return _biodata_line(code, row, template, _bio_type_from_desc(row.BioDescription, "9"), 0)
    # Old-style face (Face 7.0, SDK slot FID=50): classic "DATA UPDATE FACE".
    return f"DATA UPDATE FACE PIN={code}\tFID=50\tSIZE={len(template)}\tValid=1\tTMP={template}"


def _finger_push_line(code: str, template: str, db: Session) -> str:
    rows = (
        db.query(EmployeeBio)
        .filter(EmployeeBio.EmployeeCode == code, EmployeeBio.BioName == "FINGER")
        .order_by(EmployeeBio.EmployeeBioId.desc())
        .all()
    )
    row = next((r for r in rows if (r.Bio or "") == template), None)
    finger_no = row.FingerIndex if row is not None and row.FingerIndex is not None else 0
    if row is not None and (row.MajorVer or "").strip():
        return _biodata_line(code, row, template, _bio_type_from_desc(row.BioDescription, "1"), finger_no)
    return f"DATA FP PIN={code}\tFID={finger_no}\tValid=1\tSIZE={len(template)}\tTMP={template}"


def _translate_for_push(cmd: DeviceCommand, db: Session) -> Optional[str]:
    """
    Translate this app's stored command text (e.g. "ENROLL FACE 215") into the
    eSSL push-protocol command string the device actually understands, using
    the exact formats production eBioServer / eTimeTrackLite emit.
    Falls back to the raw stored text for anything unrecognised.

    Returns None when the command must NOT be sent: a face / finger transfer
    with no template stored on the server. eBioServer and eTimeTrackLite only
    ever send templates they hold; the on-device enrollment command
    ("ENROLL_BIO", which opens the reader's Enroll Face screen) belongs to
    their separate "Enroll" button, so here it is reserved for commands of
    Type "enroll" (Devices > Enroll on device).
    """
    raw = (cmd.DeviceCommand or "").strip()
    payload = (cmd.DeviceCommandFace or "").strip()
    parts = raw.split()
    upper = raw.upper()
    on_device_enroll = (cmd.Type or "").strip().lower() == "enroll"

    if (upper.startswith("ENROLL FACE") or upper.startswith("ENROLL_FACE")) and len(parts) >= 2:
        code = parts[2] if len(parts) >= 3 else parts[1]
        if payload:
            return _face_push_line(code, payload, db)
        if on_device_enroll:
            return f"ENROLL_BIO TYPE=9\tNO=0\tPIN={code}\tRETRY=3\tOVERWRITE=1"
        return None

    if upper.startswith("ENROLL FP") and len(parts) >= 3:
        code = parts[2]
        template = parts[3] if len(parts) >= 4 else payload
        if template:
            return _finger_push_line(code, template, db)
        if on_device_enroll:
            return f"ENROLL_BIO TYPE=1\tNO=0\tPIN={code}\tRETRY=3\tOVERWRITE=1"
        return None

    if upper.startswith("ENROLL CARD") and len(parts) >= 4:
        # Production has no separate card command — the card rides on DATA USER.
        return _user_data_line(parts[2], db, card_override=parts[3], device_id=cmd.DeviceId)

    if upper.startswith("ENROLL BIOPHOTO") and len(parts) >= 3:
        # Face as a photo: an AI-face reader extracts its own template from the JPEG (eBioServer
        # "AI Face" / eTimeTrackLite "Bio Photo"). Exact production format, Type=9 = visible-light face.
        code = parts[2]
        if payload:
            return (
                f"DATA UPDATE BIOPHOTO PIN={code}\tFileName={code}.jpg\tType=9"
                f"\tSIZE={len(payload)}\tSize={len(payload)}\tContent={payload}"
            )
        return None

    if upper.startswith("ENROLL PHOTO") and len(parts) >= 3:
        code = parts[2]
        if payload:
            return (
                f"DATA UPDATE USERPIC PIN={code}\tFileName={code}.jpg"
                f"\tSIZE={len(payload)}\tSize={len(payload)}\tContent={payload}"
            )
        return None

    if upper.startswith("SYNC USER") and len(parts) >= 3:
        return _user_data_line(parts[2], db, device_id=cmd.DeviceId)

    if upper.startswith("DELETE USER") and len(parts) >= 3:
        # Push-protocol 2.x (AI-face) readers delete with DATA DELETE USERINFO (which also removes the person's
        # faces, fingers and photos) and reject the old DEL_USER form; classic firmwares keep DEL_USER.
        device = db.get(Device, cmd.DeviceId)
        if device is not None and (device.DeviceType or "").strip().upper() == "AI":
            return f"DATA DELETE USERINFO PIN={parts[2]}"
        return f"DATA DEL_USER PIN={parts[2]}"

    if upper in {"CLEAR LOG", "CLEAR LOGS"}:
        return "CLEAR LOG"
    if upper == "REBOOT":
        return "REBOOT"
    if upper in {"OPENDOOR", "UNLOCK", "UNLOCK DOOR"}:
        return "AC_UNLOCK"

    return raw


def _mark_ai_reader(db: Session, device: Device, why: str) -> None:
    """AI-face (visible-light) readers are driven differently (BIODATA / BIOPHOTO instead of the
    old FACE table). eBioServer needs the admin to set DeviceType=AI by hand; here it is learnt
    from the reader itself and only filled in when nothing is set yet."""
    if (device.DeviceType or "").strip():
        return
    device.DeviceType = "AI"
    _log_comm(device.SerialNumber or "", "detect", f"marked as AI-face reader ({why})")


FACE_PHOTO_NAME = "BIOPHOTO"   # photo an AI-face reader enrolled the person from
PROFILE_PHOTO_NAME = "PROFILE"  # display picture (USERPIC / SDK)


def _upsert_employee_photo(
    db: Session,
    employee_code: str,
    photo_data: str,
    device_id: int,
    photo_mime_type: str = "image/jpeg",
    source: str = "iclock",
    photo_name: str = PROFILE_PHOTO_NAME,
) -> None:
    """One row per (person, kind): the display picture and the reader's enrolment face photo are
    kept apart because only the latter is known to pass an AI-face reader's quality check."""
    query = db.query(EmployeePhoto).filter(EmployeePhoto.EmployeeCode == employee_code)
    if photo_name == PROFILE_PHOTO_NAME:
        query = query.filter((EmployeePhoto.PhotoName == PROFILE_PHOTO_NAME) | (EmployeePhoto.PhotoName.is_(None)))
    else:
        query = query.filter(EmployeePhoto.PhotoName == photo_name)
    existing = query.order_by(EmployeePhoto.EmployeePhotoId.desc()).first()
    if existing:
        existing.PhotoData = photo_data
        existing.PhotoMimeType = photo_mime_type
        existing.Source = source
        existing.DeviceId = device_id
        existing.UpdatedAt = datetime.utcnow()
        return

    db.add(
        EmployeePhoto(
            EmployeeCode=employee_code,
            DeviceId=device_id,
            PhotoName=photo_name,
            PhotoMimeType=photo_mime_type,
            PhotoData=photo_data,
            Source=source,
            CreatedAt=datetime.utcnow(),
            UpdatedAt=datetime.utcnow(),
        )
    )


# Tables a reader posts users / templates to besides OPERLOG (push 2.x names and the older ones).
_TEMPLATE_TABLES = {"BIODATA", "USERINFO", "FINGERTMP", "FACE", "USER", "TEMPLATEV10"}


def _store_operlog_records(db: Session, device: Device, records: list[dict]) -> int:
    """Import users / fingerprints / faces / photos a reader uploaded (OPERLOG or a query reply).
    Returns how many records were stored."""
    inserted = 0
    blocked, students = blocked_pins(db), student_codes(db)
    skipped: dict[str, int] = {}
    for rec in records:
        kind = rec["kind"]
        pin = rec["pin"]
        fields = rec["fields"]

        employee = db.query(Employee).filter(Employee.EmployeeCode == pin).first()
        if not employee:
            why = not_a_staff_pin(db, pin, blocked, students)
            if why:   # a person deleted here, or a student on a shared reader: no staff record, data dropped
                skipped[why] = skipped.get(why, 0) + 1
                continue
            numeric_code = int(pin) if pin.isdigit() else int(datetime.utcnow().timestamp())
            employee = Employee(
                EmployeeName=fields.get("NAME") or pin,
                EmployeeCode=pin,
                StringCode=pin,
                NumericCode=numeric_code,
                Role="Employee",
            )
            db.add(employee)
            db.flush()

        if kind == "USER":
            name = (fields.get("NAME") or "").strip()
            # The server's name wins: a reader's name only fills a person who has no real name here yet (blank, or
            # just the PIN). Taking it always made every Refresh from device undo the names set on the server.
            current = (employee.EmployeeName or "").strip()
            if name and name != pin and (not current or current == pin):
                employee.EmployeeName = name
            card = (fields.get("CARD") or "").strip()
            if card and card != "0":
                employee.EmployeeRFIDNumber = card
            # Remember which reader holds this user (and their privilege on it): this is what the Users list,
            # Transfer, deletes and Send names rely on for readers we cannot reach over the SDK.
            note_user_on_device(db, device, employee, privilege=fields.get("PRI"))
            inserted += 1

        elif kind in {"FP", "FACE"}:
            tmp = (fields.get("TMP") or "").strip()
            if not tmp:
                continue
            if kind == "FP":  # one row per finger: FID is the finger number
                upsert_template(db, pin, "FINGER", tmp, "Pushed by device", finger_index=parse_finger_index(fields.get("FID")))
                propagate_template(db, device, employee, "FINGER", tmp)
            else:
                upsert_template(db, pin, "FACE", tmp, "Pushed by device")
                propagate_template(db, device, employee, "FACE", tmp)
            note_user_on_device(db, device, employee)  # a template upload means this reader holds the person
            inserted += 1

        elif kind == "BIODATA":
            tmp = (fields.get("TMP") or "").strip()
            bio_name = {"1": "FINGER", "2": "FACE", "9": "FACE"}.get((fields.get("TYPE") or "").strip())
            if not tmp or not bio_name:
                continue
            desc = f"BIODATA t{fields.get('TYPE')} v{fields.get('MAJORVER', '')}.{fields.get('MINORVER', '')} f{fields.get('FORMAT', '')}"[:50]
            finger_no = fields.get("NO") if fields.get("NO") not in (None, "") else fields.get("INDEX")
            upsert_template(
                db, pin, bio_name, tmp, desc,
                finger_index=parse_finger_index(finger_no) if bio_name == "FINGER" else None,
                major_ver=fields.get("MAJORVER"), minor_ver=fields.get("MINORVER"),
            )
            if (fields.get("TYPE") or "").strip() == "9":
                _mark_ai_reader(db, device, "uploaded a BIODATA Type=9 face")
            propagate_template(db, device, employee, bio_name, tmp)
            note_user_on_device(db, device, employee)
            inserted += 1
        elif kind in {"USERPIC", "BIOPHOTO"}:
            content = (fields.get("CONTENT") or "").strip()
            if not content:
                continue
            # USERPIC is the display picture; BIOPHOTO is the photo an AI-face reader built its
            # face template from - eBioServer stores it as the person's "AI Face" and sends it
            # to other AI readers as DATA UPDATE BIOPHOTO, which is how it transfers AI faces.
            is_face_photo = kind == "BIOPHOTO"
            _upsert_employee_photo(
                db=db,
                employee_code=pin,
                photo_data=content,
                device_id=device.DeviceId,
                source="iclock-operlog",
                photo_name=FACE_PHOTO_NAME if is_face_photo else PROFILE_PHOTO_NAME,
            )
            if is_face_photo:
                _mark_ai_reader(db, device, "uploaded a BIOPHOTO")
                note_user_on_device(db, device, employee)
            propagate_template(db, device, employee, "BIOPHOTO" if is_face_photo else "PROFILE", content)
            inserted += 1
    if skipped:
        _log_comm(device.SerialNumber or "", "skip", "not created as staff: " + ", ".join(
            f"{n} {'deleted here' if k == 'blocked' else 'student'} ID(s)" for k, n in skipped.items()))
    return inserted


@iclock_router.get("/ping")
def ping(SN: str = Query(...)):
    db = _get_db()
    try:
        device = _get_or_register_device(db, SN)
        if not device:
            _log_comm(SN, "ping", "blank serial")
            return PlainTextResponse("OK")
        device.LastPing = datetime.utcnow()
        db.commit()
        _log_comm(SN, "ping")
        return PlainTextResponse("OK")
    finally:
        db.close()


@iclock_router.get("/cdata")
def cdata_handshake(
    request: Request,
    SN: str = Query(...),
    options: Optional[str] = Query(default=None),
    pushver: Optional[str] = Query(default=None),
):
    """
    Push-protocol handshake. Devices call GET /iclock/cdata?SN=xxx&options=all
    on boot/registration and expect a plain-text option block; without it many
    firmwares never start polling getrequest or pushing attendance.

    The block below reproduces production eBioServer byte-for-byte (extracted
    from its compiled handlers): CR line terminators, old-style Stamp=/OpStamp=
    names when a stamp exists (ATTLOGStamp=None etc. otherwise), Delay=1, and a
    trailing blank line. Older eSSL firmwares key on the old option names —
    with only the new names they never begin auto-pushing.
    """
    db = _get_db()
    try:
        device = _get_or_register_device(db, SN)
        if not device:
            _log_comm(SN, "handshake", "blank serial")
            return PlainTextResponse("OK")
        device.LastPing = datetime.utcnow()
        # pushver=2.x in the handshake = push-protocol 2 firmware = AI-face reader (BIODATA / BIOPHOTO).
        if (pushver or "").strip()[:1].isdigit() and int((pushver or "0").strip()[0]) >= 2:
            _mark_ai_reader(db, device, f"pushver={pushver}")
        db.commit()
        _log_comm(SN, "handshake", f"options={options or 'all'}" + (f" pushver={pushver}" if pushver else ""))
        att_stamp = (device.TransactionStamp or "").strip()
        op_stamp = (device.OpStamp or "").strip()
        tz = (device.Timezone or "").strip()
        lines = [
            f"GET OPTION FROM: {SN}",
            f"Stamp={att_stamp}" if att_stamp and att_stamp != "0" else "ATTLOGStamp=None",
            f"OpStamp={op_stamp}" if op_stamp and op_stamp != "0" else "OPERLOGStamp=None",
            "ATTPHOTOStamp=None",
            "ErrorDelay=30",
            "Delay=1",
            "TransTimes=09:00;18:30",
            "TransInterval=1",
            "TransFlag=111111101101",
            "Realtime=1",
            "TimeOut=30",
        ]
        if tz:
            lines.append(f"TimeZone={tz}")
        lines.append("Encrypt=0")
        body = "\r".join(lines) + "\r\r"
        adms_log.record(SN, "in", "GET cdata (handshake)", request.url.query)
        adms_log.record(SN, "out", "handshake reply", None, body.replace("\r", "\n"))
        return PlainTextResponse(body)
    finally:
        db.close()


@iclock_router.get("/getrequest")
def getrequest(SN: str = Query(...)):
    """
    Device command poll. Real push-protocol devices fetch commands HERE (not
    GET /devicecmd) and expect them framed as "C:<id>:<command>" lines.
    """
    db = _get_db()
    try:
        device = _get_or_register_device(db, SN)
        if not device:
            return PlainTextResponse("OK")
        now = datetime.utcnow()
        device.LastPing = now

        pending = (
            db.query(DeviceCommand)
            .filter(DeviceCommand.DeviceId == device.DeviceId, DeviceCommand.Status == "Pending")
            .order_by(DeviceCommand.DeviceCommandId.asc())
            .limit(GETREQUEST_BATCH_SIZE)
            .all()
        )
        lines = []
        skipped = []
        expired = []
        for cmd in pending:
            if cmd.CreationDate and now - cmd.CreationDate > timedelta(hours=COMMAND_TTL_HOURS):
                cmd.Status = "Expired"
                cmd.ExecutionDate = now
                cmd.RetryCount = NO_RETRY
                expired.append(f"#{cmd.DeviceCommandId} {(cmd.DeviceCommand or '')[:40]} (queued {cmd.CreationDate:%Y-%m-%d %H:%M})")
                continue
            text = _translate_for_push(cmd, db)
            if text is None:
                # Nothing to send (no template on the server). Fail it for good: the
                # device must never be asked to enrol on its own screen in place of a transfer.
                cmd.Status = "Failed"
                cmd.ExecutionDate = now
                cmd.RetryCount = NO_RETRY
                skipped.append(f"#{cmd.DeviceCommandId} {cmd.DeviceCommand}: no template stored on the server")
                continue
            cmd.Status = "Sent"
            cmd.SentDate = now
            lines.append(f"C:{cmd.DeviceCommandId}:{text}")
        db.commit()
        _log_comm(SN, "poll", f"{len(lines)} command(s) sent" if lines else "no commands")
        if lines:
            adms_log.record(SN, "out", "commands sent", None, "\n".join(lines))
        if skipped:
            _log_comm(SN, "skip", f"{len(skipped)} command(s) not sent: no template on the server")
            adms_log.record(SN, "out", "commands skipped (no template)", None, "\n".join(skipped))
        if expired:
            _log_comm(SN, "expire", f"{len(expired)} command(s) older than {COMMAND_TTL_HOURS} h expired, not sent")
            adms_log.record(SN, "out", "commands expired (too old)", None, "\n".join(expired))
        return PlainTextResponse("\n".join(lines) if lines else "OK")
    finally:
        db.close()


@iclock_router.post("/cdata")
async def cdata(
    request: Request,
    SN: str = Query(...),
    table: str = Query(default="ATTLOG"),
    Stamp: str = Query(default="0"),
    OpStamp: Optional[str] = Query(default=None),
):
    # Classic firmwares send the OPERLOG stamp as OpStamp= (eBioServer keys on that name);
    # push 2.x sends table=OPERLOG&Stamp=. Accept both.
    if OpStamp is not None and (Stamp or "0") == "0":
        Stamp = OpStamp
    # Devices POST raw tab-separated text (not JSON) — read the body directly;
    # a typed Body(...) parameter makes FastAPI JSON-parse it and reply 422,
    # which silently drops every push.
    payload = _decode_push_body(await request.body(), request.headers.get("content-encoding"))
    if table.upper() != "ATTLOG":  # punches are frequent and already visible in the Logs page
        adms_log.record(SN, "in", f"POST cdata {table.upper()}", request.url.query, payload)
    db = _get_db()
    try:
        device = _get_or_register_device(db, SN)
        if not device:
            _log_comm(SN, f"PUSH {table.upper()}", "blank serial")
            return PlainTextResponse("OK")

        inserted = 0
        duplicates = 0
        clock_warn = None
        logs_for_webhook: list[dict] = []
        table_upper = table.upper()
        if table_upper == "ATTLOG":
            parsed = parse_attlog_lines(payload)
            existing: set = set()
            if parsed:
                # Devices re-upload their whole backlog after ATTLOGStamp=None; dedupe against what is
                # already stored for the batch's time span (a duplicate has the same LogDate, so it must
                # lie inside it). Reading the reader's entire history here, as before, made every upload
                # slower with every punch ever stored.
                lo = min(item["LogDate"] for item in parsed)
                hi = max(item["LogDate"] for item in parsed)
                existing = set(
                    db.query(DeviceLog.EmployeeCode, DeviceLog.LogDate)
                    .filter(DeviceLog.DeviceId == device.DeviceId, DeviceLog.LogDate >= lo, DeviceLog.LogDate <= hi)
                    .all()
                )
            now_local = datetime.now()
            fresh: list[dict] = []
            for item in parsed:
                key = (item["EmployeeCode"], item["LogDate"])
                if key in existing:
                    duplicates += 1
                    continue
                existing.add(key)
                if clock_warn is None and item["LogDate"] > now_local + timedelta(minutes=30):
                    clock_warn = item["LogDate"]
                fresh.append(item)
            # Burst filter: a face reader re-reads a lingering face many times in a
            # few seconds; keep one punch per duplicate window (Attendance Rules).
            punch_rule = get_punch_rule(db)
            kept = filter_new_punches(db, fresh, punch_rule)
            duplicates += len(fresh) - len(kept)
            for item in kept:
                db.add(
                    DeviceLog(
                        DeviceId=device.DeviceId,
                        EmployeeCode=item["EmployeeCode"],
                        LogDate=item["LogDate"],
                        VerificationType=item.get("VerificationType"),
                        Direction=item.get("Direction") or device.DeviceDirection,
                        WorkCode=item.get("WorkCode"),
                    )
                )
                logs_for_webhook.append(item)
                inserted += 1
            if kept:
                db.flush()
                assign_directions(db, day_keys(kept), punch_rule)  # 1st IN, 2nd OUT, ...
        elif table_upper == "OPERLOG":
            # Devices push enrolled users / fingerprints / faces / photos here.
            # Production eBioServer imports them into Employees/EmployeesBio —
            # this is how "read data from device" happens automatically.
            inserted += _store_operlog_records(db, device, parse_operlog_lines(payload))
        elif table_upper in _TEMPLATE_TABLES:
            # Readers also answer a refresh with the user / fingerprint / face tables themselves
            # (table=BIODATA is how an AI-face reader sends its faces). The lines look exactly like OPERLOG
            # ones, so they are imported the same way - these were being acknowledged and dropped.
            inserted += _store_operlog_records(db, device, parse_operlog_lines(payload))
        elif table_upper in {"BIOPHOTO", "USERPIC"} and any(
                r["fields"].get("CONTENT") for r in parse_operlog_lines(payload, default_kind=table_upper)):
            # A reader's photo table (PIN / FileName / Content): the person's enrolment photo or display picture.
            # Before, these went through the attendance-photo parser, which knows no Content= field: dropped.
            inserted += _store_operlog_records(db, device, parse_operlog_lines(payload, default_kind=table_upper))
        elif table_upper in {"ATTPHOTO", "BIOPHOTO", "PHOTO"}:
            for item in parse_photo_lines(payload):
                employee_code = item.get("EmployeeCode")
                photo_data = item.get("PhotoData")
                if not employee_code or not photo_data:
                    continue
                employee = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
                if not employee:
                    if not_a_staff_pin(db, employee_code):
                        continue   # deleted here or a student: no staff record
                    numeric_code = int(employee_code) if employee_code.isdigit() else int(datetime.utcnow().timestamp())
                    db.add(
                        Employee(
                            EmployeeName=employee_code,
                            EmployeeCode=employee_code,
                            StringCode=employee_code,
                            NumericCode=numeric_code,
                            Role="Employee",
                        )
                    )
                    db.flush()
                _upsert_employee_photo(
                    db=db,
                    employee_code=employee_code,
                    photo_data=photo_data,
                    device_id=device.DeviceId,
                    photo_mime_type=item.get("PhotoMimeType") or "image/jpeg",
                    source="iclock-cdata",
                )
                log_date = item.get("LogDate") or datetime.utcnow()
                db.add(
                    DeviceLog(
                        DeviceId=device.DeviceId,
                        EmployeeCode=employee_code,
                        LogDate=log_date,
                        VerificationType="P",
                        Direction=None,
                        AttPhoto=photo_data,
                    )
                )
                inserted += 1

        device.LastPing = datetime.utcnow()
        # Route the stamp to the matching column like production does: ATTLOG
        # advances TransactionStamp, OPERLOG advances OpStamp.
        if table_upper == "OPERLOG":
            device.OpStamp = Stamp
        elif table_upper in _TEMPLATE_TABLES or table_upper in {"BIOPHOTO", "USERPIC"}:
            pass   # template and photo tables carry no punch / operation stamp
        else:
            device.TransactionStamp = Stamp
        db.commit()
        detail = f"{inserted} record(s) stored"
        if duplicates:
            detail += f", {duplicates} duplicate(s) skipped"
        detail += f", stamp={Stamp}"
        _log_comm(SN, f"PUSH {table_upper}", detail)
        if clock_warn is not None:
            _log_comm(SN, "WARN clock", f"device sent future time {clock_warn:%Y-%m-%d %H:%M:%S} — check the device's Date/Time setting")

        # Real-time mess tokens: a punch at the mess device auto-issues a token.
        if table_upper == "ATTLOG" and logs_for_webhook:
            try:
                from app.services.mess_service import process_punches_for_mess
                process_punches_for_mess(
                    db, device.DeviceId,
                    [{"EmployeeCode": it.get("EmployeeCode"), "LogDate": it.get("LogDate")} for it in logs_for_webhook],
                )
            except Exception:
                pass

        if settings.webhook_url and logs_for_webhook:
            try:
                post_logs(
                    settings.webhook_url,
                    {
                        "serial_number": SN,
                        "table": table,
                        "stamp": Stamp,
                        "logs": logs_for_webhook,
                    },
                )
            except Exception:
                # Webhook failures should not block device ingestion.
                pass

        # Production eBioServer replies with exactly "OK" — strict firmwares
        # treat anything else as a failed upload and re-send forever, then back
        # off into ErrorDelay (device appears offline). Never append counts.
        return PlainTextResponse("OK")
    finally:
        db.close()


@iclock_router.post("/fdata")
async def fdata(
    request: Request,
    SN: str = Query(...),
    Stamp: str = Query(default="0"),
):
    payload = _decode_push_body(await request.body(), request.headers.get("content-encoding"))
    adms_log.record(SN, "in", "POST fdata", request.url.query, payload)
    db = _get_db()
    try:
        device = _get_or_register_device(db, SN)
        if not device:
            return PlainTextResponse("OK")
        inserted = 0
        for item in parse_photo_lines(payload):
            employee_code = item.get("EmployeeCode")
            photo_data = item.get("PhotoData")
            if not employee_code or not photo_data:
                continue

            employee = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
            if not employee:
                if not_a_staff_pin(db, employee_code):
                    continue   # deleted here or a student: no staff record
                numeric_code = int(employee_code) if employee_code.isdigit() else int(datetime.utcnow().timestamp())
                db.add(
                    Employee(
                        EmployeeName=employee_code,
                        EmployeeCode=employee_code,
                        StringCode=employee_code,
                        NumericCode=numeric_code,
                        Role="Employee",
                    )
                )
                db.flush()

            _upsert_employee_photo(
                db=db,
                employee_code=employee_code,
                photo_data=photo_data,
                device_id=device.DeviceId,
                photo_mime_type=item.get("PhotoMimeType") or "image/jpeg",
                source="iclock-fdata",
            )
            log_date = item.get("LogDate") or datetime.utcnow()
            db.add(
                DeviceLog(
                    DeviceId=device.DeviceId,
                    EmployeeCode=employee_code,
                    LogDate=log_date,
                    VerificationType="P",
                    Direction=None,
                    AttPhoto=photo_data,
                )
            )
            inserted += 1

        device.LastPing = datetime.utcnow()
        device.OpStamp = Stamp
        db.commit()
        return PlainTextResponse("OK")
    finally:
        db.close()


@iclock_router.get("/devicecmd")
def devicecmd(SN: str = Query(...)):
    """Legacy custom pull channel (kept for compatibility); real devices use getrequest."""
    db = _get_db()
    try:
        device = db.query(Device).filter(Device.SerialNumber == SN).first()
        if not device:
            return PlainTextResponse("OK")

        pending = (
            db.query(DeviceCommand)
            .filter(DeviceCommand.DeviceId == device.DeviceId, DeviceCommand.Status == "Pending")
            .order_by(DeviceCommand.DeviceCommandId.asc())
            .first()
        )
        if not pending:
            return PlainTextResponse("OK")
        pending.Status = "Sent"
        pending.SentDate = datetime.utcnow()
        db.commit()
        return PlainTextResponse(pending.DeviceCommand or "OK")
    finally:
        db.close()


@iclock_router.post("/devicecmd")
async def devicecmd_ack(
    request: Request,
    SN: str = Query(...),
    cmd_id: Optional[int] = Query(default=None),
):
    """
    Command acknowledgement. Push-protocol devices POST lines like
    "ID=1040&Return=0&CMD=DATA" (Return < 0 means the command failed).
    The legacy ?cmd_id= query form is still accepted.
    """
    db = _get_db()
    try:
        device = db.query(Device).filter(Device.SerialNumber == SN).first()
        if not device:
            return PlainTextResponse("OK")

        acks: list[tuple[int, int]] = []
        if cmd_id is not None:
            acks.append((cmd_id, 0))

        body = (await request.body()).decode("utf-8", errors="ignore")
        adms_log.record(SN, "in", "POST devicecmd (ack)", request.url.query, body)
        for line in body.splitlines():
            raw_fields = dict(p.split("=", 1) for p in line.strip().split("&") if "=" in p)
            fields = {k.upper(): v for k, v in raw_fields.items()}
            if "ID" in fields:
                try:
                    ack_id = int(fields["ID"])
                    ret = int(fields.get("RETURN", "0") or 0)
                except ValueError:
                    continue
                acks.append((ack_id, ret))

        now = datetime.utcnow()
        for ack_id, ret in acks:
            row = (
                db.query(DeviceCommand)
                .filter(DeviceCommand.DeviceCommandId == ack_id, DeviceCommand.DeviceId == device.DeviceId)
                .first()
            )
            if row:
                row.Status = "Executed" if ret >= 0 else "Failed"
                row.ExecutionDate = now
                if ret < 0:
                    restore_after_failed_delete(db, device, row.DeviceCommand)
        device.LastPing = now
        db.commit()
        return PlainTextResponse("OK")
    finally:
        db.close()


@iclock_router.post("/querydata")
async def querydata(request: Request, SN: str = Query(...)):
    """
    Replies to "DATA QUERY ..." commands. Readers upload the requested table here (not through
    cdata), with the table name, row count and packet number in the query string. Rows use the same
    layout as OPERLOG uploads, so they are imported the same way.
    """
    payload = _decode_push_body(await request.body(), request.headers.get("content-encoding"))
    adms_log.record(SN, "in", "POST querydata", request.url.query, payload)
    db = _get_db()
    try:
        device = _get_or_register_device(db, SN)
        if not device:
            return PlainTextResponse("OK")
        table = (request.query_params.get("tablename") or request.query_params.get("table") or "").strip().upper() or None
        stored = _store_operlog_records(db, device, parse_operlog_lines(payload, default_kind=table))
        device.LastPing = datetime.utcnow()
        db.commit()
        _log_comm(SN, "QUERYDATA", f"{(table or '').lower() or 'table'}: {stored} record(s) stored")
        return PlainTextResponse("OK")
    finally:
        db.close()


@iclock_router.api_route("/{rest:path}", methods=["GET", "POST"])
async def iclock_other(rest: str, request: Request, SN: Optional[str] = Query(default=None)):
    """Anything else a reader calls (e.g. newer-firmware endpoints we do not implement yet): record it so
    it can be seen, and answer OK so the reader does not treat it as a failure."""
    body = ""
    if request.method == "POST":
        body = _decode_push_body(await request.body(), request.headers.get("content-encoding"))
    adms_log.record(SN or "?", "in", f"{request.method} /iclock/{rest}"[:60], request.url.query, body)
    return PlainTextResponse("OK")
