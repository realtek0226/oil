from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, time, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import bindparam, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.settings import get_settings
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository


PRICE_COLUMN_MAP = {
    "山东92#现货价(元/吨)": ("sd_gas92_market", "山东92#汽油市场价", "SHANDONG", "山东", "province"),
    "全国92#现货价(元/吨)": ("cn_gas92_market", "全国92#汽油市场价", "NATIONAL", "全国", "country"),
    "华东92#现货价": ("east_china_gas92_market", "华东92#汽油市场价", "EAST_CHINA", "华东", "macro_region"),
    "华北92#现货价": ("north_china_gas92_market", "华北92#汽油市场价", "NORTH_CHINA", "华北", "macro_region"),
    "华南92#现货价": ("south_china_gas92_market", "华南92#汽油市场价", "SOUTH_CHINA", "华南", "macro_region"),
    "华中92#现货价": ("central_china_gas92_market", "华中92#汽油市场价", "CENTRAL_CHINA", "华中", "macro_region"),
    "西北92#现货价": ("northwest_gas92_market", "西北92#汽油市场价", "NORTHWEST", "西北", "macro_region"),
    "西南92#现货价": ("southwest_gas92_market", "西南92#汽油市场价", "SOUTHWEST", "西南", "macro_region"),
    "东北92#现货价": ("northeast_gas92_market", "东北92#汽油市场价", "NORTHEAST", "东北", "macro_region"),
    "汽油-石脑油价差": ("sd_gas_naphtha_spread", "山东汽油-石脑油价差", "SHANDONG", "山东", "province"),
    "MTBE价格": ("sd_mtbe_price", "山东MTBE价格", "SHANDONG", "山东", "province"),
    "直馏石脑油价格": ("sd_naphtha_price", "山东直馏石脑油价格", "SHANDONG", "山东", "province"),
    "山东92#最高零售价(元/吨)": ("sd_ceiling_gas", "山东92#汽油最高零售价", "SHANDONG", "山东", "province"),
}

MANUAL_FACTOR_COLUMN_MAP = {
    "汽油产销率3日均值(%)": ("sales_production_ratio_d3_avg", "汽油产销率3日均值", "SHANDONG_REFINERY_GASOLINE", "山东地炼汽油", "province"),
    "汽油产销率7日均值(%)": ("sales_production_ratio_w1_avg", "汽油产销率7日均值", "SHANDONG_REFINERY_GASOLINE", "山东地炼汽油", "province"),
}


def is_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not pd.isna(value) and math.isfinite(float(value))
    except Exception:
        return False


def parse_date(value: Any, fallback: date | None = None) -> date | None:
    try:
        if pd.isna(value):
            return fallback
    except Exception:
        pass
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value or "").strip()
    if not text_value:
        return fallback
    try:
        return pd.Timestamp(text_value).date()
    except Exception:
        return fallback


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def payload_hash(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def find_header_row(df: pd.DataFrame, required: str) -> int:
    for idx, row in df.iterrows():
        if required in [str(item).strip() for item in row.tolist()]:
            return int(idx)
    raise ValueError(f"未找到表头字段: {required}")


def read_table(path: Path, sheet_name: str, required_header: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    header_row = find_header_row(raw, required_header)
    headers = [str(item).strip() if not pd.isna(item) else f"未命名{idx}" for idx, item in enumerate(raw.iloc[header_row].tolist())]
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = headers
    data = data.dropna(how="all")
    return data


def first_existing_file(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
        raise FileNotFoundError(path)
    candidates = sorted(
        [path for path in ROOT.glob("*.xlsx") if path.stat().st_size == 72411],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise FileNotFoundError("未找到手工采集模板文件")


def extract_manual_payload(path: Path) -> dict[str, Any]:
    daily = read_table(path, "01每日主数据", "数据日期")
    if daily.empty:
        raise ValueError("01每日主数据没有可导入数据")
    daily_records: list[dict[str, Any]] = []
    for _, row in daily.iterrows():
        row_dict = row.to_dict()
        row_date = parse_date(row_dict.get("数据日期"))
        if row_date is None:
            continue
        daily_records.append({str(k): clean_value(v) for k, v in row_dict.items()})
    if not daily_records:
        raise ValueError("01每日主数据缺少数据日期")
    daily_records = sorted(daily_records, key=lambda item: str(item.get("数据日期")))
    daily_row = daily_records[-1]
    observation_date = parse_date(daily_row.get("数据日期"))
    if observation_date is None:
        raise ValueError("01每日主数据缺少有效数据日期")

    lonzhong = read_table(path, "02隆众经营数据", "汽油产销率(%)")
    lonzhong_row = lonzhong.iloc[0].to_dict() if not lonzhong.empty else {}
    regional = read_table(path, "03区域价格运费", "数据日期")

    price_values_by_date: dict[str, dict[str, float]] = {}
    for record in daily_records:
        record_date = parse_date(record.get("数据日期"))
        if record_date is None:
            continue
        values: dict[str, float] = {}
        for col_name, (indicator_code, *_meta) in PRICE_COLUMN_MAP.items():
            value = record.get(col_name)
            if is_number(value):
                values[indicator_code] = float(value)
        for col_name, (indicator_code, *_meta) in MANUAL_FACTOR_COLUMN_MAP.items():
            value = record.get(col_name)
            if is_number(value):
                values[indicator_code] = float(value)
        if values:
            price_values_by_date[record_date.isoformat()] = values
    price_values = price_values_by_date.get(observation_date.isoformat()) or {}

    ratio_records = []
    for record in daily_records:
        record_date = parse_date(record.get("数据日期"))
        if record_date is None or not is_number(record.get("山东地炼汽油产销率D1(%)")):
            continue
        ratio_records.append(
            {
                "observation_date": record_date.isoformat(),
                "publish_time": datetime.combine(record_date, time(18, 0)).isoformat(),
                "title": f"手工采集：山东地炼成品油产销率 {record_date.isoformat()}",
                "url": f"manual://prediction-template/{path.name}/production-sales-ratio/{record_date.isoformat()}",
                "gasoline_ratio": float(record.get("山东地炼汽油产销率D1(%)")),
                "gasoline_previous_ratio": float(record.get("汽油产销率前值(%)")) if is_number(record.get("汽油产销率前值(%)")) else None,
                "gasoline_change_pct": float(record.get("汽油产销率变化(百分点)")) if is_number(record.get("汽油产销率变化(百分点)")) else None,
                "diesel_ratio": None,
                "diesel_previous_ratio": None,
                "diesel_change_pct": None,
                "source": "manual_prediction_template",
            }
        )

    ratio_record = {
        "observation_date": observation_date.isoformat(),
        "publish_time": datetime.combine(observation_date, time(18, 0)).isoformat(),
        "title": f"手工采集：山东地炼成品油产销率 {observation_date.isoformat()}",
        "url": f"manual://prediction-template/{path.name}/production-sales-ratio/{observation_date.isoformat()}",
        "gasoline_ratio": float(lonzhong_row.get("汽油产销率(%)")) if is_number(lonzhong_row.get("汽油产销率(%)")) else None,
        "gasoline_previous_ratio": float(lonzhong_row.get("汽油前值(%)")) if is_number(lonzhong_row.get("汽油前值(%)")) else None,
        "gasoline_change_pct": float(lonzhong_row.get("汽油变化(百分点)")) if is_number(lonzhong_row.get("汽油变化(百分点)")) else None,
        "diesel_ratio": float(lonzhong_row.get("柴油产销率(%)")) if is_number(lonzhong_row.get("柴油产销率(%)")) else None,
        "diesel_previous_ratio": float(lonzhong_row.get("柴油前值(%)")) if is_number(lonzhong_row.get("柴油前值(%)")) else None,
        "diesel_change_pct": float(lonzhong_row.get("柴油变化(百分点)")) if is_number(lonzhong_row.get("柴油变化(百分点)")) else None,
        "source": "manual_prediction_template",
    }
    if ratio_record.get("gasoline_ratio") is not None:
        existing_dates = {item["observation_date"] for item in ratio_records}
        if ratio_record["observation_date"] not in existing_dates:
            ratio_records.append(ratio_record)

    weekly_records = []
    if is_number(lonzhong_row.get("（中国）产能利用率(%)")):
        weekly_records.append(
            {
                "observation_date": observation_date.isoformat(),
                "period_start": parse_date(lonzhong_row.get("周期开始"), fallback=observation_date).isoformat(),
                "period_end": parse_date(lonzhong_row.get("周期结束"), fallback=observation_date).isoformat(),
                "publish_time": datetime.combine(observation_date, time(18, 0)).isoformat(),
                "title": f"手工采集：山东地炼周度产能利用率 {observation_date.isoformat()}",
                "url": f"manual://prediction-template/{path.name}/capacity-utilization/{observation_date.isoformat()}",
                "metric_type": "capacity_utilization",
                "capacity_utilization": float(lonzhong_row.get("（中国）产能利用率(%)")),
                "capacity_utilization_wow_pct": float(lonzhong_row.get("产能利用率周环比")) if is_number(lonzhong_row.get("产能利用率周环比")) else None,
                "capacity_utilization_yoy_pct": float(lonzhong_row.get("产能利用率同比")) if is_number(lonzhong_row.get("产能利用率同比")) else None,
                "source": "manual_prediction_template",
            }
        )
    if is_number(lonzhong_row.get("综合炼油利润(元/吨)")):
        weekly_records.append(
            {
                "observation_date": observation_date.isoformat(),
                "period_start": parse_date(lonzhong_row.get("周期开始"), fallback=observation_date).isoformat(),
                "period_end": parse_date(lonzhong_row.get("周期结束"), fallback=observation_date).isoformat(),
                "publish_time": datetime.combine(observation_date, time(18, 0)).isoformat(),
                "title": f"手工采集：山东地炼综合炼油利润 {observation_date.isoformat()}",
                "url": f"manual://prediction-template/{path.name}/refining-profit/{observation_date.isoformat()}",
                "metric_type": "refining_profit",
                "refining_profit": float(lonzhong_row.get("综合炼油利润(元/吨)")),
                "refining_profit_wow_pct": float(lonzhong_row.get("利润周环比(%)")) if is_number(lonzhong_row.get("利润周环比(%)")) else None,
                "refining_profit_yoy_pct": float(lonzhong_row.get("利润同比(%)")) if is_number(lonzhong_row.get("利润同比(%)")) else None,
                "crude_cost": float(lonzhong_row.get("原油成本(元/吨)")) if is_number(lonzhong_row.get("原油成本(元/吨)")) else None,
                "crude_cost_change": float(lonzhong_row.get("原油成本变化")) if is_number(lonzhong_row.get("原油成本变化")) else None,
                "comprehensive_revenue": float(lonzhong_row.get("综合收入(元/吨)")) if is_number(lonzhong_row.get("综合收入(元/吨)")) else None,
                "comprehensive_revenue_change": float(lonzhong_row.get("综合收入变化")) if is_number(lonzhong_row.get("综合收入变化")) else None,
                "source": "manual_prediction_template",
            }
        )
    daily_weekly_existing = {
        (item.get("observation_date"), item.get("metric_type"))
        for item in weekly_records
    }
    for record in daily_records:
        record_date = parse_date(record.get("数据日期"))
        if record_date is None:
            continue
        if is_number(record.get("山东地炼产能利用率(%)")):
            key = (record_date.isoformat(), "capacity_utilization")
            weekly_records = [
                item
                for item in weekly_records
                if (item.get("observation_date"), item.get("metric_type")) != key
            ]
            daily_weekly_existing.discard(key)
            if key not in daily_weekly_existing:
                weekly_records.append(
                    {
                        "observation_date": record_date.isoformat(),
                        "period_start": record_date.isoformat(),
                        "period_end": record_date.isoformat(),
                        "publish_time": datetime.combine(record_date, time(18, 0)).isoformat(),
                        "title": f"手工采集：山东地炼产能利用率 {record_date.isoformat()}",
                        "url": f"manual://prediction-template/{path.name}/daily-capacity-utilization/{record_date.isoformat()}",
                        "metric_type": "capacity_utilization",
                        "capacity_utilization": float(record.get("山东地炼产能利用率(%)")),
                        "capacity_utilization_wow_pct": float(record.get("产能利用率周环比(百分点)")) if is_number(record.get("产能利用率周环比(百分点)")) else None,
                        "capacity_utilization_yoy_pct": None,
                        "source": "manual_prediction_template",
                    }
                )
                daily_weekly_existing.add(key)
        if is_number(record.get("山东地炼综合炼油利润(元/吨)")):
            key = (record_date.isoformat(), "refining_profit")
            weekly_records = [
                item
                for item in weekly_records
                if (item.get("observation_date"), item.get("metric_type")) != key
            ]
            daily_weekly_existing.discard(key)
            if key not in daily_weekly_existing:
                weekly_records.append(
                    {
                        "observation_date": record_date.isoformat(),
                        "period_start": record_date.isoformat(),
                        "period_end": record_date.isoformat(),
                        "publish_time": datetime.combine(record_date, time(18, 0)).isoformat(),
                        "title": f"手工采集：山东地炼综合炼油利润 {record_date.isoformat()}",
                        "url": f"manual://prediction-template/{path.name}/daily-refining-profit/{record_date.isoformat()}",
                        "metric_type": "refining_profit",
                        "refining_profit": float(record.get("山东地炼综合炼油利润(元/吨)")),
                        "refining_profit_wow_pct": float(record.get("炼油利润周变化")) if is_number(record.get("炼油利润周变化")) else None,
                        "refining_profit_yoy_pct": None,
                        "source": "manual_prediction_template",
                    }
                )
                daily_weekly_existing.add(key)

    inventory_record = {
        "observation_date": observation_date.isoformat(),
        "publish_time": datetime.combine(observation_date, time(18, 0)).isoformat(),
        "title": f"手工采集：山东独立炼厂成品油库存 {observation_date.isoformat()}",
        "url": f"manual://prediction-template/{path.name}/inventory/{observation_date.isoformat()}",
        "total_inventory": float(lonzhong_row.get("成品油总库存(万吨)")) if is_number(lonzhong_row.get("成品油总库存(万吨)")) else None,
        "gasoline_inventory": float(lonzhong_row.get("汽油库存(万吨)")) if is_number(lonzhong_row.get("汽油库存(万吨)")) else None,
        "gasoline_inventory_change_mom": float(lonzhong_row.get("汽油库存环比(万吨)")) if is_number(lonzhong_row.get("汽油库存环比(万吨)")) else None,
        "gasoline_inventory_capacity_rate": float(lonzhong_row.get("汽油库容率(%)")) if is_number(lonzhong_row.get("汽油库容率(%)")) else None,
        "diesel_inventory": float(lonzhong_row.get("柴油库存(万吨)")) if is_number(lonzhong_row.get("柴油库存(万吨)")) else None,
        "diesel_inventory_change_mom": float(lonzhong_row.get("柴油库存环比(万吨)")) if is_number(lonzhong_row.get("柴油库存环比(万吨)")) else None,
        "diesel_inventory_capacity_rate": float(lonzhong_row.get("柴油库容率(%)")) if is_number(lonzhong_row.get("柴油库容率(%)")) else None,
        "source": "manual_prediction_template",
    }

    regional_rows = []
    regional_default_date = parse_date(daily_records[0].get("数据日期"), fallback=observation_date)
    for _, row in regional.iterrows():
        region_code = str(row.get("区域编码") or "").strip()
        if not region_code:
            continue
        row_date = parse_date(row.get("数据日期"), fallback=regional_default_date)
        regional_rows.append(
            {
                "date": row_date.isoformat() if row_date else observation_date.isoformat(),
                "region_code": region_code,
                "region_name": clean_value(row.get("区域名称")),
                "shandong_price": clean_value(row.get("山东92#现货价")),
                "target_region_price": clean_value(row.get("目标区域92#现货价")),
                "target_minus_shandong_spread": clean_value(row.get("区域价差=目标-山东")),
                "freight": clean_value(row.get("手工运费(元/吨)")),
                "netback_spread": clean_value(row.get("净回款价差=区域价差-运费")),
                "freight_source": clean_value(row.get("运费来源")),
            }
        )

    return {
        "source_file": str(path),
        "observation_date": observation_date.isoformat(),
        "price_values": price_values,
        "price_values_by_date": price_values_by_date,
        "ratio_record": ratio_record,
        "ratio_records": ratio_records,
        "weekly_records": weekly_records,
        "inventory_record": inventory_record,
        "regional_rows": regional_rows,
        "daily_records": daily_records,
        "daily_row": {str(k): clean_value(v) for k, v in daily_row.items()},
        "lonzhong_row": {str(k): clean_value(v) for k, v in lonzhong_row.items()},
    }


def upsert_manual_market_prices(repository: PostgresSnapshotRepository, payload: dict[str, Any]) -> int:
    if not repository.engine:
        return 0
    now = datetime.now(timezone.utc)
    total_saved = 0
    all_indicator_rows = []
    indicator_meta_map = {**PRICE_COLUMN_MAP, **MANUAL_FACTOR_COLUMN_MAP}
    price_values_by_date = payload.get("price_values_by_date") or {payload["observation_date"]: payload.get("price_values") or {}}
    for values in price_values_by_date.values():
        for indicator_code, value in values.items():
            col_name = next(key for key, meta in indicator_meta_map.items() if meta[0] == indicator_code)
            _, indicator_name, entity_code, entity_name, region_level = indicator_meta_map[col_name]
            unit = "%" if indicator_code.startswith("sales_production_ratio") else "元/吨"
            all_indicator_rows.append(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": indicator_name,
                    "category": "manual_market",
                    "sub_category": "gasoline_92",
                    "unit": unit,
                    "freq": "daily",
                    "value_type": "number",
                    "fill_policy_default": "latest_available",
                    "description": "手工采集模板导入",
                    "entity_code": entity_code,
                    "entity_name": entity_name,
                    "entity_type": "market_region",
                    "region_level": region_level,
                    "product_family": "GASOLINE_92",
                    "value_num": value,
                }
            )
    indicator_rows = list({row["indicator_code"]: row for row in all_indicator_rows}.values())
    ts_rows = []
    if not indicator_rows:
        return 0

    with repository.engine.begin() as connection:
        source_id = repository._ensure_source_ids(connection, {"manual_prediction_template"})["manual_prediction_template"]
        repository._ensure_indicators(connection, indicator_rows)
        repository._ensure_entities(connection, indicator_rows)
        raw_payload = {
            "source_file": payload["source_file"],
            "observation_date": payload["observation_date"],
            "daily_records": payload.get("daily_records") or [payload["daily_row"]],
            "regional_rows": payload["regional_rows"],
        }
        observation_date = pd.Timestamp(payload["observation_date"]).date()
        source_record_id = f"manual-prediction-template:{observation_date.isoformat()}"
        connection.execute(
            text(
                f"""
                insert into {repository._fqtn('ods_raw_market')} (
                    source_id, source_record_id, topic, source_event_time, payload, payload_hash, dt
                )
                values (
                    :source_id, :source_record_id, :topic, :source_event_time,
                    cast(:payload as jsonb), :payload_hash, :dt
                )
                on conflict (source_id, source_record_id, payload_hash) do nothing
                """
            ),
            {
                "source_id": source_id,
                "source_record_id": source_record_id,
                "topic": "manual_prediction_template",
                "source_event_time": datetime.combine(observation_date, time(0, 0)),
                "payload": json.dumps(raw_payload, ensure_ascii=False, default=str),
                "payload_hash": payload_hash(raw_payload),
                "dt": observation_date,
            },
        )
        rows = list(
            connection.execute(
                text(
                    f"""
                    select i.indicator_id, i.indicator_code, e.entity_id, e.entity_code
                    from {repository._fqtn('dim_indicator')} i
                    join {repository._fqtn('dim_entity')} e on 1 = 1
                    where i.indicator_code in :indicator_codes
                      and e.entity_code in :entity_codes
                    """
                ).bindparams(bindparam("indicator_codes", expanding=True), bindparam("entity_codes", expanding=True)),
                {
                    "indicator_codes": [row["indicator_code"] for row in indicator_rows],
                    "entity_codes": [row["entity_code"] for row in indicator_rows],
                },
            ).mappings()
        )
        indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
        entity_id_map = {str(row["entity_code"]): int(row["entity_id"]) for row in rows}
        meta_by_code = {row["indicator_code"]: row for row in indicator_rows}
        for date_text, values in price_values_by_date.items():
            row_date = pd.Timestamp(date_text).date()
            row_source_record_id = f"manual-prediction-template:{row_date.isoformat()}"
            for indicator_code, value in values.items():
                row = meta_by_code[indicator_code]
                ts_rows.append(
                    {
                        "indicator_id": indicator_id_map[indicator_code],
                        "entity_id": entity_id_map[row["entity_code"]],
                        "observation_time": datetime.combine(row_date, time(0, 0)),
                        "publish_time": now,
                        "freq": "daily",
                        "value_num": value,
                        "value_text": None,
                        "unit": row["unit"],
                        "currency": None if row["unit"] == "%" else "CNY",
                        "source_id": source_id,
                        "source_record_id": row_source_record_id,
                        "is_final": True,
                        "revision_no": 1,
                        "quality_flag": "ok",
                        "effective_from": now,
                        "effective_to": None,
                        "dt": row_date,
                    }
                )
        if not ts_rows:
            return 0
        result = connection.execute(
            text(
                f"""
                insert into {repository._fqtn('fact_market_timeseries')} (
                    indicator_id, entity_id, observation_time, publish_time, freq, value_num,
                    value_text, unit, currency, source_id, source_record_id, is_final,
                    revision_no, quality_flag, effective_from, effective_to, dt
                )
                values (
                    :indicator_id, :entity_id, :observation_time, :publish_time, :freq, :value_num,
                    :value_text, :unit, :currency, :source_id, :source_record_id, :is_final,
                    :revision_no, :quality_flag, :effective_from, :effective_to, :dt
                )
                on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                do update set
                    publish_time = excluded.publish_time,
                    value_num = excluded.value_num,
                    source_record_id = excluded.source_record_id,
                    quality_flag = excluded.quality_flag,
                    effective_from = excluded.effective_from,
                    dt = excluded.dt
                """
            ),
            ts_rows,
        )
        total_saved += int(result.rowcount or 0)
        return total_saved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-output", default="artifacts/manual_import_summary_20260605.json")
    args = parser.parse_args()

    path = first_existing_file(args.file)
    payload = extract_manual_payload(path)
    summary = {
        "source_file": payload["source_file"],
        "observation_date": payload["observation_date"],
        "daily_row_count": len(payload.get("daily_records") or []),
        "price_date_count": len(payload.get("price_values_by_date") or {}),
        "price_indicator_count": sum(len(values) for values in (payload.get("price_values_by_date") or {}).values()),
        "ratio_record_count": len(payload.get("ratio_records") or []),
        "ratio_has_gasoline": any(item.get("gasoline_ratio") is not None for item in (payload.get("ratio_records") or [])),
        "weekly_record_count": len(payload["weekly_records"]),
        "inventory_has_gasoline": payload["inventory_record"].get("gasoline_inventory") is not None,
        "regional_row_count": len(payload["regional_rows"]),
        "dry_run": bool(args.dry_run),
    }

    if not args.dry_run:
        settings = get_settings()
        repository = PostgresSnapshotRepository(settings.database)
        repository.ensure_schema()
        summary["market_timeseries_saved"] = upsert_manual_market_prices(repository, payload)
        summary["production_sales_saved"] = repository.save_oilchem_production_sales_records(payload.get("ratio_records") or [payload["ratio_record"]])
        summary["weekly_metrics_saved"] = repository.save_oilchem_weekly_metric_records(payload["weekly_records"])
        summary["inventory_saved"] = repository.save_oilchem_inventory_records([payload["inventory_record"]])

    out = ROOT / args.summary_output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "payload": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
