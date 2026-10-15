"""Student leave types and leave requests (separate from employee leave)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.feature_flags import require_student_leaves
from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import Student, StudentLeaveConfig, StudentLeaveRequest

router = APIRouter(dependencies=[Depends(require_student_leaves)])


class LeaveTypeIn(BaseModel):
    Code: str = Field(min_length=1, max_length=10)
    Name: str = Field(min_length=1, max_length=100)
    MaxPerYear: int = Field(default=0, ge=0)
    IsPaid: str = "Y"
    IsActive: str = "Y"


class LeaveRequestIn(BaseModel):
    StudentCode: str
    StudentLeaveConfigId: int
    FromDate: date
    ToDate: date
    Reason: Optional[str] = None


class DecisionIn(BaseModel):
    status: str  # Approved | Rejected


def _type_dto(c: StudentLeaveConfig) -> dict:
    return {k: getattr(c, k) for k in ("StudentLeaveConfigId", "Code", "Name", "MaxPerYear", "IsPaid", "IsActive")}


@router.get("/types")
def list_types(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return [_type_dto(c) for c in db.query(StudentLeaveConfig).order_by(StudentLeaveConfig.StudentLeaveConfigId).all()]


@router.post("/types")
def create_type(p: LeaveTypeIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    p.Code = p.Code.strip().upper()
    if db.query(StudentLeaveConfig).filter(StudentLeaveConfig.Code == p.Code).first():
        raise HTTPException(409, "Leave code already exists")
    c = StudentLeaveConfig(**p.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _type_dto(c)


@router.put("/types/{type_id}")
def update_type(type_id: int, p: LeaveTypeIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    c = db.get(StudentLeaveConfig, type_id)
    if not c:
        raise HTTPException(404, "Leave type not found")
    p.Code = p.Code.strip().upper()
    if db.query(StudentLeaveConfig).filter(StudentLeaveConfig.Code == p.Code,
                                           StudentLeaveConfig.StudentLeaveConfigId != type_id).first():
        raise HTTPException(409, "Leave code already exists")
    for k, v in p.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _type_dto(c)


@router.delete("/types/{type_id}")
def delete_type(type_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    c = db.get(StudentLeaveConfig, type_id)
    if not c:
        raise HTTPException(404, "Leave type not found")
    if db.query(StudentLeaveRequest.StudentLeaveRequestId).filter(
            StudentLeaveRequest.StudentLeaveConfigId == type_id).first():
        raise HTTPException(409, "Leave type has requests; set it inactive instead")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/requests")
def list_requests(
    status: Optional[str] = None,
    student_code: Optional[str] = None,
    department_id: Optional[int] = None,
    year: Optional[int] = Query(default=None, ge=1, le=4),
    registered_year: Optional[str] = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = (
        db.query(StudentLeaveRequest, Student.StudentName, Student.RegisteredYear, Student.DepartmentId,
                 StudentLeaveConfig.Code, StudentLeaveConfig.Name)
        .join(Student, Student.StudentCode == StudentLeaveRequest.StudentCode)
        .join(StudentLeaveConfig, StudentLeaveConfig.StudentLeaveConfigId == StudentLeaveRequest.StudentLeaveConfigId)
    )
    if status:
        q = q.filter(StudentLeaveRequest.Status == status)
    if student_code:
        q = q.filter(StudentLeaveRequest.StudentCode == student_code)
    if department_id:
        q = q.filter(Student.DepartmentId == department_id)
    if year:
        q = q.filter(Student.YearOfStudy == year)
    if registered_year:
        q = q.filter(Student.RegisteredYear == registered_year)
    rows = q.order_by(StudentLeaveRequest.StudentLeaveRequestId.desc()).limit(500).all()
    return [
        {"StudentLeaveRequestId": r.StudentLeaveRequestId, "StudentCode": r.StudentCode, "StudentName": name,
         "RegisteredYear": ry, "DepartmentId": dept, "LeaveCode": code, "LeaveName": lname,
         "FromDate": r.FromDate.isoformat(), "ToDate": r.ToDate.isoformat(), "Reason": r.Reason,
         "Status": r.Status, "DecidedBy": r.DecidedBy}
        for r, name, ry, dept, code, lname in rows
    ]


@router.post("/requests")
def create_request(p: LeaveRequestIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    if p.ToDate < p.FromDate:
        raise HTTPException(400, "To date is before from date")
    if not db.query(Student.StudentId).filter(Student.StudentCode == p.StudentCode).first():
        raise HTTPException(404, "Student not found")
    if not db.get(StudentLeaveConfig, p.StudentLeaveConfigId):
        raise HTTPException(404, "Leave type not found")
    r = StudentLeaveRequest(**p.model_dump(), Status="Pending")
    db.add(r)
    db.commit()
    return {"StudentLeaveRequestId": r.StudentLeaveRequestId, "Status": r.Status}


@router.post("/requests/{request_id}/decision")
def decide(request_id: int, p: DecisionIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if p.status not in ("Approved", "Rejected"):
        raise HTTPException(400, "status must be Approved or Rejected")
    r = db.get(StudentLeaveRequest, request_id)
    if not r:
        raise HTTPException(404, "Request not found")
    r.Status = p.status
    r.DecidedBy = getattr(user, "LoginName", None)
    db.commit()
    if p.status == "Approved":
        # Refresh Auto rows so the leave shows in attendance immediately.
        from app.services.student_attendance_service import process_range
        try:
            process_range(db, r.FromDate, r.ToDate, [r.StudentCode])
        except ValueError:
            pass
    return {"ok": True, "Status": r.Status}
