@echo off
REM SAMPLE MODE: the dashboard with a FICTIONAL building ("Acme Riverside Plaza"). For judges and fresh clones.
REM Never reads data\private\ (real data). Meta Muse Spark runs only if you set your own key (setup_api_key.bat).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat
if not exist ".venv\Scripts\python.exe" ( echo Setup did not finish - see the messages above. & pause & exit /b 2 )
echo Starting FireRisk Intelligence in SAMPLE MODE (fictional building)... http://127.0.0.1:8765
".venv\Scripts\python.exe" -m firerisk.sample
pause
