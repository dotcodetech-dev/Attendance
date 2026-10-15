from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel
from typing import Optional

# Canonical target fields the Excel importer can map spreadsheet columns onto.
# Keep in sync with EmployeeImportService and the mapping dropdown on the frontend.
IMPORT_FIELDS = [
    "EmployeeCode",  # Face ID: the code the device / camera uses (the unique key)
    "HrCode",        # optional HR "Employee Code" shown in lists and reports (defaults to the Face ID)
    "ShortNo",       # optional short staff number (a label, not the Face ID)
    "EmployeeName",
    "EmployeeRFIDNumber",
    "Department",
    "Designation",
    "EmployeeType",
    "School",
    "Organization",
    "DateOfBirth",
    "JoiningDate",
    "CurrentStatus",
]


class HRProfileFields(BaseModel):
    ShortNo: Optional[str] = None  # optional short staff number; not unique, not sent to devices
    Designation: Optional[str] = None
    JoiningDate: Optional[str] = None
    GuardianName: Optional[str] = None
    DateOfBirth: Optional[str] = None
    BloodGroup: Optional[str] = None
    Address: Optional[str] = None
    AgreementYears: Optional[str] = None
    PersonalEmail: Optional[str] = None
    OfficialEmail: Optional[str] = None
    ContactNo: Optional[str] = None
    OfficialNo: Optional[str] = None
    EmergencyNo: Optional[str] = None
    MaritalStatus: Optional[str] = None
    AadharNo: Optional[str] = None
    PanNo: Optional[str] = None
    Salary: Optional[str] = None
    UAN: Optional[str] = None
    BiometricType: Optional[str] = None
    CurrentStatus: Optional[str] = None
    LastWorkingDay: Optional[str] = None
    ReasonForLeaving: Optional[str] = None


class EmployeeBase(HRProfileFields):
    EmployeeName: str
    EmployeeCode: str
    StringCode: str
    NumericCode: int
    EmployeeRFIDNumber: Optional[str] = None
    VerificationType: Optional[str] = None
    Role: Optional[str] = None
    Department: Optional[str] = None
    OrganizationId: Optional[int] = None
    EmployeeTypeId: Optional[int] = None
    SchoolId: Optional[int] = None
    CategoryId: Optional[int] = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(HRProfileFields):
    EmployeeName: Optional[str] = None
    StringCode: Optional[str] = None  # HR "Employee Code" (display); EmployeeCode is the Face ID
    EmployeeRFIDNumber: Optional[str] = None
    VerificationType: Optional[str] = None
    Role: Optional[str] = None
    Department: Optional[str] = None
    OrganizationId: Optional[int] = None
    EmployeeTypeId: Optional[int] = None
    SchoolId: Optional[int] = None
    CategoryId: Optional[int] = None


class EmployeeOut(EmployeeBase):
    EmployeeId: int
    CurrentShiftId: Optional[int] = None    # shift that applies today (roster row, else the default shift)
    CurrentShift: Optional[str] = None

    class Config:
        from_attributes = True


class EmployeeChangeCodeRequest(BaseModel):
    new_code: str


class EmployeeMoveRequest(BaseModel):
    employee_ids: list[int]
    OrganizationId: Optional[int] = None
    Department: Optional[str] = None
    SchoolId: Optional[int] = None


class EmployeeBiometricCreate(BaseModel):
    BioName: str
    BioDescription: Optional[str] = None
    Bio: Optional[str] = None
    MinorVer: Optional[str] = None
    MajorVer: Optional[str] = None


class EmployeePhotoUpsert(BaseModel):
    PhotoData: str
    PhotoMimeType: Optional[str] = "image/jpeg"
    Source: Optional[str] = "manual"
    PhotoName: Optional[str] = "PROFILE"
    DeviceId: Optional[int] = None


class EmployeePhotoOut(BaseModel):
    EmployeeCode: str
    HasPhoto: bool
    PhotoMimeType: Optional[str] = None
    Source: Optional[str] = None
    DeviceId: Optional[int] = None
    PhotoName: Optional[str] = None
    UpdatedAt: Optional[datetime] = None
    PhotoData: Optional[str] = None


# ---- Excel bulk import ----

class ImportColumn(BaseModel):
    index: int                    # 0-based column index
    letter: str                   # spreadsheet column letter (A, B, ...)
    header: Optional[str] = None  # header text on the detected header row, if any
    samples: list[str] = []       # first few non-empty values below the header


class ImportInspectResult(BaseModel):
    header_row: int               # 1-based row number that holds the headers
    columns: list[ImportColumn] = []
    guessed_mapping: dict[str, int] = {}  # field -> column index (best guess)
    fields: list[str] = IMPORT_FIELDS


class ImportMapping(BaseModel):
    header_row: int                       # 1-based
    columns: dict[str, int]               # field -> 0-based column index


class ImportRowResult(BaseModel):
    row_number: int
    EmployeeCode: Optional[str] = None
    EmployeeName: Optional[str] = None
    Department: Optional[str] = None
    Designation: Optional[str] = None
    EmployeeType: Optional[str] = None
    CurrentStatus: Optional[str] = None
    action: str                           # create | update | skip | error
    messages: list[str] = []


class ImportSummary(BaseModel):
    total: int = 0
    to_create: int = 0
    to_update: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


class ImportResult(BaseModel):
    committed: bool = False
    summary: ImportSummary = ImportSummary()
    rows: list[ImportRowResult] = []
    masters_created: dict[str, list[str]] = {}
