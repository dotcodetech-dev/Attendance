"""Master lists: Organization > School > Department, designations, employee types, student options."""
from __future__ import annotations

from typing import Optional

import io
import json
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import DepartmentMaster, Designation, Employee, EmployeeType, Organization, School, StudentOption

router = APIRouter()


class OrganizationIn(BaseModel):
    OrgName: str
    Address: Optional[str] = None
    IsActive: Optional[str] = "Y"


class DepartmentIn(BaseModel):
    OrganizationId: int
    DepartmentName: str
    IsActive: Optional[str] = "Y"
    SchoolId: Optional[int] = None   # sent = link (or null to unlink); left out = unchanged


class EmployeeTypeIn(BaseModel):
    TypeName: str
    IsActive: Optional[str] = "Y"


class SchoolIn(BaseModel):
    SchoolName: str
    IsActive: Optional[str] = "Y"
    OrganizationId: Optional[int] = None   # sent = link (or null to unlink); left out = unchanged


class DesignationIn(BaseModel):
    DesignationName: str
    IsActive: Optional[str] = "Y"


def _active(value: Optional[str]) -> str:
    return "Y" if (value or "Y").upper() != "N" else "N"


# ---- Organizations ----

@router.get("/organizations")
def list_organizations(include_inactive: bool = False, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    q = db.query(Organization)
    if not include_inactive:
        q = q.filter((Organization.IsActive.is_(None)) | (Organization.IsActive == "Y"))
    return [
        {"OrganizationId": o.OrganizationId, "OrgName": o.OrgName, "Address": o.Address, "IsActive": o.IsActive or "Y"}
        for o in q.order_by(Organization.OrgName).all()
    ]


@router.post("/organizations")
def create_organization(payload: OrganizationIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    name = payload.OrgName.strip()
    if not name:
        raise HTTPException(400, "Organization name is required")
    exists = db.query(Organization).filter(Organization.OrgName == name).first()
    if exists:
        raise HTTPException(400, "Organization already exists")
    row = Organization(OrgName=name, Address=(payload.Address or "").strip() or None, IsActive=_active(payload.IsActive))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"OrganizationId": row.OrganizationId, "OrgName": row.OrgName, "Address": row.Address, "IsActive": row.IsActive}


@router.put("/organizations/{org_id}")
def update_organization(org_id: int, payload: OrganizationIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(Organization).filter(Organization.OrganizationId == org_id).first()
    if not row:
        raise HTTPException(404, "Organization not found")
    row.OrgName = payload.OrgName.strip() or row.OrgName
    row.Address = (payload.Address or "").strip() or None
    row.IsActive = _active(payload.IsActive)
    db.commit()
    return {"OrganizationId": row.OrganizationId, "OrgName": row.OrgName, "Address": row.Address, "IsActive": row.IsActive}


# ---- Departments (per organization) ----

@router.get("/departments")
def list_departments(
    organization_id: Optional[int] = Query(default=None),
    school_id: Optional[int] = Query(default=None),
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(DepartmentMaster)
    if organization_id is not None:
        q = q.filter(DepartmentMaster.OrganizationId == organization_id)
    if school_id is not None:
        q = q.filter(DepartmentMaster.SchoolId == school_id)
    if not include_inactive:
        q = q.filter((DepartmentMaster.IsActive.is_(None)) | (DepartmentMaster.IsActive == "Y"))
    return [
        {
            "DepartmentId": d.DepartmentId,
            "OrganizationId": d.OrganizationId,
            "DepartmentName": d.DepartmentName,
            "IsActive": d.IsActive or "Y",
            "SchoolId": d.SchoolId,
        }
        for d in q.order_by(DepartmentMaster.DepartmentName).all()
    ]


def _dept_dto(d: DepartmentMaster) -> dict:
    return {"DepartmentId": d.DepartmentId, "OrganizationId": d.OrganizationId, "DepartmentName": d.DepartmentName,
            "IsActive": d.IsActive, "SchoolId": d.SchoolId}


def _school_for_department(db: Session, school_id: Optional[int], org_id: int) -> Optional[School]:
    """A department's school must exist and, once the school has an institution, be in the department's."""
    if school_id is None:
        return None
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(404, "School not found")
    if school.OrganizationId is not None and school.OrganizationId != org_id:
        raise HTTPException(400, "That school belongs to another organization.")
    return school


@router.post("/departments")
def create_department(payload: DepartmentIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    name = payload.DepartmentName.strip()
    if not name:
        raise HTTPException(400, "Department name is required")
    org = db.query(Organization).filter(Organization.OrganizationId == payload.OrganizationId).first()
    if not org:
        raise HTTPException(404, "Organization not found")
    _school_for_department(db, payload.SchoolId, payload.OrganizationId)
    exists = (
        db.query(DepartmentMaster)
        .filter(DepartmentMaster.OrganizationId == payload.OrganizationId)
        .filter(DepartmentMaster.DepartmentName == name)
        .filter(DepartmentMaster.SchoolId == payload.SchoolId if payload.SchoolId is not None else DepartmentMaster.SchoolId.is_(None))
        .first()
    )
    if exists:
        raise HTTPException(400, "Department already exists here")
    row = DepartmentMaster(OrganizationId=payload.OrganizationId, DepartmentName=name, IsActive=_active(payload.IsActive),
                           SchoolId=payload.SchoolId)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dept_dto(row)


@router.put("/departments/{dept_id}")
def update_department(dept_id: int, payload: DepartmentIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(DepartmentMaster).filter(DepartmentMaster.DepartmentId == dept_id).first()
    if not row:
        raise HTTPException(404, "Department not found")
    old_name = row.DepartmentName
    row.OrganizationId = payload.OrganizationId or row.OrganizationId
    row.DepartmentName = payload.DepartmentName.strip() or row.DepartmentName
    row.IsActive = _active(payload.IsActive)
    if "SchoolId" in payload.model_fields_set:
        _school_for_department(db, payload.SchoolId, row.OrganizationId)
        row.SchoolId = payload.SchoolId
    # Keep the legacy free-text employees.Department in sync on rename.
    if old_name != row.DepartmentName:
        db.query(Employee).filter(Employee.Department == old_name).update({"Department": row.DepartmentName})
    db.commit()
    return _dept_dto(row)


# ---- Employee types ----

@router.get("/employee-types")
def list_employee_types(include_inactive: bool = False, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    q = db.query(EmployeeType)
    if not include_inactive:
        q = q.filter((EmployeeType.IsActive.is_(None)) | (EmployeeType.IsActive == "Y"))
    return [
        {"EmployeeTypeId": t.EmployeeTypeId, "TypeName": t.TypeName, "IsActive": t.IsActive or "Y"}
        for t in q.order_by(EmployeeType.TypeName).all()
    ]


@router.post("/employee-types")
def create_employee_type(payload: EmployeeTypeIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    name = payload.TypeName.strip()
    if not name:
        raise HTTPException(400, "Type name is required")
    exists = db.query(EmployeeType).filter(EmployeeType.TypeName == name).first()
    if exists:
        raise HTTPException(400, "Employee type already exists")
    row = EmployeeType(TypeName=name, IsActive=_active(payload.IsActive))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"EmployeeTypeId": row.EmployeeTypeId, "TypeName": row.TypeName, "IsActive": row.IsActive}


@router.put("/employee-types/{type_id}")
def update_employee_type(type_id: int, payload: EmployeeTypeIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(EmployeeType).filter(EmployeeType.EmployeeTypeId == type_id).first()
    if not row:
        raise HTTPException(404, "Employee type not found")
    row.TypeName = payload.TypeName.strip() or row.TypeName
    row.IsActive = _active(payload.IsActive)
    db.commit()
    return {"EmployeeTypeId": row.EmployeeTypeId, "TypeName": row.TypeName, "IsActive": row.IsActive}


# ---- Schools ----

def _school_dto(s: School) -> dict:
    return {"SchoolId": s.SchoolId, "SchoolName": s.SchoolName, "IsActive": s.IsActive or "Y",
            "OrganizationId": s.OrganizationId}


def _norm(name: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _school_clash(db: Session, name: str, org_id: Optional[int], exclude_id: Optional[int] = None) -> bool:
    """School names are unique inside one organization (the same school, e.g. School of Home Science, can exist
    for Main Campus and for Ph D Scholars). Schools not linked to an organization yet are not compared."""
    if org_id is None:
        return False
    q = db.query(School).filter(School.OrganizationId == org_id, func.lower(School.SchoolName) == name.strip().lower())
    if exclude_id is not None:
        q = q.filter(School.SchoolId != exclude_id)
    return q.first() is not None


def _check_org(db: Session, org_id: Optional[int]) -> None:
    if org_id is not None and not db.get(Organization, org_id):
        raise HTTPException(404, "Organization not found")


@router.get("/schools")
def list_schools(organization_id: Optional[int] = Query(default=None), include_inactive: bool = False,
                 db: Session = Depends(get_db), _user=Depends(get_current_user)):
    q = db.query(School)
    if organization_id is not None:
        q = q.filter(School.OrganizationId == organization_id)
    if not include_inactive:
        q = q.filter((School.IsActive.is_(None)) | (School.IsActive == "Y"))
    return [_school_dto(s) for s in q.order_by(School.SchoolName).all()]


@router.post("/schools")
def create_school(payload: SchoolIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    name = payload.SchoolName.strip()
    if not name:
        raise HTTPException(400, "School name is required")
    _check_org(db, payload.OrganizationId)
    if _school_clash(db, name, payload.OrganizationId):
        raise HTTPException(400, "This organization already has a school with that name")
    row = School(SchoolName=name, IsActive=_active(payload.IsActive), OrganizationId=payload.OrganizationId)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _school_dto(row)


@router.put("/schools/{school_id}")
def update_school(school_id: int, payload: SchoolIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(School).filter(School.SchoolId == school_id).first()
    if not row:
        raise HTTPException(404, "School not found")
    name = payload.SchoolName.strip() or row.SchoolName
    target_org = payload.OrganizationId if "OrganizationId" in payload.model_fields_set else row.OrganizationId
    if _school_clash(db, name, target_org, exclude_id=school_id):
        raise HTTPException(400, "This organization already has a school with that name")
    row.SchoolName = name  # employees store the id, so nothing else needs renaming
    row.IsActive = _active(payload.IsActive)
    if "OrganizationId" in payload.model_fields_set and payload.OrganizationId != row.OrganizationId:
        _check_org(db, payload.OrganizationId)
        row.OrganizationId = payload.OrganizationId
        if payload.OrganizationId is not None:
            # Its departments follow it only if they were in no other institution; the rest are unlinked.
            db.query(DepartmentMaster).filter(DepartmentMaster.SchoolId == school_id,
                                              DepartmentMaster.OrganizationId != payload.OrganizationId) \
                .update({DepartmentMaster.SchoolId: None}, synchronize_session=False)
    db.commit()
    return _school_dto(row)


@router.post("/link-from-employees")
def link_from_employees(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> dict:
    """Fill the Organization > School > Department links that are still empty from what the employees carry:
    a school goes to the institution most of its staff are in, a department to the school most of its staff
    (in that institution) are in. Links already set are never changed."""
    schools_linked = depts_linked = 0
    for school in db.query(School).filter(School.OrganizationId.is_(None)).all():
        top = (db.query(Employee.OrganizationId, func.count(Employee.EmployeeId))
               .filter(Employee.SchoolId == school.SchoolId, Employee.OrganizationId.isnot(None))
               .group_by(Employee.OrganizationId).order_by(func.count(Employee.EmployeeId).desc()).first())
        if top:
            school.OrganizationId = top[0]
            schools_linked += 1
    db.flush()
    school_org = {s.SchoolId: s.OrganizationId for s in db.query(School)}
    for dept in db.query(DepartmentMaster).filter(DepartmentMaster.SchoolId.is_(None)).all():
        rows = (db.query(Employee.SchoolId, func.count(Employee.EmployeeId))
                .filter(func.upper(func.ltrim(func.rtrim(Employee.Department))) == dept.DepartmentName.strip().upper(),
                        Employee.OrganizationId == dept.OrganizationId, Employee.SchoolId.isnot(None))
                .group_by(Employee.SchoolId).order_by(func.count(Employee.EmployeeId).desc()).all())
        pick = next((sid for sid, _ in rows if school_org.get(sid) in (None, dept.OrganizationId)), None)
        if pick is not None:
            dept.SchoolId = pick
            depts_linked += 1
    db.commit()
    left_schools = db.query(School).filter(School.OrganizationId.is_(None)).count()
    left_depts = db.query(DepartmentMaster).filter(DepartmentMaster.SchoolId.is_(None)).count()
    return {"schools_linked": schools_linked, "departments_linked": depts_linked,
            "schools_unlinked": left_schools, "departments_unlinked": left_depts}


# ---- Import Organization > School > Department from Excel ----

def _read_hierarchy_rows(data: bytes, filename: str) -> list[tuple[str, str, Optional[str]]]:
    """(organization, school, department) rows. Blank Organization / School cells repeat the one above, as in a
    sheet laid out with merged-looking groups. The first row with "organization" / "school" in it is the header."""
    raw: list[list] = []
    if filename.lower().endswith(".csv"):
        import csv
        text = data.decode("utf-8-sig", errors="replace")
        raw = [row for row in csv.reader(io.StringIO(text))]
    else:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:
            raise HTTPException(400, f"Could not read the file as Excel (.xlsx): {exc.__class__.__name__}")
        raw = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    cols = None
    rows: list[tuple[str, str, Optional[str]]] = []
    org = school = None
    for r in raw:
        cells = [("" if v is None else str(v)).strip() for v in r]
        if cols is None:
            low = [c.lower() for c in cells]
            o = next((i for i, c in enumerate(low) if "organi" in c or "institution" in c), None)
            sc = next((i for i, c in enumerate(low) if "school" in c), None)
            d = next((i for i, c in enumerate(low) if "depart" in c), None)
            if o is not None and sc is not None:
                cols = (o, sc, d)
            continue
        get = lambda i: cells[i] if i is not None and i < len(cells) else ""
        o_val, s_val, d_val = get(cols[0]), get(cols[1]), get(cols[2])
        if o_val:
            org, school = o_val, None
        if s_val:
            school = s_val
        if not (o_val or s_val or d_val):
            continue
        if org and school:
            rows.append((org, school, d_val or None))
    if cols is None:
        raise HTTPException(400, "No header row found: the sheet needs Organization, School and Department columns.")
    if not rows:
        raise HTTPException(400, "The sheet has no organization / school rows.")
    return rows


def _suggest_org(name: str, orgs: list[Organization]) -> Optional[int]:
    """Best existing organization for a name in the file: "Main Campus" -> "Main Campus/AHS/EDU/SF",
    "Engg campus" -> "Engineering Campus Staff", "Ph D Scholar" -> "PH. D SCHOLARS"."""
    words = lambda t: [w for w in re.split(r"[^a-z0-9]+", t.lower()) if w]
    want = words(name)
    best, best_score = None, 0.0
    for o in orgs:
        have = words(o.OrgName)
        if want == have:
            return o.OrganizationId
        hits = sum(1 for w in want if any(h.startswith(w[:3]) or w.startswith(h[:3]) for h in have))
        score = hits / max(len(want), 1) - 0.01 * abs(len(have) - len(want))
        if score > best_score:
            best, best_score = o.OrganizationId, score
    return best if best_score >= 0.6 else None


def _apply_hierarchy(db: Session, rows, org_map: dict[str, Optional[int]]) -> dict:
    stats = {"organizations_created": 0, "schools_created": 0, "schools_linked": 0, "schools_existing": 0,
             "departments_created": 0, "departments_linked": 0, "departments_existing": 0}
    org_ids: dict[str, int] = {}
    for name in dict.fromkeys(o for o, _, _ in rows):
        mapped = org_map.get(name)
        if mapped:
            if not db.get(Organization, mapped):
                raise HTTPException(400, f'Organization for "{name}" no longer exists; reload and pick again.')
            org_ids[name] = mapped
            continue
        same = next((o for o in db.query(Organization) if _norm(o.OrgName) == _norm(name)), None)
        if same is None:
            same = Organization(OrgName=name.strip(), IsActive="Y")
            db.add(same)
            db.flush()
            stats["organizations_created"] += 1
        org_ids[name] = same.OrganizationId

    school_ids: dict[tuple[int, str], int] = {}
    for org_name, school_name, dept_name in rows:
        org_id = org_ids[org_name]
        key = (org_id, _norm(school_name))
        if key not in school_ids:
            linked = next((x for x in db.query(School).filter(School.OrganizationId == org_id)
                           if _norm(x.SchoolName) == key[1]), None)
            if linked is not None:
                stats["schools_existing"] += 1
            else:
                linked = next((x for x in db.query(School).filter(School.OrganizationId.is_(None))
                               if _norm(x.SchoolName) == key[1]), None)
                if linked is not None:
                    linked.OrganizationId = org_id
                    stats["schools_linked"] += 1
                else:
                    linked = School(SchoolName=school_name.strip(), IsActive="Y", OrganizationId=org_id)
                    db.add(linked)
                    stats["schools_created"] += 1
                db.flush()
            school_ids[key] = linked.SchoolId
        school_id = school_ids[key]
        if not dept_name:
            continue
        dn = _norm(dept_name)
        in_org = [d for d in db.query(DepartmentMaster).filter(DepartmentMaster.OrganizationId == org_id)
                  if _norm(d.DepartmentName) == dn]
        if any(d.SchoolId == school_id for d in in_org):
            stats["departments_existing"] += 1
            continue
        free = next((d for d in in_org if d.SchoolId is None), None)
        if free is not None:
            free.SchoolId = school_id
            stats["departments_linked"] += 1
        else:
            # Same name in another school of this organization (e.g. Computer Science in PSCS and Campus II SF).
            db.add(DepartmentMaster(OrganizationId=org_id, DepartmentName=dept_name.strip(), IsActive="Y", SchoolId=school_id))
            stats["departments_created"] += 1
        db.flush()
    return stats


@router.post("/hierarchy-import")
async def import_hierarchy(
    file: UploadFile = File(...),
    commit: bool = Form(default=False),
    org_map: str = Form(default="{}"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> dict:
    """Organization > School > Department from an Excel sheet (columns Organization, School, Department).
    commit=false: a dry run - what would be created or linked, and which existing organization each name in the
    file is matched to. org_map {"name in file": OrganizationId | null (= create it)} overrides the matches.
    Nothing already set up is renamed or removed; names are matched ignoring case and extra spaces."""
    rows = _read_hierarchy_rows(await file.read(), file.filename or "")
    try:
        chosen = {str(k): (int(v) if v not in (None, "", "new") else None) for k, v in json.loads(org_map or "{}").items()}
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "Bad organization choices.")
    orgs = db.query(Organization).all()
    file_orgs = []
    for name in dict.fromkeys(o for o, _, _ in rows):
        file_orgs.append({
            "name": name,
            "schools": len({_norm(s) for o, s, _ in rows if o == name}),
            "departments": sum(1 for o, _, d in rows if o == name and d),
            "suggested_id": _suggest_org(name, orgs),
        })
    effective = {f["name"]: chosen[f["name"]] if f["name"] in chosen else f["suggested_id"] for f in file_orgs}
    try:
        stats = _apply_hierarchy(db, rows, effective)
        if commit:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    return {"committed": commit, "rows": len(rows), "organizations": file_orgs, "used": effective, **stats}


# ---- Designations ----

def _designation_dto(d: Designation) -> dict:
    return {"DesignationId": d.DesignationId, "DesignationName": d.DesignationName, "IsActive": d.IsActive or "Y"}


@router.get("/designations")
def list_designations(include_inactive: bool = False, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    q = db.query(Designation)
    if not include_inactive:
        q = q.filter((Designation.IsActive.is_(None)) | (Designation.IsActive == "Y"))
    return [_designation_dto(d) for d in q.order_by(Designation.DesignationName).all()]


@router.post("/designations")
def create_designation(payload: DesignationIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    name = payload.DesignationName.strip()
    if not name:
        raise HTTPException(400, "Designation name is required")
    if db.query(Designation).filter(Designation.DesignationName == name).first():
        raise HTTPException(400, "Designation already exists")
    row = Designation(DesignationName=name, IsActive=_active(payload.IsActive))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _designation_dto(row)


@router.put("/designations/{designation_id}")
def update_designation(designation_id: int, payload: DesignationIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(Designation).filter(Designation.DesignationId == designation_id).first()
    if not row:
        raise HTTPException(404, "Designation not found")
    old_name = row.DesignationName
    row.DesignationName = payload.DesignationName.strip() or row.DesignationName
    row.IsActive = _active(payload.IsActive)
    # Keep employees.Designation (free text) in sync on rename.
    if old_name != row.DesignationName:
        db.query(Employee).filter(Employee.Designation == old_name).update({"Designation": row.DesignationName})
    db.commit()
    return _designation_dto(row)


# ---- Student dropdown options (Registered Year / Batch / Category) ----
_STUDENT_OPTION_TYPES = ("RegisteredYear", "Batch", "Category")


class StudentOptionIn(BaseModel):
    OptionType: str
    OptionValue: str
    IsActive: Optional[str] = "Y"


class StudentOptionUpdate(BaseModel):
    OptionValue: Optional[str] = None
    IsActive: Optional[str] = None


def _student_option_dto(o: StudentOption) -> dict:
    return {"StudentOptionId": o.StudentOptionId, "OptionType": o.OptionType,
            "OptionValue": o.OptionValue, "SortOrder": o.SortOrder, "IsActive": o.IsActive or "Y"}


def _validate_option_type(option_type: str) -> None:
    if option_type not in _STUDENT_OPTION_TYPES:
        raise HTTPException(400, f"Unknown option type (expected one of {', '.join(_STUDENT_OPTION_TYPES)})")


@router.get("/student-options")
def list_student_options(option_type: Optional[str] = None, include_inactive: bool = False,
                         db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """All configurable student dropdown values, grouped by type (active only unless include_inactive)."""
    q = db.query(StudentOption)
    if option_type:
        _validate_option_type(option_type)
        q = q.filter(StudentOption.OptionType == option_type)
    if not include_inactive:
        q = q.filter(StudentOption.IsActive == "Y")
    grouped: dict[str, list] = {t: [] for t in _STUDENT_OPTION_TYPES}
    for o in q.order_by(StudentOption.OptionType, StudentOption.SortOrder, StudentOption.OptionValue).all():
        grouped.setdefault(o.OptionType, []).append(_student_option_dto(o))
    return grouped


@router.post("/student-options")
def create_student_option(payload: StudentOptionIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _validate_option_type(payload.OptionType)
    value = payload.OptionValue.strip()
    if not value:
        raise HTTPException(400, "Value is required")
    if db.query(StudentOption).filter(StudentOption.OptionType == payload.OptionType,
                                      func.lower(StudentOption.OptionValue) == value.lower()).first():
        raise HTTPException(400, "That value already exists")
    nxt = (db.query(func.max(StudentOption.SortOrder)).filter(StudentOption.OptionType == payload.OptionType).scalar() or 0) + 1
    row = StudentOption(OptionType=payload.OptionType, OptionValue=value, SortOrder=nxt, IsActive=_active(payload.IsActive))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _student_option_dto(row)


@router.put("/student-options/{option_id}")
def update_student_option(option_id: int, payload: StudentOptionUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(StudentOption).filter(StudentOption.StudentOptionId == option_id).first()
    if not row:
        raise HTTPException(404, "Option not found")
    if payload.OptionValue is not None:
        value = payload.OptionValue.strip()
        if value and value.lower() != row.OptionValue.lower():
            clash = db.query(StudentOption).filter(StudentOption.OptionType == row.OptionType,
                                                   func.lower(StudentOption.OptionValue) == value.lower(),
                                                   StudentOption.StudentOptionId != option_id).first()
            if clash:
                raise HTTPException(400, "That value already exists")
            row.OptionValue = value
    if payload.IsActive is not None:
        row.IsActive = _active(payload.IsActive)
    db.commit()
    return _student_option_dto(row)
