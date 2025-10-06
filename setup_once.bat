@echo off
setlocal

REM --- 1) Create venv if missing ---
if not exist ".venv\Scripts\python.exe" (
  echo [Setup] Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [Setup] Could not create venv. Is Python installed? Get it from python.org and try again.
    pause
    exit /b 1
  )
)

REM --- 2) Ensure pip is available & up to date ---
echo [Setup] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

REM --- 3) Install project requirements ---
echo [Setup] Installing requirements (pandas, openpyxl, numpy, matplotlib, sqlalchemy)...
".venv\Scripts\python.exe" -m pip install pandas openpyxl numpy matplotlib sqlalchemy
if errorlevel 1 (
  echo [Setup] Failed to install requirements.
  pause
  exit /b 1
)

echo [Setup] Done. Use Run_All.bat from now on.
pause
