@echo off
setlocal
rem Without this, "-m lcsc_kicad_gui" only resolves when run.bat is started from
rem its own folder -- and under pythonw.exe that failure is completely silent.
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Virtual environment missing. Run setup.bat first.
  pause
  exit /b 1
)

rem --debug keeps a console window so the log can be pasted into a bug report.
echo.%*| findstr /i /c:"--debug" >nul
if not errorlevel 1 (
  "%~dp0.venv\Scripts\python.exe" -m lcsc_kicad_gui %*
  echo.
  pause
  exit /b
)

start "" "%~dp0.venv\Scripts\pythonw.exe" -m lcsc_kicad_gui %*
