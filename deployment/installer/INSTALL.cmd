@echo off
rem One-click installer. Double-click this file.
rem Installs prerequisites, the app, the database, IIS site and services.
rem Safe to run again later: it upgrades in place and keeps data and settings.
setlocal
cd /d "%~dp0"

rem Relaunch elevated (UAC prompt) if not already running as Administrator.
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 (
  echo.
  echo INSTALLATION FAILED - see the messages above and install.log in this folder.
)
echo.
pause
