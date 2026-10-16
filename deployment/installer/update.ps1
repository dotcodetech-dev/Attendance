<#
.SYNOPSIS
  Update an existing install with this package's code. Asks nothing.

.DESCRIPTION
  Run via UPDATE.cmd (elevates automatically). For a server that is already installed and working:
    - keeps backend\.env (SQL connection, secret key, settings), the database, logs and the venv
    - stops the backend, copies the new backend / frontend / deployment files
    - installs Python packages from the bundled wheels (offline)
    - upgrades the database schema in place (never drops data) with the server's own settings
    - restarts the services and checks http://localhost/health
  No prerequisites, IIS, firewall or SQL questions: use INSTALL.cmd for a first install or to change those.
#>
param([string] $InstallDir)

$ErrorActionPreference = "Stop"
$pkg = $PSScriptRoot
$Brand = "Aveon"
$brandFile = Join-Path $pkg "brand.txt"
if (Test-Path $brandFile) { $b = (Get-Content $brandFile -Raw).Trim(); if ($b) { $Brand = $b } }
$brandSlug = ($Brand -replace '[^A-Za-z0-9]', '')
if (-not $brandSlug) { $brandSlug = "Aveon" }
$RegKey = "HKLM:\SOFTWARE\$brandSlug"

$logPath = Join-Path $pkg "update.log"
function Log([string]$msg, [string]$color = "Gray") {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line -ForegroundColor $color
    try { Add-Content -Path $logPath -Value $line } catch {}
}
function Ok([string]$msg)   { Log "  OK    $msg" "Green" }
function Warn([string]$msg) { Log "  WARN  $msg" "Yellow" }
function Fail([string]$msg) { Log "  FAIL  $msg" "Red"; throw $msg }
function Quiet([scriptblock]$block) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $block 2>$null | Out-Null } catch { } finally { $ErrorActionPreference = $prev }
}

Log "$Brand update - package $pkg" "Cyan"

# Where it is installed: the installer's registry record, else C:\<Brand>.
if (-not $InstallDir) {
    $prev = if (Test-Path $RegKey) { Get-ItemProperty $RegKey } else { $null }
    $InstallDir = if ($prev -and $prev.InstallDir) { $prev.InstallDir } else { "C:\$brandSlug" }
}
$InstallDir = $InstallDir.TrimEnd("\")
$envPath = Join-Path $InstallDir "backend\.env"
$venvPython = Join-Path $InstallDir "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $envPath)) { Fail "No installation found at $InstallDir (backend\.env missing). Use INSTALL.cmd for a first install." }
if (-not (Test-Path $venvPython)) { Fail "Python environment missing at $InstallDir\backend\.venv. Use INSTALL.cmd to repair." }
Ok "installation found at $InstallDir (backend\.env is kept as it is)"

# 1. Stop the backend (watchdog paused first so it cannot restart it mid-copy).
Log "stopping services..."
$tasks = @("${brandSlug}Watchdog", "${brandSlug}Backend", "${brandSlug}FetchAttendance")
foreach ($t in $tasks) { Quiet { schtasks /change /tn $t /disable }; Quiet { schtasks /end /tn $t } }
$venvDir = Join-Path $InstallDir "backend\.venv"
$pids = @()
try { $pids += @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess) } catch {}
try { $pids += @(Get-Process python -ErrorAction Stop | Where-Object { $_.Path -and $_.Path.StartsWith($venvDir, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -ExpandProperty Id) } catch {}
foreach ($procId in ($pids | Where-Object { $_ -gt 4 } | Select-Object -Unique)) {
    try { Stop-Process -Id $procId -Force -ErrorAction Stop; Log "  stopped backend pid $procId" } catch {}
}
Start-Sleep -Seconds 2
Ok "services stopped"

$restarted = $false
function Start-Services {
    foreach ($t in $tasks) { Quiet { schtasks /change /tn $t /enable } }
    Quiet { schtasks /end /tn "${brandSlug}Backend" }
    Quiet { schtasks /run /tn "${brandSlug}Backend" }
    Quiet { schtasks /run /tn "${brandSlug}Watchdog" }
    $script:restarted = $true
}

try {
    # 2. Copy the new files. Never .env, logs or the venv; the frontend is mirrored (old bundles removed).
    $copies = @(
        @{ src = "app\backend";       dst = "backend";       mirror = $false },
        @{ src = "app\frontend\dist"; dst = "frontend\dist"; mirror = $true },
        @{ src = "app\database";      dst = "database";      mirror = $false },
        @{ src = "app\deployment";    dst = "deployment";    mirror = $false }
    )
    foreach ($c in $copies) {
        $src = Join-Path $pkg $c.src
        if (-not (Test-Path $src)) { if ($c.src -eq "app\database") { continue }; Fail "package is missing $($c.src)" }
        $dst = Join-Path $InstallDir $c.dst
        $mode = if ($c.mirror) { "/MIR" } else { "/E" }
        robocopy $src $dst $mode /NFL /NDL /NJH /NJS /NP /R:2 /W:2 /XF .env *.log /XD .venv __pycache__ | Out-Null
        if ($LASTEXITCODE -ge 8) { Fail "copying $($c.src) failed (robocopy $LASTEXITCODE)" }
        Ok "copied $($c.src) -> $dst"
    }
    # The watchdog reads its task names from here.
    [IO.File]::WriteAllText((Join-Path $InstallDir "deployment\brand.txt"), $brandSlug, (New-Object Text.UTF8Encoding($false)))

    # 3. Python packages (offline).
    $wheels = Join-Path $pkg "wheels"
    if (Test-Path $wheels) {
        Log "installing Python packages from the bundled wheels..."
        & $venvPython -m pip install --no-index --find-links $wheels -r (Join-Path $InstallDir "backend\requirements.txt") --disable-pip-version-check -q
        if ($LASTEXITCODE -ne 0) { Fail "pip install failed" }
        Ok "Python packages up to date"
    } else { Warn "no wheels folder in the package - Python packages left as they are" }

    # 4. Database schema upgrade with the server's own .env (adds new columns/tables; never drops data).
    #    The backend also does this on start, so a failure here is reported but does not stop the update.
    $initDb = Join-Path $InstallDir "backend\scripts\init_database.py"
    if (Test-Path $initDb) {
        Log "upgrading the database schema (keeps all data)..."
        Push-Location (Join-Path $InstallDir "backend")
        $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $out = @(& $venvPython $initDb 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        Pop-Location
        $out | ForEach-Object { Log "    $_" }
        if ($code -eq 0) { Ok "database schema up to date" } else { Warn "schema step exited $code - the backend retries it when it starts; see update.log" }
    }
}
finally {
    # 5. Always bring the services back, even if a step above failed.
    Log "starting services..."
    Start-Services
}

# 6. Check: IIS -> backend -> SQL.
$healthy = $false
$urls = @("http://localhost/health", "http://127.0.0.1:8000/health")
for ($i = 0; $i -lt 45 -and -not $healthy; $i++) {
    foreach ($u in $urls) {
        try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri $u; if ($r.StatusCode -eq 200) { $healthy = $true; $okUrl = $u; break } } catch {}
    }
    if (-not $healthy) { Start-Sleep -Seconds 2 }
}
Log ""
if ($healthy) {
    Ok "$okUrl -> ok (backend and database running)"
    Log "==============================================================" "Green"
    Log " $Brand is updated and running. Refresh the browser (Ctrl+F5)." "Green"
    Log "==============================================================" "Green"
} else {
    Warn "the site did not answer /health within 90 seconds."
    Warn "Check $InstallDir\backend\service.log, or run INSTALL.cmd to repair."
    exit 1
}
