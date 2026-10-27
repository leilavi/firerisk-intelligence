@echo off
REM One-time setup: creates a private Python environment in .venv and installs dependencies.
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY ( python --version >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python is not installed. Install "Python 3.13" from Microsoft Store, then run this again.
  pause & exit /b 2
)
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 ( echo. & echo Installation FAILED - send a screenshot of this window. & pause & exit /b 1 )
echo.
echo Running tests...
".venv\Scripts\python.exe" -m pytest -q
echo.
echo Done. Next: double-click run_dashboard.bat
pause
