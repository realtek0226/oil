from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.clients.llm_client import LlmClient
from app.models.common import AgentClaim, BusinessAdvice


GENERIC_EXPLANATION_TERMS = (
    "资讯面",
    "消息面",
    "政策周期",
    "供需面",
    "基本面",
    "市场情绪",
)


@dataclass(frozen=True)
class NarrativeBundle:
    explanation: str
    driver_summary: list[str]
    operating_advice: list[BusinessAdvice]


def enrich_prediction_narratives_batch(
    *,
    llm_client: LlmClient,
    enabled: bool,
    items: list[dict[str, Any]],
) -> dict[str, NarrativeBundle]:
    item_mapping = {str(item["id"]): item for item in items}
    fallback_mapping = {
        item_id: NarrativeBundle(
            explanation=_select_base_explanation(str(item.get("fallback_explanation") or ""), item),
            driver_summary=item["fallback_driver_summary"],
            operating_advice=item["fallback_operating_advice"],
        )
        for item_id, item in item_mapping.items()
    }
    if not enabled or not llm_client.enabled or not items:
        return fallback_mapping

    system_prompt = _batch_system_prompt()
    user_prompt = json.dumps({"items": [_serialize_item(item) for item in items]}, ensure_ascii=False)

    try:
        payload = _request_json(llm_client=llm_client, system_prompt=system_prompt, user_prompt=user_prompt)
        results = payload.get("items")
        if not isinstance(results, list):
            return fallback_mapping

        enriched = dict(fallback_mapping)
        for item_payload in results:
            if not isinstance(item_payload, dict):
                continue
            item_id = str(item_payload.get("id") or "").strip()
            if not item_id or item_id not in fallback_mapping:
                continue
            fallback = fallback_mapping[item_id]
            source_item = item_mapping[item_id]
            enriched[item_id] = NarrativeBundle(
                explanation=_normalize_explanation(
                    item_payload.get("explanation"),
                    fallback.explanation,
                    source_item,
                ),
                driver_summary=_normalize_driver_summary(
                    item_payload.get("driver_summary"),
                    fallback.driver_summary,
                ),
                operating_advice=_normalize_operating_advice(
                    item_payload.get("operating_advice"),
                    fallback.operating_advice,
                ),
            )
        return enriched
    except Exception:
        return fallback_mapping


def enrich_prediction_narrative(
    *,
    llm_client: LlmClient,
    enabled: bool,
    subject: str,
    direction_label: str | None = None,
    point_value: float | None = None,
    range_lower: float | None = None,
    range_upper: float | None = None,
    confidence_label: str | None = None,
    confidence_score: float | None = None,
    score_value: float | None = None,
    fallback_explanation: str,
    fallback_driver_summary: list[str],
    fallback_operating_advice: list[BusinessAdvice],
    claims: list[AgentClaim],
    raw_context: dict[str, Any],
    scenario_text: str | None,
) -> NarrativeBundle:
    item = {
        "id": subject,
        "subject": subject,
        "direction_label": direction_label,
        "point_value": point_value,
        "range_lower": range_lower,
        "range_upper": range_upper,
        "confidence_label": confidence_label,
        "confidence_score": confidence_score,
        "score_value": score_value,
        "fallback_explanation": fallback_explanation,
        "fallback_driver_summary": fallback_driver_summary,
        "fallback_operating_advice": fallback_operating_advice,
        "claims": claims,
        "raw_context": raw_context,
        "scenario_text": scenario_text,
    }
    base_explanation = _select_base_explanation(fallback_explanation, item)

    if not enabled or not llm_client.enabled:
        return NarrativeBundle(
            explanation=base_explanation,
            driver_summary=fallback_driver_summary,
            operating_advice=fallback_operating_advice,
        )

    system_prompt = _single_system_prompt()
    user_prompt = json.dumps({"item": _serialize_item(item)}, ensure_ascii=False)

    try:
        payload = _request_json(llm_client=llm_client, system_prompt=system_prompt, user_prompt=user_prompt)
        explanation = _normalize_explanation(payload.get("explanation"), base_explanation, item)
        driver_summary = _normalize_driver_summary(payload.get("driver_summary"), fallback_driver_summary)
        operating_advice = _normalize_operating_advice(payload.get("operating_advice"), fallback_operating_advice)
        return NarrativeBundle(
            explanation=explanation,
            driver_summary=driver_summary,
            operating_advice=operating_advice,
        )
    except Exception:
        return NarrativeBundle(
            explanation=base_explanation,
            driver_summary=fallback_driver_summary,
            operating_advice=fallback_operating_advice,
        )


def _batch_system_prompt() -> str:
    return (
        "你是国内成品油研究总监，负责把结构化预测结果整理成研究工作台可直接展示的内容。"
        "请只输出严格 JSON，不要输出 markdown，不要加任何前缀或解释。"
        "你的任务不是重新预测点位，而是根据既有预测结论、因子证据和上下文，生成 explanation、driver_summary、operating_advice。"
        "必须遵守："
        "1. 不得改动输入中的方向、点位、区间、研判可靠度、当前价格等数值；"
        "2. explanation 必须把原因说清楚，优先写具体数据、具体事件、具体价差或具体窗口天数；"
        "3. 禁止用“资讯面”“消息面”“政策周期”“供需面”“基本面”“市场情绪”这类空泛词直接充当原因；"
        "4. 如果提到政策，必须写明距离下一轮调价窗口多少个工作日，或上次汽油调整了多少元/吨；"
        "5. 如果提到资讯，必须写明具体新闻主题、炼厂检修/开工/出货、区域流向等事实，不能只写“资讯面支撑”；"
        "6. 如果提到成本，必须点名 Brent、裂解价差、MTBE、石脑油中的至少一项具体变化；"
        "7. driver_summary 写成 2到3条结论式短句；"
        "8. operating_advice 写成 2到3条可执行建议，必须包含建议动作、触发数据、执行幅度和止损条件；priority 只能是 high、medium、low。"
        "9. 若 raw_context 中 business_direction.usable_level 为 degraded 或 not_usable，不得写强补库、强去库、明确放量等强单边建议。"
        "10. 区域价差建议必须以净回款价差为经营依据；当前没有损耗、装卸、资金成本、信用缓冲数据，不计算也不展示这些扣减项。"
        '输出格式：{"items":[{"id":"...","explanation":"...","driver_summary":["..."],'
        '"operating_advice":[{"title":"...","action":"...","rationale":"...","priority":"high|medium|low"}]}]}'
    )


def _single_system_prompt() -> str:
    return (
        "你是国内成品油研究总监，负责把结构化预测结果整理成研究工作台可直接展示的内容。"
        "请只输出严格 JSON，不要输出 markdown。"
        "你不能改动输入中的方向、点位、区间、概率、当前价格，只能根据这些事实写研究语言。"
        "要求："
        "1. explanation 写成 2到4句的研判摘要；"
        "2. driver_summary 写 2到3条核心驱动；"
        "3. operating_advice 写 2到3条经营建议，必须包含动作、触发数据、执行幅度和止损条件；"
        "4. explanation 不允许出现“资讯面”“消息面”“政策周期”“供需面”“基本面”这类空泛原因；"
        "5. 任何政策、资讯、成本描述都必须落到具体数据、具体事件或具体时间窗口。"
        "6. 若 business_direction 显示结论降级，只能写轻动作或人工复核；区域价差必须按净回款价差给建议。"
        '{"explanation":"...",'
        '"driver_summary":["...","..."],'
        '"operating_advice":[{"title":"...","action":"...","rationale":"...","priority":"high|medium|low"}]}'
    )


def _request_json(*, llm_client: LlmClient, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    try:
        return llm_client.summarize_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        content = llm_client.summarize(system_prompt=system_prompt, user_prompt=user_prompt)
        return _parse_json_payload(content)


def _serialize_item(item: dict[str, Any]) -> dict[str, Any]:
    claims = item.get("claims") or []
    raw_context = item.get("raw_context") or {}
    return {
        "id": str(item.get("id") or ""),
        "subject": str(item.get("subject") or ""),
        "scenario_text": item.get("scenario_text"),
        "prediction": {
            "direction_label": item.get("direction_label"),
            "point_value": _round_or_none(item.get("point_value")),
            "range_lower": _round_or_none(item.get("range_lower")),
            "range_upper": _round_or_none(item.get("range_upper")),
            "confidence_label": item.get("confidence_label"),
            "confidence_score": _round_or_none(item.get("confidence_score")),
            "score_value": _round_or_none(item.get("score_value")),
        },
        "claims": [_compact_claim(claim) for claim in claims],
        "raw_context": _compact_context(raw_context),
    }


def _compact_claim(claim: AgentClaim | dict[str, Any]) -> dict[str, Any]:
    payload = claim if isinstance(claim, dict) else claim.model_dump()
    numeric_signals = payload.get("numeric_signals") or {}
    return {
        "agent_name": payload.get("agent_name"),
        "direction": payload.get("direction"),
        "confidence_label": payload.get("confidence_label"),
        "confidence_score": _round_or_none(payload.get("confidence_score")),
        "summary": payload.get("summary"),
        "evidence": [str(item).strip() for item in (payload.get("evidence") or [])[:3] if str(item).strip()],
        "score": _round_or_none(numeric_signals.get("weighted_score", numeric_signals.get("score"))),
        "numeric_signals": {
            key: _round_or_none(value)
            for key, value in numeric_signals.items()
            if isinstance(value, (int, float))
        },
    }


def _compact_context(raw_context: dict[str, Any]) -> dict[str, Any]:
    keep_keys = [
        "current_price",
        "predicted_delta",
        "current_spread",
        "current_shandong_price",
        "current_counter_region_price",
        "counter_region_name",
        "counter_region_code",
        "spread_change_1d",
        "spread_change_3d",
        "days_to_next_window",
        "business_days_since_ceiling_adjust",
        "refined_news_count",
        "event_news_count",
        "policy_notice_count",
        "refined_news_sources",
        "event_news_sources",
        "event_report_date",
        "event_report_title",
        "event_report_horizons",
        "horizon_label",
        "target_mode",
        "switches",
        "business_direction",
        "event_gate",
        "predicted_netback_spread",
        "trade_action",
        "freight_review_required",
    ]
    compact = {key: raw_context.get(key) for key in keep_keys if key in raw_context}
    probabilities = raw_context.get("probabilities")
    if isinstance(probabilities, dict):
        compact["probabilities"] = {
            key: _round_or_none(value)
            for key, value in probabilities.items()
            if isinstance(value, (int, float))
        }
    calibration = raw_context.get("calibration")
    if isinstance(calibration, dict):
        compact["calibration"] = {
            key: _round_or_none(value)
            for key, value in calibration.items()
            if isinstance(value, (int, float))
        }
    latest_policy_notice = raw_context.get("latest_policy_notice")
    if isinstance(latest_policy_notice, dict):
        compact["latest_policy_notice"] = {
            "title": latest_policy_notice.get("title"),
            "publish_date": latest_policy_notice.get("publish_date"),
            "effective_time": latest_policy_notice.get("effective_time"),
            "gasoline_change_yuan_per_ton": _round_or_none(latest_policy_notice.get("gasoline_change_yuan_per_ton")),
            "diesel_change_yuan_per_ton": _round_or_none(latest_policy_notice.get("diesel_change_yuan_per_ton")),
        }
    return compact


def _parse_json_payload(content: str) -> dict[str, Any]:
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_explanation(value: Any, fallback: str, item: dict[str, Any]) -> str:
    text = _clean_text(str(value or ""), fallback)
    if _is_generic_explanation(text) or _looks_mechanical_explanation(text):
        return _select_base_explanation(fallback, item)
    return text


def _select_base_explanation(explanation: str, item: dict[str, Any]) -> str:
    cleaned = _clean_text(explanation, "")
    if cleaned and not _is_generic_explanation(cleaned) and not _looks_mechanical_explanation(cleaned):
        return cleaned
    concrete = _build_concrete_explanation(item)
    return concrete or cleaned


def _build_concrete_explanation(item: dict[str, Any]) -> str:
    subject = str(item.get("subject") or "该预测").strip()
    direction_label = str(item.get("direction_label") or "").strip()
    point_value = _round_or_none(item.get("point_value"))
    range_lower = _round_or_none(item.get("range_lower"))
    range_upper = _round_or_none(item.get("range_upper"))
    raw_context = item.get("raw_context") or {}
    driver_summary = item.get("fallback_driver_summary") or []

    direction_map = {"up": "上行", "down": "下行", "flat": "震荡"}
    direction_text = direction_map.get(direction_label, "波动")

    current_value = _round_or_none(raw_context.get("current_price"))
    current_label = "当前价格"
    if current_value is None:
        current_value = _round_or_none(raw_context.get("current_spread"))
        current_label = "当前价差"

    lead_parts: list[str] = []
    if point_value is not None:
        lead_parts.append(f"{subject}预计{direction_text}至{point_value:.2f}元/吨附近")
    else:
        lead_parts.append(f"{subject}预计以{direction_text}为主")
    if current_value is not None:
        lead_parts.append(f"{current_label}{current_value:.2f}元/吨")
    if range_lower is not None and range_upper is not None:
        lead_parts.append(f"参考区间{range_lower:.2f}-{range_upper:.2f}元/吨")

    details = [_humanize_driver_line(line) for line in driver_summary[:3] if str(line).strip()]
    policy_detail = _build_policy_detail(raw_context)
    if policy_detail:
        details.append(policy_detail)

    if not lead_parts and not details:
        return ""
    if details:
        return "，".join(lead_parts) + "。" + "；".join(details) + "。"
    return "，".join(lead_parts) + "。"


def _build_policy_detail(raw_context: dict[str, Any]) -> str:
    latest_policy_notice = raw_context.get("latest_policy_notice")
    days_to_next_window = _round_or_none(raw_context.get("days_to_next_window"))
    gasoline_change = None
    if isinstance(latest_policy_notice, dict):
        gasoline_change = _round_or_none(latest_policy_notice.get("gasoline_change_yuan_per_ton"))

    fragments: list[str] = []
    if gasoline_change is not None:
        direction = "上调" if gasoline_change > 0 else "下调" if gasoline_change < 0 else "持平"
        fragments.append(f"上轮发改委汽油{direction}{abs(gasoline_change):.0f}元/吨")
    if days_to_next_window is not None and days_to_next_window <= 3:
        fragments.append(f"距下一轮调价窗口约{days_to_next_window:.0f}个工作日")
    return "，".join(fragments)


def _is_generic_explanation(text: str) -> bool:
    cleaned = _clean_text(text, "")
    if not cleaned:
        return True
    return any(term in cleaned for term in GENERIC_EXPLANATION_TERMS)


def _looks_mechanical_explanation(text: str) -> bool:
    cleaned = _clean_text(text, "")
    machine_markers = (
        "score=",
        "crude_cost_agent",
        "market_structure_agent",
        "supply_inventory_agent",
        "demand_seasonality_agent",
        "refined_oil_news_agent",
        "policy_cycle_agent",
        "event_risk_agent",
    )
    return any(marker in cleaned for marker in machine_markers)


def _clean_text(value: str, fallback: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text or fallback


def _strip_trailing_punct(text: str) -> str:
    return str(text).strip().rstrip("。；;，, ")


def _humanize_driver_line(text: str) -> str:
    line = _strip_trailing_punct(text)
    replacements = [
        (r"sales_1w=([-+]?\d+(?:\.\d+)?)", lambda m: f"销量周环比{float(m.group(1)):.1f}%"),
        (r"shipments_1w=([-+]?\d+(?:\.\d+)?)", lambda m: f"出货周环比{float(m.group(1)):.1f}%"),
        (r"Brent 1d=([-+]?\d+(?:\.\d+)?)", lambda m: f"Brent单日变动{float(m.group(1)):.1f}"),
        (r"gas crack 3d=([-+]?\d+(?:\.\d+)?)", lambda m: f"汽油裂解价差3日变动{float(m.group(1)):.1f}"),
        (r"MTBE 3d=([-+]?\d+(?:\.\d+)?)", lambda m: f"MTBE 3日变动{float(m.group(1)):.1f}"),
        (r"naphtha 3d=([-+]?\d+(?:\.\d+)?)", lambda m: f"石脑油3日变动{float(m.group(1)):.1f}"),
        (r"refining_profit_1w=([-+]?\d+(?:\.\d+)?)", lambda m: f"地炼利润周变动{float(m.group(1)):.1f}"),
        (r"crude_run_1w=([-+]?\d+(?:\.\d+)?)", lambda m: f"原油加工量周变动{float(m.group(1)):.1f}"),
        (r"sd_gas92_change_3d=([-+]?\d+(?:\.\d+)?)", lambda m: f"山东92# 3日变动{float(m.group(1)):.1f}"),
        (r"sd_cn_spread=([-+]?\d+(?:\.\d+)?)", lambda m: f"山东-全国价差{float(m.group(1)):.1f}元/吨"),
        (r"ceiling_gap=([-+]?\d+(?:\.\d+)?)", lambda m: f"批零价差{float(m.group(1)):.1f}元/吨"),
        (r"last_adjust_delta=([-+]?\d+(?:\.\d+)?)", lambda m: f"上轮汽油调整{float(m.group(1)):.0f}元/吨"),
        (r"days_to_next_window=([-+]?\d+(?:\.\d+)?)", lambda m: f"距下一轮调价窗口{float(m.group(1)):.0f}个工作日"),
        (r"target_spread=([-+]?\d+(?:\.\d+)?)", lambda m: f"当前区域价差{float(m.group(1)):.1f}元/吨"),
        (r"target_spread_change_3d=([-+]?\d+(?:\.\d+)?)", lambda m: f"区域价差3日变动{float(m.group(1)):.1f}"),
    ]
    for pattern, builder in replacements:
        line = re.sub(pattern, builder, line)
    return line


def _normalize_driver_summary(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    lines = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item)).strip()
        if text:
            lines.append(text)
    return lines[:3] or fallback


def _normalize_operating_advice(value: Any, fallback: list[BusinessAdvice]) -> list[BusinessAdvice]:
    if not isinstance(value, list):
        return fallback
    normalized: list[BusinessAdvice] = []
    for item in value[:3]:
        if not isinstance(item, dict):
            continue
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        action = re.sub(r"\s+", " ", str(item.get("action") or "")).strip()
        rationale = re.sub(r"\s+", " ", str(item.get("rationale") or "")).strip()
        priority = str(item.get("priority") or "medium").strip().lower()
        if priority not in {"low", "medium", "high"}:
            priority = "medium"
        if not title or not action or not rationale:
            continue
        normalized.append(
            BusinessAdvice(
                title=title,
                action=action,
                rationale=rationale,
                priority=priority,
            )
        )
    return normalized or fallback


def _round_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    return None
