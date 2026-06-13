from __future__ import annotations

from typing import Any

from app.models.common import AgentClaim


def build_reliability_score(
    *,
    claims: list[AgentClaim],
    predicted_delta: float,
    direction_label: str,
    range_half_width: float,
    direction_threshold: float,
    calibration_rmse: float,
    sample_size: int,
    context_metadata: dict[str, Any] | None,
) -> tuple[str, float, dict[str, float | str]]:
    """Reliability means operating-reference quality, not hit probability."""
    signal_strength = _clip(abs(predicted_delta) / max(range_half_width, direction_threshold, 1.0))
    factor_alignment = _factor_alignment(claims, direction_label)
    calibration_quality = _calibration_quality(claims, range_half_width, calibration_rmse, sample_size)
    source_data_quality = _data_quality(context_metadata)
    agent_input_quality = _agent_input_quality(claims)
    data_quality = min(source_data_quality, agent_input_quality)
    event_stability = _event_stability(claims)

    score = _clip(
        0.12
        + 0.26 * signal_strength
        + 0.22 * factor_alignment
        + 0.18 * calibration_quality
        + 0.16 * data_quality
        + 0.06 * event_stability,
        lower=0.2,
        upper=0.95,
    )
    if source_data_quality <= 0.45:
        score = min(score, 0.49)
    label = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return (
        label,
        round(score, 4),
        {
            "meaning": "研判可靠度，不等同于价格命中概率",
            "signal_strength": round(signal_strength, 4),
            "factor_alignment": round(factor_alignment, 4),
            "calibration_quality": round(calibration_quality, 4),
            "data_quality": round(data_quality, 4),
            "source_data_quality": round(source_data_quality, 4),
            "agent_input_quality": round(agent_input_quality, 4),
            "event_stability": round(event_stability, 4),
            "business_scorecard_usage": "业务打分模型仅作独立基准对比，不参与综合置信度",
        },
    )


def _factor_alignment(claims: list[AgentClaim], direction_label: str) -> float:
    weighted_scores = [
        float(claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score", 0.0)))
        for claim in claims
        if claim.agent_name not in {"business_scorecard_agent", "event_risk_agent"}
    ]
    total_abs = sum(abs(value) for value in weighted_scores)
    if total_abs <= 0:
        return 0.5
    if direction_label == "flat":
        net_score = abs(sum(weighted_scores))
        return _clip(1.0 - net_score / max(total_abs, 1.0), lower=0.35, upper=1.0)
    expected_sign = 1.0 if direction_label == "up" else -1.0
    supporting = sum(abs(value) for value in weighted_scores if value * expected_sign > 0)
    return _clip(supporting / total_abs)


def _data_quality(context_metadata: dict[str, Any] | None) -> float:
    mode = str((context_metadata or {}).get("market_data_mode") or "")
    reason = str((context_metadata or {}).get("market_data_reason") or "")
    if "brent_daily_report_missing" in reason or "brent_daily_report_stale" in reason:
        return 0.45
    if "fallback" in mode or reason:
        return 0.72
    if mode and mode not in {"eta", "wind_eta", "wind_price_api"}:
        return 0.86
    return 1.0


def _agent_input_quality(claims: list[AgentClaim]) -> float:
    available = 0.0
    missing = 0.0
    for claim in claims:
        if claim.agent_name in {"business_scorecard_agent", "event_risk_agent"} or claim.agent_name.startswith("llm_"):
            continue
        quality = claim.structured_payload.get("data_quality") or {}
        available += float(quality.get("available_count") or 0.0)
        missing += float(quality.get("missing_count") or 0.0)
    total = available + missing
    if total <= 0:
        return 1.0
    return _clip(available / total, lower=0.35, upper=1.0)


def _calibration_quality(
    claims: list[AgentClaim],
    range_half_width: float,
    calibration_rmse: float,
    sample_size: int,
) -> float:
    """Quality of historical score calibration used for operating-reference pricing."""
    active_claims = [
        claim
        for claim in claims
        if claim.agent_name not in {"business_scorecard_agent", "event_risk_agent"}
        and abs(float(claim.numeric_signals.get("weighted_score", 0.0))) > 0.0
    ]
    coverage = _clip(len(active_claims) / 6.0)
    range_penalty = _clip(1.0 - max(range_half_width - 50.0, 0.0) / 260.0, lower=0.45, upper=1.0)
    sample_hint = _clip(sample_size / 120.0) if sample_size else 0.0
    error_hint = _clip(1.0 - min(calibration_rmse / 220.0, 0.7)) if sample_size else 0.0
    calibration_hint = sample_hint * error_hint
    return _clip(0.35 + 0.35 * coverage + 0.15 * range_penalty + 0.15 * calibration_hint, lower=0.35, upper=0.92)


def _event_stability(claims: list[AgentClaim]) -> float:
    for claim in claims:
        if claim.agent_name != "event_risk_agent":
            continue
        gate = claim.structured_payload.get("risk_gate") or claim.structured_payload
        risk_level = str(gate.get("risk_level") or gate.get("level") or "low").lower()
        return {
            "none": 1.0,
            "low": 1.0,
            "medium": 0.82,
            "high": 0.58,
            "extreme": 0.35,
            "三级": 0.82,
            "二级": 0.58,
            "一级": 0.35,
        }.get(risk_level, 0.85)
    return 1.0


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))
