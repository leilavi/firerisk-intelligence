@echo off
REM Stores your Meta Model API key in the local .env file (never committed, never sent to Claude).
cd /d "%~dp0"
echo.
echo  FireRisk Intelligence - API key setup
echo  -------------------------------------
echo  Paste your Meta Model API key below (right-click to paste), then press Enter.
echo  The key is saved ONLY in this folder's .env file on your computer.
echo.
set "KEY="
set /p "KEY=  MODEL_API_KEY: "
if "%KEY%"=="" (
  echo.
  echo  No key entered. Nothing was saved.
  pause
  exit /b 1
)
> ".env" echo MODEL_API_KEY=%KEY%
set "KEY="
cls
echo.
echo  Saved. The key is stored in: %~dp0.env
echo  Next step: double-click run_api_check.bat
echo.
pause
