@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_oil_research_system.ps1"
echo.
if exist "%~dp0artifacts\oil-research-server-url.txt" (
  echo Login URL:
  type "%~dp0artifacts\oil-research-server-url.txt"
)
echo.
echo Default account: admin / CHANGE_ME
echo Stop script: stop_oil_research_system.bat
pause
