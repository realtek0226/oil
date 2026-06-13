from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from app.clients.llm_client import LlmClient
from app.models.common import AgentClaim, PredictionResult
from app.services.agent_control import AgentControlService
from app.services.agents.deterministic_agents import (
    BusinessScorecardAgent,
    CrudeCostAgent,
    DemandAgent,
    EventRiskAgent,
    MarketStructureAgent,
    PolicyCycleAgent,
    RefinedOilNewsAgent,
    ShandongSpotJumpAgent,
    SupplyAgent,
)
from app.services.agents.llm_agents import build_llm_agent_claims
from app.services.market_dataset import (
    BARREL_TO_TON_RATIO,
    GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON,
    VAT_RATE,
    MarketDatasetService,
    PredictionContext,
)
from app.services.predictors.agent_judgement import (
    apply_judgement_confidence_penalty,
    build_agent_judge_claim,
    build_agent_judgement_review,
)
from app.services.predictors.advice_engine import build_driver_summary, build_outright_advice
from app.services.predictors.confidence_engine import build_reliability_score
from app.services.predictors.horizons import DEFAULT_HORIZONS, HorizonConfig, resolve_horizon_config
from app.services.predictors.llm_label_cache import LlmLabelCache
from app.services.predictors.llm_narrative import enrich_prediction_narrative


@dataclass(frozen=True)
class CalibrationResult:
    intercept: float
    slope: float
    rmse: float
    sample_size: int
    status: str = "ok"
    reason: str = ""


NON_CALIBRATABLE_AGENT_NAMES = {"refined_oil_news_agent", "event_risk_agent"}

OUTRIGHT_EXPERT_PRIOR_WEIGHTS: dict[str, float] = {
    "crude_cost_agent": 0.22,
    "supply_inventory_agent": 0.20,
    "demand_seasonality_agent": 0.18,
    "market_structure_agent": 0.16,
    "policy_cycle_agent": 0.12,
    "refined_oil_news_agent": 0.12,
    "shandong_spot_jump_agent": 0.0,
    "event_risk_agent": 0.0,
}

HORIZON_BASE_RANGE_HALF_WIDTH: dict[str, float] = {
    "D1": 50.0,
    "D3": 85.0,
    "W1": 150.0,
    "M1": 280.0,
}

LLM_LABEL_EXTRACTOR_VERSION = "2026-06-08-v1"


class ShandongGas92Predictor:
    def __init__(
        self,
        dataset_service: MarketDatasetService,
        llm_client: LlmClient,
        agent_control_service: AgentControlService,
        scorecard_path: str,
    ) -> None:
        self.dataset_service = dataset_service
        self.llm_client = llm_client
        self.agent_control_service = agent_control_service
        self.scope_key = "outright"
        self.business_scorecard_agent = BusinessScorecardAgent(scorecard_path=scorecard_path)
        self._trade_sentiment_cache: dict[str, dict[str, Any]] = {}
        self._monthly_sentiment_cache: dict[str, dict[str, Any]] = {}
        self._llm_label_cache = LlmLabelCache()
        self.agents = [
            CrudeCostAgent(),
            MarketStructureAgent(),
            SupplyAgent(),
            DemandAgent(),
            RefinedOilNewsAgent(),
            ShandongSpotJumpAgent(),
            PolicyCycleAgent(),
            EventRiskAgent(),
        ]

    def run_prediction(
        self,
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
            as_of_date=as_of_date,
            horizon=horizon,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
        )

    def run_multi_horizon_predictions(
        self,
        as_of_date: date | None = None,
        horizons: list[str] | None = None,
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
    ) -> list[PredictionResult]:
        as_of_date = as_of_date or date.today()
        context = self.dataset_service.build_context(as_of_date)
        return self.run_multi_horizon_predictions_from_context(
            context=context,
            as_of_date=as_of_date,
            horizons=horizons,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
        )

    def run_prediction_from_context(
        self,
        context: PredictionContext,
        as_of_date: date,
        horizon: str = "D1",
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
    ) -> PredictionResult:
        return self._predict_from_frame(
            feature_frame=context.feature_frame,
            current_row=context.current_row,
            as_of_date=as_of_date,
            horizon=horizon,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            report_payload=context.report_payload,
            news_items=context.news_items,
            refined_news_items=context.refined_news_items,
            policy_items=context.policy_items,
            mode="predict",
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
            refined_news_by_date=None,
            event_news_by_date=None,
            event_report_by_date=None,
            context_metadata=context.metadata,
        )

    def run_multi_horizon_predictions_from_context(
        self,
        context: PredictionContext,
        as_of_date: date,
        horizons: list[str] | None = None,
        use_llm_explainer: bool = True,
        scenario_text: str | None = None,
        enable_refined_news: bool = True,
        enable_event_risk: bool = True,
    ) -> list[PredictionResult]:
        selected_horizons = horizons or DEFAULT_HORIZONS
        return [
            self.run_prediction_from_context(
                context=context,
                as_of_date=as_of_date,
                horizon=horizon,
                use_llm_explainer=use_llm_explainer,
                scenario_text=scenario_text,
                enable_refined_news=enable_refined_news,
                enable_event_risk=enable_event_risk,
            )
            for horizon in selected_horizons
        ]

    def predict_from_frame(
        self,
        feature_frame: pd.DataFrame,
        as_of_date: date,
        refined_news_items: list[dict[str, Any]] | None = None,
        report_payload: dict[str, Any] | None = None,
        news_items: list[dict[str, Any]] | None = None,
        policy_items: list[dict[str, Any]] | None = None,
        enable_refined_news: bool = False,
        enable_event_risk: bool = False,
        refined_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_report_by_date: dict[date, dict[str, Any] | None] | None = None,
    ) -> PredictionResult:
        current_frame = feature_frame[feature_frame["date"] <= as_of_date]
        if current_frame.empty:
            raise RuntimeError(f"No feature row found for as_of_date={as_of_date}")
        return self._predict_from_frame(
            feature_frame=feature_frame,
            current_row=current_frame.iloc[-1],
            as_of_date=as_of_date,
            horizon="D1",
            use_llm_explainer=False,
            scenario_text=None,
            report_payload=report_payload,
            news_items=news_items or [],
            refined_news_items=refined_news_items or [],
            policy_items=policy_items or [],
            mode="backtest",
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
            refined_news_by_date=refined_news_by_date,
            event_news_by_date=event_news_by_date,
            event_report_by_date=event_report_by_date,
            context_metadata=None,
        )

    def _predict_from_frame(
        self,
        feature_frame: pd.DataFrame,
        current_row: pd.Series,
        as_of_date: date,
        horizon: str,
        use_llm_explainer: bool,
        scenario_text: str | None,
        report_payload: dict[str, Any] | None,
        news_items: list[dict[str, Any]],
        refined_news_items: list[dict[str, Any]],
        policy_items: list[dict[str, Any]],
        mode: str,
        enable_refined_news: bool,
        enable_event_risk: bool,
        refined_news_by_date: dict[date, list[dict[str, Any]]] | None,
        event_news_by_date: dict[date, list[dict[str, Any]]] | None,
        event_report_by_date: dict[date, dict[str, Any] | None] | None,
        context_metadata: dict[str, Any] | None,
    ) -> PredictionResult:
        horizon_config = resolve_horizon_config(horizon)
        context_metadata = dict(context_metadata or {})
        brent_report_quality = self._brent_report_quality(
            as_of_date=as_of_date,
            report_payload=report_payload,
        )
        if brent_report_quality["status"] != "fresh":
            existing_reason = str(context_metadata.get("market_data_reason") or "").strip()
            reason_parts = [existing_reason] if existing_reason else []
            reason_parts.append(str(brent_report_quality["status"]))
            context_metadata["market_data_reason"] = ";".join(reason_parts)
            context_metadata.setdefault("market_data_mode", "eta_with_input_warning")
        score_extra = {
            "as_of_date": as_of_date,
            "report_payload": report_payload,
            "news_items": news_items,
            "refined_news_items": refined_news_items,
            "policy_items": policy_items,
            "scenario_text": scenario_text,
            "mode": mode,
            "prediction_subject": "outright",
            "enable_refined_news": enable_refined_news,
            "enable_event_risk": enable_event_risk,
            "horizon": horizon_config.code,
            "oilchem_maintenance_plan": (context_metadata or {}).get("oilchem_maintenance_plan"),
            "oilchem_inventory": (context_metadata or {}).get("oilchem_inventory"),
            "brent_feature_settlement": self._float_or_none(current_row.get("brent_active_settlement")),
        }
        score_extra["trade_sentiment"] = self._build_trade_sentiment_signal(
            as_of_date=as_of_date,
            mode=mode,
            refined_news_items=refined_news_items,
            news_items=news_items,
            scenario_text=scenario_text,
        )
        score_extra["monthly_market_sentiment"] = self._build_monthly_market_sentiment_signal(
            as_of_date=as_of_date,
            mode=mode,
            refined_news_items=refined_news_items,
            news_items=news_items,
            scenario_text=scenario_text,
        )
        score_extra["refined_news_labels"] = self._build_refined_news_label_signal(
            as_of_date=as_of_date,
            mode=mode,
            refined_news_items=refined_news_items,
            scenario_text=scenario_text,
        )
        score_extra["event_risk_labels"] = self._build_event_risk_label_signal(
            as_of_date=as_of_date,
            mode=mode,
            news_items=news_items,
            report_payload=report_payload,
            scenario_text=scenario_text,
        )
        business_claim = self._score_business_scorecard(current_row, extra=score_extra)
        claims, score_value = self._score_row(
            current_row,
            extra=score_extra,
        )
        agent_claims = [business_claim, *claims]
        _, calibration_score_value = self._score_calibration_row(current_row, extra=score_extra)
        shared_scored_history = self._historical_scored_delta_frame(
            frame=feature_frame,
            as_of_date=as_of_date,
            horizon_config=horizon_config,
            refined_news_by_date=None,
            event_news_by_date=None,
            event_report_by_date=None,
            enable_refined_news=False,
            enable_event_risk=False,
        )
        agent_mapping = self._score_delta_mapping(
            feature_frame,
            as_of_date,
            horizon_config,
            score_column="agent_score",
            score_value=score_value,
            scored_history=shared_scored_history,
        )
        calibration = CalibrationResult(
            intercept=0.0,
            slope=0.0,
            rmse=float(agent_mapping["range_half_width"]),
            sample_size=int(agent_mapping["sample_size"]),
            status=str(agent_mapping["status"]),
            reason=str(agent_mapping["reason"]),
        )
        event_gate = self._build_event_gate(
            row=current_row,
            claims=claims,
            news_items=news_items,
            report_payload=report_payload,
        )

        current_price = float(current_row["sd_gas92_market"])
        point_adjustments = self._point_adjustments(
            row=current_row,
            horizon=horizon_config.code,
            event_gate=event_gate,
            score_extra=score_extra,
            claims=claims,
            base_predicted_delta=float(agent_mapping["predicted_delta"]),
        )
        pre_judge_predicted_delta = float(agent_mapping["predicted_delta"]) + sum(point_adjustments.values())
        pre_judge_direction = self._direction_from_delta(
            pre_judge_predicted_delta,
            threshold=horizon_config.direction_threshold,
        )
        agent_judgement = build_agent_judgement_review(
            claims=agent_claims,
            predicted_delta=pre_judge_predicted_delta,
            direction_label=pre_judge_direction,
            direction_threshold=horizon_config.direction_threshold,
        )
        judge_adjustment = float(agent_judgement.get("adjustment_delta") or 0.0)
        if not math.isclose(judge_adjustment, 0.0, abs_tol=0.0001):
            point_adjustments["agent_judge"] = judge_adjustment
        predicted_delta = pre_judge_predicted_delta + judge_adjustment
        point_value = current_price + predicted_delta
        business_score = float(business_claim.numeric_signals.get("standalone_score", 0.0))
        business_mapping = self._score_delta_mapping(
            feature_frame,
            as_of_date,
            horizon_config,
            score_column="business_scorecard_score",
            score_value=business_score,
            scored_history=shared_scored_history,
        )
        business_predicted_delta = float(business_mapping["predicted_delta"])
        business_point_value = current_price + business_predicted_delta
        current_crack_spread = self._calculate_gasoline_crack_spread(
            market_price=current_price,
            brent_price=self._float_or_none(current_row.get("brent_active_settlement")),
            cny_mid=self._resolve_cny_mid_from_row(current_row),
        )
        forecast_brent_for_crack = self._resolve_brent_point_for_crack(
            report_payload=report_payload,
            horizon=horizon_config.code,
            fallback_brent=self._float_or_none(current_row.get("brent_active_settlement")),
        )
        predicted_crack_spread = self._calculate_gasoline_crack_spread(
            market_price=point_value,
            brent_price=forecast_brent_for_crack,
            cny_mid=self._resolve_cny_mid_from_row(current_row),
        )
        risk_range_half_width = self._range_half_width(
            horizon=horizon_config.code,
            claims=claims,
            context_metadata=context_metadata,
            score_value=score_value,
            event_gate=event_gate,
        )
        if calibration.status in {"empirical", "merged_bucket", "cold_start"}:
            risk_range_half_width = max(float(risk_range_half_width), float(agent_mapping["range_half_width"]))
        risk_range_half_width += float(agent_judgement.get("range_extra_width") or 0.0)
        range_half_width = risk_range_half_width
        business_risk_range_half_width = float(business_mapping["range_half_width"])
        business_range_half_width = business_risk_range_half_width
        direction_label = self._direction_from_delta(predicted_delta, threshold=horizon_config.direction_threshold)
        business_direction_label = self._direction_from_delta(
            business_predicted_delta,
            threshold=horizon_config.direction_threshold,
        )
        probabilities = self._probabilities_from_score(calibration_score_value)
        confidence_label, confidence_score, confidence_components = build_reliability_score(
            claims=agent_claims,
            predicted_delta=predicted_delta,
            direction_label=direction_label,
            range_half_width=range_half_width,
            direction_threshold=horizon_config.direction_threshold,
            calibration_rmse=calibration.rmse,
            sample_size=calibration.sample_size,
            context_metadata=context_metadata,
        )
        confidence_label, confidence_score = apply_judgement_confidence_penalty(
            confidence_label,
            confidence_score,
            agent_judgement,
        )
        confidence_components["agent_judge_penalty"] = round(float(agent_judgement.get("confidence_penalty") or 0.0), 4)
        confidence_components["agent_judge_verdict"] = str(agent_judgement.get("display_label") or "")
        business_direction = self._build_business_direction(
            predicted_delta=predicted_delta,
            direction_label=direction_label,
            probabilities=probabilities,
            calibration=calibration,
            confidence_label=confidence_label,
            confidence_score=confidence_score,
            event_gate=event_gate,
        )

        raw_context = {
            "current_price": current_price,
            "predicted_delta": round(predicted_delta, 4),
            "current_gasoline_crack_spread": self._round_or_none(current_crack_spread),
            "predicted_gasoline_crack_spread": self._round_or_none(predicted_crack_spread),
            "gasoline_crack_formula": "92#市场价/1.13-消费税(2109.76)-Brent*吨桶比(6.77)*人民币汇率中间价",
            "gasoline_crack_formula_inputs": {
                "current_market_price": round(current_price, 4),
                "predicted_market_price": round(point_value, 4),
                "current_brent": self._round_or_none(current_row.get("brent_active_settlement")),
                "forecast_brent": self._round_or_none(forecast_brent_for_crack),
                "cny_mid": self._round_or_none(self._resolve_cny_mid_from_row(current_row)),
                "consumption_tax": GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON,
                "barrel_to_ton_ratio": BARREL_TO_TON_RATIO,
                "vat_rate": VAT_RATE,
            },
            "score_value": round(score_value, 4),
            "calibration_score_value": round(calibration_score_value, 4),
            "calibration_score_basis": "主预测点位使用可回放结构分进入分桶映射；资讯和事件参与解释、预警、风控降级及已落库标签打分。",
            "point_mapping": {
                **agent_mapping,
                "formula": "score -> market_state_bucket -> historical target_delta distribution; predicted_delta=P50 + point_adjustments",
            },
            "point_adjustments": {key: round(value, 4) for key, value in point_adjustments.items()},
            "agent_judgement": {
                **agent_judgement,
                "direction_before_review": pre_judge_direction,
                "direction_after_review": direction_label,
                "predicted_delta_after_review": round(predicted_delta, 4),
            },
            "core_range_half_width": round(range_half_width, 4),
            "risk_range_half_width": round(risk_range_half_width, 4),
            "risk_range_lower": round(point_value - risk_range_half_width, 2),
            "risk_range_upper": round(point_value + risk_range_half_width, 2),
            "range_basis": {
                "core_label": "经营参考区间",
                "risk_label": "经营风险扩展区间",
                "historical_error_available": calibration.status in {"empirical", "merged_bucket"},
                "reason": (
                    "点位来自同状态分桶历史涨跌分布的中位数；区间来自同桶历史分布、数据模式、方向分歧和事件风险。"
                    if calibration.status in {"empirical", "merged_bucket"}
                    else calibration.reason or "历史样本不足，点位使用冷启动专家分桶表，需继续积累样本。"
                ),
            },
            "historical_error_half_width": round(risk_range_half_width, 4),
            "historical_error_lower": round(point_value - risk_range_half_width, 2),
            "historical_error_upper": round(point_value + risk_range_half_width, 2),
            "probabilities": probabilities,
            "business_direction": business_direction,
            "event_gate": event_gate,
            "switches": {
                "enable_refined_news": enable_refined_news,
                "enable_event_risk": enable_event_risk,
            },
            "calibration": {
                "method": "historical_bucket_distribution_mapping",
                "range_half_width": round(calibration.rmse, 4),
                "sample_size": calibration.sample_size,
                "status": calibration.status,
                "reason": calibration.reason,
            },
            "confidence_components": confidence_components,
            "refined_news_count": len(refined_news_items),
            "prediction_news_cutoff": datetime.combine(as_of_date, datetime.min.time()).replace(hour=7).isoformat(),
            "refined_news_cutoff": datetime.combine(as_of_date, datetime.min.time()).replace(hour=7).isoformat(),
            "refined_news_source": refined_news_items[0].get("source") if refined_news_items else None,
            "refined_news_sources": sorted(
                {str(item.get("source")) for item in refined_news_items if item.get("source")}
            ),
            "refined_news_fulltext_count": sum(1 for item in refined_news_items if str(item.get("content") or "").strip()),
            "event_news_count": len(news_items),
            "event_news_cutoff": datetime.combine(as_of_date, datetime.min.time()).replace(hour=7).isoformat(),
            "event_news_sources": sorted({str(item.get("source")) for item in news_items if item.get("source")}),
            "trade_sentiment": score_extra.get("trade_sentiment"),
            "monthly_market_sentiment": score_extra.get("monthly_market_sentiment"),
            "llm_extracted_labels": {
                "refined_news": score_extra.get("refined_news_labels"),
                "event_risk": score_extra.get("event_risk_labels"),
            },
            "event_report_date": report_payload.get("report_date") if report_payload else None,
            "event_report_title": report_payload.get("title") if report_payload else None,
            "brent_daily_report_quality": brent_report_quality,
            "event_report_horizons": (
                report_payload.get("signals", {}).get("horizon_forecasts", {}) if report_payload else {}
            ),
            "brent_forecast_basis": self._build_brent_forecast_basis(
                report_payload=report_payload,
                horizon=horizon_config.code,
                feature_settlement=self._float_or_none(current_row.get("brent_active_settlement")),
            ),
            "policy_notice_count": len(policy_items),
            "latest_policy_notice": policy_items[0] if policy_items else None,
            "oilchem_maintenance_plan": (context_metadata or {}).get("oilchem_maintenance_plan"),
            "oilchem_inventory": (context_metadata or {}).get("oilchem_inventory"),
            "days_to_next_window": self._float_or_none(current_row.get("days_to_next_window")),
            "business_days_since_ceiling_adjust": self._float_or_none(
                current_row.get("business_days_since_ceiling_adjust")
            ),
            "horizon_steps": horizon_config.steps,
            "horizon_label": horizon_config.label,
            "target_mode": "endpoint_price",
            "runtime_controls": {
                claim.agent_name: claim.structured_payload.get("runtime_control", {}) for claim in agent_claims
            },
            "business_scorecard": self._business_scorecard_payload(agent_claims),
            "business_scorecard_prediction": {
                "model_name": "山东成品油市场价预测打分模型",
                "current_price": round(current_price, 2),
                "score": round(business_score, 4),
                "predicted_delta": round(business_predicted_delta, 4),
                "point_value": round(business_point_value, 2),
                "range_lower": round(business_point_value - business_range_half_width, 2),
                "range_upper": round(business_point_value + business_range_half_width, 2),
                "risk_range_lower": round(business_point_value - business_risk_range_half_width, 2),
                "risk_range_upper": round(business_point_value + business_risk_range_half_width, 2),
                "direction_label": business_direction_label,
                "range_half_width": round(business_range_half_width, 4),
                "risk_range_half_width": round(business_risk_range_half_width, 4),
                "mapping": business_mapping,
                "calibration": {
                    "status": "disabled",
                    "reason": "业务打分模型不再使用截距/斜率，也不使用周期点值上限；改用业务分专用状态桶后的历史同状态涨跌分布。",
                },
                "basis": "业务打分模型作为独立基准：业务总分进入业务分专用状态桶，点位取同桶历史涨跌中位数；样本不足时只看相邻桶，仍不足则走专家冷启动，不参与智能体综合分加权。",
            },
            "business_scorecard_comparison": self._business_scorecard_comparison(
                business_claim=business_claim,
                business_direction=business_direction_label,
                agent_score=score_value,
                final_direction=direction_label,
            ),
            "market_data_mode": (context_metadata or {}).get("market_data_mode"),
            "market_data_reason": (context_metadata or {}).get("market_data_reason"),
        }
        business_narrative_claim = business_claim.model_copy(deep=True)
        business_narrative_claim.numeric_signals = {
            **business_narrative_claim.numeric_signals,
            "weighted_score": float(business_claim.numeric_signals.get("standalone_score", business_score)),
            "score": float(business_claim.numeric_signals.get("standalone_score", business_score)),
        }
        business_driver_summary = build_driver_summary([business_narrative_claim])
        business_operating_advice = build_outright_advice(
            direction_label=business_direction_label,
            confidence_label=confidence_label,
            current_price=current_price,
            point_value=business_point_value,
            raw_context={**raw_context, "business_direction": {}},
            claims=[business_narrative_claim],
        )
        raw_context["business_scorecard_prediction"]["driver_summary"] = business_driver_summary
        raw_context["business_scorecard_prediction"]["operating_advice"] = [
            item.model_dump(mode="json") for item in business_operating_advice
        ]
        input_hash = self._build_input_hash(
            {
                "entity_code": "SD_GAS92",
                "region_code": "SHANDONG",
                "product_code": "GASOLINE_92",
                "horizon": horizon_config.code,
                "as_of_date": as_of_date.isoformat(),
                "scenario_text": scenario_text or "",
                "score_value": round(score_value, 4),
                "calibration_score_value": round(calibration_score_value, 4),
                "raw_context": raw_context,
            }
        )
        raw_context["input_hash"] = input_hash
        llm_agent_claims = build_llm_agent_claims(
            llm_client=self.llm_client,
            enabled=use_llm_explainer and mode != "backtest",
            subject=f"山东92#汽油 {horizon_config.code}",
            as_of_date=as_of_date,
            horizon=horizon_config.code,
            direction_label=direction_label,
            point_value=point_value,
            range_lower=point_value - range_half_width,
            range_upper=point_value + range_half_width,
            score_value=score_value,
            deterministic_claims=agent_claims,
            raw_context=raw_context,
        )
        raw_context["llm_agent_reviews"] = [claim.model_dump(mode="json") for claim in llm_agent_claims]
        judge_claim = build_agent_judge_claim(raw_context["agent_judgement"])

        fallback_explanation = self._build_explanation(
            claims=claims,
            score_value=score_value,
            point_value=point_value,
            range_lower=point_value - range_half_width,
            range_upper=point_value + range_half_width,
            direction_label=direction_label,
            horizon_config=horizon_config,
            current_price=current_price,
        )
        fallback_driver_summary = build_driver_summary(claims)
        fallback_operating_advice = build_outright_advice(
            direction_label=direction_label,
            confidence_label=confidence_label,
            current_price=current_price,
            point_value=point_value,
            raw_context=raw_context,
            claims=claims,
        )
        narrative = enrich_prediction_narrative(
            llm_client=self.llm_client,
            enabled=use_llm_explainer,
            subject=f"山东92#汽油 {horizon_config.code}",
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
            run_id=f"sdgas92-{input_hash[:12]}",
            entity_code="SD_GAS92",
            region_code="SHANDONG",
            product_code="GASOLINE_92",
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
            agent_claims=[*agent_claims, judge_claim, *llm_agent_claims],
            driver_summary=narrative.driver_summary,
            operating_advice=narrative.operating_advice,
            explanation=narrative.explanation,
            raw_context=raw_context,
        )

    def score_frame_for_backtest(
        self,
        frame: pd.DataFrame,
        refined_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_report_by_date: dict[date, dict[str, Any] | None] | None = None,
        enable_refined_news: bool = False,
        enable_event_risk: bool = False,
        horizon: str = "D1",
    ) -> pd.DataFrame:
        frame = frame.copy()
        scores = []
        business_scores = []
        for _, row in frame.iterrows():
            row_date = row["date"]
            backtest_extra = {
                "as_of_date": row_date,
                "mode": "calibration_backtest",
                "report_payload": None,
                "news_items": [],
                "refined_news_items": [],
                "policy_items": [],
                "prediction_subject": "outright",
                "enable_refined_news": False,
                "enable_event_risk": False,
                "horizon": horizon,
            }
            business_claim = self._score_business_scorecard(row, extra=backtest_extra)
            _, score_value = self._score_row(
                row,
                extra=backtest_extra,
            )
            scores.append(score_value)
            business_scores.append(float(business_claim.numeric_signals.get("standalone_score", 0.0)))
        frame["agent_score"] = scores
        frame["business_scorecard_score"] = business_scores
        return frame

    def _build_refined_news_label_signal(
        self,
        *,
        as_of_date: date,
        mode: str,
        refined_news_items: list[dict[str, Any]],
        scenario_text: str | None,
    ) -> dict[str, Any]:
        fallback = self._fallback_trade_sentiment_signal(refined_news_items=refined_news_items, news_items=[])
        fallback = {
            "deal_activity": fallback.get("label", "neutral_flat"),
            "trader_mindset": fallback.get("trader_mindset", "neutral"),
            "quote_behavior": "stable",
            "transaction_behavior": fallback.get("activity", "flat"),
            "inventory_signal_text": "",
            "supply_signal_text": "",
            "region_scope": "山东",
            "product_scope": "92#汽油",
            "evidence": fallback.get("reason"),
            "confidence": fallback.get("confidence", 0.35),
            "source": fallback.get("source", "rule_refined_news_label_fallback"),
            "_determinism": "rule_fallback",
        }
        if mode == "backtest" or not self.llm_client.enabled:
            return fallback
        source_text = self._trade_sentiment_source_text(
            refined_news_items=refined_news_items,
            news_items=[],
            scenario_text=scenario_text,
        )
        if not source_text.strip():
            return fallback
        cache_key = self._build_input_hash(
            {
                "task": "refined_news_labels",
                "model_name": self.llm_client.settings.model_name,
                "prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
                "as_of_date": as_of_date.isoformat(),
                "source_text": source_text[:5000],
            }
        )
        cached = self._load_llm_label_result(cache_key, self._trade_sentiment_cache)
        if cached is not None:
            return cached
        system_prompt = (
            "你是山东成品油现货资讯标签抽取员。只从材料抽取交易标签，不预测价格，不输出分数。"
            "必须输出 JSON，不得编造材料中不存在的事实。"
        )
        user_prompt = f"""
请从以下材料中抽取用于山东92#汽油现货研判的标签。

字段要求：
{{
  "deal_activity": "bullish_active|neutral_flat|bearish_selling",
  "trader_mindset": "bullish|neutral|bearish",
  "quote_behavior": "raise|firm|stable|discount|cut",
  "transaction_behavior": "active|flat|weak",
  "inventory_signal_text": "库存/补库相关事实，没有则空字符串",
  "supply_signal_text": "炼厂出货/检修/降负相关事实，没有则空字符串",
  "region_scope": "山东|全国|其他",
  "product_scope": "92#汽油|汽油|成品油|其他",
  "evidence": "用一句话写具体依据，不能写资讯面、消息面这种概述词",
  "confidence": 0.0
}}

材料：
{source_text[:5000]}
""".strip()
        try:
            payload = self.llm_client.summarize_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        if not isinstance(payload, dict):
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        label = str(payload.get("deal_activity") or "").strip()
        if label not in {"bullish_active", "neutral_flat", "bearish_selling"}:
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        result = {
            "deal_activity": label,
            "trader_mindset": str(payload.get("trader_mindset") or "neutral"),
            "quote_behavior": str(payload.get("quote_behavior") or "stable"),
            "transaction_behavior": str(payload.get("transaction_behavior") or "flat"),
            "inventory_signal_text": str(payload.get("inventory_signal_text") or ""),
            "supply_signal_text": str(payload.get("supply_signal_text") or ""),
            "region_scope": str(payload.get("region_scope") or ""),
            "product_scope": str(payload.get("product_scope") or ""),
            "evidence": str(payload.get("evidence") or "LLM抽取成品油交易标签"),
            "confidence": self._float_or_none(payload.get("confidence")),
            "source": "llm_refined_news_label_extractor",
            "_cache_key": cache_key,
            "_determinism": "input_hash_persistent_cache_temperature_0",
            "_model_name": self.llm_client.settings.model_name,
            "_prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
        }
        self._save_llm_label_result(cache_key, result, task="refined_news_labels", memory_cache=self._trade_sentiment_cache)
        return result

    def _build_event_risk_label_signal(
        self,
        *,
        as_of_date: date,
        mode: str,
        news_items: list[dict[str, Any]],
        report_payload: dict[str, Any] | None,
        scenario_text: str | None,
    ) -> dict[str, Any]:
        fallback = self._fallback_event_risk_label(news_items=news_items, report_payload=report_payload)
        if mode == "backtest" or not self.llm_client.enabled:
            return fallback
        source_text = self._event_source_text(news_items=news_items, report_payload=report_payload, scenario_text=scenario_text)
        if not source_text.strip():
            return fallback
        cache_key = self._build_input_hash(
            {
                "task": "event_risk_labels",
                "model_name": self.llm_client.settings.model_name,
                "prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
                "as_of_date": as_of_date.isoformat(),
                "source_text": source_text[:6000],
            }
        )
        cached = self._load_llm_label_result(cache_key, self._trade_sentiment_cache)
        if cached is not None:
            return cached
        system_prompt = (
            "你是成品油事件风险标签抽取员。只抽取黑天鹅、地缘、供应中断、政策突发等事件标签，"
            "不预测价格，不输出分数。必须输出 JSON。"
        )
        user_prompt = f"""
请判断以下材料是否包含会导致国内成品油现货明显波动的事件，并抽取标签。

字段要求：
{{
  "event_type": "geopolitical|supply_disruption|policy|macro|weather|none",
  "impact_chain": "事件 -> Brent -> 调价预期 -> 主营/地炼报价 -> 山东92#",
  "direction": "up|down|flat",
  "severity": "none|low|medium|high|extreme",
  "duration": "intraday|D1|D3|W1|M1|unknown",
  "affected_region": "山东|全国|海外|其他",
  "affected_product": "92#汽油|汽油|成品油|原油|其他",
  "evidence": "写清具体事件时间、主体和影响，不得只写地缘风险或黑天鹅",
  "manual_review_required": false
}}

材料：
{source_text[:6000]}
""".strip()
        try:
            payload = self.llm_client.summarize_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        if not isinstance(payload, dict):
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        severity = str(payload.get("severity") or "low").strip()
        if severity not in {"none", "low", "medium", "high", "extreme"}:
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        result = {
            "event_type": str(payload.get("event_type") or "none"),
            "impact_chain": str(payload.get("impact_chain") or ""),
            "direction": str(payload.get("direction") or "flat"),
            "severity": severity,
            "duration": str(payload.get("duration") or "unknown"),
            "affected_region": str(payload.get("affected_region") or ""),
            "affected_product": str(payload.get("affected_product") or ""),
            "evidence": str(payload.get("evidence") or ""),
            "manual_review_required": bool(payload.get("manual_review_required")),
            "source": "llm_event_risk_label_extractor",
            "_cache_key": cache_key,
            "_determinism": "input_hash_persistent_cache_temperature_0",
            "_model_name": self.llm_client.settings.model_name,
            "_prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
        }
        self._save_llm_label_result(cache_key, result, task="event_risk_labels", memory_cache=self._trade_sentiment_cache)
        return result

    def _score_calibration_row(self, row: pd.Series, extra: dict[str, Any]) -> tuple[list[AgentClaim], float]:
        calibration_extra = {
            **extra,
            "mode": "calibration",
            "report_payload": None,
            "news_items": [],
            "refined_news_items": [],
            "enable_refined_news": False,
            "enable_event_risk": False,
        }
        return self._score_row(row, calibration_extra, excluded_agent_names=NON_CALIBRATABLE_AGENT_NAMES)

    def _score_row(
        self,
        row: pd.Series,
        extra: dict[str, Any],
        excluded_agent_names: set[str] | None = None,
    ) -> tuple[list[AgentClaim], float]:
        claims: list[AgentClaim] = []
        total_score = 0.0
        total_weight = 0.0
        controls = self.agent_control_service.get_runtime_controls(self.scope_key)
        excluded_agent_names = excluded_agent_names or set()
        for agent in self.agents:
            if agent.name in excluded_agent_names:
                continue
            claim = agent.analyze(row, extra)
            control = controls.get(agent.name, {"enabled": True})
            raw_score = float(claim.numeric_signals.get("score", 0.0))
            max_score = float(claim.numeric_signals.get("max_score", getattr(agent, "max_score", 100.0)) or 100.0)
            enabled = bool(control.get("enabled", True))
            expert_weight = OUTRIGHT_EXPERT_PRIOR_WEIGHTS.get(agent.name, 0.0)
            weight = expert_weight if enabled else 0.0
            normalized_score = max(-1.0, min(1.0, raw_score / max(max_score, 1.0)))
            weighted_score = normalized_score * weight
            claim.numeric_signals = {
                **claim.numeric_signals,
                "score": round(normalized_score, 4),
                "raw_score": round(raw_score, 4),
                "max_score": round(max_score, 4),
                "weight": round(weight, 4),
                "expert_prior_weight": round(expert_weight, 4),
                "normalized_score": round(normalized_score, 4),
                "weighted_score": round(weighted_score, 4),
            }
            claim.structured_payload = {
                **claim.structured_payload,
                "runtime_control": {
                    "scope_key": self.scope_key,
                    "enabled": enabled,
                    "weight": round(weight, 4),
                    "weight_basis": "expert_prior_fixed",
                },
            }
            claims.append(claim)
            total_score += weighted_score
            if weight > 0:
                total_weight += weight
        composite_score = total_score / total_weight if total_weight > 0 else 0.0
        composite_score = max(-1.0, min(1.0, composite_score))
        return claims, round(composite_score, 4)

    def _build_trade_sentiment_signal(
        self,
        *,
        as_of_date: date,
        mode: str,
        refined_news_items: list[dict[str, Any]],
        news_items: list[dict[str, Any]],
        scenario_text: str | None,
    ) -> dict[str, Any]:
        fallback = self._fallback_trade_sentiment_signal(
            refined_news_items=refined_news_items,
            news_items=news_items,
        )
        if mode == "backtest" or not self.llm_client.enabled:
            return fallback
        source_text = self._trade_sentiment_source_text(
            refined_news_items=refined_news_items,
            news_items=news_items,
            scenario_text=scenario_text,
        )
        if not source_text.strip():
            return fallback
        cache_key = self._build_input_hash(
            {
                "task": "trade_sentiment",
                "model_name": self.llm_client.settings.model_name,
                "prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
                "as_of_date": as_of_date.isoformat(),
                "source_text": source_text[:4000],
            }
        )
        cached = self._load_llm_label_result(cache_key, self._trade_sentiment_cache)
        if cached is not None:
            return cached
        system_prompt = (
            "你是山东成品油市场交易情绪评估员。只判断成交活跃度和贸易商心态，"
            "不要判断原油方向，不要给价格预测。必须输出 JSON。"
        )
        user_prompt = f"""
请根据以下成品油资讯、午评、成交描述，判断山东92#汽油市场的成交活跃度和贸易商心态。

只允许 label 取以下三类之一：
- bullish_active：成交活跃、抢货积极、贸易商挺价或推涨意愿强。
- neutral_flat：成交一般、刚需采购、观望为主、心态平稳。
- bearish_selling：成交转弱、抛货/让利集中、贸易商看跌或去库存压力大。

输出 JSON 字段：
{{
  "label": "bullish_active|neutral_flat|bearish_selling",
  "activity": "active|flat|weak",
  "trader_mindset": "bullish|neutral|bearish",
  "confidence": 0.0,
  "reason": "20字以内，必须说明成交或贸易商心态依据"
}}

材料：
{source_text[:4000]}
""".strip()
        try:
            payload = self.llm_client.summarize_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        if not isinstance(payload, dict):
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        label = str(payload.get("label") or "").strip()
        if label not in {"bullish_active", "neutral_flat", "bearish_selling"}:
            self._trade_sentiment_cache[cache_key] = fallback
            return fallback
        result = {
            "label": label,
            "activity": str(payload.get("activity") or ""),
            "trader_mindset": str(payload.get("trader_mindset") or ""),
            "confidence": self._float_or_none(payload.get("confidence")),
            "reason": str(payload.get("reason") or "LLM判断成交活跃度和贸易商心态"),
            "source": "llm_trade_sentiment",
            "_cache_key": cache_key,
            "_determinism": "input_hash_persistent_cache_temperature_0",
            "_model_name": self.llm_client.settings.model_name,
            "_prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
        }
        self._save_llm_label_result(cache_key, result, task="trade_sentiment", memory_cache=self._trade_sentiment_cache)
        return result

    def _trade_sentiment_source_text(
        self,
        *,
        refined_news_items: list[dict[str, Any]],
        news_items: list[dict[str, Any]],
        scenario_text: str | None,
    ) -> str:
        lines: list[str] = []
        if scenario_text:
            lines.append(f"人工场景：{scenario_text}")
        for item in [*refined_news_items[:12], *news_items[:5]]:
            text = " ".join(
                str(item.get(key) or "")
                for key in ("publish_time", "headline", "title", "summary", "content")
            ).strip()
            if text:
                lines.append(text[:500])
        return "\n".join(lines)

    def _event_source_text(
        self,
        *,
        news_items: list[dict[str, Any]],
        report_payload: dict[str, Any] | None,
        scenario_text: str | None,
    ) -> str:
        lines: list[str] = []
        if scenario_text:
            lines.append(f"人工场景：{scenario_text}")
        if report_payload:
            lines.append(
                " ".join(
                    str(report_payload.get(key) or "")
                    for key in ("report_date", "title", "summary", "markdown")
                )[:1600]
            )
        for item in news_items[:20]:
            text = " ".join(
                str(item.get(key) or "")
                for key in ("publish_time", "headline", "title", "summary", "content")
            ).strip()
            if text:
                lines.append(text[:500])
        return "\n".join(lines)

    def _fallback_event_risk_label(
        self,
        *,
        news_items: list[dict[str, Any]],
        report_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        text = self._event_source_text(news_items=news_items, report_payload=report_payload, scenario_text=None)
        high_words = ("战争", "袭击", "封锁", "断供", "制裁", "霍尔木兹", "红海")
        medium_words = ("OPEC", "减产", "库存骤降", "供应中断", "地缘")
        high_hits = sum(text.count(word) for word in high_words)
        medium_hits = sum(text.count(word) for word in medium_words)
        report_signals = (report_payload or {}).get("signals") or {}
        brent_change = self._float_or_none(report_signals.get("brent_settlement_change_usd")) or 0.0
        if high_hits and abs(brent_change) >= 3.0:
            severity = "high"
            direction = "up"
            event_type = "geopolitical"
            evidence = "地缘/供应中断关键词与Brent大幅波动同时出现"
        elif high_hits or medium_hits:
            severity = "medium"
            direction = "up"
            event_type = "supply_disruption"
            evidence = "命中供应扰动关键词，但未伴随Brent大幅波动"
        else:
            severity = "low" if news_items else "none"
            direction = "flat"
            event_type = "none"
            evidence = "未识别到高等级突发事件"
        return {
            "event_type": event_type,
            "impact_chain": "事件 -> Brent -> 调价预期 -> 主营/地炼报价 -> 山东92#",
            "direction": direction,
            "severity": severity,
            "duration": "unknown",
            "affected_region": "",
            "affected_product": "",
            "evidence": evidence,
            "manual_review_required": severity in {"high", "extreme"},
            "source": "rule_event_risk_label_fallback",
            "_determinism": "rule_fallback",
        }

    def _build_monthly_market_sentiment_signal(
        self,
        *,
        as_of_date: date,
        mode: str,
        refined_news_items: list[dict[str, Any]],
        news_items: list[dict[str, Any]],
        scenario_text: str | None,
    ) -> dict[str, Any]:
        fallback = {
            "label": "neutral",
            "confidence": 0.3,
            "reason": "月度情绪信号不足",
            "source": "rule_monthly_sentiment_fallback",
            "_determinism": "rule_fallback",
        }
        if mode == "backtest" or not self.llm_client.enabled:
            return fallback
        source_text = self._trade_sentiment_source_text(
            refined_news_items=refined_news_items,
            news_items=news_items,
            scenario_text=scenario_text,
        )
        if not source_text.strip():
            return fallback
        cache_key = self._build_input_hash(
            {
                "task": "monthly_market_sentiment",
                "model_name": self.llm_client.settings.model_name,
                "prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
                "as_of_date": as_of_date.isoformat(),
                "source_text": source_text[:4000],
            }
        )
        cached = self._load_llm_label_result(cache_key, self._monthly_sentiment_cache)
        if cached is not None:
            return cached
        system_prompt = (
            "你是山东92#汽油月度市场情绪评估员。只判断月度备货和市场心态，"
            "不要给价格预测，不要输出分数，必须输出 JSON。"
        )
        user_prompt = f"""
请根据以下成品油资讯、淡旺季、节假日和市场描述，判断山东92#汽油下月市场整体情绪。

只允许 label 取以下三类之一：
- peak_season_bullish：旺季备货情绪浓厚、补库意愿强、市场心态偏多。
- neutral：观望中性、刚需采购、节奏平稳。
- bearish：悲观利空情绪主导、补库减少、库存压力或需求转弱。

输出 JSON 字段：
{{
  "label": "peak_season_bullish|neutral|bearish",
  "confidence": 0.0,
  "reason": "20字以内，说明月度备货或市场心态依据"
}}

材料：
{source_text[:4000]}
""".strip()
        try:
            payload = self.llm_client.summarize_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            self._monthly_sentiment_cache[cache_key] = fallback
            return fallback
        if not isinstance(payload, dict):
            self._monthly_sentiment_cache[cache_key] = fallback
            return fallback
        label = str(payload.get("label") or "").strip()
        if label not in {"peak_season_bullish", "neutral", "bearish"}:
            self._monthly_sentiment_cache[cache_key] = fallback
            return fallback
        result = {
            "label": label,
            "confidence": self._float_or_none(payload.get("confidence")),
            "reason": str(payload.get("reason") or "LLM判断月度市场情绪"),
            "source": "llm_monthly_market_sentiment",
            "_cache_key": cache_key,
            "_determinism": "input_hash_persistent_cache_temperature_0",
            "_model_name": self.llm_client.settings.model_name,
            "_prompt_version": LLM_LABEL_EXTRACTOR_VERSION,
        }
        self._save_llm_label_result(
            cache_key,
            result,
            task="monthly_market_sentiment",
            memory_cache=self._monthly_sentiment_cache,
        )
        return result

    def _fallback_trade_sentiment_signal(
        self,
        *,
        refined_news_items: list[dict[str, Any]],
        news_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        positive_words = (
            "抢货", "成交活跃", "推涨", "挺价", "补货", "询盘增加", "心态偏强", "出货顺畅",
            "低价惜售", "集中补库", "炼厂推价", "成交放量", "贸易商接货积极",
        )
        negative_words = (
            "抛货", "让利", "成交转弱", "出货不畅", "降价", "看跌", "观望浓厚", "去库压力",
            "高价抵触", "成交清淡", "按需采购", "降库", "套利窗口关闭", "出货承压",
        )
        text = "\n".join(
            " ".join(str(item.get(key) or "") for key in ("headline", "title", "summary", "content"))
            for item in [*refined_news_items[:12], *news_items[:5]]
        )
        positive = sum(text.count(word) for word in positive_words)
        negative = sum(text.count(word) for word in negative_words)
        if positive > negative:
            label = "bullish_active"
            reason = "成交或挺价关键词偏多"
        elif negative > positive:
            label = "bearish_selling"
            reason = "让利或弱成交关键词偏多"
        else:
            label = "neutral_flat"
            reason = "成交与心态信号不明显"
        return {
            "label": label,
            "activity": "flat",
            "trader_mindset": "neutral",
            "confidence": 0.35,
            "reason": reason,
            "source": "rule_trade_sentiment_fallback",
            "_determinism": "rule_fallback",
        }

    def _score_business_scorecard(self, row: pd.Series, extra: dict[str, Any]) -> AgentClaim:
        claim = self.business_scorecard_agent.analyze(row, extra)
        raw_score = float(claim.numeric_signals.get("score", 0.0))
        claim.numeric_signals = {
            **claim.numeric_signals,
            "score": round(raw_score, 4),
            "raw_score": round(raw_score, 4),
            "standalone_score": round(raw_score, 4),
            "weight": 0.0,
            "weighted_score": 0.0,
            "excluded_from_model_score": 1.0,
        }
        claim.structured_payload = {
            **claim.structured_payload,
            "runtime_control": {
                "scope_key": self.scope_key,
                "enabled": True,
                "weight": 0.0,
                "mode": "standalone_baseline",
            },
        }
        return claim

    def _business_scorecard_payload(self, claims: list[AgentClaim]) -> dict[str, Any] | None:
        for claim in claims:
            if claim.agent_name == "business_scorecard_agent":
                payload = claim.structured_payload.get("scorecard")
                return payload if isinstance(payload, dict) else None
        return None

    def _business_scorecard_comparison(
        self,
        *,
        business_claim: AgentClaim,
        business_direction: str,
        agent_score: float,
        final_direction: str,
    ) -> dict[str, Any]:
        if business_direction == final_direction:
            consistency = "方向一致"
        elif {business_direction, final_direction} == {"up", "down"}:
            consistency = "方向冲突"
        else:
            consistency = "强弱分歧"
        return {
            "business_score": round(float(business_claim.numeric_signals.get("standalone_score", 0.0)), 4),
            "business_direction": business_direction,
            "agent_composite_score": round(agent_score, 4),
            "final_direction": final_direction,
            "consistency": consistency,
            "usage": "业务打分模型作为独立基准，不参与多智能体综合分加权。",
        }

    def _score_delta_mapping(
        self,
        frame: pd.DataFrame,
        as_of_date: date,
        horizon_config: HorizonConfig,
        score_column: str,
        score_value: float,
        refined_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_report_by_date: dict[date, dict[str, Any] | None] | None = None,
        enable_refined_news: bool = False,
        enable_event_risk: bool = False,
        scored_history: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        if scored_history is None:
            scored_history = self._historical_scored_delta_frame(
                frame=frame,
                as_of_date=as_of_date,
                horizon_config=horizon_config,
                refined_news_by_date=refined_news_by_date,
                event_news_by_date=event_news_by_date,
                event_report_by_date=event_report_by_date,
                enable_refined_news=enable_refined_news,
                enable_event_risk=enable_event_risk,
            )
        score_points = self._score_points(score_column=score_column, score_value=score_value)
        bucket_schema = "business_scorecard" if score_column == "business_scorecard_score" else "agent_composite"
        bucket_defs = self._score_bucket_defs(score_column=score_column)
        bucket_index = self._score_bucket_index(score_points, bucket_defs=bucket_defs)
        bucket = bucket_defs[bucket_index]
        scored_history = scored_history.dropna(subset=[score_column, "target_delta"]).copy()
        if not scored_history.empty:
            scored_history["_score_points"] = scored_history[score_column].map(
                lambda value: self._score_points(score_column=score_column, score_value=float(value))
            )
            scored_history["_bucket_index"] = scored_history["_score_points"].map(
                lambda value: self._score_bucket_index(float(value), bucket_defs=bucket_defs)
            )
            scored_history = scored_history.tail(180)

        selected = self._select_bucket_history(
            scored_history,
            bucket_index=bucket_index,
            min_sample_size=12,
            bucket_defs=bucket_defs,
            max_merge_radius=1 if score_column == "business_scorecard_score" else None,
        )
        if selected.empty:
            mapping = self._cold_start_bucket_mapping(
                score_column=score_column,
                score_points=score_points,
                bucket_index=bucket_index,
                horizon=horizon_config.code,
                history_sample_size=len(scored_history),
            )
        else:
            deltas = selected["target_delta"].astype(float).to_numpy()
            p10 = float(np.quantile(deltas, 0.10))
            p25 = float(np.quantile(deltas, 0.25))
            p50 = float(np.quantile(deltas, 0.50))
            p75 = float(np.quantile(deltas, 0.75))
            p90 = float(np.quantile(deltas, 0.90))
            raw_p25 = p25
            raw_p50 = p50
            raw_p75 = p75
            constrained = self._apply_score_direction_constraint(
                predicted_delta=p50,
                lower_delta=p25,
                upper_delta=p75,
                score_points=score_points,
                bucket=bucket,
            )
            p50 = constrained["predicted_delta"]
            p25 = constrained["lower_delta"]
            p75 = constrained["upper_delta"]
            directional_fallback = self._directional_bucket_fallback_delta(
                deltas=deltas,
                bucket=bucket,
                constrained_delta=p50,
            )
            if directional_fallback["applied"]:
                p50 = float(directional_fallback["predicted_delta"])
                if int(bucket.get("polarity", 0)) > 0:
                    p25 = min(p25, 0.0)
                    p75 = max(p75, p50)
                else:
                    p25 = min(p25, p50)
                    p75 = max(p75, 0.0)
            range_half_width = max(abs(p50 - p25), abs(p75 - p50), horizon_config.direction_threshold)
            selected_bucket_indexes = sorted({int(value) for value in selected["_bucket_index"].dropna().tolist()})
            reason = (
                "使用当前分数所在状态桶的历史真实涨跌分布。"
                if selected_bucket_indexes == [bucket_index]
                else "当前状态桶样本不足，合并相邻状态桶后取历史真实涨跌分布。"
            )
            if directional_fallback["applied"]:
                reason = f"{reason} 整体中位数与方向桶信号冲突，改用同向样本的保守分位数生成点位。"
            mapping = {
                "method": "historical_bucket_distribution_mapping",
                "status": "empirical" if selected_bucket_indexes == [bucket_index] else "merged_bucket",
                "reason": reason,
                "score_column": score_column,
                "bucket_schema": bucket_schema,
                "score_value": round(float(score_value), 4),
                "score_points": round(float(score_points), 4),
                "bucket": bucket["label"],
                "bucket_range": bucket["range_label"],
                "selected_buckets": [bucket_defs[index]["label"] for index in selected_bucket_indexes],
                "sample_size": int(len(selected)),
                "history_sample_size": int(len(scored_history)),
                "predicted_delta": round(float(p50), 4),
                "p10_delta": round(float(p10), 4),
                "p25_delta": round(float(p25), 4),
                "p50_delta": round(float(p50), 4),
                "p75_delta": round(float(p75), 4),
                "p90_delta": round(float(p90), 4),
                "raw_p25_delta": round(float(raw_p25), 4),
                "raw_p50_delta": round(float(raw_p50), 4),
                "raw_p75_delta": round(float(raw_p75), 4),
                "range_lower_delta": round(float(p25), 4),
                "range_upper_delta": round(float(p75), 4),
                "range_half_width": round(float(range_half_width), 4),
                "semantic_constraint_applied": bool(constrained["applied"]),
                "directional_fallback": directional_fallback,
            }
        return mapping

    def _historical_scored_delta_frame(
        self,
        *,
        frame: pd.DataFrame,
        as_of_date: date,
        horizon_config: HorizonConfig,
        refined_news_by_date: dict[date, list[dict[str, Any]]] | None,
        event_news_by_date: dict[date, list[dict[str, Any]]] | None,
        event_report_by_date: dict[date, dict[str, Any] | None],
        enable_refined_news: bool,
        enable_event_risk: bool,
    ) -> pd.DataFrame:
        work = frame.sort_values("date").copy()
        work["target_date"] = work["date"].shift(-horizon_config.steps)
        work["target_price"] = work["sd_gas92_market"].shift(-horizon_config.steps)
        work["target_delta"] = work["target_price"] - work["sd_gas92_market"]
        history = work[(work["date"] < as_of_date) & (work["target_date"] <= as_of_date)].copy()
        history = history.dropna(subset=["target_delta"])
        if history.empty:
            return history
        return self.score_frame_for_backtest(
            history,
            refined_news_by_date=refined_news_by_date,
            event_news_by_date=event_news_by_date,
            event_report_by_date=event_report_by_date,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
            horizon=horizon_config.code,
        )

    def _score_points(self, *, score_column: str, score_value: float) -> float:
        value = float(score_value)
        if score_column == "agent_score":
            return max(-100.0, min(100.0, value * 100.0))
        return max(-100.0, min(100.0, value))

    def _score_bucket_defs(self, score_column: str | None = None) -> list[dict[str, Any]]:
        if score_column == "business_scorecard_score":
            return [
                {"label": "强空", "range_label": "<=-70", "lower": -math.inf, "upper": -70.0, "polarity": -1},
                {"label": "偏空", "range_label": "-70~-35", "lower": -70.0, "upper": -35.0, "polarity": -1},
                {"label": "弱空", "range_label": "-35~-10", "lower": -35.0, "upper": -10.0, "polarity": -1},
                {"label": "震荡", "range_label": "-10~10", "lower": -10.0, "upper": 10.0, "polarity": 0},
                {"label": "弱多", "range_label": "10~35", "lower": 10.0, "upper": 35.0, "polarity": 1},
                {"label": "偏多", "range_label": "35~70", "lower": 35.0, "upper": 70.0, "polarity": 1},
                {"label": "强多", "range_label": ">=70", "lower": 70.0, "upper": math.inf, "polarity": 1},
            ]
        return [
            {"label": "强空", "range_label": "<=-12", "lower": -math.inf, "upper": -12.0, "polarity": -1},
            {"label": "偏空", "range_label": "-12~-6", "lower": -12.0, "upper": -6.0, "polarity": -1},
            {"label": "弱空", "range_label": "-6~-2", "lower": -6.0, "upper": -2.0, "polarity": -1},
            {"label": "震荡", "range_label": "-2~2", "lower": -2.0, "upper": 2.0, "polarity": 0},
            {"label": "弱多", "range_label": "2~6", "lower": 2.0, "upper": 6.0, "polarity": 1},
            {"label": "偏多", "range_label": "6~12", "lower": 6.0, "upper": 12.0, "polarity": 1},
            {"label": "强多", "range_label": ">=12", "lower": 12.0, "upper": math.inf, "polarity": 1},
        ]

    def _score_bucket_index(
        self,
        score_points: float,
        bucket_defs: list[dict[str, Any]] | None = None,
    ) -> int:
        bucket_defs = bucket_defs or self._score_bucket_defs()
        for index, bucket in enumerate(bucket_defs):
            if float(bucket["lower"]) <= float(score_points) < float(bucket["upper"]):
                return index
        return len(bucket_defs) - 1

    def _select_bucket_history(
        self,
        history: pd.DataFrame,
        *,
        bucket_index: int,
        min_sample_size: int,
        bucket_defs: list[dict[str, Any]] | None = None,
        max_merge_radius: int | None = None,
    ) -> pd.DataFrame:
        if history.empty:
            return history
        bucket_count = len(bucket_defs or self._score_bucket_defs())
        selected = history[history["_bucket_index"] == bucket_index]
        if len(selected) >= min_sample_size:
            return selected
        max_radius = bucket_count - 1 if max_merge_radius is None else min(max_merge_radius, bucket_count - 1)
        for radius in range(1, max_radius + 1):
            allowed = {
                index
                for index in range(bucket_index - radius, bucket_index + radius + 1)
                if 0 <= index < bucket_count
            }
            selected = history[history["_bucket_index"].isin(allowed)]
            if len(selected) >= min_sample_size:
                return selected
        if max_merge_radius is not None and len(selected) < min_sample_size:
            return history.iloc[0:0]
        return selected

    def _apply_score_direction_constraint(
        self,
        *,
        predicted_delta: float,
        lower_delta: float,
        upper_delta: float,
        score_points: float,
        bucket: dict[str, Any],
    ) -> dict[str, Any]:
        applied = False
        point = float(predicted_delta)
        lower = float(lower_delta)
        upper = float(upper_delta)
        polarity = int(bucket.get("polarity", 0))
        if polarity < 0 and point > 0:
            point = 0.0
            upper = min(upper, 0.0)
            lower = min(lower, upper)
            applied = True
        elif polarity > 0 and point < 0:
            point = 0.0
            lower = max(lower, 0.0)
            upper = max(upper, lower)
            applied = True
        elif polarity == 0:
            point = 0.0
            applied = not math.isclose(float(predicted_delta), 0.0, abs_tol=0.0001)
        return {
            "predicted_delta": point,
            "lower_delta": lower,
            "upper_delta": upper,
            "applied": applied,
        }

    def _directional_bucket_fallback_delta(
        self,
        *,
        deltas: np.ndarray,
        bucket: dict[str, Any],
        constrained_delta: float,
    ) -> dict[str, Any]:
        polarity = int(bucket.get("polarity", 0))
        if polarity == 0 or not math.isclose(float(constrained_delta), 0.0, abs_tol=0.0001):
            return {"applied": False, "reason": "not_needed"}

        same_direction = deltas[deltas > 0] if polarity > 0 else deltas[deltas < 0]
        min_sample_size = max(5, int(math.ceil(len(deltas) * 0.15)))
        if len(same_direction) < min_sample_size:
            return {
                "applied": False,
                "reason": "insufficient_same_direction_samples",
                "same_direction_sample_size": int(len(same_direction)),
                "min_sample_size": int(min_sample_size),
            }

        quantile = 0.25 if polarity > 0 else 0.75
        predicted_delta = float(np.quantile(same_direction, quantile))
        return {
            "applied": True,
            "reason": "same_direction_conservative_quantile",
            "quantile": quantile,
            "same_direction_sample_size": int(len(same_direction)),
            "min_sample_size": int(min_sample_size),
            "predicted_delta": round(predicted_delta, 4),
        }

    def _cold_start_bucket_mapping(
        self,
        *,
        score_column: str,
        score_points: float,
        bucket_index: int,
        horizon: str,
        history_sample_size: int = 0,
    ) -> dict[str, Any]:
        base_by_bucket = [-45.0, -25.0, -10.0, 0.0, 10.0, 25.0, 45.0]
        horizon_scale = {"D1": 1.0, "D3": 1.6, "W1": 2.4, "M1": 4.0}.get(horizon, 1.0)
        point = base_by_bucket[bucket_index] * horizon_scale
        bucket = self._score_bucket_defs(score_column=score_column)[bucket_index]
        if int(bucket.get("polarity", 0)) == 0:
            point = 0.0
        half_width = max(abs(point) * 0.75, HORIZON_BASE_RANGE_HALF_WIDTH.get(horizon, 50.0))
        return {
            "method": "historical_bucket_distribution_mapping",
            "status": "cold_start",
            "reason": "当前可回放历史样本不足，暂用专家冷启动状态桶；积累样本后自动切换为同桶历史分布。",
            "score_column": score_column,
            "bucket_schema": "business_scorecard" if score_column == "business_scorecard_score" else "agent_composite",
            "score_value": round(float(score_points / 100.0 if score_column == "agent_score" else score_points), 4),
            "score_points": round(float(score_points), 4),
            "bucket": bucket["label"],
            "bucket_range": bucket["range_label"],
            "selected_buckets": [bucket["label"]],
            "sample_size": 0,
            "history_sample_size": int(history_sample_size),
            "predicted_delta": round(float(point), 4),
            "p10_delta": round(float(point - half_width), 4),
            "p25_delta": round(float(point - half_width / 2.0), 4),
            "p50_delta": round(float(point), 4),
            "p75_delta": round(float(point + half_width / 2.0), 4),
            "p90_delta": round(float(point + half_width), 4),
            "range_lower_delta": round(float(point - half_width / 2.0), 4),
            "range_upper_delta": round(float(point + half_width / 2.0), 4),
            "range_half_width": round(float(half_width / 2.0), 4),
            "semantic_constraint_applied": False,
        }

    def _fit_calibration(
        self,
        frame: pd.DataFrame,
        as_of_date: date,
        horizon_config: HorizonConfig,
        score_column: str = "agent_score",
        refined_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_news_by_date: dict[date, list[dict[str, Any]]] | None = None,
        event_report_by_date: dict[date, dict[str, Any] | None] | None = None,
        enable_refined_news: bool = False,
        enable_event_risk: bool = False,
    ) -> CalibrationResult:
        history = frame[frame["date"] < as_of_date].copy()
        history["target_price"] = history["sd_gas92_market"].shift(-horizon_config.steps)
        history["target_delta"] = history["target_price"] - history["sd_gas92_market"]
        history = history.dropna(subset=["target_delta"])
        history = self.score_frame_for_backtest(
            history,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
            horizon=horizon_config.code,
        )
        history = history.dropna(subset=[score_column])
        history = history.tail(120)
        min_sample_size = 30
        if len(history) < min_sample_size:
            rmse_floor = 80.0 + max(horizon_config.steps - 1, 0) * 4.0
            return CalibrationResult(
                intercept=0.0,
                slope=0.0,
                rmse=rmse_floor,
                sample_size=len(history),
                status="insufficient_sample",
                reason=f"可回放历史样本 {len(history)} 条，低于最低要求 {min_sample_size} 条；不使用固定周期点值兜底。",
            )

        x = history[score_column].astype(float).to_numpy()
        y = history["target_delta"].astype(float).to_numpy()
        x_mean = float(np.mean(x))
        y_mean = float(np.mean(y))
        denom = float(np.sum((x - x_mean) ** 2))
        slope = 0.6 if math.isclose(denom, 0.0) else float(np.sum((x - x_mean) * (y - y_mean)) / denom)
        intercept = y_mean - slope * x_mean
        residuals = y - (intercept + slope * x)
        rmse = float(np.sqrt(np.mean(residuals**2)))
        return CalibrationResult(
            intercept=intercept,
            slope=slope,
            rmse=rmse,
            sample_size=len(history),
            status="ok",
            reason="由可回放结构化历史样本拟合得到。",
        )

    def _delta_from_calibration(self, *, calibration: CalibrationResult, score_value: float) -> float:
        if calibration.status != "ok":
            return 0.0
        return float(calibration.intercept) + float(calibration.slope) * float(score_value)

    def _build_explanation(
        self,
        *,
        claims: list[AgentClaim],
        score_value: float,
        point_value: float,
        range_lower: float,
        range_upper: float,
        direction_label: str,
        horizon_config: HorizonConfig,
        current_price: float,
    ) -> str:
        direction_text = {"up": "上行", "down": "下行", "flat": "震荡"}[direction_label]
        top_claims = sorted(
            claims,
            key=lambda item: abs(float(item.numeric_signals.get("weighted_score", 0.0))),
            reverse=True,
        )[:3]
        details = "；".join(item.evidence[0] if item.evidence else item.summary for item in top_claims if item.summary)
        return (
            f"山东92#汽油 {horizon_config.code} 判断为{direction_text}，当前价格 {current_price:.2f}，"
            f"模型综合分 {score_value:.2f}，预测点位 {point_value:.2f}，参考区间 {range_lower:.2f}~{range_upper:.2f}。"
            + (f" 主要依据包括：{details}。" if details else "")
        )

    def _direction_from_delta(self, predicted_delta: float, threshold: float = 3.0) -> str:
        if predicted_delta > threshold:
            return "up"
        if predicted_delta < -threshold:
            return "down"
        return "flat"

    def _probabilities_from_score(self, score_value: float) -> dict[str, float]:
        normalized = max(-1.0, min(1.0, float(score_value)))
        up_raw = max(normalized, 0.0) * 45.0 + 12.0
        down_raw = max(-normalized, 0.0) * 45.0 + 12.0
        flat_raw = max(8.0, 55.0 - abs(normalized) * 38.0)
        total = up_raw + down_raw + flat_raw
        return {
            "up": round(up_raw / total, 4),
            "flat": round(flat_raw / total, 4),
            "down": round(down_raw / total, 4),
        }

    def _brent_report_quality(
        self,
        *,
        as_of_date: date,
        report_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not report_payload:
            return {
                "status": "brent_daily_report_missing",
                "report_date": None,
                "as_of_date": as_of_date.isoformat(),
                "reason": "预测日没有可用 Brent 日报，点位只能作为降级参考。",
            }

        report_date_raw = report_payload.get("report_date")
        report_date = None
        if isinstance(report_date_raw, date):
            report_date = report_date_raw
        elif report_date_raw:
            try:
                report_date = date.fromisoformat(str(report_date_raw)[:10])
            except ValueError:
                report_date = None

        if report_date != as_of_date:
            return {
                "status": "brent_daily_report_stale",
                "report_date": report_date.isoformat() if report_date else report_date_raw,
                "as_of_date": as_of_date.isoformat(),
                "reason": "Brent 日报日期与预测日不一致，不能按正常日报口径使用。",
            }

        return {
            "status": "fresh",
            "report_date": report_date.isoformat(),
            "as_of_date": as_of_date.isoformat(),
            "reason": "Brent 日报日期与预测日一致。",
        }

    def _point_adjustments(
        self,
        *,
        row: pd.Series,
        horizon: str,
        event_gate: dict[str, Any],
        score_extra: dict[str, Any],
        claims: list[AgentClaim],
        base_predicted_delta: float,
    ) -> dict[str, float]:
        if horizon != "D1":
            return {}
        adjustments: dict[str, float] = {}
        brent_change = self._float_or_none(row.get("brent_change_1d")) or 0.0
        gate_level = str(event_gate.get("level") or "low").lower()
        gate_direction = str((event_gate.get("llm_risk_gate") or {}).get("direction") or "flat").lower()

        spot_claim = next((claim for claim in claims if claim.agent_name == "shandong_spot_jump_agent"), None)
        if spot_claim is not None:
            jump_delta = self._float_or_none(spot_claim.structured_payload.get("jump_delta_d1")) or 0.0
            if abs(jump_delta) > 0:
                jump_delta = self._soft_cap_spot_jump_adjustment(
                    base_predicted_delta=base_predicted_delta,
                    jump_delta=jump_delta,
                    spot_payload=spot_claim.structured_payload,
                )
                adjustments["shandong_spot_jump"] = jump_delta

        event_overlay = self._event_cost_overlay_adjustment(
            base_predicted_delta=base_predicted_delta + sum(adjustments.values()),
            brent_change=brent_change,
            gate_level=gate_level,
            gate_direction=gate_direction,
        )
        if abs(event_overlay) > 0:
            adjustments["event_cost_overlay"] = event_overlay

        return adjustments

    def _event_cost_overlay_adjustment(
        self,
        *,
        base_predicted_delta: float,
        brent_change: float,
        gate_level: str,
        gate_direction: str,
    ) -> float:
        if gate_level not in {"high", "extreme"}:
            return 0.0
        if abs(float(brent_change)) < 3.0 or gate_direction not in {"up", "down"}:
            return 0.0

        brent_direction = "up" if brent_change > 0 else "down"
        if gate_direction != brent_direction:
            return 0.0

        base = float(base_predicted_delta)
        event_sign = 1.0 if gate_direction == "up" else -1.0
        if base * event_sign > 0:
            return 0.0

        magnitude = 40.0 if gate_level == "extreme" else 25.0
        if math.isclose(base, 0.0, abs_tol=0.0001):
            magnitude *= 0.5
        return round(event_sign * magnitude, 4)

    def _soft_cap_spot_jump_adjustment(
        self,
        *,
        base_predicted_delta: float,
        jump_delta: float,
        spot_payload: dict[str, Any],
    ) -> float:
        components = spot_payload.get("components") or []
        hard_component_names = {"炼厂报价调整", "实际成交重心"}
        has_hard_price_evidence = any(str(item.get("name")) in hard_component_names for item in components if isinstance(item, dict))
        if has_hard_price_evidence:
            return float(jump_delta)

        base = float(base_predicted_delta)
        jump = float(jump_delta)
        if base == 0.0 or jump == 0.0 or base * jump <= 0:
            return jump

        soft_total_cap = 35.0
        total = base + jump
        if abs(total) <= soft_total_cap:
            return jump
        capped_total = math.copysign(soft_total_cap, total)
        return round(capped_total - base, 4)

    def _range_half_width(
        self,
        *,
        horizon: str,
        claims: list[AgentClaim],
        context_metadata: dict[str, Any] | None,
        score_value: float,
        event_gate: dict[str, Any],
    ) -> float:
        half_width = HORIZON_BASE_RANGE_HALF_WIDTH.get(horizon, 50.0)
        data_mode = str((context_metadata or {}).get("market_data_mode") or "")
        data_reason = str((context_metadata or {}).get("market_data_reason") or "")
        if "fallback" in data_mode or data_reason:
            half_width += 20.0 if horizon == "D1" else 35.0
        if "brent_daily_report_missing" in data_reason or "brent_daily_report_stale" in data_reason:
            half_width += 60.0 if horizon == "D1" else 100.0
        if abs(score_value) < 0.18:
            half_width += 15.0 if horizon == "D1" else 30.0
        directions = [
            claim.direction
            for claim in claims
            if claim.agent_name not in {"event_risk_agent"} and abs(float(claim.numeric_signals.get("weighted_score", 0.0))) > 0.01
        ]
        if "up" in directions and "down" in directions:
            half_width += 15.0 if horizon in {"D1", "D3"} else 35.0
        gate_level = str(event_gate.get("level") or event_gate.get("risk_level") or "low").lower()
        if gate_level == "medium":
            half_width += 15.0
        elif gate_level == "high":
            half_width += 35.0
        elif gate_level == "extreme":
            half_width += 60.0
        return round(float(half_width), 4)

    def _build_business_direction(
        self,
        *,
        predicted_delta: float,
        direction_label: str,
        probabilities: dict[str, float],
        calibration: CalibrationResult,
        confidence_label: str,
        confidence_score: float,
        event_gate: dict[str, Any],
    ) -> dict[str, Any]:
        range_half_width = max(float(calibration.rmse), 1.0)
        move_vs_range = abs(float(predicted_delta)) / range_half_width
        point_direction = "up" if predicted_delta > 0 else "down" if predicted_delta < 0 else "flat"
        directional_probability = float(probabilities.get(point_direction, 0.0)) if point_direction != "flat" else float(probabilities.get("flat", 0.0))
        strongest_direction, strongest_probability = max(probabilities.items(), key=lambda item: float(item[1]))

        if point_direction == "flat" or move_vs_range < 0.25:
            tone = "flat"
            label = "震荡"
        elif predicted_delta > 0:
            tone = "strong_up" if move_vs_range >= 0.8 and directional_probability >= 0.65 and confidence_score >= 0.6 else "weak_up"
            label = "明确上涨" if tone == "strong_up" else "震荡偏强"
        else:
            tone = "strong_down" if move_vs_range >= 0.8 and directional_probability >= 0.65 and confidence_score >= 0.6 else "weak_down"
            label = "明确下跌" if tone == "strong_down" else "震荡偏弱"

        gate_level = str(event_gate.get("level") or "low")
        if gate_level in {"high", "extreme"}:
            tone = "manual_review"
            label = "等待人工确认" if gate_level == "extreme" else "事件扰动中"

        allow_strong_action = tone in {"strong_up", "strong_down"} and gate_level in {"low", "medium"}
        if gate_level == "extreme":
            usable_level = "not_usable"
            operating_grade = "D"
            usage = "不作为自动经营依据，只能人工复核后使用。"
        elif gate_level == "high" or move_vs_range < 0.5 or confidence_label == "low":
            usable_level = "degraded"
            operating_grade = "C"
            usage = "可作盘中观察，不允许直接触发放量、重仓补库或大幅让利。"
        elif allow_strong_action:
            usable_level = "usable"
            operating_grade = "A" if move_vs_range >= 1.0 else "B"
            usage = "可作为经营动作触发依据，但仍需执行止损条件。"
        else:
            usable_level = "degraded"
            operating_grade = "B"
            usage = "可触发轻动作，不作为强单边依据。"

        if move_vs_range < 0.5:
            reason = f"预测变化 {predicted_delta:.2f} 元/吨，小于状态桶区间半宽的50%（区间半宽 {range_half_width:.2f}）。"
        elif allow_strong_action:
            reason = f"预测变化达到状态桶区间半宽的 {move_vs_range:.2f} 倍，方向概率 {directional_probability:.1%}。"
        else:
            reason = f"预测变化达到状态桶区间半宽的 {move_vs_range:.2f} 倍，但方向概率或可靠度未达到强单边阈值。"
        if gate_level in {"high", "extreme"}:
            reason = f"{reason} 事件风控等级为{event_gate.get('label')}，自动结论降级。"

        return {
            "tone": tone,
            "display_label": label,
            "point_direction": point_direction,
            "strongest_probability_direction": strongest_direction,
            "strongest_probability": round(float(strongest_probability), 4),
            "directional_probability": round(directional_probability, 4),
            "range_half_width": round(range_half_width, 4),
            "move_vs_range": round(move_vs_range, 4),
            "move_vs_rmse": round(move_vs_range, 4),
            "allow_strong_action": allow_strong_action,
            "usable_level": usable_level,
            "operating_grade": operating_grade,
            "usage": usage,
            "reason": reason,
        }

    def _build_event_gate(
        self,
        *,
        row: pd.Series,
        claims: list[AgentClaim],
        news_items: list[dict[str, Any]],
        report_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        brent = self._float_or_none(row.get("brent_active_settlement"))
        brent_change = self._float_or_none(row.get("brent_change_1d")) or 0.0
        brent_change_pct = abs(brent_change) / brent if brent and brent > 0 else 0.0
        event_claim = next((claim for claim in claims if claim.agent_name == "event_risk_agent"), None)
        event_score = abs(float((event_claim.numeric_signals if event_claim else {}).get("raw_score", 0.0)))
        event_risk_gate = ((event_claim.structured_payload if event_claim else {}).get("risk_gate") or {})
        keyword_hits = 0
        keywords = ("战争", "袭击", "制裁", "断供", "封锁", "霍尔木兹", "红海", "OPEC减产", "减产")
        text_parts = [str(report_payload.get("markdown", ""))] if report_payload else []
        text_parts.extend(
            " ".join(str(item.get(key, "")) for key in ("headline", "title", "content"))
            for item in news_items[:20]
        )
        joined_text = "\n".join(text_parts)
        keyword_hits = sum(joined_text.count(keyword) for keyword in keywords)

        level = "low"
        label = "低"
        action = "模型正常展示。"
        llm_level = str(event_risk_gate.get("risk_level") or "").lower()
        if llm_level in {"extreme", "high", "medium"}:
            level = llm_level
        if brent_change_pct >= 0.05 and keyword_hits >= 2:
            level = "extreme"
            label = "极高"
            action = "暂停自动经营结论，切换人工决策。"
        elif brent_change_pct >= 0.03 or event_score >= 70.0 or (keyword_hits >= 5 and brent_change_pct >= 0.02):
            level = "high"
            label = "高"
            action = "隐藏强单边措辞，人工确认后再执行。"
        elif brent_change_pct >= 0.01 or event_score >= 35.0 or keyword_hits > 0 or news_items:
            level = "medium"
            label = "中"
            action = "保留预测，但经营建议降为轻动作。"
        if level == "medium":
            label = "中"
            action = "保留预测，但经营建议降为轻动作。"
        elif level == "high":
            label = "高"
            action = "隐藏强单边措辞，人工确认后再执行。"
        elif level == "extreme":
            label = "极高"
            action = "暂停自动经营结论，切换人工决策。"

        return {
            "level": level,
            "label": label,
            "brent_change_1d": round(brent_change, 4),
            "brent_change_pct_1d": round(brent_change_pct, 4),
            "event_score_abs": round(event_score, 4),
            "keyword_hits": keyword_hits,
            "news_count": len(news_items),
            "llm_risk_gate": event_risk_gate,
            "action": action,
        }

    def _build_brent_forecast_basis(
        self,
        *,
        report_payload: dict[str, Any] | None,
        horizon: str,
        feature_settlement: float | None,
    ) -> dict[str, Any]:
        if not report_payload:
            return {}
        signals = report_payload.get("signals") or {}
        realtime_context = signals.get("realtime_context") or {}
        horizon_code = str(horizon or "D1").upper()
        if horizon_code == "D1":
            forecast = signals.get("daily_forecast") or {}
            forecast_source = "daily_forecast"
        else:
            forecast = (signals.get("horizon_forecasts") or {}).get(horizon_code) or {}
            forecast_source = f"horizon_forecasts.{horizon_code}"
        previous_settlement = self._float_or_none(realtime_context.get("previous_settlement"))
        settlement = self._float_or_none(signals.get("brent_settlement"))
        settlement_change = self._float_or_none(signals.get("brent_settlement_change_usd"))
        forecast_point = self._float_or_none(forecast.get("point_value"))
        if forecast_point is not None and settlement is not None:
            scorecard_change = forecast_point - settlement
            scorecard_change_source = "forecast_point_minus_report_settlement"
            anchor_basis = "report_settlement"
        elif forecast_point is not None and feature_settlement is not None:
            scorecard_change = forecast_point - feature_settlement
            scorecard_change_source = "forecast_point_minus_feature_settlement_fallback"
            anchor_basis = "feature_settlement_fallback"
        else:
            scorecard_change = self._float_or_none(forecast.get("change_usd"))
            scorecard_change_source = str(forecast.get("change_source") or "forecast_change_fallback")
            anchor_basis = "forecast_change_fallback"
        return {
            "report_date": report_payload.get("report_date"),
            "report_title": report_payload.get("title"),
            "horizon": horizon_code,
            "forecast_source": forecast_source,
            "forecast_point_usd": forecast_point,
            "forecast_anchor_close_usd": self._float_or_none(forecast.get("anchor_close")),
            "anchor_basis": anchor_basis,
            "feature_settlement_usd": feature_settlement,
            "brent_settlement_usd": settlement,
            "brent_settlement_change_usd": settlement_change,
            "previous_settlement_usd": previous_settlement,
            "scorecard_change_usd": scorecard_change,
            "scorecard_change_source": scorecard_change_source,
            "change_vs_realtime_usd": self._float_or_none(forecast.get("change_vs_realtime_usd")),
            "formula": "Brent涨跌=Brent预测点位-日报当天settlement；无日报settlement时才回退到特征结算价或日报原始涨跌。",
        }

    def _resolve_brent_point_for_crack(
        self,
        *,
        report_payload: dict[str, Any] | None,
        horizon: str,
        fallback_brent: float | None,
    ) -> float | None:
        if not report_payload:
            return fallback_brent
        signals = report_payload.get("signals") or {}
        horizon_code = str(horizon or "D1").upper()
        if horizon_code == "D1":
            forecast = signals.get("daily_forecast") or {}
        else:
            forecast = (signals.get("horizon_forecasts") or {}).get(horizon_code) or {}
        return self._float_or_none(forecast.get("point_value")) or fallback_brent

    def _resolve_cny_mid_from_row(self, row: pd.Series) -> float | None:
        for column in (
            "cny_mid_rate",
            "usd_cny_mid_rate",
            "usdcny_mid",
            "usd_cny",
            "cny_exchange_rate",
            "rmb_exchange_rate_mid",
            "人民币汇率中间价",
        ):
            value = self._float_or_none(row.get(column))
            if value is not None:
                return value
        return None

    def _calculate_gasoline_crack_spread(
        self,
        *,
        market_price: float | None,
        brent_price: float | None,
        cny_mid: float | None,
    ) -> float | None:
        if market_price is None or brent_price is None or cny_mid is None:
            return None
        return (
            market_price / (1.0 + VAT_RATE)
            - GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON
            - brent_price * BARREL_TO_TON_RATIO * cny_mid
        )

    def _load_llm_label_result(
        self,
        cache_key: str,
        memory_cache: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        if cache_key in memory_cache:
            cached = memory_cache[cache_key]
            return dict(cached) if isinstance(cached, dict) else None
        result = self._llm_label_cache.load(cache_key)
        if result is None:
            return None
        memory_cache[cache_key] = dict(result)
        return dict(result)

    def _save_llm_label_result(
        self,
        cache_key: str,
        result: dict[str, Any],
        *,
        task: str,
        memory_cache: dict[str, dict[str, Any]],
    ) -> None:
        memory_cache[cache_key] = dict(result)
        try:
            self._llm_label_cache.save(cache_key, result, task=task)
        except Exception:
            return

    def _round_or_none(self, value: Any, digits: int = 4) -> float | None:
        numeric = self._float_or_none(value)
        return round(numeric, digits) if numeric is not None else None

    def _float_or_none(self, value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    def _build_input_hash(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _claim_score(claims: list[AgentClaim], agent_name: str) -> float:
    for claim in claims:
        if claim.agent_name == agent_name:
            return float(claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score", 0.0)))
    return 0.0
