"""HR attendance report endpoints (read from materialized attendance_processed)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.settings import get_organization_settings
from app.core.security import get_current_user
from app.database import get_db
from app.services import report_export, reports as reports_service
from app.services.report_scope import ReportScope, report_scope

router = APIRouter()


def _csv_response(text: str, filename: str) -> Response:
    return Response(content=text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _file_response(report: str, fmt: str, data: dict, base: str, grouped: bool, db: Session) -> Response:
    """csv | xlsx | pdf download; grouped=True inserts Department/Designation sections."""
    fmt = fmt if fmt in report_export.MEDIA_TYPES else "csv"
    body = report_export.render(report, fmt, data, grouped=grouped, org=get_organization_settings(db))
    return Response(content=body, media_type=report_export.MEDIA_TYPES[fmt],
                    headers={"Content-Disposition": f'attachment; filename="{base}.{fmt}"'})


@router.get("/register")
def monthly_register(
    year: int = Query(...),
    month: int = Query(...),
    refresh: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return reports_service.monthly_register(db, year, month, scope, refresh)


@router.get("/daily")
def daily_status_report(
    day: Optional[date] = Query(default=None, alias="date"),
    kind: str = Query(default="all", pattern="^(all|present|absent|leave)$"),
    refresh: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Present / Absent / Leave list for one day, grouped Department -> Designation.
    refresh (default on) reprocesses that one day first so today's punches count."""
    return reports_service.daily_status_report(db, day or date.today(), kind, scope, refresh)


@router.get("/leave-balance")
def leave_balance_report(
    year: Optional[int] = Query(default=None),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return reports_service.leave_balance_report(db, year or datetime.utcnow().year, scope)


@router.get("/late-ot")
def late_ot_report(
    year: int = Query(...),
    month: int = Query(...),
    refresh: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return reports_service.late_ot_report(db, year, month, scope, refresh)


@router.get("/individual")
def individual_sheet(
    employee_code: str = Query(...),
    year: int = Query(...),
    month: int = Query(...),
    refresh: bool = Query(default=True),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return reports_service.individual_sheet(db, employee_code, year, month, refresh)


# ------------------------------------------------------------------ exports

@router.get("/register/export.{fmt}")
def export_register(
    fmt: str,
    year: int = Query(...), month: int = Query(...),
    grouped: bool = Query(default=False),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.monthly_register(db, year, month, scope, refresh=True)
    return _file_response("register", fmt, data, f"register_{year}-{month:02d}", grouped, db)


@router.get("/daily/export.{fmt}")
def export_daily(
    fmt: str,
    day: Optional[date] = Query(default=None, alias="date"),
    kind: str = Query(default="all", pattern="^(all|present|absent|leave)$"),
    grouped: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    d = day or date.today()
    data = reports_service.daily_status_report(db, d, kind, scope, refresh=True)
    return _file_response("daily", fmt, data, f"{kind}_{d.isoformat()}", grouped, db)


@router.get("/leave-balance/export.{fmt}")
def export_leave_balance(
    fmt: str,
    year: Optional[int] = Query(default=None),
    grouped: bool = Query(default=False),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    y = year or datetime.utcnow().year
    data = reports_service.leave_balance_report(db, y, scope)
    return _file_response("leave-balance", fmt, data, f"leave_balance_{y}", grouped, db)


@router.get("/late-ot/export.{fmt}")
def export_late_ot(
    fmt: str,
    year: int = Query(...), month: int = Query(...),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.late_ot_report(db, year, month, scope, refresh=True)
    base = f"late_ot_{year}-{month:02d}"
    if fmt == "pdf":
        return _pdf_response(report_export.late_ot_pdf(data, get_organization_settings(db)), f"{base}.pdf")
    return _csv_response(report_export.late_ot_csv(data), f"{base}.csv")


@router.get("/individual/export.{fmt}")
def export_individual(
    fmt: str,
    employee_code: str = Query(...), year: int = Query(...), month: int = Query(...),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.individual_sheet(db, employee_code, year, month, refresh=True)
    base = f"attendance_{employee_code}_{year}-{month:02d}"
    if fmt == "pdf":
        return _pdf_response(report_export.individual_pdf(data, get_organization_settings(db)), f"{base}.pdf")
    return _csv_response(report_export.individual_csv(data), f"{base}.csv")


# ============================================================ staff formatted reports
# Date-range reports (date-wise / weekly / yearly) grouped Department -> Designation.
# Each: JSON GET /reports/<key> + GET /reports/<key>/export.{fmt}.

@router.get("/muster-time")
def muster_time(
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    refresh: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    return reports_service.muster_time_report(db, from_date, to_date, scope, refresh)


@router.get("/muster-time/export.{fmt}")
def export_muster_time(
    fmt: str,
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    grouped: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.muster_time_report(db, from_date, to_date, scope, refresh=True)
    return _file_response("muster-time", fmt, data, f"attendance_{data['FromDate']}_{data['ToDate']}", grouped, db)


@router.get("/muster-leave")
def muster_leave(
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    refresh: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    return reports_service.muster_time_leave_report(db, from_date, to_date, scope, refresh)


@router.get("/muster-leave/export.{fmt}")
def export_muster_leave(
    fmt: str,
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    grouped: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.muster_time_leave_report(db, from_date, to_date, scope, refresh=True)
    return _file_response("muster-leave", fmt, data, f"attendance_leave_{data['FromDate']}_{data['ToDate']}", grouped, db)


@router.get("/late-arrival")
def late_arrival(
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    refresh: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    return reports_service.late_arrival_report(db, from_date, to_date, scope, refresh)


@router.get("/late-arrival/export.{fmt}")
def export_late_arrival(
    fmt: str,
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    grouped: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.late_arrival_report(db, from_date, to_date, scope, refresh=True)
    return _file_response("late-arrival", fmt, data, f"late_arrival_{data['FromDate']}_{data['ToDate']}", grouped, db)


@router.get("/early-departure")
def early_departure(
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    refresh: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    return reports_service.early_departure_report(db, from_date, to_date, scope, refresh)


@router.get("/early-departure/export.{fmt}")
def export_early_departure(
    fmt: str,
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    grouped: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.early_departure_report(db, from_date, to_date, scope, refresh=True)
    return _file_response("early-departure", fmt, data, f"early_departure_{data['FromDate']}_{data['ToDate']}", grouped, db)


@router.get("/in-out")
def in_out_list(
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    return reports_service.in_out_list_report(db, from_date, to_date, scope)


@router.get("/in-out/export.{fmt}")
def export_in_out(
    fmt: str,
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    grouped: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.in_out_list_report(db, from_date, to_date, scope)
    return _file_response("in-out", fmt, data, f"in_out_{data['FromDate']}_{data['ToDate']}", grouped, db)


@router.get("/employee-list")
def employee_list(
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    return reports_service.employee_list_report(db, scope)


@router.get("/employee-list/export.{fmt}")
def export_employee_list(
    fmt: str,
    grouped: bool = Query(default=True),
    scope: ReportScope = Depends(report_scope),
    db: Session = Depends(get_db), _user=Depends(get_current_user),
):
    data = reports_service.employee_list_report(db, scope)
    return _file_response("employee-list", fmt, data, "employee_list", grouped, db)
