# Aveon health watchdog - runs every minute as SYSTEM (task "AveonWatchdog").
# For each service: if /health does not answer 200, kill any wedged process for
# that service (matched by its venv path) and re-run its start task. This is the
# single authority that keeps the backend + camera up through crashes AND wedges.
$ErrorActionPreference = "Continue"
# Paths are relative to this script (<root>\deployment\), so the same file works
# on the dev machine and in a client install (e.g. C:\Aveon\deployment\).
$root = Split-Path -Parent $PSScriptRoot
$logFile = Join-Path $PSScriptRoot "watchdog.log"

function Write-Log($message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Add-Content -Path $logFile -Value $line
    $lines = @(Get-Content -Path $logFile -ErrorAction SilentlyContinue)
    if ($lines.Count -gt 500) { $lines[-400..-1] | Set-Content -Path $logFile }
}

# Task names carry the brand prefix chosen at install time (deployment\brand.txt); dev machine = Aveon.
$prefix = "Aveon"
$brandFile = Join-Path $PSScriptRoot "brand.txt"
if (Test-Path $brandFile) { $b = (Get-Content $brandFile -Raw).Trim(); if ($b) { $prefix = $b } }
$services = @(
    @{ name = "backend"; port = 8000; task = "${prefix}Backend"; match = "backend\\.venv" }
)
# The camera service is optional (client installs ship without it).
if (Test-Path (Join-Path $root "camera_service")) {
    $services += @{ name = "camera"; port = 8100; task = "${prefix}Camera"; match = "camera_service\\venv" }
}

$status = @()
foreach ($s in $services) {
    $ok = $false
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 6 -Uri ("http://localhost:{0}/health" -f $s.port)
        if ($resp.StatusCode -eq 200) { $ok = $true }
    } catch {
        $ok = $false
    }

    if ($ok) {
        $status += ("{0}=ok" -f $s.name)
        continue
    }

    $status += ("{0}=DOWN" -f $s.name)
    Write-Log ("{0}: /health failed on port {1} - recycling" -f $s.name, $s.port)

    # Locate the wedged process without WMI (Get-CimInstance can hang on a sick WMI repository):
    # whatever listens on the service port, plus any python running from the service's venv.
    $pids = @()
    try { $pids += @(Get-NetTCPConnection -LocalPort $s.port -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess) } catch {}
    try { $pids += @(Get-Process python -ErrorAction Stop | Where-Object { $_.Path -and ($_.Path -match $s.match) } | Select-Object -ExpandProperty Id) } catch {}
    foreach ($procId in ($pids | Where-Object { $_ -gt 4 } | Select-Object -Unique)) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Log ("  killed pid {0}" -f $procId) } catch {}
    }

    Start-Sleep -Seconds 2
    schtasks /run /tn $s.task 2>&1 | Out-Null
    Write-Log ("  restart task '{0}' triggered" -f $s.task)
}

Write-Log ("tick: " + ($status -join ", "))
