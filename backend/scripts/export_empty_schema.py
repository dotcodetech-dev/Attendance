r"""
Write a single, standalone T-SQL script that creates an EMPTY Aveon database
(all tables, indexes and default master rows, no employee/attendance data).

    .venv\Scripts\python.exe scripts\export_empty_schema.py [--database Aveon] [--out path]

Default output: database\Aveon_EmptyDatabase.sql. Run it in SSMS (or
`sqlcmd -S <server> -i Aveon_EmptyDatabase.sql`) as a sysadmin. It is exactly
what the installer's init_database.py executes, so both paths give identical
schemas. Safe to re-run: every step is guarded with IF NOT EXISTS.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

from app.database import COMPAT_SCHEMA_SQL  # noqa: E402
from app.services.masters_seed import DEFAULT_DEPARTMENTS, DEFAULT_DESIGNATIONS  # noqa: E402

_SCHEMA_SQL = os.path.join(os.path.dirname(_BACKEND_DIR), "database", "schema.sql")
_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", default="Aveon")
    ap.add_argument("--brand", default="Aveon")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(_BACKEND_DIR), "database", "Aveon_EmptyDatabase.sql"))
    a = ap.parse_args()
    db = a.database
    brand = a.brand
    if not re.fullmatch(r"[A-Za-z0-9_]+", db):
        raise SystemExit("database name: letters, digits, _ only")

    with open(_SCHEMA_SQL, encoding="utf-8-sig") as f:
        base = f.read()
    # Drop the master-guard batch and the trailing NOEXEC batch; keep the table batch,
    # and make the DROPs conditional on an empty database so re-running never wipes data.
    batches = [b.strip() for b in _GO.split(base) if b.strip()]
    tables_batch = next(b for b in batches if "CREATE TABLE" in b)
    tables_batch = re.sub(r"^\s*DROP TABLE IF EXISTS .*?;\s*$", "", tables_batch, flags=re.MULTILINE).strip()

    parts = [
        f"-- {brand} empty database script  (generated {date.today().isoformat()})",
        "-- Creates the database and every table with no employee/attendance data.",
        f"-- Run as sysadmin in SSMS or:  sqlcmd -S <server> -i {os.path.basename(a.out)}",
        "-- Safe to re-run: existing tables and data are left untouched.",
        "",
        f"IF DB_ID(N'{db}') IS NULL CREATE DATABASE [{db}];",
        "GO",
        f"USE [{db}];",
        "GO",
        "-- ---------------------------------------------------------------- core tables",
        "IF OBJECT_ID('dbo.devices', 'U') IS NULL",
        "BEGIN",
        "    EXEC(N'" + tables_batch.replace("'", "''") + "');",
        "END",
        "GO",
        "-- ---------------------------------------------------------------- remaining tables / columns",
        COMPAT_SCHEMA_SQL.strip(),
        "GO",
        "-- ---------------------------------------------------------------- default masters",
        "IF NOT EXISTS (SELECT 1 FROM dbo.organizations)",
        "    INSERT INTO dbo.organizations (OrgName, IsActive) VALUES (N'Default', 'Y');",
        "DECLARE @org INT = (SELECT MIN(OrganizationId) FROM dbo.organizations);",
    ]
    for d in DEFAULT_DEPARTMENTS:
        parts.append(f"IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'{d}') "
                     f"INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'{d}', 'Y');")
    for d in DEFAULT_DESIGNATIONS:
        parts.append(f"IF NOT EXISTS (SELECT 1 FROM dbo.designations WHERE DesignationName = N'{d}') "
                     f"INSERT INTO dbo.designations (DesignationName, IsActive) VALUES (N'{d}', 'Y');")
    parts += [
        "-- The web administrator is ADMIN_USERNAME / ADMIN_PASSWORD from backend\\.env; no user row is seeded.",
        "DELETE FROM dbo.users WHERE LoginName = 'admin' AND LoginPassword = 'admin123';",
        "GO",
        "DECLARE @n INT; SELECT @n = COUNT(*) FROM sys.tables;",
        f"PRINT '{brand} database [{db}] ready: ' + CAST(@n AS varchar) + ' tables';",
        "GO",
        "",
    ]
    with open(a.out, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(parts))
    print(f"written {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
