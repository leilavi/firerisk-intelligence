@echo off
REM Runs the Meta Model API connection check (Python standard library only).
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY ( python --version >nul 2>nul && set "PY=python" )
if not defined PY (
  echo.
  echo  Python is not installed on this computer.
  echo  Easiest: open Microsoft Store, search "Python 3.13" ^(Python Software Foundation^), click Get.
  echo  Then close this window and run this file again.
  echo.
  pause
  exit /b 2
)
%PY% scripts\check_meta_api.py
echo.
pause
