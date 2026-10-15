"""
Custom roles (User Roles): a role with its own menu switches, for ONE institution (a campus role, e.g. "Campus 2")
or for ALL institutions (e.g. "Leave Section": reports + leave entry only).

A campus role is defined on the User Roles page (e.g. "Campus 2" -> Engineering Campus Staff). It is stored as a
row of `role_config` whose JSON is {"kind": "campus", "organization_id": <id>, "permissions": {...}}; the built-in
Admin / Manager / Employee rows keep their flat {key: bool} JSON. A login whose RoleName is a campus role sees, and
can change, only that institution's employees, devices and reports. Every check lives here so the API stays
consistent: list filters (`employees_query`, `devices_query`) and single-object guards (`check_employee`,
`check_device`, ...). A login without a campus role is unrestricted (None = all institutions).
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Query, Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import Device, Employee, Organization, RoleConfig, User

CAMPUS_KIND = "campus"
BUILT_IN_ROLES = {"admin", "manager", "employee", "principal", "director", "hod"}

# Menu keys a new campus role starts with: Admin's daily work, without the shared configuration
# (shifts, holidays, leave types, roles, masters are used by every campus).
DEFAULT_CAMPUS_PERMISSIONS = {
    "dashboard": True, "devices": True, "employees": True, "enrollment": True, "transfer": True, "commands": True,
    "logs": True, "reports": True, "leave_entry": True,
    "ess_attendance": True, "ess_leaves": True, "ess_manual_entry": True,
}


def _parse(row: RoleConfig) -> Optional[dict]:
    try:
        data = json.loads(row.PermissionsJson or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("kind") != CAMPUS_KIND:
        return None
    perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    org = data.get("organization_id")
    return {"name": row.RoleName, "organization_id": int(org) if isinstance(org, int) or str(org).isdigit() else None,
            "permissions": {k: bool(v) for k, v in perms.items()}}


def list_campus_roles(db: Session) -> list[dict]:
    out = []
    for row in db.query(RoleConfig).all():
        role = _parse(row)
        if role:
            out.append(role)
    return sorted(out, key=lambda r: r["name"].lower())


def campus_role(db: Session, role_name: Optional[str]) -> Optional[dict]:
    name = (role_name or "").strip()
    if not name or name.lower() in BUILT_IN_ROLES:
        return None
    row = db.query(RoleConfig).filter(RoleConfig.RoleName == name).first()
    return _parse(row) if row else None


def save_campus_role(db: Session, name: str, organization_id: Optional[int], permissions: dict[str, bool],
                     original_name: Optional[str] = None) -> dict:
    name = (name or "").strip()
    if not name or len(name) > 50:
        raise HTTPException(400, "Give the role a name (up to 50 characters).")
    if name.lower() in BUILT_IN_ROLES:
        raise HTTPException(400, f'"{name}" is a built-in role name; choose another, e.g. "Campus 2".')
    if organization_id is not None and not db.get(Organization, organization_id):
        raise HTTPException(400, "That institution does not exist.")   # None = all institutions
    existing = db.query(RoleConfig).filter(RoleConfig.RoleName == name).first()
    if existing and (original_name or "").strip() != name:   # a new role, or a rename onto a taken name
        raise HTTPException(400, f'A role called "{name}" already exists.')
    payload = json.dumps({"kind": CAMPUS_KIND, "organization_id": organization_id,
                          "permissions": {k: bool(v) for k, v in (permissions or {}).items()}})
    old = (original_name or "").strip()
    if old and old != name:
        prev = db.query(RoleConfig).filter(RoleConfig.RoleName == old).first()
        if prev is not None and _parse(prev) is not None:
            db.delete(prev)
            db.query(User).filter(User.RoleName == old).update({User.RoleName: name}, synchronize_session=False)
    if existing:
        existing.PermissionsJson = payload
    else:
        db.add(RoleConfig(RoleName=name, PermissionsJson=payload))
    db.commit()
    return campus_role(db, name)


def delete_campus_role(db: Session, name: str) -> None:
    row = db.query(RoleConfig).filter(RoleConfig.RoleName == (name or "").strip()).first()
    if row is None or _parse(row) is None:
        raise HTTPException(404, "Campus role not found")
    in_use = db.query(User.UserId).filter(User.RoleName == row.RoleName).count()
    if in_use:
        raise HTTPException(400, f"{in_use} login(s) still use this role; give them another role first.")
    db.delete(row)
    db.commit()


# --------------------------------------------------------------------------- the limit, per login

def user_org_id(db: Session, user: Optional[User]) -> Optional[int]:
    """The institution this login is limited to, or None for all institutions."""
    role = campus_role(db, getattr(user, "RoleName", None)) if user is not None else None
    return role["organization_id"] if role else None


def employees_query(db: Session, user: Optional[User], q: Optional[Query] = None) -> Query:
    q = q if q is not None else db.query(Employee)
    org = user_org_id(db, user)
    return q.filter(Employee.OrganizationId == org) if org is not None else q


def devices_query(db: Session, user: Optional[User], q: Optional[Query] = None) -> Query:
    q = q if q is not None else db.query(Device)
    org = user_org_id(db, user)
    return q.filter(Device.OrganizationId == org) if org is not None else q


def allowed_employee_codes(db: Session, user: Optional[User]) -> Optional[set[str]]:
    """Face IDs this login may see, or None for everyone."""
    org = user_org_id(db, user)
    if org is None:
        return None
    return {c for (c,) in db.query(Employee.EmployeeCode).filter(Employee.OrganizationId == org)}


def check_employee(db: Session, user: Optional[User], employee: Optional[Employee]) -> None:
    org = user_org_id(db, user)
    if org is not None and (employee is None or employee.OrganizationId != org):
        raise HTTPException(404, "Employee not found")   # other campuses are invisible, not "forbidden"


def check_employee_code(db: Session, user: Optional[User], code: Optional[str]) -> None:
    if user_org_id(db, user) is None or not code:
        return
    emp = (db.query(Employee).filter(Employee.EmployeeCode == code.strip()).first()
           or db.query(Employee).filter(Employee.StringCode == code.strip()).first())
    check_employee(db, user, emp)


def check_employee_id(db: Session, user: Optional[User], employee_id: int) -> None:
    """Same lookup as EmployeeRepository.resolve: the internal id first, then the Face ID (EmployeeCode)."""
    if user_org_id(db, user) is None:
        return
    emp = db.get(Employee, employee_id) or db.query(Employee).filter(Employee.EmployeeCode == str(employee_id)).first()
    check_employee(db, user, emp)


def check_device(db: Session, user: Optional[User], device: Optional[Device]) -> None:
    org = user_org_id(db, user)
    if org is not None and (device is None or device.OrganizationId != org):
        raise HTTPException(404, "Device not found")


def check_device_id(db: Session, user: Optional[User], device_id: Optional[int]) -> None:
    if user_org_id(db, user) is None or device_id is None:
        return
    check_device(db, user, db.get(Device, device_id))


def check_codes(db: Session, user: Optional[User], codes) -> None:
    """Every Face ID / Employee Code in `codes` must belong to the login's institution."""
    allowed = allowed_employee_codes(db, user)
    if allowed is None:
        return
    for code in codes or []:
        if code and str(code).strip() and str(code).strip() not in allowed:
            check_employee_code(db, user, str(code))   # also accepts an HR Employee Code; raises when foreign


def check_transfer(db: Session, user: Optional[User], payload) -> None:
    """A transfer request (source reader, target readers, people) must stay inside the login's institution."""
    if user_org_id(db, user) is None:
        return
    check_device_id(db, user, getattr(payload, "source_device_id", None))
    for did in getattr(payload, "target_device_ids", None) or []:
        check_device_id(db, user, did)
    for eid in getattr(payload, "employee_ids", None) or []:
        check_employee_id(db, user, eid)
    check_codes(db, user, getattr(payload, "employee_codes", None) or [])


def job_visible(db: Session, user: Optional[User], job) -> bool:
    """A transfer job is visible to a campus login when its source and every target reader are its own."""
    org = user_org_id(db, user)
    if org is None:
        return True
    try:
        targets = [int(x) for x in json.loads(job.TargetDeviceIds or "[]")]
    except (json.JSONDecodeError, TypeError, ValueError):
        targets = []
    ids = targets + ([job.SourceDeviceId] if job.SourceDeviceId else [])
    if not ids:
        return False
    mine = {d for (d,) in db.query(Device.DeviceId).filter(Device.DeviceId.in_(ids), Device.OrganizationId == org)}
    return all(i in mine for i in ids)


def check_job(db: Session, user: Optional[User], job) -> None:
    if job is not None and not job_visible(db, user, job):
        raise HTTPException(404, "Transfer job not found")


def is_custom_role(db: Session, user: Optional[User]) -> bool:
    """A login with a custom role (User Roles), whether limited to one institution or not."""
    return user is not None and campus_role(db, getattr(user, "RoleName", None)) is not None


def role_allows(db: Session, user: Optional[User], perm: str) -> bool:
    """True for every built-in role (unchanged behaviour); for a custom role, only when its switch is on."""
    role = campus_role(db, getattr(user, "RoleName", None)) if user is not None else None
    return True if role is None else bool(role["permissions"].get(perm))


def deny_for_campus(db: Session, user: Optional[User], what: str) -> None:
    """Features shared by every institution (or not yet limited per institution) are Admin-only."""
    if is_custom_role(db, user):
        raise HTTPException(403, f"{what} is not available to this role.")


def shared_read_only(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    """Router-level guard for settings shared by every institution (shifts, holidays, leave types, roles, masters,
    students ...): a campus login may read them (dropdowns need them) but not change them."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and is_custom_role(db, user):
        raise HTTPException(403, "These settings are shared by every institution; only an Admin can change them.")


def campus_guard(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    """Router-level guard: for a campus login, any device / employee named in the URL (path or query) must belong
    to its institution. List endpoints and request bodies are filtered/checked in the endpoints themselves."""
    if user_org_id(db, user) is None:
        return
    params = {**request.query_params, **request.path_params}
    for key in ("device_id", "source_device_id"):
        val = params.get(key)
        if val not in (None, "") and str(val).isdigit():
            check_device_id(db, user, int(val))
    val = params.get("employee_id")
    if val not in (None, "") and str(val).isdigit():
        check_employee_id(db, user, int(val))
    for key in ("employee_code", "code", "face_id"):
        val = params.get(key)
        if val not in (None, ""):
            check_employee_code(db, user, str(val))
