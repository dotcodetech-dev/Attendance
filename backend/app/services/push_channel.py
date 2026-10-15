"""
Push-protocol (Cloud/ADMS) channel for readers the server cannot reach directly.

LAN readers can be driven over the eSSL SDK (server -> reader, TCP 4370). Remote
readers (other site, NAT, WAN) can only be reached the way eBioServer /
eTimeTrackLite do it: the reader polls /iclock/getrequest every few seconds and
the server hands it commands; the reader answers by POSTing to /iclock/cdata
(OPERLOG for users / templates / photos). This module decides which channel a
device is on and implements the push-side equivalents of the SDK features.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Device, DeviceCommand, DeviceEmployee, DeviceLog, Employee, EmployeeBio, MasterSetting
from app.services.device_sdk import _tcp_reachable

PUSH_ONLINE_SECONDS = 180      # a polling reader touches LastPing every few seconds
SDK_PROBE_SECONDS = 2.0        # fast TCP probe before we commit to a 30 s SDK attempt

# Commands that make an eSSL/ZK push reader upload everything it knows about its
# users (answered via OPERLOG USER / FP / FACE / BIOPHOTO lines).
# Older firmwares answer the short table names; push-protocol 2.x readers (AI-face, pushver=2.x in the
# handshake) keep visible-light faces and fingerprints in the BIODATA table and only answer the
# tablename= form (replies arrive on /iclock/querydata). Both forms are sent; a reader ignores the
# ones it does not know.
USER_REFRESH_COMMANDS = [
    "CHECK",
    "DATA QUERY USERINFO", "DATA QUERY FINGERTMP", "DATA QUERY FACE",
    "DATA QUERY tablename=user,fielddesc=*,filter=*",
    "DATA QUERY tablename=biodata,fielddesc=*,filter=*",
]


def push_age_seconds(device: Device) -> Optional[float]:
    if not device.LastPing:
        return None
    return (datetime.utcnow() - device.LastPing).total_seconds()


def is_push_online(device: Device) -> bool:
    age = push_age_seconds(device)
    return age is not None and age <= PUSH_ONLINE_SECONDS


def sdk_reachable(device: Device, port: int = 4370) -> bool:
    """True when the server can open TCP to the reader - i.e. the SDK path is possible."""
    return bool(device.DeviceIPAddress) and _tcp_reachable(device.DeviceIPAddress, port, SDK_PROBE_SECONDS)


def channel_for(device: Device, port: int = 4370) -> str:
    """'sdk' when the reader is directly reachable, 'push' when it is only polling us, else 'offline'."""
    if sdk_reachable(device, port):
        return "sdk"
    if is_push_online(device):
        return "push"
    return "offline"


def queue_commands(db: Session, device: Device, commands: list[str], title: str) -> int:
    now = datetime.utcnow()
    for text in commands:
        db.add(DeviceCommand(DeviceId=device.DeviceId, Title=title, DeviceCommand=text,
                             Status="Pending", Type="push", CreationDate=now))
    db.commit()
    return len(commands)


def queue_user_refresh(db: Session, device: Device) -> int:
    """Ask the reader to re-send all its users and templates (arrives via OPERLOG)."""
    return queue_commands(db, device, USER_REFRESH_COMMANDS, "Refresh users from device")


def note_user_on_device(db: Session, device: Device, employee: Employee, status: str = "OnDevice") -> None:
    """Remember that this reader has this user (filled from OPERLOG USER pushes)."""
    row = (db.query(DeviceEmployee)
           .filter(DeviceEmployee.DeviceId == device.DeviceId, DeviceEmployee.EmployeeId == employee.EmployeeId)
           .first())
    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    if row is None:
        db.add(DeviceEmployee(DeviceId=device.DeviceId, EmployeeId=employee.EmployeeId, Status=status, SyncDate=stamp))
    else:
        row.Status = status
        row.SyncDate = stamp


def push_users(db: Session, device: Device) -> list[dict]:
    """Users known to be on the reader, from what it has pushed to us: the device<->employee
    map (OPERLOG USER), plus anyone whose template was pushed or who has punched on it."""
    seen: dict[str, dict] = {}

    for emp, de in (db.query(Employee, DeviceEmployee)
                    .join(DeviceEmployee, DeviceEmployee.EmployeeId == Employee.EmployeeId)
                    .filter(DeviceEmployee.DeviceId == device.DeviceId).all()):
        seen[emp.EmployeeCode] = {"EmployeeCode": emp.EmployeeCode, "EmployeeName": emp.EmployeeName,
                                  "Role": de.Role or emp.Role, "Enabled": True, "Source": "push", "SyncDate": de.SyncDate}

    # Template uploads now record the reader in the device<->employee map, so only people who punched here are added.
    # (Previously anyone with a template stored for ANY reader was listed on every reader.)
    punched = {c for (c,) in db.query(DeviceLog.EmployeeCode).filter(DeviceLog.DeviceId == device.DeviceId).distinct().all()}
    extra_codes = punched - set(seen)
    if extra_codes:
        for emp in db.query(Employee).filter(Employee.EmployeeCode.in_(list(extra_codes))).all():
            seen[emp.EmployeeCode] = {"EmployeeCode": emp.EmployeeCode, "EmployeeName": emp.EmployeeName,
                                      "Role": emp.Role, "Enabled": True, "Source": "push", "SyncDate": None}
    return sorted(seen.values(), key=lambda u: (u["EmployeeName"] or "", u["EmployeeCode"]))


def push_delete_user(db: Session, device: Device, employee_code: str) -> int:
    """Queue DATA DEL_USER for the reader and forget the mapping locally."""
    emp = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
    if emp:
        db.query(DeviceEmployee).filter(DeviceEmployee.DeviceId == device.DeviceId,
                                        DeviceEmployee.EmployeeId == emp.EmployeeId).delete()
    return queue_commands(db, device, [f"DELETE USER {employee_code}"], f"Delete user {employee_code}")


# ---------------------------------------------------------------------------
# Auto-sync: keep every reader a person is on up to date (eBioServer behaviour).
#
# eBioServer marks the employee "Pending" on every assigned reader whenever one
# reader uploads a new user / template / photo, so an enrolment made on reader A
# reaches readers B and C on their next poll without anyone pressing Transfer.
# eTimeTrackLite does the same for a master reader's slave list. Here it is a
# switch (Transfer page) because it changes what readers hold without an admin
# action; off by default.
# ---------------------------------------------------------------------------
AUTO_SYNC_KEY = "AutoSyncTemplates"          # Y / N in mastersettings
AUTO_SYNC_DEDUPE_HOURS = 24                  # same data sent to the same reader within this window is not re-queued


def auto_sync_enabled(db: Session) -> bool:
    row = db.query(MasterSetting).filter(MasterSetting.Name == AUTO_SYNC_KEY).first()
    return bool(row and (row.Value or "").strip().upper() == "Y")


def set_auto_sync(db: Session, enabled: bool) -> None:
    row = db.query(MasterSetting).filter(MasterSetting.Name == AUTO_SYNC_KEY).first()
    if row is None:
        row = MasterSetting(Name=AUTO_SYNC_KEY)
        db.add(row)
    row.Value = "Y" if enabled else "N"


def propagate_template(db: Session, source_device: Device, employee: Employee, kind: str, payload: str,
                       finger_template: Optional[str] = None) -> int:
    """
    Queue the data one reader just uploaded for every OTHER reader that holds this person
    (a deviceemployees row). kind: FACE (payload = template), FINGER (finger_template = the
    template), BIOPHOTO (payload = base64 jpg the reader enrolled from), PROFILE (payload = user
    picture). Returns how many commands were queued. No-op unless auto-sync is switched on.
    """
    if not auto_sync_enabled(db):
        return 0
    code = employee.EmployeeCode
    if kind == "FACE":
        text, title, face = f"ENROLL FACE {code}", "Auto-sync Face", payload
    elif kind == "FINGER":
        text, title, face = f"ENROLL FP {code} {finger_template or payload}", "Auto-sync Finger", None
    elif kind == "BIOPHOTO":
        text, title, face = f"ENROLL BIOPHOTO {code}", "Auto-sync Face photo", payload
    elif kind == "PROFILE":
        text, title, face = f"ENROLL PHOTO {code}", "Auto-sync Photo", payload
    else:
        return 0

    targets = (db.query(Device)
               .join(DeviceEmployee, DeviceEmployee.DeviceId == Device.DeviceId)
               .filter(DeviceEmployee.EmployeeId == employee.EmployeeId,
                       Device.DeviceId != source_device.DeviceId)
               .all())
    now = datetime.utcnow()
    since = now - timedelta(hours=AUTO_SYNC_DEDUPE_HOURS)
    queued = 0
    for dev in targets:
        if (dev.DeviceType or "").strip().lower() == "camera" or not (dev.SerialNumber or "").strip():
            continue
        # Do not queue what is already waiting for, or was recently sent to, this reader: a reader
        # that re-uploads data the server just wrote must not bounce it back and forth.
        recent = (db.query(DeviceCommand)
                  .filter(DeviceCommand.DeviceId == dev.DeviceId, DeviceCommand.Title == title,
                          DeviceCommand.CreationDate >= since)
                  .order_by(DeviceCommand.DeviceCommandId.desc()).limit(20).all())
        duplicate = any(
            (c.DeviceCommand or "") == text and (c.DeviceCommandFace or "") == (face or "")
            and (c.Status in ("Pending", "Sent") or (c.Status == "Executed"))
            for c in recent
        )
        if duplicate:
            continue
        db.add(DeviceCommand(DeviceId=dev.DeviceId, Title=title, DeviceCommand=text, DeviceCommandFace=face,
                             Status="Pending", Type="autosync", CreationDate=now))
        queued += 1
    return queued


def push_status_message(device: Device) -> str:
    age = push_age_seconds(device)
    when = "just now" if age is not None and age < 15 else (f"{int(age)} s ago" if age is not None else "never")
    return (f"Online via Cloud/ADMS push (last poll {when}). The SDK port 4370 is not reachable from this "
            f"server (remote/NAT device) - users, transfer and deletes go through the push channel instead.")
