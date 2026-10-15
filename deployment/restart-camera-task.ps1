# Restarts the AveonCamera scheduled task (kills stuck process, relaunches fresh).
# Must run elevated. Safe to re-run.
$ErrorActionPreference = "Stop"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\restart-camera-task.result.txt"
try {
    schtasks /end /tn "AveonCamera" 2>&1 | Out-Null
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*camera_service*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep 2
    schtasks /run /tn "AveonCamera" | Out-Null
    "DONE" | Out-File -Encoding utf8 $log
} catch {
    "FAILED: $($_.Exception.Message)" | Out-File -Encoding utf8 $log
}
