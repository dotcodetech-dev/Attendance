-- =====================================================================
-- Aveon database schema.
--
-- IMPORTANT: run this against YOUR Aveon database (e.g. AIFace), NOT master.
--   * In SSMS: select the target database in the toolbar dropdown first
--     (or right-click the database -> New Query), then execute.
--   * Or from a shell:  sqlcmd -S <server> -d <YourDatabase> -i schema.sql
--
-- The guard below aborts (without creating anything) if run against master,
-- so tables never land in the wrong database by accident.
-- =====================================================================
IF DB_NAME() = 'master'
BEGIN
    RAISERROR('ABORTED: do not run schema.sql against master. Select your Aveon database (e.g. AIFace) first, then re-run.', 16, 1);
    SET NOEXEC ON;
END
GO

DROP TABLE IF EXISTS deviceemployees;
DROP TABLE IF EXISTS devicecommands;
DROP TABLE IF EXISTS devicelogs;
DROP TABLE IF EXISTS deviceoplogs;
DROP TABLE IF EXISTS employeephotos;
DROP TABLE IF EXISTS employeesbio;
DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS [users];
DROP TABLE IF EXISTS mastersettings;
DROP TABLE IF EXISTS locations;

CREATE TABLE locations (
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
    TransactionStamp NVARCHAR(50) NOT NULL DEFAULT '0',
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
-- 'admin123' row here would remain a valid login on every installation.

INSERT INTO mastersettings ([Name], [Value]) VALUES
('AttendanceDay', '01'),
('AttendanceMonth', '01'),
('Version', 'BiometricServer 1.0');
GO

-- Re-enable execution (only matters if the master guard above tripped).
SET NOEXEC OFF;
GO
