"""Business logic for shift rosters (3-tier: Application tier)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import Employee, Shift, ShiftRoster
from app.repositories.roster_repository import RosterRepository
from app.schemas.roster import RosterAssign, RosterCreate, RosterUpdate

_DAY = timedelta(days=1)


def _midnight(value: datetime) -> datetime:
    return datetime.combine(value.date(), time.min)


def current_shift_map(db: Session, codes: List[str]) -> Dict[str, dict]:
    """EmployeeCode -> {ShiftId, ShiftName, Source} that applies today: the roster row covering
    today (latest start wins if rows ever overlap), else the default shift, else nothing."""
    out: Dict[str, dict] = {}
    if not codes:
        return out
    names = {s.ShiftId: s.ShiftName for s in db.query(Shift).all()}
    default = db.query(Shift).filter(Shift.IsDefault == "Y").first()
    today = datetime.combine(date.today(), time.min)
    rows = (
        db.query(ShiftRoster)
        .filter(ShiftRoster.EmployeeCode.in_(codes), ShiftRoster.FromDate <= today)
        .order_by(ShiftRoster.FromDate.asc())
        .all()
    )
    for r in rows:
        if r.ToDate is None or r.ToDate >= today:
            out[r.EmployeeCode] = {"ShiftId": r.ShiftId, "ShiftName": names.get(r.ShiftId, ""), "Source": "roster"}
    if default is not None:
        for c in codes:
            out.setdefault(c, {"ShiftId": default.ShiftId, "ShiftName": default.ShiftName, "Source": "default"})
    return out


class RosterService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = RosterRepository(session)

    def list_all(self, employee_code: Optional[str] = None) -> List[ShiftRoster]:
        return self._repo.list_all(employee_code)

    # ---- helpers -------------------------------------------------------------------------
    def _make_room(self, code: str, start: datetime, end: Optional[datetime], exclude_id: Optional[int] = None) -> None:
        """Trim / split / drop this employee's other roster rows so [start, end] belongs only to
        the new entry. Overlapping rows used to resolve in database order (non-deterministic);
        this keeps history intact and the ranges disjoint. The caller commits."""
        q = self._session.query(ShiftRoster).filter(ShiftRoster.EmployeeCode == code)
        if exclude_id is not None:
            q = q.filter(ShiftRoster.ShiftRosterId != exclude_id)
        for r in q.all():
            r_end = r.ToDate
            overlaps = (r_end is None or r_end >= start) and (end is None or r.FromDate <= end)
            if not overlaps:
                continue
            starts_before = r.FromDate < start
            ends_after = end is not None and (r_end is None or r_end > end)
            if starts_before and ends_after:
                # The new entry lands in the middle of an older one: keep both sides.
                self._session.add(ShiftRoster(EmployeeCode=code, ShiftId=r.ShiftId, FromDate=end + _DAY, ToDate=r_end))
                r.ToDate = start - _DAY
            elif starts_before:
                r.ToDate = start - _DAY
            elif ends_after:
                r.FromDate = end + _DAY
            else:
                self._session.delete(r)

    def _recompute(self, code: str, start: datetime, end: Optional[datetime]) -> None:
        """Refresh stored attendance for the changed days. The roster change is already saved,
        so a failure here must not undo it (the scheduled recalculation will catch up)."""
        from app.services.attendance_processing import process_range

        first = start.date()
        last = min(end.date() if end else date.today(), date.today())
        if first > last:
            return
        try:
            process_range(self._session, first, last, code)
        except Exception:  # noqa: BLE001
            self._session.rollback()

    def _check_shift(self, shift_id: int) -> None:
        if not self._session.get(Shift, shift_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Shift not found")

    @staticmethod
    def _check_range(start: datetime, end: Optional[datetime]) -> None:
        if end is not None and end < start:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The end date cannot be before the start date.")

    # ---- CRUD ----------------------------------------------------------------------------
    def create(self, payload: RosterCreate) -> ShiftRoster:
        self._check_shift(payload.ShiftId)
        start = _midnight(payload.FromDate)
        end = _midnight(payload.ToDate) if payload.ToDate else None
        self._check_range(start, end)
        self._make_room(payload.EmployeeCode, start, end)
        row = self._repo.add(ShiftRoster(EmployeeCode=payload.EmployeeCode, ShiftId=payload.ShiftId, FromDate=start, ToDate=end))
        self._recompute(row.EmployeeCode, start, end)
        return row

    def update(self, roster_id: int, payload: RosterUpdate) -> ShiftRoster:
        row = self._repo.get_by_id(roster_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Roster entry not found",
            )
        old_start, old_end = row.FromDate, row.ToDate
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        self._check_shift(row.ShiftId)
        row.FromDate = _midnight(row.FromDate)
        row.ToDate = _midnight(row.ToDate) if row.ToDate else None
        self._check_range(row.FromDate, row.ToDate)
        self._make_room(row.EmployeeCode, row.FromDate, row.ToDate, exclude_id=row.ShiftRosterId)
        row = self._repo.update(row)
        open_ended = old_end is None or row.ToDate is None
        self._recompute(row.EmployeeCode, min(old_start, row.FromDate), None if open_ended else max(old_end, row.ToDate))
        return row

    def delete(self, roster_id: int) -> dict[str, bool]:
        row = self._repo.get_by_id(roster_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Roster entry not found",
            )
        code, start, end = row.EmployeeCode, row.FromDate, row.ToDate
        self._repo.delete(row)
        self._recompute(code, start, end)
        return {"deleted": True}

    # ---- bulk ----------------------------------------------------------------------------
    def assign(self, payload: RosterAssign) -> dict:
        """Give a shift to one or many employees from a date (optionally until another).
        Their earlier assignments are ended the day before, so history is kept."""
        self._check_shift(payload.ShiftId)
        start = _midnight(payload.FromDate)
        end = _midnight(payload.ToDate) if payload.ToDate else None
        self._check_range(start, end)
        codes = list(dict.fromkeys(c.strip() for c in payload.EmployeeCodes if c and c.strip()))
        if not codes:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick at least one employee.")
        known = {c for (c,) in self._session.query(Employee.EmployeeCode).filter(Employee.EmployeeCode.in_(codes)).all()}
        for code in codes:
            if code not in known:
                continue
            self._make_room(code, start, end)
            self._session.add(ShiftRoster(EmployeeCode=code, ShiftId=payload.ShiftId, FromDate=start, ToDate=end))
        self._session.commit()
        for code in codes:
            if code in known:
                self._recompute(code, start, end)
        return {"assigned": len(known), "skipped": [c for c in codes if c not in known]}
