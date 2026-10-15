# One-shot setup of resilient Aveon services. Must run elevated.
# - frees ports 8000/8100 (kills any wedged uvicorn)
# - (re)registers AveonBackend, AveonCamera, AveonWatchdog from XML
# - starts backend + camera now, then runs the watchdog once
$ErrorActionPreference = "Continue"
$result = "D:\ESSL\ESSL_SW\Aveon\deployment\setup-resilient-services.result.txt"
$steps = @()

# 1. Kill any existing Aveon uvicorn processes (wedged or looping)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and ($_.CommandLine -match "Aveon\\(backend|camera_service)") } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $steps += "killed pid $($_.ProcessId)" } catch {} }

# also free the ports in case an orphan holds them
foreach ($port in 8000, 8100) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction Stop } catch {} }
}
Start-Sleep 2

# 2. Register tasks from XML (overwrites any old versions)
schtasks /create /f /tn "AveonBackend"  /xml "D:\ESSL\ESSL_SW\Aveon\deployment\AveonBackend.xml"  | Out-Null; $steps += "AveonBackend create=$LASTEXITCODE"
schtasks /create /f /tn "AveonCamera"   /xml "D:\ESSL\ESSL_SW\Aveon\deployment\AveonCamera.xml"   | Out-Null; $steps += "AveonCamera create=$LASTEXITCODE"
schtasks /create /f /tn "AveonWatchdog" /xml "D:\ESSL\ESSL_SW\Aveon\deployment\AveonWatchdog.xml" | Out-Null; $steps += "AveonWatchdog create=$LASTEXITCODE"

# remove the now-obsolete logon-twin tasks (superseded by the watchdog + boot/logon triggers)
schtasks /delete /f /tn "AveonBackendLogon" 2>&1 | Out-Null
schtasks /delete /f /tn "AveonCameraLogon" 2>&1 | Out-Null

# 3. Start now
schtasks /run /tn "AveonBackend" | Out-Null; $steps += "AveonBackend run=$LASTEXITCODE"
schtasks /run /tn "AveonCamera"  | Out-Null; $steps += "AveonCamera run=$LASTEXITCODE"

$steps -join "`r`n" | Out-File -Encoding utf8 $result
