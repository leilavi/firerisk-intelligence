@echo off
REM Demo privacy: SAM finds signs and labels in the evidence frames; blurred copies are made (originals unchanged).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo First run install.bat & pause & exit /b 2 )
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\mask_labels_for_demo.py %*
if exist "data\private\media\frames_demo\review.html" start "" "data\private\media\frames_demo\review.html"
echo.
pause
