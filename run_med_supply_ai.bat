@echo off
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found.
  echo Run these commands first:
  echo   python -m venv venv
  echo   venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
"venv\Scripts\python.exe" "backend\app.py"
endlocal
