# Final repair: force VC++ runtime repair (registry says installed, files are old),
# register nightly recalc task from XML, start backend + camera.
# Must run elevated.
$ErrorActionPreference = "Continue"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\repair-final.result.txt"
$steps = @()

$exe = "C:\Users\Ranjith\AppData\Local\Temp\claude\D--ESSL-ESSL-SW-Aveon\5640c470-5151-4c1f-b055-dcd0daeed44e\scratchpad\VC_redist.x64.exe"
$p = Start-Process $exe -ArgumentList "/repair","/quiet","/norestart" -Wait -PassThru
$steps += "vcredist repair exit: $($p.ExitCode)"
$steps += "msvcp140.dll now: $((Get-Item 'C:\Windows\System32\msvcp140.dll').VersionInfo.FileVersion)"
$steps += "vcruntime140.dll now: $((Get-Item 'C:\Windows\System32\vcruntime140.dll').VersionInfo.FileVersion)"

schtasks /create /f /tn "AveonAttendanceRecalc" /xml "D:\ESSL\ESSL_SW\Aveon\deployment\AveonAttendanceRecalc.xml" | Out-Null
$steps += "AveonAttendanceRecalc: $LASTEXITCODE"

schtasks /run /tn "AveonBackend" | Out-Null
schtasks /run /tn "AveonCamera" | Out-Null
$steps += "tasks started"

$steps -join "`r`n" | Out-File -Encoding utf8 $log
