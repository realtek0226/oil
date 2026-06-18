from __future__ import annotations

import numbers
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


CHINA_PUBLIC_HOLIDAY_DATES_2026 = {
    date(2026, 1, 1),
    date(2026, 1, 2),
    date(2026, 1, 3),
    date(2026, 2, 15),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 20),
    date(2026, 2, 21),
    date(2026, 2, 22),
    date(2026, 2, 23),
    date(2026, 4, 4),
    date(2026, 4, 5),
    date(2026, 4, 6),
    date(2026, 5, 1),
    date(2026, 5, 2),
    date(2026, 5, 3),
    date(2026, 5, 4),
    date(2026, 5, 5),
    date(2026, 6, 19),
    date(2026, 6, 20),
    date(2026, 6, 21),
    date(2026, 9, 25),
    date(2026, 9, 26),
    date(2026, 9, 27),
    date(2026, 10, 1),
    date(2026, 10, 2),
    date(2026, 10, 3),
    date(2026, 10, 4),
    date(2026, 10, 5),
    date(2026, 10, 6),
    date(2026, 10, 7),
}


@dataclass(frozen=True)
class ScorecardEvaluation:
    scorecard_code: str
    scorecard_version: str
    source_document: str
    horizon_requested: str
    horizon_used: str
    total_score: float
    group_scores: list[dict[str, Any]]
    unresolved_items: list[dict[str, Any]]


class ScorecardEngine:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._payload: dict[str, Any] | None = None

    def evaluate(
        self,
        *,
        scorecard_code: str,
        horizon: str,
        row: pd.Series,
        extra: dict[str, Any],
    ) -> ScorecardEvaluation:
        payload = self._load()
        card = self._find_scorecard(payload, scorecard_code)
        horizon_used = self._resolve_horizon(card, horizon)
        horizon_payload = card["horizons"][horizon_used]
        extra = {**extra, "horizon": horizon_used}

        group_scores: list[dict[str, Any]] = []
        unresolved_items: list[dict[str, Any]] = []
        total_score = 0.0

        for group in horizon_payload.get("factor_groups", []):
            group_code = str(group.get("group_code") or "unknown")
            group_cap = float(group.get("score_cap") or group.get("weight_pct") or 0.0)
            feature_scores: list[dict[str, Any]] = []
            group_score = 0.0

            if group.get("unresolved_thresholds"):
                unresolved_items.append(
                    {
                        "group_code": group_code,
                        "feature_name": group.get("primary_feature"),
                        "reason": group.get("unresolved_reason") or "业务打分模型未给出明确阈值",
                    }
                )

            for feature in group.get("features", []):
                evaluated = self._evaluate_feature(feature, row=row, extra=extra)
                feature_scores.append(evaluated)
                group_score += float(evaluated["score"])

            for adjustment in group.get("adjustments", []):
                evaluated = self._evaluate_feature(adjustment, row=row, extra=extra)
                evaluated["is_adjustment"] = True
                feature_scores.append(evaluated)
                group_score += float(evaluated["score"])

            group_score = _clip(group_score, -group_cap, group_cap) if group_cap > 0 else group_score
            total_score += group_score
            group_scores.append(
                {
                    "group_code": group_code,
                    "display_name": group.get("display_name") or group_code,
                    "score": round(group_score, 4),
                    "score_cap": group_cap,
                    "features": feature_scores,
                }
            )

        score_range = horizon_payload.get("score_range") or payload.get("globals", {}).get("score_range", {})
        if isinstance(score_range, list) and len(score_range) == 2:
            total_score = _clip(total_score, float(score_range[0]), float(score_range[1]))
        elif isinstance(score_range, dict):
            total_score = _clip(total_score, float(score_range.get("min", -100)), float(score_range.get("max", 100)))

        return ScorecardEvaluation(
            scorecard_code=scorecard_code,
            scorecard_version=str(payload.get("version") or "unknown"),
            source_document=str(payload.get("source_document") or ""),
            horizon_requested=horizon,
            horizon_used=horizon_used,
            total_score=round(total_score, 4),
            group_scores=group_scores,
            unresolved_items=unresolved_items,
        )

    def _load(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        return self._payload

    def _find_scorecard(self, payload: dict[str, Any], scorecard_code: str) -> dict[str, Any]:
        for card in payload.get("scorecards", []):
            if card.get("scorecard_code") == scorecard_code:
                return card
        raise KeyError(f"scorecard_code not found: {scorecard_code}")

    def _resolve_horizon(self, card: dict[str, Any], horizon: str) -> str:
        normalized = horizon.strip().upper()
        horizons = card.get("horizons", {})
        if normalized in horizons:
            return normalized
        if normalized.startswith("W") and "W1" in horizons:
            return "W1"
        if normalized.startswith("M") and "W1" in horizons:
            return "W1"
        if normalized.startswith("D") and "D1" in horizons:
            return "D1"
        return next(iter(horizons))

    def _evaluate_feature(self, feature: dict[str, Any], *, row: pd.Series, extra: dict[str, Any]) -> dict[str, Any]:
        feature_name = str(feature.get("feature_name") or "unknown")
        method = str(feature.get("method") or "")
        resolved = self._resolve_feature(feature_name, row=row, extra=extra)
        value = resolved.get("value")
        score_value = value
        explicit_score_value_feature = feature.get("score_value_feature")
        score_value_feature = explicit_score_value_feature or self._default_score_value_feature(feature_name)
        if score_value_feature:
            score_resolved = self._resolve_feature(str(score_value_feature), row=row, extra=extra)
            resolved_score_value = score_resolved.get("value")
            if resolved_score_value is not None:
                score_value = resolved_score_value
            elif explicit_score_value_feature:
                score_value = resolved_score_value
            else:
                score_value_feature = None

        effective_rules = self._default_score_rules(feature_name, feature.get("rules") or []) if score_value_feature else (feature.get("rules") or [])
        if self._unchanged_score_gate(feature_name=feature_name, row=row, extra=extra):
            score, label = 0.0, "unchanged_from_previous"
        elif method == "bucket_score":
            score, label = self._bucket_score(score_value, effective_rules)
        elif method == "enum_score":
            label = str(value)
            score = float((feature.get("rules") or {}).get(label, 0.0))
        elif method == "bounded_numeric":
            lower = float(feature.get("min", -100.0))
            upper = float(feature.get("max", 100.0))
            score = _clip(float(value or 0.0), lower, upper)
            label = "bounded_numeric"
        elif method == "calendar_month_band":
            score, label = self._calendar_month_score(feature, extra=extra)
        else:
            score = 0.0
            label = "unsupported_method"

        score_cap = feature.get("score_cap")
        if score_cap is not None:
            cap = float(score_cap)
            score = _clip(score, -cap, cap)

        return {
            "feature_name": feature_name,
            "method": method,
            "value": value,
            "score_value": score_value,
            "score_value_feature": score_value_feature,
            "matched_label": label,
            "score": round(float(score), 4),
            "value_source": resolved.get("source"),
            "value_note": resolved.get("note"),
        }

    def _resolve_feature(self, feature_name: str, *, row: pd.Series, extra: dict[str, Any]) -> dict[str, Any]:
        brent_forecast = self._resolve_brent_forecast_change(feature_name, extra=extra)
        if brent_forecast is not None:
            return brent_forecast
        if feature_name.startswith("trader_sentiment_label"):
            sentiment = extra.get("trade_sentiment") or {}
            if isinstance(sentiment, dict) and sentiment.get("label"):
                return {
                    "value": str(sentiment.get("label")),
                    "source": sentiment.get("source") or "llm_trade_sentiment",
                    "note": sentiment.get("reason"),
                }
        return {"value": self._resolve_feature_value(feature_name, row=row, extra=extra), "source": "feature_frame"}

    def _default_score_value_feature(self, feature_name: str) -> str | None:
        return {
            "shandong_cdu_utilization_weekly": "shandong_cdu_utilization_percentile_weekly",
            "shandong_product_inventory_percentile_weekly": "shandong_product_inventory_change_weekly",
            "refinery_inventory_monthly": "shandong_refinery_inventory_change_weekly",
            "main_company_inventory_monthly": "shandong_main_company_inventory_change_weekly",
        }.get(feature_name)

    def _default_score_rules(self, feature_name: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if feature_name in {
            "shandong_product_inventory_percentile_weekly",
            "refinery_inventory_monthly",
            "main_company_inventory_monthly",
        }:
            cap = self._max_abs_rule_score(rules)
            return [
                {"min": None, "max": -100.0, "score": cap, "label": "inventory_down_large"},
                {"min": -100.0, "max": -20.0, "score": cap * 0.5, "label": "inventory_down"},
                {"min": -20.0, "max": 20.0, "score": 0.0, "label": "inventory_flat"},
                {"min": 20.0, "max": 100.0, "score": -cap * 0.5, "label": "inventory_up"},
                {"min": 100.0, "max": None, "score": -cap, "label": "inventory_up_large"},
            ]
        return rules

    def _max_abs_rule_score(self, rules: list[dict[str, Any]]) -> float:
        values = []
        for rule in rules:
            try:
                values.append(abs(float(rule.get("score") or 0.0)))
            except Exception:
                continue
        return max(values) if values else 0.0

    def _bucket_score(self, value: Any, rules: list[dict[str, Any]]) -> tuple[float, str]:
        numeric_value = self._safe_float(value)
        if numeric_value is None:
            return 0.0, "missing"
        for rule in rules:
            lower = rule.get("min")
            upper = rule.get("max")
            if lower is not None and numeric_value < float(lower):
                continue
            if upper is not None and numeric_value >= float(upper):
                continue
            return float(rule.get("score") or 0.0), str(rule.get("label") or "matched")
        return 0.0, "unmatched"

    def _calendar_month_score(self, feature: dict[str, Any], *, extra: dict[str, Any]) -> tuple[float, str]:
        as_of = extra.get("as_of_date")
        target_date = as_of if isinstance(as_of, date) else date.today()
        target_date = self._add_months(target_date, int(feature.get("target_month_offset") or 0))
        month = target_date.month
        scores = feature.get("scores") or {}
        if month in (feature.get("peak_months") or []):
            return float(scores.get("peak", 0.0)), "peak"
        if month in (feature.get("secondary_peak_months") or []):
            return float(scores.get("secondary_peak", scores.get("neutral", 0.0))), "secondary_peak"
        if month in (feature.get("secondary_off_months") or []):
            return float(scores.get("secondary_off", scores.get("neutral", 0.0))), "secondary_off"
        if month in (feature.get("off_months") or []):
            return float(scores.get("off", 0.0)), "off"
        return float(scores.get("neutral", 0.0)), "neutral"

    def _add_months(self, value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, self._days_in_month(year, month))
        return date(year, month, day)

    def _days_in_month(self, year: int, month: int) -> int:
        if month == 12:
            return 31
        return (date(year, month + 1, 1) - timedelta(days=1)).day

    def _resolve_feature_value(self, feature_name: str, *, row: pd.Series, extra: dict[str, Any]) -> Any:
        feature_aliases = {
            "brent_change_usd_d1": "brent_change_1d",
            "brent_change_usd_d3": "brent_change_3d",
            "brent_change_usd_w1": "brent_change_5d",
            "brent_change_usd_mom": "brent_change_20d",
            "shandong_cdu_utilization_weekly": "shandong_cdu_utilization_weekly",
            "shandong_cdu_utilization_percentile_weekly": "shandong_cdu_utilization_percentile_weekly",
            "shandong_cdu_utilization_percentile_monthly": "shandong_cdu_utilization_percentile_monthly",
            "shandong_product_inventory_percentile_weekly": "shandong_product_inventory_percentile_weekly",
            "refinery_inventory_monthly": "shandong_refinery_inventory_percentile_monthly",
            "main_company_inventory_monthly": "shandong_main_company_inventory_percentile_monthly",
            "sales_production_ratio_d1": "sales_production_ratio_d1",
            "sales_production_ratio_d3_avg": "sales_production_ratio_d3_avg",
            "sales_production_ratio_w1_avg": "sales_production_ratio_w1_avg",
            "sales_ratio_d1": "sales_ratio_d1",
            "sales_ratio_d3_avg": "sales_ratio_d3_avg",
            "sales_ratio_w1_avg": "sales_ratio_w1_avg",
            "crude_run_change_1w": "crude_run_change_1w",
            "shandong_product_inventory_change_weekly": "shandong_product_inventory_change_weekly",
            "shandong_refinery_inventory_change_weekly": "shandong_refinery_inventory_change_weekly",
            "shandong_main_company_inventory_change_weekly": "shandong_main_company_inventory_change_weekly",
        }
        if feature_name in feature_aliases:
            if feature_name.startswith("brent_change_usd_"):
                return None
            if feature_name == "shandong_product_inventory_percentile_weekly":
                product_code = str((extra or {}).get("product_code") or "").upper()
                if product_code == "DIESEL_0":
                    return self._row_value(row, "shandong_diesel_product_inventory_percentile_weekly")
            return self._row_value(row, feature_aliases[feature_name])
        if feature_name in {"gasoline_crack_trend_d1", "gasoline_crack_trend_monthly"}:
            value = self._safe_float(self._row_value(row, "gasoline_crack_change_3d"))
            if value is None:
                return "flat"
            if value > 5:
                return "expanded"
            if value < -5:
                return "contracted"
            return "flat"
        if feature_name.startswith("trader_sentiment_label"):
            return self._sentiment_label(extra)
        if feature_name.startswith("shandong_refinery_load_news_adjustment"):
            return self._refinery_load_news_adjustment(extra)
        if feature_name == "inventory_trend_weekly":
            return self._inventory_trend(row)
        if feature_name.startswith("price_window_expectation"):
            return self._price_window_expectation(row)
        if feature_name == "monthly_seasonality_phase":
            return feature_name
        if feature_name == "next_month_maintenance_plan":
            return self._maintenance_plan_label(extra, horizon=str(extra.get("horizon") or "M1"))
        if feature_name.startswith("refinery_maintenance_plan_adjustment"):
            return self._maintenance_plan_adjustment(extra, horizon=str(extra.get("horizon") or "M1"))
        if feature_name == "monthly_utilization_band":
            return "mid_band_balanced"
        if feature_name == "restocking_rhythm_monthly":
            return self._restocking_rhythm_monthly(row)
        if feature_name == "holiday_demand_delta_monthly":
            return self._holiday_demand_delta_monthly(row=row, extra=extra)
        if feature_name == "refinery_inventory_monthly":
            return self._refinery_inventory_monthly(row)
        if feature_name == "main_company_inventory_monthly":
            return self._main_company_inventory_monthly(row)
        if feature_name == "social_inventory_cycle_position":
            return self._social_inventory_cycle_position(row)
        if feature_name == "market_sentiment_monthly":
            return self._market_sentiment_monthly(extra)
        return self._row_value(row, feature_name)

    def _parse_observation_date(self, value: Any) -> date | None:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        if isinstance(value, numbers.Real):
            magnitude = abs(float(value))
            unit = "ns"
            if magnitude < 10_000_000_000:
                unit = "s"
            elif magnitude < 10_000_000_000_000:
                unit = "ms"
            elif magnitude < 10_000_000_000_000_000:
                unit = "us"
            try:
                return pd.to_datetime(value, unit=unit).date()
            except Exception:
                return None
        try:
            return pd.Timestamp(value).date()
        except Exception:
            return None

    def _cdu_utilization_not_new_for_score(self, *, row: pd.Series, extra: dict[str, Any]) -> bool:
        as_of_raw = extra.get("as_of_date")
        observation_raw = self._row_value(row, "shandong_cdu_utilization_observation_date")
        as_of_date = self._parse_observation_date(as_of_raw)
        observation_date = self._parse_observation_date(observation_raw)
        if as_of_date is None or observation_date is None:
            return False
        expected_date = as_of_date - timedelta(days=1)
        if observation_date != expected_date:
            return True
        change = self._safe_float(self._row_value(row, "shandong_cdu_utilization_wow_pct"))
        if change is not None:
            return abs(change) < 1e-9
        current_value = self._safe_float(self._row_value(row, "shandong_cdu_utilization_weekly"))
        previous_value = self._safe_float(self._row_value(row, "shandong_cdu_utilization_previous_value"))
        if current_value is None or previous_value is None:
            return True
        return abs(current_value - previous_value) < 1e-9

    def _unchanged_score_gate(self, *, feature_name: str, row: pd.Series, extra: dict[str, Any] | None = None) -> bool:
        if feature_name in {
            "shandong_cdu_utilization_weekly",
            "shandong_cdu_utilization_percentile_weekly",
            "shandong_cdu_utilization_percentile_monthly",
        }:
            if self._cdu_utilization_not_new_for_score(row=row, extra=extra or {}):
                return True
        if feature_name == "shandong_product_inventory_percentile_weekly":
            product_code = str((extra or {}).get("product_code") or "").upper()
            if product_code == "DIESEL_0":
                change = self._safe_float(self._row_value(row, "shandong_diesel_product_inventory_change_weekly"))
                return change is None or abs(change) < 1e-9
            change = self._safe_float(self._row_value(row, "shandong_product_inventory_change_weekly"))
            return change is None or abs(change) < 1e-9
        if feature_name == "refinery_inventory_monthly":
            change = self._safe_float(self._row_value(row, "shandong_refinery_inventory_change_weekly"))
            return change is None or abs(change) < 1e-9
        if feature_name == "main_company_inventory_monthly":
            change = self._safe_float(self._row_value(row, "shandong_main_company_inventory_change_weekly"))
            return change is None or abs(change) < 1e-9
        return False

    def _resolve_brent_forecast_change(self, feature_name: str, *, extra: dict[str, Any]) -> dict[str, Any] | None:
        horizons_by_feature = {
            "brent_change_usd_d1": ["D1"],
            "brent_change_usd_d3": ["D3", "W1"],
            "brent_change_usd_w1": ["W1"],
            "brent_change_usd_mom": ["M1", "W4"],
        }
        target_horizons = horizons_by_feature.get(feature_name)
        if not target_horizons:
            return None

        report_payload = extra.get("report_payload") or {}
        signals = report_payload.get("signals") or {}
        if target_horizons == ["D1"]:
            daily = signals.get("daily_forecast") or {}
            point = self._safe_float(daily.get("point_value"))
            settlement = self._safe_float(signals.get("brent_settlement"))
            if point is not None and settlement is not None:
                return {
                    "value": point - settlement,
                    "source": "brent_daily_report",
                    "note": "daily_point_minus_report_settlement",
                }
            return {
                "value": None,
                "source": "brent_daily_report",
                "note": "missing_daily_point_or_settlement",
            }

        forecasts = signals.get("horizon_forecasts") or {}
        settlement = self._safe_float(signals.get("brent_settlement"))
        for target_horizon in target_horizons:
            forecast = forecasts.get(target_horizon) or {}
            point = self._safe_float(forecast.get("point_value"))
            if point is not None and settlement is not None:
                return {
                    "value": point - settlement,
                    "source": "brent_daily_report",
                    "note": f"{target_horizon}_point_minus_report_settlement",
                }
            change = self._safe_float(forecast.get("change_usd"))
            if change is not None:
                return {
                    "value": change,
                    "source": "brent_daily_report",
                    "note": forecast.get("change_source") or target_horizon,
                }
        return None

    def _row_value(self, row: pd.Series, column: str) -> Any:
        try:
            value = row.get(column)
        except Exception:
            return None
        if value is None or pd.isna(value):
            return None
        return float(value) if isinstance(value, (int, float)) else value

    def _safe_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _sentiment_label(self, extra: dict[str, Any]) -> str:
        sentiment = extra.get("trade_sentiment") or {}
        if isinstance(sentiment, dict) and sentiment.get("label") in {
            "bullish_active",
            "neutral_flat",
            "bearish_selling",
        }:
            return str(sentiment["label"])
        items = extra.get("refined_news_items") or []
        if not items:
            return "neutral_flat"
        positive_words = ("挺价", "推涨", "补货", "去库", "停工", "限产", "需求回暖", "上调", "走强")
        negative_words = ("促销", "让利", "降价", "下调", "累库", "出货不畅", "供应增加", "需求偏弱", "回落")
        positive = 0
        negative = 0
        for item in items[:20]:
            text = " ".join(
                str(item.get(key) or "") for key in ("headline", "title", "summary", "content")
            )
            positive += sum(1 for word in positive_words if word in text)
            negative += sum(1 for word in negative_words if word in text)
        if positive > negative:
            return "bullish_active"
        if negative > positive:
            return "bearish_selling"
        return "neutral_flat"

    def _refinery_load_news_adjustment(self, extra: dict[str, Any]) -> float:
        items = extra.get("refined_news_items") or []
        score = 0.0
        for item in items[:20]:
            text = " ".join(
                str(item.get(key) or "") for key in ("headline", "title", "summary", "content")
            )
            if any(word in text for word in ("停工", "检修", "降负", "限产")):
                score += 1.5
            if any(word in text for word in ("复工", "提负", "开工提升", "供应增加")):
                score -= 1.5
        return _clip(score, -5.0, 5.0)

    def _inventory_trend(self, row: pd.Series) -> str:
        gasoline_inventory_change = self._safe_float(self._row_value(row, "shandong_gasoline_inventory_change_mom"))
        if gasoline_inventory_change is not None:
            if gasoline_inventory_change <= -1.0:
                return "low_and_drawing"
            if gasoline_inventory_change >= 1.0:
                return "high_and_building"
            return "stable_mid"
        sales_change = self._safe_float(self._row_value(row, "sales_change_1w")) or 0.0
        shipments_change = self._safe_float(self._row_value(row, "shipments_change_1w")) or 0.0
        combined = sales_change + shipments_change
        if combined > 0.05:
            return "low_and_drawing"
        if combined < -0.05:
            return "high_and_building"
        return "stable_mid"

    def _refinery_inventory_monthly(self, row: pd.Series) -> str:
        gasoline_inventory_change = self._safe_float(self._row_value(row, "shandong_gasoline_inventory_change_mom"))
        if gasoline_inventory_change is None:
            return "flat"
        if gasoline_inventory_change <= -1.0:
            return "drawing"
        if gasoline_inventory_change >= 1.0:
            return "building"
        return "flat"

    def _main_company_inventory_monthly(self, row: pd.Series) -> str:
        inventory_change = self._safe_float(self._row_value(row, "shandong_main_company_inventory_change_mom"))
        if inventory_change is None:
            return "flat"
        if inventory_change <= -1.0:
            return "drawing"
        if inventory_change >= 1.0:
            return "building"
        return "flat"

    def _social_inventory_cycle_position(self, row: pd.Series) -> str:
        gasoline_capacity_rate = self._safe_float(
            self._row_value(row, "shandong_gasoline_inventory_capacity_rate")
        )
        if gasoline_capacity_rate is None:
            return "balanced"
        if gasoline_capacity_rate <= 35.0:
            return "low_inventory_restock_room"
        if gasoline_capacity_rate >= 45.0:
            return "high_inventory_pressure"
        return "balanced"

    def _price_window_expectation(self, row: pd.Series) -> str | None:
        expected_adjustment = self._safe_float(self._row_value(row, "price_adjustment_expected_yuan"))
        if expected_adjustment is None:
            return None
        if expected_adjustment > 50.0:
            return "up_adjustment_expected"
        if expected_adjustment < -50.0:
            return "down_adjustment_expected"
        return "neutral"

    def _restocking_rhythm_monthly(self, row: pd.Series) -> str | None:
        change = self._safe_float(self._row_value(row, "restocking_rhythm_monthly_change"))
        if change is None:
            return None
        if change >= 5.0:
            return "active_restocking"
        if change <= -5.0:
            return "reduced_restocking"
        return "stable_small_lots"

    def _holiday_demand_delta_monthly(self, *, row: pd.Series, extra: dict[str, Any]) -> str:
        explicit_delta = self._first_numeric_row_value(
            row,
            ["holiday_days_delta_monthly", "next_month_holiday_delta", "holiday_count_delta_m1"],
        )
        if explicit_delta is not None:
            return self._holiday_delta_label(explicit_delta)
        current_count = self._first_numeric_row_value(
            row,
            ["current_month_holiday_count", "holiday_days_current_month"],
        )
        next_count = self._first_numeric_row_value(
            row,
            ["next_month_holiday_count", "holiday_days_next_month"],
        )
        if current_count is not None and next_count is not None:
            return self._holiday_delta_label(next_count - current_count)
        as_of = extra.get("as_of_date")
        target_date = as_of if isinstance(as_of, date) else date.today()
        next_month = self._add_months(target_date, 1)
        return self._holiday_delta_label(
            self._holiday_count_for_month(next_month.year, next_month.month)
            - self._holiday_count_for_month(target_date.year, target_date.month)
        )

    def _holiday_delta_label(self, delta: float) -> str:
        if delta > 0:
            return "more_holidays"
        if delta < 0:
            return "fewer_holidays"
        return "unchanged"

    def _holiday_count_for_month(self, year: int, month: int) -> int:
        return sum(1 for day in CHINA_PUBLIC_HOLIDAY_DATES_2026 if day.year == year and day.month == month)

    def _market_sentiment_monthly(self, extra: dict[str, Any]) -> str:
        sentiment = extra.get("monthly_market_sentiment") or {}
        if isinstance(sentiment, dict) and sentiment.get("label") in {
            "peak_season_bullish",
            "neutral",
            "bearish",
        }:
            return str(sentiment["label"])
        return None

    def _first_numeric_row_value(self, row: pd.Series, columns: list[str]) -> float | None:
        for column in columns:
            value = self._safe_float(self._row_value(row, column))
            if value is not None:
                return value
        return None


    def _maintenance_plan_adjustment(self, extra: dict[str, Any], *, horizon: str) -> float:
        label = self._maintenance_plan_label(extra, horizon=horizon)
        if label == "concentrated_maintenance_supply_tight":
            return 5.0
        if label == "restart_and_supply_surplus":
            return -5.0
        return 0.0

    def _maintenance_plan_label(self, extra: dict[str, Any], *, horizon: str) -> str | None:
        plan = extra.get("oilchem_maintenance_plan") or {}
        if not isinstance(plan, dict) or not plan:
            return None
        horizon_code = str(horizon).upper()
        horizon_key = {"D1": "d1", "D3": "d3", "W1": "w1"}.get(horizon_code, "m1")
        if str(horizon).upper() == "M1":
            label = plan.get("m1_effective_capacity_label")
            if label in {"concentrated_maintenance_supply_tight", "restart_and_supply_surplus", "stable_load"}:
                return str(label)
            active_capacity = self._safe_float(plan.get("m1_active_capacity"))
            active_count = self._safe_float(plan.get("m1_active_count"))
            if active_capacity is None and active_count is None:
                return None
            if (active_capacity or 0.0) > 0 or (active_count or 0.0) > 0:
                return "concentrated_maintenance_supply_tight"
            return "stable_load"
        start_capacity = self._safe_float(plan.get(f"{horizon_key}_start_capacity"))
        end_capacity = self._safe_float(plan.get(f"{horizon_key}_end_capacity"))
        active_capacity = self._safe_float(plan.get(f"{horizon_key}_active_capacity"))
        active_count = self._safe_float(plan.get(f"{horizon_key}_active_count"))
        if start_capacity is None and end_capacity is None:
            start_capacity = self._safe_float(plan.get("next_30d_start_capacity"))
            end_capacity = self._safe_float(plan.get("next_30d_end_capacity"))
        if start_capacity is None and end_capacity is None and active_capacity is None and active_count is None:
            return None
        net_tightening = (start_capacity or 0.0) - (end_capacity or 0.0)
        if net_tightening > 0 or (active_capacity or 0.0) > 0 or (active_count or 0.0) > 0:
            return "concentrated_maintenance_supply_tight"
        if net_tightening < 0:
            return "restart_and_supply_surplus"
        return "stable_load"
