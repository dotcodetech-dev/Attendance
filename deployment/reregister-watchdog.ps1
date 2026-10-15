# Re-register AveonWatchdog with the fixed daily-repetition trigger, run once now.
# Must run elevated.
$ErrorActionPreference = "Continue"
$log = "D:\ESSL\ESSL_SW\Aveon\deployment\reregister-watchdog.result.txt"
schtasks /create /f /tn "AveonWatchdog" /xml "D:\ESSL\ESSL_SW\Aveon\deployment\AveonWatchdog.xml" | Out-Null
$create = $LASTEXITCODE
schtasks /run /tn "AveonWatchdog" | Out-Null
$run = $LASTEXITCODE
"create=$create run=$run" | Out-File -Encoding utf8 $log
