r"""
Repair punches already stored: delete repeated reads inside the duplicate window
(first punch of each burst is kept), re-number IN/OUT (1st punch of the day IN,
2nd OUT, ...), then recalculate attendance for the range.

    .venv\Scripts\python.exe scripts\fix_punches.py --from 2026-09-01 [--to 2026-09-30] [--seconds 60]

Run from the backend folder of the installation (uses backend\.env). Safe to re-run.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

from app.database import SessionLocal  # noqa: E402
from app.services.attendance_processing import process_range  # noqa: E402
from app.services.attendance_settings import get_punch_rule, set_punch_rule  # noqa: E402
from app.services.punch_rules import repair_stored_punches  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_day", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="to_day", type=date.fromisoformat, default=date.today())
    ap.add_argument("--seconds", type=int, default=None, help="also save this duplicate window as the rule")
    ap.add_argument("--no-recalc", action="store_true")
    a = ap.parse_args()
    with SessionLocal() as db:
        if a.seconds is not None:
            set_punch_rule(db, a.seconds, "alternate")
        rule = get_punch_rule(db)
        print(f"rule: duplicate window {rule.duplicate_seconds}s, direction {rule.direction_mode}")
        r = repair_stored_punches(db, a.from_day, a.to_day, rule)
        print(f"{r['punches']} punches in range: {r['duplicates_deleted']} duplicates deleted, "
              f"{r['directions_changed']} directions corrected over {r['employee_days']} employee-days")
        if not a.no_recalc:
            print("recalculating attendance:", process_range(db, a.from_day, a.to_day))
    return 0


if __name__ == "__main__":
    sys.exit(main())
