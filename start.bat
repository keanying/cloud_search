@echo off
rem ============================================================
rem  CloudSearch one-click launcher for Windows (double-click)
rem  Usage: start.bat [--dev] [--no-install] [--no-build] [--rebuild] [--port 8001] [--setup-only]
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

set "PY="
py -3.13 --version >nul 2>nul && set "PY=py -3.13"
if not defined PY py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
  echo [ERROR] Python 3.12 or 3.13 not found.
  echo         Install from https://www.python.org/downloads/  and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

%PY% run.py %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo [ERROR] Launcher exited with code %RC%. See messages above.
  pause
)
exit /b %RC%
