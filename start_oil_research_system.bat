@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_oil_research_system.ps1"
echo.
if exist "%~dp0artifacts\oil-research-server-url.txt" (
  echo Workbench URL:
  type "%~dp0artifacts\oil-research-server-url.txt"
)
echo.
echo If the page shows the login screen, please sign in first.
echo Stop script: stop_oil_research_system.bat
pause
