-- Aveon empty database script  (generated 2026-09-25)
-- Creates the database and every table with no employee/attendance data.
-- Run as sysadmin in SSMS or:  sqlcmd -S <server> -i Aveon_EmptyDatabase.sql
-- Safe to re-run: existing tables and data are left untouched.

IF DB_ID(N'Aveon') IS NULL CREATE DATABASE [Aveon];
GO
USE [Aveon];
GO
-- ---------------------------------------------------------------- core tables
IF OBJECT_ID('dbo.devices', 'U') IS NULL
BEGIN
    EXEC(N'CREATE TABLE locations (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    Code NVARCHAR(50) NULL,
    Description NVARCHAR(250) NULL
);

CREATE TABLE devices (
    DeviceId INT IDENTITY(1,1) PRIMARY KEY,
    DeviceName NVARCHAR(255) NOT NULL,
    DeviceDirection NVARCHAR(255) NULL,
    SerialNumber NVARCHAR(255) NOT NULL UNIQUE,
    DeviceIPAddress NVARCHAR(50) NULL,
    TransactionStamp NVARCHAR(50) NOT NULL DEFAULT ''0'',
    LastPing DATETIME2 NULL,
    OpStamp NVARCHAR(255) NULL,
    [Timezone] NVARCHAR(50) NULL,
    ActivationCode NVARCHAR(250) NULL,
    LastReset DATETIME2 NULL,
    DeviceType NVARCHAR(255) NULL,
    IsAttendanceDevice NCHAR(1) NULL,
    LocationId INT NULL,
    CONSTRAINT FK_devices_locations FOREIGN KEY (LocationId) REFERENCES locations (Id)
);

CREATE TABLE employees (
    EmployeeId INT IDENTITY(1,1) PRIMARY KEY,
    EmployeeName NVARCHAR(250) NOT NULL,
    EmployeeCode NVARCHAR(250) NOT NULL UNIQUE,
    StringCode NVARCHAR(250) NOT NULL,
    NumericCode INT NOT NULL,
    EmployeeRFIDNumber NVARCHAR(255) NULL,
    EmployeeDevicePassword NVARCHAR(250) NULL,
    VerificationType NVARCHAR(2) NULL,
    [Role] NVARCHAR(15) NULL,
    Department NVARCHAR(50) NULL,
    LastPunch DATETIME2 NULL,
    LastPunchDeviceId INT NULL,
    LastPunchDirection NVARCHAR(50) NULL,
    AttendanceLocationId INT NULL,
    [Location] NVARCHAR(MAX) NULL
);

CREATE TABLE employeesbio (
    EmployeeBioId BIGINT IDENTITY(1,1) PRIMARY KEY,
    EmployeeCode NVARCHAR(250) NOT NULL,
    BioName NVARCHAR(50) NULL,
    BioDescription NVARCHAR(50) NULL,
    Bio NVARCHAR(MAX) NULL,
    MinorVer NVARCHAR(50) NULL,
    MajorVer NVARCHAR(50) NULL,
    CONSTRAINT FK_employeesbio_employees FOREIGN KEY (EmployeeCode) REFERENCES employees (EmployeeCode)
);

CREATE TABLE employeephotos (
    EmployeePhotoId BIGINT IDENTITY(1,1) PRIMARY KEY,
    EmployeeCode NVARCHAR(250) NOT NULL,
    DeviceId INT NULL,
    PhotoName NVARCHAR(50) NULL,
    PhotoMimeType NVARCHAR(100) NULL,
    PhotoData NVARCHAR(MAX) NOT NULL,
    [Source] NVARCHAR(50) NULL,
    [Checksum] NVARCHAR(128) NULL,
    CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_employeephotos_employees FOREIGN KEY (EmployeeCode) REFERENCES employees (EmployeeCode),
    CONSTRAINT FK_employeephotos_devices FOREIGN KEY (DeviceId) REFERENCES devices (DeviceId)
);

CREATE INDEX IX_employeephotos_EmployeeCode ON employeephotos (EmployeeCode);

CREATE TABLE deviceemployees (
    DeviceEmployeeId BIGINT IDENTITY(1,1) PRIMARY KEY,
    DeviceId INT NOT NULL,
    EmployeeId INT NOT NULL,
    [Role] NVARCHAR(50) NULL,
    Command NVARCHAR(50) NULL,
    [Status] NVARCHAR(50) NULL,
    SyncDate NVARCHAR(50) NULL,
    EmployeeCode NVARCHAR(50) NULL,
    IsDirtyDateTime DATETIME2 NULL,
    CONSTRAINT FK_deviceemployees_devices FOREIGN KEY (DeviceId) REFERENCES devices (DeviceId),
    CONSTRAINT FK_deviceemployees_employees FOREIGN KEY (EmployeeId) REFERENCES employees (EmployeeId)
);

CREATE TABLE devicecommands (
    DeviceCommandId INT IDENTITY(1,1) PRIMARY KEY,
    DeviceId INT NOT NULL,
    Title NVARCHAR(255) NULL,
    DeviceCommand NVARCHAR(MAX) NULL,
    [Status] NVARCHAR(255) NULL,
    [Type] NVARCHAR(255) NULL,
    CreationDate DATETIME2 NULL,
    ExecutionDate DATETIME2 NULL,
    DeviceCommandFace NVARCHAR(MAX) NULL,
    CONSTRAINT FK_devicecommands_devices FOREIGN KEY (DeviceId) REFERENCES devices (DeviceId)
);

CREATE TABLE devicelogs (
    DeviceLogId BIGINT IDENTITY(1,1) PRIMARY KEY,
    DeviceId INT NOT NULL,
    EmployeeCode NVARCHAR(50) NOT NULL,
    LogDate DATETIME2 NOT NULL,
    VerificationType NVARCHAR(2) NULL,
    GPS NVARCHAR(100) NULL,
    Direction NVARCHAR(50) NULL,
    WorkCode NVARCHAR(50) NULL,
    IsAttPhoto NCHAR(1) NULL,
    AttPhoto NVARCHAR(MAX) NULL,
    WebhookSyncStatus NCHAR(1) NULL,
    DownloadDate DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    AttDirectionCode NVARCHAR(50) NULL,
    CONSTRAINT FK_devicelogs_devices FOREIGN KEY (DeviceId) REFERENCES devices (DeviceId)
);

CREATE INDEX IX_devicelogs_LogDate ON devicelogs (LogDate);
CREATE INDEX IX_devicelogs_EmployeeCode_LogDate ON devicelogs (EmployeeCode, LogDate);

CREATE TABLE deviceoplogs (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    DeviceId INT NOT NULL,
    OPCode NVARCHAR(50) NULL,
    OPLogDate DATETIME2 NULL,
    CONSTRAINT FK_deviceoplogs_devices FOREIGN KEY (DeviceId) REFERENCES devices (DeviceId)
);

CREATE TABLE [users] (
    UserId INT IDENTITY(1,1) PRIMARY KEY,
    LoginName NVARCHAR(250) NOT NULL UNIQUE,
    LoginPassword NVARCHAR(250) NOT NULL,
    RoleName NVARCHAR(255) NULL,
    Permissions NVARCHAR(2000) NULL,
    [Locations] NVARCHAR(MAX) NULL,
    Blocked NVARCHAR(50) NULL,
    AuthToken NVARCHAR(100) NULL,
    Expiry NVARCHAR(50) NULL
);

CREATE TABLE mastersettings (
    [Name] NVARCHAR(50) PRIMARY KEY,
    [Value] NVARCHAR(MAX) NULL
);

-- NOTE: no seed user. The built-in administrator is ADMIN_USERNAME / ADMIN_PASSWORD
-- from backend\.env (see app/services/auth_service.py). Seeding a plain-text
-- ''admin123'' row here would remain a valid login on every installation.

INSERT INTO mastersettings ([Name], [Value]) VALUES
(''AttendanceDay'', ''01''),
(''AttendanceMonth'', ''01''),
(''Version'', ''BiometricServer 1.0'');');
END
GO
-- ---------------------------------------------------------------- remaining tables / columns
IF OBJECT_ID('dbo.shifts', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.shifts (
            ShiftId INT IDENTITY(1,1) PRIMARY KEY,
            ShiftName NVARCHAR(100) NOT NULL,
            ShortName NVARCHAR(20) NULL,
            StartTime CHAR(5) NOT NULL,
            EndTime CHAR(5) NOT NULL,
            GraceInMinutes INT NULL DEFAULT 0,
            GraceOutMinutes INT NULL DEFAULT 0,
            Break1Enabled CHAR(1) NULL DEFAULT 'N',
            Break1StartTime CHAR(5) NULL,
            Break1EndTime CHAR(5) NULL,
            Break2Enabled CHAR(1) NULL DEFAULT 'N',
            Break2StartTime CHAR(5) NULL,
            Break2EndTime CHAR(5) NULL,
            IsFlexibleShift CHAR(1) NULL DEFAULT 'N',
            PunchBeginBeforeMinutes INT NULL DEFAULT 60,
            PunchEndAfterMinutes INT NULL DEFAULT 120,
            GraceTimeMinutes INT NULL DEFAULT 10,
            PartialDayEnabled CHAR(1) NULL DEFAULT 'N',
            PartialDayWeekday NVARCHAR(20) NULL,
            PartialDayStartTime CHAR(5) NULL,
            PartialDayEndTime CHAR(5) NULL,
            IsDefault CHAR(1) NULL DEFAULT 'N',
            IsActive CHAR(1) NULL DEFAULT 'Y'
        );
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'ShortName') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD ShortName NVARCHAR(20) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'Break1Enabled') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD Break1Enabled CHAR(1) NULL CONSTRAINT DF_shifts_Break1Enabled DEFAULT 'N';
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'Break1StartTime') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD Break1StartTime CHAR(5) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'Break1EndTime') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD Break1EndTime CHAR(5) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'Break2Enabled') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD Break2Enabled CHAR(1) NULL CONSTRAINT DF_shifts_Break2Enabled DEFAULT 'N';
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'Break2StartTime') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD Break2StartTime CHAR(5) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'Break2EndTime') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD Break2EndTime CHAR(5) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'IsFlexibleShift') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD IsFlexibleShift CHAR(1) NULL CONSTRAINT DF_shifts_IsFlexibleShift DEFAULT 'N';
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'PunchBeginBeforeMinutes') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD PunchBeginBeforeMinutes INT NULL CONSTRAINT DF_shifts_PunchBeginBefore DEFAULT 60;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'PunchEndAfterMinutes') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD PunchEndAfterMinutes INT NULL CONSTRAINT DF_shifts_PunchEndAfter DEFAULT 120;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'GraceTimeMinutes') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD GraceTimeMinutes INT NULL CONSTRAINT DF_shifts_GraceTime DEFAULT 10;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'PartialDayEnabled') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD PartialDayEnabled CHAR(1) NULL CONSTRAINT DF_shifts_PartialDayEnabled DEFAULT 'N';
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'PartialDayWeekday') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD PartialDayWeekday NVARCHAR(20) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'PartialDayStartTime') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD PartialDayStartTime CHAR(5) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'PartialDayEndTime') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD PartialDayEndTime CHAR(5) NULL;
    END

    IF OBJECT_ID('dbo.shifts', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.shifts', 'IsDefault') IS NULL
    BEGIN
        ALTER TABLE dbo.shifts ADD IsDefault CHAR(1) NULL CONSTRAINT DF_shifts_IsDefault DEFAULT 'N';
    END

    IF OBJECT_ID('dbo.attendance_categories', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.attendance_categories (
            CategoryId INT IDENTITY(1,1) PRIMARY KEY,
            CategoryName NVARCHAR(120) NOT NULL,
            ShortName NVARCHAR(30) NULL,
            OTFormula NVARCHAR(50) NULL DEFAULT 'Total Duration - Shift Hours',
            MinOTMinutes INT NULL DEFAULT 30,
            MaxOTMinutes INT NULL DEFAULT 0,
            GraceLateComingMinutes INT NULL DEFAULT 15,
            GraceEarlyGoingMinutes INT NULL DEFAULT 15,
            WeeklyOff1Enabled CHAR(1) NULL DEFAULT 'N',
            WeeklyOff1Weekday NVARCHAR(20) NULL,
            WeeklyOff2Enabled CHAR(1) NULL DEFAULT 'N',
            WeeklyOff2Weekday NVARCHAR(20) NULL,
            WeeklyOff2Occurrence1 CHAR(1) NULL DEFAULT 'N',
            WeeklyOff2Occurrence2 CHAR(1) NULL DEFAULT 'N',
            WeeklyOff2Occurrence3 CHAR(1) NULL DEFAULT 'N',
            WeeklyOff2Occurrence4 CHAR(1) NULL DEFAULT 'N',
            WeeklyOff2Occurrence5 CHAR(1) NULL DEFAULT 'N',
            ConsiderEarlyComingPunch CHAR(1) NULL DEFAULT 'N',
            ConsiderOnlyFirstLastPunch CHAR(1) NULL DEFAULT 'Y',
            ConsiderLateGoingPunch CHAR(1) NULL DEFAULT 'Y',
            DeductBreakHours CHAR(1) NULL DEFAULT 'N',
            NeglectLastInPunch CHAR(1) NULL DEFAULT 'N',
            HalfDayIfWorkDurationLessThanMinutes INT NULL DEFAULT 240,
            AbsentIfWorkDurationLessThanMinutes INT NULL DEFAULT 120,
            PartialDayCalculateHalfDayIfWorkDurationLessThanMinutes INT NULL DEFAULT 0,
            PartialDayCalculateAbsentIfWorkDurationLessThanMinutes INT NULL DEFAULT 0,
            MarkWeeklyOffHolidayAsAbsentPrefixAbsent CHAR(1) NULL DEFAULT 'N',
            MarkWeeklyOffHolidayAsAbsentSuffixAbsent CHAR(1) NULL DEFAULT 'N',
            MarkWeeklyOffHolidayAsAbsentBothSidesAbsent CHAR(1) NULL DEFAULT 'N',
            MarkHalfDayWhenLateForDays INT NULL DEFAULT 0,
            MarkHalfDayIfLateByMinutes INT NULL DEFAULT 0,
            MarkHalfDayIfEarlyGoingByMinutes INT NULL DEFAULT 0,
            IsActive CHAR(1) NULL DEFAULT 'Y'
        );
        CREATE INDEX IX_attendance_categories_Name ON dbo.attendance_categories (CategoryName);
    END

    IF OBJECT_ID('dbo.employees', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.employees', 'CategoryId') IS NULL
    BEGIN
        ALTER TABLE dbo.employees ADD CategoryId INT NULL;
    END

    IF OBJECT_ID('dbo.devices', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.devices', 'DeviceIPAddress') IS NULL
    BEGIN
        ALTER TABLE dbo.devices ADD DeviceIPAddress NVARCHAR(50) NULL;
    END

    IF OBJECT_ID('dbo.employeephotos', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.employeephotos (
            EmployeePhotoId BIGINT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode NVARCHAR(250) NOT NULL,
            DeviceId INT NULL,
            PhotoName NVARCHAR(50) NULL,
            PhotoMimeType NVARCHAR(100) NULL,
            PhotoData NVARCHAR(MAX) NOT NULL,
            [Source] NVARCHAR(50) NULL,
            [Checksum] NVARCHAR(128) NULL,
            CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
            UpdatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE INDEX IX_employeephotos_EmployeeCode ON dbo.employeephotos (EmployeeCode);
    END

    IF OBJECT_ID('dbo.manualentries', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.manualentries (
            ManualEntryId INT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode NVARCHAR(250) NOT NULL,
            LogDate DATETIME2 NOT NULL,
            EntryType NVARCHAR(20) NOT NULL DEFAULT 'Manual',
            InTime CHAR(5) NULL,
            OutTime CHAR(5) NULL,
            Reason NVARCHAR(500) NULL,
            Status NVARCHAR(20) NOT NULL DEFAULT 'Pending',
            AppliedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE INDEX IX_manualentries_EmployeeCode ON dbo.manualentries (EmployeeCode);
    END

    IF OBJECT_ID('dbo.manualentries', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.manualentries', 'EntryType') IS NULL
    BEGIN
        ALTER TABLE dbo.manualentries ADD EntryType NVARCHAR(20) NOT NULL DEFAULT 'Manual';
    END

    IF OBJECT_ID('dbo.leaveconfigs', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.leaveconfigs (
            LeaveConfigId INT IDENTITY(1,1) PRIMARY KEY,
            Code NVARCHAR(50) NOT NULL,
            Name NVARCHAR(200) NOT NULL,
            MaxPerYear INT NULL,
            IsPaid CHAR(1) NULL DEFAULT 'Y',
            IsActive CHAR(1) NULL DEFAULT 'Y'
        );
    END

    IF OBJECT_ID('dbo.leaverequests', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.leaverequests (
            LeaveRequestId INT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode NVARCHAR(250) NOT NULL,
            LeaveConfigId INT NOT NULL,
            FromDate DATETIME2 NOT NULL,
            ToDate DATETIME2 NOT NULL,
            Reason NVARCHAR(500) NULL,
            Status NVARCHAR(20) NOT NULL DEFAULT 'Pending',
            AppliedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE INDEX IX_leaverequests_EmployeeCode ON dbo.leaverequests (EmployeeCode);
    END

    IF OBJECT_ID('dbo.role_config', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.role_config (
            RoleName NVARCHAR(50) NOT NULL PRIMARY KEY,
            PermissionsJson NVARCHAR(MAX) NULL
        );
    END

    IF OBJECT_ID('dbo.transferjobs', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.transferjobs (
            TransferJobId   INT IDENTITY(1,1) PRIMARY KEY,
            Status          NVARCHAR(50)  NOT NULL DEFAULT 'pending',
            Phase           NVARCHAR(20)  NULL DEFAULT 'face',
            TotalUsers      INT           NOT NULL DEFAULT 0,
            BatchSize       INT           NOT NULL DEFAULT 500,
            TotalBatches    INT           NOT NULL DEFAULT 1,
            FaceQueued      INT           NULL DEFAULT 0,
            FaceExecuted    INT           NULL DEFAULT 0,
            FaceFailed      INT           NULL DEFAULT 0,
            FingerQueued    INT           NULL DEFAULT 0,
            FingerExecuted  INT           NULL DEFAULT 0,
            FingerFailed    INT           NULL DEFAULT 0,
            IncludeFace     CHAR(1)       NOT NULL DEFAULT 'Y',
            IncludeFinger   CHAR(1)       NOT NULL DEFAULT 'Y',
            IncludeCard     CHAR(1)       NOT NULL DEFAULT 'Y',
            IncludePhoto    CHAR(1)       NOT NULL DEFAULT 'N',
            SequentialBiometrics CHAR(1)  NOT NULL DEFAULT 'Y',
            EmployeeCodes   NVARCHAR(MAX) NULL,
            TargetDeviceIds NVARCHAR(MAX) NULL,
            SourceDeviceId  INT           NULL,
            CreationDate    DATETIME2     NULL DEFAULT SYSUTCDATETIME(),
            StartDate       DATETIME2     NULL,
            CompletionDate  DATETIME2     NULL,
            ErrorMessage    NVARCHAR(MAX) NULL
        );
    END

    IF OBJECT_ID('dbo.devicecommands', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.devicecommands', 'TransferJobId') IS NULL
    BEGIN
        ALTER TABLE dbo.devicecommands ADD TransferJobId INT NULL;
    END

    IF OBJECT_ID('dbo.devicecommands', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.devicecommands', 'Phase') IS NULL
    BEGIN
        ALTER TABLE dbo.devicecommands ADD Phase NVARCHAR(20) NULL;
    END

    IF OBJECT_ID('dbo.devicecommands', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.devicecommands', 'RetryCount') IS NULL
    BEGIN
        ALTER TABLE dbo.devicecommands ADD RetryCount INT NULL DEFAULT 0;
    END

    IF OBJECT_ID('dbo.devicecommands', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.devicecommands', 'SentDate') IS NULL
    BEGIN
        ALTER TABLE dbo.devicecommands ADD SentDate DATETIME2 NULL;
    END

    IF OBJECT_ID('dbo.attendance_processed', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.attendance_processed (
            AttendanceProcessedId INT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode      NVARCHAR(250) NOT NULL,
            AttendanceDate    DATE          NOT NULL,
            Status            NVARCHAR(2)   NOT NULL,
            StatusLabel       NVARCHAR(50)  NULL,
            ShiftId           INT           NULL,
            ShiftName         NVARCHAR(255) NULL,
            ShiftTime         NVARCHAR(100) NULL,
            FirstIn           NVARCHAR(5)   NULL,
            LastOut           NVARCHAR(5)   NULL,
            TotalLogs         INT           NOT NULL DEFAULT 0,
            ActualWorkMinutes INT           NOT NULL DEFAULT 0,
            Remarks           NVARCHAR(255) NULL,
            ProcessedAt       DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT uq_attendance_processed_emp_date UNIQUE (EmployeeCode, AttendanceDate)
        );
        CREATE INDEX ix_attendance_processed_date ON dbo.attendance_processed (AttendanceDate);
        CREATE INDEX ix_attendance_processed_emp ON dbo.attendance_processed (EmployeeCode);
    END

    -- Reporting columns added to attendance_processed after initial release.
    IF OBJECT_ID('dbo.attendance_processed', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.attendance_processed', 'LeaveCode') IS NULL
        ALTER TABLE dbo.attendance_processed ADD LeaveCode NVARCHAR(50) NULL;
    IF OBJECT_ID('dbo.attendance_processed', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.attendance_processed', 'LateMinutes') IS NULL
        ALTER TABLE dbo.attendance_processed ADD LateMinutes INT NOT NULL DEFAULT 0;
    IF OBJECT_ID('dbo.attendance_processed', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.attendance_processed', 'EarlyMinutes') IS NULL
        ALTER TABLE dbo.attendance_processed ADD EarlyMinutes INT NOT NULL DEFAULT 0;
    IF OBJECT_ID('dbo.attendance_processed', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.attendance_processed', 'OTMinutes') IS NULL
        ALTER TABLE dbo.attendance_processed ADD OTMinutes INT NOT NULL DEFAULT 0;

    -- Per-employee leave entitlement (mirrors eTimeTrackLite EMPLOYEELEAVES).
    IF OBJECT_ID('dbo.employee_leave_balances', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.employee_leave_balances (
            EmployeeLeaveBalanceId INT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode   NVARCHAR(250) NOT NULL,
            LeaveConfigId  INT           NOT NULL,
            LeaveYear      INT           NOT NULL,
            AllowedLeaves  FLOAT         NOT NULL DEFAULT 0,
            CarriedForward FLOAT         NOT NULL DEFAULT 0,
            CONSTRAINT uq_emp_leave_balance UNIQUE (EmployeeCode, LeaveConfigId, LeaveYear)
        );
        CREATE INDEX ix_emp_leave_balance_emp ON dbo.employee_leave_balances (EmployeeCode);
    END

    -- HR profile columns on employees (added incrementally, all nullable).
    IF OBJECT_ID('dbo.employees', 'U') IS NOT NULL
    BEGIN
        IF COL_LENGTH('dbo.employees','Designation')     IS NULL ALTER TABLE dbo.employees ADD Designation NVARCHAR(120) NULL;
        IF COL_LENGTH('dbo.employees','JoiningDate')      IS NULL ALTER TABLE dbo.employees ADD JoiningDate NVARCHAR(10) NULL;
        IF COL_LENGTH('dbo.employees','GuardianName')     IS NULL ALTER TABLE dbo.employees ADD GuardianName NVARCHAR(150) NULL;
        IF COL_LENGTH('dbo.employees','DateOfBirth')      IS NULL ALTER TABLE dbo.employees ADD DateOfBirth NVARCHAR(10) NULL;
        IF COL_LENGTH('dbo.employees','BloodGroup')       IS NULL ALTER TABLE dbo.employees ADD BloodGroup NVARCHAR(10) NULL;
        IF COL_LENGTH('dbo.employees','Address')          IS NULL ALTER TABLE dbo.employees ADD Address NVARCHAR(500) NULL;
        IF COL_LENGTH('dbo.employees','AgreementYears')   IS NULL ALTER TABLE dbo.employees ADD AgreementYears NVARCHAR(10) NULL;
        IF COL_LENGTH('dbo.employees','PersonalEmail')    IS NULL ALTER TABLE dbo.employees ADD PersonalEmail NVARCHAR(150) NULL;
        IF COL_LENGTH('dbo.employees','OfficialEmail')    IS NULL ALTER TABLE dbo.employees ADD OfficialEmail NVARCHAR(150) NULL;
        IF COL_LENGTH('dbo.employees','ContactNo')        IS NULL ALTER TABLE dbo.employees ADD ContactNo NVARCHAR(20) NULL;
        IF COL_LENGTH('dbo.employees','OfficialNo')       IS NULL ALTER TABLE dbo.employees ADD OfficialNo NVARCHAR(20) NULL;
        IF COL_LENGTH('dbo.employees','EmergencyNo')      IS NULL ALTER TABLE dbo.employees ADD EmergencyNo NVARCHAR(20) NULL;
        IF COL_LENGTH('dbo.employees','MaritalStatus')    IS NULL ALTER TABLE dbo.employees ADD MaritalStatus NVARCHAR(20) NULL;
        IF COL_LENGTH('dbo.employees','AadharNo')         IS NULL ALTER TABLE dbo.employees ADD AadharNo NVARCHAR(20) NULL;
        IF COL_LENGTH('dbo.employees','PanNo')            IS NULL ALTER TABLE dbo.employees ADD PanNo NVARCHAR(20) NULL;
        IF COL_LENGTH('dbo.employees','Salary')           IS NULL ALTER TABLE dbo.employees ADD Salary NVARCHAR(30) NULL;
        IF COL_LENGTH('dbo.employees','UAN')              IS NULL ALTER TABLE dbo.employees ADD UAN NVARCHAR(30) NULL;
        IF COL_LENGTH('dbo.employees','BiometricType')    IS NULL ALTER TABLE dbo.employees ADD BiometricType NVARCHAR(50) NULL;
        IF COL_LENGTH('dbo.employees','CurrentStatus')    IS NULL ALTER TABLE dbo.employees ADD CurrentStatus NVARCHAR(20) NULL;
        IF COL_LENGTH('dbo.employees','LastWorkingDay')   IS NULL ALTER TABLE dbo.employees ADD LastWorkingDay NVARCHAR(10) NULL;
        IF COL_LENGTH('dbo.employees','ReasonForLeaving') IS NULL ALTER TABLE dbo.employees ADD ReasonForLeaving NVARCHAR(500) NULL;
    END

    -- Mess token module: meal windows + issued tokens.
    IF OBJECT_ID('dbo.mess_meals', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.mess_meals (
            MessMealId INT IDENTITY(1,1) PRIMARY KEY,
            MealType  NVARCHAR(30) NOT NULL UNIQUE,
            StartTime NVARCHAR(5)  NOT NULL,
            EndTime   NVARCHAR(5)  NOT NULL,
            SortOrder INT          NOT NULL DEFAULT 0,
            IsActive  NVARCHAR(1)  NOT NULL DEFAULT 'Y'
        );
        INSERT INTO dbo.mess_meals (MealType, StartTime, EndTime, SortOrder, IsActive) VALUES
            ('Breakfast', '07:00', '10:00', 1, 'Y'),
            ('Lunch',     '12:00', '15:00', 2, 'Y'),
            ('Dinner',    '19:00', '22:30', 3, 'Y');
    END

    IF OBJECT_ID('dbo.mess_tokens', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.mess_tokens (
            MessTokenId   INT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode  NVARCHAR(250) NOT NULL,
            EmployeeName  NVARCHAR(250) NULL,
            MealType      NVARCHAR(30)  NOT NULL,
            TokenNumber   INT           NOT NULL,
            TokenDate     DATE          NOT NULL,
            CreatedAt     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
            PrintStatus   NVARCHAR(20)  NOT NULL DEFAULT 'Printed',
            ReprintCount  INT           NOT NULL DEFAULT 0,
            LastReprintAt DATETIME2     NULL,
            CONSTRAINT uq_mess_token_emp_meal_day UNIQUE (EmployeeCode, MealType, TokenDate)
        );
        CREATE INDEX ix_mess_tokens_date ON dbo.mess_tokens (TokenDate);
        CREATE INDEX ix_mess_tokens_emp ON dbo.mess_tokens (EmployeeCode);
    END

    -- Organization / Department / Employee-Type masters (per-organization departments).
    IF OBJECT_ID('dbo.organizations', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.organizations (
            OrganizationId INT IDENTITY(1,1) PRIMARY KEY,
            OrgName  NVARCHAR(250) NOT NULL,
            Address  NVARCHAR(500) NULL,
            IsActive NVARCHAR(1)   NULL DEFAULT 'Y'
        );
        -- Seed the default organization from the receipt/report org name setting.
        INSERT INTO dbo.organizations (OrgName, IsActive)
        SELECT COALESCE((SELECT TOP 1 Value FROM dbo.mastersettings WHERE Name = 'OrgName' AND Value IS NOT NULL AND Value <> ''), 'Aveon'), 'Y';
    END

    IF OBJECT_ID('dbo.departments', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.departments (
            DepartmentId   INT IDENTITY(1,1) PRIMARY KEY,
            OrganizationId INT NOT NULL,
            DepartmentName NVARCHAR(150) NOT NULL,
            IsActive       NVARCHAR(1)   NULL DEFAULT 'Y'
        );
        -- Migrate distinct free-text departments already on employees into the master
        -- list under the default organization.
        INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive)
        SELECT (SELECT MIN(OrganizationId) FROM dbo.organizations), LTRIM(RTRIM(Department)), 'Y'
        FROM dbo.employees
        WHERE Department IS NOT NULL AND LTRIM(RTRIM(Department)) <> ''
        GROUP BY LTRIM(RTRIM(Department));
    END

    IF OBJECT_ID('dbo.employee_types', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.employee_types (
            EmployeeTypeId INT IDENTITY(1,1) PRIMARY KEY,
            TypeName NVARCHAR(100) NOT NULL,
            IsActive NVARCHAR(1)   NULL DEFAULT 'Y'
        );
        INSERT INTO dbo.employee_types (TypeName, IsActive) VALUES
            ('Staff', 'Y'), ('Faculty', 'Y'), ('PhD Student', 'Y'), ('Intern', 'Y'), ('Contract', 'Y');
    END

    IF OBJECT_ID('dbo.employees', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.employees', 'OrganizationId') IS NULL
        ALTER TABLE dbo.employees ADD OrganizationId INT NULL;
    IF OBJECT_ID('dbo.employees', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.employees', 'EmployeeTypeId') IS NULL
        ALTER TABLE dbo.employees ADD EmployeeTypeId INT NULL;

    -- Face-recognition attendance: embeddings enrolled from photos (camera_service).
    IF OBJECT_ID('dbo.employeefaceembeddings', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.employeefaceembeddings (
            EmployeeFaceEmbeddingId INT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode    NVARCHAR(250) NOT NULL,
            Embedding       NVARCHAR(MAX) NOT NULL,
            DetScore        FLOAT         NULL,
            EmployeePhotoId INT           NULL,
            [Source]        NVARCHAR(50)  NULL DEFAULT 'Enroll',
            CreatedAt       DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE INDEX IX_employeefaceembeddings_EmployeeCode ON dbo.employeefaceembeddings (EmployeeCode);
    END

    -- Leave-type columns added after initial release.
    IF OBJECT_ID('dbo.leaveconfigs', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.leaveconfigs', 'ConsiderWeeklyOff') IS NULL
        ALTER TABLE dbo.leaveconfigs ADD ConsiderWeeklyOff NVARCHAR(1) NULL DEFAULT 'N';
    IF OBJECT_ID('dbo.leaveconfigs', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.leaveconfigs', 'ConsiderHoliday') IS NULL
        ALTER TABLE dbo.leaveconfigs ADD ConsiderHoliday NVARCHAR(1) NULL DEFAULT 'N';
    IF OBJECT_ID('dbo.leaveconfigs', 'U') IS NOT NULL
       AND COL_LENGTH('dbo.leaveconfigs', 'CarryForwardLimit') IS NULL
        ALTER TABLE dbo.leaveconfigs ADD CarryForwardLimit INT NULL DEFAULT 0;

    -- Leave approval (HOD / Manager -> Principal / Director).
    IF OBJECT_ID('dbo.users', 'U') IS NOT NULL AND COL_LENGTH('dbo.users', 'EmployeeCode') IS NULL
        ALTER TABLE dbo.users ADD EmployeeCode NVARCHAR(250) NULL;

    IF OBJECT_ID('dbo.leave_approvals', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.leave_approvals (
            LeaveApprovalId INT IDENTITY(1,1) PRIMARY KEY,
            LeaveRequestId  INT           NOT NULL,
            Level           INT           NOT NULL,
            Action          NVARCHAR(20)  NOT NULL,
            ByUser          NVARCHAR(250) NULL,
            ByRole          NVARCHAR(100) NULL,
            Remarks         NVARCHAR(500) NULL,
            ActionAt        DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE INDEX ix_leave_approvals_req ON dbo.leave_approvals (LeaveRequestId);
    END

    -- Shift rosters + holidays (same shape as existing installs; no FK, because
    -- employees.EmployeeCode is NVARCHAR while roster codes are VARCHAR).
    IF OBJECT_ID('dbo.shiftrosters', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.shiftrosters (
            ShiftRosterId INT IDENTITY(1,1) PRIMARY KEY,
            EmployeeCode  VARCHAR(250) NOT NULL,
            ShiftId       INT          NOT NULL,
            FromDate      DATETIME     NOT NULL,
            ToDate        DATETIME     NULL
        );
    END

    IF OBJECT_ID('dbo.holidays', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.holidays (
            HolidayId   INT IDENTITY(1,1) PRIMARY KEY,
            HolidayDate DATETIME     NOT NULL,
            HolidayName VARCHAR(200) NOT NULL,
            Category    VARCHAR(20)  NOT NULL,
            IsActive    VARCHAR(1)   NULL
        );
    END

    -- Designation master (dropdown on the employee form); seeded from existing employee values.
    IF OBJECT_ID('dbo.designations', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.designations (
            DesignationId   INT IDENTITY(1,1) PRIMARY KEY,
            DesignationName NVARCHAR(150) NOT NULL,
            IsActive        NVARCHAR(1)   NULL DEFAULT 'Y'
        );
        -- EXEC defers compilation: employees.Designation is added earlier in this
        -- same batch, so on a fresh database a direct reference fails to compile.
        EXEC(N'INSERT INTO dbo.designations (DesignationName, IsActive)
        SELECT LTRIM(RTRIM(Designation)), ''Y''
        FROM dbo.employees
        WHERE Designation IS NOT NULL AND LTRIM(RTRIM(Designation)) <> ''''
        GROUP BY LTRIM(RTRIM(Designation));');
    END

    -- Student attendance module (separate shifts / leave; departments shared).
    IF OBJECT_ID('dbo.student_shifts', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.student_shifts (
            StudentShiftId INT IDENTITY(1,1) PRIMARY KEY,
            ShiftName      NVARCHAR(100) NOT NULL,
            StartTime      NVARCHAR(5)   NOT NULL,
            EndTime        NVARCHAR(5)   NOT NULL,
            GraceInMinutes INT           NOT NULL DEFAULT 10,
            HalfDayMinutes INT           NOT NULL DEFAULT 240,
            WeeklyOff      NVARCHAR(20)  NULL DEFAULT 'Sunday',
            IsActive       NVARCHAR(1)   NOT NULL DEFAULT 'Y'
        );
        INSERT INTO dbo.student_shifts (ShiftName, StartTime, EndTime, GraceInMinutes, HalfDayMinutes, WeeklyOff)
        VALUES ('General (Students)', '09:00', '16:00', 10, 240, 'Sunday');
    END

    IF OBJECT_ID('dbo.students', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.students (
            StudentId      INT IDENTITY(1,1) PRIMARY KEY,
            StudentCode    NVARCHAR(50)  NOT NULL,
            StudentName    NVARCHAR(250) NOT NULL,
            DepartmentId   INT           NOT NULL,
            YearOfStudy    INT           NOT NULL,
            Section        NVARCHAR(20)  NULL,
            RollNo         NVARCHAR(50)  NULL,
            GuardianName   NVARCHAR(250) NULL,
            GuardianPhone  NVARCHAR(30)  NULL,
            DateOfBirth    NVARCHAR(10)  NULL,
            StudentShiftId INT           NULL,
            IsActive       NVARCHAR(1)   NOT NULL DEFAULT 'Y',
            CreatedAt      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT uq_students_code UNIQUE (StudentCode),
            CONSTRAINT ck_students_year CHECK (YearOfStudy BETWEEN 1 AND 4)
        );
        CREATE INDEX ix_students_dept_year ON dbo.students (DepartmentId, YearOfStudy);
    END

    IF OBJECT_ID('dbo.students', 'U') IS NOT NULL AND COL_LENGTH('dbo.students', 'Status') IS NULL
        ALTER TABLE dbo.students ADD Status NVARCHAR(20) NOT NULL CONSTRAINT df_students_status DEFAULT 'Active';
    IF OBJECT_ID('dbo.students', 'U') IS NOT NULL AND COL_LENGTH('dbo.students', 'StatusDate') IS NULL
        ALTER TABLE dbo.students ADD StatusDate NVARCHAR(10) NULL;
    IF OBJECT_ID('dbo.students', 'U') IS NOT NULL AND COL_LENGTH('dbo.students', 'StatusNote') IS NULL
        ALTER TABLE dbo.students ADD StatusNote NVARCHAR(250) NULL;

    IF OBJECT_ID('dbo.student_leave_configs', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.student_leave_configs (
            StudentLeaveConfigId INT IDENTITY(1,1) PRIMARY KEY,
            Code       NVARCHAR(10)  NOT NULL UNIQUE,
            Name       NVARCHAR(100) NOT NULL,
            MaxPerYear INT           NOT NULL DEFAULT 0,
            IsPaid     NVARCHAR(1)   NOT NULL DEFAULT 'Y',
            IsActive   NVARCHAR(1)   NOT NULL DEFAULT 'Y'
        );
        INSERT INTO dbo.student_leave_configs (Code, Name, MaxPerYear, IsPaid) VALUES
            ('SL', 'Sick Leave', 12, 'Y'), ('CL', 'Casual Leave', 8, 'Y'), ('OD', 'On Duty', 0, 'Y');
    END

    IF OBJECT_ID('dbo.student_leave_requests', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.student_leave_requests (
            StudentLeaveRequestId INT IDENTITY(1,1) PRIMARY KEY,
            StudentCode          NVARCHAR(50)  NOT NULL,
            StudentLeaveConfigId INT           NOT NULL,
            FromDate  DATE          NOT NULL,
            ToDate    DATE          NOT NULL,
            Reason    NVARCHAR(500) NULL,
            Status    NVARCHAR(20)  NOT NULL DEFAULT 'Pending',
            DecidedBy NVARCHAR(100) NULL,
            CreatedAt DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE INDEX ix_student_leave_code ON dbo.student_leave_requests (StudentCode);
    END

    IF OBJECT_ID('dbo.student_attendance_processed', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.student_attendance_processed (
            StudentAttendanceId INT IDENTITY(1,1) PRIMARY KEY,
            StudentCode    NVARCHAR(50) NOT NULL,
            AttendanceDate DATE         NOT NULL,
            Status         NVARCHAR(20) NOT NULL,
            InTime         NVARCHAR(5)  NULL,
            OutTime        NVARCHAR(5)  NULL,
            LateMinutes    INT          NOT NULL DEFAULT 0,
            LeaveCode      NVARCHAR(10) NULL,
            [Source]       NVARCHAR(10) NOT NULL DEFAULT 'Auto',
            CONSTRAINT uq_student_att_code_date UNIQUE (StudentCode, AttendanceDate)
        );
        CREATE INDEX ix_student_att_date ON dbo.student_attendance_processed (AttendanceDate);
    END

    -- Student module provision (off by default; toggled from Canteen Settings).
    IF NOT EXISTS (SELECT 1 FROM dbo.mastersettings WHERE Name = 'StudentModuleEnabled')
        INSERT INTO dbo.mastersettings (Name, Value) VALUES ('StudentModuleEnabled', 'N');
GO
-- ---------------------------------------------------------------- default masters
IF NOT EXISTS (SELECT 1 FROM dbo.organizations)
    INSERT INTO dbo.organizations (OrgName, IsActive) VALUES (N'Default', 'Y');
DECLARE @org INT = (SELECT MIN(OrganizationId) FROM dbo.organizations);
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'CSE') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'CSE', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'EEE') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'EEE', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'ECE') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'ECE', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'MECH') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'MECH', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'CIVIL') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'CIVIL', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'IT') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'IT', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'AI & DS') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'AI & DS', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.departments WHERE DepartmentName = N'Administration') INSERT INTO dbo.departments (OrganizationId, DepartmentName, IsActive) VALUES (@org, N'Administration', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.designations WHERE DesignationName = N'HOD') INSERT INTO dbo.designations (DesignationName, IsActive) VALUES (N'HOD', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.designations WHERE DesignationName = N'Professor') INSERT INTO dbo.designations (DesignationName, IsActive) VALUES (N'Professor', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.designations WHERE DesignationName = N'Associate Professor') INSERT INTO dbo.designations (DesignationName, IsActive) VALUES (N'Associate Professor', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.designations WHERE DesignationName = N'Assistant Professor') INSERT INTO dbo.designations (DesignationName, IsActive) VALUES (N'Assistant Professor', 'Y');
IF NOT EXISTS (SELECT 1 FROM dbo.designations WHERE DesignationName = N'Non-Teaching') INSERT INTO dbo.designations (DesignationName, IsActive) VALUES (N'Non-Teaching', 'Y');
-- The web administrator is ADMIN_USERNAME / ADMIN_PASSWORD from backend\.env; no user row is seeded.
DELETE FROM dbo.users WHERE LoginName = 'admin' AND LoginPassword = 'admin123';
GO
DECLARE @n INT; SELECT @n = COUNT(*) FROM sys.tables;
PRINT 'Aveon database [Aveon] ready: ' + CAST(@n AS varchar) + ' tables';
GO
