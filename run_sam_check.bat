@echo off
REM SAM 3.1 connection check (Phase 1): one real request with one frame of "Electrical Panel - B1".
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.bat
  pause & exit /b 2
)
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\check_sam.py %*
echo.
pause
