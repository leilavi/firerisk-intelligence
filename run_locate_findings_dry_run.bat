@echo off
REM SAM 3.1 localization of existing video findings (dry_run).
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\locate_video_findings.py --dry-run %*
echo.
pause
