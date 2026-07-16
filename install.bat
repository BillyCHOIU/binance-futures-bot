@echo off
cd /d "%~dp0"
echo ============================================
echo   Install FluxBot
echo ============================================

set "SRC=%~dp0dist\FluxBot"
set "DEST=%LOCALAPPDATA%\FluxBot"

if not exist "%SRC%\FluxBot.exe" (
  echo [ERROR] dist\FluxBot\FluxBot.exe not found.
  echo Run build.bat first.
  pause
  exit /b 1
)

echo Installing to:
echo   %DEST%
if not exist "%DEST%" mkdir "%DEST%"

xcopy /E /I /Y "%SRC%\*" "%DEST%\" >nul
if errorlevel 1 (
  echo Copy failed
  pause
  exit /b 1
)

REM keep user config if already exists  do not wipe .env
if not exist "%DEST%\config.yaml" if exist "%~dp0config.yaml" copy /Y "%~dp0config.yaml" "%DEST%\config.yaml" >nul
if not exist "%DEST%\.env.example" if exist "%~dp0.env.example" copy /Y "%~dp0.env.example" "%DEST%\.env.example" >nul

REM Desktop shortcut via PowerShell
set "DESKTOP=%USERPROFILE%\Desktop"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP%\FluxBot.lnk'); $s.TargetPath = '%DEST%\FluxBot.exe'; $s.WorkingDirectory = '%DEST%'; $s.WindowStyle = 1; $s.Description = 'FluxBot Binance Futures'; $s.Save()"

echo.
echo Installed.
echo Shortcut: Desktop\FluxBot.lnk
echo App folder: %DEST%
echo.
echo Double-click Desktop FluxBot to start.
pause
