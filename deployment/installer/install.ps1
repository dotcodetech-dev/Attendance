<#
.SYNOPSIS
  One-click installer / upgrader for a Windows client server (brand from brand.txt).

.DESCRIPTION
  Run via INSTALL.cmd (elevates automatically). Every step detects first and
  only acts when needed, so re-running it is an in-place UPGRADE:
  backend\.env, the database and all logs are preserved.

    1. Prerequisites (offline, from .\prereqs): VC++ runtime, Python 3.12,
       ODBC Driver 18, IIS + URL Rewrite + ARR, SQL Server Express (only when
       no SQL Server is installed on this machine).
    2. Application files -> InstallDir (default C:\<Brand>), Python venv from
       the bundled wheels (no internet needed).
    3. backend\.env (first install only), database create/upgrade (never drops data).
    4. eSSL 32-bit SDK, IIS site on port 80, firewall rule.
    5. Scheduled tasks: <Brand>Backend, <Brand>Watchdog, <Brand>AttendanceRecalc,
       <Brand>FetchAttendance. Then verifies http://localhost/health.

.PARAMETER DryRun     Detect and report only; change nothing.
.PARAMETER Uninstall  Remove tasks, IIS site and firewall rule (keeps files, DB, prerequisites).
#>
param(
    [string] $ConfigFile = (Join-Path $PSScriptRoot "install-config.psd1"),
    [string] $InstallDir,
    [switch] $DryRun,
    [switch] $Uninstall,
    [switch] $SkipPrereqs
)

$ErrorActionPreference = "Stop"
$pkg = $PSScriptRoot
$script:RebootNeeded = $false
# Brand baked in by build-client-package.ps1 -Brand (package root brand.txt). It names the
# install folder, IIS site, database, firewall rule, registry key and scheduled tasks.
$Brand = "Aveon"
$brandFile = Join-Path $PSScriptRoot "brand.txt"
if (Test-Path $brandFile) { $b = (Get-Content $brandFile -Raw).Trim(); if ($b) { $Brand = $b } }
$brandSlug = ($Brand -replace '[^A-Za-z0-9]', '')
if (-not $brandSlug) { $brandSlug = "Aveon" }
$TaskNames = @("${brandSlug}Backend", "${brandSlug}Watchdog", "${brandSlug}AttendanceRecalc", "${brandSlug}FetchAttendance")
$TemplateNames = @{ "${brandSlug}Backend" = "AveonBackend"; "${brandSlug}Watchdog" = "AveonWatchdog";
                    "${brandSlug}AttendanceRecalc" = "AveonAttendanceRecalc"; "${brandSlug}FetchAttendance" = "AveonFetchAttendance" }
$RegKey = "HKLM:\SOFTWARE\$brandSlug"
$FirewallRule = "$brandSlug HTTP"
$AppCmd = Join-Path $env:windir "System32\inetsrv\appcmd.exe"

# Bundled installers (file names must match build-client-package.ps1).
$Prereq = @{
    VcRedist   = "VC_redist.x64.exe"
    Python     = "python-3.12.7-amd64.exe"
    Odbc       = "msodbcsql18.msi"
    UrlRewrite = "rewrite_amd64_en-US.msi"
    Arr        = "requestRouter_amd64.msi"
    SqlExpress = "SQLEXPR_x64_ENU.exe"
}

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
$logPath = Join-Path $pkg "install.log"
function Log([string]$msg, [string]$color = "Gray") {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line -ForegroundColor $color
    try { Add-Content -Path $logPath -Value $line } catch {}
}
function Section([string]$title) { Log ""; Log "=== $title ===" "Cyan" }
function Ok([string]$msg)   { Log "  OK    $msg" "Green" }
function Act([string]$msg)  { if ($DryRun) { Log "  WOULD $msg" "Yellow" } else { Log "  DO    $msg" "White" } }
function Warn([string]$msg) { Log "  WARN  $msg" "Yellow" }
function Fail([string]$msg) { Log "  FAIL  $msg" "Red"; throw $msg }

function Get-PrereqPath([string]$key) {
    $path = Join-Path $pkg ("prereqs\" + $Prereq[$key])
    if (-not (Test-Path $path)) { Fail "Missing bundled installer: prereqs\$($Prereq[$key])" }
    return $path
}

# Run an installer and accept the "success" exit codes (0, reboot-required, already-newer).
function Invoke-Installer([string]$file, [string[]]$arguments, [string]$label) {
    if ($file -like "*.msi") {
        $arguments = @("/i", "`"$file`"") + $arguments
        $file = "msiexec.exe"
    }
    $proc = Start-Process -FilePath $file -ArgumentList $arguments -Wait -PassThru
    $code = $proc.ExitCode
    if ($code -in 3010, 1641) { $script:RebootNeeded = $true; Ok "$label installed (reboot requested)"; return }
    if ($code -in 0, 1638)    { Ok "$label installed"; return }
    Fail "$label installer exited with code $code"
}

function Invoke-AppCmd([string[]]$arguments) {
    $out = & $AppCmd @arguments 2>&1
    if ($LASTEXITCODE -ne 0) { Fail ("appcmd {0} failed: {1}" -f ($arguments -join " "), ($out -join " ")) }
    return $out
}

function New-RandomSecret([int]$bytes = 48) {
    $buffer = New-Object byte[] $bytes
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return ([Convert]::ToBase64String($buffer)).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

# Best-effort native command: ignore its exit code AND its stderr. Under this
# script's $ErrorActionPreference='Stop', a native tool (schtasks/appcmd/iisreset)
# writing to stderr through '2>&1' turns into a terminating NativeCommandError, so
# ending a task that does not exist, or deleting a site that is already gone, would
# abort the whole install. Use this for operations that legitimately no-op when the
# target is absent or already in the desired state.
function Quiet([scriptblock]$block) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $block 2>$null | Out-Null } catch { } finally { $ErrorActionPreference = $prev }
}

function Stop-Backend([string]$root) {
    # Pause the watchdog first so it cannot relaunch the backend while files are being replaced
    # (the task is re-created and re-enabled when the services are registered at the end).
    foreach ($t in "${brandSlug}Watchdog", "${brandSlug}Backend", "${brandSlug}FetchAttendance") {
        Quiet { schtasks /change /tn $t /disable }
        Quiet { schtasks /end /tn $t }
    }
    # Find the backend WITHOUT WMI (Get-CimInstance Win32_Process can hang for minutes on
    # servers with a sick WMI repository): by listening port, then by executable path.
    $venvDir = Join-Path $root "backend\.venv"
    $pids = @()
    try { $pids += @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess) } catch {}
    try { $pids += @(Get-Process python -ErrorAction Stop | Where-Object { $_.Path -and $_.Path.StartsWith($venvDir, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -ExpandProperty Id) } catch {}
    foreach ($procId in ($pids | Where-Object { $_ -gt 4 } | Select-Object -Unique)) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; Log "  stopped backend pid $procId" } catch {}
    }
    Start-Sleep -Seconds 1
}

function Find-Python312 {
    foreach ($hive in "HKLM:", "HKCU:") {
        $key = "$hive\SOFTWARE\Python\PythonCore\3.12\InstallPath"
        if (Test-Path $key) {
            $item = Get-ItemProperty $key
            $exe = $item.ExecutablePath
            if (-not $exe -and $item.'(default)') { $exe = Join-Path $item.'(default)' "python.exe" }
            if ($exe -and (Test-Path $exe)) { return $exe }
        }
    }
    $fallback = Join-Path $env:ProgramFiles "Python312\python.exe"
    if (Test-Path $fallback) { return $fallback }
    return $null
}

function Test-LocalSqlHost([string]$h) {
    return $h -in @("localhost", ".", "127.0.0.1", "(local)", $env:COMPUTERNAME)
}

# Try a SQL connection with .NET SqlClient (always present in Windows PowerShell).
# Without -User it uses the current Windows account. Returns @{ok; sysadmin; error}.
function Test-SqlConnection([string]$server, [string]$User, [string]$Password) {
    $cs = "Server=$server;Database=master;Encrypt=False;TrustServerCertificate=True;Connect Timeout=8;"
    $cs += if ($User) { "User ID=$User;Password=$Password;" } else { "Integrated Security=True;" }
    $conn = New-Object System.Data.SqlClient.SqlConnection $cs
    try {
        $conn.Open()
        $cmd = $conn.CreateCommand(); $cmd.CommandText = "SELECT IS_SRVROLEMEMBER('sysadmin')"
        $isAdmin = [int]$cmd.ExecuteScalar()
        return @{ ok = $true; sysadmin = ($isAdmin -eq 1); error = "" }
    } catch {
        $m = $_.Exception.Message; if ($_.Exception.InnerException) { $m = $_.Exception.InnerException.Message }
        return @{ ok = $false; sysadmin = $false; error = $m }
    } finally { $conn.Dispose() }
}

# Using the installing admin's Windows login (must be SQL sysadmin): enable mixed-mode
# auth if needed, create a SQL login for Aveon, create the database and make the login
# its owner. Avoids needing the sa password on servers shared with other products.
function New-AveonSqlLogin([string]$server, [string]$login, [string]$password, [string]$database) {
    $cs = "Server=$server;Database=master;Integrated Security=True;Encrypt=False;TrustServerCertificate=True;Connect Timeout=15;"
    $conn = New-Object System.Data.SqlClient.SqlConnection $cs
    $conn.Open()
    try {
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = "SELECT CAST(SERVERPROPERTY('IsIntegratedSecurityOnly') AS int), CAST(SERVERPROPERTY('InstanceName') AS nvarchar(100))"
        $rd = $cmd.ExecuteReader(); $null = $rd.Read(); $winOnly = $rd.GetInt32(0); $inst = if ($rd.IsDBNull(1)) { "" } else { $rd.GetString(1) }; $rd.Close()
        if ($winOnly -eq 1) {
            Log "  enabling SQL Server authentication (mixed mode) - instance restart required"
            $cmd.CommandText = "EXEC xp_instance_regwrite N'HKEY_LOCAL_MACHINE', N'Software\Microsoft\MSSQLServer\MSSQLServer', N'LoginMode', REG_DWORD, 2"
            $null = $cmd.ExecuteNonQuery()
        }
        $pw = $password.Replace("'", "''")
        $cmd.CommandText = @"
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'$login')
    CREATE LOGIN [$login] WITH PASSWORD = N'$pw', CHECK_POLICY = OFF, CHECK_EXPIRATION = OFF, DEFAULT_DATABASE = master;
ELSE
    ALTER LOGIN [$login] WITH PASSWORD = N'$pw', CHECK_POLICY = OFF;
ALTER LOGIN [$login] ENABLE;
IF DB_ID(N'$database') IS NULL CREATE DATABASE [$database];
ALTER AUTHORIZATION ON DATABASE::[$database] TO [$login];
"@
        $null = $cmd.ExecuteNonQuery()
    } finally { $conn.Dispose() }
    if ($winOnly -eq 1) {
        $svc = if ($inst) { "MSSQL`$$inst" } else { "MSSQLSERVER" }
        Restart-Service $svc -Force
        Start-Sleep -Seconds 5
    }
    $t = Test-SqlConnection $server -User $login -Password $password
    if (-not $t.ok) { Fail "created login '$login' but cannot connect with it: $($t.error)" }
    Ok "SQL login '$login' ready (owner of database '$database')"
}

# --------------------------------------------------------------------------
# Elevation + package sanity
# --------------------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $DryRun) {
    throw "Run this installer as Administrator (double-click INSTALL.cmd, it elevates automatically)."
}
if (-not [Environment]::Is64BitOperatingSystem) { throw "$Brand requires 64-bit Windows." }
# Windows Server 2012 R2 / 8.1 ship PowerShell 4; this script needs 5.1 (Windows Management Framework 5.1).
if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "PowerShell $($PSVersionTable.PSVersion) is too old. Install Windows Management Framework 5.1 (KB3191564, free from Microsoft), restart, then run INSTALL.cmd again."
}
$osVersion = [Environment]::OSVersion.Version
if ($osVersion -lt [version]"6.3") { throw "Windows 8.1 / Server 2012 R2 or newer is required (this is $osVersion)." }
$legacyOs = $osVersion -lt [version]"10.0"   # 8.1 / 2012 R2: bundled SQL Express 2025 cannot be installed

# Files extracted from a downloaded zip carry Mark-of-the-Web; unblock so installers run silently.
if (-not $DryRun) { Get-ChildItem $pkg -Recurse -File | Unblock-File -ErrorAction SilentlyContinue }

Log "$Brand installer - package $pkg $(if ($DryRun) { '(DRY RUN - no changes)' })" "Cyan"

# --------------------------------------------------------------------------
# Uninstall
# --------------------------------------------------------------------------
if ($Uninstall) {
    $root = $InstallDir
    if (-not $root -and (Test-Path $RegKey)) { $root = (Get-ItemProperty $RegKey).InstallDir }
    $site = $brandSlug
    if (Test-Path $RegKey) { $s = (Get-ItemProperty $RegKey).SiteName; if ($s) { $site = $s } }
    Section "Uninstall"
    foreach ($t in $TaskNames) { Act "delete task $t"; if (-not $DryRun) { Quiet { schtasks /end /tn $t }; Quiet { schtasks /delete /f /tn $t } } }
    if ($root -and -not $DryRun) { Stop-Backend $root }
    if (Test-Path $AppCmd) {
        Act "remove IIS site '$site' and app pool"
        if (-not $DryRun) { Quiet { & $AppCmd delete site $site }; Quiet { & $AppCmd delete apppool $site } }
    }
    Act "remove firewall rule '$FirewallRule'"
    if (-not $DryRun) { Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule }
    Log ""
    Log "Uninstalled. Kept: files in '$root', the SQL database, and prerequisites." "Green"
    exit 0
}

# --------------------------------------------------------------------------
# 1. Configuration
# --------------------------------------------------------------------------
Section "Configuration"
$cfg = @{}
if (Test-Path $ConfigFile) { $cfg = Import-PowerShellDataFile $ConfigFile; Ok "loaded $ConfigFile" }

$previous = if (Test-Path $RegKey) { Get-ItemProperty $RegKey } else { $null }
# LAN address = the IPv4 on the interface that carries the default route (skips
# Hyper-V / VPN adapters that have no gateway).
$detectedIp = $null
$gwIf = (Get-NetRoute -DestinationPrefix "0.0.0.0/0" -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1).InterfaceIndex
if ($gwIf) { $detectedIp = (Get-NetIPAddress -InterfaceIndex $gwIf -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress }
if (-not $detectedIp) {
    $detectedIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
}

function Get-Setting([string]$name, [string]$default, [string]$prompt, [switch]$Secret, [switch]$Required,
                     [string]$Pattern = "", [string]$Hint = "") {
    $value = $cfg[$name]
    if ($value) {
        if ($Pattern -and $value -notmatch $Pattern) { Fail "install-config.psd1: $name='$value' is not valid. $Hint" }
        return [string]$value
    }
    if ($DryRun) { return $default }
    while ($true) {
        $label = if ($default -and -not $Secret) { "$prompt [$default]" } else { $prompt }
        if ($Secret) {
            $secure = Read-Host "  $label (typing is hidden - type it, then press Enter)" -AsSecureString
            $value = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        } else {
            $value = Read-Host "  $label"
        }
        if (-not $value) { $value = $default }
        if (-not $value -and $Required) { Write-Host "  A value is required." -ForegroundColor Yellow; continue }
        if ($value -and $Pattern -and $value -notmatch $Pattern) {
            Write-Host "  '$value' is not valid here. $Hint" -ForegroundColor Yellow; continue
        }
        return $value
    }
}

Ok "brand: $Brand"
$defaultDir = if ($previous -and $previous.InstallDir) { $previous.InstallDir } else { "C:\$brandSlug" }
if (-not $InstallDir) { $InstallDir = Get-Setting "InstallDir" $defaultDir "Install folder" }
# Must be an absolute local path like C:\Aveon - a stray "y" or "yes" is not a folder.
while ($InstallDir -notmatch '^[A-Za-z]:\\[^<>:"|?*]+$' -or $InstallDir -match '^[A-Za-z]:\\?$') {
    if ($DryRun -or $cfg["InstallDir"]) { Fail "Install folder '$InstallDir' is not a valid absolute path (example: C:\$brandSlug)." }
    Write-Host "  '$InstallDir' is not a valid folder. Enter a full path like C:\$brandSlug (or press Enter for the default)." -ForegroundColor Yellow
    $InstallDir = Read-Host "  Install folder [$defaultDir]"
    if (-not $InstallDir) { $InstallDir = $defaultDir }
}
$InstallDir = $InstallDir.TrimEnd("\")
$envPath = Join-Path $InstallDir "backend\.env"
$isUpgrade = Test-Path $envPath
$sqlReconfigure = $false

$defaultSite = if ($previous -and $previous.SiteName) { $previous.SiteName } else { $brandSlug }
$SiteName = Get-Setting "SiteName" $defaultSite "IIS site name"
$SitePort = [int](Get-Setting "SitePort" "80" "Web/device port (a number; normally 80)" -Pattern '^\d{1,5}$' -Hint "Enter a number such as 80.")
$ServerAddress = Get-Setting "ServerAddress" $detectedIp "Server IP devices will use"

if ($isUpgrade) {
    Ok "existing install found at $InstallDir - upgrading (backend\.env kept)"
    $envLines = Get-Content $envPath
    function Read-Env([string]$key, [string]$default) {
        $line = $envLines | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
        if ($line) { return ($line -split "=", 2)[1].Trim().Trim("'").Trim('"') } else { return $default }
    }
    $SqlHost = Read-Env "SQLSERVER_HOST" "localhost"
    $SqlServer = Read-Env "SQLSERVER_SERVER" ""
    $SqlPort = Read-Env "SQLSERVER_PORT" "1433"
    $SqlDatabase = Read-Env "SQLSERVER_DATABASE" $brandSlug
    $SqlUser = Read-Env "SQLSERVER_USER" "sa"
    $SqlPassword = Read-Env "SQLSERVER_PASSWORD" ""
    $SqlInstallInstance = $null; $SqlCreateLogin = $false
    # The saved login can be stale (SQL reinstalled, sa password changed, server moved):
    # verify it now and, if it fails, ask for the SQL details again like a fresh install.
    if (-not $DryRun) {
        $target = if ($SqlServer) { $SqlServer } else { "$SqlHost,$SqlPort" }
        $t = Test-SqlConnection $target -User $SqlUser -Password $SqlPassword
        if ($t.ok) { Ok "saved SQL login '$SqlUser' works on $target" }
        else {
            Warn "saved SQL login '$SqlUser' no longer works on ${target}: $($t.error)"
            Warn "backend\.env will be updated with the SQL details you enter now (everything else in it is kept)."
            $sqlReconfigure = $true
        }
    }
}
if (-not $isUpgrade -or $sqlReconfigure) {
    if ($sqlReconfigure) { Write-Host ""; Write-Host "  SQL Server details (press Enter to accept the value in brackets):" -ForegroundColor Cyan }
    $SqlHost     = Get-Setting "SqlHost" $(if ($isUpgrade -and $SqlHost) { $SqlHost } else { "localhost" }) "1) SQL Server host (this machine = localhost; or name, IP, host\INSTANCE)"
    # People naturally type "localhost\SQLEXPRESS" or "192.168.1.5\SQL2019" here: split it.
    # An instance name and a port must never be combined (the port wins and the
    # instance is silently ignored, which is exactly how "host\INSTANCE,1433" times out).
    $hostInstance = $null
    if ($SqlHost -match '^\s*([^\\,]+?)\s*\\\s*([^\\,]+?)\s*$') { $SqlHost = $Matches[1]; $hostInstance = $Matches[2] }
    elseif ($SqlHost -match '^\s*([^\\,]+?)\s*,\s*(\d+)\s*$') { $SqlHost = $Matches[1]; $cfg["SqlPort"] = $Matches[2] }
    $SqlHost = $SqlHost.Trim()
    if ($SqlHost -in @(".", "(local)", "127.0.0.1", $env:COMPUTERNAME)) { $SqlHost = "localhost" }
    $SqlPort     = if ($hostInstance) { "1433" } else { Get-Setting "SqlPort" $(if ($isUpgrade -and $SqlPort) { $SqlPort } else { "1433" }) "2) SQL Server port (a number; normally 1433)" -Pattern '^\d{1,5}$' -Hint "Enter a number such as 1433." }
    $SqlDatabase = Get-Setting "SqlDatabase" $(if ($isUpgrade -and $SqlDatabase) { $SqlDatabase } else { $brandSlug }) "3) Database name (letters/digits only, e.g. $brandSlug)" -Pattern '^[A-Za-z0-9_]+$' -Hint "Only letters, digits and _ - this is the DATABASE NAME, not a password."
    $SqlServer   = ""            # "host\INSTANCE" for named instances, else empty (host,port is used)
    $SqlInstallInstance = $null  # set when SQL Express must be installed (MSSQLSERVER or <BRAND>)
    $SqlCreateLogin = $false     # set when the login is created via Windows auth (admin is SQL sysadmin)

    $localSql = Test-LocalSqlHost $SqlHost
    $instances = @()
    if ($localSql) {
        $instances = @(Get-Service -Name "MSSQLSERVER", 'MSSQL$*' -ErrorAction SilentlyContinue |
            ForEach-Object { if ($_.Name -eq "MSSQLSERVER") { "MSSQLSERVER" } else { $_.Name.Substring(6) } })
    }
    if ($localSql -and $instances.Count -eq 0) {
        Ok "no SQL Server on this machine - SQL Server Express will be installed"
        $SqlInstallInstance = "MSSQLSERVER"
        $SqlUser = "sa"
    } else {
        if ($localSql) {
            Ok ("SQL Server instances found: " + ($instances -join ", "))
            # Ask which one (default: what was typed after the backslash, else the default
            # instance, else SQLEXPRESS, else the first).
            $prefer = if ($hostInstance) { $hostInstance }
                      elseif ($instances -contains "MSSQLSERVER") { "MSSQLSERVER" }
                      elseif ($instances -contains "SQLEXPRESS") { "SQLEXPRESS" } else { $instances[0] }
            $match = $instances | Where-Object { $_ -ieq $prefer } | Select-Object -First 1
            if ($match) { $prefer = $match }
            # Only ask when there is actually a choice to make.
            $chosen = if (($hostInstance -and $match) -or $instances.Count -eq 1) { $prefer } else { Get-Setting "SqlInstance" $prefer "SQL instance to use ($($instances -join ' / '))" }
            $match = $instances | Where-Object { $_ -ieq $chosen } | Select-Object -First 1
            if (-not $match) { Fail "SQL instance '$chosen' does not exist on this machine (found: $($instances -join ', '))." }
            $chosen = $match
            if ($chosen -ne "MSSQLSERVER") {
                $SqlServer = "localhost\$chosen"
                # Named instances are found through SQL Browser (locally shared memory also works).
                if (-not $DryRun) { try { Set-Service SQLBrowser -StartupType Automatic -ErrorAction Stop; Start-Service SQLBrowser -ErrorAction Stop } catch {} }
            }
        } elseif ($hostInstance) {
            $SqlServer = "$SqlHost\$hostInstance"
            Ok "remote named instance $SqlServer (needs SQL Browser running on that server, UDP 1434 open)"
        }
        $SqlUser = Get-Setting "SqlUser" $(if ($isUpgrade -and $SqlUser) { $SqlUser } else { "sa" }) "4) SQL login name (normally sa)"
    }
    $SqlPassword = Get-Setting "SqlPassword" "" "5) SQL password for '$SqlUser'$(if ($SqlInstallInstance) { ' (becomes the new sa password)' })" -Secret -Required
    $AdminPassword = if ($isUpgrade) { "" } else { Get-Setting "AdminPassword" "" "Web admin password (user 'admin')" -Secret -Required }
    foreach ($p in @($SqlPassword, $AdminPassword)) {
        if ($p -match "[;'`"]") { Fail "Passwords must not contain ; ' or `" characters." }
    }
    if (-not $DryRun -and $SqlDatabase -notmatch "^[A-Za-z0-9_]+$") { Fail "Database name may only contain letters, digits and _." }

    # Verify the SQL login NOW, before anything is installed or copied.
    if (-not $SqlInstallInstance -and -not $DryRun) {
        $target = if ($SqlServer) { $SqlServer } else { "$SqlHost,$SqlPort" }
        $t = Test-SqlConnection $target -User $SqlUser -Password $SqlPassword
        # Wrong password / wrong instance: let the operator re-enter the details manually
        # as many times as needed before falling back to the automatic options.
        if (-not $t.ok -and $cfg["SqlPassword"]) { Warn "the SQL password saved in install-config.psd1 no longer works - please enter it again."; $cfg["SqlPassword"] = "" }
        while (-not $t.ok) {
            Warn "SQL login '$SqlUser' failed on ${target}: $($t.error)"
            $again = Read-Host "  Enter the SQL details again? [Y/n]  (n = use automatic options)"
            if ($again -and $again -notmatch '^[Yy]') { break }
            if ($localSql -and $instances.Count -gt 1) {
                $chosen = Read-Host "  SQL instance ($($instances -join ' / ')) [$chosen]"
                if (-not $chosen) { $chosen = $prefer }
                if ($instances -notcontains $chosen) { Write-Host "  no such instance" -ForegroundColor Yellow; continue }
                $SqlServer = if ($chosen -eq "MSSQLSERVER") { "" } else { "localhost\$chosen" }
            } elseif (-not $localSql) {
                $h = Read-Host "  SQL Server host (name, IP, or host\INSTANCE) [$(if ($SqlServer) { $SqlServer } else { $SqlHost })]"
                if ($h) {
                    if ($h -match '^\s*([^\\,]+?)\s*\\\s*([^\\,]+?)\s*$') { $SqlHost = $Matches[1]; $SqlServer = "$($Matches[1])\$($Matches[2])" }
                    else { $SqlHost = $h.Trim(); $SqlServer = "" }
                }
            }
            $u = Read-Host "  SQL login [$SqlUser]"; if ($u) { $SqlUser = $u }
            $secure = Read-Host "  SQL password for '$SqlUser'" -AsSecureString
            $SqlPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
            if ($SqlPassword -match "[;'`"]") { Write-Host "  password must not contain ; ' or `"" -ForegroundColor Yellow; continue }
            $target = if ($SqlServer) { $SqlServer } else { "$SqlHost,$SqlPort" }
            $t = Test-SqlConnection $target -User $SqlUser -Password $SqlPassword
        }
        if ($t.ok) { Ok "SQL login '$SqlUser' works on $target" }
        else {
            Warn "SQL login '$SqlUser' failed on ${target}: $($t.error)"
            $w = Test-SqlConnection $target
            if ($w.ok -and $w.sysadmin) {
                # The installing Windows account is a SQL administrator: create a dedicated
                # login for Aveon so the (unknown) sa password is never needed.
                $SqlUser = $brandSlug.ToLower()
                $SqlCreateLogin = $true
                Ok "Windows login is SQL sysadmin - a dedicated login '$SqlUser' will be created with the password you entered"
            } elseif ($localSql -and (Test-Path (Join-Path $pkg "prereqs\$($Prereq.SqlExpress)"))) {
                $reason = if ($w.ok) { "Windows login has no admin rights on it" } else { "Windows login cannot connect either" }
                $ownInstance = $brandSlug.ToUpper(); if ($ownInstance.Length -gt 16) { $ownInstance = $ownInstance.Substring(0, 16) }
                Warn "$reason. $Brand can install its OWN SQL Server Express instance '$ownInstance' instead (uses ~1 GB, does not touch the other instances)."
                $ans = if ($cfg["InstallOwnInstance"]) { [string]$cfg["InstallOwnInstance"] } else { Read-Host "  Install a separate SQL instance '$ownInstance'? [Y/n]" }
                if ($ans -and $ans -notmatch '^[Yy]') { Fail "Cannot log in to SQL Server. Re-run with the correct password for '$SqlUser' on $target." }
                $SqlInstallInstance = $ownInstance; $SqlServer = "localhost\$ownInstance"; $SqlUser = "sa"
            } else {
                Fail "Cannot log in to SQL Server $target as '$SqlUser'. Ask the SQL administrator for the sa password (or a login with dbcreator rights) and run INSTALL.cmd again."
            }
        }
    }
    if ($SqlInstallInstance) {
        # SQL Server enforces password policy for sa: 8+ chars, 3 of upper/lower/digit/symbol.
        $classes = @(($SqlPassword -cmatch "[A-Z]"), ($SqlPassword -cmatch "[a-z]"), ($SqlPassword -match "[0-9]"), ($SqlPassword -match "[^A-Za-z0-9]")) | Where-Object { $_ }
        if (-not $DryRun -and ($SqlPassword.Length -lt 8 -or $classes.Count -lt 3)) { Fail "SQL password too weak for SQL Server Express: use 8+ characters with at least 3 of upper, lower, digit, symbol." }
    }
}
Ok "InstallDir=$InstallDir  Site=${SiteName}:$SitePort  ServerAddress=$ServerAddress"

# Remember every answer in install-config.psd1 so the next run of INSTALL.cmd (upgrade or
# re-install) asks nothing. Passwords are included - keep the setup folder private.
if (-not $DryRun) {
    function _q([string]$v) { return "'" + ([string]$v).Replace("'", "''") + "'" }
    $remember = [ordered]@{
        InstallDir = $InstallDir; SiteName = $SiteName; SitePort = [string]$SitePort; ServerAddress = $ServerAddress
        SqlHost = $SqlHost; SqlPort = [string]$SqlPort; SqlDatabase = $SqlDatabase; SqlUser = $SqlUser; SqlPassword = $SqlPassword
        SqlInstance = $(if ($SqlServer -match '\\(.+)$') { $Matches[1] } else { "" })
        AdminPassword = $(if ($AdminPassword) { $AdminPassword } elseif ($cfg["AdminPassword"]) { [string]$cfg["AdminPassword"] } else { "" })
        InstallOwnInstance = $(if ($cfg["InstallOwnInstance"]) { [string]$cfg["InstallOwnInstance"] } else { "" })
    }
    $psd = @("# Answers saved by INSTALL.cmd on $(Get-Date -Format 'yyyy-MM-dd HH:mm'). Delete a value to be asked again;",
             "# delete this file to be asked everything. Contains passwords - keep this folder private.", "@{")
    foreach ($k in $remember.Keys) { $psd += "    {0,-18} = {1}" -f $k, (_q $remember[$k]) }
    $psd += "}"
    try { [IO.File]::WriteAllLines($ConfigFile, $psd, (New-Object Text.UTF8Encoding($false))); Ok "answers saved to $(Split-Path $ConfigFile -Leaf) - next run will not ask again" }
    catch { Warn "could not save answers to ${ConfigFile}: $($_.Exception.Message)" }
}

# --------------------------------------------------------------------------
# 2. Prerequisites
# --------------------------------------------------------------------------
Section "Prerequisites"
if ($SkipPrereqs) { Warn "skipped (-SkipPrereqs)" } else {

    # SQL Server (decided in the Configuration step): install an Express instance when needed.
    $sqlServices = @(Get-Service -Name "MSSQLSERVER", 'MSSQL$*' -ErrorAction SilentlyContinue)
    if (-not $SqlInstallInstance) {
        if ($sqlServices.Count) { Ok ("SQL Server: " + (($sqlServices | ForEach-Object { "$($_.Name) ($($_.Status))" }) -join ", ")) }
        else { Ok "SQL Server is remote ($SqlHost)" }
        foreach ($svc in $sqlServices) {
            if ($svc.Status -ne "Running" -and -not $DryRun) { Set-Service $svc.Name -StartupType Automatic; Start-Service $svc.Name }
        }
    } else {
        $svcName = if ($SqlInstallInstance -eq "MSSQLSERVER") { "MSSQLSERVER" } else { "MSSQL`$$SqlInstallInstance" }
        Act "install SQL Server Express instance '$SqlInstallInstance' (SQL auth, TCP enabled)"
        if ($legacyOs) {
            Fail ("The bundled SQL Server Express (2025) needs Windows Server 2016 / Windows 10 or newer. On this OS ($osVersion) " +
                  "install SQL Server 2017 Express (or 2016 SP2 Express) yourself first, or point SqlHost at another SQL Server, then run INSTALL.cmd again.")
        }
        if (-not (Test-Path (Join-Path $pkg "prereqs\$($Prereq.SqlExpress)"))) {
            Fail "This package has no SQL Express media. Install SQL Server first, or set SqlHost in install-config.psd1 to an existing server."
        }
        # SQL Setup's RebootRequiredCheck rule fails on a pending restart, so check first
        # and give a clear instruction instead of a cryptic setup error.
        $pending = (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending") -or
                   (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired") -or
                   ((Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -ErrorAction SilentlyContinue).PendingFileRenameOperations)
        if ($pending -and -not $DryRun) { Fail "Windows has a RESTART PENDING; SQL Server setup cannot run. Restart this server, then run INSTALL.cmd again." }
        if (-not $DryRun) {
            $extract = Join-Path $env:TEMP "AveonSqlSetup"
            if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
            $p = Start-Process (Get-PrereqPath "SqlExpress") -ArgumentList "/Q", "/x:`"$extract`"" -Wait -PassThru
            if ($p.ExitCode -ne 0) { Fail "SQL Express extraction failed ($($p.ExitCode))" }
            Log "  running SQL Server setup (5-15 minutes)..."
            Invoke-Installer (Join-Path $extract "SETUP.EXE") @(
                "/Q", "/ACTION=Install", "/FEATURES=SQLENGINE", "/INSTANCENAME=$SqlInstallInstance",
                "/SECURITYMODE=SQL", "/SAPWD=`"$SqlPassword`"", "/SQLSYSADMINACCOUNTS=`"BUILTIN\Administrators`"",
                "/TCPENABLED=1", "/UPDATEENABLED=0", "/IACCEPTSQLSERVERLICENSETERMS") "SQL Server Express"
            Set-Service $svcName -StartupType Automatic
            Start-Service $svcName
            if ($SqlInstallInstance -ne "MSSQLSERVER") {
                # Named instance: SQL Browser lets remote tools find it; locally shared memory is used.
                Set-Service SQLBrowser -StartupType Automatic -ErrorAction SilentlyContinue
                Start-Service SQLBrowser -ErrorAction SilentlyContinue
            }
        }
    }
    if ($SqlCreateLogin -and -not $DryRun) {
        Act "create SQL login '$SqlUser' and database '$SqlDatabase' (via Windows authentication)"
        New-AveonSqlLogin $(if ($SqlServer) { $SqlServer } else { "$SqlHost,$SqlPort" }) $SqlUser $SqlPassword $SqlDatabase
    }
    # VC++ 2015-2022 x64 runtime. After a Windows in-place upgrade the System32 DLL
    # can be ancient while the registry claims "installed" -> use /repair then.
    $vcDll = Join-Path $env:windir "System32\vcruntime140.dll"
    $vcVer = if (Test-Path $vcDll) { (Get-Item $vcDll).VersionInfo.FileVersionRaw } else { $null }
    if ($vcVer -and $vcVer -ge [version]"14.40.0.0") { Ok "VC++ runtime $vcVer" }
    else {
        Act "install VC++ runtime (current System32 DLL: $vcVer)"
        if (-not $DryRun) {
            Invoke-Installer (Get-PrereqPath "VcRedist") @("/install", "/quiet", "/norestart") "VC++ runtime"
            $vcVer = if (Test-Path $vcDll) { (Get-Item $vcDll).VersionInfo.FileVersionRaw } else { $null }
            if (-not $vcVer -or $vcVer -lt [version]"14.40.0.0") {
                # "Already installed" per registry but the DLL is stale -> /repair rewrites it.
                Invoke-Installer (Get-PrereqPath "VcRedist") @("/repair", "/quiet", "/norestart") "VC++ runtime (repair)"
            }
        }
    }

    # Python 3.12 (all users, so SYSTEM tasks can run it).
    $python = Find-Python312
    if ($python) { Ok "Python 3.12 at $python" }
    else {
        Act "install Python 3.12 (all users)"
        if (-not $DryRun) {
            $target = Join-Path $env:ProgramFiles "Python312"
            Invoke-Installer (Get-PrereqPath "Python") @("/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0", "Include_launcher=1", "TargetDir=`"$target`"") "Python 3.12"
            $python = Find-Python312
            if (-not $python) { Fail "Python 3.12 not found after install." }
        }
    }

    # ODBC Driver 18 for SQL Server.
    if (Test-Path "HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Driver 18 for SQL Server") { Ok "ODBC Driver 18" }
    else {
        Act "install ODBC Driver 18 for SQL Server"
        if (-not $DryRun) { Invoke-Installer (Get-PrereqPath "Odbc") @("/qn", "/norestart", "IACCEPTMSODBCSQLLICENSETERMS=YES") "ODBC Driver 18" }
    }

    # IIS web server role.
    if ((Get-Service W3SVC -ErrorAction SilentlyContinue) -and (Test-Path $AppCmd)) { Ok "IIS" }
    else {
        Act "enable IIS (static content, default document, request filtering, console)"
        if (-not $DryRun) {
            # Server vs client OS without WMI: Install-WindowsFeature only exists on Server SKUs.
            $isServer = [bool](Get-Command Install-WindowsFeature -ErrorAction SilentlyContinue)
            if ($isServer) {
                $r = Install-WindowsFeature Web-Server, Web-Static-Content, Web-Default-Doc, Web-Http-Errors, Web-Filtering, Web-Stat-Compression, Web-Mgmt-Console
                if ($r.RestartNeeded -eq "Yes") { $script:RebootNeeded = $true }
            } else {
                $features = "IIS-WebServerRole", "IIS-WebServer", "IIS-CommonHttpFeatures", "IIS-StaticContent",
                            "IIS-DefaultDocument", "IIS-HttpErrors", "IIS-RequestFiltering", "IIS-Security",
                            "IIS-HttpCompressionStatic", "IIS-Performance", "IIS-ManagementConsole", "IIS-WebServerManagementTools"
                $r = Enable-WindowsOptionalFeature -Online -All -NoRestart -FeatureName $features
                if ($r.RestartNeeded) { $script:RebootNeeded = $true }
            }
            Ok "IIS enabled"
        }
    }

    # URL Rewrite + ARR (reverse proxy /api, /iclock, /health -> uvicorn :8000).
    $modulesInstalled = $false
    if (Test-Path (Join-Path $env:windir "System32\inetsrv\rewrite.dll")) { Ok "IIS URL Rewrite" }
    else { Act "install IIS URL Rewrite 2.1"; if (-not $DryRun) { Invoke-Installer (Get-PrereqPath "UrlRewrite") @("/qn", "/norestart") "URL Rewrite"; $modulesInstalled = $true } }

    if (Test-Path (Join-Path $env:ProgramFiles "IIS\Application Request Routing\requestRouter.dll")) { Ok "IIS ARR" }
    else { Act "install IIS Application Request Routing 3.0"; if (-not $DryRun) { Invoke-Installer (Get-PrereqPath "Arr") @("/qn", "/norestart") "ARR"; $modulesInstalled = $true } }

    if ($modulesInstalled) {
        # New global modules are only picked up by a fresh IIS process.
        Quiet { & iisreset /noforce }
        Ok "IIS restarted to load new modules"
    }

    if (Test-Path $AppCmd) {
        $proxy = (& $AppCmd list config -section:system.webServer/proxy 2>$null) -join " "
        if ($proxy -match 'enabled="true"') { Ok "ARR proxy enabled" }
        else {
            Act "enable ARR proxy"
            if (-not $DryRun) { Invoke-AppCmd @("set", "config", "-section:system.webServer/proxy", "/enabled:True", "/commit:apphost") | Out-Null }
        }
    }


}

if (-not $python) { $python = Find-Python312 }

# --------------------------------------------------------------------------
# 3. Application files + Python environment
# --------------------------------------------------------------------------
Section "Application files"
if ($isUpgrade) { Act "stop running backend for upgrade"; if (-not $DryRun) { Stop-Backend $InstallDir } }

$copies = @(
    @{ src = "app\backend";  dst = "backend";  mirror = $false },
    @{ src = "app\frontend\dist"; dst = "frontend\dist"; mirror = $true },
    @{ src = "app\database"; dst = "database"; mirror = $false },
    @{ src = "app\deployment"; dst = "deployment"; mirror = $false }
)
foreach ($c in $copies) {
    $src = Join-Path $pkg $c.src
    $dst = Join-Path $InstallDir $c.dst
    if (-not (Test-Path $src)) { Fail "package is missing $($c.src)" }
    Act "copy $($c.src) -> $dst"
    if (-not $DryRun) {
        $mode = if ($c.mirror) { "/MIR" } else { "/E" }
        # Never overwrite the client's .env or logs; never touch the venv.
        robocopy $src $dst $mode /NFL /NDL /NJH /NJS /NP /R:2 /W:2 /XF .env *.log /XD .venv __pycache__ | Out-Null
        if ($LASTEXITCODE -ge 8) { Fail "robocopy $($c.src) failed ($LASTEXITCODE)" }
    }
}

$venvPython = Join-Path $InstallDir "backend\.venv\Scripts\python.exe"
if (Test-Path $venvPython) { Ok "Python venv exists" }
else {
    Act "create Python venv"
    if (-not $DryRun) {
        if (-not $python) { Fail "Python 3.12 not found (run without -SkipPrereqs)." }
        & $python -m venv (Join-Path $InstallDir "backend\.venv")
        if ($LASTEXITCODE -ne 0) { Fail "venv creation failed" }
    }
}
Act "install Python packages from bundled wheels (offline)"
if (-not $DryRun) {
    & $venvPython -m pip install --no-index --find-links (Join-Path $pkg "wheels") -r (Join-Path $InstallDir "backend\requirements.txt") --disable-pip-version-check -q
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed" }
    Ok "Python packages installed"
}

# --------------------------------------------------------------------------
# 4. Configuration file + database
# --------------------------------------------------------------------------
Section "Configuration + database"
if ($isUpgrade -and -not $sqlReconfigure) { Ok "backend\.env kept" }
elseif ($isUpgrade) {
    Act "update SQL connection settings in backend\.env (other settings kept)"
    if (-not $DryRun) {
        $lines = [System.Collections.Generic.List[string]](Get-Content $envPath)
        $newVals = [ordered]@{ "SQLSERVER_HOST" = $SqlHost; "SQLSERVER_PORT" = $SqlPort; "SQLSERVER_DATABASE" = $SqlDatabase;
                               "SQLSERVER_USER" = $SqlUser; "SQLSERVER_PASSWORD" = $SqlPassword; "SQLSERVER_SERVER" = $SqlServer }
        foreach ($k in $newVals.Keys) {
            $idx = -1
            for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match "^\s*$k\s*=") { $idx = $i; break } }
            $val = [string]$newVals[$k]
            if ($k -eq "SQLSERVER_SERVER" -and -not $val) { if ($idx -ge 0) { $lines.RemoveAt($idx) }; continue }
            if ($idx -ge 0) { $lines[$idx] = "$k=$val" } else { $lines.Add("$k=$val") }
        }
        [IO.File]::WriteAllLines($envPath, $lines, (New-Object Text.UTF8Encoding($false)))
        Ok "backend\.env updated"
    }
}
else {
    Act "write backend\.env (new SECRET_KEY)"
    if (-not $DryRun) {
        $envText = Get-Content (Join-Path $pkg "templates\backend.env.template") -Raw
        $values = @{
            "__SECRET_KEY__" = (New-RandomSecret); "__ADMIN_PASSWORD__" = $AdminPassword; "__BRAND__" = $Brand
            "__SQL_HOST__" = $SqlHost; "__SQL_PORT__" = $SqlPort; "__SQL_DATABASE__" = $SqlDatabase
            "__SQL_USER__" = $SqlUser; "__SQL_PASSWORD__" = $SqlPassword; "__SERVER_IP__" = $ServerAddress
        }
        foreach ($k in $values.Keys) { $envText = $envText.Replace($k, [string]$values[$k]) }
        if ($SqlServer) { $envText = $envText.Replace("SQLSERVER_HOST=", "SQLSERVER_SERVER=$SqlServer`r`nSQLSERVER_HOST=") }
        [IO.File]::WriteAllText($envPath, $envText, (New-Object Text.UTF8Encoding($false)))
        Ok "backend\.env written"
    }
}

$initDb = Join-Path $InstallDir "backend\scripts\init_database.py"
if ($DryRun) {
    if ((Test-Path $venvPython) -and (Test-Path $envPath)) { & $venvPython $initDb --check }
    else { Act "create database + tables (scripts\init_database.py)" }
} else {
    Log "  initialising database (safe: never drops existing data)..."
    # Capture the script's own output (incl. any Python traceback) into install.log so a
    # failure is diagnosable; stderr merge needs EAP=Continue or PowerShell aborts on it.
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $initOut = @(& $venvPython $initDb 2>&1 | ForEach-Object { "$_" })
    $initCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    $initOut | ForEach-Object { Log "    $_" }
    if ($initCode -ne 0) {
        $tail = ($initOut | Where-Object { $_ -match "Error|error|\[SQL|^\s*\(|Exception|ERROR" } | Select-Object -Last 6) -join "`n         "
        Fail ("database initialisation failed (exit $initCode). Last error lines:`n         " + $tail + "`n         Full output is in install.log next to INSTALL.cmd.")
    }
    # Organisation name baked into the package (build-client-package.ps1 -Organization):
    # fills the sidebar / report header name unless the client already set their own.
    $orgFile = Join-Path $pkg "organization.txt"
    if (Test-Path $orgFile) {
        $orgName = (Get-Content $orgFile -Raw).Trim()
        if ($orgName) {
            & $venvPython (Join-Path $InstallDir "backend\scripts\set_organization.py") --name "$orgName"
            if ($LASTEXITCODE -ne 0) { Warn "could not set organisation name (set it under Configuration -> Organization)" }
        }
    }
}

# --------------------------------------------------------------------------
# 5. eSSL SDK (32-bit COM, used for pulling punches over TCP 4370)
# --------------------------------------------------------------------------
Section "eSSL device SDK"
$wow = Join-Path $env:windir "SysWOW64"
if (Test-Path "Registry::HKEY_CLASSES_ROOT\zkemkeeper.ZKEM") { Ok "zkemkeeper.ZKEM already registered" }
else {
    Act "copy 32-bit SDK DLLs to SysWOW64 and register zkemkeeper.dll"
    if (-not $DryRun) {
        Get-ChildItem (Join-Path $pkg "sdk32") -Filter *.dll | ForEach-Object {
            try { Copy-Item $_.FullName $wow -Force } catch { Warn "could not copy $($_.Name): $($_.Exception.Message)" }
        }
        $p = Start-Process (Join-Path $wow "regsvr32.exe") -ArgumentList "/s", "`"$(Join-Path $wow 'zkemkeeper.dll')`"" -Wait -PassThru
        if ($p.ExitCode -eq 0) { Ok "zkemkeeper registered" } else { Warn "regsvr32 zkemkeeper.dll returned $($p.ExitCode) - SDK pull will not work" }
    }
}

# --------------------------------------------------------------------------
# 6. IIS site + firewall
# --------------------------------------------------------------------------
Section "IIS site"
$dist = Join-Path $InstallDir "frontend\dist"
if (Test-Path $AppCmd) {
    # Upgrade: reuse whichever site already serves this dist folder (e.g. an older
    # hand-made "AveonApp") instead of creating a duplicate that fights for port 80.
    if (-not $cfg["SiteName"]) {
        $started = @(& $AppCmd list site /state:Started 2>$null | ForEach-Object { if ($_ -match '^SITE "([^"]+)"') { $Matches[1] } })
        $serving = @(& $AppCmd list vdir 2>$null | ForEach-Object {
            if ($_ -match '^VDIR "([^"/]+)/" \(physicalPath:(.+)\)$' -and $Matches[2].TrimEnd("\") -ieq $dist) { $Matches[1] } })
        $adopt = @($serving | Where-Object { $started -contains $_ }) + $serving | Select-Object -First 1
        if ($adopt -and $adopt -ne $SiteName) { Ok "existing site '$adopt' serves $dist - reusing it"; $SiteName = $adopt }
    }
    # Stop any other started site that owns the same all-hosts port binding.
    $sites = & $AppCmd list site 2>$null
    foreach ($line in $sites) {
        # bindings is itself comma-separated (http/*:80:,https/*:443:), so match lazily up to ",state:".
        if ($line -match '^SITE "([^"]+)" \(id:\d+,bindings:(.*?),state:(\w+)') {
            $name, $bindings, $state = $Matches[1], $Matches[2], $Matches[3]
            if ($name -ne $SiteName -and $state -eq "Started" -and $bindings -match "http/\*:${SitePort}:(,|$)") {
                Act "stop IIS site '$name' (it holds port $SitePort)"
                if (-not $DryRun) { Invoke-AppCmd @("stop", "site", "/site.name:$name") | Out-Null }
            }
        }
    }
    $siteExists = (& $AppCmd list site "/name:$SiteName" 2>$null) -ne $null
    if (-not $siteExists) {
        $poolExists = (& $AppCmd list apppool "/name:$SiteName" 2>$null) -ne $null
        if (-not $poolExists) {
            Act "create app pool '$SiteName' (No Managed Code)"
            if (-not $DryRun) { Invoke-AppCmd @("add", "apppool", "/name:$SiteName", "/managedRuntimeVersion:") | Out-Null }
        }
        Act "create site '$SiteName' http/*:$SitePort -> $dist"
        if (-not $DryRun) {
            Invoke-AppCmd @("add", "site", "/name:$SiteName", "/bindings:http/*:${SitePort}:", "/physicalPath:$dist") | Out-Null
            Invoke-AppCmd @("set", "app", "$SiteName/", "/applicationPool:$SiteName") | Out-Null
        }
    } else {
        Act "update site '$SiteName' -> $dist"
        if (-not $DryRun) {
            Invoke-AppCmd @("set", "vdir", "$SiteName/", "/physicalPath:$dist") | Out-Null
            Quiet { & $AppCmd start site "/site.name:$SiteName" }   # no-op if already started
        }
    }
    if (-not $DryRun) {
        # Read access for IIS worker (IIS_IUSRS) and anonymous user (IUSR), by SID so it is locale-independent.
        icacls $dist /grant "*S-1-5-32-568:(OI)(CI)RX" "*S-1-5-17:(OI)(CI)RX" /T /Q | Out-Null
        Ok "site '$SiteName' ready on port $SitePort"
    }
} elseif (-not $DryRun) { Fail "IIS appcmd.exe not found - IIS installation failed?" }

Section "Firewall"
if (Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue) { Ok "rule '$FirewallRule' exists" }
else {
    Act "allow inbound TCP $SitePort (rule '$FirewallRule')"
    if (-not $DryRun) { New-NetFirewallRule -DisplayName $FirewallRule -Direction Inbound -Protocol TCP -LocalPort $SitePort -Action Allow -Profile Any | Out-Null }
}

# --------------------------------------------------------------------------
# 7. Scheduled tasks (SYSTEM): backend, watchdog, nightly recalc, SDK fetch
# --------------------------------------------------------------------------
Section "Services (scheduled tasks)"
$taskDir = Join-Path $InstallDir "deployment\tasks"
if (-not $DryRun) {
    New-Item -ItemType Directory -Force $taskDir | Out-Null
    # The watchdog derives its task names from this file.
    [IO.File]::WriteAllText((Join-Path $InstallDir "deployment\brand.txt"), $brandSlug, (New-Object Text.UTF8Encoding($false)))
}
foreach ($t in $TaskNames) {
    Act "register task $t"
    if (-not $DryRun) {
        $xml = (Get-Content (Join-Path $pkg "templates\$($TemplateNames[$t]).xml") -Raw).Replace("__AVEON_ROOT__", $InstallDir).Replace("__BRAND__", $Brand).Replace("__SLUG__", $brandSlug)
        $out = Join-Path $taskDir "$t.xml"
        [IO.File]::WriteAllText($out, $xml, [Text.Encoding]::Unicode)
        $res = schtasks /create /f /tn $t /xml $out 2>&1
        if ($LASTEXITCODE -ne 0) { Fail "schtasks /create $t failed: $res" }
        Quiet { schtasks /change /tn $t /enable }   # undo the pause from Stop-Backend
    }
}
if (-not $DryRun) {
    if (-not (Test-Path $RegKey)) { New-Item -Path $RegKey | Out-Null }
    Set-ItemProperty -Path $RegKey -Name InstallDir -Value $InstallDir
    Set-ItemProperty -Path $RegKey -Name SiteName -Value $SiteName
    Set-ItemProperty -Path $RegKey -Name InstalledAt -Value (Get-Date -Format s)
    # /end first: a still-"Running" instance would make /run a no-op (IgnoreNew policy).
    Quiet { schtasks /end /tn "${brandSlug}Backend" }
    schtasks /run /tn "${brandSlug}Backend" | Out-Null
    Ok "${brandSlug}Backend started"
}

# --------------------------------------------------------------------------
# 8. Verify
# --------------------------------------------------------------------------
Section "Verification"
if ($DryRun) { Log "Dry run complete - nothing was changed." "Green"; exit 0 }

$healthy = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "http://localhost:$SitePort/health"
        if ($r.StatusCode -eq 200) { $healthy = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
$url = if ($SitePort -eq 80) { "http://$ServerAddress/" } else { "http://${ServerAddress}:$SitePort/" }
if ($healthy) {
    Ok "http://localhost:$SitePort/health -> ok (IIS -> backend -> SQL)"
    Log ""
    Log "==============================================================" "Green"
    Log " $Brand is installed and running." "Green"
    Log "   Web UI      : $url   (user: admin)" "Green"
    Log "   Devices     : Comm > Cloud Server/ADMS = $ServerAddress, port $SitePort" "Green"
    Log "   Config      : $envPath" "Green"
    Log "   Logs        : $InstallDir\backend\service.log, $InstallDir\deployment\watchdog.log" "Green"
    Log "==============================================================" "Green"
} else {
    Warn "health check did not pass within 90 s. Last lines of service.log:"
    $svcLog = Join-Path $InstallDir "backend\service.log"
    if (Test-Path $svcLog) { Get-Content $svcLog -Tail 25 | ForEach-Object { Log "    $_" } }
    Warn "the watchdog keeps retrying every minute; fix backend\.env (SQL login) if the database is unreachable."
}
if ($script:RebootNeeded) { Warn "A prerequisite requested a RESTART. Please restart this server once." }
