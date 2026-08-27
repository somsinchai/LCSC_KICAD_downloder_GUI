@echo off
setlocal
set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not exist "%PY%" (
  echo Python 3.10 not found at %PY%
  pause
  exit /b 1
)
"%PY%" -m venv "%~dp0.venv"
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
echo.
echo Done. Launch with run.bat
pause
