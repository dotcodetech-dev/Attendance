"""Bell notifications: things that need an admin's attention right now."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.feature_flags import student_leaves_enabled
from app.core.security import get_current_user
from app.services.campus_scope import devices_query
from app.database import get_db
from app.models.entities import Device, LeaveRequest, ManualEntry, StudentLeaveRequest

router = APIRouter()


def _duration(mins: int) -> str:
    if mins < 60:
        return f"{mins} min"
    if mins < 60 * 24:
        return f"{mins // 60} hr"
    days = mins // (60 * 24)
    return f"{days} day{'' if days == 1 else 's'}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


@router.get("")
def list_notifications(db: Session = Depends(get_db), user=Depends(get_current_user)):
    now = datetime.utcnow()
    items: list[dict] = []

    # Offline devices (same 5-minute heartbeat rule as the dashboard).
    threshold = now - timedelta(minutes=5)
    offline = [d for d in devices_query(db, user).all() if not (d.LastPing and d.LastPing >= threshold)]
    if offline:
        worst = min(offline, key=lambda d: d.LastPing or datetime.min)
        if not worst.LastPing:
            detail = f"{worst.DeviceName} has not sent a heartbeat yet."
            severity = "critical"
        else:
            mins = int((now - worst.LastPing).total_seconds() // 60)
            detail = f"{worst.DeviceName} has been offline for {_duration(mins)}."
            severity = "critical" if mins >= 30 else "warning"
        items.append({
            "id": f"devices:{len(offline)}:{worst.DeviceId}", "kind": "device", "severity": severity,
            "title": f"{_plural(len(offline), 'device')} offline",
            "message": detail + (f" {len(offline) - 1} more." if len(offline) > 1 else ""),
            "link": "/devices", "time": worst.LastPing.isoformat() + "Z" if worst.LastPing else None,
        })

    # Leave requests waiting for THIS person (HOD / Manager, Principal / Director, or Admin).
    from app.services.leave_approval_service import waiting_count
    waiting = waiting_count(db, user)
    if waiting:
        latest = db.query(func.max(LeaveRequest.AppliedAt)).filter(LeaveRequest.Status.in_(["Pending", "HodApproved"])).scalar()
        items.append({
            "id": f"leave-approvals:{waiting}", "kind": "leave", "severity": "info",
            "title": f"{_plural(waiting, 'leave request')} waiting for your approval",
            "message": "Review and approve or reject them.",
            "link": "/ess/leave-approvals", "time": latest.isoformat() + "Z" if latest else None,
        })

    pending_manual = db.query(func.count(ManualEntry.ManualEntryId)).filter(ManualEntry.Status == "Pending").scalar() or 0
    if pending_manual:
        latest = db.query(func.max(ManualEntry.AppliedAt)).filter(ManualEntry.Status == "Pending").scalar()
        items.append({
            "id": f"manual:{pending_manual}", "kind": "manual", "severity": "info",
            "title": f"{_plural(pending_manual, 'manual / OD entry')} pending",
            "message": "Manual punches and on-duty requests need a decision.",
            "link": "/ess/manual-entry", "time": latest.isoformat() + "Z" if latest else None,
        })

    if student_leaves_enabled(db):
        pending_students = (
            db.query(func.count(StudentLeaveRequest.StudentLeaveRequestId))
            .filter(StudentLeaveRequest.Status == "Pending").scalar() or 0
        )
        if pending_students:
            latest = db.query(func.max(StudentLeaveRequest.CreatedAt)).filter(StudentLeaveRequest.Status == "Pending").scalar()
            items.append({
                "id": f"student-leaves:{pending_students}", "kind": "student", "severity": "info",
                "title": f"{_plural(pending_students, 'student leave request')} pending",
                "message": "Review and approve or reject them.",
                "link": "/students/leaves", "time": latest.isoformat() + "Z" if latest else None,
            })

    order = {"critical": 0, "warning": 1, "info": 2}
    items.sort(key=lambda i: order.get(i["severity"], 3))
    return {"count": len(items), "items": items}
