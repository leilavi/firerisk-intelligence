@echo off
REM Dashboard in DEMO MODE: building names hidden, only blurred frames, no original videos.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo First run install.bat & pause & exit /b 2 )
set FIRERISK_DEMO_MODE=1
echo Starting FireRisk Intelligence in DEMO MODE... http://127.0.0.1:8765
".venv\Scripts\python.exe" -m firerisk.serve
pause
