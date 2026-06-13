# Daily Excel Import and Ganglian Plugin Refresh

This folder contains two independent workflows for the shared Windows machine.

## Workflow A: refresh the Ganglian Excel plugin

Use this when the Excel workbook must be refreshed by the "Ganglian Data 2.0" Excel add-in.
This workflow only opens Excel, clicks the add-in refresh button, saves, and closes Excel.
It does not import data into PostgreSQL.

### Coordinate calibration

If the add-in button cannot be detected by UIAutomation, calibrate the update button coordinate once.
Open Excel manually, maximize the window, move the mouse to the "Update All Pages" button, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\set_ganglian_click_config.ps1 -ExcelPath "<EXCEL_PATH>" -SetUpdate -CountdownSeconds 8
```

This writes:

```text
artifacts\ganglian_click_config.json
```

### Manual plugin refresh

Preferred desktop mode, which launches Excel normally so the add-in toolbar can load:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh_ganglian_excel_plugin_desktop.ps1 -ExcelPath "<EXCEL_PATH>" -RefreshWaitSeconds 240
```

### Install plugin refresh task

Recommended time: 07:50.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_ganglian_plugin_refresh_task.ps1 -ExcelPath "<EXCEL_PATH>" -RunTime "07:50" -DesktopMode -RefreshWaitSeconds 240 -RunAtLogon
```

Task name:

```text
Zhonglu-Ganglian-ExcelPluginRefresh
```

## Workflow B: import Excel data into PostgreSQL

This workflow only reads the workbook and imports parsed time-series rows into PostgreSQL.
It does not open or refresh the Ganglian add-in.

### Manual dry run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_daily_excel_import.ps1 -ExcelPath "<EXCEL_PATH>" -DatabaseHost "<DB_HOST>" -DatabasePassword "<DB_PASSWORD>" -DryRun
```

### Manual import

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_daily_excel_import.ps1 -ExcelPath "<EXCEL_PATH>" -DatabaseHost "<DB_HOST>" -DatabasePassword "<DB_PASSWORD>"
```

### Install import task

Recommended time: 08:00, after the plugin refresh task has finished.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_daily_excel_import_task.ps1 -ExcelPath "<EXCEL_PATH>" -RunTime "08:00" -RunAtLogon -DatabaseHost "<DB_HOST>" -DatabasePassword "<DB_PASSWORD>"
```

Task name:

```text
Zhonglu-OilResearch-DailyExcelImport
```

## PostgreSQL network requirements

The PostgreSQL host must allow the shared machine to connect to port 5432.
Check these on the database host:

- `postgresql.conf`: `listen_addresses` includes the LAN interface or `*`.
- `pg_hba.conf`: the shared machine IP or subnet is allowed with `scram-sha-256`.
- Windows Firewall allows inbound TCP 5432.

No real API keys, database passwords, or internal endpoint values should be committed to Git.
Use local config files or command-line parameters on the shared machine.
