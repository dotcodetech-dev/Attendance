"""
Nightly attendance recalculation — Aveon's equivalent of eTimeTrackLite's
WebScheduler.exe.

Folds raw devicelogs into the materialized `attendance_processed` table for a
rolling window (default: the last 35 days, which covers late-arriving punches
and the current month boundary). Idempotent, so running it repeatedly is safe.

Register it in Windows Task Scheduler to run once a day, e.g.:

    Program:   D:\ESSL\ESSL_SW\Aveon\backend\.venv\Scripts\python.exe
    Arguments: scripts\recalc_attendance.py --days 35
    Start in:  D:\ESSL\ESSL_SW\Aveon\backend

Or process an explicit range / single employee:

    python scripts\recalc_attendance.py --from 2026-07-01 --to 2026-07-31
    python scripts\recalc_attendance.py --days 60 --employee 202413
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

# Allow running from anywhere: put the backend dir on sys.path.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.database import SessionLocal  # noqa: E402
from app.services.attendance_export import export_attendance  # noqa: E402
from app.services.attendance_processing import process_range  # noqa: E402


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Recalculate materialized daily attendance.")
    parser.add_argument("--from", dest="from_date", type=_parse_date, help="YYYY-MM-DD start date")
    parser.add_argument("--to", dest="to_date", type=_parse_date, help="YYYY-MM-DD end date")
    parser.add_argument("--days", type=int, default=35,
                        help="Rolling window size ending today (used when --from/--to omitted)")
    parser.add_argument("--employee", dest="employee_code", default=None,
                        help="Limit to a single employee code")
    parser.add_argument("--export", action="store_true",
                        help="After processing, deliver CSV to the configured folder/FTP targets")
    args = parser.parse_args()

    today = date.today()
    if args.from_date and args.to_date:
        from_date, to_date = args.from_date, args.to_date
    else:
        to_date = today
        from_date = today - timedelta(days=max(1, args.days) - 1)

    if to_date < from_date:
        print(f"ERROR: to_date {to_date} is before from_date {from_date}", file=sys.stderr)
        return 2

    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M:%S}] Recalculating attendance "
          f"{from_date} .. {to_date}"
          + (f" for employee {args.employee_code}" if args.employee_code else " (all employees)"))

    db = SessionLocal()
    try:
        result = process_range(db, from_date, to_date, args.employee_code)
        if args.export:
            report = export_attendance(db, from_date, to_date, args.employee_code)
            print(f"Export: rows={report['rows']} file={report['filename']} "
                  f"folder={report['folder_written']} ftp={report['ftp_uploaded']}")
    except Exception as exc:  # surface failures to Task Scheduler's last-result
        print(f"ERROR: recalculation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    took = (datetime.now() - started).total_seconds()
    print(f"Done in {took:.1f}s — employees={result['employees']} "
          f"days={result['days']} rows_written={result['rows_written']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
