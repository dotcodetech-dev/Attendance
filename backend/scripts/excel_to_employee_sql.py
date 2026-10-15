r"""
Turn an employee Excel sheet into ONE T-SQL script that (optionally) wipes the
employee data and re-imports everything. Run the output in SSMS on the client.

    .venv\Scripts\python.exe scripts\excel_to_employee_sql.py "C:\path\Employee details.xlsx" --out Employees.sql

Expected columns (header row 1, matched case-insensitively, order does not matter):
  Employee No | Face ID | Employee Name | D.O.B | D.O.J | Company | Unit | Department
  | Sub-Location (= employee type) | <designation> | <flag> | <status>
The last three columns have no header in the client's sheet, so they are taken
by position (columns 11, 12, 13).

Mapping (why): devices push punches with their user ID, and the backend matches
them on employees.EmployeeCode - so EmployeeCode = Face ID. Employee No goes to
StringCode (the ERP/HR code), which is shown alongside the name.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime

import openpyxl

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

DEPENDENT_TABLES = [  # employee-linked rows removed by the clear step (order matters for FKs)
    "deviceemployees", "employeesbio", "employeephotos", "employeefaceembeddings",
    "employee_leave_balances", "shiftrosters", "attendance_processed", "leaverequests",
    "manualentries", "mess_tokens",
]


def q(v) -> str:
    """SQL literal: N'...' with quotes doubled, NULL for empty."""
    if v is None:
        return "NULL"
    s = str(v).strip()
    if s == "" or s.upper() in ("NA", "N/A", "NONE", "NULL"):
        return "NULL"
    return "N'" + s.replace("'", "''") + "'"


def d(v) -> str:
    if isinstance(v, (datetime, date)):
        return f"'{v:%Y-%m-%d}'"
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return f"'{datetime.strptime(s[:10], fmt):%Y-%m-%d}'"
        except ValueError:
            pass
    return "NULL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sheet", default=None)
    args = ap.parse_args()
    out = args.out or os.path.splitext(args.xlsx)[0] + "_import.sql"

    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    ws = wb[args.sheet] if args.sheet else wb.active
    rows = [r for r in ws.iter_rows(values_only=True)]
    header = [str(c or "").strip().lower() for c in rows[0]]

    def col(*names, pos=None):
        for n in names:
            if n.lower() in header:
                return header.index(n.lower())
        return pos

    c_no, c_face, c_name = col("employee no", "employee code"), col("face id", "device id"), col("employee name", "name")
    c_dob, c_doj = col("d.o.b", "dob", "date of birth"), col("d.o.j", "doj", "joining date", "date of joining")
    c_unit, c_dept = col("unit", "school"), col("department")
    c_type, c_desig, c_status = col("sub-location", "employee type", pos=9), col("designation", pos=10), col("status", pos=12)
    missing = [n for n, c in [("Employee No", c_no), ("Face ID", c_face), ("Employee Name", c_name)] if c is None]
    if missing:
        raise SystemExit(f"columns not found in sheet: {missing}")

    emps, types, depts, desigs, seen_codes, problems = [], [], [], [], set(), []
    for i, r in enumerate(rows[1:], start=2):
        if not any(c not in (None, "") for c in r):
            continue
        face = str(r[c_face] or "").strip()
        name = str(r[c_name] or "").strip()
        emp_no = str(r[c_no] or "").strip()
        if not face or not name:
            problems.append(f"row {i}: missing Face ID or name - skipped")
            continue
        if face in seen_codes:
            problems.append(f"row {i}: duplicate Face ID {face} - skipped")
            continue
        seen_codes.add(face)
        def clean(idx):
            if idx is None or idx >= len(r):
                return ""
            v = str(r[idx] or "").strip()
            return "" if v.upper() in ("NA", "N/A", "NONE", "NULL", "-") else v
        etype, dept, desig = clean(c_type), clean(c_dept), clean(c_desig)
        status = str(r[c_status] or "Active").strip() if c_status is not None and c_status < len(r) else "Active"
        if etype and etype not in types: types.append(etype)
        if dept and dept not in depts: depts.append(dept)
        if desig and desig not in desigs: desigs.append(desig)
        numeric = int(face) if face.isdigit() and int(face) < 2_000_000_000 else 900_000_000 + i
        emps.append(dict(face=face, emp_no=emp_no or face, name=name, dob=r[c_dob] if c_dob is not None else None,
                         doj=r[c_doj] if c_doj is not None else None, unit=r[c_unit] if c_unit is not None else None,
                         dept=dept, desig=desig, etype=etype, status=status or "Active", numeric=numeric))

    L = []
    w = L.append
    w(f"-- Employee import generated {datetime.now():%Y-%m-%d %H:%M} from {os.path.basename(args.xlsx)}")
    w(f"-- {len(emps)} employees, {len(depts)} departments, {len(desigs)} designations, {len(types)} employee types.")
    w("--")
    w("-- HOW TO RUN: in SSMS select the attendance database in the toolbar dropdown")
    w("-- (or uncomment the USE line), then Execute. Runs as ONE transaction: all or nothing.")
    w("--")
    w("-- Employees whose Face ID is in the sheet are UPDATED in place: their device users,")
    w("-- fingerprint/face templates, photos and punch logs are all KEPT.")
    w("-- @RemoveOthers = 1  deletes employees that are NOT in the sheet (e.g. rows from a wrong")
    w("--   earlier import) together with their linked rows. 0 = keep them.")
    w("-- @WipeAll = 1       old behaviour: delete EVERY employee and all linked rows first. Default 0.")
    w("-- @ClearPunchLogs = 1  also deletes raw device punch logs (devicelogs). Default 0 = keep.")
    w("-- USE [Dotcode];")
    w("SET NOCOUNT ON; SET XACT_ABORT ON;")
    w("IF DB_NAME() = 'master' BEGIN RAISERROR('Select the attendance database first (not master).', 16, 1); RETURN; END")
    w("IF OBJECT_ID('dbo.employees','U') IS NULL BEGIN RAISERROR('This database has no employees table.', 16, 1); RETURN; END")
    w("DECLARE @RemoveOthers BIT = 1;")
    w("DECLARE @WipeAll BIT = 0;")
    w("DECLARE @ClearPunchLogs BIT = 0;")
    w("BEGIN TRANSACTION;")
    w("IF @ClearPunchLogs = 1 DELETE FROM dbo.devicelogs;")
    w("")
    w("-- ---------------------------------------------------------------- 1. masters")
    w("DECLARE @org INT = (SELECT MIN(OrganizationId) FROM dbo.organizations);")
    w("IF @org IS NULL BEGIN INSERT INTO dbo.organizations (OrgName, IsActive) VALUES (N'Default', 'Y'); SET @org = SCOPE_IDENTITY(); END")
    w("DECLARE @cat INT = (SELECT MIN(CategoryId) FROM dbo.attendance_categories);")
    for t in types:
        w(f"IF NOT EXISTS (SELECT 1 FROM dbo.employee_types WHERE TypeName = {q(t)}) INSERT INTO dbo.employee_types (TypeName, IsActive) VALUES ({q(t)}, 'Y');")
    for t in depts:
        w(f"IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = {q(t)}) INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, {q(t)}, 'Y');")
    for t in desigs:
        w(f"IF NOT EXISTS (SELECT 1 FROM dbo.designations WHERE DesignationName = {q(t)}) INSERT INTO dbo.designations (DesignationName, IsActive) VALUES ({q(t)}, 'Y');")
    w("")
    w("-- ---------------------------------------------------------------- 2. sheet rows")
    w("-- EmployeeCode = Face ID (device user ID, what punches are matched on); StringCode = Employee No.")
    w("DECLARE @in TABLE (Face NVARCHAR(50), EmpNo NVARCHAR(50), Name NVARCHAR(250), DOB NVARCHAR(10), DOJ NVARCHAR(10),")
    w("                   Unit NVARCHAR(200), Dept NVARCHAR(150), Desig NVARCHAR(120), EType NVARCHAR(100), Status NVARCHAR(20), Numeric INT);")
    for k in range(0, len(emps), 100):
        w("INSERT INTO @in (Face, EmpNo, Name, DOB, DOJ, Unit, Dept, Desig, EType, Status, Numeric) VALUES")
        vals = []
        for e in emps[k:k + 100]:
            vals.append(f"  ({q(e['face'])}, {q(e['emp_no'])}, {q(e['name'])}, {d(e['dob'])}, {d(e['doj'])}, {q(e['unit'])}, "
                        f"{q(e['dept'])}, {q(e['desig'])}, {q(e['etype'])}, {q(e['status'])}, {e['numeric']})")
        w(",\n".join(vals) + ";")
    w("")
    w("-- ---------------------------------------------------------------- 3. remove employees not in the sheet")
    w("DECLARE @gone TABLE (EmployeeId INT, EmployeeCode NVARCHAR(250));")
    w("INSERT INTO @gone SELECT e.EmployeeId, e.EmployeeCode FROM dbo.employees e")
    w("WHERE @WipeAll = 1 OR (@RemoveOthers = 1 AND NOT EXISTS (SELECT 1 FROM @in i WHERE i.Face = e.EmployeeCode));")
    for t in DEPENDENT_TABLES:
        key = "EmployeeId" if t == "deviceemployees" else "EmployeeCode"
        w(f"IF OBJECT_ID('dbo.{t}','U') IS NOT NULL DELETE FROM dbo.{t} WHERE {key} IN (SELECT {key} FROM @gone);")
    w("IF COL_LENGTH('dbo.users','EmployeeCode') IS NOT NULL DELETE FROM dbo.users WHERE EmployeeCode IN (SELECT EmployeeCode FROM @gone);")
    w("DELETE FROM dbo.employees WHERE EmployeeId IN (SELECT EmployeeId FROM @gone);")
    w("DECLARE @removed INT = (SELECT COUNT(*) FROM @gone);")
    w("")
    w("-- ---------------------------------------------------------------- 4. upsert: update matching Face IDs in place, insert the rest")
    w("UPDATE e SET e.EmployeeName = i.Name, e.StringCode = i.EmpNo, e.NumericCode = i.Numeric, e.Department = LEFT(i.Dept, 50),")
    w("    e.Designation = i.Desig, e.JoiningDate = i.DOJ, e.DateOfBirth = i.DOB, e.Location = i.Unit, e.CurrentStatus = i.Status,")
    w("    e.OrganizationId = @org, e.EmployeeTypeId = t.EmployeeTypeId")
    w("FROM dbo.employees e JOIN @in i ON e.EmployeeCode = i.Face LEFT JOIN dbo.employee_types t ON t.TypeName = i.EType;")
    w("INSERT INTO dbo.employees (EmployeeName, EmployeeCode, StringCode, NumericCode, Role, Department, Designation, JoiningDate,")
    w("    DateOfBirth, Location, CurrentStatus, OrganizationId, EmployeeTypeId, CategoryId)")
    w("SELECT i.Name, i.Face, i.EmpNo, i.Numeric, N'Employee', LEFT(i.Dept, 50), i.Desig, i.DOJ, i.DOB, i.Unit, i.Status, @org, t.EmployeeTypeId, @cat")
    w("FROM @in i LEFT JOIN dbo.employee_types t ON t.TypeName = i.EType")
    w("WHERE NOT EXISTS (SELECT 1 FROM dbo.employees e WHERE e.EmployeeCode = i.Face);")
    w("")
    w("COMMIT TRANSACTION;")
    w("DECLARE @n INT; SELECT @n = COUNT(*) FROM dbo.employees;")
    w("PRINT 'Done: ' + CAST(@n AS varchar) + ' employees now in the database (' + CAST(@removed AS varchar) + ' not in the sheet were removed). Device users, templates and photos of matched employees were kept.';")
    w("")
    with open(out, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(L))
    print(f"written {out}: {len(emps)} employees, {len(depts)} departments, {len(desigs)} designations, {len(types)} types")
    for p in problems:
        print("  WARNING", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
