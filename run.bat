@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "VENV=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%VENV%" (
  echo Virtual environment missing. Run: setup.bat
  pause
  exit /b 1
)
start "" "%VENV%" -m lcsc_kicad_gui %*
