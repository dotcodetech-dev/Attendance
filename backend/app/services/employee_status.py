"""
Employee exit status: Inactive / Resigned / Terminated, with a Last Working Day.
Shared by attendance (stop counting days), reports (leave out leavers) and login (block access).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Employee, User

EXIT_STATUSES = ("inactive", "resigned", "terminated")


def is_exit_status(employee: Optional[Employee]) -> bool:
    return bool(employee) and (employee.CurrentStatus or "").strip().lower() in EXIT_STATUSES


def exit_cutoff(employee: Optional[Employee]) -> Optional[date]:
    """
    Last day attendance is counted for someone who has left (status Inactive / Resigned /
    Terminated with a Last Working Day). None for active employees, or when no date was given.
    """
    if not is_exit_status(employee):
        return None
    try:
        return date.fromisoformat((employee.LastWorkingDay or "").strip()[:10])
    except ValueError:
        return None


def login_block_reason(db: Session, user: Optional[User], today: Optional[date] = None) -> Optional[str]:
    """
    Why this portal login may not be used, or None if it may.
      - the login is marked Blocked
      - its employee has left: exit status with a last working day before today, or an exit status
        with no date at all (nothing says they are still working)
    The last working day itself is still allowed. Logins not linked to an employee are unaffected.
    """
    if user is None:
        return None
    if (user.Blocked or "").strip().lower() in ("1", "y", "yes", "true", "blocked"):
        return "This login has been blocked. Contact the administrator."
    code = getattr(user, "EmployeeCode", None)
    if not code:
        return None
    employee = db.query(Employee).filter(Employee.EmployeeCode == code).first()
    if not is_exit_status(employee):
        return None
    cutoff = exit_cutoff(employee)
    if cutoff is None or cutoff < (today or date.today()):
        status = (employee.CurrentStatus or "").strip()
        return f"Access has ended: this employee is {status}. Contact the administrator."
    return None
