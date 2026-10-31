@echo off
REM Make the draft "panel -> emergency lights / exit signs / fire equipment" table from the drawing OCR (local only).
REM Run run_drawing_ocr.bat first. Prints counts only. Output: data\private\drawings\power_links_draft.xlsx
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.bat
  pause & exit /b 2
)
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\draft_power_links.py %*
echo.
pause
