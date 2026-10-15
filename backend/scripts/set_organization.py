r"""
Set the organisation name shown in the sidebar and on report headers.

    .venv\Scripts\python.exe scripts\set_organization.py --name "Some College" [--address ...] [--force]

Used by the installer when the package was built with -Organization. Without
--force it only fills in a name that is still the default (blank / brand name),
so a name the client already changed under Configuration -> Organization is kept.
"""
from __future__ import annotations

import argparse
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.entities import MasterSetting, Organization  # noqa: E402

DEFAULTS = {"", "aveon", "aveon infotech", "default", settings.brand_name.lower()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--address", default=None)
    ap.add_argument("--force", action="store_true", help="overwrite even if the client changed it")
    a = ap.parse_args()
    name = " ".join(a.name.split())

    with SessionLocal() as db:
        row = db.query(MasterSetting).filter(MasterSetting.Name == "OrgName").first()
        current = (row.Value or "").strip() if row else ""
        if current.lower() in DEFAULTS or a.force:
            if row is None:
                db.add(MasterSetting(Name="OrgName", Value=name))
            else:
                row.Value = name
            print(f"OrgName set to: {name}")
        else:
            print(f"OrgName kept (client value): {current}")

        if a.address is not None:
            arow = db.query(MasterSetting).filter(MasterSetting.Name == "OrgAddress").first()
            if arow is None:
                db.add(MasterSetting(Name="OrgAddress", Value=a.address))
            elif not (arow.Value or "").strip() or a.force:
                arow.Value = a.address

        # Organisation master (departments hang off it): rename the seeded placeholder.
        org = db.query(Organization).order_by(Organization.OrganizationId).first()
        if org is None:
            db.add(Organization(OrgName=name, IsActive="Y"))
            print("organizations: created")
        elif (org.OrgName or "").strip().lower() in DEFAULTS or a.force:
            org.OrgName = name
            print(f"organizations: renamed to {name}")
        db.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
