@echo off
cd /d "%~dp0"

echo ============================================
echo   FluxBot Launcher
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.11+ and add to PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating venv...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] venv create failed
    pause
    exit /b 1
  )
)

echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -U pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed
  pause
  exit /b 1
)

if not exist ".env" (
  echo [INFO] Creating .env from template
  copy /Y ".env.example" ".env" >nul
)

echo [3/3] Starting GUI...
".venv\Scripts\python.exe" -m app.main
if errorlevel 1 (
  echo [ERROR] App exited with error
  pause
)
