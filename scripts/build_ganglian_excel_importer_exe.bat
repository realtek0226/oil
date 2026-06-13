@echo off
setlocal

cd /d "%~dp0\.."

if not exist outputs mkdir outputs

python -m PyInstaller ^
  --onefile ^
  --name ganglian_excel_importer ^
  --paths . ^
  scripts\import_ganglian_excel_timeseries.py

echo.
echo Build finished. EXE path: dist\ganglian_excel_importer.exe

