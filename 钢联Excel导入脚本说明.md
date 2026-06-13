# 模型预测基础数据 Excel 导入脚本说明

## 作用

脚本用于读取根目录下的 `模型预测基础数据.xlsx`，把其中可用于价格预测的核心指标写入系统 PostgreSQL。

这份文件替代原来的 `test.xlsx` 作为默认导入文件。脚本保留数据来源编码 `ganglian_excel_import`，是为了让系统现有取数链路继续生效，不需要改动预测服务里的来源优先级。

## Excel 结构

脚本按以下固定结构读取每个有效 Sheet：

| 行号 | 含义 |
|---:|---|
| 第 2 行 | 指标名称 |
| 第 3 行 | 单位 |
| 第 4 行 | 数据来源 |
| 第 5 行 | 指标编码 |
| 第 6 行 | 频度 |
| 第 7 行 | 时间区间 |
| 第 8 行 | 指标描述 |
| 第 9 行 | 结束时间 |
| 第 10 行 | 更新时间 |
| 第 11 行起 | 第 1 列为日期，后续列为各指标历史值 |

空白/影子 Sheet 会自动跳过，例如 `BBPTACShadowWks0001`。

## 当前默认导入范围

默认只导入已映射到系统模型字段的核心指标，未映射字段不入库，避免把暂时不用的数据混进预测口径。

当前共导入 22 个指标：

| 类型 | 系统指标编码 | 含义 |
|---|---|---|
| 价格 | `sd_gas92_market` | 山东 92# 汽油市场现汇价 |
| 价格 | `cn_gas92_market` | 全国 92# 汽油市场价 |
| 价格 | `east_china_gas92_market` | 华东 92# 汽油市场价 |
| 价格 | `north_china_gas92_market` | 华北 92# 汽油市场价 |
| 价格 | `south_china_gas92_market` | 华南 92# 汽油市场价 |
| 价格 | `central_china_gas92_market` | 华中 92# 汽油市场价 |
| 价格 | `northwest_gas92_market` | 西北 92# 汽油市场价 |
| 价格 | `southwest_gas92_market` | 西南 92# 汽油市场价 |
| 价格 | `northeast_gas92_market` | 东北 92# 汽油市场价 |
| 价格 | `sd_diesel0_market` | 山东 0# 柴油市场现汇价 |
| 价格 | `cn_diesel0_market` | 全国 0# 柴油市场价 |
| 价格 | `east_china_diesel0_market` | 华东 0# 柴油市场价 |
| 价格 | `north_china_diesel0_market` | 华北 0# 柴油市场价 |
| 价格 | `south_china_diesel0_market` | 华南 0# 柴油市场价 |
| 价格 | `central_china_diesel0_market` | 华中 0# 柴油市场价 |
| 价格 | `northwest_diesel0_market` | 西北 0# 柴油市场价 |
| 价格 | `southwest_diesel0_market` | 西南 0# 柴油市场价 |
| 价格 | `northeast_diesel0_market` | 东北 0# 柴油市场价 |
| 供应 | `sd_crude_run_weekly` | 山东独立炼厂常减压产能利用率 |
| 需求 | `sd_gas_sales_weekly` | 山东独立炼厂汽油出货量 |
| 需求 | `sd_gas_production_weekly` | 山东独立炼厂汽油产量 |
| 库存 | `shandong_independent_refinery_inventory` | 山东独立炼厂汽油厂内库存 |

其中产销率不直接从 Excel 读取，而是在模型特征中按以下公式计算：

```text
山东地炼汽油产销率 = 山东独立炼厂汽油出货量 / 山东独立炼厂汽油产量 × 100
```

## 写入数据表

导入后的时序数据写入：

```text
oil_research.fact_market_timeseries
```

原始导入摘要写入：

```text
oil_research.ods_raw_market
```

数据来源编码：

```text
ganglian_excel_import
```

系统构建预测特征时，会把该来源作为本地基础数据覆盖到 ETA/Wind 等来源之上。

## 替换旧数据

正式导入建议使用：

```powershell
python scripts\import_ganglian_excel_timeseries.py --replace-source --summary-output artifacts\model_base_excel_import_summary.json
```

`--replace-source` 只会删除并替换 `ganglian_excel_import` 这个来源下的数据：

- `oil_research.fact_market_timeseries`
- `oil_research.ods_raw_market`

不会删除 Wind、隆众 OpenAPI、手工模板、新闻事件等其他来源的数据。

## 先解析不入库

```powershell
python scripts\import_ganglian_excel_timeseries.py --dry-run
```

如果需要临时导入全部列，可以显式增加：

```powershell
python scripts\import_ganglian_excel_timeseries.py --all-columns --dry-run
```

但预测系统默认不建议使用 `--all-columns`。

## 指定文件或远程数据库

可以用参数指定 Excel 文件：

```powershell
python scripts\import_ganglian_excel_timeseries.py --excel D:\data\模型预测基础数据.xlsx --replace-source
```

也可以写入远程服务器数据库：

```powershell
python scripts\import_ganglian_excel_timeseries.py `
  --excel D:\data\模型预测基础数据.xlsx `
  --database-url "postgresql+psycopg://用户名:密码@服务器IP:5432/postgres" `
  --schema oil_research `
  --replace-source
```

Windows 定时任务可以通过环境变量配置：

```powershell
setx GANGLIAN_EXCEL_PATH "D:\data\模型预测基础数据.xlsx"
setx OIL_RESEARCH_DB_URL "postgresql+psycopg://用户名:密码@服务器IP:5432/postgres"
setx OIL_RESEARCH_DB_SCHEMA "oil_research"
```

## 指定日期范围

```powershell
python scripts\import_ganglian_excel_timeseries.py --start-date 2026-06-01 --end-date 2026-06-11 --replace-source
```

注意：如果使用 `--replace-source`，会先清空该来源已有数据，再写入指定日期范围的数据。只想补充局部日期时不要加 `--replace-source`。

## 导入摘要

每次执行会生成摘要文件：

```text
artifacts/model_base_excel_import_summary.json
```

摘要包含：

- Excel 文件路径
- Sheet 数量与跳过的 Sheet
- 识别到的核心指标数量
- 实际写入的时序行数
- 日期范围
- 已映射指标清单
- 未映射指标清单
- 替换导入时删除的旧数据行数

## 后续打包 exe

安装依赖：

```powershell
python -m pip install -r requirements_ganglian_importer.txt
```

打包：

```powershell
scripts\build_ganglian_excel_importer_exe.bat
```

生成文件：

```text
dist\ganglian_excel_importer.exe
```

放到另一台 Windows 电脑后，可以直接执行：

```powershell
dist\ganglian_excel_importer.exe --excel D:\data\模型预测基础数据.xlsx --database-url "postgresql+psycopg://用户名:密码@服务器IP:5432/postgres" --schema oil_research --replace-source
```

