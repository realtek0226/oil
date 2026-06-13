from __future__ import annotations

from typing import Any

from app.models.common import AgentClaim


HARD_EVIDENCE_AGENTS = {
    "crude_cost_agent",
    "market_structure_agent",
    "supply_inventory_agent",
    "demand_seasonality_agent",
    "shandong_spot_jump_agent",
    "policy_cycle_agent",
}

SOFT_EVIDENCE_AGENTS = {
    "refined_oil_news_agent",
    "event_risk_agent",
}

BASELINE_AGENTS = {
    "business_scorecard_agent",
}


def build_agent_judgement_review(
    *,
    claims: list[AgentClaim],
    predicted_delta: float,
    direction_label: str,
    direction_threshold: float,
) -> dict[str, Any]:
    """Review agent conclusions before the final operating price is shown.

    This layer is deterministic. It does not replace the score model; it only
    checks whether the model direction is supported by hard evidence, challenged
    by hard counter-evidence, or mostly driven by soft signals.
    """
    expected_sign = _direction_sign(direction_label)
    review_items: list[dict[str, Any]] = []
    hard_support = 0.0
    hard_counter = 0.0
    soft_support = 0.0
    soft_counter = 0.0
    hard_up = 0.0
    hard_down = 0.0
    soft_up = 0.0
    soft_down = 0.0
    missing_count = 0
    active_count = 0

    for claim in claims:
        if claim.agent_name.startswith("llm_"):
            continue
        evidence_type = _evidence_type(claim.agent_name)
        relation = _relation_to_direction(claim.direction, expected_sign)
        contribution = _claim_contribution(claim)
        quality = claim.structured_payload.get("data_quality") or {}
        missing_count += int(float(quality.get("missing_count") or 0))
        active_count += int(float(quality.get("available_count") or 0))

        if evidence_type != "baseline" and abs(contribution) > 0.0001:
            claim_sign = _direction_sign(claim.direction)
            if evidence_type == "hard" and claim_sign > 0:
                hard_up += abs(contribution)
            elif evidence_type == "hard" and claim_sign < 0:
                hard_down += abs(contribution)
            elif evidence_type == "soft" and claim_sign > 0:
                soft_up += abs(contribution)
            elif evidence_type == "soft" and claim_sign < 0:
                soft_down += abs(contribution)
            if evidence_type == "hard":
                if relation == "support":
                    hard_support += abs(contribution)
                elif relation == "counter":
                    hard_counter += abs(contribution)
            elif evidence_type == "soft":
                if relation == "support":
                    soft_support += abs(contribution)
                elif relation == "counter":
                    soft_counter += abs(contribution)

        review_items.append(
            {
                "agent_name": claim.agent_name,
                "evidence_type": evidence_type,
                "direction": claim.direction,
                "relation": relation,
                "contribution": round(float(contribution), 4),
                "summary": claim.summary,
                "evidence": claim.evidence[:3],
                "data_quality": quality,
            }
        )

    hard_balance = hard_support - hard_counter
    soft_balance = soft_support - soft_counter
    data_coverage = _coverage(active_count=active_count, missing_count=missing_count)
    verdict = "passed"
    display_label = "证据通过"
    range_extra_width = 0.0
    confidence_penalty = 0.0
    adjustment_delta = 0.0
    reasons: list[str] = []
    pressure_balance = (hard_up + soft_up) - (hard_down + soft_down)
    pressure_direction = "up" if pressure_balance > 0.0 else "down" if pressure_balance < 0.0 else "flat"

    if data_coverage < 0.7:
        verdict = "data_limited"
        display_label = "数据不足，降级使用"
        range_extra_width += 20.0
        confidence_penalty += 0.08
        reasons.append(f"核心智能体数据覆盖率 {data_coverage:.0%}，缺失字段偏多。")

    if direction_label != "flat" and hard_counter > hard_support + 0.04:
        verdict = "hard_counter_evidence"
        display_label = "硬反证压制"
        range_extra_width += 25.0
        confidence_penalty += 0.12
        adjustment_delta = _counter_adjustment(
            predicted_delta=predicted_delta,
            direction_label=direction_label,
            direction_threshold=direction_threshold,
        )
        reasons.append("硬数据反向证据强于同向证据，自动拉回预测幅度。")
    elif direction_label != "flat" and hard_support <= 0.02 and soft_support > 0.0:
        verdict = "soft_signal_only"
        display_label = "软信号主导"
        range_extra_width += 15.0
        confidence_penalty += 0.06
        reasons.append("当前方向主要由资讯、事件或情绪类信号支撑，硬数据验证不足。")
    elif direction_label != "flat" and hard_balance * soft_balance < 0 and abs(soft_balance) > 0.02:
        verdict = "mixed_evidence"
        display_label = "证据分歧"
        range_extra_width += 12.0
        confidence_penalty += 0.04
        reasons.append("硬数据与软信号方向不一致，经营动作需降一级。")
    elif direction_label == "flat" and abs(pressure_balance) > 0.05:
        verdict = "balanced_but_pressured"
        display_label = "震荡但有单边压力"
        range_extra_width += 10.0
        confidence_penalty += 0.03
        reasons.append("点位未突破方向阈值，但上行/下行压力并不完全均衡，需关注盘中确认。")
        hard_pressure = hard_up - hard_down
        soft_pressure = soft_up - soft_down
        if abs(hard_pressure) >= 0.20 and hard_pressure * soft_pressure >= -0.02:
            verdict = "hard_pressure_attention"
            display_label = "硬数据单边压力"
            range_extra_width += 10.0
            confidence_penalty += 0.02
            reasons.append("硬数据单边压力明显强于反向证据，裁判层只提示风险，不直接改预测点位。")

    if not reasons:
        reasons.append("硬数据、软信号与模型方向未出现明显冲突。")

    return {
        "version": "agent_judge_v1",
        "verdict": verdict,
        "display_label": display_label,
        "predicted_delta_before_review": round(float(predicted_delta), 4),
        "adjustment_delta": round(float(adjustment_delta), 4),
        "range_extra_width": round(float(range_extra_width), 4),
        "confidence_penalty": round(float(min(confidence_penalty, 0.25)), 4),
        "hard_support": round(float(hard_support), 4),
        "hard_counter": round(float(hard_counter), 4),
        "soft_support": round(float(soft_support), 4),
        "soft_counter": round(float(soft_counter), 4),
        "hard_up": round(float(hard_up), 4),
        "hard_down": round(float(hard_down), 4),
        "soft_up": round(float(soft_up), 4),
        "soft_down": round(float(soft_down), 4),
        "pressure_balance": round(float(pressure_balance), 4),
        "pressure_direction": pressure_direction,
        "data_coverage": round(float(data_coverage), 4),
        "reasons": reasons,
        "review_items": review_items,
    }


def build_agent_judge_claim(review: dict[str, Any]) -> AgentClaim:
    direction = _judge_direction(review)
    score = _judge_score(review, direction)
    display_label = str(review.get("display_label") or "证据通过")
    adjustment = float(review.get("adjustment_delta") or 0.0)
    range_extra = float(review.get("range_extra_width") or 0.0)
    penalty = float(review.get("confidence_penalty") or 0.0)
    evidence = [str(item) for item in (review.get("reasons") or [])[:4]]
    if adjustment:
        evidence.append(f"裁判点位修正 {adjustment:+.2f} 元/吨。")
    if range_extra:
        evidence.append(f"风险区间额外放宽 {range_extra:.2f} 元/吨。")
    if penalty:
        evidence.append(f"研判可靠度扣减 {penalty:.2f}。")
    if not evidence:
        evidence = ["未识别到需要裁判层干预的证据冲突。"]
    quality = _review_data_quality(review)
    return AgentClaim(
        agent_name="agent_judge_agent",
        direction=direction,
        confidence_label="medium" if penalty < 0.08 else "low",
        confidence_score=round(max(0.35, 0.75 - penalty), 4),
        summary=f"裁判层：{display_label}",
        evidence=evidence,
        numeric_signals={
            "score": round(score, 4),
            "max_score": 100.0,
            "raw_score": round(score, 4),
            "standalone_score": round(score, 4),
            "weighted_score": 0.0,
            "excluded_from_model_score": 1.0,
            "adjustment_delta": round(adjustment, 4),
            "range_extra_width": round(range_extra, 4),
            "confidence_penalty": round(penalty, 4),
        },
        structured_payload={
            "agent_judgement": review,
            "data_quality": quality,
            "runtime_control": {
                "enabled": True,
                "weight": 0.0,
                "mode": "post_model_judge",
            },
        },
    )


def apply_judgement_confidence_penalty(label: str, score: float, review: dict[str, Any]) -> tuple[str, float]:
    adjusted = max(0.2, min(0.95, float(score) - float(review.get("confidence_penalty") or 0.0)))
    if adjusted >= 0.75:
        return "high", round(adjusted, 4)
    if adjusted >= 0.5:
        return "medium", round(adjusted, 4)
    return "low", round(adjusted, 4)


def _evidence_type(agent_name: str) -> str:
    if agent_name in BASELINE_AGENTS:
        return "baseline"
    if agent_name in SOFT_EVIDENCE_AGENTS:
        return "soft"
    if agent_name in HARD_EVIDENCE_AGENTS:
        return "hard"
    return "soft"


def _direction_sign(direction_label: str) -> int:
    if direction_label == "up":
        return 1
    if direction_label == "down":
        return -1
    return 0


def _relation_to_direction(claim_direction: str, expected_sign: int) -> str:
    claim_sign = _direction_sign(claim_direction)
    if expected_sign == 0 or claim_sign == 0:
        return "neutral"
    return "support" if claim_sign == expected_sign else "counter"


def _claim_contribution(claim: AgentClaim) -> float:
    signals = claim.numeric_signals or {}
    if int(float(signals.get("excluded_from_model_score") or 0)) == 1:
        return 0.0
    if "weighted_score" in signals:
        return float(signals.get("weighted_score") or 0.0)
    raw = float(signals.get("score") or 0.0)
    max_score = max(float(signals.get("max_score") or 100.0), 1.0)
    return max(-1.0, min(1.0, raw / max_score))


def _coverage(*, active_count: int, missing_count: int) -> float:
    total = active_count + missing_count
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, active_count / total))


def _review_data_quality(review: dict[str, Any]) -> dict[str, Any]:
    available_count = 0
    missing_count = 0
    missing_fields: list[str] = []
    for item in review.get("review_items") or []:
        quality = item.get("data_quality") or {}
        available_count += int(float(quality.get("available_count") or 0))
        missing_count += int(float(quality.get("missing_count") or 0))
        missing_fields.extend(str(field) for field in quality.get("missing_fields") or [])
    total = available_count + missing_count
    return {
        "available_count": available_count,
        "missing_count": missing_count,
        "missing_fields": sorted(set(missing_fields)),
        "coverage_ratio": round(available_count / total, 4) if total else float(review.get("data_coverage") or 1.0),
        "note": "裁判层沿用上游智能体数据质量；缺失字段不做方向假设，按0分处理。",
    }


def _counter_adjustment(*, predicted_delta: float, direction_label: str, direction_threshold: float) -> float:
    if abs(float(predicted_delta)) <= max(float(direction_threshold), 1.0):
        return 0.0
    sign = 1.0 if direction_label == "up" else -1.0
    return round(-sign * min(abs(float(predicted_delta)) * 0.35, 30.0), 4)


def _pressure_adjustment(*, hard_pressure: float, direction_threshold: float) -> float:
    if abs(float(hard_pressure)) < 0.20:
        return 0.0
    sign = 1.0 if hard_pressure > 0 else -1.0
    magnitude = min(48.0, max(float(direction_threshold) + 8.0, abs(float(hard_pressure)) * 140.0))
    return round(sign * magnitude, 4)


def _judge_direction(review: dict[str, Any]) -> str:
    adjustment = float(review.get("adjustment_delta") or 0.0)
    if adjustment > 0:
        return "up"
    if adjustment < 0:
        return "down"
    direction = str(review.get("pressure_direction") or "flat")
    return direction if direction in {"up", "down", "flat"} else "flat"


def _judge_score(review: dict[str, Any], direction: str) -> float:
    if direction == "flat":
        return 0.0
    pressure = abs(float(review.get("pressure_balance") or 0.0)) * 100.0
    adjustment = min(abs(float(review.get("adjustment_delta") or 0.0)), 30.0)
    score = min(100.0, pressure + adjustment)
    return score if direction == "up" else -score
