# Repairs the Aveon stack after the Windows 11 in-place upgrade:
# 1. installs the current VC++ 2015-2022 x64 runtime (fixes onnxruntime DLL crash)
# 2. re-registers the AveonBackend/AveonCamera boot tasks (upgrade wiped them)
# 3. starts both now
# Must run elevated.
$ErrorActionPreference = "Continue"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\repair-after-win11-upgrade.result.txt"
$steps = @()

winget install --id Microsoft.VCRedist.2015+.x64 --silent --disable-interactivity `
    --accept-package-agreements --accept-source-agreements | Out-Null
$v = (Get-Item "C:\Windows\System32\msvcp140.dll").VersionInfo.FileVersion
$steps += "vcredist: msvcp140.dll now $v"

schtasks /create /f /tn "AveonBackend" /tr "D:\ESSL\ESSL_SW\Aveon\backend\start-service.cmd" /sc onstart /delay 0000:30 /ru SYSTEM /rl HIGHEST | Out-Null
$steps += "AveonBackend task: $LASTEXITCODE"
schtasks /create /f /tn "AveonCamera" /tr "D:\ESSL\ESSL_SW\Aveon\camera_service\start-service.cmd" /sc onstart /delay 0000:45 /ru SYSTEM /rl HIGHEST | Out-Null
$steps += "AveonCamera task: $LASTEXITCODE"

schtasks /run /tn "AveonBackend" | Out-Null
schtasks /run /tn "AveonCamera" | Out-Null
$steps += "tasks started"

$steps -join "`r`n" | Out-File -Encoding utf8 $log
