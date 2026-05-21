@echo off
REM AI Overlord — one-click launcher for Windows 11
REM Double-click this file. It will install everything on first run, then launch.

setlocal ENABLEEXTENSIONS
cd /d "%~dp0"

title AI Overlord

REM Resolve a usable Python (3.11+). Try `py`, then `python`, then `python3`.
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if "%PY_CMD%"=="" (
    where python >nul 2>nul && set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
    where python3 >nul 2>nul && set "PY_CMD=python3"
)

if "%PY_CMD%"=="" goto :no_python

%PY_CMD% --version >nul 2>nul
if errorlevel 1 goto :no_python

%PY_CMD% launch.py %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Launcher exited with code %RC%.
    echo Press any key to close...
    pause >nul
)
exit /b %RC%

:no_python
echo.
echo [!] Python 3.11+ was not found on PATH.
echo.
echo Install it from the Microsoft Store (recommended) or by running:
echo     winget install Python.Python.3.12
echo.
echo Then double-click this file again.
echo.
pause
exit /b 1
