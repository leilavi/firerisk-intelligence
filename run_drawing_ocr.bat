@echo off
REM Read text from SCANNED drawings ON THIS COMPUTER (local OCR, no AI service, no network).
REM Put the drawings into data\private\drawings\ first (private, git-ignored). Prints counts only - safe to paste in the chat.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.bat
  pause & exit /b 2
)
if not exist "data\private\drawings" mkdir "data\private\drawings"
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt >nul 2>&1
".venv\Scripts\python.exe" scripts\ocr_drawings.py %*
echo.
echo Open data\private\drawings\ocr\review.html in your browser to check what was read.
pause
