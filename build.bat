@echo off
cd /d "%~dp0"
echo ============================================
echo   Build FluxBot (PyInstaller)
echo ============================================

if not exist ".venv\Scripts\python.exe" (
  echo Creating venv...
  python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -U pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller -q
if errorlevel 1 (
  echo pip failed
  pause
  exit /b 1
)

echo Building... (may take several minutes)
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean FluxBot.spec
if errorlevel 1 (
  echo Build failed
  pause
  exit /b 1
)

echo.
echo Build OK: dist\FluxBot\
echo Run install.bat to install to this PC.
pause
