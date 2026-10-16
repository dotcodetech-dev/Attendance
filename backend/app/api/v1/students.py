"""Student master data (department + year wise) and student face enrollment."""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.feature_flags import require_student_module, student_module_enabled
from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import DepartmentMaster, Employee, MasterSetting, Student

router = APIRouter()
gated = [Depends(require_student_module)]


class StudentIn(BaseModel):
    StudentCode: str = Field(min_length=1, max_length=50)
    StudentName: str = Field(min_length=1, max_length=250)
    DepartmentId: int
    RegisteredYear: Optional[str] = Field(default=None, max_length=20)  # admission session, e.g. "Jan 2026"
    Batch: Optional[str] = Field(default=None, max_length=20)           # admission year, e.g. "2026"
    Category: Optional[str] = Field(default=None, max_length=20)        # Full Time | Part Time (configurable)
    SchoolId: Optional[int] = None                                     # Org & Masters -> School
    YearOfStudy: Optional[int] = Field(default=1, ge=1, le=4)           # legacy; no longer collected in the UI
    Section: Optional[str] = None
    RollNo: Optional[str] = None
    GuardianName: Optional[str] = None  # retired from the UI, still accepted for back-compat
    GuardianPhone: Optional[str] = None
    DateOfBirth: Optional[str] = None   # surfaced in the UI as "Registered Date"
    StudentShiftId: Optional[int] = None
    IsActive: str = "Y"


class ImportIn(BaseModel):
    rows: List[StudentIn]


def _dto(s: Student, dept_names: dict[int, str], school_names: dict[int, str] | None = None) -> dict:
    return {
        "StudentId": s.StudentId, "StudentCode": s.StudentCode, "StudentName": s.StudentName,
        "DepartmentId": s.DepartmentId, "DepartmentName": dept_names.get(s.DepartmentId, ""),
        "RegisteredYear": s.RegisteredYear, "Batch": s.Batch, "Category": s.Category,
        "SchoolId": s.SchoolId, "SchoolName": (school_names or {}).get(s.SchoolId, "") if s.SchoolId else "",
        "YearOfStudy": s.YearOfStudy, "Section": s.Section, "RollNo": s.RollNo,
        "GuardianName": s.GuardianName, "GuardianPhone": s.GuardianPhone,
        "DateOfBirth": s.DateOfBirth, "StudentShiftId": s.StudentShiftId, "IsActive": s.IsActive,
        "Status": s.Status or "Active", "StatusDate": s.StatusDate, "StatusNote": s.StatusNote,
    }


def _school_names(db: Session) -> dict[int, str]:
    from app.models.entities import School
    return {s.SchoolId: s.SchoolName for s in db.query(School).all()}


def _default_shift_id(db: Session) -> Optional[int]:
    """The single active student shift (req: shift is fixed, not chosen per student)."""
    from app.models.entities import StudentShift
    row = (db.query(StudentShift.StudentShiftId)
           .filter(StudentShift.IsActive == "Y")
           .order_by(StudentShift.StudentShiftId).first())
    return row[0] if row else None


def _dept_names(db: Session) -> dict[int, str]:
    return {d.DepartmentId: d.DepartmentName for d in db.query(DepartmentMaster).all()}


_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _reg_year_key(label: str) -> tuple:
    """Sort key for registered-year session labels like 'Jan 2026'; unknown/'—' sort last."""
    parts = (label or "").split()
    if len(parts) == 2 and parts[1].isdigit() and parts[0][:3].lower() in _MONTHS:
        return (0, int(parts[1]), _MONTHS[parts[0][:3].lower()])
    return (1, 0, 0)


def _sort_reg_years(years) -> list[str]:
    return sorted(years, key=lambda y: (_reg_year_key(y), y))


def _code_taken(db: Session, code: str, exclude_student_id: Optional[int] = None) -> bool:
    q = db.query(Student.StudentId).filter(Student.StudentCode == code)
    if exclude_student_id:
        q = q.filter(Student.StudentId != exclude_student_id)
    if q.first():
        return True
    return db.query(Employee.EmployeeId).filter(Employee.EmployeeCode == code).first() is not None


def _validate_dept(db: Session, department_id: int) -> None:
    if not db.query(DepartmentMaster.DepartmentId).filter(DepartmentMaster.DepartmentId == department_id).first():
        raise HTTPException(400, "Unknown department")


@router.get("/module-status")
def module_status(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Ungated: the UI uses this to show/hide the Students menu."""
    return {"enabled": student_module_enabled(db)}


@router.get("", dependencies=gated)
def list_students(
    department_id: Optional[int] = None,
    year: Optional[int] = Query(default=None, ge=1, le=4),
    registered_year: Optional[str] = None,
    batch: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    include_inactive: bool = False,
    status: Optional[str] = Query(default=None, description="active | discontinued | completed | archived | all"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    query = db.query(Student)
    mode = (status or "").lower()
    if mode == "discontinued":
        query = query.filter(Student.Status == "Discontinued")
    elif mode == "completed":
        query = query.filter(Student.Status == "Completed")
    elif mode == "archived":
        query = query.filter(Student.Status.in_(("Discontinued", "Completed")))
    elif mode == "all" or include_inactive:
        pass
    else:
        query = query.filter(Student.IsActive == "Y")
    if department_id:
        query = query.filter(Student.DepartmentId == department_id)
    if year:
        query = query.filter(Student.YearOfStudy == year)
    if registered_year:
        query = query.filter(Student.RegisteredYear == registered_year)
    if batch:
        query = query.filter(Student.Batch == batch)
    if category:
        query = query.filter(Student.Category == category)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Student.StudentName.like(like)) | (Student.StudentCode.like(like)) | (Student.RollNo.like(like)))
    names = _dept_names(db)
    schools = _school_names(db)
    rows = query.order_by(Student.DepartmentId, Student.RegisteredYear, Student.StudentName).all()
    return [_dto(s, names, schools) for s in rows]


@router.get("/summary", dependencies=gated)
def summary(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Active student counts by department x registered year (dynamic columns)."""
    names = _dept_names(db)
    rows = (
        db.query(Student.DepartmentId, Student.RegisteredYear, func.count(Student.StudentId))
        .filter(Student.IsActive == "Y")
        .group_by(Student.DepartmentId, Student.RegisteredYear)
        .all()
    )
    years: set[str] = set()
    by_dept: dict[int, dict] = {}
    for dept_id, ry, n in rows:
        label = ry or "—"
        years.add(label)
        d = by_dept.setdefault(dept_id, {"DepartmentId": dept_id, "DepartmentName": names.get(dept_id, ""),
                                         "years": {}, "total": 0})
        d["years"][label] = d["years"].get(label, 0) + n
        d["total"] += n
    return {
        "years": _sort_reg_years(years),
        "departments": sorted(by_dept.values(), key=lambda d: d["DepartmentName"]),
    }


@router.post("", dependencies=gated)
def create_student(payload: StudentIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    payload.StudentCode = payload.StudentCode.strip()
    _validate_dept(db, payload.DepartmentId)
    if _code_taken(db, payload.StudentCode):
        raise HTTPException(409, "Code already used by a student or employee")
    data = payload.model_dump()
    data["StudentShiftId"] = _default_shift_id(db)  # shift is fixed to the active student shift, not chosen
    s = Student(**data)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _dto(s, _dept_names(db))


@router.put("/{student_id}", dependencies=gated)
def update_student(student_id: int, payload: StudentIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    s = db.get(Student, student_id)
    if not s:
        raise HTTPException(404, "Student not found")
    payload.StudentCode = payload.StudentCode.strip()
    if payload.StudentCode != s.StudentCode:
        raise HTTPException(400, "Student code cannot be changed (it links punches and face data)")
    _validate_dept(db, payload.DepartmentId)
    for k, v in payload.model_dump().items():
        if k == "StudentShiftId":
            continue  # shift is fixed to the active student shift, not editable
        if k in ("GuardianName", "GuardianPhone") and v is None:
            continue  # retired from the UI; keep any existing value instead of clearing it
        setattr(s, k, v)
    s.StudentShiftId = _default_shift_id(db)
    if (s.Status or "Active") != "Active":
        s.IsActive = "N"  # editing details must not bring an archived student back
    db.commit()
    return _dto(s, _dept_names(db))


@router.delete("/{student_id}", dependencies=gated)
def deactivate_student(student_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Soft delete — keeps attendance history."""
    s = db.get(Student, student_id)
    if not s:
        raise HTTPException(404, "Student not found")
    s.IsActive = "N"
    db.commit()
    return {"ok": True}


# ---- lifecycle: discontinue / complete (archive) / restore / yearly promotion ----
LAST_PROMOTION_KEY = "StudentLastPromotion"
PROMOTION_LOCK_DAYS = 180


class StatusIn(BaseModel):
    Date: Optional[str] = None  # YYYY-MM-DD; defaults to today, cannot be in the future
    Note: Optional[str] = Field(default=None, max_length=250)


def _status_date(value: Optional[str]) -> str:
    if not (value or "").strip():
        return date.today().isoformat()
    try:
        d = date.fromisoformat(value.strip()[:10])
    except ValueError:
        raise HTTPException(400, "Enter a valid date")
    if d > date.today():
        raise HTTPException(400, "The date cannot be in the future")
    return d.isoformat()


def _leave(db: Session, student_id: int, status: str, payload: StatusIn) -> dict:
    s = db.get(Student, student_id)
    if not s:
        raise HTTPException(404, "Student not found")
    if (s.Status or "Active") != "Active":
        raise HTTPException(400, f"This student is already {s.Status}. Restore them first to change it.")
    s.Status = status
    s.StatusDate = _status_date(payload.Date)
    s.StatusNote = (payload.Note or "").strip() or None
    s.IsActive = "N"
    db.commit()
    return _dto(s, _dept_names(db))


@router.post("/{student_id}/discontinue", dependencies=gated)
def discontinue_student(student_id: int, payload: StatusIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Left the course. Attendance stops, history is kept, the student moves to the archive."""
    return _leave(db, student_id, "Discontinued", payload)


@router.post("/{student_id}/complete", dependencies=gated)
def complete_student(student_id: int, payload: StatusIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Finished the course (4th year). Moves to the archive."""
    return _leave(db, student_id, "Completed", payload)


@router.post("/{student_id}/restore", dependencies=gated)
def restore_student(student_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    s = db.get(Student, student_id)
    if not s:
        raise HTTPException(404, "Student not found")
    s.Status, s.StatusDate, s.StatusNote, s.IsActive = "Active", None, None, "Y"
    db.commit()
    return _dto(s, _dept_names(db))


class PromoteIn(BaseModel):
    department_id: Optional[int] = None  # None = every department
    dry_run: bool = True
    force: bool = False  # run again inside the lock window


def _last_promotion(db: Session) -> Optional[str]:
    row = db.query(MasterSetting).filter(MasterSetting.Name == LAST_PROMOTION_KEY).first()
    return (row.Value or None) if row else None


@router.post("/promote", dependencies=gated)
def promote_students(payload: PromoteIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """
    Year-end promotion: 3rd -> 4th, 2nd -> 3rd, 1st -> 2nd, and 4th year students are marked Completed
    (archived). Only active students move. dry_run returns the counts without changing anything.
    """
    q = db.query(Student).filter(Student.IsActive == "Y")
    if payload.department_id:
        q = q.filter(Student.DepartmentId == payload.department_id)
    students = q.all()
    names = _dept_names(db)
    per: dict[int, dict] = {}
    for s in students:
        d = per.setdefault(s.DepartmentId, {"DepartmentId": s.DepartmentId, "DepartmentName": names.get(s.DepartmentId, ""),
                                            "y1": 0, "y2": 0, "y3": 0, "completing": 0})
        d["completing" if s.YearOfStudy == 4 else f"y{s.YearOfStudy}"] += 1
    totals = {k: sum(d[k] for d in per.values()) for k in ("y1", "y2", "y3", "completing")}
    last = _last_promotion(db)
    locked = False
    if last:
        try:
            locked = (date.today() - date.fromisoformat(last)).days < PROMOTION_LOCK_DAYS
        except ValueError:
            pass
    result = {"departments": sorted(per.values(), key=lambda d: d["DepartmentName"]), "totals": totals,
              "last_promotion": last, "recently_promoted": locked, "applied": False}
    if payload.dry_run:
        return result
    if locked and not payload.force:
        raise HTTPException(409, f"Students were already promoted on {last}. Confirm again to run it a second time.")
    today = date.today().isoformat()
    for s in students:
        if s.YearOfStudy == 4:
            s.Status, s.StatusDate, s.StatusNote, s.IsActive = "Completed", today, "Completed 4th year", "N"
        else:
            s.YearOfStudy += 1
    if not payload.department_id:  # the lock is for whole-college runs; a single department can follow later
        row = db.query(MasterSetting).filter(MasterSetting.Name == LAST_PROMOTION_KEY).first()
        if row is None:
            row = MasterSetting(Name=LAST_PROMOTION_KEY)
            db.add(row)
        row.Value = today
    db.commit()
    result["applied"] = True
    return result


# ---- Excel / CSV import with column mapping (like Employees -> Import from Excel) ----

def _import_mapping(raw: str) -> tuple[dict[str, int], int, Optional[int]]:
    import json
    try:
        m = json.loads(raw or "{}")
        cols = {str(k): int(v) for k, v in (m.get("columns") or {}).items()}
        return cols, max(1, int(m.get("header_row") or 1)), (int(m["organization_id"]) if m.get("organization_id") else None)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise HTTPException(400, "Bad column mapping.")


@router.post("/import/inspect", dependencies=gated)
async def inspect_student_import(file: UploadFile = File(...), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Header row, columns with samples, a guessed mapping and the suggested organization."""
    from app.services.student_import import StudentImportService
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    return StudentImportService(db).inspect(data, file.filename or "")


@router.post("/import/preview", dependencies=gated)
async def preview_student_import(file: UploadFile = File(...), mapping: str = Form(...), db: Session = Depends(get_db),
                                 _user=Depends(get_current_user)):
    """Dry run: every row checked and the masters it would add, nothing saved."""
    from app.services.student_import import StudentImportService
    cols, header_row, org_id = _import_mapping(mapping)
    return StudentImportService(db).process(await file.read(), file.filename or "", cols, header_row, org_id, commit=False)


@router.post("/import/commit", dependencies=gated)
async def commit_student_import(file: UploadFile = File(...), mapping: str = Form(...), db: Session = Depends(get_db),
                                _user=Depends(get_current_user)):
    from app.services.student_import import StudentImportService
    cols, header_row, org_id = _import_mapping(mapping)
    return StudentImportService(db).process(await file.read(), file.filename or "", cols, header_row, org_id, commit=True)


@router.post("/import", dependencies=gated)
def import_students(payload: ImportIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    created, errors = 0, []
    seen: set[str] = set()
    for i, row in enumerate(payload.rows, start=1):
        code = row.StudentCode.strip()
        try:
            _validate_dept(db, row.DepartmentId)
            if code in seen or _code_taken(db, code):
                raise ValueError("code already used")
            row.StudentCode = code
            data = row.model_dump()
            data["StudentShiftId"] = _default_shift_id(db)
            db.add(Student(**data))
            db.flush()
            seen.add(code)
            created += 1
        except (ValueError, HTTPException) as exc:
            errors.append({"row": i, "code": code, "error": getattr(exc, "detail", None) or str(exc)})
    db.commit()
    return {"created": created, "errors": errors}


# ---- face enrollment (embeddings/photos are keyed by code, shared with employees) ----
def _student_or_404(db: Session, code: str) -> Student:
    s = db.query(Student).filter(Student.StudentCode == code).first()
    if not s:
        raise HTTPException(404, "Student not found")
    return s


@router.post("/{student_code}/enroll", dependencies=gated)
async def enroll_student_face(
    student_code: str,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    from app.api.v1.face import _embed_and_store

    s = _student_or_404(db, student_code)
    data = await photo.read()
    if not data:
        raise HTTPException(400, "Empty file")
    ident = SimpleNamespace(EmployeeCode=s.StudentCode, EmployeeName=s.StudentName)
    return await _embed_and_store(db, ident, data, photo.filename or "student-enroll.jpg",
                                  photo.content_type or "image/jpeg", "Enroll")


@router.post("/{student_code}/enroll-from-camera", dependencies=gated)
async def enroll_student_from_camera(
    student_code: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    from app.api.v1.face import _embed_and_store

    s = _student_or_404(db, student_code)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{settings.camera_service_url}/frame")
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"Camera service unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        raise HTTPException(503, "No live camera frame available")
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    ident = SimpleNamespace(EmployeeCode=s.StudentCode, EmployeeName=s.StudentName)
    return await _embed_and_store(db, ident, resp.content, f"camera-capture-{stamp}.jpg",
                                  "image/jpeg", "CameraCapture")
