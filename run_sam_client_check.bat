@echo off
REM Phase 2 live check of the production SAM client (firerisk\sam.py) on one frame.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\check_sam_client.py %*
echo.
pause
