"""
Default master data for a new installation: academic departments and the
designation ladder used by the department-wise reports. Idempotent - only
adds names that are missing (case-insensitive), never removes or renames.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import DepartmentMaster, Designation, LeaveConfig, Organization, Shift

DEFAULT_DEPARTMENTS = ["CSE", "EEE", "ECE", "MECH", "CIVIL", "IT", "AI & DS", "Administration"]
DEFAULT_DESIGNATIONS = ["HOD", "Professor", "Associate Professor", "Assistant Professor", "Non-Teaching"]

# Shift-wise timings for the attendance reports (HH:MM). ShortName is the register tag.
DEFAULT_SHIFTS = [
    {"ShiftName": "Teaching", "ShortName": "TCH", "StartTime": "09:45", "EndTime": "16:30"},
    {"ShiftName": "Non-Teaching", "ShortName": "NTCH", "StartTime": "09:30", "EndTime": "17:00"},
    {"ShiftName": "Physical Education", "ShortName": "PED", "StartTime": "10:00", "EndTime": "17:00"},
    {"ShiftName": "Scholar", "ShortName": "SCH", "StartTime": "09:30", "EndTime": "16:30"},
]

# Register leave codes surfaced as dynamic columns in the Time & Leave report.
# (P / A / WO are intrinsic statuses, not leave configs.) Names for FW/CoL are
# placeholders the client can rename; the report columns follow whatever is active.
DEFAULT_LEAVE_CODES = [
    {"Code": "CL", "Name": "Casual Leave", "MaxPerYear": 12, "IsPaid": "Y"},
    {"Code": "EL", "Name": "Earned Leave", "MaxPerYear": 15, "IsPaid": "Y"},
    {"Code": "FW", "Name": "Field Work", "MaxPerYear": 0, "IsPaid": "Y"},
    {"Code": "OD", "Name": "On Duty", "MaxPerYear": 0, "IsPaid": "Y"},
    {"Code": "LOP", "Name": "Loss of Pay", "MaxPerYear": 0, "IsPaid": "N"},
    {"Code": "HPL", "Name": "Half Pay Leave", "MaxPerYear": 0, "IsPaid": "Y"},
    {"Code": "MaL", "Name": "Maternity Leave", "MaxPerYear": 0, "IsPaid": "Y"},
    {"Code": "CO", "Name": "Comp Off", "MaxPerYear": 0, "IsPaid": "Y"},
    {"Code": "CoL", "Name": "Compensatory Leave", "MaxPerYear": 0, "IsPaid": "Y"},
]


def _norm(name: str) -> str:
    return " ".join((name or "").split()).lower()


def seed_default_masters(db: Session) -> dict[str, list[str]]:
    added = {"departments": [], "designations": [], "shifts": [], "leaves": []}

    org = db.query(Organization).order_by(Organization.OrganizationId).first()
    if org is None:
        org = Organization(OrgName="Default", IsActive="Y")
        db.add(org)
        db.flush()

    have = {_norm(d.DepartmentName) for d in db.query(DepartmentMaster).all()}
    for name in DEFAULT_DEPARTMENTS:
        if _norm(name) not in have:
            db.add(DepartmentMaster(OrganizationId=org.OrganizationId, DepartmentName=name, IsActive="Y"))
            added["departments"].append(name)

    have = {_norm(d.DesignationName) for d in db.query(Designation).all()}
    # Common misspelling seen in the field; treat as already present.
    if "assosiate professor" in have:
        have.add("associate professor")
    for name in DEFAULT_DESIGNATIONS:
        if _norm(name) not in have:
            db.add(Designation(DesignationName=name, IsActive="Y"))
            added["designations"].append(name)

    # Shift-wise timings (never flip an existing default shift).
    have = {_norm(s.ShiftName) for s in db.query(Shift).all()}
    for s in DEFAULT_SHIFTS:
        if _norm(s["ShiftName"]) not in have:
            db.add(Shift(ShiftName=s["ShiftName"], ShortName=s["ShortName"],
                         StartTime=s["StartTime"], EndTime=s["EndTime"],
                         GraceInMinutes=0, GraceOutMinutes=0, IsDefault="N", IsActive="Y"))
            added["shifts"].append(s["ShiftName"])

    # Register leave codes (case-insensitive on Code).
    have = {_norm(c.Code) for c in db.query(LeaveConfig).all()}
    for c in DEFAULT_LEAVE_CODES:
        if _norm(c["Code"]) not in have:
            db.add(LeaveConfig(Code=c["Code"], Name=c["Name"], MaxPerYear=c["MaxPerYear"],
                               IsPaid=c["IsPaid"], IsActive="Y"))
            added["leaves"].append(c["Code"])

    db.commit()
    return added
