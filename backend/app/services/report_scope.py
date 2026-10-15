"""
The filters every employee report shares, defined ONCE.

A report endpoint takes `scope: ReportScope = Depends(report_scope)` and passes it on; the report services
hand it to `reports._employees()`, the single place filters are applied. To add a filter later:
  1. add a field here (and a Query line in `report_scope`),
  2. add one `if scope.<field> ...: q = q.filter(...)` line in `reports._employees`,
  3. add one dropdown to the frontend `ReportFilters` component.
No endpoint, service signature or API-client method needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Query


@dataclass(frozen=True)
class ReportScope:
    department: Optional[str] = None
    designation: Optional[str] = None        # still accepted by the API; not shown in the UI
    organization_id: Optional[int] = None
    employee_type_id: Optional[int] = None
    school_id: Optional[int] = None          # still accepted by the API; not shown in the UI
    category_id: Optional[int] = None        # attendance category; 0 = employees that have none


def report_scope(
    department: Optional[str] = Query(default=None),
    designation: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None),
    employee_type_id: Optional[int] = Query(default=None),
    school_id: Optional[int] = Query(default=None),
    category_id: Optional[int] = Query(default=None, description="Attendance category id; 0 = employees without one"),
) -> ReportScope:
    return ReportScope(
        department=(department or "").strip() or None,
        designation=(designation or "").strip() or None,
        organization_id=organization_id,
        employee_type_id=employee_type_id,
        school_id=school_id,
        category_id=category_id,
    )
