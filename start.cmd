@echo off
setlocal enabledelayedexpansion
rem Joblooper first run for Windows.
rem
rem This exists because the guided setup is written in Python, so it cannot be
rem what tells you that Python is missing. Everything here runs on a machine
rem with nothing installed.

echo.
echo   Joblooper
echo   Checking what this computer already has...
echo.

set "PY="
for %%C in (py python python3) do (
  if not defined PY (
    %%C -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "PY=%%C"
  )
)

if defined PY goto :run

echo   Python 3.10 or newer is required, and this computer does not have it.
echo   Nothing else is needed: Joblooper uses no other libraries.
echo.

where winget >nul 2>&1
if errorlevel 1 goto :manual

echo   It can be installed for you with:
echo.
echo       winget install --id Python.Python.3.12
echo.
set /p "REPLY=  Install Python now? [y/N] "
if /i not "%REPLY%"=="y" goto :manual

echo.
echo   Installing Python. Windows may ask you to approve this.
winget install --exact --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo.
echo   Python is installed. Close this window, open a new one, and run start.cmd
echo   again — Windows only notices a new program in a fresh window.
echo.
pause
exit /b 0

:manual
echo   To install it yourself:
echo.
echo       1. Open https://www.python.org/downloads/
echo       2. Download Python 3.12 and run the installer
echo       3. Tick "Add python.exe to PATH" on the first screen
echo       4. Open a new window here and run start.cmd again
echo.
pause
exit /b 1

:run
echo   Python found. Starting Joblooper...
echo.
%PY% "%~dp0jl.py" setup %*
exit /b %errorlevel%
