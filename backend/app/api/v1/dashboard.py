from __future__ import annotations
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import OperationalError, DBAPIError
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.campus_scope import user_org_id
from app.database import get_db
from app.models.entities import Device, DeviceLog, Employee

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        return _build_summary(db, user_org_id(db, user))
    except (OperationalError, DBAPIError, OSError) as exc:
        log.error("Dashboard DB error: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Database connection failed. Please check SQL Server is running and accessible."},
        )


def _build_summary(db: Session, org: Optional[int] = None):
    """org: a campus login's institution - every count covers only its readers, staff and their punches."""
    def dev(q):
        return q.filter(Device.OrganizationId == org) if org is not None else q

    def emp(q):
        return q.filter(Employee.OrganizationId == org) if org is not None else q

    def logs(q):
        if org is None:
            return q
        return q.filter(DeviceLog.EmployeeCode.in_(db.query(Employee.EmployeeCode).filter(Employee.OrganizationId == org)))

    now = datetime.utcnow()
    total_devices = dev(db.query(func.count(Device.DeviceId))).scalar() or 0
    online_threshold = now - timedelta(minutes=5)
    online_devices = dev(db.query(func.count(Device.DeviceId))).filter(Device.LastPing >= online_threshold).scalar() or 0
    # Employees who have left (Inactive / Resigned / Terminated, past their last working day) are not counted.
    total_users = (
        emp(db.query(func.count(Employee.EmployeeId)))
        .filter(or_(
            Employee.CurrentStatus.is_(None),
            Employee.CurrentStatus.notin_(["Inactive", "Resigned", "Terminated"]),
            and_(Employee.LastWorkingDay.isnot(None), Employee.LastWorkingDay >= now.date().isoformat()),
        ))
        .scalar() or 0
    )

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_logs = logs(db.query(func.count(DeviceLog.DeviceLogId))).filter(DeviceLog.LogDate >= today_start).scalar() or 0
    face_logs_today = (
        logs(db.query(func.count(DeviceLog.DeviceLogId)))
        .filter(DeviceLog.LogDate >= today_start)
        .filter(
            or_(
                DeviceLog.AttPhoto.isnot(None),
                func.upper(func.coalesce(DeviceLog.VerificationType, "")).in_(["F", "FR", "FACE", "15"]),
            )
        )
        .scalar()
        or 0
    )

    # Attendance trend for last 7 days (including today).
    trend_start = today_start - timedelta(days=6)
    trend_rows = logs(db.query(DeviceLog.LogDate)).filter(DeviceLog.LogDate >= trend_start).all()
    trend_buckets: dict[str, int] = defaultdict(int)
    for row in trend_rows:
        day_key = row.LogDate.strftime("%Y-%m-%d")
        trend_buckets[day_key] += 1
    attendance_trends = []
    for idx in range(7):
        day = trend_start + timedelta(days=idx)
        day_key = day.strftime("%Y-%m-%d")
        attendance_trends.append(
            {
                "date": day_key,
                "label": day.strftime("%d %b"),
                "count": int(trend_buckets.get(day_key, 0)),
            }
        )

    # Today's device activity (top devices by log count).
    activity_rows = (
        logs(db.query(DeviceLog.DeviceId, func.count(DeviceLog.DeviceLogId).label("count")))
        .filter(DeviceLog.LogDate >= today_start)
        .group_by(DeviceLog.DeviceId)
        .order_by(func.count(DeviceLog.DeviceLogId).desc())
        .limit(8)
        .all()
    )
    device_map = {d.DeviceId: d for d in db.query(Device).all()}
    device_activity = [
        {
            "DeviceId": int(row.DeviceId),
            "DeviceName": (device_map.get(row.DeviceId).DeviceName if device_map.get(row.DeviceId) else f"Device {row.DeviceId}"),
            "count": int(row[1] or 0),
        }
        for row in activity_rows
    ]

    # Recent attendance panel.
    recent_logs = (
        logs(db.query(DeviceLog))
        .order_by(DeviceLog.LogDate.desc())
        .limit(20)
        .all()
    )
    # Face recognition logs panel.
    recent_face_logs = (
        logs(db.query(DeviceLog))
        .filter(
            or_(
                DeviceLog.AttPhoto.isnot(None),
                func.upper(func.coalesce(DeviceLog.VerificationType, "")).in_(["F", "FR", "FACE", "15"]),
            )
        )
        .order_by(DeviceLog.LogDate.desc())
        .limit(12)
        .all()
    )

    # Device alerts panel (offline devices, worst first).
    devices = dev(db.query(Device)).all()
    offline_threshold = now - timedelta(minutes=5)
    alerts = []
    for device in devices:
        is_online = bool(device.LastPing and device.LastPing >= offline_threshold)
        if is_online:
            continue
        if not device.LastPing:
            severity = "critical"
            message = "No heartbeat received yet."
        else:
            down_minutes = int((now - device.LastPing).total_seconds() // 60)
            severity = "critical" if down_minutes >= 30 else "warning"
            message = f"Offline for {down_minutes} min."
        alerts.append(
            {
                "DeviceId": device.DeviceId,
                "DeviceName": device.DeviceName,
                "DeviceIPAddress": device.DeviceIPAddress,
                "LastPing": device.LastPing,
                "severity": severity,
                "message": message,
            }
        )
    alerts.sort(key=lambda x: (0 if x["severity"] == "critical" else 1, x["DeviceName"]))

    # System notifications panel.
    notifications = []
    offline_devices = max(total_devices - online_devices, 0)
    if offline_devices > 0:
        notifications.append(
            {
                "type": "warning",
                "message": f"{offline_devices} device(s) are offline. Check network connectivity.",
            }
        )
    if today_logs == 0:
        notifications.append(
            {
                "type": "warning",
                "message": "No attendance logs recorded today.",
            }
        )
    if face_logs_today == 0:
        notifications.append(
            {
                "type": "info",
                "message": "No face recognition events captured today.",
            }
        )
    if not notifications:
        notifications.append(
            {
                "type": "success",
                "message": "System is healthy. Devices and attendance ingestion look normal.",
            }
        )

    latest_log_at = recent_logs[0].LogDate if recent_logs else None
    latest_ping_at = max((d.LastPing for d in devices if d.LastPing), default=None)

    return {
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": offline_devices,
        "total_users": total_users,
        "today_attendance_count": today_logs,
        "face_logs_today": face_logs_today,
        "attendance_trends": attendance_trends,
        "device_activity": device_activity,
        "live_panel": {
            "latest_log_at": latest_log_at,
            "latest_ping_at": latest_ping_at,
            "recent_attendance_count": len(recent_logs),
        },
        "device_alerts": alerts[:8],
        "system_notifications": notifications,
        "recent_logs": [
            {
                "DeviceLogId": row.DeviceLogId,
                "DeviceId": row.DeviceId,
                "DeviceName": (device_map.get(row.DeviceId).DeviceName if device_map.get(row.DeviceId) else f"Device {row.DeviceId}"),
                "EmployeeCode": row.EmployeeCode,
                "LogDate": row.LogDate,
                "VerificationType": row.VerificationType,
                "Direction": row.Direction,
                "HasPhoto": bool(row.AttPhoto),
            }
            for row in recent_logs
        ],
        "face_recognition_logs": [
            {
                "DeviceLogId": row.DeviceLogId,
                "DeviceId": row.DeviceId,
                "DeviceName": (device_map.get(row.DeviceId).DeviceName if device_map.get(row.DeviceId) else f"Device {row.DeviceId}"),
                "EmployeeCode": row.EmployeeCode,
                "LogDate": row.LogDate,
                "VerificationType": row.VerificationType,
                "HasPhoto": bool(row.AttPhoto),
            }
            for row in recent_face_logs
        ],
    }
