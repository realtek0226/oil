# 数据库清理重整审查报告

生成时间：2026-06-11 08:20

## 一、三轮审查结论

### 第一轮：代码依赖审查

数据库主要入口集中在 `app/services/postgres_snapshot_repository.py`，建表来源为 `sql/v1_schema.sql`，部分运行时表和字段由仓储层 `ensure_*` 方法补充。

明确被代码使用的核心表包括：

| 类别 | 表 |
| --- | --- |
| 维表 | `dim_indicator`、`dim_entity`、`dim_source` |
| 市场数据 | `fact_market_timeseries`、`ods_raw_market`、`ods_raw_news`、`ods_raw_forecast` |
| 预测输出 | `prediction_run`、`prediction_factor_breakdown`、`prediction_llm_label`、`agent_run_log` |
| 权限与审计 | `app_user`、`app_role`、`app_permission`、`app_user_role`、`app_user_permission`、`app_user_session`、`app_usage_log` |
| 业务配置 | `regional_freight_setting` |

`sql/v1_schema.sql` 中存在多张预留表，当前代码未直接写入：`alert_case`、`business_action_recommendation`、`fact_calendar_event`、`fact_forecast_snapshot`、`fact_news_event`、`feature_registry`、`feature_snapshot`、`feature_materialization_log`、`manual_override_log`、`ods_raw_calendar`、`publish_audit_log`。

### 第二轮：真实数据库审查

当前 schema：`oil_research`。

| 表 | 行数 | 空间 | 判断 |
| --- | ---: | ---: | --- |
| `fact_market_timeseries` | 474674 | 约 346MB | 最大业务事实表，保存历史价格、手工数据、隆众库存等，不能直接清 |
| `agent_run_log` | 4038 | 约 19MB | 单行 JSON 较重，后续可做保留期策略 |
| `ods_raw_news` | 3282 | 约 12MB | 新闻归档，参与资讯和事件回溯，暂不清 |
| `ods_raw_market` | 2607 | 约 3.8MB | 原始市场快照和政策等归档，暂不清 |
| `prediction_run` | 545 | 约 3.5MB | 预测记录，暂不清 |
| `app_usage_log` | 5320 | 约 2.6MB | 使用记录，暂不清 |

空表占用很小，单表通常 16KB 到 40KB。直接删空表对性能和空间收益很小，但会增加未来功能恢复成本，因此本次不删除。

### 第三轮：查询路径与风险审查

核心慢点不在空表，而在 `fact_market_timeseries` 的常用过滤条件。

常用查询路径：

```sql
source_code + indicator_codes + dt 范围
source_code + dt 范围
```

原索引主要是：

```sql
(entity_id, indicator_id, observation_time desc)
(dt)
(publish_time desc)
```

缺少按 `source_id` 开头的组合索引，导致部分查询先扫日期范围再筛来源。

## 二、本次已执行的低风险优化

### 1. 新增索引

已在当前数据库执行，并同步写入 `sql/v1_schema.sql`：

```sql
create index concurrently if not exists idx_fact_market_source_dt
on oil_research.fact_market_timeseries (source_id, dt desc);

create index concurrently if not exists idx_fact_market_source_indicator_dt
on oil_research.fact_market_timeseries (source_id, indicator_id, dt, publish_time desc);
```

### 2. 清理明确无效数据

| 清理项 | 清理前 | 清理后 | 说明 |
| --- | ---: | ---: | --- |
| 过期或撤销会话 `app_user_session` | 296 | 0 | 只清理已过期/已撤销 session，不影响有效登录 |
| 孤立智能体日志 `agent_run_log` | 8 | 0 | 只清理没有对应 `prediction_run` 的日志 |

未发现以下重复数据：

| 检查项 | 结果 |
| --- | ---: |
| `fact_market_timeseries` 业务唯一键重复 | 0 |
| `ods_raw_market` 业务唯一键重复 | 0 |
| `ods_raw_news` 业务唯一键重复 | 0 |
| `prediction_factor_breakdown` 孤立记录 | 0 |

### 3. 刷新统计信息

已执行 `ANALYZE`：

```text
fact_market_timeseries
ods_raw_market
ods_raw_news
ods_raw_forecast
prediction_run
agent_run_log
app_user_session
app_usage_log
```

## 三、优化效果验证

### 1. ETA/市场历史查询

查询条件：`eta_market_snapshot` + 3 个指标 + 近 30 日。

| 指标 | 优化前 | 优化后 |
| --- | ---: | ---: |
| 执行时间 | 约 57ms | 约 17ms |
| 使用索引 | 旧唯一索引绕行 | `idx_fact_market_source_indicator_dt` |

### 2. 隆众库存范围查询

查询条件：`oilchem_openapi_inventory` + 日期范围。

| 指标 | 优化前 | 优化后 |
| --- | ---: | ---: |
| 执行时间 | 约 24ms | 约 2.4ms |
| 扫描方式 | 先按 `dt` 扫约 2.5 万行再筛来源 | `idx_fact_market_source_dt` 直接命中 44 行 |

## 四、本次没有删除的内容及原因

| 对象 | 是否删除 | 原因 |
| --- | --- | --- |
| `fact_market_timeseries` 历史数据 | 否 | 当前预测、历史走势、区域价差和回测都依赖 |
| `ods_raw_news` / `ods_raw_market` 原始归档 | 否 | 用于资讯、政策、事件、隆众原文和可追溯性 |
| `prediction_run` / `agent_run_log` | 否 | 用于智能体历史输出、解释链和预测复盘 |
| 0 行预留表 | 否 | 空间收益极小，且可能对应后续预警、特征、发布审计模块 |
| 无用字段 | 否 | 目前字段多为 schema 预留或 JSON 审计用途，直接删会破坏兼容性，需另走迁移方案 |

## 五、后续建议

1. 建立数据保留策略，而不是手工随意删：
   - `app_user_session`：定时清理过期/撤销 session。
   - `app_usage_log`：建议保留 90 天，超过 90 天可归档。
   - `agent_run_log`：建议保留 90 天或仅保留最近 N 次预测的详细输入输出。

2. 对 0 行预留表先标记为“未启用”，不要立刻删除。若 1 个月内确认不做对应模块，再统一出迁移脚本删除。

3. 对 `fact_market_timeseries` 不建议删历史。若后续空间继续增长，应优先考虑：
   - 按年份或来源分区；
   - 对高频实时快照做降采样；
   - 保留日度最终值，归档盘中重复快照。

4. 当前新增的两个索引已显著改善常用查询，下一步可继续针对首页接口和一屏看清接口做 `EXPLAIN ANALYZE`，只补真实慢查询需要的索引。
