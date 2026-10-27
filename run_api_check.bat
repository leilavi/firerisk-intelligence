@echo off
REM Runs the Meta Model API connection check (Python standard library only).
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo.
  echo  Python was not found on this computer.
  echo  Install Python 3.11+ from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" during installation, then run this file again.
  echo.
  pause
  exit /b 2
)
%PY% scripts\check_meta_api.py
echo.
pause
