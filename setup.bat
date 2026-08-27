@echo off
setlocal
set "ROOT=%~dp0"
set "PY="

echo Looking for a supported Python (3.10 - 3.14) ...
echo.

rem Try the py launcher, newest supported first. Always use full tags:
rem "py -3.1" asks for Python 3.1, it does not match 3.10 or any other 3.1x.
rem No delayed expansion needed -- "if defined" and "if errorlevel" are both
rem evaluated when the line runs, not when the block is parsed.
for %%V in (3.14 3.13 3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PY=py -%%V"
    )
)

rem No launcher? Fall back to whatever "python" is on PATH, but only if it is
rem actually in range -- otherwise the failure surfaces much later and far
rem less clearly, during the PySide6 install.
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,15) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo Could not find Python 3.10, 3.11, 3.12, 3.13 or 3.14.
    echo.
    echo Versions the py launcher can see:
    py --list 2>nul || echo   ^(the py launcher is not installed either^)
    echo.
    echo Install Python from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH" in the installer, then run setup.bat again.
    echo.
    pause
    exit /b 1
)

echo Using %PY%
%PY% -c "import sys; print('  ' + sys.version); print('  ' + sys.executable)"
echo.

echo Creating the virtual environment in .venv ...
%PY% -m venv "%ROOT%.venv"
if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo.
    echo Could not create the virtual environment in "%ROOT%.venv".
    echo If a half-created .venv folder is there, delete it and try again.
    echo.
    pause
    exit /b 1
)

set "VPY=%ROOT%.venv\Scripts\python.exe"

echo Upgrading pip ...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo pip could not be upgraded. Check your network or proxy settings.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing PySide6 and easyeda2kicad ...
"%VPY%" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 (
    echo.
    echo Installing the dependencies failed.
    echo PySide6 ships wheels only for 64-bit Python on x86-64 Windows --
    echo there are none for 32-bit Python or for Windows on ARM.
    echo.
    pause
    exit /b 1
)

echo.
echo Done. Launch the app with run.bat
pause
