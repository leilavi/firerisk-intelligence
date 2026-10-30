@echo off
REM Probe the technical drawings ON THIS COMPUTER (no AI, no network). Prints counts only - safe to paste in the chat.
REM Put the PDFs into data\private\drawings\ first (private, git-ignored).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.bat
  pause & exit /b 2
)
if not exist "data\private\drawings" mkdir "data\private\drawings"
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\probe_drawings.py %*
echo.
pause
