"""
Attendance export — writes computed daily attendance from `attendance_processed`
to CSV, delivered to a local folder and/or an FTP server. This is Aveon's
equivalent of eTimeTrackLite's WebScheduler CSV/FTP export that feeds payroll.

Uses only the standard library (csv, ftplib) — no extra dependencies.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from ftplib import FTP
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import AttendanceProcessed, Employee

CSV_COLUMNS = [
    "EmployeeCode", "EmployeeName", "Department", "AttendanceDate", "Status",
    "StatusLabel", "ShiftName", "FirstIn", "LastOut", "ActualWorkMinutes",
    "TotalLogs", "Remarks",
]


def _separator() -> str:
    sep = settings.attendance_export_separator or ","
    # Allow "\t" written literally in .env to mean a real tab.
    return "\t" if sep in ("\\t", "tab", "TAB") else sep


def build_attendance_csv(
    db: Session,
    from_date: date,
    to_date: date,
    employee_code: Optional[str] = None,
) -> tuple[str, int]:
    """Build the CSV text for a date range. Returns (csv_text, row_count)."""
    query = (
        db.query(AttendanceProcessed, Employee)
        .outerjoin(Employee, Employee.EmployeeCode == AttendanceProcessed.EmployeeCode)
        .filter(AttendanceProcessed.AttendanceDate >= from_date)
        .filter(AttendanceProcessed.AttendanceDate <= to_date)
    )
    if employee_code:
        query = query.filter(AttendanceProcessed.EmployeeCode == employee_code)
    rows = query.order_by(
        AttendanceProcessed.EmployeeCode, AttendanceProcessed.AttendanceDate
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=_separator(), lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for att, emp in rows:
        writer.writerow([
            att.EmployeeCode,
            (emp.EmployeeName if emp else "") or "",
            (getattr(emp, "Department", None) if emp else "") or "",
            att.AttendanceDate.isoformat(),
            att.Status,
            att.StatusLabel or "",
            att.ShiftName or "",
            att.FirstIn or "",
            att.LastOut or "",
            att.ActualWorkMinutes,
            att.TotalLogs,
            att.Remarks or "",
        ])
    return buffer.getvalue(), len(rows)


def _export_filename(from_date: date, to_date: date) -> str:
    prefix = settings.attendance_export_prefix or "attendance_"
    ext = (settings.attendance_export_extension or "csv").lstrip(".")
    return f"{prefix}{from_date.isoformat()}_{to_date.isoformat()}.{ext}"


def export_attendance(
    db: Session,
    from_date: date,
    to_date: date,
    employee_code: Optional[str] = None,
) -> dict:
    """
    Build the CSV and deliver it per configured targets (folder and/or FTP).
    Returns a report dict; never raises for a delivery failure — each target's
    outcome is reported individually so a nightly run can log partial success.
    """
    csv_text, row_count = build_attendance_csv(db, from_date, to_date, employee_code)
    filename = _export_filename(from_date, to_date)
    report: dict = {
        "filename": filename,
        "rows": row_count,
        "folder_written": None,
        "ftp_uploaded": None,
    }

    folder = settings.attendance_export_folder
    if folder:
        try:
            target_dir = Path(folder)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / filename
            target_path.write_text(csv_text, encoding="utf-8-sig")
            report["folder_written"] = str(target_path)
        except Exception as exc:
            report["folder_written"] = f"ERROR: {exc}"

    if settings.attendance_export_ftp_host:
        try:
            with FTP() as ftp:
                ftp.connect(
                    settings.attendance_export_ftp_host,
                    settings.attendance_export_ftp_port or 21,
                    timeout=30,
                )
                ftp.login(
                    settings.attendance_export_ftp_user or "",
                    settings.attendance_export_ftp_password or "",
                )
                remote_dir = settings.attendance_export_ftp_dir or "/"
                if remote_dir and remote_dir != "/":
                    try:
                        ftp.cwd(remote_dir)
                    except Exception:
                        ftp.mkd(remote_dir)
                        ftp.cwd(remote_dir)
                ftp.storbinary(f"STOR {filename}", io.BytesIO(csv_text.encode("utf-8-sig")))
            report["ftp_uploaded"] = f"{settings.attendance_export_ftp_host}:{remote_dir}/{filename}"
        except Exception as exc:
            report["ftp_uploaded"] = f"ERROR: {exc}"

    return report
