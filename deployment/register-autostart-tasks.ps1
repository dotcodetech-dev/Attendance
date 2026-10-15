# Registers Aveon backend + camera service as boot tasks (run as SYSTEM).
# Must run elevated. Safe to re-run (/f overwrites).
$ErrorActionPreference = "Stop"
schtasks /create /f /tn "AveonBackend" /tr "D:\ESSL\ESSL_SW\Aveon\backend\start-service.cmd" /sc onstart /delay 0000:30 /ru SYSTEM /rl HIGHEST
schtasks /create /f /tn "AveonCamera" /tr "D:\ESSL\ESSL_SW\Aveon\camera_service\start-service.cmd" /sc onstart /delay 0000:45 /ru SYSTEM /rl HIGHEST
# Start them right now too (no reboot needed today)
schtasks /run /tn "AveonBackend"
schtasks /run /tn "AveonCamera"
"DONE" | Out-File -Encoding utf8 "$PSScriptRoot\register-autostart-tasks.result.txt"
