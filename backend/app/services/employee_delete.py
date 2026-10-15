"""
Deleting a person properly, and keeping deleted or student IDs from being re-created by the readers.

A delete used to remove only the employees row, which the database refused whenever anything hung off the
person (a template, a photo, a leave ...), and the page swallowed the error. Even when it worked, the reader
still held the person and its next upload created them again, because every ingest path creates an employee
for any unknown ID. Students on a shared reader turned into staff the same way.

So: `delete_employee` clears everything attached (raw punches are kept for audit), tells the readers to drop
the person, and puts the Face ID on the blocked list; `not_a_staff_pin` is asked by every ingest path before
it creates an employee, and answers "blocked" or "student" when it must not.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    AttendanceProcessed, BlockedPin, Device, DeviceEmployee, Employee, EmployeeBio, EmployeeFaceEmbedding,
    EmployeeLeaveBalance, EmployeePhoto, LeaveRequest, ManualEntry, ShiftRoster, Student, User,
)
from app.services.device_sdk import delete_device_user
from app.services.push_channel import is_push_online, push_delete_user, sdk_reachable


# ------------------------------------------------------------------ who may NOT become an employee

def blocked_pins(db: Session) -> set[str]:
    return {p for (p,) in db.query(BlockedPin.Pin).all()}


def student_codes(db: Session) -> set[str]:
    return {c for (c,) in db.query(Student.StudentCode).all()}


def not_a_staff_pin(db: Session, pin: str, blocked: Optional[set[str]] = None, students: Optional[set[str]] = None) -> Optional[str]:
    """Why a reader's ID must not become an employee: 'blocked' (a person deleted here) or 'student';
    None when a staff record may be created. Pass the two sets when checking many IDs in one go."""
    pin = (pin or "").strip()
    if not pin:
        return None
    if pin in (blocked if blocked is not None else blocked_pins(db)):
        return "blocked"
    if pin in (students if students is not None else student_codes(db)):
        return "student"
    return None


def block_pin(db: Session, pin: str, name: Optional[str], reason: str) -> None:
    if not db.query(BlockedPin).filter(BlockedPin.Pin == pin).first():
        db.add(BlockedPin(Pin=pin, EmployeeName=name, Reason=reason, CreatedAt=datetime.utcnow()))


def unblock_pin(db: Session, pin: str) -> bool:
    """Adding or importing a person with this ID again lifts the block. Returns True when one was lifted."""
    return db.query(BlockedPin).filter(BlockedPin.Pin == (pin or "").strip()).delete(synchronize_session=False) > 0


def list_blocked(db: Session) -> list[dict]:
    return [{"Pin": b.Pin, "EmployeeName": b.EmployeeName, "Reason": b.Reason,
             "CreatedAt": b.CreatedAt.isoformat() if b.CreatedAt else None}
            for b in db.query(BlockedPin).order_by(BlockedPin.CreatedAt.desc()).all()]


# ------------------------------------------------------------------ deleting one person

def _readers_holding(db: Session, employee: Employee) -> list[Device]:
    return (db.query(Device).join(DeviceEmployee, DeviceEmployee.DeviceId == Device.DeviceId)
            .filter(DeviceEmployee.EmployeeId == employee.EmployeeId).all())


def delete_preview(db: Session, employee: Employee) -> dict:
    """What a delete would remove, for the confirmation dialog."""
    code = employee.EmployeeCode
    count = lambda model, col: db.query(model).filter(col == code).count()
    return {
        "EmployeeId": employee.EmployeeId, "EmployeeCode": code, "HrCode": employee.StringCode, "EmployeeName": employee.EmployeeName,
        "templates": count(EmployeeBio, EmployeeBio.EmployeeCode),
        "photos": count(EmployeePhoto, EmployeePhoto.EmployeeCode),
        "face_embeddings": count(EmployeeFaceEmbedding, EmployeeFaceEmbedding.EmployeeCode),
        "rosters": count(ShiftRoster, ShiftRoster.EmployeeCode),
        "leave_requests": count(LeaveRequest, LeaveRequest.EmployeeCode),
        "leave_balances": count(EmployeeLeaveBalance, EmployeeLeaveBalance.EmployeeCode),
        "manual_entries": count(ManualEntry, ManualEntry.EmployeeCode),
        "processed_days": count(AttendanceProcessed, AttendanceProcessed.EmployeeCode),
        "readers": [d.DeviceName for d in _readers_holding(db, employee)],
        "portal_login": db.query(User).filter(User.EmployeeCode == code).first() is not None,
    }


def delete_employee(db: Session, employee: Employee, remove_from_readers: bool = True, block: bool = True) -> dict:
    """Remove the person and everything attached, in one transaction. Raw punches (devicelogs) stay for audit.
    With remove_from_readers, every reader holding the person is told to drop them (push command when the
    reader polls this server, the SDK when it is on the LAN); the Face ID is then blocked so a reader that
    still uploads it cannot create the person again."""
    code = employee.EmployeeCode
    name = employee.EmployeeName
    preview = delete_preview(db, employee)
    reader_notes: list[str] = []
    if remove_from_readers:
        for dev in _readers_holding(db, employee):
            if is_push_online(dev):
                push_delete_user(db, dev, code)      # queues the reader's delete command (and drops the mapping)
                reader_notes.append(f"{dev.DeviceName}: delete queued, the reader removes the person on its next poll")
            elif sdk_reachable(dev):
                r = delete_device_user(dev.DeviceIPAddress, code, comm_key=dev.CommKey)
                reader_notes.append(f"{dev.DeviceName}: " + ("removed over the SDK" if r.get("deleted") or r.get("connected") else f"SDK delete failed: {r.get('message')}"))
            else:
                reader_notes.append(f"{dev.DeviceName}: offline, not removed - delete the user there when it is back")

    for model, col in ((ShiftRoster, ShiftRoster.EmployeeCode), (LeaveRequest, LeaveRequest.EmployeeCode),
                       (EmployeeLeaveBalance, EmployeeLeaveBalance.EmployeeCode), (ManualEntry, ManualEntry.EmployeeCode),
                       (EmployeeBio, EmployeeBio.EmployeeCode), (EmployeePhoto, EmployeePhoto.EmployeeCode),
                       (EmployeeFaceEmbedding, EmployeeFaceEmbedding.EmployeeCode),
                       (AttendanceProcessed, AttendanceProcessed.EmployeeCode)):
        db.query(model).filter(col == code).delete(synchronize_session=False)
    db.query(DeviceEmployee).filter(DeviceEmployee.EmployeeId == employee.EmployeeId).delete(synchronize_session=False)
    db.query(User).filter(User.EmployeeCode == code).update({"EmployeeCode": None}, synchronize_session=False)
    db.delete(employee)
    if block:
        block_pin(db, code, name, "deleted")
    db.commit()

    removed = {k: preview[k] for k in ("templates", "photos", "face_embeddings", "rosters", "leave_requests",
                                       "leave_balances", "manual_entries", "processed_days")}
    parts = [f"{n} {k.replace('_', ' ')}" for k, n in removed.items() if n]
    msg = f"{name or code} deleted" + (f" with {', '.join(parts)}" if parts else "") + ". Punches kept."
    if reader_notes:
        msg += " Readers: " + "; ".join(reader_notes) + "."
    if block:
        msg += f" ID {code} is blocked, so a reader cannot re-create this person."
    return {"deleted": True, "EmployeeCode": code, "removed": removed, "readers": reader_notes, "blocked": block, "message": msg}


# ------------------------------------------------------------------ students that were turned into staff

def student_duplicates(db: Session) -> list[dict]:
    """Employees that are really students (same ID as a student) and look reader-created: name equals the
    ID or no department. Reviewed in a preview before they are deleted."""
    students = {s.StudentCode: s for s in db.query(Student).all()}
    if not students:
        return []
    out = []
    for e in db.query(Employee).filter(Employee.EmployeeCode.in_(list(students))).all():
        auto = (e.EmployeeName or "").strip() == (e.EmployeeCode or "").strip() or not (e.Department or "").strip()
        st = students[e.EmployeeCode]
        out.append({"EmployeeId": e.EmployeeId, "EmployeeCode": e.EmployeeCode, "EmployeeName": e.EmployeeName,
                    "Department": e.Department, "StudentName": st.StudentName, "LooksAutoCreated": auto})
    return sorted(out, key=lambda r: r["EmployeeCode"])


def delete_student_duplicates(db: Session, codes: list[str]) -> dict:
    """Delete the chosen staff records of students. The readers keep the students (their faces must still
    work), and the IDs are not blocked: the student check already stops them being re-created as staff."""
    done, missing = [], []
    for code in codes:
        e = db.query(Employee).filter(Employee.EmployeeCode == code).first()
        if e is None:
            missing.append(code)
            continue
        delete_employee(db, e, remove_from_readers=False, block=False)
        done.append(code)
    return {"deleted": done, "missing": missing, "message": f"{len(done)} student record(s) removed from staff."}
