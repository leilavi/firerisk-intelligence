@echo off
REM Demo privacy: count frames and estimate SAM cost (no API call).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo First run install.bat & pause & exit /b 2 )
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\mask_labels_for_demo.py --dry-run
echo.
pause
