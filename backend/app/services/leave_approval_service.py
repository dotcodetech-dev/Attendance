"""
Two-step leave approval:  employee applies -> HOD / Manager approves -> Principal / Director approves.

Status of a LeaveRequest:
  Pending      waiting for the HOD / Manager of the employee's department
  HodApproved  waiting for the Principal / Director
  Approved     final; this is the only status that turns days into Leave in attendance
  Rejected     declined at either step (a reason is required)
  Cancelled    undone by an admin (e.g. entered by mistake)

An admin can also enter a leave directly (Leave Entry): it is saved as Approved with no steps.

Who can act is decided by the login's role and the employee it is linked to:
  Manager (HOD)          only leaves of employees in the SAME department as their own employee record
  Principal / Director   the second step, any department
  Admin                  any step (for setup and emergencies)
Nobody can decide their own leave. If a department has no HOD / Manager, or the applicant is the
HOD / Manager, the first step is skipped so a request never gets stuck.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status as http
from sqlalchemy.orm import Session

from app.models.entities import Employee, LeaveApproval, LeaveConfig, LeaveRequest, User
from app.services.employee_status import login_block_reason
from app.services.leave_days import count_leave_days

PENDING = "Pending"
HOD_APPROVED = "HodApproved"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"   # undone by an admin; kept for the record, frees the balance
OPEN_STATUSES = (PENDING, HOD_APPROVED)
RESERVING_STATUSES = (PENDING, HOD_APPROVED, APPROVED)  # count against the balance while undecided

L1_ROLES = {"manager", "hod"}
L2_ROLES = {"principal", "director"}

WAITING_LABEL = {PENDING: "HOD / Manager", HOD_APPROVED: "Principal / Director"}


def role_kind(user: Optional[User]) -> str:
    role = ((user.RoleName if user else "") or "").strip().lower()
    if role == "admin":
        return "admin"
    if role in L1_ROLES:
        return "hod"
    if role in L2_ROLES:
        return "principal"
    return "other"


def _blocked(db: Session, user: User) -> bool:
    return login_block_reason(db, user) is not None


def _employee(db: Session, code: Optional[str]) -> Optional[Employee]:
    if not code:
        return None
    return db.query(Employee).filter(Employee.EmployeeCode == code).first()


def employee_of(db: Session, user: Optional[User]) -> Optional[Employee]:
    return _employee(db, getattr(user, "EmployeeCode", None)) if user else None


def _same_department(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def hod_users_for(db: Session, applicant: Employee) -> list[User]:
    """Active HOD / Manager logins linked to an employee in the applicant's department."""
    out = []
    for u in db.query(User).filter(User.EmployeeCode.isnot(None)).all():
        if role_kind(u) != "hod" or _blocked(db, u) or u.EmployeeCode == applicant.EmployeeCode:
            continue
        emp = _employee(db, u.EmployeeCode)
        if emp and _same_department(emp.Department, applicant.Department):
            out.append(u)
    return out


def initial_status(db: Session, employee_code: str) -> tuple[str, Optional[str]]:
    """Where a new request starts, and why the HOD step was skipped (if it was)."""
    applicant = _employee(db, employee_code)
    if applicant is None:
        return PENDING, None
    own_logins = db.query(User).filter(User.EmployeeCode == employee_code).all()
    if any(role_kind(u) in ("hod", "principal", "admin") for u in own_logins):
        return HOD_APPROVED, "The applicant is a HOD / Manager, so the first step does not apply"
    if not hod_users_for(db, applicant):
        dept = applicant.Department or "no department"
        return HOD_APPROVED, f"No HOD / Manager is set up for {dept}"
    return PENDING, None


def can_act(db: Session, user: User, req: LeaveRequest, applicant: Optional[Employee]) -> tuple[bool, str]:
    if req.Status not in OPEN_STATUSES:
        return False, "This request has already been decided."
    me = employee_of(db, user)
    if me is not None and me.EmployeeCode == req.EmployeeCode:
        return False, "You cannot decide your own leave."
    kind = role_kind(user)
    if kind == "admin":
        return True, ""
    if req.Status == PENDING:
        if kind == "hod" and me is not None and applicant is not None and _same_department(me.Department, applicant.Department):
            return True, ""
        return False, "Waiting for the HOD / Manager of this department."
    if req.Status == HOD_APPROVED:
        if kind == "principal":
            return True, ""
        return False, "Waiting for the Principal / Director."
    return False, ""


def _trail(db: Session, request_id: int) -> list[dict]:
    rows = (
        db.query(LeaveApproval).filter(LeaveApproval.LeaveRequestId == request_id)
        .order_by(LeaveApproval.LeaveApprovalId).all()
    )
    return [
        {"level": r.Level, "action": r.Action, "by": r.ByUser, "role": r.ByRole,
         "remarks": r.Remarks, "at": r.ActionAt.isoformat() + "Z" if r.ActionAt else None}
        for r in rows
    ]


def serialize(db: Session, user: User, req: LeaveRequest) -> dict:
    applicant = _employee(db, req.EmployeeCode)
    config = db.get(LeaveConfig, req.LeaveConfigId)
    days = count_leave_days(db, req.EmployeeCode, config, req.FromDate.date(), req.ToDate.date()).counted
    allowed, why = can_act(db, user, req, applicant)
    return {
        "LeaveRequestId": req.LeaveRequestId,
        "EmployeeCode": req.EmployeeCode,
        "EmployeeName": applicant.EmployeeName if applicant else None,
        "Department": applicant.Department if applicant else None,
        "LeaveCode": config.Code if config else None,
        "LeaveName": config.Name if config else None,
        "FromDate": req.FromDate.date().isoformat(),
        "ToDate": req.ToDate.date().isoformat(),
        "Days": days,
        "Reason": req.Reason,
        "Status": req.Status,
        "WaitingFor": WAITING_LABEL.get(req.Status),
        "AppliedAt": req.AppliedAt.isoformat() + "Z" if req.AppliedAt else None,
        "CanAct": allowed,
        "CantActReason": why if not allowed else "",
        "Trail": _trail(db, req.LeaveRequestId),
    }


def list_requests(db: Session, user: User, tab: str = "waiting") -> list[dict]:
    q = db.query(LeaveRequest)
    if tab in ("waiting", "open"):
        q = q.filter(LeaveRequest.Status.in_(OPEN_STATUSES))
    elif tab == "decided":
        q = q.filter(LeaveRequest.Status.in_((APPROVED, REJECTED)))
    rows = q.order_by(LeaveRequest.AppliedAt.desc(), LeaveRequest.LeaveRequestId.desc()).limit(300).all()
    items = [serialize(db, user, r) for r in rows]
    if tab == "waiting":
        items = [i for i in items if i["CanAct"]]
    return items


def waiting_count(db: Session, user: User) -> int:
    kind = role_kind(user)
    if kind == "other":
        return 0
    return len(list_requests(db, user, "waiting"))


def record(db: Session, request_id: int, level: int, action: str, by: str, role: str, remarks: Optional[str]) -> None:
    db.add(LeaveApproval(LeaveRequestId=request_id, Level=level, Action=action, ByUser=by, ByRole=role,
                         Remarks=remarks, ActionAt=datetime.utcnow()))


def decide(db: Session, user: User, request_id: int, action: str, remarks: Optional[str]) -> dict:
    if action not in (APPROVED, REJECTED):
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "action must be Approved or Rejected")
    req = db.get(LeaveRequest, request_id)
    if req is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Leave request not found")
    applicant = _employee(db, req.EmployeeCode)
    allowed, why = can_act(db, user, req, applicant)
    if not allowed:
        raise HTTPException(http.HTTP_403_FORBIDDEN, why or "You cannot decide this request.")
    remarks = (remarks or "").strip() or None
    if action == REJECTED and not remarks:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "Give a reason when rejecting a leave request.")

    level = 1 if req.Status == PENDING else 2
    kind = role_kind(user)
    role_label = {"admin": "Admin", "hod": "HOD / Manager", "principal": "Principal / Director"}.get(kind, user.RoleName or "")
    if action == REJECTED:
        req.Status = REJECTED
    elif level == 1:
        req.Status = HOD_APPROVED
    else:
        req.Status = APPROVED
    record(db, req.LeaveRequestId, level, action, user.LoginName, role_label, remarks)
    db.commit()

    if req.Status == APPROVED:
        # Approved leave now counts in attendance: refresh those days.
        from app.services.attendance_processing import process_range
        try:
            process_range(db, req.FromDate.date(), req.ToDate.date(), req.EmployeeCode)
        except Exception:  # noqa: BLE001 - the approval itself is already saved
            db.rollback()
    return serialize(db, user, req)


def approvers_overview(db: Session) -> dict:
    """Who can approve, and which departments have no HOD / Manager yet (for the setup card)."""
    def row(u: User):
        emp = _employee(db, u.EmployeeCode)
        return {"LoginName": u.LoginName, "Role": u.RoleName, "EmployeeCode": u.EmployeeCode,
                "EmployeeName": emp.EmployeeName if emp else None, "Department": emp.Department if emp else None,
                "Blocked": _blocked(db, u)}
    users = db.query(User).all()
    hods = [row(u) for u in users if role_kind(u) == "hod"]
    principals = [row(u) for u in users if role_kind(u) == "principal"]
    covered = {h["Department"].strip().lower() for h in hods if h["Department"] and not h["Blocked"]}
    depts = sorted({(e[0] or "").strip() for e in db.query(Employee.Department).all() if (e[0] or "").strip()})
    return {
        "hods": hods,
        "principals": principals,
        "departments_without_hod": [d for d in depts if d.lower() not in covered],
    }
