# 1. Installs VC++ 2015-2022 x64 runtime from the verified local installer
# 2. Adds ONLOGON twin tasks (Fast Startup means ONSTART doesn't fire on
#    shutdown->power-on; ONLOGON covers that path; launchers now port-guard)
# 3. Registers the nightly attendance recalc task (per docs/deployment.md)
# 4. Starts backend + camera now
# Must run elevated.
$ErrorActionPreference = "Continue"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\repair-vcredist-and-triggers.result.txt"
$steps = @()

$exe = "C:\Users\Ranjith\AppData\Local\Temp\claude\D--ESSL-ESSL-SW-Aveon\5640c470-5151-4c1f-b055-dcd0daeed44e\scratchpad\VC_redist.x64.exe"
$p = Start-Process $exe -ArgumentList "/install","/quiet","/norepair","/norestart" -Wait -PassThru
$steps += "vcredist installer exit: $($p.ExitCode)"
$steps += "msvcp140.dll now: $((Get-Item 'C:\Windows\System32\msvcp140.dll').VersionInfo.FileVersion)"
$steps += "vcruntime140.dll now: $((Get-Item 'C:\Windows\System32\vcruntime140.dll').VersionInfo.FileVersion)"

schtasks /create /f /tn "AveonBackendLogon" /tr "D:\ESSL\ESSL_SW\Aveon\backend\start-service.cmd" /sc onlogon /ru SYSTEM /rl HIGHEST | Out-Null
$steps += "AveonBackendLogon: $LASTEXITCODE"
schtasks /create /f /tn "AveonCameraLogon" /tr "D:\ESSL\ESSL_SW\Aveon\camera_service\start-service.cmd" /sc onlogon /ru SYSTEM /rl HIGHEST | Out-Null
$steps += "AveonCameraLogon: $LASTEXITCODE"

schtasks /create /f /tn "AveonAttendanceRecalc" /tr "\"D:\ESSL\ESSL_SW\Aveon\backend\.venv\Scripts\python.exe\" scripts\recalc_attendance.py --days 35" /sc daily /st 01:00 /ru SYSTEM /rl HIGHEST | Out-Null
$steps += "AveonAttendanceRecalc: $LASTEXITCODE"
# schtasks has no 'start in' switch; set the working directory via the task XML update
$xml = [xml](schtasks /query /tn "AveonAttendanceRecalc" /xml)
$xml.Task.Actions.Exec.AppendChild($xml.CreateElement("WorkingDirectory", $xml.Task.NamespaceURI)) | Out-Null
$xml.Task.Actions.Exec.WorkingDirectory = "D:\ESSL\ESSL_SW\Aveon\backend"
$tmp = "$env:TEMP\aveon-recalc-task.xml"
$xml.Save($tmp)
schtasks /create /f /tn "AveonAttendanceRecalc" /xml $tmp | Out-Null
$steps += "AveonAttendanceRecalc workdir set: $LASTEXITCODE"

schtasks /run /tn "AveonBackend" | Out-Null
schtasks /run /tn "AveonCamera" | Out-Null
$steps += "tasks started"

$steps -join "`r`n" | Out-File -Encoding utf8 $log
