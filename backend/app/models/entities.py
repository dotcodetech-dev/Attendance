from __future__ import annotations
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Shift(Base):
    __tablename__ = "shifts"

    ShiftId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ShiftName: Mapped[str] = mapped_column(String(100), nullable=False)
    ShortName: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    StartTime: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    EndTime: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    GraceInMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    GraceOutMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    Break1Enabled: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    Break1StartTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    Break1EndTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    Break2Enabled: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    Break2StartTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    Break2EndTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    IsFlexibleShift: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    PunchBeginBeforeMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    PunchEndAfterMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    GraceTimeMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    PartialDayEnabled: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    PartialDayWeekday: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    PartialDayStartTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    PartialDayEndTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    IsDefault: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")


class ShiftRoster(Base):
    __tablename__ = "shiftrosters"

    ShiftRosterId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(
        String(250), ForeignKey("employees.EmployeeCode"), nullable=False
    )
    ShiftId: Mapped[int] = mapped_column(
        Integer, ForeignKey("shifts.ShiftId"), nullable=False
    )
    FromDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ToDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Holiday(Base):
    __tablename__ = "holidays"

    HolidayId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    HolidayDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    HolidayName: Mapped[str] = mapped_column(String(200), nullable=False)
    Category: Mapped[str] = mapped_column(String(20), nullable=False, default="Public")
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")


class AttendanceCategory(Base):
    __tablename__ = "attendance_categories"

    CategoryId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    CategoryName: Mapped[str] = mapped_column(String(120), nullable=False)
    ShortName: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    OTFormula: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default="Total Duration - Shift Hours"
    )
    MinOTMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=30)
    MaxOTMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    GraceLateComingMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=15)
    GraceEarlyGoingMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=15)
    WeeklyOff1Enabled: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    WeeklyOff1Weekday: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    WeeklyOff2Enabled: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    WeeklyOff2Weekday: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    WeeklyOff2Occurrence1: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    WeeklyOff2Occurrence2: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    WeeklyOff2Occurrence3: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    WeeklyOff2Occurrence4: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    WeeklyOff2Occurrence5: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    ConsiderEarlyComingPunch: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    ConsiderOnlyFirstLastPunch: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")
    ConsiderLateGoingPunch: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")
    DeductBreakHours: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    NeglectLastInPunch: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    HalfDayIfWorkDurationLessThanMinutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=240
    )
    AbsentIfWorkDurationLessThanMinutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=120
    )
    PartialDayCalculateHalfDayIfWorkDurationLessThanMinutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0
    )
    PartialDayCalculateAbsentIfWorkDurationLessThanMinutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0
    )
    MarkWeeklyOffHolidayAsAbsentPrefixAbsent: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True, default="N"
    )
    MarkWeeklyOffHolidayAsAbsentSuffixAbsent: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True, default="N"
    )
    MarkWeeklyOffHolidayAsAbsentBothSidesAbsent: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True, default="N"
    )
    MarkHalfDayWhenLateForDays: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    MarkHalfDayIfLateByMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    MarkHalfDayIfEarlyGoingByMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")


class LeaveConfig(Base):
    __tablename__ = "leaveconfigs"

    LeaveConfigId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    Code: Mapped[str] = mapped_column(String(50), nullable=False)  # register symbol, e.g. CL / EL
    Name: Mapped[str] = mapped_column(String(200), nullable=False)
    MaxPerYear: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # default yearly entitlement
    IsPaid: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")
    ConsiderWeeklyOff: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    ConsiderHoliday: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="N")
    CarryForwardLimit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")


class EmployeeLeaveBalance(Base):
    """Per-employee, per-year leave entitlement (mirrors eTimeTrackLite EMPLOYEELEAVES).
    Overrides LeaveConfig.MaxPerYear for a specific employee/type/year."""

    __tablename__ = "employee_leave_balances"
    __table_args__ = (
        UniqueConstraint("EmployeeCode", "LeaveConfigId", "LeaveYear", name="uq_emp_leave_balance"),
    )

    EmployeeLeaveBalanceId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    LeaveConfigId: Mapped[int] = mapped_column(Integer, nullable=False)
    LeaveYear: Mapped[int] = mapped_column(Integer, nullable=False)
    AllowedLeaves: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    CarriedForward: Mapped[float] = mapped_column(Float, nullable=False, default=0)


class LeaveRequest(Base):
    __tablename__ = "leaverequests"

    LeaveRequestId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(
        String(250), ForeignKey("employees.EmployeeCode"), nullable=False
    )
    LeaveConfigId: Mapped[int] = mapped_column(
        Integer, ForeignKey("leaveconfigs.LeaveConfigId"), nullable=False
    )
    FromDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ToDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    Reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    Status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Pending"
    )  # Pending/Approved/Rejected
    AppliedAt: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class LeaveApproval(Base):
    """One decision in a leave request's approval trail."""

    __tablename__ = "leave_approvals"

    LeaveApprovalId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    LeaveRequestId: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    Level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = HOD / Manager, 2 = Principal / Director
    Action: Mapped[str] = mapped_column(String(20), nullable=False)  # Approved | Rejected | Skipped
    ByUser: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    ByRole: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    Remarks: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ActionAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ManualEntry(Base):
    __tablename__ = "manualentries"

    ManualEntryId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(
        String(250), ForeignKey("employees.EmployeeCode"), nullable=False
    )
    LogDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    EntryType: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Manual"
    )  # Manual / OD
    InTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # HH:MM
    OutTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # HH:MM
    Reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    Status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Pending"
    )  # Pending/Approved/Rejected
    AppliedAt: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class Device(Base):
    __tablename__ = "devices"

    DeviceId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    DeviceName: Mapped[str] = mapped_column(String(255), nullable=False)
    DeviceDirection: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    SerialNumber: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    DeviceIPAddress: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    TransactionStamp: Mapped[str] = mapped_column(String(50), default="0")
    LastPing: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    OpStamp: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    Timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ActivationCode: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    LastReset: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    DeviceType: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    IsAttendanceDevice: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    LocationId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    CommKey: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # SDK login key set on the reader
    # Institution the reader belongs to: a campus-role login (User Roles) sees only its institution's readers.
    OrganizationId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Organization(Base):
    __tablename__ = "organizations"

    OrganizationId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    OrgName: Mapped[str] = mapped_column(String(250), nullable=False)
    Address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")


class DepartmentMaster(Base):
    __tablename__ = "departments"

    DepartmentId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    OrganizationId: Mapped[int] = mapped_column(Integer, nullable=False)
    DepartmentName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")
    SchoolId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # Organization > School > Department


class EmployeeType(Base):
    __tablename__ = "employee_types"

    EmployeeTypeId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    TypeName: Mapped[str] = mapped_column(String(100), nullable=False)
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")


class School(Base):
    """A school / faculty inside an institution (e.g. School of Computer Science): Organization > School > Department.
    Employees carry a SchoolId. OrganizationId NULL = not linked to an institution yet (older data)."""

    __tablename__ = "schools"

    SchoolId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    SchoolName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")
    OrganizationId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Designation(Base):
    __tablename__ = "designations"

    DesignationId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    DesignationName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, default="Y")


class Employee(Base):
    __tablename__ = "employees"

    EmployeeId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeName: Mapped[str] = mapped_column(String(250), nullable=False)
    EmployeeCode: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    StringCode: Mapped[str] = mapped_column(String(250), nullable=False)
    NumericCode: Mapped[int] = mapped_column(Integer, nullable=False)
    EmployeeRFIDNumber: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    VerificationType: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    Role: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    Department: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    OrganizationId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    EmployeeTypeId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    SchoolId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    CategoryId: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("attendance_categories.CategoryId"), nullable=True
    )
    ShortNo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)   # optional short staff number (a label; not the Face ID)
    # --- HR profile fields ---
    Designation: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    JoiningDate: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)      # YYYY-MM-DD
    GuardianName: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)    # Parent/Spouse
    DateOfBirth: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)      # YYYY-MM-DD
    BloodGroup: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    Address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    AgreementYears: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    PersonalEmail: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    OfficialEmail: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    ContactNo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    OfficialNo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    EmergencyNo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    MaritalStatus: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    AadharNo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    PanNo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    Salary: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    UAN: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    BiometricType: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    CurrentStatus: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="Active")
    LastWorkingDay: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)   # YYYY-MM-DD
    ReasonForLeaving: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class EmployeeBio(Base):
    __tablename__ = "employeesbio"

    EmployeeBioId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(String(250), ForeignKey("employees.EmployeeCode"), nullable=False)
    BioName: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    BioDescription: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    Bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    MinorVer: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    MajorVer: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Finger number (0-9) for FINGER rows, so every finger is kept. NULL = an older row (counts as one finger) or a face.
    FingerIndex: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class EmployeePhoto(Base):
    __tablename__ = "employeephotos"

    EmployeePhotoId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(String(250), ForeignKey("employees.EmployeeCode"), nullable=False)
    DeviceId: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.DeviceId"), nullable=True)
    PhotoName: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    PhotoMimeType: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    PhotoData: Mapped[str] = mapped_column(Text, nullable=False)
    Source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    Checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    CreatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    UpdatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)


class EmployeeFaceEmbedding(Base):
    __tablename__ = "employeefaceembeddings"

    EmployeeFaceEmbeddingId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(String(250), ForeignKey("employees.EmployeeCode"), nullable=False)
    Embedding: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of 512 floats, L2-normalized
    DetScore: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    EmployeePhotoId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # source photo in employeephotos
    Source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="Enroll")
    CreatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)


class BlockedPin(Base):
    """Face IDs that must not become employees again: people deleted here. Readers may keep sending them."""
    __tablename__ = "blocked_pins"

    BlockedPinId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    Pin: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    EmployeeName: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    Reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class DeviceEmployee(Base):
    __tablename__ = "deviceemployees"

    DeviceEmployeeId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    DeviceId: Mapped[int] = mapped_column(ForeignKey("devices.DeviceId"), nullable=False)
    EmployeeId: Mapped[int] = mapped_column(ForeignKey("employees.EmployeeId"), nullable=False)
    Role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    Command: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    Status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    SyncDate: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class TransferJob(Base):
    __tablename__ = "transferjobs"

    TransferJobId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    Status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    Phase: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="face")
    TotalUsers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    BatchSize: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    TotalBatches: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    FaceQueued: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    FaceExecuted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    FaceFailed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    FingerQueued: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    FingerExecuted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    FingerFailed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    IncludeFace: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    IncludeFinger: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    IncludeCard: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    IncludePhoto: Mapped[str] = mapped_column(String(1), nullable=False, default="N")
    SequentialBiometrics: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    EmployeeCodes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON array
    TargetDeviceIds: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    SourceDeviceId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    CreationDate: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    StartDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    CompletionDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ErrorMessage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DeviceCommand(Base):
    __tablename__ = "devicecommands"

    DeviceCommandId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    DeviceId: Mapped[int] = mapped_column(ForeignKey("devices.DeviceId"), nullable=False)
    Title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    DeviceCommand: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    Status: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default="Pending")
    Type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    CreationDate: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    ExecutionDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    DeviceCommandFace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Transfer job tracking
    TransferJobId: Mapped[Optional[int]] = mapped_column(ForeignKey("transferjobs.TransferJobId"), nullable=True)
    Phase: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    RetryCount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    SentDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DeviceLog(Base):
    __tablename__ = "devicelogs"

    DeviceLogId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    DeviceId: Mapped[int] = mapped_column(ForeignKey("devices.DeviceId"), nullable=False)
    EmployeeCode: Mapped[str] = mapped_column(String(50), nullable=False)
    LogDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    VerificationType: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    Direction: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    WorkCode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    AttPhoto: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    WebhookSyncStatus: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    DownloadDate: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    UserId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    LoginName: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    LoginPassword: Mapped[str] = mapped_column(String(250), nullable=False)
    RoleName: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    Permissions: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    Locations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    Blocked: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Employee this login belongs to. Approvers (HOD / Manager, Principal / Director) need it so the
    # app knows their department and never lets anyone decide their own leave.
    EmployeeCode: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    AuthToken: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    Expiry: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class RoleConfig(Base):
    __tablename__ = "role_config"

    RoleName: Mapped[str] = mapped_column(String(50), primary_key=True)
    PermissionsJson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class MasterSetting(Base):
    """Key/value application settings (organisation branding, address, etc.)."""

    __tablename__ = "mastersettings"

    Name: Mapped[str] = mapped_column("Name", String(50), primary_key=True)
    Value: Mapped[Optional[str]] = mapped_column("Value", Text, nullable=True)


class MessMeal(Base):
    """Configurable meal window for mess token generation (Breakfast/Lunch/Dinner)."""

    __tablename__ = "mess_meals"

    MessMealId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    MealType: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    StartTime: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM (24h)
    EndTime: Mapped[str] = mapped_column(String(5), nullable=False)
    SortOrder: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    IsActive: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")


class MessToken(Base):
    """One issued mess token. One per employee per meal per day."""

    __tablename__ = "mess_tokens"
    __table_args__ = (
        UniqueConstraint("EmployeeCode", "MealType", "TokenDate", name="uq_mess_token_emp_meal_day"),
    )

    MessTokenId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    EmployeeName: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    MealType: Mapped[str] = mapped_column(String(30), nullable=False)
    TokenNumber: Mapped[int] = mapped_column(Integer, nullable=False)
    TokenDate: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    PrintStatus: Mapped[str] = mapped_column(String(20), nullable=False, default="Printed")
    ReprintCount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    LastReprintAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AttendanceProcessed(Base):
    """
    Materialized daily attendance — one row per employee per day, computed from
    raw devicelogs against shift/holiday/leave rules by the recalc processor.
    Mirrors eTimeTrackLite's ATTENDANCELOGS: reports/dashboards read from here
    instead of recomputing from raw punches on every request.
    """

    __tablename__ = "attendance_processed"
    __table_args__ = (
        UniqueConstraint("EmployeeCode", "AttendanceDate", name="uq_attendance_processed_emp_date"),
    )

    AttendanceProcessedId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    EmployeeCode: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    AttendanceDate: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    Status: Mapped[str] = mapped_column(String(2), nullable=False)          # P/H/A/L/O
    StatusLabel: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ShiftId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ShiftName: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ShiftTime: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    FirstIn: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)   # HH:MM
    LastOut: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)   # HH:MM
    TotalLogs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ActualWorkMinutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    LeaveCode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)   # CL/EL/... when Status='L'
    LateMinutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    EarlyMinutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    OTMinutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    Remarks: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ProcessedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Student attendance module (separate from Employees; shares departments,
# devicelogs and face embeddings via the unique code string).
# ---------------------------------------------------------------------------
class StudentShift(Base):
    __tablename__ = "student_shifts"

    StudentShiftId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ShiftName: Mapped[str] = mapped_column(String(100), nullable=False)
    StartTime: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    EndTime: Mapped[str] = mapped_column(String(5), nullable=False)
    GraceInMinutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    HalfDayMinutes: Mapped[int] = mapped_column(Integer, nullable=False, default=240)  # worked < this => HalfDay
    WeeklyOff: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="Sunday")
    IsActive: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")


class StudentOption(Base):
    """Configurable dropdown values for the student form (Registered Year, Batch, Category).
    One row per value; OptionType groups them so the same table serves every list."""

    __tablename__ = "student_options"
    __table_args__ = (
        UniqueConstraint("OptionType", "OptionValue", name="uq_student_option"),
    )

    StudentOptionId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    OptionType: Mapped[str] = mapped_column(String(30), nullable=False)   # RegisteredYear | Batch | Category
    OptionValue: Mapped[str] = mapped_column(String(50), nullable=False)
    SortOrder: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    IsActive: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")


class Student(Base):
    __tablename__ = "students"

    StudentId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    StudentCode: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    StudentName: Mapped[str] = mapped_column(String(250), nullable=False)
    DepartmentId: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    YearOfStudy: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # legacy; kept for compatibility
    RegisteredYear: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # admission session, e.g. "Jan 2026"
    Batch: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)           # admission year, e.g. "2026"
    Category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)        # Full Time | Part Time (configurable)
    SchoolId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)           # Org & Masters -> School
    Section: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    RollNo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    GuardianName: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)   # retired from UI; column kept
    GuardianPhone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)   # retired from UI; column kept
    DateOfBirth: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)     # now surfaced as "Registered Date"
    StudentShiftId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    IsActive: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    Status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")  # Active | Discontinued | Completed
    StatusDate: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    StatusNote: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class StudentLeaveConfig(Base):
    __tablename__ = "student_leave_configs"

    StudentLeaveConfigId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    Code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    Name: Mapped[str] = mapped_column(String(100), nullable=False)
    MaxPerYear: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    IsPaid: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")
    IsActive: Mapped[str] = mapped_column(String(1), nullable=False, default="Y")


class StudentLeaveRequest(Base):
    __tablename__ = "student_leave_requests"

    StudentLeaveRequestId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    StudentCode: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    StudentLeaveConfigId: Mapped[int] = mapped_column(Integer, nullable=False)
    FromDate: Mapped[date] = mapped_column(Date, nullable=False)
    ToDate: Mapped[date] = mapped_column(Date, nullable=False)
    Reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    Status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    DecidedBy: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class StudentAttendanceProcessed(Base):
    __tablename__ = "student_attendance_processed"
    __table_args__ = (
        UniqueConstraint("StudentCode", "AttendanceDate", name="uq_student_att_code_date"),
    )

    StudentAttendanceId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    StudentCode: Mapped[str] = mapped_column(String(50), nullable=False)
    AttendanceDate: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    Status: Mapped[str] = mapped_column(String(20), nullable=False)  # Present/Late/HalfDay/Absent/Leave/WeeklyOff
    InTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    OutTime: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    LateMinutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    LeaveCode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    Source: Mapped[str] = mapped_column(String(10), nullable=False, default="Auto")  # Auto | Manual


class AdmsLog(Base):
    """What readers send to / receive from the push (ADMS) endpoints; see services/adms_log.py."""

    __tablename__ = "adms_log"

    AdmsLogId: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    SerialNumber: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    LoggedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    Direction: Mapped[str] = mapped_column(String(3), nullable=False)  # in | out
    Kind: Mapped[str] = mapped_column(String(60), nullable=False)
    Query: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    Body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    BodyLength: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
