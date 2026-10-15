# Registers AveonFetchAttendance (SDK pull every 10 min) and runs it once now.
# Must run elevated.
$ErrorActionPreference = "Continue"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\register-fetch-task.result.txt"
Remove-Item "D:\ESSL\ESSL_SW\Aveon\backend\fetch.log" -ErrorAction SilentlyContinue
schtasks /create /f /tn "AveonFetchAttendance" /xml "D:\ESSL\ESSL_SW\Aveon\deployment\AveonFetchAttendance.xml" | Out-Null
$create = $LASTEXITCODE
schtasks /run /tn "AveonFetchAttendance" | Out-Null
"create_exit=$create run_exit=$LASTEXITCODE" | Out-File -Encoding utf8 $log
