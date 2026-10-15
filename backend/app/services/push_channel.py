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

# A polling reader touches LastPing every second (Delay=1). One window for everything: the Devices card's
# Online/Offline and the choice of channel, so a reader shown Online is never sent down the SDK path.
PUSH_ONLINE_SECONDS = 300
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


def is_ai_reader(device: Device) -> bool:
    """AI-face (push-protocol 2.x) reader: answers on TCP 4370 but refuses the SDK login, so push is its only channel."""
    return (device.DeviceType or "").strip().upper() == "AI"


def reader_channel(device: Device, port: int = 4370) -> str:
    """The channel for the Users panel actions (list, refresh, delete, send names, photo):
    'push' (answer from / queue for the push channel), 'sdk' (talk to the reader directly) or 'offline'.
    An AI reader that has ever polled is always 'push': a quiet spell only delays delivery of queued commands,
    and trying the SDK on it can only fail."""
    if is_ai_reader(device):
        return "push" if device.LastPing is not None else "offline"
    if is_push_online(device):
        return "push"
    return "sdk" if sdk_reachable(device, port) else "offline"


def last_polled_text(device: Device) -> str:
    """'12 s ago' / '6 min ago' / '3 h ago' / 'never' - for messages and the Users panel."""
    age = push_age_seconds(device)
    if age is None:
        return "never"
    if age < 90:
        return f"{int(age)} s ago"
    if age < 5400:
        return f"{int(age // 60)} min ago"
    if age < 172800:
        return f"{int(age // 3600)} h ago"
    return f"{int(age // 86400)} days ago"


def queued_note(device: Device) -> str:
    """Suffix for a queued action: when the reader will act on it."""
    if is_push_online(device):
        return "the reader picks it up on its next poll (a few seconds)."
    return (f"the reader last polled {last_polled_text(device)}, so it applies this when it next connects. "
            f"If it stays quiet, check its network and its Cloud Server / ADMS setting.")


def push_reader_status(db: Session, device: Device) -> dict:
    """What the server knows about a push reader, to explain an empty or short user list."""
    users_on_record = db.query(DeviceEmployee.DeviceEmployeeId).filter(DeviceEmployee.DeviceId == device.DeviceId).count()
    punchers = (db.query(DeviceLog.EmployeeCode).filter(DeviceLog.DeviceId == device.DeviceId)
                .distinct().count())
    last_refresh = (db.query(DeviceCommand)
                    .filter(DeviceCommand.DeviceId == device.DeviceId, DeviceCommand.Title == "Refresh users from device")
                    .order_by(DeviceCommand.DeviceCommandId.desc()).first())
    age = push_age_seconds(device)
    return {
        "ai_reader": is_ai_reader(device),
        "channel": reader_channel(device) if is_ai_reader(device) or is_push_online(device) else "sdk-or-offline",
        "polling": is_push_online(device),
        "last_poll_seconds": None if age is None else int(age),
        "last_poll_text": last_polled_text(device),
        "users_on_record": users_on_record,
        "people_who_punched": punchers,
        "last_refresh": None if last_refresh is None else {
            "status": last_refresh.Status,
            "queued_utc": last_refresh.CreationDate.isoformat() if last_refresh.CreationDate else None,
        },
    }


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


PRI_ADMIN = "14"   # eSSL / ZK privilege of a device administrator (0 = normal user)
ROLE_DEVICE_ADMIN = "Admin"
ROLE_DEVICE_USER = "User"


def note_user_on_device(db: Session, device: Device, employee: Employee, status: str = "OnDevice",
                        privilege: Optional[str] = None) -> None:
    """Remember that this reader has this user (filled from OPERLOG USER pushes), and, when the upload says, whether
    they are an administrator on it - so re-sending the user (e.g. a new name) never takes their admin rights away."""
    row = (db.query(DeviceEmployee)
           .filter(DeviceEmployee.DeviceId == device.DeviceId, DeviceEmployee.EmployeeId == employee.EmployeeId)
           .first())
    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    role = None
    if privilege is not None and str(privilege).strip() != "":
        role = ROLE_DEVICE_ADMIN if str(privilege).strip() == PRI_ADMIN else ROLE_DEVICE_USER
    if row is None:
        db.add(DeviceEmployee(DeviceId=device.DeviceId, EmployeeId=employee.EmployeeId, Status=status, SyncDate=stamp,
                              Role=role))
    else:
        row.Status = status
        row.SyncDate = stamp
        if role:
            row.Role = role


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
    # People deleted from this reader are left out even though they once punched here; if the reader re-uploads
    # them (re-enrolled) they come back through the map above, and a delete the reader rejects does not count.
    punched = {c for (c,) in db.query(DeviceLog.EmployeeCode).filter(DeviceLog.DeviceId == device.DeviceId).distinct().all()}
    extra_codes = punched - set(seen) - deleted_codes(db, device)
    if extra_codes:
        for emp in db.query(Employee).filter(Employee.EmployeeCode.in_(list(extra_codes))).all():
            seen[emp.EmployeeCode] = {"EmployeeCode": emp.EmployeeCode, "EmployeeName": emp.EmployeeName,
                                      "Role": emp.Role, "Enabled": True, "Source": "push", "SyncDate": None}
    return sorted(seen.values(), key=lambda u: (u["EmployeeName"] or "", u["EmployeeCode"]))


SYNC_USER_PREFIX = "SYNC USER "


def has_real_name(employee: Employee) -> bool:
    name = (employee.EmployeeName or "").strip()
    return bool(name) and name != (employee.EmployeeCode or "").strip()


def _queue_name(db: Session, device_id: int, code: str, now: datetime) -> bool:
    """Queue one SYNC USER (sent as DATA USER with the server's name), unless one is already waiting."""
    waiting = (db.query(DeviceCommand.DeviceCommandId)
               .filter(DeviceCommand.DeviceId == device_id, DeviceCommand.DeviceCommand == f"{SYNC_USER_PREFIX}{code}",
                       DeviceCommand.Status.in_(("Pending", "Sent")))
               .first())
    if waiting:
        return False
    db.add(DeviceCommand(DeviceId=device_id, Title=f"Send name {code}", DeviceCommand=f"{SYNC_USER_PREFIX}{code}",
                         Status="Pending", Type="push", CreationDate=now))
    return True


def send_names_to_reader(db: Session, device: Device) -> dict:
    """Send the server's names of everyone on this reader. Only people whose privilege on the reader is known
    (learnt from its user upload - Refresh from device) are sent, so no device administrator is ever demoted."""
    now = datetime.utcnow()
    on_reader = (db.query(Employee, DeviceEmployee)
                 .join(DeviceEmployee, DeviceEmployee.EmployeeId == Employee.EmployeeId)
                 .filter(DeviceEmployee.DeviceId == device.DeviceId).all())
    gone = deleted_codes(db, device)
    out = {"queued": 0, "already_waiting": 0, "no_name": 0, "unknown_privilege": 0}
    for emp, link in on_reader:
        if emp.EmployeeCode in gone:
            continue
        if not has_real_name(emp):
            out["no_name"] += 1
        elif link.Role not in (ROLE_DEVICE_ADMIN, ROLE_DEVICE_USER):
            out["unknown_privilege"] += 1
        elif _queue_name(db, device.DeviceId, emp.EmployeeCode, now):
            out["queued"] += 1
        else:
            out["already_waiting"] += 1
    db.commit()
    return out


def queue_name_change(db: Session, employee: Employee) -> int:
    """A person was renamed on the server: send the new name to every push reader they are on (same privilege rule
    as send_names_to_reader). The caller commits. Returns how many readers were queued."""
    if not has_real_name(employee):
        return 0
    now = datetime.utcnow()
    n = 0
    for device, link in (db.query(Device, DeviceEmployee)
                         .join(DeviceEmployee, DeviceEmployee.DeviceId == Device.DeviceId)
                         .filter(DeviceEmployee.EmployeeId == employee.EmployeeId,
                                 Device.LastPing.isnot(None)).all()):   # readers that poll us (push channel)
        if link.Role in (ROLE_DEVICE_ADMIN, ROLE_DEVICE_USER) and employee.EmployeeCode not in deleted_codes(db, device):
            n += _queue_name(db, device.DeviceId, employee.EmployeeCode, now)
    return n


DELETE_USER_PREFIX = "DELETE USER "


def push_delete_user(db: Session, device: Device, employee_code: str) -> int:
    """Queue the delete for the reader (sent as DATA DELETE USERINFO / DATA DEL_USER by its protocol) and forget
    the mapping locally. If the reader rejects the command, restore_after_failed_delete() puts the mapping back."""
    emp = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
    if emp:
        db.query(DeviceEmployee).filter(DeviceEmployee.DeviceId == device.DeviceId,
                                        DeviceEmployee.EmployeeId == emp.EmployeeId).delete()
    return queue_commands(db, device, [f"{DELETE_USER_PREFIX}{employee_code}"], f"Delete user {employee_code}")


def deleted_codes(db: Session, device: Device) -> set[str]:
    """Codes with a delete queued, sent or done on this reader (a Failed one - rejected by the reader - does not count)."""
    rows = (db.query(DeviceCommand.DeviceCommand)
            .filter(DeviceCommand.DeviceId == device.DeviceId,
                    DeviceCommand.DeviceCommand.like(f"{DELETE_USER_PREFIX}%"),
                    DeviceCommand.Status != "Failed")
            .all())
    return {text[len(DELETE_USER_PREFIX):].strip() for (text,) in rows if text}


def restore_after_failed_delete(db: Session, device: Device, command_text: Optional[str]) -> None:
    """The reader rejected a delete: the person is still on it, so put them back on its user list."""
    text = (command_text or "").strip()
    if not text.upper().startswith(DELETE_USER_PREFIX):
        return
    emp = db.query(Employee).filter(Employee.EmployeeCode == text[len(DELETE_USER_PREFIX):].strip()).first()
    if emp:
        note_user_on_device(db, device, emp)


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
