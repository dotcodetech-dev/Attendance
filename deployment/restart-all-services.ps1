# Clean restart of Aveon backend + camera services (kills wedged python, reruns tasks).
# Must run elevated.
$ErrorActionPreference = "Continue"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\restart-all-services.result.txt"
schtasks /end /tn "AveonBackend" 2>&1 | Out-Null
schtasks /end /tn "AveonCamera" 2>&1 | Out-Null
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*Aveon*" -or $_.CommandLine -eq $null } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 3
schtasks /run /tn "AveonBackend" | Out-Null
schtasks /run /tn "AveonCamera" | Out-Null
"restarted" | Out-File -Encoding utf8 $log
