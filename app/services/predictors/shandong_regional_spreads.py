from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from app.clients.llm_client import LlmClient
from app.models.common import AgentClaim, PredictionResult
from app.services.agent_control import AgentControlService
from app.services.agents.llm_agents import build_llm_agent_claims
from app.services.market_dataset import MarketDatasetService, PredictionContext
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository
from app.services.predictors.advice_engine import build_driver_summary, build_spread_advice
from app.services.predictors.confidence_engine import build_reliability_score
from app.services.predictors.horizons import DEFAULT_HORIZONS, HorizonConfig, resolve_horizon_config
from app.services.predictors.llm_narrative import enrich_prediction_narrative


REGIONAL_FREIGHT_ESTIMATES = {
    "EAST_CHINA": 55.0,
    "NORTH_CHINA": 45.0,
    "SOUTH_CHINA": 95.0,
    "CENTRAL_CHINA": 75.0,
    "NORTHWEST": 110.0,
    "SOUTHWEST": 120.0,
    "NORTHEAST": 95.0,
}


def _zh(text: str) -> str:
    try:
        return text.encode("ascii").decode("unicode_escape")
    except UnicodeEncodeError:
        return text


REGIONAL_FREIGHT_COMPONENT_CONFIGS: list[dict[str, Any]] = [
    {"region_code": "EAST_CHINA", "region_name": _zh("\u534e\u4e1c"), "component_key": "EAST_CHINA_ZHOUSHAN_SHIP", "short_name": _zh("\u6d59\u6c5f\u77f3\u5316"), "route_name": _zh("\u6d59\u6c5f\u7701\u821f\u5c71\u5e02(\u8239\u8fd0\u8d39)"), "freight_value": 100.0},
    {"region_code": "NORTH_CHINA", "region_name": _zh("\u534e\u5317"), "component_key": "NORTH_CHINA_CANGZHOU_TRUCK", "short_name": _zh("\u6cb3\u5317\u946b\u6d77"), "route_name": _zh("\u6cb3\u5317\u7701\u6ca7\u5dde\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 70.0},
    {"region_code": "NORTH_CHINA", "region_name": _zh("\u534e\u5317"), "component_key": "NORTH_CHINA_PUYANG_TRUCK", "short_name": _zh("\u4e30\u5229\u77f3\u5316"), "route_name": _zh("\u6cb3\u5357\u7701\u6fee\u9633\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 130.0},
    {"region_code": "CENTRAL_CHINA", "region_name": _zh("\u534e\u4e2d"), "component_key": "CENTRAL_CHINA_QIANJIANG_TRUCK", "short_name": _zh("\u91d1\u6fb3\u79d1\u6280"), "route_name": _zh("\u6e56\u5317\u7701\u6f5c\u6c5f\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 260.0},
    {"region_code": "CENTRAL_CHINA", "region_name": _zh("\u534e\u4e2d"), "component_key": "CENTRAL_CHINA_NANCHANG_TRUCK", "short_name": _zh("\u5357\u660c\u8d38\u6613"), "route_name": _zh("\u6c5f\u897f\u7701\u5357\u660c\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 300.0},
    {"region_code": "CENTRAL_CHINA", "region_name": _zh("\u534e\u4e2d"), "component_key": "CENTRAL_CHINA_HEFEI_TRUCK", "short_name": _zh("\u5408\u80a5\u8d38\u6613"), "route_name": _zh("\u5b89\u5fbd\u7701\u5408\u80a5\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 240.0},
    {"region_code": "SOUTH_CHINA", "region_name": _zh("\u534e\u5357"), "component_key": "SOUTH_CHINA_HUIZHOU_SHIP", "short_name": _zh("\u60e0\u5dde\u6d77\u6cb9"), "route_name": _zh("\u5e7f\u4e1c\u7701\u60e0\u5dde\u5e02(\u8239\u8fd0\u8d39)"), "freight_value": 120.0},
    {"region_code": "NORTHWEST", "region_name": _zh("\u897f\u5317"), "component_key": "NORTHWEST_YANAN_TRUCK", "short_name": _zh("\u5ef6\u5b89\u70bc\u5382"), "route_name": _zh("\u9655\u897f\u7701\u5ef6\u5b89\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 260.0},
    {"region_code": "NORTHWEST", "region_name": _zh("\u897f\u5317"), "component_key": "NORTHWEST_WUZHONG_TRUCK", "short_name": _zh("\u5b81\u9c81\u77f3\u5316"), "route_name": _zh("\u5b81\u590f\u5434\u5fe0\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 260.0},
    {"region_code": "SOUTHWEST", "region_name": _zh("\u897f\u5357"), "component_key": "SOUTHWEST_SUINING_TRUCK", "short_name": _zh("\u76db\u9a6c\u5316\u5de5"), "route_name": _zh("\u56db\u5ddd\u7701\u9042\u5b81\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 420.0},
    {"region_code": "NORTHEAST", "region_name": _zh("\u4e1c\u5317"), "component_key": "NORTHEAST_PANJIN_TRUCK", "short_name": _zh("\u9526\u57ce\u77f3\u5316"), "route_name": _zh("\u8fbd\u5b81\u7701\u76d8\u9526\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 180.0},
    {"region_code": "NORTHEAST", "region_name": _zh("\u4e1c\u5317"), "component_key": "NORTHEAST_SONGYUAN_TRUCK", "short_name": _zh("\u677e\u539f\u77f3\u5316"), "route_name": _zh("\u5409\u6797\u7701\u677e\u539f\u5e02(\u8f66\u8fd0\u8d39)"), "freight_value": 200.0},
]

REGIONAL_STATE_MIN_SAMPLE = 12
REGIONAL_RULE_CORRECTION_WEIGHT = 0.35
REGIONAL_REQUIRED_MARGIN = 40.0
REGIONAL_RISK_BUFFER = 40.0

FREIGHT_INPUT_WORKBOOK = Path(__file__).resolve().parents[3] / "运费录入.xlsx"

REGIONAL_FREIGHT_EXCEL_LABELS = {
    "山东-华东": "EAST_CHINA",
    "山东-华北": "NORTH_CHINA",
    "山东-华南": "SOUTH_CHINA",
    "山东-华中": "CENTRAL_CHINA",
    "山东-西北": "NORTHWEST",
    "山东-西南": "SOUTHWEST",
    "山东-东北": "NORTHEAST",
}



class RegionalFreightWorkbook:
    def __init__(self, path: Path = FREIGHT_INPUT_WORKBOOK) -> None:
        self.path = path

    def available(self) -> bool:
        return self.path.exists()

    def load_settings(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        workbook = load_workbook(self.path, data_only=False)
        value_workbook = load_workbook(self.path, data_only=True)
        sheet = workbook["Sheet1"]
        value_sheet = value_workbook["Sheet1"]
        value_row = self._latest_value_row(sheet)
        if value_row is None:
            return {}
        as_of_cell = sheet.cell(value_row, 1).value
        as_of_date = as_of_cell.date().isoformat() if isinstance(as_of_cell, datetime) else str(as_of_cell or "")
        grouped: dict[str, dict[str, Any]] = {}
        pending_components: list[dict[str, Any]] = []
        for column in range(2, sheet.max_column + 1):
            row1 = str(value_sheet.cell(1, column).value or sheet.cell(1, column).value or "").strip()
            row2 = str(value_sheet.cell(2, column).value or sheet.cell(2, column).value or row1).strip()
            is_aggregate = bool(sheet.cell(1, column).font and sheet.cell(1, column).font.bold) or row2 in REGIONAL_FREIGHT_EXCEL_LABELS
            value = self._float_or_none(value_sheet.cell(value_row, column).value)
            if is_aggregate:
                region_code = REGIONAL_FREIGHT_EXCEL_LABELS.get(row2) or REGIONAL_FREIGHT_EXCEL_LABELS.get(row1)
                if region_code:
                    component_values = [item["freight_value"] for item in pending_components if item.get("freight_value") is not None]
                    calculated = round(sum(component_values) / len(component_values), 4) if component_values else value
                    grouped[region_code] = {
                        "region_code": region_code,
                        "region_name": row2.replace("山东-", "") or row1.replace("山东-", ""),
                        "freight_value": calculated if calculated is not None else 0.0,
                        "workbook_value": value,
                        "unit": "元/吨",
                        "source_type": "excel_aggregate",
                        "updated_by": "运费录入.xlsx",
                        "updated_at": self._file_mtime(),
                        "as_of_date": as_of_date,
                        "excel_column": column,
                        "excel_label": row2 or row1,
                        "components": pending_components,
                        "calculation": self._calculation_text(pending_components, calculated),
                    }
                pending_components = []
            else:
                pending_components.append(
                    {
                        "component_key": self._column_letter(column),
                        "short_name": row1,
                        "route_name": row2,
                        "freight_value": value,
                        "unit": "元/吨",
                        "excel_column": column,
                    }
                )
        return grouped

    def update_component(self, *, component_key: str, freight_value: float) -> dict[str, Any]:
        if not self.path.exists():
            raise RuntimeError(f"未找到运费录入文件：{self.path}")
        workbook = load_workbook(self.path, data_only=False)
        sheet = workbook["Sheet1"]
        value_row = self._latest_value_row(sheet)
        if value_row is None:
            value_row = 3
            sheet.cell(value_row, 1).value = datetime.now().date()
        target_column = self._component_column(sheet, component_key)
        if target_column is None:
            raise ValueError(f"未找到运费录入项：{component_key}")
        sheet.cell(value_row, target_column).value = float(freight_value)
        self._recalculate_aggregates(sheet, value_row)
        workbook.save(self.path)
        return self.load_settings()

    def _recalculate_aggregates(self, sheet: Any, value_row: int) -> None:
        pending_columns: list[int] = []
        for column in range(2, sheet.max_column + 1):
            row1 = str(sheet.cell(1, column).value or "").strip()
            row2 = str(sheet.cell(2, column).value or row1).strip()
            is_aggregate = bool(sheet.cell(1, column).font and sheet.cell(1, column).font.bold) or row2 in REGIONAL_FREIGHT_EXCEL_LABELS
            if is_aggregate:
                values = [self._float_or_none(sheet.cell(value_row, col).value) for col in pending_columns]
                values = [value for value in values if value is not None]
                if values:
                    sheet.cell(value_row, column).value = sum(values) / len(values)
                pending_columns = []
            else:
                pending_columns.append(column)

    def _component_column(self, sheet: Any, component_key: str) -> int | None:
        normalized = str(component_key or "").strip()
        if normalized.isalpha():
            column = self._letter_to_column(normalized)
            if 1 <= column <= sheet.max_column:
                return column
        for column in range(2, sheet.max_column + 1):
            labels = {
                str(sheet.cell(1, column).value or "").strip(),
                str(sheet.cell(2, column).value or "").strip(),
                self._column_letter(column),
            }
            is_aggregate = bool(sheet.cell(1, column).font and sheet.cell(1, column).font.bold) or str(sheet.cell(2, column).value or "").strip() in REGIONAL_FREIGHT_EXCEL_LABELS
            if not is_aggregate and normalized in labels:
                return column
        return None

    def _latest_value_row(self, sheet: Any) -> int | None:
        for row in range(sheet.max_row, 2, -1):
            if any(sheet.cell(row, col).value is not None for col in range(1, sheet.max_column + 1)):
                return row
        return None

    def _file_mtime(self) -> datetime | None:
        try:
            return datetime.fromtimestamp(self.path.stat().st_mtime)
        except OSError:
            return None

    def _calculation_text(self, components: list[dict[str, Any]], value: float | None) -> str:
        labels = [item.get("route_name") or item.get("short_name") for item in components]
        labels = [label for label in labels if label]
        if not labels:
            return "未配置明细线路，使用表内区域运费。"
        result = round(float(value), 2) if value is not None else "-"
        return f"({'+'.join(labels)}) ÷ {len(labels)} = {result} 元/吨"
    def _float_or_none(self, value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None

    def _column_letter(self, column: int) -> str:
        letters = ""
        while column:
            column, remainder = divmod(column - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    def _letter_to_column(self, value: str) -> int:
        column = 0
        for char in value.upper():
            if not ("A" <= char <= "Z"):
                return -1
            column = column * 26 + (ord(char) - 64)
        return column


class RegionalSpreadStructureAgent:
    name = "regional_spread_structure_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        current_spread = self._num(row.get("target_region_spread"))
        change_1d = self._num(row.get("target_region_spread_change_1d"))
        change_3d = self._num(row.get("target_region_spread_change_3d"))
        score = 0.0
        evidence: list[str] = []

        if change_3d is not None:
            if change_3d >= 1.5:
                score += 2.0
                evidence.append(f"区域价差3日走扩{change_3d:.1f}元/吨，短线动量仍偏强")
            elif change_3d <= -1.5:
                score -= 2.0
                evidence.append(f"区域价差3日收窄{abs(change_3d):.1f}元/吨，短线动量偏弱")
            elif change_3d >= 0.5:
                score += 1.0
                evidence.append(f"区域价差3日小幅走扩{change_3d:.1f}元/吨")
            elif change_3d <= -0.5:
                score -= 1.0
                evidence.append(f"区域价差3日小幅收窄{abs(change_3d):.1f}元/吨")

        if current_spread is not None:
            if current_spread >= 150:
                score -= 1.5
                evidence.append(f"当前价差{current_spread:.1f}元/吨处于高位，存在回落压力")
            elif current_spread <= 30:
                score += 1.5
                evidence.append(f"当前价差{current_spread:.1f}元/吨处于低位，存在修复空间")

        if change_1d is not None and abs(change_1d) >= 0.5:
            score += 1.0 if change_1d > 0 else -1.0
            evidence.append(f"区域价差单日变化{change_1d:.1f}元/吨")

        return self._claim(score, evidence or ["区域价差结构未出现明显单边信号"])

    def _claim(self, score: float, evidence: list[str]) -> AgentClaim:
        direction = "up" if score > 1 else "down" if score < -1 else "flat"
        return AgentClaim(
            agent_name=self.name,
            direction=direction,
            confidence_label="medium" if abs(score) >= 4 else "low",
            confidence_score=min(0.85, 0.45 + abs(score) / 40),
            summary=f"价差结构贡献{score:.1f}元/吨",
            evidence=evidence,
            numeric_signals={"score": round(score, 4)},
            structured_payload={"factor": "spread_structure"},
        )

    def _num(self, value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None


class RegionalFreightNetbackAgent:
    name = "regional_freight_netback_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        spread = self._num(row.get("target_region_spread"))
        freight = self._num(extra.get("freight_estimate"))
        score = 0.0
        evidence: list[str] = []
        if spread is None or freight is None:
            return self._claim(0.0, ["运费或区域价差缺失，净回款不参与打分"])

        netback_spread = spread - freight
        if netback_spread >= 80:
            score -= 6.0
            evidence.append(f"净回款价差{netback_spread:.1f}元/吨，套利窗口过宽，后续有收敛压力")
        elif netback_spread >= 40:
            score -= 3.0
            evidence.append(f"净回款价差{netback_spread:.1f}元/吨，外流利润较好但需防价差回落")
        elif netback_spread >= 0:
            score -= 1.0
            evidence.append(f"净回款价差{netback_spread:.1f}元/吨，价差维持正区间但收敛压力仍在")
        elif netback_spread <= -60:
            score -= 1.0
            evidence.append(f"净回款价差{netback_spread:.1f}元/吨，目标区域显著弱于山东")
        elif netback_spread <= -20:
            score -= 0.5
            evidence.append(f"净回款价差{netback_spread:.1f}元/吨，目标区域偏弱")
        else:
            evidence.append(f"净回款价差{netback_spread:.1f}元/吨，运费后价差处于中性区间")

        return self._claim(score, evidence)

    def _claim(self, score: float, evidence: list[str]) -> AgentClaim:
        direction = "up" if score > 1 else "down" if score < -1 else "flat"
        return AgentClaim(
            agent_name=self.name,
            direction=direction,
            confidence_label="medium" if abs(score) >= 4 else "low",
            confidence_score=min(0.85, 0.45 + abs(score) / 40),
            summary=f"运费净回款贡献{score:.1f}元/吨",
            evidence=evidence,
            numeric_signals={"score": round(score, 4)},
            structured_payload={"factor": "freight_netback"},
        )

    def _num(self, value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None


class RegionalInventoryPressureAgent:
    name = "regional_inventory_pressure_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        snapshot = extra.get("regional_inventory") or {}
        if not snapshot.get("available"):
            return self._claim(0.0, [str(snapshot.get("reason") or "区域库存数据缺失，不参与打分")], "low")

        ratio = snapshot.get("ratio_to_median")
        wow_change = snapshot.get("wow_change")
        latest_date = snapshot.get("latest_date")
        subject = snapshot.get("subject") or "贸易商"
        score = 0.0
        evidence: list[str] = []

        if ratio is not None:
            if ratio >= 1.25:
                score -= 4.0
                evidence.append(f"{subject}库存较区域中位数高{(ratio - 1) * 100:.1f}%，目标区域承压")
            elif ratio >= 1.12:
                score -= 2.0
                evidence.append(f"{subject}库存较区域中位数高{(ratio - 1) * 100:.1f}%，偏弱")
            elif ratio <= 0.75:
                score += 4.0
                evidence.append(f"{subject}库存较区域中位数低{(1 - ratio) * 100:.1f}%，目标区域抗跌")
            elif ratio <= 0.88:
                score += 2.0
                evidence.append(f"{subject}库存较区域中位数低{(1 - ratio) * 100:.1f}%，偏强")

        if wow_change is not None:
            if wow_change >= 5:
                score -= 2.0
                evidence.append(f"{subject}库存环比增加{wow_change:.2f}万吨")
            elif wow_change <= -5:
                score += 2.0
                evidence.append(f"{subject}库存环比下降{abs(wow_change):.2f}万吨")

        if not evidence:
            evidence.append(f"{latest_date}区域库存处于中性位置")
        return self._claim(score, evidence, "medium" if abs(score) >= 5 else "low")

    def _claim(self, score: float, evidence: list[str], confidence_label: str) -> AgentClaim:
        direction = "up" if score > 1 else "down" if score < -1 else "flat"
        return AgentClaim(
            agent_name=self.name,
            direction=direction,
            confidence_label=confidence_label,
            confidence_score=min(0.9, 0.45 + abs(score) / 35),
            summary=f"区域库存压力贡献{score:.1f}元/吨",
            evidence=evidence,
            numeric_signals={"score": round(score, 4)},
            structured_payload={"factor": "regional_inventory_pressure"},
        )


@dataclass(frozen=True)
class RegionalSpreadConfig:
    region_code: str
    region_name: str
    price_column: str
    spread_column: str

    @property
    def spread_change_1d_column(self) -> str:
        return f"{self.spread_column}_change_1d"

    @property
    def spread_change_3d_column(self) -> str:
        return f"{self.spread_column}_change_3d"

    @property
    def entity_code(self) -> str:
        return f"{self.region_code}_VS_SD_GAS92_SPREAD"

    @property
    def output_region_code(self) -> str:
        return f"{self.region_code}_VS_SHANDONG"


REGIONAL_SPREAD_CONFIGS: dict[str, RegionalSpreadConfig] = {
    "EAST_CHINA": RegionalSpreadConfig("EAST_CHINA", "华东", "east_china_gas92_market", "sd_vs_east_china_spread"),
    "NORTH_CHINA": RegionalSpreadConfig("NORTH_CHINA", "华北", "north_china_gas92_market", "sd_vs_north_china_spread"),
    "SOUTH_CHINA": RegionalSpreadConfig("SOUTH_CHINA", "华南", "south_china_gas92_market", "sd_vs_south_china_spread"),
    "CENTRAL_CHINA": RegionalSpreadConfig(
        "CENTRAL_CHINA", "华中", "central_china_gas92_market", "sd_vs_central_china_spread"
    ),
    "NORTHWEST": RegionalSpreadConfig("NORTHWEST", "西北", "northwest_gas92_market", "sd_vs_northwest_spread"),
    "SOUTHWEST": RegionalSpreadConfig("SOUTHWEST", "西南", "southwest_gas92_market", "sd_vs_southwest_spread"),
    "NORTHEAST": RegionalSpreadConfig("NORTHEAST", "东北", "northeast_gas92_market", "sd_vs_northeast_spread"),
}


def attach_regional_price_forecasts(
    regional_predictions: list[PredictionResult],
    outright_predictions: list[PredictionResult],
) -> list[PredictionResult]:
    outright_by_horizon = {item.horizon: item for item in outright_predictions}
    fallback_outright = outright_predictions[0] if outright_predictions else None
    for regional in regional_predictions:
        outright = outright_by_horizon.get(regional.horizon) or fallback_outright
        if outright is None:
            continue
        raw_context = dict(regional.raw_context or {})
        predicted_spread = _float_or_none(raw_context.get("predicted_region_minus_shandong_spread"))
        if predicted_spread is None:
            predicted_spread = float(regional.point_value)
        predicted_shandong_price = float(outright.point_value)
        business_prediction = (outright.raw_context or {}).get("business_scorecard_prediction") or {}
        business_shandong_price = _float_or_none(business_prediction.get("point_value"))
        predicted_region_price = predicted_shandong_price + predicted_spread
        actual_region_minus_shandong = _float_or_none(raw_context.get("current_spread"))
        range_lower = float(regional.range_lower)
        range_upper = float(regional.range_upper)
        raw_context.update(
            {
                "predicted_shandong_price": round(predicted_shandong_price, 2),
                "predicted_region_price": round(predicted_region_price, 2),
                "predicted_region_price_range_lower": round(predicted_shandong_price + range_lower, 2),
                "predicted_region_price_range_upper": round(predicted_shandong_price + range_upper, 2),
                "predicted_region_minus_shandong_spread": round(predicted_spread, 2),
                "predicted_region_minus_shandong_spread_range_lower": round(range_lower, 2),
                "predicted_region_minus_shandong_spread_range_upper": round(range_upper, 2),
                "actual_region_minus_shandong_spread": actual_region_minus_shandong,
                "predicted_shandong_minus_region_spread": round(-predicted_spread, 2),
                "predicted_shandong_minus_region_spread_range_lower": round(-range_upper, 2),
                "predicted_shandong_minus_region_spread_range_upper": round(-range_lower, 2),
                "actual_shandong_minus_region_spread": round(-actual_region_minus_shandong, 2)
                if actual_region_minus_shandong is not None
                else None,
                "regional_price_prediction_mode": "shandong_forecast_plus_regional_spread",
                "regional_price_prediction_formula": "预测区域单价=山东92#预测价+(目标区域预测价差)，目标区域预测价差=目标区域价格-山东价格",
                "predicted_spread_formula": "预测展示价差=山东92#预测价-预测区域单价",
                "actual_spread_formula": "真实展示价差=当前山东92#价格-当前目标区域92#价格",
                "shandong_prediction_run_id": outright.run_id,
            }
        )
        composite_variant = _regional_variant_from_legacy(
            raw_context.get("regional_composite_prediction"),
            model_name="区域智能体综合预测",
            prediction_type="regional_composite",
            direction_label=regional.direction_label,
            point_value=regional.point_value,
            range_lower=regional.range_lower,
            range_upper=regional.range_upper,
            predicted_delta=raw_context.get("predicted_delta"),
            method=raw_context.get("prediction_method"),
            basis="区域状态表中位数叠加规则智能体修正，并受经营上下边界约束。",
        )
        raw_context["regional_composite_prediction"] = _attach_regional_variant_prices(
            composite_variant,
            predicted_shandong_price=predicted_shandong_price,
            shandong_prediction_source="智能体综合预测",
        )
        baseline_variant = raw_context.get("regional_baseline_prediction")
        if isinstance(baseline_variant, dict):
            raw_context["regional_baseline_prediction"] = _attach_regional_variant_prices(
                baseline_variant,
                predicted_shandong_price=business_shandong_price or predicted_shandong_price,
                shandong_prediction_source=(
                    "山东成品油市场价预测打分模型" if business_shandong_price is not None else "智能体综合预测"
                ),
            )
        raw_context["regional_prediction_variants"] = [
            raw_context["regional_composite_prediction"],
            *(
                [raw_context["regional_baseline_prediction"]]
                if isinstance(raw_context.get("regional_baseline_prediction"), dict)
                else []
            ),
        ]
        regional.raw_context = raw_context
    return regional_predictions


def _regional_variant_from_legacy(
    variant: Any,
    *,
    model_name: str,
    prediction_type: str,
    direction_label: str,
    point_value: float,
    range_lower: float,
    range_upper: float,
    predicted_delta: Any,
    method: Any,
    basis: str,
) -> dict[str, Any]:
    if isinstance(variant, dict):
        return dict(variant)
    return {
        "model_name": model_name,
        "prediction_type": prediction_type,
        "direction_label": direction_label,
        "predicted_delta": _float_or_none(predicted_delta),
        "predicted_region_minus_shandong_spread": round(float(point_value), 2),
        "predicted_region_minus_shandong_spread_range_lower": round(float(range_lower), 2),
        "predicted_region_minus_shandong_spread_range_upper": round(float(range_upper), 2),
        "method": method,
        "basis": basis,
    }


def _attach_regional_variant_prices(
    variant: dict[str, Any],
    *,
    predicted_shandong_price: float,
    shandong_prediction_source: str,
) -> dict[str, Any]:
    result = dict(variant)
    spread = _float_or_none(
        result.get("predicted_region_minus_shandong_spread")
        if result.get("predicted_region_minus_shandong_spread") is not None
        else result.get("point_value")
    )
    if spread is None:
        return result
    range_lower = _float_or_none(result.get("predicted_region_minus_shandong_spread_range_lower"))
    range_upper = _float_or_none(result.get("predicted_region_minus_shandong_spread_range_upper"))
    if range_lower is None:
        range_lower = spread
    if range_upper is None:
        range_upper = spread
    result.update(
        {
            "predicted_shandong_price": round(float(predicted_shandong_price), 2),
            "shandong_prediction_source": shandong_prediction_source,
            "predicted_region_price": round(float(predicted_shandong_price) + spread, 2),
            "predicted_region_price_range_lower": round(float(predicted_shandong_price) + range_lower, 2),
            "predicted_region_price_range_upper": round(float(predicted_shandong_price) + range_upper, 2),
            "predicted_region_minus_shandong_spread": round(spread, 2),
            "predicted_region_minus_shandong_spread_range_lower": round(range_lower, 2),
            "predicted_region_minus_shandong_spread_range_upper": round(range_upper, 2),
            "predicted_shandong_minus_region_spread": round(-spread, 2),
            "predicted_shandong_minus_region_spread_range_lower": round(-range_upper, 2),
            "predicted_shandong_minus_region_spread_range_upper": round(-range_lower, 2),
            "regional_price_prediction_formula": "预测区域单价=对应山东92#预测价+区域预测价差",
            "predicted_spread_formula": "预测展示价差=山东92#预测价-预测区域单价",
        }
    )
    return result


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None



def build_freight_settings_from_components(snapshot_repository: PostgresSnapshotRepository | None) -> list[dict[str, Any]]:
    if snapshot_repository is not None:
        components = snapshot_repository.list_freight_components(REGIONAL_FREIGHT_COMPONENT_CONFIGS)
    else:
        components = [
            dict(item, unit="元/吨", display_order=index, updated_by=None, updated_at=None)
            for index, item in enumerate(REGIONAL_FREIGHT_COMPONENT_CONFIGS, start=1)
        ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for component in components:
        grouped.setdefault(component["region_code"], []).append(component)
    items: list[dict[str, Any]] = []
    for config in REGIONAL_SPREAD_CONFIGS.values():
        region_components = sorted(grouped.get(config.region_code, []), key=lambda item: item.get("display_order") or 0)
        if not region_components:
            items.append(
                {
                    "region_code": config.region_code,
                    "region_name": config.region_name,
                    "freight_value": REGIONAL_FREIGHT_ESTIMATES.get(config.region_code, 80.0),
                    "unit": "元/吨",
                    "source_type": "default",
                    "updated_by": None,
                    "updated_at": None,
                    "components": [],
                    "calculation": "未配置运费明细，使用默认估算。",
                }
            )
            continue
        values = [float(item["freight_value"]) for item in region_components]
        average = round(sum(values) / len(values), 4)
        latest_updated_at = max((item.get("updated_at") for item in region_components if item.get("updated_at")), default=None)
        labels = [item.get("route_name") or item.get("short_name") or item.get("component_key") for item in region_components]
        items.append(
            {
                "region_code": config.region_code,
                "region_name": config.region_name,
                "freight_value": average,
                "unit": "元/吨",
                "source_type": "database_components",
                "updated_by": next((item.get("updated_by") for item in region_components if item.get("updated_by")), None),
                "updated_at": latest_updated_at,
                "components": [
                    {
                        "component_key": item["component_key"],
                        "short_name": item.get("short_name"),
                        "route_name": item.get("route_name"),
                        "freight_value": float(item["freight_value"]),
                        "unit": "元/吨",
                        "excel_column": None,
                    }
                    for item in region_components
                ],
                "calculation": f"({'+'.join(labels)}) ÷ {len(labels)} = {round(average, 2)} 元/吨",
            }
        )
    return items

class ShandongRegionalSpreadPredictor:
    def __init__(
        self,
        dataset_service: MarketDatasetService,
        llm_client: LlmClient,
        agent_control_service: AgentControlService,
        snapshot_repository: PostgresSnapshotRepository | None = None,
    ) -> None:
        self.dataset_service = dataset_service
        self.llm_client = llm_client
        self.agent_control_service = agent_control_service
        self.snapshot_repository = snapshot_repository
        self.scope_key = "regional_spread"
        self._regional_inventory_cache: dict[date, list[dict[str, Any]]] = {}
        self._regional_inventory_context_cache: dict[tuple[str, date], dict[str, Any]] = {}
        self.agents = [
            RegionalSpreadStructureAgent(),
            RegionalFreightNetbackAgent(),
            RegionalInventoryPressureAgent(),
        ]

    def list_regions(self) -> list[dict[str, str]]:
        return [{"region_code": item.region_code, "region_name": item.region_name} for item in REGIONAL_SPREAD_CONFIGS.values()]

    def run_prediction(
        self,
        region_code: str,
        as_of_date: date | None = None,
        horizon: str = "D1",
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
    ) -> PredictionResult:
        as_of_date = as_of_date or date.today()
        context = self.dataset_service.build_context(as_of_date)
        return self.run_prediction_from_context(
            context=context,
            region_code=region_code,
            as_of_date=as_of_date,
            horizon=horizon,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
        )

    def run_prediction_from_context(
        self,
        context: PredictionContext,
        region_code: str,
        as_of_date: date,
        horizon: str = "D1",
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
    ) -> PredictionResult:
        config = self._resolve_config(region_code)
        horizon_config = resolve_horizon_config(horizon)
        return self._predict_from_context(
            context=context,
            config=config,
            horizon_config=horizon_config,
            as_of_date=as_of_date,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
            context_metadata=context.metadata,
        )

    def run_all_predictions(
        self,
        as_of_date: date | None = None,
        horizon: str = "D1",
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
        region_codes: list[str] | None = None,
    ) -> list[PredictionResult]:
        as_of_date = as_of_date or date.today()
        context = self.dataset_service.build_context(as_of_date)
        return self.run_all_predictions_from_context(
            context=context,
            as_of_date=as_of_date,
            horizon=horizon,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
            region_codes=region_codes,
        )

    def run_all_predictions_from_context(
        self,
        context: PredictionContext,
        as_of_date: date,
        horizon: str = "D1",
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
        region_codes: list[str] | None = None,
    ) -> list[PredictionResult]:
        horizon_config = resolve_horizon_config(horizon)
        configs = self._resolve_configs(region_codes)
        return [
            self._predict_from_context(
                context=context,
                config=config,
                horizon_config=horizon_config,
                as_of_date=as_of_date,
                use_llm_explainer=use_llm_explainer,
                scenario_text=scenario_text,
                enable_refined_news=enable_refined_news,
                enable_event_risk=enable_event_risk,
                context_metadata=context.metadata,
            )
            for config in configs
        ]

    def run_multi_horizon_predictions_from_context(
        self,
        context: PredictionContext,
        as_of_date: date,
        region_codes: list[str] | None = None,
        horizons: list[str] | None = None,
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
    ) -> dict[str, list[PredictionResult]]:
        selected_horizons = horizons or DEFAULT_HORIZONS
        configs = self._resolve_configs(region_codes)
        result: dict[str, list[PredictionResult]] = {}
        for horizon in selected_horizons:
            horizon_config = resolve_horizon_config(horizon)
            result[horizon] = [
                self._predict_from_context(
                    context=context,
                    config=config,
                    horizon_config=horizon_config,
                    as_of_date=as_of_date,
                    use_llm_explainer=use_llm_explainer,
                    scenario_text=scenario_text,
                    enable_refined_news=enable_refined_news,
                    enable_event_risk=enable_event_risk,
                    context_metadata=context.metadata,
                )
                for config in configs
            ]
        return result

    def _resolve_config(self, region_code: str) -> RegionalSpreadConfig:
        normalized = region_code.strip().upper()
        if normalized not in REGIONAL_SPREAD_CONFIGS:
            supported = ", ".join(sorted(REGIONAL_SPREAD_CONFIGS))
            raise ValueError(f"Unsupported region_code={region_code}. Supported: {supported}")
        return REGIONAL_SPREAD_CONFIGS[normalized]

    def _resolve_configs(self, region_codes: list[str] | None) -> list[RegionalSpreadConfig]:
        if not region_codes:
            return list(REGIONAL_SPREAD_CONFIGS.values())
        return [self._resolve_config(region_code) for region_code in region_codes]

    def list_freight_settings(self) -> list[dict[str, Any]]:
        return self._component_settings_grouped()

    def update_freight_setting(self, *, region_code: str, freight_value: float, updated_by: str | None) -> dict[str, Any]:
        config = self._resolve_config(region_code)
        components = [item for item in REGIONAL_FREIGHT_COMPONENT_CONFIGS if item["region_code"] == config.region_code]
        if not components:
            raise ValueError(f"未配置区域运费明细：{config.region_name}")
        per_component = float(freight_value)
        for component in components:
            self.update_freight_component(
                component_key=component["component_key"],
                freight_value=per_component,
                updated_by=updated_by,
            )
        return self._freight_setting_for(config)

    def update_freight_component(
        self,
        *,
        component_key: str,
        freight_value: float,
        updated_by: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.snapshot_repository is None:
            raise RuntimeError("PostgreSQL 未配置，无法保存运费明细。")
        self.snapshot_repository.upsert_freight_component(
            defaults=REGIONAL_FREIGHT_COMPONENT_CONFIGS,
            component_key=component_key,
            freight_value=freight_value,
            updated_by=updated_by,
        )
        return self.list_freight_settings()

    def _component_settings_grouped(self) -> list[dict[str, Any]]:
        return build_freight_settings_from_components(self.snapshot_repository)

    def _freight_setting_for(self, config: RegionalSpreadConfig) -> dict[str, Any]:
        settings = {item["region_code"]: item for item in self.list_freight_settings()}
        return settings.get(
            config.region_code,
            {
                "region_code": config.region_code,
                "region_name": config.region_name,
                "freight_value": REGIONAL_FREIGHT_ESTIMATES.get(config.region_code, 80.0),
                "source_type": "default",
                "updated_by": None,
                "updated_at": None,
                "components": [],
                "calculation": "未配置运费明细，使用默认估算。",
            },
        )

    def _predict_from_context(
        self,
        context: PredictionContext,
        config: RegionalSpreadConfig,
        horizon_config: HorizonConfig,
        as_of_date: date,
        use_llm_explainer: bool,
        scenario_text: str | None,
        enable_refined_news: bool,
        enable_event_risk: bool,
        context_metadata: dict[str, Any] | None,
    ) -> PredictionResult:
        feature_frame = context.feature_frame.copy()
        current_frame = feature_frame[feature_frame["date"] <= as_of_date]
        if current_frame.empty:
            raise RuntimeError(f"No feature row found for as_of_date={as_of_date}")

        current_row = self._enrich_row(current_frame.iloc[-1], config)
        current_spread = current_row.get("target_region_spread")
        counter_region_price = current_row.get("target_region_price")
        if pd.isna(current_spread) or pd.isna(counter_region_price):
            raise RuntimeError(f"Missing region price history for {config.region_name} on or before {as_of_date}.")
        freight_setting = self._freight_setting_for(config)
        freight_estimate = float(freight_setting.get("freight_value", REGIONAL_FREIGHT_ESTIMATES.get(config.region_code, 80.0)))
        regional_inventory = self._regional_inventory_context(config=config, as_of_date=as_of_date)

        claims, score_value = self._score_row(
            current_row,
            extra={
                "as_of_date": as_of_date,
                "report_payload": context.report_payload,
                "news_items": context.news_items,
                "refined_news_items": context.refined_news_items,
                "policy_items": context.policy_items,
                "scenario_text": scenario_text,
                "mode": "predict",
                "prediction_subject": "regional_spread",
                "enable_refined_news": enable_refined_news,
                "enable_event_risk": enable_event_risk,
                "target_region_code": config.region_code,
                "target_region_name": config.region_name,
                "freight_estimate": freight_estimate,
                "regional_inventory": regional_inventory,
            },
        )
        current_agent_scores = {
            claim.agent_name: float(claim.numeric_signals.get("score", 0.0))
            for claim in claims
        }

        current_spread_value = float(current_spread)
        expert_delta = self._expert_regional_delta(
            frame=feature_frame,
            config=config,
            row=current_row,
            as_of_date=as_of_date,
            freight_estimate=freight_estimate,
            regional_inventory=regional_inventory,
            horizon_config=horizon_config,
        )
        predicted_delta = expert_delta["predicted_delta"]
        point_value = current_spread_value + predicted_delta
        baseline_prediction = self._regional_baseline_prediction(
            current_spread=current_spread_value,
            rule_delta=expert_delta["rule_delta"],
            operating_bounds=expert_delta["operating_bounds"],
            regional_inventory=regional_inventory,
            horizon_config=horizon_config,
        )
        range_half_width = self._regional_expert_range_half_width(
            expert_delta=expert_delta,
            regional_inventory=regional_inventory,
            horizon_config=horizon_config,
        )
        risk_range_half_width = range_half_width
        range_basis = {
            "core_label": "经营参考区间",
            "risk_label": "专家规则风险区间",
            "historical_error_available": False,
            "reason": "区域价差不再使用历史拟合系数生成点位；区间来自周期基础半宽、因子分歧和数据缺口。",
        }
        direction_threshold = self._regional_direction_threshold(horizon_config)
        direction_label = self._direction_from_delta(predicted_delta, threshold=direction_threshold)
        probabilities = self._probabilities_from_score(score_value)
        confidence_label, confidence_score, confidence_components = build_reliability_score(
            claims=claims,
            predicted_delta=predicted_delta,
            direction_label=direction_label,
            range_half_width=range_half_width,
            direction_threshold=direction_threshold,
            calibration_rmse=range_half_width,
            sample_size=0,
            context_metadata=context_metadata,
        )
        current_netback_spread = float(counter_region_price) - float(current_row["sd_gas92_market"]) - freight_estimate
        predicted_netback_spread = point_value - freight_estimate
        freight_review_required = self._freight_review_required(freight_setting)
        trade_action = self._trade_action_from_netback_spread(
            netback_spread=predicted_netback_spread,
            freight_review_required=freight_review_required,
        )

        raw_context = {
            "current_spread": round(current_spread_value, 2),
            "spread_formula": "目标区域92#价格-山东92#价格",
            "predicted_delta": round(predicted_delta, 4),
            "score_value": round(score_value, 4),
            "current_agent_scores": current_agent_scores,
            "prediction_method": expert_delta["method"],
            "prediction_method_note": "区域价差点位由冻结状态表价差变化中位数作为主点位，叠加当日规则修正，并用经营上下边界约束；状态样本不足时降级为规则修正。",
            "expert_delta": expert_delta,
            "regional_composite_prediction": {
                "model_name": "区域智能体综合预测",
                "prediction_type": "regional_composite",
                "direction_label": direction_label,
                "score": round(score_value, 4),
                "predicted_delta": round(predicted_delta, 4),
                "predicted_region_minus_shandong_spread": round(point_value, 2),
                "predicted_region_minus_shandong_spread_range_lower": round(point_value - range_half_width, 2),
                "predicted_region_minus_shandong_spread_range_upper": round(point_value + range_half_width, 2),
                "range_half_width": round(range_half_width, 4),
                "method": expert_delta["method"],
                "basis": "状态表同状态价差变化中位数作为主点位，叠加区域规则智能体修正，并受经营上下边界约束。",
                "calculation": expert_delta.get("calculation"),
            },
            "regional_baseline_prediction": baseline_prediction,
            "core_range_half_width": round(range_half_width, 4),
            "risk_range_half_width": round(risk_range_half_width, 4),
            "risk_range_lower": round(point_value - risk_range_half_width, 2),
            "risk_range_upper": round(point_value + risk_range_half_width, 2),
            "range_basis": range_basis,
            "historical_error_half_width": None,
            "historical_error_lower": None,
            "historical_error_upper": None,
            "current_shandong_price": round(float(current_row["sd_gas92_market"]), 2),
            "current_counter_region_price": round(float(counter_region_price), 2),
            "freight_estimate": round(freight_estimate, 2),
            "freight_source": freight_setting.get("source_type", "default"),
            "freight_updated_at": freight_setting.get("updated_at"),
            "freight_updated_by": freight_setting.get("updated_by"),
            "freight_as_of_date": freight_setting.get("as_of_date"),
            "freight_components": freight_setting.get("components", []),
            "freight_calculation": freight_setting.get("calculation"),
            "freight_workbook_value": freight_setting.get("workbook_value"),
            "regional_inventory": regional_inventory,
            "netback_spread": round(current_netback_spread, 2),
            "predicted_netback_spread": round(predicted_netback_spread, 2),
            "trade_action": trade_action,
            "freight_review_required": freight_review_required,
            "netback_quality": "手工运费优先，未录入时默认估算",
            "counter_region_code": config.region_code,
            "counter_region_name": config.region_name,
            "spread_column": config.spread_column,
            "spread_change_1d": self._round_or_none(current_row.get("target_region_spread_change_1d")),
            "spread_change_3d": self._round_or_none(current_row.get("target_region_spread_change_3d")),
            "probabilities": probabilities,
            "switches": {
                "enable_refined_news": enable_refined_news,
                "enable_event_risk": enable_event_risk,
            },
            "calibration": {
                "status": "disabled",
                "reason": "区域价差点位不使用历史回归系数、截距或斜率拟合。",
                "mode": expert_delta["method"],
            },
            "confidence_components": confidence_components,
            "refined_news_count": len(context.refined_news_items),
            "event_news_count": len(context.news_items),
            "policy_notice_count": len(context.policy_items),
            "horizon_steps": horizon_config.steps,
            "horizon_label": horizon_config.label,
            "target_mode": "endpoint_spread",
            "runtime_controls": {
                claim.agent_name: claim.structured_payload.get("runtime_control", {}) for claim in claims
            },
            "market_data_mode": (context_metadata or {}).get("market_data_mode"),
            "market_data_reason": (context_metadata or {}).get("market_data_reason"),
        }
        input_hash = self._build_input_hash(
            {
                "entity_code": config.entity_code,
                "region_code": config.output_region_code,
                "product_code": "GASOLINE_92_SPREAD",
                "horizon": horizon_config.code,
                "as_of_date": as_of_date.isoformat(),
                "scenario_text": scenario_text or "",
                "score_value": round(score_value, 4),
                "raw_context": raw_context,
            }
        )
        raw_context["input_hash"] = input_hash
        llm_agent_claims = build_llm_agent_claims(
            llm_client=self.llm_client,
            enabled=use_llm_explainer,
            subject=f"山东-目标区域92#价差 {config.region_name} {horizon_config.code}",
            as_of_date=as_of_date,
            horizon=horizon_config.code,
            direction_label=direction_label,
            point_value=point_value,
            range_lower=point_value - range_half_width,
            range_upper=point_value + range_half_width,
            score_value=score_value,
            deterministic_claims=claims,
            raw_context=raw_context,
        )
        raw_context["llm_agent_reviews"] = [claim.model_dump(mode="json") for claim in llm_agent_claims]

        fallback_explanation = self._build_explanation(
            config=config,
            claims=claims,
            current_spread=current_spread_value,
            score_value=score_value,
            point_value=point_value,
            range_lower=point_value - range_half_width,
            range_upper=point_value + range_half_width,
            direction_label=direction_label,
            horizon_config=horizon_config,
        )
        fallback_driver_summary = build_driver_summary(claims)
        fallback_operating_advice = build_spread_advice(
            region_name=config.region_name,
            direction_label=direction_label,
            current_spread=current_spread_value,
            point_value=point_value,
            current_shandong_price=float(current_row["sd_gas92_market"]),
            current_counter_region_price=float(counter_region_price),
            freight_estimate=freight_estimate,
            confidence_label=confidence_label,
            claims=claims,
            freight_review_required=freight_review_required,
            trade_action=trade_action,
        )
        narrative = enrich_prediction_narrative(
            llm_client=self.llm_client,
            enabled=use_llm_explainer,
            subject=f"{config.region_name}-山东92#价差 {horizon_config.code}",
            direction_label=direction_label,
            point_value=round(point_value, 2),
            range_lower=round(point_value - range_half_width, 2),
            range_upper=round(point_value + range_half_width, 2),
            confidence_label=confidence_label,
            confidence_score=round(confidence_score, 4),
            score_value=round(score_value, 4),
            fallback_explanation=fallback_explanation,
            fallback_driver_summary=fallback_driver_summary,
            fallback_operating_advice=fallback_operating_advice,
            claims=claims,
            raw_context=raw_context,
            scenario_text=scenario_text,
        )

        factor_breakdown = [
            {
                "factor_group": claim.agent_name,
                "factor_name": claim.agent_name,
                "factor_score": round(float(claim.numeric_signals.get("raw_score", 0.0)), 4),
                "contribution": round(float(claim.numeric_signals.get("weighted_score", 0.0)), 4),
                "evidence": claim.evidence,
            }
            for claim in claims
        ]

        return PredictionResult(
            run_id=f"sdspread-{config.region_code.lower()}-{input_hash[:12]}",
            entity_code=config.entity_code,
            region_code=config.output_region_code,
            product_code="GASOLINE_92_SPREAD",
            horizon=horizon_config.code,
            as_of_date=as_of_date,
            target_date=horizon_config.target_date_from(as_of_date),
            direction_label=direction_label,
            point_value=round(point_value, 2),
            range_lower=round(point_value - range_half_width, 2),
            range_upper=round(point_value + range_half_width, 2),
            confidence_label=confidence_label,
            confidence_score=round(confidence_score, 4),
            score_value=round(score_value, 4),
            degrade_flag=bool((context_metadata or {}).get("market_data_mode") != "eta"),
            degrade_reason=(context_metadata or {}).get("market_data_reason"),
            factor_breakdown=factor_breakdown,
            agent_claims=[*claims, *llm_agent_claims],
            driver_summary=narrative.driver_summary,
            operating_advice=narrative.operating_advice,
            explanation=narrative.explanation,
            raw_context=raw_context,
        )

    def _enrich_row(self, row: pd.Series, config: RegionalSpreadConfig) -> pd.Series:
        enriched = row.copy()
        target_price = row.get(config.price_column)
        shandong_price = row.get("sd_gas92_market")
        enriched["target_region_price"] = target_price
        if pd.notna(target_price) and pd.notna(shandong_price):
            enriched["target_region_spread"] = float(target_price) - float(shandong_price)
        else:
            enriched["target_region_spread"] = np.nan
        enriched["target_region_spread_change_1d"] = self._invert_number(row.get(config.spread_change_1d_column))
        enriched["target_region_spread_change_3d"] = self._invert_number(row.get(config.spread_change_3d_column))
        return enriched

    def _score_row(
        self,
        row: pd.Series,
        extra: dict[str, Any],
        excluded_agent_names: set[str] | None = None,
    ) -> tuple[list[AgentClaim], float]:
        claims: list[AgentClaim] = []
        total_score = 0.0
        controls = self.agent_control_service.get_runtime_controls(self.scope_key)
        excluded_agent_names = excluded_agent_names or set()
        for agent in self.agents:
            if agent.name in excluded_agent_names:
                continue
            claim = agent.analyze(row, extra)
            control = controls.get(agent.name, {"enabled": True, "weight": 1.0})
            raw_score = float(claim.numeric_signals.get("score", 0.0))
            enabled = bool(control.get("enabled", True))
            weight = float(control.get("weight", 1.0)) if enabled else 0.0
            weighted_score = raw_score * weight
            claim.numeric_signals = {
                **claim.numeric_signals,
                "score": round(weighted_score, 4),
                "raw_score": round(raw_score, 4),
                "weight": round(weight, 4),
                "weighted_score": round(weighted_score, 4),
            }
            claim.structured_payload = {
                **claim.structured_payload,
                "runtime_control": {
                    "scope_key": self.scope_key,
                    "enabled": enabled,
                    "weight": round(weight, 4),
                },
            }
            claims.append(claim)
            total_score += weighted_score
        return claims, round(total_score, 4)

    def _bounded_delta_from_score(self, score_value: float, *, horizon_config: HorizonConfig) -> float:
        horizon_multiplier = {
            "D1": 1.0,
            "D3": 1.25,
            "W1": 1.6,
            "M1": 2.2,
        }.get(horizon_config.code, 1.0)
        return round(float(score_value) * horizon_multiplier, 4)

    def _expert_regional_delta(
        self,
        *,
        frame: pd.DataFrame,
        config: RegionalSpreadConfig,
        row: pd.Series,
        as_of_date: date,
        freight_estimate: float,
        regional_inventory: dict[str, Any],
        horizon_config: HorizonConfig,
    ) -> dict[str, Any]:
        current_spread = self._float_or_none(row.get("target_region_spread")) or 0.0
        state_delta = self._regional_state_table_delta(
            frame=frame,
            config=config,
            current_row=row,
            as_of_date=as_of_date,
            freight_estimate=freight_estimate,
            horizon_config=horizon_config,
        )
        rule_delta = self._regional_rule_delta(
            row=row,
            freight_estimate=freight_estimate,
            regional_inventory=regional_inventory,
            horizon_config=horizon_config,
        )
        bounds = self._regional_operating_bounds(
            frame=frame,
            config=config,
            as_of_date=as_of_date,
            freight_estimate=freight_estimate,
        )
        if state_delta["status"] == "enabled":
            weight = REGIONAL_RULE_CORRECTION_WEIGHT
            raw_delta = float(state_delta["median_delta"]) + weight * float(rule_delta["predicted_delta"])
            method = "state_median_plus_rule_correction"
        else:
            weight = 1.0
            raw_delta = float(rule_delta["predicted_delta"])
            method = "rule_correction_fallback"
        raw_point = current_spread + raw_delta
        bounded_point = self._clip(raw_point, bounds["lower"], bounds["upper"])
        predicted_delta = bounded_point - current_spread
        return {
            "method": method,
            "formula": "预测变化量=状态表价差变化中位数+当日规则修正；预测价差再受经营上下边界约束。状态样本不足时降级为规则修正。",
            "current_spread": round(current_spread, 4),
            "state_delta": state_delta,
            "rule_delta": rule_delta,
            "rule_correction_weight": weight,
            "operating_bounds": bounds,
            "raw_predicted_spread": round(raw_point, 4),
            "bounded_predicted_spread": round(bounded_point, 4),
            "predicted_delta": round(predicted_delta, 4),
            "calculation": (
                f"{state_delta.get('median_delta', 0.0)} + {weight} × {rule_delta['predicted_delta']}；"
                f"价差边界[{bounds['lower']}, {bounds['upper']}]，得到变化{round(predicted_delta, 4)}"
            ),
        }

    def _regional_rule_delta(
        self,
        *,
        row: pd.Series,
        freight_estimate: float,
        regional_inventory: dict[str, Any],
        horizon_config: HorizonConfig,
    ) -> dict[str, Any]:
        current_spread = self._float_or_none(row.get("target_region_spread")) or 0.0
        change_1d = self._float_or_none(row.get("target_region_spread_change_1d")) or 0.0
        change_3d = self._float_or_none(row.get("target_region_spread_change_3d")) or 0.0
        netback_spread = current_spread - freight_estimate

        momentum_delta = self._clip(change_3d * 0.45 + change_1d * 0.25, -6.0, 6.0)
        structure_reversion = 0.0
        if current_spread >= 160.0:
            structure_reversion = -5.0
        elif current_spread >= 120.0:
            structure_reversion = -3.0
        elif current_spread >= 80.0:
            structure_reversion = -1.0
        elif current_spread <= 0.0:
            structure_reversion = 4.0
        elif current_spread <= 30.0:
            structure_reversion = 2.0

        netback_delta = 0.0
        if netback_spread >= 80.0:
            netback_delta = -4.0
        elif netback_spread >= 40.0:
            netback_delta = -2.0
        elif netback_spread >= 0.0:
            netback_delta = -1.0

        inventory_delta = 0.0
        inventory_ratio = regional_inventory.get("ratio_to_median") if regional_inventory.get("available") else None
        inventory_wow = regional_inventory.get("wow_change") if regional_inventory.get("available") else None
        if inventory_ratio is not None:
            inventory_ratio = float(inventory_ratio)
            if inventory_ratio >= 1.25:
                inventory_delta -= 4.0
            elif inventory_ratio >= 1.12:
                inventory_delta -= 2.0
            elif inventory_ratio <= 0.75:
                inventory_delta += 4.0
            elif inventory_ratio <= 0.88:
                inventory_delta += 2.0
        if inventory_wow is not None:
            inventory_wow = float(inventory_wow)
            if inventory_wow >= 5.0:
                inventory_delta -= 1.5
            elif inventory_wow <= -5.0:
                inventory_delta += 1.5

        raw_d1_delta = momentum_delta + structure_reversion + netback_delta + inventory_delta
        horizon_multiplier = {
            "D1": 1.0,
            "D3": 1.6,
            "W1": 2.4,
            "M1": 4.0,
        }.get(horizon_config.code, 1.0)
        horizon_cap = {
            "D1": 12.0,
            "D3": 22.0,
            "W1": 35.0,
            "M1": 50.0,
        }.get(horizon_config.code, 12.0)
        predicted_delta = self._clip(raw_d1_delta * horizon_multiplier, -horizon_cap, horizon_cap)
        contributions = {
            "momentum_delta": round(momentum_delta, 4),
            "structure_reversion_delta": round(structure_reversion, 4),
            "netback_delta": round(netback_delta, 4),
            "inventory_delta": round(inventory_delta, 4),
        }
        return {
            "method": "expert_rule_point_contribution",
            "formula": "预测变化量=限幅((价差动量贡献+价差极值回归贡献+净回款套利贡献+区域库存贡献)*周期倍数)",
            "current_spread": round(current_spread, 4),
            "spread_change_1d": round(change_1d, 4),
            "spread_change_3d": round(change_3d, 4),
            "netback_spread": round(netback_spread, 4),
            "inventory_ratio_to_median": round(float(inventory_ratio), 4) if inventory_ratio is not None else None,
            "inventory_wow_change": round(float(inventory_wow), 4) if inventory_wow is not None else None,
            "contributions": contributions,
            "raw_d1_delta": round(raw_d1_delta, 4),
            "horizon_multiplier": horizon_multiplier,
            "horizon_cap": horizon_cap,
            "predicted_delta": round(predicted_delta, 4),
            "calculation": (
                f"({contributions['momentum_delta']} + {contributions['structure_reversion_delta']} + "
                f"{contributions['netback_delta']} + {contributions['inventory_delta']}) * "
                f"{horizon_multiplier}，限幅±{horizon_cap} = {round(predicted_delta, 4)}"
            ),
        }

    def _regional_baseline_prediction(
        self,
        *,
        current_spread: float,
        rule_delta: dict[str, Any],
        operating_bounds: dict[str, Any],
        regional_inventory: dict[str, Any],
        horizon_config: HorizonConfig,
    ) -> dict[str, Any]:
        raw_delta = float(rule_delta.get("predicted_delta") or 0.0)
        lower_bound = float(operating_bounds.get("lower"))
        upper_bound = float(operating_bounds.get("upper"))
        raw_point = current_spread + raw_delta
        point_value = self._clip(raw_point, lower_bound, upper_bound)
        predicted_delta = point_value - current_spread
        range_half_width = self._regional_baseline_range_half_width(
            rule_delta=rule_delta,
            regional_inventory=regional_inventory,
            horizon_config=horizon_config,
            predicted_delta=predicted_delta,
        )
        direction_label = self._direction_from_delta(
            predicted_delta,
            threshold=self._regional_direction_threshold(horizon_config),
        )
        return {
            "model_name": "区域业务基准预测",
            "prediction_type": "regional_baseline",
            "direction_label": direction_label,
            "predicted_delta": round(predicted_delta, 4),
            "predicted_region_minus_shandong_spread": round(point_value, 2),
            "predicted_region_minus_shandong_spread_range_lower": round(point_value - range_half_width, 2),
            "predicted_region_minus_shandong_spread_range_upper": round(point_value + range_half_width, 2),
            "range_half_width": round(range_half_width, 4),
            "method": "regional_rule_baseline",
            "basis": "只使用区域规则贡献，不使用状态表中位数；用于和区域智能体综合预测并列对比。",
            "rule_delta": rule_delta,
            "operating_bounds": operating_bounds,
            "calculation": (
                f"当前价差{round(current_spread, 4)} + 规则变化{round(raw_delta, 4)}，"
                f"经经营边界[{lower_bound}, {upper_bound}]约束后得到变化{round(predicted_delta, 4)}"
            ),
        }

    def _regional_baseline_range_half_width(
        self,
        *,
        rule_delta: dict[str, Any],
        regional_inventory: dict[str, Any],
        horizon_config: HorizonConfig,
        predicted_delta: float,
    ) -> float:
        base = {
            "D1": 14.0,
            "D3": 26.0,
            "W1": 40.0,
            "M1": 58.0,
        }.get(horizon_config.code, 14.0)
        contributions = [
            float(value)
            for value in (rule_delta.get("contributions") or {}).values()
            if abs(float(value)) > 0
        ]
        has_positive = any(value > 0 for value in contributions)
        has_negative = any(value < 0 for value in contributions)
        conflict_addon = 5.0 if has_positive and has_negative else 0.0
        inventory_addon = 5.0 if not regional_inventory.get("available") else 0.0
        weak_signal_addon = (
            4.0 if abs(float(predicted_delta or 0.0)) < self._regional_direction_threshold(horizon_config) else 0.0
        )
        return min(65.0, base + conflict_addon + inventory_addon + weak_signal_addon)

    def _regional_state_table_delta(
        self,
        *,
        frame: pd.DataFrame,
        config: RegionalSpreadConfig,
        current_row: pd.Series,
        as_of_date: date,
        freight_estimate: float,
        horizon_config: HorizonConfig,
    ) -> dict[str, Any]:
        history_rows: list[dict[str, Any]] = []
        sorted_frame = frame[frame["date"] <= as_of_date].sort_values("date").reset_index(drop=True)
        for idx in range(len(sorted_frame) - horizon_config.steps):
            source_row = sorted_frame.iloc[idx]
            target_row = sorted_frame.iloc[idx + horizon_config.steps]
            source_date = self._parse_date_text(source_row.get("date"))
            target_date = self._parse_date_text(target_row.get("date"))
            if source_date is None or target_date is None or target_date > as_of_date:
                continue
            enriched_source = self._enrich_row(source_row, config)
            enriched_target = self._enrich_row(target_row, config)
            source_spread = self._float_or_none(enriched_source.get("target_region_spread"))
            target_spread = self._float_or_none(enriched_target.get("target_region_spread"))
            if source_spread is None or target_spread is None:
                continue
            history_rows.append(
                {
                    "date": source_date,
                    "spread": source_spread,
                    "change_3d": self._float_or_none(enriched_source.get("target_region_spread_change_3d")) or 0.0,
                    "netback": source_spread - freight_estimate,
                    "future_delta": target_spread - source_spread,
                }
            )
        if len(history_rows) < REGIONAL_STATE_MIN_SAMPLE:
            return {
                "status": "fallback",
                "reason": f"有效历史状态样本{len(history_rows)}条，低于{REGIONAL_STATE_MIN_SAMPLE}条",
                "sample_size": len(history_rows),
                "median_delta": 0.0,
            }

        spreads = np.array([item["spread"] for item in history_rows], dtype=float)
        quantiles = {
            "q10": float(np.quantile(spreads, 0.10)),
            "q30": float(np.quantile(spreads, 0.30)),
            "q70": float(np.quantile(spreads, 0.70)),
            "q90": float(np.quantile(spreads, 0.90)),
        }
        current_state = self._regional_state_key(
            spread=float(current_row["target_region_spread"]),
            change_3d=self._float_or_none(current_row.get("target_region_spread_change_3d")) or 0.0,
            netback=float(current_row["target_region_spread"]) - freight_estimate,
            quantiles=quantiles,
        )
        for level in ("full", "position_momentum", "position"):
            matched = [
                item["future_delta"]
                for item in history_rows
                if self._state_matches(
                    current_state,
                    self._regional_state_key(
                        spread=item["spread"],
                        change_3d=item["change_3d"],
                        netback=item["netback"],
                        quantiles=quantiles,
                    ),
                    level=level,
                )
            ]
            if len(matched) >= REGIONAL_STATE_MIN_SAMPLE:
                lower = float(np.quantile(matched, 0.20))
                upper = float(np.quantile(matched, 0.80))
                return {
                    "status": "enabled",
                    "match_level": level,
                    "state_key": current_state,
                    "sample_size": len(matched),
                    "median_delta": round(float(np.median(matched)), 4),
                    "p20_delta": round(lower, 4),
                    "p80_delta": round(upper, 4),
                    "quantiles": {key: round(value, 4) for key, value in quantiles.items()},
                    "reason": "使用预测日前已完成样本的同状态价差变化中位数",
                }
        return {
            "status": "fallback",
            "reason": f"状态{current_state}匹配样本不足，降级为当日规则修正",
            "state_key": current_state,
            "sample_size": len(history_rows),
            "median_delta": 0.0,
            "quantiles": {key: round(value, 4) for key, value in quantiles.items()},
        }

    def _regional_state_key(
        self,
        *,
        spread: float,
        change_3d: float,
        netback: float,
        quantiles: dict[str, float],
    ) -> dict[str, str]:
        if spread <= quantiles["q10"]:
            position = "extreme_low"
        elif spread <= quantiles["q30"]:
            position = "low"
        elif spread >= quantiles["q90"]:
            position = "extreme_high"
        elif spread >= quantiles["q70"]:
            position = "high"
        else:
            position = "normal"
        if change_3d >= 2.0:
            momentum = "expanding"
        elif change_3d <= -2.0:
            momentum = "narrowing"
        else:
            momentum = "stable"
        if netback >= 80.0:
            netback_state = "strong_open"
        elif netback >= 30.0:
            netback_state = "open"
        elif netback >= 0.0:
            netback_state = "weak_open"
        else:
            netback_state = "closed"
        return {"position": position, "momentum": momentum, "netback": netback_state}

    def _state_matches(self, current: dict[str, str], candidate: dict[str, str], *, level: str) -> bool:
        if level == "full":
            return current == candidate
        if level == "position_momentum":
            return current["position"] == candidate["position"] and current["momentum"] == candidate["momentum"]
        if level == "position":
            return current["position"] == candidate["position"]
        return False

    def _regional_operating_bounds(
        self,
        *,
        frame: pd.DataFrame,
        config: RegionalSpreadConfig,
        as_of_date: date,
        freight_estimate: float,
    ) -> dict[str, float]:
        spreads: list[float] = []
        for _, source_row in frame[frame["date"] <= as_of_date].iterrows():
            enriched = self._enrich_row(source_row, config)
            spread = self._float_or_none(enriched.get("target_region_spread"))
            if spread is not None:
                spreads.append(spread)
        if len(spreads) < 20:
            lower = -0.35 * freight_estimate - REGIONAL_RISK_BUFFER
            upper = freight_estimate + REGIONAL_REQUIRED_MARGIN + REGIONAL_RISK_BUFFER
            return {"lower": round(lower, 4), "upper": round(upper, 4), "basis": "route_cost_fallback"}
        values = np.array(spreads, dtype=float)
        median = float(np.median(values))
        robust_sigma = 1.4826 * float(np.median(np.abs(values - median)))
        distribution_lower = float(np.quantile(values, 0.05)) - 0.5 * robust_sigma
        distribution_upper = float(np.quantile(values, 0.95)) + 0.5 * robust_sigma
        route_lower = -0.35 * freight_estimate - REGIONAL_RISK_BUFFER
        route_upper = freight_estimate + REGIONAL_REQUIRED_MARGIN + REGIONAL_RISK_BUFFER
        lower = max(distribution_lower, route_lower)
        upper = min(distribution_upper, route_upper) if distribution_upper > lower else route_upper
        return {
            "lower": round(lower, 4),
            "upper": round(upper, 4),
            "basis": "distribution_and_route_cost",
            "median": round(median, 4),
            "robust_sigma": round(robust_sigma, 4),
            "distribution_lower": round(distribution_lower, 4),
            "distribution_upper": round(distribution_upper, 4),
            "route_lower": round(route_lower, 4),
            "route_upper": round(route_upper, 4),
        }

    def _regional_expert_range_half_width(
        self,
        *,
        expert_delta: dict[str, Any],
        regional_inventory: dict[str, Any],
        horizon_config: HorizonConfig,
    ) -> float:
        base = {
            "D1": 12.0,
            "D3": 22.0,
            "W1": 35.0,
            "M1": 50.0,
        }.get(horizon_config.code, 12.0)
        rule_delta = expert_delta.get("rule_delta") or expert_delta
        contributions = [
            float(value)
            for value in (rule_delta.get("contributions") or {}).values()
            if abs(float(value)) > 0
        ]
        has_positive = any(value > 0 for value in contributions)
        has_negative = any(value < 0 for value in contributions)
        conflict_addon = 4.0 if has_positive and has_negative else 0.0
        inventory_addon = 4.0 if not regional_inventory.get("available") else 0.0
        state_addon = 0.0 if (expert_delta.get("state_delta") or {}).get("status") == "enabled" else 6.0
        weak_signal_addon = 3.0 if abs(float(expert_delta.get("predicted_delta") or 0.0)) < self._regional_direction_threshold(horizon_config) else 0.0
        return min(50.0, base + conflict_addon + inventory_addon + state_addon + weak_signal_addon)

    def _regional_direction_threshold(self, horizon_config: HorizonConfig) -> float:
        return {
            "D1": 0.5,
            "D3": 1.0,
            "W1": 1.5,
            "M1": 2.5,
        }.get(horizon_config.code, 0.5)

    def _clip(self, value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, float(value)))

    def _regional_inventory_context(self, *, config: RegionalSpreadConfig, as_of_date: date) -> dict[str, Any]:
        cache_key = (config.region_code, as_of_date)
        cached = self._regional_inventory_context_cache.get(cache_key)
        if cached is not None:
            return cached

        rows = self._load_regional_inventory_rows(as_of_date=as_of_date)
        if not rows:
            result = {"available": False, "reason": "未找到区域库存归档数据"}
            self._regional_inventory_context_cache[cache_key] = result
            return result

        region_token = config.region_name
        selected_project_id = None
        selected_rows: list[dict[str, Any]] = []
        for project_id in (12975, 12944):
            candidates = [
                row
                for row in rows
                if row.get("project_quota_id") == project_id
                and "汽油" in str(row.get("product") or row.get("project_label") or "")
            ]
            if candidates:
                selected_project_id = project_id
                selected_rows = candidates
                break
        if not selected_rows or selected_project_id is None:
            result = {"available": False, "reason": "未找到汽油贸易商区域库存数据"}
            self._regional_inventory_context_cache[cache_key] = result
            return result

        latest_date = max((self._parse_date_text(row.get("date")) for row in selected_rows), default=None)
        if latest_date is None:
            result = {"available": False, "reason": "区域库存日期缺失"}
            self._regional_inventory_context_cache[cache_key] = result
            return result

        latest_rows = [row for row in selected_rows if self._parse_date_text(row.get("date")) == latest_date]
        target_rows = [row for row in latest_rows if region_token in str(row.get("region") or "")]
        if not target_rows:
            result = {"available": False, "reason": f"未找到{config.region_name}库存样本"}
            self._regional_inventory_context_cache[cache_key] = result
            return result

        target_value = self._float_or_none(target_rows[0].get("value"))
        peer_values = [self._float_or_none(row.get("value")) for row in latest_rows]
        peer_values = [value for value in peer_values if value is not None]
        if target_value is None or not peer_values:
            result = {"available": False, "reason": f"{config.region_name}库存数值缺失"}
            self._regional_inventory_context_cache[cache_key] = result
            return result

        prior_dates = sorted(
            {
                parsed
                for row in selected_rows
                for parsed in [self._parse_date_text(row.get("date"))]
                if parsed is not None and parsed < latest_date
            },
            reverse=True,
        )
        prior_value = None
        if prior_dates:
            prior_date = prior_dates[0]
            prior_target = [
                row
                for row in selected_rows
                if self._parse_date_text(row.get("date")) == prior_date and region_token in str(row.get("region") or "")
            ]
            if prior_target:
                prior_value = self._float_or_none(prior_target[0].get("value"))
        median_value = float(np.median(peer_values))
        wow_change = target_value - prior_value if prior_value is not None else None
        stale_days = (as_of_date - latest_date).days
        subject = "贸易商" if selected_project_id == 12975 else "部分社会油库"
        result = {
            "available": stale_days <= 21,
            "reason": None if stale_days <= 21 else f"区域库存最新日期{latest_date.isoformat()}，距预测日超过21天",
            "project_quota_id": selected_project_id,
            "subject": subject,
            "latest_date": latest_date.isoformat(),
            "target_region": config.region_name,
            "target_value": round(target_value, 4),
            "peer_median": round(median_value, 4),
            "ratio_to_median": round(target_value / median_value, 4) if median_value else None,
            "wow_change": round(wow_change, 4) if wow_change is not None else None,
            "unit": target_rows[0].get("unit") or "万吨",
        }
        self._regional_inventory_context_cache[cache_key] = result
        return result

    def _load_regional_inventory_rows(self, *, as_of_date: date) -> list[dict[str, Any]]:
        cached = self._regional_inventory_cache.get(as_of_date)
        if cached is not None:
            return cached
        try:
            payload = self.dataset_service.get_oilchem_openapi_inventory(
                start_date=as_of_date - timedelta(days=90),
                end_date=as_of_date,
            )
            rows = list(payload.get("items") or [])
        except Exception:
            rows = []
        self._regional_inventory_cache[as_of_date] = rows
        return rows

    def _parse_date_text(self, value: Any) -> date | None:
        if isinstance(value, date):
            return value
        try:
            text = str(value or "").strip()
            if not text:
                return None
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    def _float_or_none(self, value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None

    def _build_explanation(
        self,
        *,
        config: RegionalSpreadConfig,
        claims: list[AgentClaim],
        current_spread: float,
        score_value: float,
        point_value: float,
        range_lower: float,
        range_upper: float,
        direction_label: str,
        horizon_config: HorizonConfig,
    ) -> str:
        direction_text = {"up": "走扩", "down": "收敛", "flat": "震荡"}[direction_label]
        top_claims = sorted(
            claims,
            key=lambda item: abs(float(item.numeric_signals.get("weighted_score", 0.0))),
            reverse=True,
        )[:3]
        details = "；".join(item.evidence[0] if item.evidence else item.summary for item in top_claims if item.summary)
        return (
            f"{config.region_name}-山东92#价差 {horizon_config.code} 判断为{direction_text}，当前价差 {current_spread:.2f}，"
            f"综合分 {score_value:.2f}，预测点位 {point_value:.2f}，区间 {range_lower:.2f}~{range_upper:.2f}。"
            + (f" 主要依据包括：{details}。" if details else "")
        )

    def _invert_number(self, value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return -float(value)
        except Exception:
            return None

    def _direction_from_delta(self, predicted_delta: float, threshold: float = 2.0) -> str:
        if predicted_delta > threshold:
            return "up"
        if predicted_delta < -threshold:
            return "down"
        return "flat"

    def _probabilities_from_score(self, score_value: float) -> dict[str, float]:
        up_raw = max(score_value, 0.0) + 10.0
        down_raw = max(-score_value, 0.0) + 10.0
        flat_raw = max(5.0, 50.0 - abs(score_value))
        total = up_raw + down_raw + flat_raw
        return {
            "up": round(up_raw / total, 4),
            "flat": round(flat_raw / total, 4),
            "down": round(down_raw / total, 4),
        }

    def _freight_review_required(self, freight_setting: dict[str, Any]) -> bool:
        if freight_setting.get("source_type") != "manual":
            return True
        updated_at = freight_setting.get("updated_at")
        if not updated_at:
            return True
        if isinstance(updated_at, datetime):
            updated_dt = updated_at
        else:
            try:
                updated_dt = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            except ValueError:
                return True
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - updated_dt.astimezone(timezone.utc)).total_seconds() > 24 * 3600

    def _trade_action_from_netback_spread(
        self,
        *,
        netback_spread: float,
        freight_review_required: bool,
    ) -> dict[str, Any]:
        if freight_review_required:
            review_note = "运费超过24小时未确认或仍为默认估算，执行前必须复核。"
        else:
            review_note = "运费已人工确认。"
        if netback_spread > 60.0:
            return {
                "level": "expand",
                "label": "扩大外发",
                "action": "连续两次刷新保持为正后，可扩大外发。",
                "trigger": "预测净回款价差 > 60 元/吨",
                "review_note": review_note,
            }
        if netback_spread >= 30.0:
            return {
                "level": "trial",
                "label": "小批量试发",
                "action": "成交活跃且客户账期可控时，小批量试发。",
                "trigger": "预测净回款价差 30-60 元/吨",
                "review_note": review_note,
            }
        if netback_spread >= 0.0:
            return {
                "level": "maintenance",
                "label": "客户维护",
                "action": "仅做客户维护或锁价订单，不主动放量。",
                "trigger": "预测净回款价差 0-30 元/吨",
                "review_note": review_note,
            }
        return {
            "level": "stop",
            "label": "原则停发",
            "action": "原则上停止跨区外发，优先本地或近距离成交。",
            "trigger": "预测净回款价差 < 0 元/吨",
            "review_note": review_note,
        }

    def _round_or_none(self, value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)

    def _build_input_hash(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
