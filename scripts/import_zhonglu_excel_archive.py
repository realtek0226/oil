from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
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


SOURCE_CODE = "zhonglu_excel_archive"

ZHONGLU_DIR = (
    ROOT
    / "\u6570\u636e\u6e05\u5355\u53ca\u6253\u5206\u903b\u8f91"
    / "\u4e2d\u9c81"
)

CORE_INDICATOR_BY_NAME = {
    "汽油：国六：92#：市场现汇价：山东（日）": ("sd_gas92_market", "山东92#汽油市场现汇价", "SHANDONG", "山东", "province", "GASOLINE_92"),
    "汽油：国六：92#：市场价：中国（日）": ("cn_gas92_market", "全国92#汽油市场价", "NATIONAL", "全国", "country", "GASOLINE_92"),
    "汽油：国六：92#：市场价：华东地区（日）": ("east_china_gas92_market", "华东92#汽油市场价", "EAST_CHINA", "华东", "macro_region", "GASOLINE_92"),
    "汽油：国六：92#：市场价：华北地区（日）": ("north_china_gas92_market", "华北92#汽油市场价", "NORTH_CHINA", "华北", "macro_region", "GASOLINE_92"),
    "汽油：国六：92#：市场价：华南地区（日）": ("south_china_gas92_market", "华南92#汽油市场价", "SOUTH_CHINA", "华南", "macro_region", "GASOLINE_92"),
    "汽油：国六：92#：市场价：华中地区（日）": ("central_china_gas92_market", "华中92#汽油市场价", "CENTRAL_CHINA", "华中", "macro_region", "GASOLINE_92"),
    "汽油：国六：92#：市场价：西北地区（日）": ("northwest_gas92_market", "西北92#汽油市场价", "NORTHWEST", "西北", "macro_region", "GASOLINE_92"),
    "汽油：国六：92#：市场价：西南地区（日）": ("southwest_gas92_market", "西南92#汽油市场价", "SOUTHWEST", "西南", "macro_region", "GASOLINE_92"),
    "汽油：国六：92#：市场价：东北地区（日）": ("northeast_gas92_market", "东北92#汽油市场价", "NORTHEAST", "东北", "macro_region", "GASOLINE_92"),
    "柴油：国六：0#：市场现汇价：山东（日）": ("sd_diesel0_market", "山东0#柴油市场现汇价", "SHANDONG", "山东", "province", "DIESEL"),
    "柴油：国六：0#：市场价：中国（日）": ("cn_diesel0_market", "全国0#柴油市场价", "NATIONAL", "全国", "country", "DIESEL"),
    "柴油：国六：0#：市场价：华东地区（日）": ("east_china_diesel0_market", "华东0#柴油市场价", "EAST_CHINA", "华东", "macro_region", "DIESEL"),
    "柴油：国六：0#：市场价：华北地区（日）": ("north_china_diesel0_market", "华北0#柴油市场价", "NORTH_CHINA", "华北", "macro_region", "DIESEL"),
    "柴油：国六：0#：市场价：华南地区（日）": ("south_china_diesel0_market", "华南0#柴油市场价", "SOUTH_CHINA", "华南", "macro_region", "DIESEL"),
    "柴油：国六：0#：市场价：华中地区（日）": ("central_china_diesel0_market", "华中0#柴油市场价", "CENTRAL_CHINA", "华中", "macro_region", "DIESEL"),
    "柴油：国六：0#：市场价：西北地区（日）": ("northwest_diesel0_market", "西北0#柴油市场价", "NORTHWEST", "西北", "macro_region", "DIESEL"),
    "柴油：国六：0#：市场价：西南地区（日）": ("southwest_diesel0_market", "西南0#柴油市场价", "SOUTHWEST", "西南", "macro_region", "DIESEL"),
    "柴油：国六：0#：市场价：东北地区（日）": ("northeast_diesel0_market", "东北0#柴油市场价", "NORTHEAST", "东北", "macro_region", "DIESEL"),
    "汽油：出货量：山东：独立炼厂（周）": ("sd_gas_sales_weekly", "山东独立炼厂汽油出货量", "SHANDONG_REFINERY_GASOLINE", "山东独立炼厂汽油", "province", "GASOLINE_92"),
    '汽油：出货量：华东地区（除山东）：独立炼厂（周）': ('east_china_gasoline_shipments_weekly', '华东独立炼厂汽油出货量', 'EAST_CHINA_REFINERY_GASOLINE', '华东独立炼厂汽油', 'macro_region', 'GASOLINE_92'),
    '汽油：出货量：华北地区：独立炼厂（周）': ('north_china_gasoline_shipments_weekly', '华北独立炼厂汽油出货量', 'NORTH_CHINA_REFINERY_GASOLINE', '华北独立炼厂汽油', 'macro_region', 'GASOLINE_92'),
    '汽油：出货量：华南地区：独立炼厂（周）': ('south_china_gasoline_shipments_weekly', '华南独立炼厂汽油出货量', 'SOUTH_CHINA_REFINERY_GASOLINE', '华南独立炼厂汽油', 'macro_region', 'GASOLINE_92'),
    '汽油：出货量：华中地区：独立炼厂（周）': ('central_china_gasoline_shipments_weekly', '华中独立炼厂汽油出货量', 'CENTRAL_CHINA_REFINERY_GASOLINE', '华中独立炼厂汽油', 'macro_region', 'GASOLINE_92'),
    '汽油：出货量：西北地区：独立炼厂（周）': ('northwest_gasoline_shipments_weekly', '西北独立炼厂汽油出货量', 'NORTHWEST_REFINERY_GASOLINE', '西北独立炼厂汽油', 'macro_region', 'GASOLINE_92'),
    '汽油：出货量：西南地区：独立炼厂（周）': ('southwest_gasoline_shipments_weekly', '西南独立炼厂汽油出货量', 'SOUTHWEST_REFINERY_GASOLINE', '西南独立炼厂汽油', 'macro_region', 'GASOLINE_92'),
    '汽油：出货量：东北地区：独立炼厂（周）': ('northeast_gasoline_shipments_weekly', '东北独立炼厂汽油出货量', 'NORTHEAST_REFINERY_GASOLINE', '东北独立炼厂汽油', 'macro_region', 'GASOLINE_92'),
    '柴油：出货量：华东地区（除山东）：独立炼厂（周）': ('east_china_diesel_shipments_weekly', '华东独立炼厂柴油出货量', 'EAST_CHINA_REFINERY_DIESEL', '华东独立炼厂柴油', 'macro_region', 'DIESEL'),
    '柴油：出货量：华北地区：独立炼厂（周）': ('north_china_diesel_shipments_weekly', '华北独立炼厂柴油出货量', 'NORTH_CHINA_REFINERY_DIESEL', '华北独立炼厂柴油', 'macro_region', 'DIESEL'),
    '柴油：出货量：华南地区：独立炼厂（周）': ('south_china_diesel_shipments_weekly', '华南独立炼厂柴油出货量', 'SOUTH_CHINA_REFINERY_DIESEL', '华南独立炼厂柴油', 'macro_region', 'DIESEL'),
    '柴油：出货量：华中地区：独立炼厂（周）': ('central_china_diesel_shipments_weekly', '华中独立炼厂柴油出货量', 'CENTRAL_CHINA_REFINERY_DIESEL', '华中独立炼厂柴油', 'macro_region', 'DIESEL'),
    '柴油：出货量：西北地区：独立炼厂（周）': ('northwest_diesel_shipments_weekly', '西北独立炼厂柴油出货量', 'NORTHWEST_REFINERY_DIESEL', '西北独立炼厂柴油', 'macro_region', 'DIESEL'),
    '柴油：出货量：西南地区：独立炼厂（周）': ('southwest_diesel_shipments_weekly', '西南独立炼厂柴油出货量', 'SOUTHWEST_REFINERY_DIESEL', '西南独立炼厂柴油', 'macro_region', 'DIESEL'),
    '柴油：出货量：东北地区：独立炼厂（周）': ('northeast_diesel_shipments_weekly', '东北独立炼厂柴油出货量', 'NORTHEAST_REFINERY_DIESEL', '东北独立炼厂柴油', 'macro_region', 'DIESEL'),
    "汽油：产量：山东：独立炼厂（周）": ("sd_gasoline_independent_output_weekly", "山东独立炼厂汽油产量", "SHANDONG_REFINERY_GASOLINE", "山东独立炼厂汽油", "province", "GASOLINE_92"),
    "原油：常减压：产能利用率：山东：独立炼厂（周）": ("sd_crude_run_weekly", "山东独立炼厂原油常减压产能利用率", "SHANDONG_REFINERY", "山东独立炼厂", "province", "REFINED_OIL"),
    '成品油：常减压：产能利用率：山东：独立炼厂（周）': ('shandong_cdu_utilization_weekly', '山东独立炼厂成品油常减压产能利用率', 'SHANDONG_REFINERY', '山东独立炼厂', 'province', "REFINED_OIL"),
    '成品油：常减压：产能利用率：华东地区（除山东）：独立炼厂（周）': ('east_china_cdu_utilization_weekly', '华东独立炼厂成品油常减压产能利用率', 'EAST_CHINA_REFINERY', '华东独立炼厂', 'macro_region', "REFINED_OIL"),
    '成品油：常减压：产能利用率：华北地区：独立炼厂（周）': ('north_china_cdu_utilization_weekly', '华北独立炼厂成品油常减压产能利用率', 'NORTH_CHINA_REFINERY', '华北独立炼厂', 'macro_region', "REFINED_OIL"),
    '成品油：常减压：产能利用率：华南地区：独立炼厂（周）': ('south_china_cdu_utilization_weekly', '华南独立炼厂成品油常减压产能利用率', 'SOUTH_CHINA_REFINERY', '华南独立炼厂', 'macro_region', "REFINED_OIL"),
    '成品油：常减压：产能利用率：华中地区：独立炼厂（周）': ('central_china_cdu_utilization_weekly', '华中独立炼厂成品油常减压产能利用率', 'CENTRAL_CHINA_REFINERY', '华中独立炼厂', 'macro_region', "REFINED_OIL"),
    '成品油：常减压：产能利用率：西北地区：独立炼厂（周）': ('northwest_cdu_utilization_weekly', '西北独立炼厂成品油常减压产能利用率', 'NORTHWEST_REFINERY', '西北独立炼厂', 'macro_region', "REFINED_OIL"),
    '成品油：常减压：产能利用率：西南地区：独立炼厂（周）': ('southwest_cdu_utilization_weekly', '西南独立炼厂成品油常减压产能利用率', 'SOUTHWEST_REFINERY', '西南独立炼厂', 'macro_region', "REFINED_OIL"),
    '成品油：常减压：产能利用率：东北地区：独立炼厂（周）': ('northeast_cdu_utilization_weekly', '东北独立炼厂成品油常减压产能利用率', 'NORTHEAST_REFINERY', '东北独立炼厂', 'macro_region', "REFINED_OIL"),
    "成品油：炼油工序：实际毛利：山东：独立炼厂（周）": ("sd_refining_profit", "山东独立炼厂成品油实际毛利", "SHANDONG_REFINERY", "山东独立炼厂", "province", "REFINED_OIL"),
    "汽油：炼油工序：毛利：山东：独立炼厂（周）": ("sd_gasoline_refining_margin_weekly", "山东独立炼厂汽油炼油毛利", "SHANDONG_REFINERY_GASOLINE", "山东独立炼厂汽油", "province", "GASOLINE_92"),
    "柴油：炼油工序：毛利：山东：独立炼厂（周）": ("sd_diesel_refining_margin_weekly", "山东独立炼厂柴油炼油毛利", "SHANDONG_REFINERY_DIESEL", "山东独立炼厂柴油", "province", "DIESEL"),
    "汽油：厂内库存：山东：独立炼厂（周）": ("shandong_independent_refinery_inventory", "山东独立炼厂汽油厂内库存", "SHANDONG_REFINERY_GASOLINE", "山东独立炼厂汽油", "province", "GASOLINE_92"),
    "汽油：产销率：山东：独立炼厂（周）": ("sales_production_ratio_weekly", "山东独立炼厂汽油周度产销率", "SHANDONG_REFINERY_GASOLINE", "山东独立炼厂汽油", "province", "GASOLINE_92"),
    "汽油：商业库存：中国（周）": ("shandong_commercial_gasoline_inventory", "汽油商业库存中国周度", "NATIONAL_GASOLINE", "全国汽油", "country", "GASOLINE_92"),
    "汽油：贸易商：库存：中国（周）": ("shandong_trade_company_inventory", "汽油贸易商库存中国周度", "NATIONAL_GASOLINE", "全国汽油", "country", "GASOLINE_92"),
    "中国主营汽油库存": ("shandong_main_company_inventory", "中国主营汽油库存", "NATIONAL_GASOLINE", "全国汽油", "country", "GASOLINE_92"),
    "汽油：商业库存：中国（月）": ("shandong_trader_inventory", "汽油商业库存中国", "NATIONAL_GASOLINE", "全国汽油", "country", "GASOLINE_92"),
    "汽油：贸易商：库存：中国（月）": ("shandong_trade_company_inventory", "汽油贸易商库存中国", "NATIONAL_GASOLINE", "全国汽油", "country", "GASOLINE_92"),
}

SOURCE_FILES = [
    "\u6210\u54c1\u6cb9\u5468\u5ea6\u6570\u636e\uff08\u52ff\u52a8\uff09.xlsx",
    "\u6210\u54c1\u6cb9\u4ef7\u683c.xls",
    "\u533a\u57df\u4f9b\u9700.xlsx",
    "\u94a2\u8054\u6570\u636e_\u5404\u5730\u533a\u6c7d\u6cb9\u72ec\u7acb\u51fa\u8d27\u91cf.xls",
    "\u94a2\u8054\u6570\u636e_\u5404\u5730\u533a\u6c7d\u6cb9\u72ec\u7acb\u4ea7\u91cf.xls",
    "\u94a2\u8054\u6570\u636e_\u5404\u5730\u533a\u67f4\u6cb9\u72ec\u7acb\u51fa\u8d27\u91cf.xls",
    "\u94a2\u8054\u6570\u636e_\u5404\u5730\u533a\u67f4\u6cb9\u5730\u70bc\u4ea7\u91cf.xls",
    "\u94a2\u8054\u6570\u636e_\u5404\u5730\u533a\u6c7d\u6cb9\u4e3b\u8425\u4ea7\u91cf.xls",
    "\u94a2\u8054\u6570\u636e_\u5404\u5730\u533a\u67f4\u6cb9\u4e3b\u8425\u4ea7\u91cf.xls",
]


@dataclass(frozen=True)
class SeriesColumn:
    file_name: str
    sheet_name: str
    column_index: int
    indicator_name: str
    unit: str | None
    source_name: str | None
    source_indicator_code: str | None
    freq: str
    indicator_code: str
    entity_code: str
    entity_name: str
    region_level: str
    product_family: str


def is_number(value: Any) -> bool:
    try:
        return value is not None and not pd.isna(value) and math.isfinite(float(value))
    except Exception:
        return False


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def payload_hash(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def find_meta_row(raw: pd.DataFrame, label: str) -> int | None:
    for idx, row in raw.iterrows():
        values = [str(item).strip() for item in row.tolist() if not pd.isna(item)]
        if label in values:
            return int(idx)
    return None


def infer_freq(indicator_name: str, fallback: str | None = None) -> str:
    if "（日）" in indicator_name or "(日)" in indicator_name:
        return "daily"
    if "（周）" in indicator_name or "(周)" in indicator_name:
        return "weekly"
    if "（月）" in indicator_name or "(月)" in indicator_name:
        return "monthly"
    if "（季）" in indicator_name or "(季)" in indicator_name:
        return "quarterly"
    if "（年）" in indicator_name or "(年)" in indicator_name:
        return "yearly"
    if fallback:
        if fallback == "日":
            return "daily"
        if fallback == "周":
            return "weekly"
        if fallback == "月":
            return "monthly"
    return "unknown"


def fallback_indicator_code(source_indicator_code: str | None, indicator_name: str) -> str:
    if source_indicator_code and source_indicator_code.strip():
        return f"zhonglu_{source_indicator_code.strip().lower()}"
    digest = sha256(indicator_name.encode("utf-8")).hexdigest()[:12]
    return f"zhonglu_{digest}"


def infer_entity(indicator_name: str) -> tuple[str, str, str, str]:
    region_map = [
        ("山东", "SHANDONG", "山东", "province"),
        ("中国", "NATIONAL", "全国", "country"),
        ("华东地区", "EAST_CHINA", "华东", "macro_region"),
        ("华北地区", "NORTH_CHINA", "华北", "macro_region"),
        ("华南地区", "SOUTH_CHINA", "华南", "macro_region"),
        ("华中地区", "CENTRAL_CHINA", "华中", "macro_region"),
        ("西北地区", "NORTHWEST", "西北", "macro_region"),
        ("西南地区", "SOUTHWEST", "西南", "macro_region"),
        ("东北地区", "NORTHEAST", "东北", "macro_region"),
    ]
    for token, code, name, level in region_map:
        if token in indicator_name:
            return code, name, level, "market_region"
    return "NATIONAL", "全国", "country", "market_region"


def product_family(indicator_name: str) -> str:
    if "柴油" in indicator_name:
        return "DIESEL"
    if "汽油" in indicator_name:
        return "GASOLINE_92" if "92#" in indicator_name or "汽油" in indicator_name else "GASOLINE"
    if "原油" in indicator_name:
        return "CRUDE"
    return "REFINED_OIL"


def build_series_columns(path: Path, sheet_name: str, raw: pd.DataFrame) -> tuple[list[SeriesColumn], int]:
    indicator_row = find_meta_row(raw, "指标名称")
    if indicator_row is None:
        return [], 0
    unit_row = find_meta_row(raw, "单位")
    source_row = find_meta_row(raw, "数据来源")
    code_row = find_meta_row(raw, "指标编码")
    freq_row = find_meta_row(raw, "频度")
    data_start = max(idx for idx in [indicator_row, unit_row, source_row, code_row, freq_row] if idx is not None) + 1

    columns: list[SeriesColumn] = []
    for col_idx in range(1, raw.shape[1]):
        indicator_name = raw.iat[indicator_row, col_idx]
        if pd.isna(indicator_name) or not str(indicator_name).strip():
            continue
        indicator_name = str(indicator_name).strip()
        unit = None if unit_row is None or pd.isna(raw.iat[unit_row, col_idx]) else str(raw.iat[unit_row, col_idx]).strip()
        source_name = None if source_row is None or pd.isna(raw.iat[source_row, col_idx]) else str(raw.iat[source_row, col_idx]).strip()
        source_indicator_code = None if code_row is None or pd.isna(raw.iat[code_row, col_idx]) else str(raw.iat[code_row, col_idx]).strip()
        freq_hint = None if freq_row is None or pd.isna(raw.iat[freq_row, col_idx]) else str(raw.iat[freq_row, col_idx]).strip()

        mapped = CORE_INDICATOR_BY_NAME.get(indicator_name)
        if mapped:
            indicator_code, indicator_display, entity_code, entity_name, region_level, product = mapped
        else:
            entity_code, entity_name, region_level, _entity_type = infer_entity(indicator_name)
            product = product_family(indicator_name)
            indicator_code = fallback_indicator_code(source_indicator_code, indicator_name)
            indicator_display = indicator_name

        columns.append(
            SeriesColumn(
                file_name=path.name,
                sheet_name=sheet_name,
                column_index=col_idx,
                indicator_name=indicator_display,
                unit=unit,
                source_name=source_name,
                source_indicator_code=source_indicator_code,
                freq=infer_freq(indicator_name, freq_hint),
                indicator_code=indicator_code,
                entity_code=entity_code,
                entity_name=entity_name,
                region_level=region_level,
                product_family=product,
            )
        )
    return columns, data_start


def extract_series(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    indicator_rows: dict[str, dict[str, Any]] = {}
    data_rows: list[dict[str, Any]] = []
    raw_payloads: list[dict[str, Any]] = []
    sheet_summaries: list[dict[str, Any]] = []

    for file_name in SOURCE_FILES:
        path = root / file_name
        if not path.exists():
            continue
        excel = pd.ExcelFile(path)
        for sheet_name in excel.sheet_names:
            raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
            series_columns, data_start = build_series_columns(path, sheet_name, raw)
            if not series_columns:
                continue
            rows_before = len(data_rows)
            for series in series_columns:
                indicator_rows.setdefault(
                    series.indicator_code,
                    {
                        "indicator_code": series.indicator_code,
                        "indicator_name": series.indicator_name,
                        "category": "refined_oil",
                        "sub_category": "zhonglu_excel",
                        "unit": series.unit or "",
                        "freq": series.freq,
                        "value_type": "number",
                        "fill_policy_default": "latest_available",
                        "description": f"中鲁目录Excel归档导入；原指标编码={series.source_indicator_code or ''}",
                        "entity_code": series.entity_code,
                        "entity_name": series.entity_name,
                        "entity_type": "market_region" if series.region_level in {"country", "macro_region", "province"} else "refinery_group",
                        "region_level": series.region_level,
                        "product_family": series.product_family,
                    },
                )
            for row_idx in range(data_start, raw.shape[0]):
                observation_date = parse_date(raw.iat[row_idx, 0])
                if observation_date is None:
                    continue
                for series in series_columns:
                    value = raw.iat[row_idx, series.column_index]
                    if not is_number(value):
                        continue
                    data_rows.append(
                        {
                            "indicator_code": series.indicator_code,
                            "entity_code": series.entity_code,
                            "observation_date": observation_date,
                            "value_num": float(value),
                            "unit": series.unit or "",
                            "freq": series.freq,
                            "source_record_id": f"{SOURCE_CODE}:{path.name}:{sheet_name}:{series.indicator_code}:{observation_date.isoformat()}",
                            "file_name": path.name,
                            "sheet_name": sheet_name,
                            "source_indicator_code": series.source_indicator_code,
                        }
                    )
            raw_payloads.append(
                {
                    "file_name": path.name,
                    "sheet_name": sheet_name,
                    "indicator_count": len(series_columns),
                    "data_start_row": data_start + 1,
                }
            )
            sheet_summaries.append(
                {
                    "file_name": path.name,
                    "sheet_name": sheet_name,
                    "indicator_count": len(series_columns),
                    "rows_saved_candidate": len(data_rows) - rows_before,
                }
            )
    summary = {
        "root": str(root),
        "source_code": SOURCE_CODE,
        "indicator_count": len(indicator_rows),
        "timeseries_row_count": len(data_rows),
        "sheets": sheet_summaries,
        "raw_payloads": raw_payloads,
    }
    return list(indicator_rows.values()), data_rows, summary


def upsert_timeseries(repository: PostgresSnapshotRepository, indicator_rows: list[dict[str, Any]], data_rows: list[dict[str, Any]], summary: dict[str, Any]) -> int:
    if not repository.engine or not data_rows:
        return 0
    now = datetime.now(timezone.utc)
    with repository.engine.begin() as connection:
        source_id = repository._ensure_source_ids(connection, {SOURCE_CODE})[SOURCE_CODE]
        repository._ensure_indicators(connection, indicator_rows)
        repository._ensure_entities(connection, indicator_rows)
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
                "source_record_id": f"{SOURCE_CODE}:inventory:{sha256(json.dumps(summary, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:16]}",
                "topic": "zhonglu_excel_archive_inventory",
                "source_event_time": now,
                "payload": json.dumps(summary, ensure_ascii=False, default=str),
                "payload_hash": payload_hash(summary),
                "dt": date.today(),
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
        ts_rows = []
        for row in data_rows:
            indicator_id = indicator_id_map.get(row["indicator_code"])
            entity_id = entity_id_map.get(row["entity_code"])
            if not indicator_id or not entity_id:
                continue
            observation_time = datetime.combine(row["observation_date"], time(0, 0))
            ts_rows.append(
                {
                    "indicator_id": indicator_id,
                    "entity_id": entity_id,
                    "observation_time": observation_time,
                    "publish_time": now,
                    "freq": row["freq"],
                    "value_num": row["value_num"],
                    "value_text": None,
                    "unit": row["unit"],
                    "currency": "CNY" if row["unit"] in {"元/吨", "元"} else None,
                    "source_id": source_id,
                    "source_record_id": row["source_record_id"],
                    "is_final": True,
                    "revision_no": 1,
                    "quality_flag": "ok",
                    "effective_from": now,
                    "effective_to": None,
                    "dt": row["observation_date"],
                }
            )
        saved = 0
        chunk_size = 5000
        statement = text(
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
        )
        for start in range(0, len(ts_rows), chunk_size):
            result = connection.execute(statement, ts_rows[start : start + chunk_size])
            saved += int(result.rowcount or 0)
        return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Zhonglu refined-oil Excel archive into PostgreSQL.")
    parser.add_argument("--root", default=str(ZHONGLU_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-output", default="artifacts/zhonglu_excel_import_summary.json")
    args = parser.parse_args()

    root = Path(args.root)
    indicator_rows, data_rows, summary = extract_series(root)
    core_rows = [row for row in data_rows if row["indicator_code"] in {item[0] for item in CORE_INDICATOR_BY_NAME.values()}]
    summary["core_timeseries_row_count"] = len(core_rows)
    summary["core_indicator_codes"] = sorted({row["indicator_code"] for row in core_rows})
    summary["dry_run"] = bool(args.dry_run)

    if not args.dry_run:
        settings = get_settings()
        repository = PostgresSnapshotRepository(settings.database)
        repository.ensure_schema()
        summary["timeseries_saved"] = upsert_timeseries(repository, indicator_rows, data_rows, summary)

    out = ROOT / args.summary_output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
