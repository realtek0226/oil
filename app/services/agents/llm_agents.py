from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.clients.llm_client import LlmClient
from app.models.common import AgentClaim


LLM_AGENT_NAMES = [
    "llm_event_interpreter_agent",
    "llm_consistency_reviewer_agent",
    "llm_manual_review_agent",
]


def build_llm_agent_claims(
    *,
    llm_client: LlmClient,
    enabled: bool,
    subject: str,
    as_of_date: date,
    horizon: str,
    direction_label: str,
    point_value: float,
    range_lower: float,
    range_upper: float,
    score_value: float,
    deterministic_claims: list[AgentClaim],
    raw_context: dict[str, Any],
) -> list[AgentClaim]:
    if not enabled or not llm_client.enabled:
        return []

    payload = {
        "subject": subject,
        "as_of_date": as_of_date.isoformat(),
        "horizon": horizon,
        "fixed_prediction": {
            "direction_label": direction_label,
            "point_value": round(point_value, 2),
            "range_lower": round(range_lower, 2),
            "range_upper": round(range_upper, 2),
            "score_value": round(score_value, 4),
        },
        "deterministic_claims": [_claim_payload(item) for item in deterministic_claims],
        "context": _compact_context(raw_context),
        "review_context": _derived_review_context(raw_context, direction_label),
    }
    try:
        result = llm_client.summarize_json(
            system_prompt=_system_prompt(),
            user_prompt=json.dumps(payload, ensure_ascii=False, default=str),
        )
    except Exception:
        return []

    item_mapping = _normalize_result_mapping(result)
    claims: list[AgentClaim] = []
    for agent_name in LLM_AGENT_NAMES:
        item = item_mapping.get(agent_name)
        claim = _claim_from_payload(agent_name, item)
        if claim is not None:
            claims.append(claim)
    return claims


def _system_prompt() -> str:
    return (
        "你是国内成品油研究智能体集群中的LLM评审层，由山东地炼现货、原油事件、发改委调价机制、"
        "炼厂供需、区域套利、量化校准六位专家的规则共同约束。你不能重新预测价格，也不能修改输入中的方向、点位、区间、综合分。"
        "你的任务不是点评，而是输出可核查、可复核、可执行的结构化审查。必须只输出JSON对象，顶层包含 items 数组，"
        "每个元素必须有 agent_name，且只允许以下三个：llm_event_interpreter_agent、llm_consistency_reviewer_agent、llm_manual_review_agent。"
        "通用字段：direction(up/down/flat)、confidence_label(low/medium/high)、confidence_score(0-1)、summary、evidence、review_result、recommendation。"
        "禁止使用空泛词作为原因：资讯面、消息面、政策面、基本面、供需面、利多已消化、影响有限、建议关注、后续观察、存在不确定性。"
        "如果缺少事实，必须写'缺少哪项事实'并触发人工复核，不得编造。"
        "事件归因智能体必须输出 event_type、event_time、event_subject、affected_area、transmission_chain、impact_horizon、risk_level、facts_to_verify。"
        "传导链必须写成：事件 -> Brent -> 调价预期 -> 主营/地炼报价 -> 山东92#或区域价差。必须引用事件时间、主体、Brent变化、调价窗口天数、国内现货是否响应。"
        "一致性评审智能体必须输出 probability_conflict、highest_probability_direction、point_direction、calibration_summary、conflict_items、suggested_display_tone。"
        "必须引用状态桶、桶样本量、P50、P25、P75、区间半宽、上涨/震荡/下跌概率。若最高概率方向与最终方向不一致，或预测变化小于区间半宽的50%，"
        "不得给强单边措辞，suggested_display_tone 应写震荡偏强或震荡偏弱。"
        "人工复核智能体必须输出 manual_review_required、review_level、review_owner、review_questions、pass_action、fail_action、risk_stop。"
        "复核问题必须具体到岗位和数据，例如贸易岗确认实际成交价、物流岗确认运费、销售岗确认账期、研究员确认调价窗口和Brent变化率。"
        "经营触发要包含采购/销售/库存/跨区发运。区域价差必须同时检查：区域价差=目标区域92#-山东92#，净回款=区域价差-运费。"
        "当前系统没有损耗、装卸、资金成本、信用缓冲等结构化数据，不计算也不展示这些扣减项。经营动作以净回款价差为准："
        ">60且连续维持可扩大外发，30-60可小批量试发，0-30只做客户维护，<0原则上不外发。"
    )


def _claim_payload(claim: AgentClaim) -> dict[str, Any]:
    return {
        "agent_name": claim.agent_name,
        "direction": claim.direction,
        "confidence_label": claim.confidence_label,
        "confidence_score": claim.confidence_score,
        "summary": claim.summary,
        "evidence": claim.evidence[:5],
        "numeric_signals": claim.numeric_signals,
    }


def _compact_context(raw_context: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "current_price",
        "current_spread",
        "predicted_delta",
        "probabilities",
        "calibration",
        "point_mapping",
        "risk_range_half_width",
        "core_range_half_width",
        "latest_policy_notice",
        "days_to_next_window",
        "business_days_since_ceiling_adjust",
        "refined_news_count",
        "event_news_count",
        "policy_notice_count",
        "event_report_title",
        "event_report_date",
        "business_scorecard_comparison",
        "current_shandong_price",
        "current_counter_region_price",
        "freight_estimate",
        "netback_spread",
        "predicted_netback_spread",
        "trade_action",
        "freight_review_required",
        "spread_formula",
        "counter_region_name",
        "business_direction",
        "event_gate",
        "market_data_mode",
        "market_data_reason",
    ]
    return {key: raw_context.get(key) for key in keys if key in raw_context}


def _derived_review_context(raw_context: dict[str, Any], direction_label: str) -> dict[str, Any]:
    probabilities = raw_context.get("probabilities") or {}
    probability_pairs = {
        key: _safe_float(probabilities.get(key))
        for key in ("up", "flat", "down")
        if probabilities.get(key) is not None
    }
    highest_probability_direction = None
    highest_probability = None
    if probability_pairs:
        highest_probability_direction, highest_probability = max(probability_pairs.items(), key=lambda item: item[1])
    predicted_delta = _safe_float(raw_context.get("predicted_delta"))
    calibration = raw_context.get("calibration") or {}
    point_mapping = raw_context.get("point_mapping") or {}
    range_half_width = _safe_float(
        point_mapping.get("range_half_width")
        or calibration.get("range_half_width")
        or raw_context.get("risk_range_half_width")
    )
    move_vs_range_ratio = None
    if predicted_delta is not None and range_half_width and range_half_width > 0:
        move_vs_range_ratio = abs(predicted_delta) / range_half_width
    point_direction = "flat"
    if predicted_delta is not None:
        if predicted_delta > 0:
            point_direction = "up"
        elif predicted_delta < 0:
            point_direction = "down"
    return {
        "highest_probability_direction": highest_probability_direction,
        "highest_probability": highest_probability,
        "final_direction_label": direction_label,
        "point_direction": point_direction,
        "probability_conflict": bool(highest_probability_direction and highest_probability_direction != direction_label),
        "predicted_delta": predicted_delta,
        "range_half_width": range_half_width,
        "move_vs_range_ratio": round(move_vs_range_ratio, 4) if move_vs_range_ratio is not None else None,
        "weak_move_vs_range": bool(move_vs_range_ratio is not None and move_vs_range_ratio < 0.5),
        "calibration_sample_size": calibration.get("sample_size"),
        "bucket_schema": point_mapping.get("bucket_schema"),
        "bucket": point_mapping.get("bucket"),
        "bucket_range": point_mapping.get("bucket_range"),
        "selected_buckets": point_mapping.get("selected_buckets"),
        "bucket_sample_size": point_mapping.get("sample_size"),
        "bucket_status": point_mapping.get("status"),
        "p25_delta": point_mapping.get("p25_delta"),
        "p50_delta": point_mapping.get("p50_delta"),
        "p75_delta": point_mapping.get("p75_delta"),
    }


def _normalize_result_mapping(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        if any(name in result for name in LLM_AGENT_NAMES):
            return {name: result.get(name) for name in LLM_AGENT_NAMES}
        items = result.get("items") or result.get("agents") or result.get("results")
        if isinstance(items, list):
            return _items_to_mapping(items)
    if isinstance(result, list):
        return _items_to_mapping(result)
    return {}


def _items_to_mapping(items: list[Any]) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        agent_name = str(item.get("agent_name") or item.get("id") or "").strip()
        if agent_name in LLM_AGENT_NAMES:
            mapping[agent_name] = item
    return mapping


def _claim_from_payload(agent_name: str, payload: Any) -> AgentClaim | None:
    if not isinstance(payload, dict):
        return None
    summary = _clean_text(payload.get("summary")) or _default_summary(agent_name)
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
    evidence_items = [_clean_text(item) for item in evidence if _clean_text(item)]
    recommendation = _clean_text(payload.get("recommendation"))
    review_result = _clean_text(payload.get("review_result"))
    structured_payload = {
        "llm_agent": True,
        "review_result": review_result,
        "recommendation": recommendation,
        "does_not_affect_price": True,
    }
    for key in (
        "event_type",
        "event_time",
        "event_subject",
        "affected_area",
        "transmission_chain",
        "impact_horizon",
        "risk_level",
        "facts_to_verify",
        "probability_conflict",
        "highest_probability_direction",
        "point_direction",
        "calibration_summary",
        "conflict_items",
        "suggested_display_tone",
        "manual_review_required",
        "review_level",
        "review_owner",
        "review_questions",
        "pass_action",
        "fail_action",
        "risk_stop",
    ):
        if key in payload:
            structured_payload[key] = payload.get(key)
    return AgentClaim(
        agent_name=agent_name,
        direction=_direction(payload.get("direction")),
        confidence_label=_confidence_label(payload.get("confidence_label")),
        confidence_score=_confidence_score(payload.get("confidence_score")),
        summary=summary,
        evidence=evidence_items[:6],
        numeric_signals={
            "score": 0.0,
            "raw_score": 0.0,
            "weight": 0.0,
            "weighted_score": 0.0,
        },
        structured_payload=structured_payload,
    )


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _direction(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"up", "down", "flat"} else "flat"


def _confidence_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"low", "medium", "high"} else "medium"


def _confidence_score(value: Any) -> float:
    try:
        return round(max(0.0, min(float(value), 1.0)), 4)
    except (TypeError, ValueError):
        return 0.5


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _default_summary(agent_name: str) -> str:
    mapping = {
        "llm_event_interpreter_agent": "LLM事件归因智能体完成事件、政策和资讯传导审查。",
        "llm_consistency_reviewer_agent": "LLM一致性评审智能体完成规则结论一致性检查。",
        "llm_manual_review_agent": "LLM人工复核智能体完成复核触发项检查。",
    }
    return mapping.get(agent_name, "LLM评审智能体完成审查。")
