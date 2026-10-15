"""
Pull attendance from a device over the zkemkeeper SDK and store new punches.
Shared by the manual "Fetch from Device" endpoint and the scheduled auto-fetch
script, so both dedupe and insert identically.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import Device, DeviceLog
from app.services.attendance_settings import get_punch_rule
from app.services.device_sdk import _tcp_reachable, read_device_attendance
from app.services.iclock_parser import VERIFY_MODE
from app.services.punch_rules import assign_directions, day_keys, filter_new_punches


def fetch_and_store(db: Session, device: Device, port: int = 4370) -> dict:
    """Pull attendance from one device via SDK and store new (deduped) rows.
    Returns {connected, fetched, inserted, message}."""
    if not device.DeviceIPAddress:
        return {"connected": False, "fetched": 0, "inserted": 0, "message": "Device IP missing"}
    # Remote (push-only) readers cannot be pulled; their punches arrive by Cloud/ADMS push.
    # Skip the slow SDK attempt instead of timing out every 10 minutes in the fetch task.
    if not _tcp_reachable(device.DeviceIPAddress, port, 2.0):
        return {"connected": False, "fetched": 0, "inserted": 0,
                "message": f"not reachable over SDK ({device.DeviceIPAddress}:{port}); punches arrive by push"}

    result = read_device_attendance(device.DeviceIPAddress, port, comm_key=device.CommKey)
    if not result.get("connected"):
        return {
            "connected": False, "fetched": 0, "inserted": 0,
            "message": result.get("message") or "Could not connect over SDK.",
        }

    records = result.get("records") or []
    inserted = 0
    if records:
        existing = set(
            db.query(DeviceLog.EmployeeCode, DeviceLog.LogDate)
            .filter(DeviceLog.DeviceId == device.DeviceId)
            .all()
        )
        seen: set = set()
        to_insert: list[dict] = []
        for rec in records:
            code = str(rec.get("EmployeeCode") or "").strip()[:50]
            log_raw = rec.get("LogDate")
            if not code or not log_raw:
                continue
            try:
                log_dt = datetime.strptime(log_raw, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                continue
            key = (code, log_dt)
            if key in existing or key in seen:
                continue
            seen.add(key)
            inout = rec.get("InOutMode")
            direction = "IN" if inout in (0, None) else ("OUT" if inout == 1 else device.DeviceDirection)
            to_insert.append({
                "DeviceId": device.DeviceId,
                "EmployeeCode": code,
                "LogDate": log_dt,
                "VerificationType": VERIFY_MODE.get(rec.get("VerifyMode")),
                "Direction": direction,
                "WorkCode": (str(rec.get("WorkCode")) if rec.get("WorkCode") else None),
            })
        # Burst filter + IN/OUT numbering shared with the push path (Attendance Rules).
        punch_rule = get_punch_rule(db)
        to_insert = filter_new_punches(db, to_insert, punch_rule)
        if to_insert:
            db.bulk_insert_mappings(DeviceLog, to_insert)
            db.flush()
            assign_directions(db, day_keys(to_insert), punch_rule)
        inserted = len(to_insert)
        device.LastPing = datetime.utcnow()
        db.commit()

    # Auto-generate mess tokens for today's new punches if this is the mess device.
    tokens = 0
    if inserted:
        try:
            from app.services.mess_service import process_punches_for_mess
            tokens = process_punches_for_mess(
                db, device.DeviceId,
                [{"EmployeeCode": r["EmployeeCode"], "LogDate": r["LogDate"]} for r in to_insert],
            )
        except Exception:
            pass

    return {
        "connected": True,
        "fetched": len(records),
        "inserted": inserted,
        "mess_tokens": tokens,
        "message": f"Fetched {len(records)} record(s); {inserted} new stored." + (f" {tokens} mess token(s) generated." if tokens else ""),
    }
