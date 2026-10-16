@echo off
rem Update an existing installation. Double-click this file.
rem Keeps backend\.env, the database and settings; asks no questions.
rem For a first install, or to change SQL / IIS settings, use INSTALL.cmd instead.
setlocal
cd /d "%~dp0"

rem Relaunch elevated (UAC prompt) if not already running as Administrator.
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %*
if errorlevel 1 (
  echo.
  echo UPDATE FAILED - see the messages above and update.log in this folder.
)
echo.
pause
