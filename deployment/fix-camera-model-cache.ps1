# Copies the already-downloaded InsightFace model into the SYSTEM profile cache
# (avoids the stalled 280MB re-download) and restarts the AveonCamera task.
# Must run elevated.
$ErrorActionPreference = "Stop"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\fix-camera-model-cache.result.txt"
try {
    schtasks /end /tn "AveonCamera" 2>&1 | Out-Null
    # Kill any leftover camera-service python (started from camera_service\venv)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*camera_service*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep 2

    $dst = "C:\Windows\system32\config\systemprofile\.insightface\models"
    New-Item -ItemType Directory -Force "$dst" | Out-Null
    Remove-Item "$dst\buffalo_l.zip" -Force -ErrorAction SilentlyContinue
    Remove-Item "$dst\buffalo_l" -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item "C:\Users\Ranjith\.insightface\models\buffalo_l" "$dst\buffalo_l" -Recurse -Force

    schtasks /run /tn "AveonCamera" | Out-Null
    "DONE" | Out-File -Encoding utf8 $log
} catch {
    "FAILED: $($_.Exception.Message)" | Out-File -Encoding utf8 $log
}
