r"""
Safe, idempotent database setup for a fresh or existing Aveon install.

Used by the one-click client installer (deployment/installer/install.ps1), but
safe to run by hand at any time:

    cd <install>\backend
    .venv\Scripts\python.exe scripts\init_database.py            # create / upgrade
    .venv\Scripts\python.exe scripts\init_database.py --check    # report only

Steps (connection settings come from backend\.env):
  1. CREATE DATABASE if it does not exist (connects to master).
  2. Run database\schema.sql ONLY when the database has no user tables at all.
     schema.sql DROPs tables, so it is never run against a populated database.
  3. ensure_compat_schema() - the same self-heal the backend runs on startup.
  4. create_all() for any ORM table still missing (e.g. holidays, shiftrosters).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

# Allow running from anywhere: put the backend dir on sys.path and make .env resolve.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

import pyodbc  # noqa: E402

from app.config import settings  # noqa: E402

_DEFAULT_SCHEMA = os.path.join(os.path.dirname(_BACKEND_DIR), "database", "schema.sql")
_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)


def _connect(database: str, retries: int = 10) -> pyodbc.Connection:
    server = settings.sqlserver_server or f"{settings.sqlserver_host},{settings.sqlserver_port}"
    conn_str = (
        f"DRIVER={{{settings.sqlserver_driver}}};SERVER={server};DATABASE={database};"
        f"UID={settings.sqlserver_user};PWD={settings.sqlserver_password};"
        f"TrustServerCertificate=yes;Encrypt={settings.sqlserver_encrypt};"
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return pyodbc.connect(conn_str, autocommit=True, timeout=10)
        except pyodbc.Error as exc:  # SQL service may still be starting right after install
            last_error = exc
            if exc.args and str(exc.args[0]) == "28000":  # login failed: retrying cannot help
                break
            print(f"  SQL connect attempt {attempt}/{retries} failed, retrying...")
            time.sleep(3)
    raise SystemExit(f"ERROR: cannot connect to SQL Server '{server}': {last_error}")


def _user_tables(conn: pyodbc.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sys.tables WHERE is_ms_shipped = 0").fetchall()
    return {row[0].lower() for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create / upgrade the Aveon database safely.")
    parser.add_argument("--check", action="store_true", help="report what would happen, change nothing")
    parser.add_argument("--schema", default=_DEFAULT_SCHEMA, help="path to database\\schema.sql")
    args = parser.parse_args()

    db_name = settings.sqlserver_database
    if not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
        raise SystemExit(f"ERROR: unsupported database name '{db_name}' (letters, digits, _ only)")

    master = _connect("master")
    exists = master.execute("SELECT 1 FROM sys.databases WHERE name = ?", db_name).fetchone() is not None
    if not exists:
        if args.check:
            print(f"[check] database '{db_name}' missing -> would CREATE it and run schema.sql")
            return 0
        print(f"Creating database '{db_name}'...")
        master.execute(f"CREATE DATABASE [{db_name}]")
    else:
        print(f"Database '{db_name}' exists.")
    master.close()

    conn = _connect(db_name)
    tables = _user_tables(conn)
    if not tables:
        if args.check:
            print("[check] database is empty -> would run schema.sql")
            return 0
        print(f"Empty database - running {args.schema}...")
        with open(args.schema, encoding="utf-8-sig") as handle:
            batches = [b.strip() for b in _GO.split(handle.read()) if b.strip()]
        for batch in batches:
            conn.execute(batch)
        print(f"  schema.sql applied ({len(batches)} batches).")
    elif "devices" not in tables:
        raise SystemExit(
            f"ERROR: '{db_name}' has tables but no 'devices' table - it does not look like an "
            "Aveon database. Choose another database name in backend\\.env."
        )
    else:
        print(f"  {len(tables)} tables present - schema.sql skipped (never re-run on data).")
    conn.close()

    if args.check:
        print("[check] would run ensure_compat_schema() + create_all() for missing tables")
        return 0

    from app.database import Base, ensure_compat_schema, get_engine
    import app.models.entities  # noqa: F401  (registers every ORM table on Base.metadata)

    print("Applying compatibility schema...")
    ensure_compat_schema()
    Base.metadata.create_all(get_engine(), checkfirst=True)

    # Older schema.sql versions seeded a plain-text 'admin'/'admin123' row. The real
    # administrator is ADMIN_USERNAME/ADMIN_PASSWORD in .env, so that row is only a
    # permanent default-password backdoor - remove it wherever it still exists.
    conn = _connect(db_name)
    removed = conn.execute(
        "DELETE FROM dbo.users WHERE LoginName = 'admin' AND LoginPassword = 'admin123'"
    ).rowcount
    if removed:
        print(f"  removed {removed} default 'admin'/'admin123' login row.")

    # Default departments / designations so department-wise reports work out of the box.
    from app.database import SessionLocal
    from app.services.masters_seed import seed_default_masters
    with SessionLocal() as session:
        added = seed_default_masters(session)
    for kind, names in added.items():
        if names:
            print(f"  seeded {kind}: {', '.join(names)}")

    final = _user_tables(conn)
    print(f"Database ready: {len(final)} tables.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
