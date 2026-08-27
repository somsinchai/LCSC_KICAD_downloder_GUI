@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Virtual environment missing. Run setup.bat first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller
"%~dp0.venv\Scripts\python.exe" build.py %*
pause
