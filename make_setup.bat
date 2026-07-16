@echo off
cd /d "%~dp0"
echo Building shareable FluxBot-Setup.exe ...
if not exist "dist\FluxBot\FluxBot.exe" (
  echo App not built yet. Running build first...
  call build.bat
)
".venv\Scripts\python.exe" make_setup.py
if errorlevel 1 (
  echo Failed
  pause
  exit /b 1
)
echo.
echo Send this file to other PCs:
echo   Desktop\FluxBot-Setup.exe
echo   or dist\FluxBot-Setup.exe
pause
