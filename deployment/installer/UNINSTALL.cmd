@echo off
rem Removes the services (scheduled tasks), IIS site and firewall rule.
rem KEEPS the installed files, backend\.env, the SQL database and prerequisites.
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

choice /M "Remove the attendance services and IIS site from this server"
if errorlevel 2 exit /b

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Uninstall
echo.
pause
