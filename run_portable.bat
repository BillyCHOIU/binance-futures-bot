@echo off
REM Portable: run built exe without install
cd /d "%~dp0"
if exist "dist\FluxBot\FluxBot.exe" (
  start "" "dist\FluxBot\FluxBot.exe"
) else (
  echo Build not found. Run build.bat first.
  pause
)
