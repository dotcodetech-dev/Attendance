"""
Automatic attendance fetch — pull punches from every reachable device over the
SDK and store new ones. Register in Windows Task Scheduler to run on a short
interval (e.g. every 10 minutes) so attendance flows in WITHOUT the device
needing to push, as long as the server can reach the device on TCP 4370 (LAN/VPN).

    Program:   <backend>\.venv\Scripts\python.exe
    Arguments: scripts\fetch_all_attendance.py
    Start in:  <backend>
    Trigger:   Repeat every 10 minutes

Optionally limit to specific devices:
    python scripts\fetch_all_attendance.py --device-ids 1002 3
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.database import SessionLocal  # noqa: E402
from app.models.entities import Device  # noqa: E402
from app.services.attendance_ingest import fetch_and_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-fetch attendance from all devices via SDK.")
    parser.add_argument("--device-ids", type=int, nargs="*", help="Limit to these DeviceIds")
    parser.add_argument("--port", type=int, default=4370)
    args = parser.parse_args()

    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M:%S}] Auto-fetch attendance starting…")

    db = SessionLocal()
    total_new = 0
    reached = 0
    try:
        q = db.query(Device).filter(Device.DeviceIPAddress.isnot(None))
        if args.device_ids:
            q = q.filter(Device.DeviceId.in_(args.device_ids))
        devices = q.all()
        for d in devices:
            try:
                res = fetch_and_store(db, d, args.port)
            except Exception as exc:
                print(f"  {d.DeviceName} ({d.DeviceIPAddress}): ERROR {exc}")
                continue
            if res.get("connected"):
                reached += 1
                total_new += res.get("inserted", 0)
                print(f"  {d.DeviceName} ({d.DeviceIPAddress}): fetched {res.get('fetched')}, new {res.get('inserted')}")
            else:
                print(f"  {d.DeviceName} ({d.DeviceIPAddress}): unreachable — {res.get('message')}")
    finally:
        db.close()

    took = (datetime.now() - started).total_seconds()
    print(f"Done in {took:.1f}s — devices reached {reached}, new punches stored {total_new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
