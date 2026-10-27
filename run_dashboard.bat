@echo off
REM Starts the FireRisk Intelligence dashboard at http://127.0.0.1:8765 (keep this window open).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.bat
  pause & exit /b 2
)
echo Starting FireRisk Intelligence... your browser will open http://127.0.0.1:8765
echo Close this window to stop the dashboard.
".venv\Scripts\python.exe" -m firerisk.serve
pause
