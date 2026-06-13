@echo off
setlocal
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_daily_excel_import.ps1" %*
exit /b %ERRORLEVEL%
