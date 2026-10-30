@echo off
REM Live check: Meta Muse Spark tool calling (synthetic TEST records only, no building data is sent).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.bat
  pause & exit /b 2
)
".venv\Scripts\python.exe" scripts\check_tool_calling.py
echo.
pause
