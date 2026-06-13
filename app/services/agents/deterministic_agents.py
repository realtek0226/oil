from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from app.models.common import AgentClaim


class BaseDeterministicAgent:
    name = "base_agent"
    max_score = 100.0

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        raise NotImplementedError


class CrudeCostAgent(BaseDeterministicAgent):
    name = "crude_cost_agent"
    max_score = 65.0

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        horizon = _horizon(extra)
        brent_change = _report_forecast_change(extra, horizon)
        if brent_change is None:
            brent_change = _first_float(row, _brent_fallback_columns(horizon))
        brent_score = (
            0.0
            if brent_change is None
            else _bucket_score(
                brent_change,
                [
                    (3, None, 55),
                    (2, 3, 42),
                    (1, 2, 28),
                    (0.5, 1, 14),
                    (-0.5, 0.5, 0),
                    (-1, -0.5, -14),
                    (-2, -1, -28),
                    (-3, -2, -42),
                    (None, -3, -55),
                ],
            )
        )
        crack_score = 0.0
        crack_pct = _first_float(row, ["gasoline_crack_percentile"])
        mtbe_change = _first_float(row, ["mtbe_change_3d"])
        naphtha_change = _first_float(row, ["naphtha_change_3d"])
        blend_score = (
            _clip(((mtbe_change or 0.0) + (naphtha_change or 0.0)) / 60.0 * 10.0, -10, 10)
            if mtbe_change is not None or naphtha_change is not None
            else 0.0
        )
        score = _clip(brent_score + crack_score + blend_score, -100, 100)
        evidence = [
            f"Brent预测/结算变化 {brent_change:.2f} 美元，对应成本分 {brent_score:.1f}"
            if brent_change is not None
            else "Brent预测/结算变化缺失，成本分按0处理",
        ]
        if mtbe_change is not None or naphtha_change is not None:
            evidence.append(
                f"MTBE 3日变化 {_format_value(mtbe_change)}，石脑油3日变化 {_format_value(naphtha_change)}"
            )
        if crack_pct is not None:
            evidence.append(f"汽油裂解价差分位 {_format_value(crack_pct)}，仅展示不参与打分")
        return _claim(
            self.name,
            score,
            f"成本端{_direction_text(score)}",
            evidence,
            {"brent_change_usd": brent_change, "gasoline_crack_percentile": crack_pct},
            max_score=self.max_score,
        )


class MarketStructureAgent(BaseDeterministicAgent):
    name = "market_structure_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        regions = [
            ("华东", "sd_vs_east_china_spread"),
            ("华北", "sd_vs_north_china_spread"),
            ("华南", "sd_vs_south_china_spread"),
            ("华中", "sd_vs_central_china_spread"),
            ("西北", "sd_vs_northwest_spread"),
            ("西南", "sd_vs_southwest_spread"),
            ("东北", "sd_vs_northeast_spread"),
        ]
        target_minus_sd_values: list[float] = []
        evidence: list[str] = []
        for label, column in regions:
            sd_minus_target = _safe_float(row.get(column))
            if sd_minus_target is None:
                continue
            target_minus_sd = -sd_minus_target
            target_minus_sd_values.append(target_minus_sd)
            evidence.append(f"{label}-山东价差 {target_minus_sd:.0f} 元/吨")
        avg_spread = sum(target_minus_sd_values) / len(target_minus_sd_values) if target_minus_sd_values else None
        spread_score = 0.0 if avg_spread is None else _clip(avg_spread / 120.0 * 65.0, -65, 65)
        sd_cn_spread = _safe_float(row.get("sd_cn_spread"))
        national_score = 0.0 if sd_cn_spread is None else _clip((-sd_cn_spread) / 90.0 * 20.0, -20, 20)
        price_momentum = _first_float(row, ["gas_price_change_3d", "gas_price_change_1d"])
        momentum_score = 0.0 if price_momentum is None else _clip(price_momentum / 80.0 * 15.0, -15, 15)
        score = _clip(spread_score + national_score + momentum_score, -100, 100)
        if not evidence:
            evidence.append("区域价格数据不足，市场结构按中性处理")
        return _claim(
            self.name,
            score,
            f"区域结构{_direction_text(score)}",
            evidence[:5],
            {
                "avg_target_minus_shandong_spread": avg_spread,
                "sd_cn_spread": sd_cn_spread,
                "gas_price_change": price_momentum,
            },
        )


class SupplyAgent(BaseDeterministicAgent):
    name = "supply_inventory_agent"
    max_score = 62.0

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        utilization_pct = _first_float(
            row,
            ["shandong_cdu_utilization_percentile_weekly", "shandong_cdu_utilization_percentile_monthly"],
        )
        inventory_pct = None
        utilization_change = _first_float(row, ["shandong_cdu_utilization_wow_pct", "crude_run_change_1w"])
        refining_profit = _safe_float(row.get("sd_refining_profit"))
        utilization_score = _percentile_inverse_score(utilization_pct, 40.0)
        inventory_score = 0.0
        if utilization_change is None or abs(utilization_change) < 0.01:
            utilization_change_score = 0.0
        else:
            utilization_change_score = _clip(-utilization_change / 5.0 * 12.0, -12, 12)
        profit_score = 0.0 if refining_profit is None else _clip(-refining_profit / 600.0 * 10.0, -10, 10)
        score = _clip(utilization_score + inventory_score + utilization_change_score + profit_score, -100, 100)
        evidence = [
            f"开工率分位 {utilization_pct:.1f}%" if utilization_pct is not None else "开工率分位缺失",
            f"开工变化 {utilization_change:.2f}" if utilization_change is not None else "开工变化缺失",
        ]
        if refining_profit is not None:
            evidence.append(f"山东炼油利润 {refining_profit:.1f} 元/吨")
        return _claim(
            self.name,
            score,
            f"供给库存{_direction_text(score)}",
            evidence,
            {
                "utilization_percentile": utilization_pct,
                "inventory_total_percentile": None,
                "utilization_change": utilization_change,
                "refining_profit": refining_profit,
            },
            max_score=self.max_score,
        )


class DemandAgent(BaseDeterministicAgent):
    name = "demand_seasonality_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        horizon = _horizon(extra)
        ratio_column = {
            "D1": "sales_production_ratio_d1",
            "D3": "sales_production_ratio_d3_avg",
            "W1": "sales_production_ratio_w1_avg",
            "M1": "sales_production_ratio_monthly_avg",
        }.get(horizon, "sales_production_ratio_d1")
        ratio = _safe_float(row.get(ratio_column))
        if ratio is None and horizon == "D1":
            ratio = _safe_float(row.get("sales_production_ratio_w1_avg"))
        ratio_score = _bucket_score(
            ratio,
            [
                (110, None, 60),
                (100, 110, 36),
                (95, 100, 22),
                (90, 95, 10),
                (85, 90, 0),
                (70, 85, -34),
                (None, 70, -60),
            ],
        )
        ratio_change = _safe_float(row.get("sales_production_ratio_monthly_change"))
        rhythm_score = 0.0 if ratio_change is None else _clip(ratio_change / 12.0 * 18.0, -18, 18)
        season_score = _season_score(extra.get("as_of_date"), horizon)
        holiday_score = _holiday_score(extra.get("as_of_date"), horizon)
        score = _clip(ratio_score + rhythm_score + season_score + holiday_score, -100, 100)
        evidence = [
            f"{horizon}产销率口径 {ratio_column}={ratio:.1f}%" if ratio is not None else f"{horizon}产销率缺失",
            f"月度产销率变化 {ratio_change:.1f}" if ratio_change is not None else "月度产销率变化缺失",
            f"季节性修正 {season_score:.1f}，节假日修正 {holiday_score:.1f}",
        ]
        return _claim(
            self.name,
            score,
            f"需求季节{_direction_text(score)}",
            evidence,
            {
                "sales_production_ratio": ratio,
                "ratio_column": ratio_column,
                "monthly_ratio_change": ratio_change,
                "season_score": season_score,
                "holiday_score": holiday_score,
            },
        )


class RefinedOilNewsAgent(BaseDeterministicAgent):
    name = "refined_oil_news_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        if extra.get("enable_refined_news") is False:
            return _claim(
                self.name,
                0.0,
                "成品油资讯中性",
                ["成品油资讯开关已关闭"],
                {"llm_labels": {}, "label": "neutral_flat", "trader_mindset": "neutral", "quote_behavior": "stable"},
            )
        refined_labels = extra.get("refined_news_labels") or {}
        labels = refined_labels or extra.get("trade_sentiment") or {}
        has_refined_label = bool(refined_labels.get("deal_activity") or refined_labels.get("label"))
        has_any_structured_label = bool(labels.get("deal_activity") or labels.get("label"))
        if not has_any_structured_label:
            raw_signal = self._raw_news_signal(
                extra.get("refined_news_items") or [],
                as_of_date=extra.get("as_of_date"),
            )
            if raw_signal is not None:
                return _claim(
                    self.name,
                    raw_signal["score"],
                    f"成品油资讯{_direction_text(raw_signal['score'])}",
                    raw_signal["evidence"],
                    {
                        "llm_labels": {},
                        "label": raw_signal["label"],
                        "trader_mindset": raw_signal["trader_mindset"],
                        "quote_behavior": raw_signal["quote_behavior"],
                        "raw_news_score": raw_signal["score"],
                        "raw_news_count": raw_signal["count"],
                    },
                )
        label = str(labels.get("deal_activity") or labels.get("label") or "neutral_flat")
        mindset = str(labels.get("trader_mindset") or "neutral")
        quote_behavior = str(labels.get("quote_behavior") or "stable")
        inferred_reason = ""
        if label == "neutral_flat" and not has_refined_label:
            ratio = _safe_float(row.get("sales_production_ratio_d1"))
            gas_change_1d = _safe_float(row.get("gas_price_change_1d")) or 0.0
            gas_change_3d = _safe_float(row.get("gas_price_change_3d")) or 0.0
            if ratio is not None and ratio < 70.0 and (gas_change_1d >= 80.0 or gas_change_3d >= 100.0):
                label = "bearish_selling"
                mindset = "bearish"
                quote_behavior = "discount"
                inferred_reason = "急涨后产销率偏弱，成交验证不足"
            elif ratio is not None and ratio > 105.0 and (gas_change_1d <= -60.0 or gas_change_3d <= -90.0):
                label = "bullish_active"
                mindset = "bullish"
                quote_behavior = "firm"
                inferred_reason = "急跌后产销率偏强，补库支撑增强"
        label_score = {
            "bullish_active": 70,
            "active": 70,
            "neutral_flat": 0,
            "flat": 0,
            "bearish_selling": -70,
            "weak": -70,
        }.get(label, 0)
        mindset_score = {"bullish": 18, "neutral": 0, "bearish": -18}.get(mindset, 0)
        quote_score = {"raise": 12, "firm": 8, "stable": 0, "discount": -8, "cut": -12}.get(quote_behavior, 0)
        score = _clip(label_score + mindset_score + quote_score, -100, 100)
        reason = inferred_reason or str(labels.get("reason") or labels.get("evidence") or "成品油资讯标签不足")
        evidence = [f"成交标签 {label}", f"贸易商心态 {mindset}", f"报价行为 {quote_behavior}", reason[:80]]
        return _claim(
            self.name,
            score,
            f"成品油资讯{_direction_text(score)}",
            evidence,
            {"llm_labels": labels, "label": label, "trader_mindset": mindset, "quote_behavior": quote_behavior},
        )

    def _raw_news_signal(self, items: list[dict[str, Any]], *, as_of_date: Any) -> dict[str, Any] | None:
        if not items:
            return None
        as_of = pd.to_datetime(as_of_date, errors="coerce")
        total = 0.0
        evidence: list[str] = []
        count = 0
        for item in items[:10]:
            text = " ".join(
                str(item.get(key) or "")
                for key in ("direction_hint", "headline", "title", "summary", "content")
            )
            direction = 0
            if str(item.get("direction_hint") or "").lower() in {"bullish_refined", "bullish", "up"}:
                direction = 1
            elif str(item.get("direction_hint") or "").lower() in {"bearish_refined", "bearish", "down"}:
                direction = -1
            elif any(word in text for word in ("上调", "推涨", "挺价", "抢货", "成交活跃")):
                direction = 1
            elif any(word in text for word in ("下调", "让利", "抛货", "成交转弱", "出货承压")):
                direction = -1
            if direction == 0:
                continue

            major_score = _safe_float(item.get("major_score"))
            base_score = (major_score if major_score is not None else 3.0) * 10.0
            publish_time = pd.to_datetime(item.get("publish_time") or item.get("publish_date"), errors="coerce")
            recency_weight = 1.0
            if not pd.isna(as_of) and not pd.isna(publish_time):
                days = max(0, int((as_of.normalize() - publish_time.normalize()).days))
                if days <= 1:
                    recency_weight = 1.0
                elif days <= 3:
                    recency_weight = 0.7
                elif days <= 7:
                    recency_weight = 0.4
                else:
                    recency_weight = 0.1
            total += direction * base_score * recency_weight
            count += 1
            title = str(item.get("headline") or item.get("title") or "成品油资讯").strip()
            evidence.append(f"{title[:40]}，新闻衰减权重 {recency_weight:.1f}")

        if count == 0:
            return None
        score = _clip(total, -100, 100)
        if score > 0:
            label, mindset, quote_behavior = "bullish_active", "bullish", "raise"
        elif score < 0:
            label, mindset, quote_behavior = "bearish_selling", "bearish", "cut"
        else:
            label, mindset, quote_behavior = "neutral_flat", "neutral", "stable"
        return {
            "score": score,
            "label": label,
            "trader_mindset": mindset,
            "quote_behavior": quote_behavior,
            "count": count,
            "evidence": evidence[:4] or ["原始成品油资讯未识别出方向"],
        }


class ShandongSpotJumpAgent(BaseDeterministicAgent):
    name = "shandong_spot_jump_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        labels = extra.get("refined_news_labels") or extra.get("trade_sentiment") or {}
        components: list[dict[str, Any]] = []
        score = 0.0
        hard_signal_hit = False

        refinery_quote_change = _first_float(
            row,
            [
                "sd_refinery_quote_change_median",
                "shandong_refinery_quote_change_median",
                "refinery_quote_change_yuan",
                "sd_refinery_price_adjustment_yuan",
            ],
        )
        if refinery_quote_change is not None:
            component = _change_component(refinery_quote_change, 80, 50, 30, "炼厂报价调整")
            score += component["score"]
            components.append(component)
            hard_signal_hit = hard_signal_hit or abs(float(component.get("score") or 0.0)) > 0.0

        deal_price_change = _first_float(
            row,
            [
                "sd_actual_deal_price_change",
                "shandong_actual_deal_price_change",
                "sd_deal_center_change",
                "actual_transaction_price_change",
            ],
        )
        if deal_price_change is not None:
            component = _change_component(deal_price_change, 80, 50, 30, "实际成交重心")
            score += component["score"]
            components.append(component)
            hard_signal_hit = hard_signal_hit or abs(float(component.get("score") or 0.0)) > 0.0

        ratio = _safe_float(row.get("sales_production_ratio_d1"))

        text = " ".join(
            str(labels.get(key) or "")
            for key in (
                "evidence",
                "inventory_signal_text",
                "supply_signal_text",
                "reason",
                "deal_activity",
                "trader_mindset",
                "quote_behavior",
            )
        )
        optional_spot_signals: dict[str, Any] = {}

        def _apply_optional_signal(
            key: str,
            *,
            hit: bool,
            words: tuple[str, ...],
            score_value: float,
            component: dict[str, Any],
        ) -> None:
            nonlocal score, hard_signal_hit
            matched_words = [word for word in words if word and word in text]
            is_hit = bool(hit or matched_words)
            optional_spot_signals[key] = {
                "status": "hit" if is_hit else "missing",
                "matched_words": matched_words,
                "score_if_hit": score_value,
            }
            if not is_hit:
                return
            score += score_value
            hard_signal_hit = hard_signal_hit or abs(float(score_value)) > 0.0
            components.append(component)

        _apply_optional_signal(
            "low_price_resource",
            hit=_flag_from_row(
                row,
                ["low_price_resource_swept", "sd_low_price_resource_swept", "low_price_resource_signal"],
            ),
            words=("低价资源减少", "低价扫空", "低价资源扫空", "低端上移", "低价惜售", "低端资源减少"),
            score_value=15,
            component={"name": "低价资源", "value": 1, "score": 15, "reason": "低价资源减少、扫空或低端上移"},
        )
        _apply_optional_signal(
            "sealed_or_reluctant_sale",
            hit=_flag_from_row(
                row,
                ["sealed_or_reluctant_sale", "sd_sealed_or_reluctant_sale", "refinery_sealed_sale", "refinery_reluctant_sale"],
            ),
            words=("封单", "惜售", "停售", "控量", "限量", "暂停报价"),
            score_value=15,
            component={"name": "封单惜售", "value": 1, "score": 15, "reason": "炼厂封单、惜售、控量或停售"},
        )
        _apply_optional_signal(
            "trader_grab_or_restock",
            hit=_flag_from_row(row, ["trader_grab_cargo", "sd_trader_grab_cargo", "trader_restock_active"]),
            words=("抢货", "集中补库", "接货积极", "询盘增加", "入市采购", "补货", "拿货积极"),
            score_value=15,
            component={"name": "贸易商心态", "value": 1, "score": 15, "reason": "贸易商抢货、补库或接货积极"},
        )
        _apply_optional_signal(
            "trader_dump_or_discount",
            hit=_flag_from_row(row, ["trader_dump_cargo", "sd_trader_dump_cargo", "trader_discount_sale"]),
            words=("让利", "抛货", "降价出货", "甩货", "高价抵触"),
            score_value=-15,
            component={"name": "贸易商心态", "value": -1, "score": -15, "reason": "贸易商抛货、让利或高价抵触"},
        )
        _apply_optional_signal(
            "shipment_strong",
            hit=_flag_from_row(row, ["shipment_strong", "sd_shipment_strong"]),
            words=("出货顺畅", "出货较好", "出货好转", "出货量大增", "成交放量"),
            score_value=10,
            component={"name": "出货节奏", "value": 1, "score": 10, "reason": "炼厂出货顺畅、好转或成交放量"},
        )
        _apply_optional_signal(
            "shipment_weak",
            hit=_flag_from_row(row, ["shipment_weak", "sd_shipment_weak"]),
            words=("出货承压", "出货清淡", "出货放缓", "成交清淡", "成交一般", "交投清淡", "出货不佳"),
            score_value=-10,
            component={"name": "出货节奏", "value": -1, "score": -10, "reason": "炼厂出货承压、放缓或成交清淡"},
        )

        gas_change_1d = _safe_float(row.get("gas_price_change_1d")) or 0.0
        gas_change_3d = _safe_float(row.get("gas_price_change_3d")) or 0.0
        quote_or_deal_push = any(
            value is not None and value >= 30.0
            for value in (refinery_quote_change, deal_price_change)
        )
        if ratio is not None and quote_or_deal_push:
            if ratio >= 110:
                score += 15
                hard_signal_hit = True
                components.append(
                    {
                        "name": "产销率验证",
                        "value": ratio,
                        "score": 15,
                        "reason": "炼厂推价或成交重心上移，且产销率高于110%，确认上涨有效",
                    }
                )
            elif ratio >= 100:
                score += 8
                hard_signal_hit = True
                components.append(
                    {
                        "name": "产销率验证",
                        "value": ratio,
                        "score": 8,
                        "reason": "炼厂推价或成交重心上移，且产销率高于100%，上涨信号获得部分确认",
                    }
                )
        if ratio is not None and ratio < 70.0 and gas_change_1d >= 80.0:
            score -= 20
            hard_signal_hit = True
            components.append(
                {
                    "name": "急涨成交验证不足",
                    "value": gas_change_1d,
                    "score": -20,
                    "reason": "当日急涨但产销率低于70%，追涨成交验证不足",
                }
            )
        elif ratio is not None and ratio < 70.0 and gas_change_3d >= 100.0 and gas_change_1d <= -10.0:
            score -= 20
            hard_signal_hit = True
            components.append(
                {
                    "name": "急涨后实质回落",
                    "value": gas_change_1d,
                    "score": -20,
                    "reason": "三日急涨后当日继续回落，且产销率低于70%",
                }
            )
        elif ratio is not None and ratio > 105.0 and (gas_change_1d <= -60.0 or gas_change_3d <= -90.0):
            score += 35
            hard_signal_hit = True
            components.append(
                {
                    "name": "急跌后补库",
                    "value": gas_change_1d or gas_change_3d,
                    "score": 35,
                    "reason": "急跌后产销率偏强，补库支撑增强",
                }
            )

        if not hard_signal_hit:
            score = 0.0
            components = []
        score = _clip(score, -100, 100)
        regime = _spot_jump_regime(score)
        jump_delta = _spot_jump_delta(score)
        evidence = [str(item["reason"]) for item in components[:5]] or ["未触发山东现货跳变信号"]
        return _claim(
            self.name,
            score,
            f"山东现货跳变{_direction_text(score)}",
            evidence,
            {
                "spot_strength_score": round(score, 4),
                "regime": regime,
                "jump_delta_d1": jump_delta,
                "components": components,
                "optional_spot_signals": optional_spot_signals,
                "ratio_usage": "validation_only",
                "basis": "只处理山东现货跳涨/跳跌日的点位修正，不参与综合智能体常规加权。",
            },
        )


class PolicyCycleAgent(BaseDeterministicAgent):
    name = "policy_cycle_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        expected_adjust = _first_float(
            row,
            [
                "price_adjustment_expected_yuan",
                "refined_oil_adjustment_expected_yuan",
                "oil_price_adjustment_forecast_yuan",
                "expected_price_adjustment_yuan_per_ton",
                "price_window_expected_adjustment",
            ],
        )
        days_to_window = _safe_float(row.get("days_to_next_window"))
        last_adjust = _safe_float(row.get("last_ceiling_adjust_delta"))
        expected_score = _bucket_score(
            expected_adjust,
            [
                (100, None, 70),
                (50, 100, 45),
                (0, 50, 20),
                (-50, 0, -20),
                (-100, -50, -45),
                (None, -100, -70),
            ],
        )
        if expected_adjust is None:
            expected_score = 0.0
        window_multiplier = 1.0
        if days_to_window is not None:
            if days_to_window <= 2:
                window_multiplier = 1.25
            elif days_to_window >= 8:
                window_multiplier = 0.75
        rollover_score = 0.0 if last_adjust is None else _clip(last_adjust / 300.0 * 12.0, -12, 12)
        score = _clip(expected_score * window_multiplier + rollover_score, -100, 100)
        evidence = [
            f"调价预测金额 {expected_adjust:.0f} 元/吨" if expected_adjust is not None else "调价预测金额缺失",
            f"距离调价窗口 {days_to_window:.0f} 个工作日" if days_to_window is not None else "调价窗口天数缺失",
            f"上轮调价 {last_adjust:.0f} 元/吨" if last_adjust is not None else "上轮调价幅度缺失",
        ]
        return _claim(
            self.name,
            score,
            f"政策周期{_direction_text(score)}",
            evidence,
            {"expected_adjustment_yuan": expected_adjust, "days_to_next_window": days_to_window, "last_adjust": last_adjust},
        )


class EventRiskAgent(BaseDeterministicAgent):
    name = "event_risk_agent"

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        labels = extra.get("event_risk_labels") or {}
        severity = str(labels.get("severity") or labels.get("risk_level") or "low").lower()
        direction = str(labels.get("direction") or "flat").lower()
        brent_change = abs(_safe_float(row.get("brent_change_1d")) or 0.0)
        severity_score = {
            "none": 0,
            "low": 10,
            "medium": 35,
            "high": 70,
            "extreme": 100,
        }.get(severity, 10)
        if brent_change >= 3 and severity_score < 35:
            severity_score = 35
        signed_score = severity_score if direction == "up" else -severity_score if direction == "down" else 0.0
        manual_review_required = bool(labels.get("manual_review_required")) or severity in {"high", "extreme"}
        risk_gate = {
            "risk_level": severity,
            "direction": direction,
            "manual_review_required": manual_review_required,
            "event_type": labels.get("event_type"),
            "impact_chain": labels.get("impact_chain"),
        }
        evidence = [
            f"事件风险等级 {severity}",
            f"事件方向 {direction}",
            str(labels.get("evidence") or labels.get("impact_chain") or "未识别到高等级事件")[:120],
        ]
        return _claim(
            self.name,
            signed_score,
            "事件风险门控",
            evidence,
            {"llm_labels": labels, "risk_gate": risk_gate, "brent_change_abs": brent_change},
        )


class BusinessScorecardAgent(BaseDeterministicAgent):
    name = "business_scorecard_agent"

    def __init__(self, scorecard_path: str) -> None:
        self.scorecard_path = scorecard_path
        self.config = self._load_config(scorecard_path)

    def analyze(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        horizon = _horizon(extra)
        scorecard = self._gasoline_scorecard()
        horizon_config = ((scorecard.get("horizons") or {}).get(horizon) or {})
        groups = horizon_config.get("factor_groups") or []
        total_score = 0.0
        group_results: list[dict[str, Any]] = []
        evidence: list[str] = []
        for group in groups:
            group_score = 0.0
            feature_results: list[dict[str, Any]] = []
            for feature in [*(group.get("features") or []), *(group.get("adjustments") or [])]:
                feature_name = str(feature.get("feature_name") or "")
                value = self._feature_value(feature_name, row, extra)
                score_value_feature = feature.get("score_value_feature")
                score_value = self._feature_value(str(score_value_feature), row, extra) if score_value_feature else value
                if self._unchanged_score_gate(feature_name, row):
                    feature_score, matched_label = 0.0, "unchanged_from_previous"
                else:
                    feature_score, matched_label = self._feature_score_detail(feature, score_value)
                group_score += feature_score
                feature_results.append(
                    {
                        "feature_name": feature_name,
                        "display_name": feature.get("display_name") or feature_name,
                        "method": feature.get("method"),
                        "value": value,
                        "score_value": score_value,
                        "score_value_feature": score_value_feature,
                        "matched_label": matched_label,
                        "score": round(feature_score, 4),
                        "status": "missing" if _is_missing_value(value) else "available",
                    }
                )
                if len(evidence) < 8:
                    evidence.append(f"{feature_name}={_format_value(value)} -> {feature_score:.1f}")
            cap = _safe_float(group.get("score_cap"))
            if cap is not None and cap > 0:
                group_score = _clip(group_score, -cap, cap)
            total_score += group_score
            group_results.append(
                {
                    "group_code": group.get("group_code"),
                    "display_name": group.get("display_name"),
                    "score": round(group_score, 4),
                    "score_cap": cap,
                    "features": feature_results,
                }
            )
        total_score = _clip(total_score, -100, 100)
        all_features = [feature for group in group_results for feature in group.get("features", [])]
        missing_features = [feature["feature_name"] for feature in all_features if feature.get("status") == "missing"]
        payload = {
            "scorecard_code": scorecard.get("scorecard_code"),
            "horizon": horizon,
            "groups": group_results,
            "source_document": self.config.get("source_document"),
            "version": self.config.get("version"),
            "data_quality": {
                "available_count": len(all_features) - len(missing_features),
                "missing_count": len(missing_features),
                "missing_fields": missing_features,
                "coverage_ratio": round((len(all_features) - len(missing_features)) / len(all_features), 4)
                if all_features
                else 1.0,
                "note": "缺失字段不做方向假设，按0分处理。",
            },
        }
        return _claim(
            self.name,
            total_score,
            f"业务基准{_direction_text(total_score)}",
            evidence or ["业务打分模型未匹配到可执行规则"],
            {"scorecard": payload},
        )

    def _load_config(self, scorecard_path: str) -> dict[str, Any]:
        path = Path(scorecard_path)
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _gasoline_scorecard(self) -> dict[str, Any]:
        for item in self.config.get("scorecards") or []:
            if item.get("scorecard_code") == "sd_gas92":
                return item
        return ((self.config.get("scorecards") or [{}])[0]) if self.config.get("scorecards") else {}

    def _feature_value(self, feature_name: str, row: pd.Series, extra: dict[str, Any]) -> Any:
        horizon = _horizon(extra)
        if feature_name.startswith("brent_change_usd"):
            return _report_forecast_change(extra, horizon)
        if feature_name.startswith("gasoline_crack_percentile"):
            return _safe_float(row.get("gasoline_crack_percentile"))
        if feature_name == "shandong_cdu_utilization_weekly":
            return _safe_float(row.get("sd_crude_run_weekly"))
        if feature_name == "shandong_cdu_utilization_percentile_weekly":
            return _safe_float(row.get("shandong_cdu_utilization_percentile_weekly"))
        if feature_name == "shandong_cdu_utilization_percentile_monthly":
            return _safe_float(row.get("shandong_cdu_utilization_percentile_monthly"))
        if feature_name == "trader_sentiment_label_d1" or feature_name == "trader_sentiment_label_d3":
            labels = extra.get("refined_news_labels") or extra.get("trade_sentiment") or {}
            return labels.get("deal_activity") or labels.get("label")
        if feature_name == "market_sentiment_monthly":
            labels = extra.get("monthly_market_sentiment") or {}
            return labels.get("label")
        if feature_name == "monthly_seasonality_phase":
            return _month_phase(extra.get("as_of_date"), horizon)
        if feature_name == "restocking_rhythm_monthly":
            change = _safe_float(row.get("sales_production_ratio_monthly_change"))
            if change is None:
                return None
            return "faster" if change > 3 else "slower" if change < -3 else "stable_small_lots"
        if feature_name == "holiday_demand_delta_monthly":
            return _holiday_delta_label(extra.get("as_of_date"), horizon)
        if feature_name in {"price_window_expectation_weekly", "price_window_expectation_monthly"}:
            return _first_float(
                row,
                [
                    "price_adjustment_expected_yuan",
                    "refined_oil_adjustment_expected_yuan",
                    "oil_price_adjustment_forecast_yuan",
                    "expected_price_adjustment_yuan_per_ton",
                    "price_window_expected_adjustment",
                ],
            )
        if feature_name == "refinery_inventory_monthly":
            return _safe_float(row.get("shandong_refinery_inventory_percentile_monthly"))
        if feature_name == "main_company_inventory_monthly":
            return _safe_float(row.get("shandong_main_company_inventory_percentile_monthly"))
        if feature_name == "shandong_product_inventory_percentile_weekly":
            return _safe_float(row.get("shandong_product_inventory_percentile_weekly"))
        if feature_name == "next_month_maintenance_plan":
            plan = extra.get("oilchem_maintenance_plan") or {}
            text = " ".join(str(plan.get(key) or "") for key in ("title", "summary", "content", "text"))
            if any(word in text for word in ("检修", "降负", "停工")):
                return "maintenance_increase"
            return "neutral" if text.strip() else None
        if feature_name.startswith("shandong_refinery_load_news_adjustment"):
            return None
        return _safe_float(row.get(feature_name))

    def _unchanged_score_gate(self, feature_name: str, row: pd.Series) -> bool:
        if feature_name in {
            "shandong_cdu_utilization_weekly",
            "shandong_cdu_utilization_percentile_weekly",
            "shandong_cdu_utilization_percentile_monthly",
        }:
            wow_pct = _safe_float(row.get("shandong_cdu_utilization_wow_pct"))
            if wow_pct is not None:
                return abs(wow_pct) < 1e-9
            change = _safe_float(row.get("crude_run_change_1w"))
            if change is not None:
                return abs(change) < 1e-9
        return False

    def _feature_score(self, feature: dict[str, Any], value: Any) -> float:
        score, _label = self._feature_score_detail(feature, value)
        return score

    def _feature_score_detail(self, feature: dict[str, Any], value: Any) -> tuple[float, str]:
        method = feature.get("method")
        if method == "bucket_score":
            numeric = _safe_float(value)
            if numeric is None:
                return 0.0, "missing"
            for rule in feature.get("rules") or []:
                lower = _safe_float(rule.get("min"))
                upper = _safe_float(rule.get("max"))
                if lower is not None and numeric < lower:
                    continue
                if upper is not None and numeric >= upper:
                    continue
                return float(rule.get("score") or 0.0), str(rule.get("label") or "matched")
            return 0.0, "unmatched"
        if method == "enum_score":
            label = str(value)
            return float((feature.get("rules") or {}).get(label, 0.0)), label
        if method == "bounded_numeric":
            numeric = _safe_float(value) or 0.0
            return _clip(numeric, float(feature.get("min", -100)), float(feature.get("max", 100))), "bounded_numeric"
        return 0.0, "unsupported_method"


def _claim(
    agent_name: str,
    score: float,
    summary: str,
    evidence: list[str],
    structured_payload: dict[str, Any] | None = None,
    max_score: float = 100.0,
) -> AgentClaim:
    score = _clip(score, -100, 100)
    payload = dict(structured_payload or {})
    scorecard_quality = (payload.get("scorecard") or {}).get("data_quality") if isinstance(payload.get("scorecard"), dict) else None
    payload.setdefault("data_quality", scorecard_quality or _data_quality_from_payload(payload))
    return AgentClaim(
        agent_name=agent_name,
        direction=_direction_from_score(score),
        confidence_label=_confidence_label(score),
        confidence_score=_confidence_score(score, max_score=max_score),
        summary=summary,
        evidence=evidence,
        numeric_signals={"score": round(score, 4), "max_score": round(float(max_score or 100.0), 4)},
        structured_payload=payload,
    )


def _horizon(extra: dict[str, Any]) -> str:
    return str(extra.get("horizon") or "D1").upper()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _data_quality_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    ignored_keys = {
        "components",
        "optional_spot_signals",
        "scorecard",
        "risk_gate",
        "llm_labels",
        "runtime_control",
        "basis",
    }
    available_fields: list[str] = []
    missing_fields: list[str] = []
    for key, value in payload.items():
        if key in ignored_keys or isinstance(value, (dict, list, tuple)):
            continue
        if _is_missing_value(value):
            missing_fields.append(key)
        else:
            available_fields.append(key)
    total = len(available_fields) + len(missing_fields)
    return {
        "available_count": len(available_fields),
        "missing_count": len(missing_fields),
        "missing_fields": missing_fields,
        "coverage_ratio": round(len(available_fields) / total, 4) if total else 1.0,
        "note": "缺失字段不做方向假设，按0分处理。",
    }


def _first_float(row: pd.Series, columns: list[str]) -> float | None:
    for column in columns:
        value = _safe_float(row.get(column))
        if value is not None:
            return value
    return None


def _bucket_score(value: Any, rules: list[tuple[Any, Any, Any]]) -> float:
    numeric = _safe_float(value)
    if numeric is None:
        return 0.0
    for min_value, max_value, score in rules:
        lower = _safe_float(min_value)
        upper = _safe_float(max_value)
        if lower is not None and numeric < lower:
            continue
        if upper is not None and numeric >= upper:
            continue
        return float(score or 0.0)
    return 0.0


def _change_component(value: float, high: float, medium: float, score: float, name: str) -> dict[str, Any]:
    if value >= high:
        return {"name": name, "value": value, "score": score, "reason": f"{name}上移超过{high:.0f}元/吨"}
    if value >= medium:
        return {"name": name, "value": value, "score": score * 0.65, "reason": f"{name}上移超过{medium:.0f}元/吨"}
    if value <= -high:
        return {"name": name, "value": value, "score": -score, "reason": f"{name}下移超过{high:.0f}元/吨"}
    if value <= -medium:
        return {"name": name, "value": value, "score": -score * 0.65, "reason": f"{name}下移超过{medium:.0f}元/吨"}
    return {"name": name, "value": value, "score": 0.0, "reason": f"{name}变化不足{medium:.0f}元/吨"}


def _flag_from_row(row: pd.Series, columns: list[str]) -> bool:
    for column in columns:
        value = row.get(column)
        if isinstance(value, bool):
            return value
        numeric = _safe_float(value)
        if numeric is not None:
            return numeric > 0
        text = str(value or "").strip()
        if text in {"是", "true", "True", "yes", "Y", "1"}:
            return True
    return False


def _spot_jump_regime(score: float) -> str:
    if score >= 80:
        return "strong_push_up"
    if score >= 60:
        return "push_up"
    if score <= -80:
        return "strong_selloff"
    if score <= -60:
        return "selloff"
    if score <= -35:
        return "weak_after_rally"
    if score >= 35:
        return "mild_strength"
    return "normal"


def _spot_jump_delta(score: float) -> float:
    if score >= 80:
        return 75.0
    if score >= 60:
        return 55.0
    if score >= 40:
        return 30.0
    if score <= -80:
        return -35.0
    if score <= -60:
        return -30.0
    if score <= -35:
        return -25.0
    return 0.0


def _percentile_inverse_score(percentile: float | None, cap: float) -> float:
    if percentile is None:
        return 0.0
    if percentile < 25:
        return cap
    if percentile < 45:
        return cap * 0.5
    if percentile <= 55:
        return 0.0
    if percentile <= 75:
        return -cap * 0.5
    return -cap


def _report_forecast_change(extra: dict[str, Any], horizon: str) -> float | None:
    report_payload = extra.get("report_payload") or {}
    signals = report_payload.get("signals") or {}
    if horizon == "D1":
        forecast = signals.get("daily_forecast") or {}
    else:
        forecast = (signals.get("horizon_forecasts") or {}).get(horizon) or {}
    point = _safe_float(forecast.get("point_value"))
    report_settlement = _safe_float(signals.get("brent_settlement"))
    if point is not None and report_settlement is not None:
        return point - report_settlement
    change_source = str(forecast.get("change_source") or "")
    forecast_change = None
    for key in ("change_usd", "settlement_change_usd", "change_vs_previous_settlement_usd"):
        forecast_change = _safe_float(forecast.get(key))
        if forecast_change is not None:
            break
    if forecast_change is not None and change_source != "daily_point_minus_realtime":
        return forecast_change
    return _safe_float(signals.get("brent_settlement_change_usd"))


def _brent_fallback_columns(horizon: str) -> list[str]:
    return {
        "D1": ["brent_change_1d"],
        "D3": ["brent_change_3d", "brent_change_1d"],
        "W1": ["brent_change_5d", "brent_change_3d"],
        "M1": ["brent_change_20d", "brent_change_5d"],
    }.get(horizon, ["brent_change_1d"])


def _season_score(as_of_date: Any, horizon: str) -> float:
    month = _target_month(as_of_date, horizon)
    if month in {5, 6, 7, 8}:
        return 14.0
    if month in {3, 4, 9}:
        return 7.0
    if month == 2:
        return -5.0
    if month in {1, 10, 11, 12}:
        return -10.0
    return 0.0


def _month_phase(as_of_date: Any, horizon: str) -> str:
    month = _target_month(as_of_date, horizon)
    if month in {5, 6, 7, 8}:
        return "peak"
    if month in {3, 4, 9}:
        return "secondary_peak"
    if month == 2:
        return "secondary_off"
    if month in {1, 10, 11, 12}:
        return "off"
    return "neutral"


def _holiday_score(as_of_date: Any, horizon: str) -> float:
    return {"increase": 6.0, "unchanged": 0.0, "decrease": -4.0}.get(_holiday_delta_label(as_of_date, horizon), 0.0)


def _holiday_delta_label(as_of_date: Any, horizon: str) -> str:
    month = _target_month(as_of_date, horizon)
    return "increase" if month in {1, 2, 4, 5, 6, 9, 10} else "unchanged"


def _target_month(as_of_date: Any, horizon: str) -> int:
    try:
        ts = pd.Timestamp(as_of_date)
    except Exception:
        ts = pd.Timestamp.today()
    if horizon == "M1":
        ts = ts + pd.DateOffset(months=1)
    return int(ts.month)


def _direction_from_score(score: float) -> str:
    if score > 5:
        return "up"
    if score < -5:
        return "down"
    return "flat"


def _direction_text(score: float) -> str:
    if score > 5:
        return "利多"
    if score < -5:
        return "利空"
    return "中性"


def _confidence_label(score: float) -> str:
    absolute = abs(score)
    if absolute >= 55:
        return "high"
    if absolute >= 20:
        return "medium"
    return "low"


def _confidence_score(score: float, *, max_score: float = 100.0) -> float:
    denominator = max(abs(float(max_score or 100.0)), 1.0)
    return round(_clip(0.35 + abs(score) / denominator * 0.45, 0.2, 0.85), 4)


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _format_value(value: Any) -> str:
    if _is_missing_value(value):
        return "-"
    numeric = _safe_float(value)
    if numeric is not None:
        return f"{numeric:.2f}"
    return str(value)
