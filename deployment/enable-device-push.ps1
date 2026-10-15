<#
.SYNOPSIS
  Make the Aveon backend reachable by biometric devices so they can PUSH
  attendance over the network (real ADMS/iClock push, not SDK fetch).

  Run ONCE in an ELEVATED PowerShell (right-click > Run as administrator):
      powershell -ExecutionPolicy Bypass -File .\enable-device-push.ps1

  What it does:
   1. Re-registers the AveonBackend service to listen on 0.0.0.0:8000
      (all network interfaces) instead of 127.0.0.1 (localhost only) — this is
      THE fix that lets a device on the LAN reach the server at all.
   2. Opens inbound TCP 8000 in Windows Firewall.
   3. Restarts the backend.
   4. Prints the server IP + the exact Cloud Server settings to enter on each device.
#>
$ErrorActionPreference = "Stop"
$backend = "D:\ESSL\ESSL_SW\Aveon\backend"
$py = "$backend\.venv\Scripts\python.exe"

Write-Host "1) Re-registering AveonBackend on 0.0.0.0:8000..." -ForegroundColor Cyan
$a = New-ScheduledTaskAction -Execute $py -Argument "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" -WorkingDirectory $backend
$t = New-ScheduledTaskTrigger -AtStartup
$p = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$s = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "AveonBackend" -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null

Write-Host "2) Opening firewall inbound TCP 8000..." -ForegroundColor Cyan
Remove-NetFirewallRule -DisplayName "Aveon Device Push 8000" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Aveon Device Push 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Any | Out-Null

Write-Host "3) Restarting backend..." -ForegroundColor Cyan
Stop-ScheduledTask -TaskName "AveonBackend" -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*uvicorn*app.main*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 2
Start-ScheduledTask -TaskName "AveonBackend"
Start-Sleep 7
$listen = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
Write-Host ("   Backend now listening on " + $listen.LocalAddress + ":" + $listen.LocalPort) -ForegroundColor Green

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.*" } | Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host " Set THIS on each device (Menu > Comm > Cloud Server):" -ForegroundColor Yellow
Write-Host ("   Server Address : " + $ip) -ForegroundColor White
Write-Host "   Server Port    : 8000" -ForegroundColor White
Write-Host "   Enable Domain  : OFF     HTTPS/SSL : OFF" -ForegroundColor White
Write-Host "   Then REBOOT the device." -ForegroundColor White
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host "Verify: on the device network, open  http://$ip`:8000/health  -> {""status"":""ok""}"
Write-Host "Then watch Attendance Logs > Live Device Activity for 'PUSH ATTLOG' after a face punch."
