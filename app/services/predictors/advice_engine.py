from __future__ import annotations

from typing import Any

from app.models.common import AgentClaim, BusinessAdvice


AGENT_LABELS = {
    "business_scorecard_agent": "业务打分模型",
    "crude_cost_agent": "成本",
    "market_structure_agent": "市场结构",
    "supply_inventory_agent": "供给",
    "demand_seasonality_agent": "需求",
    "refined_oil_news_agent": "成品油资讯",
    "policy_cycle_agent": "调价周期",
    "event_risk_agent": "事件风险",
    "llm_event_interpreter_agent": "LLM事件归因",
    "llm_consistency_reviewer_agent": "LLM一致性评审",
    "llm_manual_review_agent": "LLM人工复核",
}


def build_driver_summary(claims: list[AgentClaim], limit: int = 3) -> list[str]:
    ranked_claims = sorted(
        claims,
        key=lambda claim: abs(float(claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score", 0.0)))),
        reverse=True,
    )
    lines: list[str] = []
    for claim in ranked_claims[:limit]:
        score_value = float(claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score", 0.0)))
        direction_text = "利多" if score_value > 0 else "利空" if score_value < 0 else "中性"
        evidence = claim.evidence[0] if claim.evidence else claim.summary
        lines.append(f"{AGENT_LABELS.get(claim.agent_name, claim.agent_name)}{direction_text}，{evidence}")
    return lines


def build_outright_advice(
    *,
    direction_label: str,
    confidence_label: str,
    current_price: float,
    point_value: float,
    raw_context: dict[str, Any],
    claims: list[AgentClaim],
) -> list[BusinessAdvice]:
    advice: list[BusinessAdvice] = []
    predicted_delta = float(point_value - current_price)
    driver_summary = build_driver_summary(claims, limit=2)
    driver_text = "；".join(driver_summary) if driver_summary else "当前主驱动分化不强"
    business_direction = raw_context.get("business_direction") if isinstance(raw_context.get("business_direction"), dict) else {}
    event_gate = raw_context.get("event_gate") if isinstance(raw_context.get("event_gate"), dict) else {}
    move_vs_range = float(business_direction.get("move_vs_range") or business_direction.get("move_vs_rmse") or 0.0)
    display_label = str(business_direction.get("display_label") or "")
    allow_strong_action = bool(business_direction.get("allow_strong_action"))
    usable_level = str(business_direction.get("usable_level") or "")

    if usable_level in {"degraded", "not_usable"} or (business_direction and not allow_strong_action):
        action_text = "维持滚动采购和安全库存，不做方向性重仓。"
        volume_text = "不超过常规日均需求的轻量调整"
        if display_label == "震荡偏强":
            action_text = "只做逢低小批补库，不追高扩库存；报价有效期适度缩短。"
            volume_text = "小批补库，执行前复核产销率、库存和Brent变化"
        elif display_label == "震荡偏弱":
            action_text = "以销定采，优先消化高价库存；弱势客户小步快跑成交。"
            volume_text = "库存以降至安全线附近为目标，不扩大采购敞口"
        elif display_label in {"事件扰动中", "等待人工确认", "极端事件复核中"}:
            action_text = "暂停放量动作，研究员确认事件传导后再恢复报价或采购指令。"
            volume_text = "人工确认前不新增方向性敞口"
        advice.append(
            BusinessAdvice(
                title="经营动作分层",
                action=action_text,
                rationale=(
                    f"系统显示{display_label or '震荡'}，预测变化 {predicted_delta:.2f} 元/吨，"
                    f"仅为状态桶区间半宽的 {move_vs_range:.2f} 倍；{driver_text}。"
                ),
                priority="high" if usable_level == "not_usable" else "medium",
                action_type="经营",
                trigger_condition=business_direction.get("reason") or f"预测变化 {predicted_delta:.2f} 元/吨",
                volume_suggestion=volume_text,
                price_limit=round(point_value, 2),
                risk_stop="Brent单边突破、发改委窗口临近或现货成交未验证时停止方向性动作",
                owner_role="经营经理",
            )
        )
        advice.append(
            BusinessAdvice(
                title="人工复核清单",
                action="执行前复核产销率、库存天数、山东实际成交价、主营批发报价和调价窗口天数。",
                rationale=f"当前结论不是强单边信号，{business_direction.get('usage') or '只能作为盘中观察'}",
                priority="high" if event_gate.get("level") in {"high", "extreme"} else "medium",
                action_type="复核",
                trigger_condition=f"经营等级 {business_direction.get('operating_grade', 'C')}，事件等级 {event_gate.get('label', '低')}",
                volume_suggestion="复核通过后只允许轻动作",
                price_limit=round(point_value, 2),
                risk_stop="复核不通过则维持快进快出和中性库存",
                owner_role="研究员",
            )
        )

    if not advice and direction_label == "up":
        advice.append(
            BusinessAdvice(
                title="采购与库存",
                action="逢低补库，保留1-2个工作日弹性库存，避免完全空仓。",
                rationale=f"当前预测较现货抬升 {predicted_delta:.2f} 元/吨，{driver_text}。",
                priority="high" if confidence_label in {"high", "medium"} else "medium",
                action_type="采购",
                trigger_condition=f"预测较现货抬升 {predicted_delta:.2f} 元/吨",
                volume_suggestion="补至1-2个工作日弹性库存",
                price_limit=round(point_value, 2),
                risk_stop="Brent回落或区域价差收窄时暂停追涨补库",
                owner_role="采购经理",
            )
        )
        advice.append(
            BusinessAdvice(
                title="销售报价",
                action="报价以稳中偏强为主，缩短报价有效期，优先锁定高毛利订单。",
                rationale="上涨判断下，先锁利润比追求纯销量更重要，尤其适合短单和日内调价。",
                priority="medium",
                action_type="销售",
                trigger_condition="方向判断为上行且研判可靠度不低",
                volume_suggestion="优先锁定高毛利订单",
                price_limit=round(point_value, 2),
                risk_stop="成交跟进不足时恢复滚动报价",
                owner_role="销售经理",
            )
        )
    elif not advice and direction_label == "down":
        advice.append(
            BusinessAdvice(
                title="采购与库存",
                action="以销定采，控制高位库存，优先去库而不是扩库存。",
                rationale=f"当前预测较现货下移 {abs(predicted_delta):.2f} 元/吨，{driver_text}。",
                priority="high" if confidence_label in {"high", "medium"} else "medium",
                action_type="库存",
                trigger_condition=f"预测较现货下移 {abs(predicted_delta):.2f} 元/吨",
                volume_suggestion="库存降至安全线附近",
                price_limit=round(point_value, 2),
                risk_stop="政策上调或炼厂挺价时暂停低价去库",
                owner_role="经营经理",
            )
        )
        advice.append(
            BusinessAdvice(
                title="销售报价",
                action="加快出货节奏，必要时对弱势区域执行小步快跑式让利。",
                rationale="在下行窗口里，库存周转效率通常比名义挂牌价格更关键。",
                priority="medium",
                action_type="销售",
                trigger_condition="方向判断为下行且库存暴露偏高",
                volume_suggestion="弱势区域优先成交",
                price_limit=round(point_value, 2),
                risk_stop="成交放量但利润低于底线时停止让利",
                owner_role="销售经理",
            )
        )
    elif not advice:
        advice.append(
            BusinessAdvice(
                title="采购与库存",
                action="维持滚动补库和快进快出，避免方向性重仓。",
                rationale=f"当前判断偏震荡，{driver_text}，更适合保持库存中性。",
                priority="medium",
                action_type="库存",
                trigger_condition="方向判断为震荡",
                volume_suggestion="维持中性库存",
                price_limit=round(point_value, 2),
                risk_stop="Brent单边突破或突发事件升级时人工复核",
                owner_role="经营经理",
            )
        )
        advice.append(
            BusinessAdvice(
                title="销售报价",
                action="报价跟随区域价差动态调整，优先做结构性订单，不押单边。",
                rationale="震荡市里，区域流向和客户结构通常比绝对价格方向更重要。",
                priority="low",
                action_type="销售",
                trigger_condition="方向分歧且区域价差仍可交易",
                volume_suggestion="结构性订单优先",
                price_limit=round(point_value, 2),
                risk_stop="价差走弱时停止跨区追单",
                owner_role="销售经理",
            )
        )

    if confidence_label == "low":
        advice.append(
            BusinessAdvice(
                title="人工复核",
                action="本次研判可靠度偏低，采购、库存或报价动作执行前需要人工复核关键数据。",
                rationale="低可靠度通常意味着因子分歧、样本校准不足或事件扰动偏强，不能直接按单一方向放量。",
                priority="high",
                action_type="复核",
                trigger_condition="研判可靠度为低",
                volume_suggestion="复核前不做方向性重仓",
                price_limit=round(point_value, 2),
                risk_stop="复核通过后再恢复常规执行",
                owner_role="研究员",
            )
        )

    days_to_next_window = raw_context.get("days_to_next_window")
    if days_to_next_window is not None and float(days_to_next_window) <= 2.0:
        advice.append(
            BusinessAdvice(
                title="调价窗口",
                action="发改委窗口临近，减少跨窗口囤货，关注零售价兑现与终端补库节奏。",
                rationale=f"距离下一轮调价窗口约 {float(days_to_next_window):.0f} 个工作日，政策扰动会放大现货波动。",
                priority="high",
                action_type="政策",
                trigger_condition=f"距调价窗口 {float(days_to_next_window):.0f} 个工作日",
                volume_suggestion="减少跨窗口囤货",
                risk_stop="窗口兑现后重新评估采购节奏",
                owner_role="研究员",
            )
        )

    event_score = _claim_score(claims, "event_risk_agent")
    if abs(event_score) >= 4.0:
        advice.append(
            BusinessAdvice(
                title="夜盘与黑天鹅监控",
                action="保留夜盘调价和临时调运预案，重点盯地缘、OPEC和突发装置事件。",
                rationale=f"事件风险因子强度为 {event_score:.2f}，短时跳变对成品油报价传导通常快于基本面。",
                priority="high",
                action_type="锁价",
                trigger_condition=f"事件风险因子强度 {event_score:.2f}",
                volume_suggestion="保留夜盘锁单额度",
                risk_stop="事件证伪或Brent回落后关闭临时权限",
                owner_role="值班经理",
            )
        )

    return advice[:3]


def build_spread_advice(
    *,
    region_name: str,
    direction_label: str,
    current_spread: float,
    point_value: float,
    current_shandong_price: float,
    current_counter_region_price: float,
    freight_estimate: float,
    confidence_label: str,
    claims: list[AgentClaim],
    freight_review_required: bool = False,
    trade_action: dict[str, Any] | None = None,
) -> list[BusinessAdvice]:
    advice: list[BusinessAdvice] = []
    driver_summary = build_driver_summary(claims, limit=2)
    driver_text = "；".join(driver_summary) if driver_summary else "当前驱动没有显著一边倒"
    netback_point = point_value - freight_estimate
    trade_action = trade_action or {}

    action_label = str(trade_action.get("label") or ("原则停发" if netback_point < 0 else "小批试单"))
    review_note = "运费超过24小时未确认，执行前必须复核。" if freight_review_required else "运费已按当前录入口径计算。"
    advice.append(
        BusinessAdvice(
            title="跨区流向",
            action=f"{region_name}流向按“{action_label}”处理；先确认实际运费、到岸成交价和客户账期。",
            rationale=(
                f"预测区域价差 {point_value:.2f} 元/吨，扣除运费 {freight_estimate:.2f} 元/吨后，"
                f"预测净回款价差为 {netback_point:.2f} 元/吨。"
            ),
            priority="high" if netback_point > 60.0 or freight_review_required else "medium",
            action_type="跨区流向",
            trigger_condition=str(trade_action.get("trigger") or f"预测净回款价差 {netback_point:.2f} 元/吨"),
            volume_suggestion=str(trade_action.get("action") or "按净回款价差分层执行"),
            price_limit=round(current_shandong_price + max(point_value, 0.0), 2),
            risk_stop=f"{review_note} 若净回款价差连续两次转负、运费上涨或目标区域成交转弱，立即停止外发。",
            owner_role="经营经理",
        )
    )

    if direction_label == "up":
        advice.append(
            BusinessAdvice(
                title="价差窗口管理",
                action="目标区域相对山东升水有扩大迹象，可优先锁定外发订单和运力。",
                rationale=f"价差预计从 {current_spread:.2f} 走向 {point_value:.2f}，山东外发窗口可能改善。{driver_text}。",
                priority="high",
                action_type="锁价",
                trigger_condition="价差方向走扩",
                volume_suggestion="优先锁定已覆盖运费的订单",
                risk_stop="价差回落或运费上涨时取消增量计划",
                owner_role="销售经理",
            )
        )
    elif direction_label == "down":
        advice.append(
            BusinessAdvice(
                title="价差窗口管理",
                action="目标区域相对山东升水有收窄迹象，跨区订单以短单和已锁利润为主。",
                rationale=f"价差预计从 {current_spread:.2f} 走向 {point_value:.2f}，山东外发窗口可能变弱。{driver_text}。",
                priority="medium",
                action_type="销售",
                trigger_condition="价差方向收敛",
                volume_suggestion="短单为主",
                risk_stop="目标区域升水跌破运费覆盖线时暂停外发",
                owner_role="销售经理",
            )
        )
    else:
        advice.append(
            BusinessAdvice(
                title="价差窗口管理",
                action="保持滚动报价和小批量试单，不建议单边重压某一区域流向。",
                rationale=f"预测价差变化有限，{driver_text}，更适合维持灵活性。",
                priority="low",
                action_type="报价",
                trigger_condition="价差方向震荡",
                volume_suggestion="小批量滚动",
                risk_stop="价差突破运费覆盖线后重新评估",
                owner_role="经营经理",
            )
        )

    if confidence_label == "low":
        advice.append(
            BusinessAdvice(
                title="人工复核",
                action="本次价差研判可靠度偏低，外发前需要人工复核运费、到岸价和客户成交。",
                rationale="低可靠度下，价差点位只能作为观察线，不能直接作为放量依据。",
                priority="high",
                action_type="复核",
                trigger_condition="研判可靠度为低",
                volume_suggestion="未复核前不放量",
                risk_stop="复核通过后再恢复跨区执行",
                owner_role="研究员",
            )
        )

    advice.append(
        BusinessAdvice(
            title="报价策略",
            action="对外省流向报价采用到岸净回款口径，和本地成交价同步比较。",
            rationale="当前系统只掌握区域价格和运费，区域外发先按净回款价差判断，损耗、装卸、资金成本和信用缓冲暂不进入系统计算。",
            priority="medium",
            action_type="报价",
            trigger_condition="涉及外省流向报价",
            volume_suggestion="按净回款择优",
            risk_stop="净回款低于本地成交时停止跨区追单",
            owner_role="销售经理",
        )
    )
    return advice[:3]


def _claim_score(claims: list[AgentClaim], agent_name: str) -> float:
    for claim in claims:
        if claim.agent_name == agent_name:
            return float(claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score", 0.0)))
    return 0.0
