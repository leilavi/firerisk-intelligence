@echo off
REM One-time setup of automatic Google Drive updates (see README, "Automatic updates from Google Drive").
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.bat
  pause & exit /b 2
)
".venv\Scripts\python.exe" scripts\setup_drive_sync.py %*
echo.
pause
