from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from app.models.api import AgentHealthStatus
from app.models.common import PredictionResult
from app.services.run_repository import FileRunRepository, StoredJsonRecord


SCOPE_LABELS = {
    "outright": "山东92#现货预测",
    "regional_spread": "区域价差预测",
}

AGENT_REGISTRY: list[dict[str, Any]] = [
    {
        "agent_name": "chief_orchestrator",
        "label": "总控编排智能体",
        "role": "任务拆解、证据聚合与最终结论",
        "layer": "chief",
        "optimizable": False,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "business_scorecard_agent",
        "label": "业务打分模型智能体",
        "role": "执行《山东成品油市场价预测打分模型》配置化规则，形成业务基线分",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": [SCOPE_LABELS["outright"]],
    },
    {
        "agent_name": "crude_cost_agent",
        "label": "原油成本智能体",
        "role": "Brent、裂解价差与调油成本传导",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "market_structure_agent",
        "label": "市场结构智能体",
        "role": "现货动量、批零价差与区域结构",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "supply_inventory_agent",
        "label": "供给库存智能体",
        "role": "炼厂利润、开工与供给弹性",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "demand_seasonality_agent",
        "label": "需求季节性智能体",
        "role": "销量、出货与季节节奏",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "refined_oil_news_agent",
        "label": "成品油资讯智能体",
        "role": "成品油快讯、全文与山东地炼动态",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "shandong_spot_jump_agent",
        "label": "山东现货跳变识别智能体",
        "role": "识别山东地炼成交、推价、抢货、低价资源扫空和急涨后回调，形成D1点位冲击修正",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": [SCOPE_LABELS["outright"]],
    },
    {
        "agent_name": "policy_cycle_agent",
        "label": "政策周期智能体",
        "role": "发改委调价窗口、批零价差与政策残余效应",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "event_risk_agent",
        "label": "事件风险智能体",
        "role": "地缘、黑天鹅与事件冲击识别",
        "layer": "subagent",
        "optimizable": True,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "agent_judge_agent",
        "label": "智能体裁判",
        "role": "审查硬数据、软信号、业务基准与最终方向是否冲突，并对点位、区间和置信度做后置裁判",
        "layer": "subagent",
        "optimizable": False,
        "downstream_targets": [SCOPE_LABELS["outright"]],
    },
    {
        "agent_name": "llm_event_interpreter_agent",
        "label": "LLM事件归因智能体",
        "role": "解释事件、政策、资讯对现货价格和价差的传导路径",
        "layer": "llm_agent",
        "optimizable": False,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "llm_consistency_reviewer_agent",
        "label": "LLM一致性评审智能体",
        "role": "检查规则智能体之间的矛盾、证据缺口和结论稳健性",
        "layer": "llm_agent",
        "optimizable": False,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
    {
        "agent_name": "llm_manual_review_agent",
        "label": "LLM人工复核智能体",
        "role": "识别需要人工确认的数据、新闻和经营动作触发项",
        "layer": "llm_agent",
        "optimizable": False,
        "downstream_targets": list(SCOPE_LABELS.values()),
    },
]

AGENT_METADATA = {item["agent_name"]: item for item in AGENT_REGISTRY}
SUBAGENT_NAMES = [item["agent_name"] for item in AGENT_REGISTRY if item["layer"] == "subagent"]
LLM_AGENT_NAMES = [item["agent_name"] for item in AGENT_REGISTRY if item["layer"] == "llm_agent"]
TRACKED_AGENT_NAMES = [*SUBAGENT_NAMES, *LLM_AGENT_NAMES]

DEFAULT_SCOPE_WEIGHTS: dict[str, dict[str, float]] = {
    "outright": {
        "business_scorecard_agent": 0.0,
        "crude_cost_agent": 0.22,
        "market_structure_agent": 0.16,
        "supply_inventory_agent": 0.20,
        "demand_seasonality_agent": 0.18,
        "refined_oil_news_agent": 0.12,
        "shandong_spot_jump_agent": 0.0,
        "policy_cycle_agent": 0.12,
        "event_risk_agent": 0.0,
        "agent_judge_agent": 0.0,
    },
    "regional_spread": {
        "business_scorecard_agent": 0.0,
        "crude_cost_agent": 0.35,
        "market_structure_agent": 1.2,
        "supply_inventory_agent": 1.0,
        "demand_seasonality_agent": 1.0,
        "refined_oil_news_agent": 0.8,
        "shandong_spot_jump_agent": 0.0,
        "policy_cycle_agent": 0.4,
        "event_risk_agent": 0.35,
        "agent_judge_agent": 0.0,
    },
}

PRODUCT_SCOPE_MAPPING = {
    "GASOLINE_92": "outright",
    "GASOLINE_92_SPREAD": "regional_spread",
}


class AgentControlService:
    def __init__(self, repository: FileRunRepository) -> None:
        self.repository = repository

    def get_catalog(self) -> dict[str, Any]:
        return {
            "chief": AGENT_METADATA["chief_orchestrator"],
            "subagents": [AGENT_METADATA[name] for name in SUBAGENT_NAMES],
            "llm_agents": [AGENT_METADATA[name] for name in LLM_AGENT_NAMES],
            "scopes": [{"scope_key": key, "scope_label": value} for key, value in SCOPE_LABELS.items()],
        }

    def get_runtime_controls(self, scope_key: str) -> dict[str, dict[str, Any]]:
        state = self._load_runtime_state()
        return state["scopes"][scope_key]

    def get_overview(self, limit_runs: int = 40) -> dict[str, Any]:
        records = self.repository.list_prediction_records(limit=limit_runs)
        state = self._load_runtime_state()
        latest_backtest = self._latest_backtest_snapshot()

        run_stats: dict[str, dict[str, Any]] = {
            agent_name: {
                "run_count": 0,
                "sum_confidence": 0.0,
                "sum_abs_contribution": 0.0,
                "last_record": None,
                "last_claim": None,
            }
            for agent_name in TRACKED_AGENT_NAMES
        }

        for record in records:
            prediction = self._prediction_from_record(record)
            if prediction is None:
                continue
            for claim in prediction.agent_claims:
                if claim.agent_name not in run_stats:
                    continue
                stats = run_stats[claim.agent_name]
                stats["run_count"] += 1
                stats["sum_confidence"] += float(claim.confidence_score)
                stats["sum_abs_contribution"] += abs(
                    float(claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score", 0.0)))
                )
                if stats["last_record"] is None:
                    stats["last_record"] = record
                    stats["last_claim"] = claim

        agents: list[dict[str, Any]] = []
        chief_status, chief_reason = self._resolve_chief_status(records)
        agents.append(
            {
                **AGENT_METADATA["chief_orchestrator"],
                "status": chief_status,
                "status_reason": chief_reason,
                "run_count": len(records),
                "last_run_id": (self._prediction_from_record(records[0]).run_id if records else None),
                "last_seen_at": (records[0].modified_at if records else None),
                "recent_direction": None,
                "recent_confidence_label": None,
                "avg_confidence_score": None,
                "avg_abs_contribution": None,
                "recent_summary": "统一调度子智能体并汇总最终结论",
                "controls": [],
            }
        )

        for agent_name in TRACKED_AGENT_NAMES:
            metadata = AGENT_METADATA[agent_name]
            stats = run_stats[agent_name]
            last_claim = stats["last_claim"]
            last_record = stats["last_record"]
            controls = []
            enabled_scopes = 0
            if metadata.get("optimizable"):
                for scope_key, scope_label in SCOPE_LABELS.items():
                    scope_state = state["scopes"][scope_key][agent_name]
                    if scope_state["enabled"]:
                        enabled_scopes += 1
                    controls.append(
                        {
                            "scope_key": scope_key,
                            "scope_label": scope_label,
                            "enabled": scope_state["enabled"],
                            "weight": round(float(scope_state["weight"]), 4),
                            "default_weight": round(float(DEFAULT_SCOPE_WEIGHTS[scope_key][agent_name]), 4),
                            "updated_at": self._parse_datetime(scope_state.get("updated_at")),
                            "source": scope_state.get("source"),
                        }
                    )
            else:
                enabled_scopes = 1

            avg_confidence = (
                round(stats["sum_confidence"] / stats["run_count"], 4) if stats["run_count"] else None
            )
            avg_abs_contribution = (
                round(stats["sum_abs_contribution"] / stats["run_count"], 4) if stats["run_count"] else None
            )
            status, reason = self._resolve_agent_status(
                enabled_scopes=enabled_scopes,
                last_record=last_record,
                avg_confidence=avg_confidence,
                run_count=stats["run_count"],
            )
            agents.append(
                {
                    **metadata,
                    "status": status,
                    "status_reason": reason,
                    "run_count": stats["run_count"],
                    "last_run_id": (self._prediction_from_record(last_record).run_id if last_record else None),
                    "last_seen_at": (last_record.modified_at if last_record else None),
                    "recent_direction": (last_claim.direction if last_claim else None),
                    "recent_confidence_label": (last_claim.confidence_label if last_claim else None),
                    "avg_confidence_score": avg_confidence,
                    "avg_abs_contribution": avg_abs_contribution,
                    "recent_summary": (last_claim.summary if last_claim else "暂无运行记录"),
                    "controls": controls,
                }
            )

        return {
            "generated_at": datetime.now(),
            "recent_run_count": len(records),
            "latest_backtest": latest_backtest,
            "agents": agents,
        }

    def get_graph(self) -> dict[str, Any]:
        overview = self.get_overview(limit_runs=12)
        status_mapping = {item["agent_name"]: item["status"] for item in overview["agents"]}
        nodes = [
            {
                "id": "chief_orchestrator",
                "label": AGENT_METADATA["chief_orchestrator"]["label"],
                "role": AGENT_METADATA["chief_orchestrator"]["role"],
                "layer": "chief",
                "status": status_mapping.get("chief_orchestrator", "idle"),
                "x": 0.5,
                "y": 0.12,
                "metadata": {"optimizable": False},
            },
            {
                "id": "forecast_hub",
                "label": "预测引擎",
                "role": "现货、区域价差与多周期计算",
                "layer": "system",
                "status": "online",
                "x": 0.5,
                "y": 0.55,
                "metadata": {"optimizable": False},
            },
            {
                "id": "research_output",
                "label": "研究输出",
                "role": "首页结论、对话再预测与晨报",
                "layer": "system",
                "status": "online",
                "x": 0.5,
                "y": 0.88,
                "metadata": {"optimizable": False},
            },
        ]
        for index, agent_name in enumerate(SUBAGENT_NAMES):
            angle = (math.tau * index) / len(SUBAGENT_NAMES)
            nodes.append(
                {
                    "id": agent_name,
                    "label": AGENT_METADATA[agent_name]["label"],
                    "role": AGENT_METADATA[agent_name]["role"],
                    "layer": "subagent",
                    "status": status_mapping.get(agent_name, "idle"),
                    "x": 0.5 + math.cos(angle) * 0.34,
                    "y": 0.52 + math.sin(angle) * 0.22,
                    "metadata": {"optimizable": True},
                }
            )
        for index, agent_name in enumerate(LLM_AGENT_NAMES):
            nodes.append(
                {
                    "id": agent_name,
                    "label": AGENT_METADATA[agent_name]["label"],
                    "role": AGENT_METADATA[agent_name]["role"],
                    "layer": "llm_agent",
                    "status": status_mapping.get(agent_name, "idle"),
                    "x": 0.25 + index * 0.25,
                    "y": 0.72,
                    "metadata": {"optimizable": False},
                }
            )
        edges = [{"source": "chief_orchestrator", "target": name, "relation": "delegates"} for name in SUBAGENT_NAMES]
        edges.extend({"source": name, "target": "forecast_hub", "relation": "feeds"} for name in SUBAGENT_NAMES)
        edges.extend({"source": "forecast_hub", "target": name, "relation": "reviews"} for name in LLM_AGENT_NAMES)
        edges.extend({"source": name, "target": "research_output", "relation": "guards"} for name in LLM_AGENT_NAMES)
        edges.append({"source": "forecast_hub", "target": "research_output", "relation": "publishes"})
        return {
            "generated_at": datetime.now(),
            "nodes": nodes,
            "edges": edges,
        }

    def list_runs(self, limit: int = 30) -> dict[str, Any]:
        records = self.repository.list_prediction_records(limit=limit)
        items = []
        for record in records:
            summary = self._build_run_summary(record)
            if summary is not None:
                items.append(summary)
        return {"items": items}

    def get_run_detail(self, run_id: str) -> dict[str, Any]:
        record = self._find_prediction_record(run_id)
        if record is None:
            raise KeyError(run_id)
        prediction = self._prediction_from_record(record)
        if prediction is None:
            raise KeyError(run_id)
        scope_key = PRODUCT_SCOPE_MAPPING.get(prediction.product_code, "outright")
        outputs: list[dict[str, Any]] = []
        for claim in prediction.agent_claims:
            metadata = AGENT_METADATA.get(claim.agent_name, {"label": claim.agent_name, "role": claim.agent_name})
            outputs.append(
                {
                    "agent_name": claim.agent_name,
                    "label": metadata.get("label", claim.agent_name),
                    "role": metadata.get("role", claim.agent_name),
                    "scope_key": scope_key,
                    "enabled": bool(claim.structured_payload.get("runtime_control", {}).get("enabled", True)),
                    "weight": self._float_or_none(
                        claim.numeric_signals.get("weight", claim.numeric_signals.get("weight_multiplier"))
                    ),
                    "raw_score": self._float_or_none(
                        claim.numeric_signals.get("raw_score", claim.numeric_signals.get("score"))
                    ),
                    "contribution": self._float_or_none(
                        claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score"))
                    ),
                    "direction": claim.direction,
                    "confidence_label": claim.confidence_label,
                    "confidence_score": round(float(claim.confidence_score), 4),
                    "summary": claim.summary,
                    "evidence": claim.evidence,
                    "numeric_signals": {
                        key: round(float(value), 4)
                        for key, value in claim.numeric_signals.items()
                        if isinstance(value, (int, float))
                    },
                    "structured_payload": claim.structured_payload,
                }
            )
        return {
            "run": self._build_run_summary(record),
            "explanation": prediction.explanation,
            "driver_summary": prediction.driver_summary,
            "operating_advice": prediction.operating_advice,
            "raw_context": prediction.raw_context,
            "factor_breakdown": prediction.factor_breakdown,
            "agent_outputs": outputs,
        }

    def get_agent_output_history(self, agent_name: str, limit: int = 20) -> dict[str, Any]:
        if agent_name not in AGENT_METADATA:
            raise KeyError(agent_name)
        records = self.repository.list_prediction_records(limit=max(limit * 4, 20))
        items: list[dict[str, Any]] = []
        for record in records:
            prediction = self._prediction_from_record(record)
            if prediction is None:
                continue
            claim = next((item for item in prediction.agent_claims if item.agent_name == agent_name), None)
            if claim is None:
                continue
            items.append(
                {
                    "run": self._build_run_summary(record),
                    "output": {
                        "agent_name": claim.agent_name,
                        "label": AGENT_METADATA[agent_name]["label"],
                        "role": AGENT_METADATA[agent_name]["role"],
                        "scope_key": PRODUCT_SCOPE_MAPPING.get(prediction.product_code, "outright"),
                        "enabled": bool(claim.structured_payload.get("runtime_control", {}).get("enabled", True)),
                        "weight": self._float_or_none(
                            claim.numeric_signals.get("weight", claim.numeric_signals.get("weight_multiplier"))
                        ),
                        "raw_score": self._float_or_none(
                            claim.numeric_signals.get("raw_score", claim.numeric_signals.get("score"))
                        ),
                        "contribution": self._float_or_none(
                            claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score"))
                        ),
                        "direction": claim.direction,
                        "confidence_label": claim.confidence_label,
                        "confidence_score": round(float(claim.confidence_score), 4),
                        "summary": claim.summary,
                        "evidence": claim.evidence,
                        "numeric_signals": {
                            key: round(float(value), 4)
                            for key, value in claim.numeric_signals.items()
                            if isinstance(value, (int, float))
                        },
                        "structured_payload": claim.structured_payload,
                    },
                }
            )
            if len(items) >= limit:
                break
        return {"agent_name": agent_name, "label": AGENT_METADATA[agent_name]["label"], "items": items}

    def get_optimization_state(self) -> dict[str, Any]:
        state = self._load_runtime_state()
        proposals = self._load_proposals()
        latest = proposals[0] if proposals else None
        pending = [proposal for proposal in proposals if proposal.get("status") == "pending"]
        return {
            "generated_at": datetime.now(),
            "scopes": [self._scope_controls_for_response(scope_key, state) for scope_key in SCOPE_LABELS],
            "latest_proposal": self._proposal_to_response(latest) if latest else None,
            "pending_proposals": [self._proposal_to_response(item) for item in pending],
        }

    def generate_optimization_proposal(self, lookback_runs: int = 40) -> dict[str, Any]:
        state = self._load_runtime_state()
        proposals = self._load_proposals()
        for proposal in proposals:
            if proposal.get("status") == "pending":
                proposal["status"] = "superseded"

        recent_records = self.repository.list_prediction_records(limit=lookback_runs)
        backtest_snapshot = self._latest_backtest_snapshot()
        suggestions: list[dict[str, Any]] = []
        recommended_state = self._deep_copy_state(state)

        for scope_key, scope_label in SCOPE_LABELS.items():
            scope_records = [record for record in recent_records if self._record_scope(record) == scope_key]
            scope_stats = self._collect_scope_stats(scope_records)
            for agent_name in SUBAGENT_NAMES:
                current_control = state["scopes"][scope_key][agent_name]
                stats = scope_stats.get(agent_name, {})
                suggestion = self._suggest_control_adjustment(
                    scope_key=scope_key,
                    scope_label=scope_label,
                    agent_name=agent_name,
                    current_control=current_control,
                    stats=stats,
                    backtest_snapshot=backtest_snapshot,
                )
                if suggestion is None:
                    continue
                suggestions.append(suggestion)
                recommended_state["scopes"][scope_key][agent_name]["enabled"] = suggestion["proposed_enabled"]
                recommended_state["scopes"][scope_key][agent_name]["weight"] = suggestion["proposed_weight"]

        summary = (
            f"基于最近 {len(recent_records)} 次预测运行生成 {len(suggestions)} 条可执行建议"
            if suggestions
            else f"基于最近 {len(recent_records)} 次预测运行，当前未生成新的权重调整建议"
        )
        rationale = self._build_proposal_rationale(backtest_snapshot, suggestions)

        proposal = {
            "proposal_id": f"agtopt-{uuid.uuid4().hex[:10]}",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "confirmed_at": None,
            "reviewer": None,
            "note": None,
            "summary": summary,
            "rationale": rationale,
            "backtest_snapshot": backtest_snapshot,
            "suggestions": suggestions,
            "recommended_state": recommended_state,
        }
        proposals.insert(0, proposal)
        self.repository.save_optimization_proposals({"items": proposals})
        return {
            "proposal": self._proposal_to_response(proposal),
            "state": self.get_optimization_state(),
        }

    def confirm_optimization_proposal(
        self,
        proposal_id: str,
        *,
        approved: bool,
        reviewer: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        proposals = self._load_proposals()
        proposal = next((item for item in proposals if item.get("proposal_id") == proposal_id), None)
        if proposal is None:
            raise KeyError(proposal_id)
        if proposal.get("status") != "pending":
            raise ValueError("Only pending proposals can be confirmed.")

        now = datetime.now().isoformat()
        proposal["confirmed_at"] = now
        proposal["reviewer"] = reviewer or "manual_review"
        proposal["note"] = note

        if approved:
            proposal["status"] = "confirmed"
            state = proposal["recommended_state"]
            state["updated_at"] = now
            state["updated_by"] = proposal_id
            for scope_key in SCOPE_LABELS:
                for agent_name in SUBAGENT_NAMES:
                    state["scopes"][scope_key][agent_name]["updated_at"] = now
                    state["scopes"][scope_key][agent_name]["source"] = proposal_id
            self.repository.save_agent_control_state(state)
        else:
            proposal["status"] = "rejected"

        for item in proposals:
            if item is proposal:
                continue
            if item.get("status") == "pending":
                item["status"] = "superseded"

        self.repository.save_optimization_proposals({"items": proposals})
        return {
            "proposal": self._proposal_to_response(proposal),
            "state": self.get_optimization_state(),
        }

    def _build_run_summary(self, record: StoredJsonRecord) -> dict[str, Any] | None:
        prediction = self._prediction_from_record(record)
        if prediction is None:
            return None

        scope_key = PRODUCT_SCOPE_MAPPING.get(prediction.product_code, "outright")
        if scope_key == "regional_spread":
            counter_region_name = str(prediction.raw_context.get("counter_region_name") or prediction.region_code).strip()
            title = f"{counter_region_name}-山东 92#价差 {prediction.horizon}"
            region_label = f"{counter_region_name}-山东"
            product_label = "92#区域价差"
        else:
            title = f"山东 92#现货 {prediction.horizon}"
            region_label = "山东"
            product_label = "92#现货"

        return {
            "run_id": prediction.run_id,
            "run_type": scope_key,
            "title": title,
            "product_label": product_label,
            "region_label": region_label,
            "as_of_date": prediction.as_of_date,
            "target_date": prediction.target_date,
            "horizon": prediction.horizon,
            "direction_label": prediction.direction_label,
            "point_value": prediction.point_value,
            "range_lower": prediction.range_lower,
            "range_upper": prediction.range_upper,
            "confidence_label": prediction.confidence_label,
            "confidence_score": prediction.confidence_score,
            "created_at": record.modified_at,
        }

    def _record_scope(self, record: StoredJsonRecord) -> str:
        prediction = self._prediction_from_record(record)
        if prediction is None:
            return "outright"
        return PRODUCT_SCOPE_MAPPING.get(prediction.product_code, "outright")

    def _collect_scope_stats(self, records: list[StoredJsonRecord]) -> dict[str, dict[str, float]]:
        stats: dict[str, dict[str, float]] = {
            agent_name: {
                "run_count": 0.0,
                "sum_confidence": 0.0,
                "sum_abs_contribution": 0.0,
                "alignment_hits": 0.0,
            }
            for agent_name in SUBAGENT_NAMES
        }
        for record in records:
            prediction = self._prediction_from_record(record)
            if prediction is None:
                continue
            for claim in prediction.agent_claims:
                if claim.agent_name not in stats:
                    continue
                item = stats[claim.agent_name]
                contribution = abs(
                    float(claim.numeric_signals.get("weighted_score", claim.numeric_signals.get("score", 0.0)))
                )
                item["run_count"] += 1.0
                item["sum_confidence"] += float(claim.confidence_score)
                item["sum_abs_contribution"] += contribution
                if claim.direction == prediction.direction_label:
                    item["alignment_hits"] += 1.0

        normalized: dict[str, dict[str, float]] = {}
        for agent_name, values in stats.items():
            run_count = values["run_count"]
            normalized[agent_name] = {
                "run_count": run_count,
                "avg_confidence_score": (values["sum_confidence"] / run_count if run_count else 0.0),
                "avg_abs_contribution": (values["sum_abs_contribution"] / run_count if run_count else 0.0),
                "alignment_ratio": (values["alignment_hits"] / run_count if run_count else 0.0),
            }
        return normalized

    def _suggest_control_adjustment(
        self,
        *,
        scope_key: str,
        scope_label: str,
        agent_name: str,
        current_control: dict[str, Any],
        stats: dict[str, Any],
        backtest_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        run_count = int(stats.get("run_count", 0) or 0)
        if run_count < 6:
            return None

        avg_confidence = float(stats.get("avg_confidence_score", 0.0) or 0.0)
        avg_abs_contribution = float(stats.get("avg_abs_contribution", 0.0) or 0.0)
        alignment_ratio = float(stats.get("alignment_ratio", 0.0) or 0.0)
        current_weight = float(current_control.get("weight", DEFAULT_SCOPE_WEIGHTS[scope_key][agent_name]))
        current_enabled = bool(current_control.get("enabled", True))
        proposed_weight = current_weight
        proposed_enabled = current_enabled
        reasons: list[str] = []

        low_signal_threshold = 1.1 if scope_key == "outright" else 0.8
        high_signal_threshold = 3.2 if scope_key == "outright" else 1.6
        min_weight = 0.35 if scope_key == "outright" else 0.2
        max_weight = 1.6 if scope_key == "outright" else 1.4

        if avg_abs_contribution < low_signal_threshold and avg_confidence < 0.45:
            proposed_weight *= 0.9
            reasons.append(
                f"最近 {run_count} 次运行平均贡献仅 {avg_abs_contribution:.2f}，平均可靠度 {avg_confidence:.2f}，建议收敛权重"
            )

        if avg_abs_contribution > high_signal_threshold and avg_confidence >= 0.55 and alignment_ratio >= 0.55:
            proposed_weight *= 1.08
            reasons.append(
                f"最近 {run_count} 次运行平均贡献 {avg_abs_contribution:.2f}，与最终结论同向比例 {alignment_ratio:.2%}，建议小幅放大影响"
            )
        elif alignment_ratio <= 0.28 and avg_abs_contribution > low_signal_threshold:
            proposed_weight *= 0.85
            reasons.append(f"与最终结论同向比例仅 {alignment_ratio:.2%}，建议下调权重观察")

        delta_mae = self._float_or_none(backtest_snapshot.get("delta_mae"))
        if agent_name in {"refined_oil_news_agent", "event_risk_agent"} and delta_mae is not None:
            if delta_mae < -0.3:
                proposed_weight *= 1.05
                reasons.append(f"最近一次回测 MAE 改善 {abs(delta_mae):.2f}，保留并轻微放大资讯/事件因子")
            elif delta_mae > 0.3:
                proposed_weight *= 0.95
                reasons.append(f"最近一次回测 MAE 恶化 {delta_mae:.2f}，建议小幅收缩资讯/事件因子")

        if avg_abs_contribution < 0.25 and avg_confidence < 0.25 and run_count >= 12:
            proposed_enabled = False
            reasons.append("样本内长期低贡献且低可靠度，建议先停用观察")

        proposed_weight = round(max(min(proposed_weight, max_weight), min_weight), 4)
        if proposed_enabled == current_enabled and math.isclose(proposed_weight, current_weight, abs_tol=0.03):
            return None

        metadata = AGENT_METADATA[agent_name]
        return {
            "scope_key": scope_key,
            "scope_label": scope_label,
            "agent_name": agent_name,
            "label": metadata["label"],
            "current_enabled": current_enabled,
            "proposed_enabled": proposed_enabled,
            "current_weight": round(current_weight, 4),
            "proposed_weight": proposed_weight,
            "reason": "；".join(reasons),
            "metrics": {
                "run_count": run_count,
                "avg_confidence_score": round(avg_confidence, 4),
                "avg_abs_contribution": round(avg_abs_contribution, 4),
                "alignment_ratio": round(alignment_ratio, 4),
            },
        }

    def _build_proposal_rationale(self, backtest_snapshot: dict[str, Any], suggestions: list[dict[str, Any]]) -> str:
        if not suggestions:
            if backtest_snapshot:
                return (
                    f"最近一次回测方向准确率 {backtest_snapshot.get('direction_accuracy', '-')}"
                    f"，MAE {backtest_snapshot.get('mae', '-')}"
                    "，暂未形成需要人工确认的新建议。"
                )
            return "当前仅依据最近运行记录完成巡检，暂未形成新的权重调整建议。"

        if not backtest_snapshot:
            return "建议主要基于最近预测运行中的贡献度、可靠度与同向比例生成，确认后将直接进入下一轮预测。"

        return (
            f"建议同时参考最近运行记录与最新回测结果：方向准确率 {backtest_snapshot.get('direction_accuracy', '-')}"
            f"，MAE {backtest_snapshot.get('mae', '-')}"
            "。确认后会覆盖对应 scope 下的运行时权重。"
        )

    def _scope_controls_for_response(self, scope_key: str, state: dict[str, Any]) -> dict[str, Any]:
        controls = []
        for agent_name in SUBAGENT_NAMES:
            scope_state = state["scopes"][scope_key][agent_name]
            controls.append(
                {
                    "agent_name": agent_name,
                    "label": AGENT_METADATA[agent_name]["label"],
                    "role": AGENT_METADATA[agent_name]["role"],
                    "enabled": scope_state["enabled"],
                    "weight": round(float(scope_state["weight"]), 4),
                    "default_weight": round(float(DEFAULT_SCOPE_WEIGHTS[scope_key][agent_name]), 4),
                    "updated_at": self._parse_datetime(scope_state.get("updated_at")),
                    "source": scope_state.get("source"),
                }
            )
        return {
            "scope_key": scope_key,
            "scope_label": SCOPE_LABELS[scope_key],
            "controls": controls,
        }

    def _proposal_to_response(self, proposal: dict[str, Any]) -> dict[str, Any]:
        return {
            "proposal_id": proposal["proposal_id"],
            "status": proposal["status"],
            "created_at": self._parse_datetime(proposal.get("created_at")),
            "confirmed_at": self._parse_datetime(proposal.get("confirmed_at")),
            "reviewer": proposal.get("reviewer"),
            "note": proposal.get("note"),
            "summary": proposal.get("summary") or "",
            "rationale": proposal.get("rationale") or "",
            "backtest_snapshot": proposal.get("backtest_snapshot") or {},
            "suggestions": proposal.get("suggestions") or [],
        }

    def _load_runtime_state(self) -> dict[str, Any]:
        default_state = self._default_runtime_state()
        stored = self.repository.load_agent_control_state() or {}
        scopes = stored.get("scopes") if isinstance(stored, dict) else {}

        for scope_key in SCOPE_LABELS:
            stored_scope = scopes.get(scope_key, {}) if isinstance(scopes, dict) else {}
            for agent_name in SUBAGENT_NAMES:
                stored_control = stored_scope.get(agent_name, {}) if isinstance(stored_scope, dict) else {}
                default_state["scopes"][scope_key][agent_name] = {
                    "enabled": bool(stored_control.get("enabled", default_state["scopes"][scope_key][agent_name]["enabled"])),
                    "weight": round(
                        float(stored_control.get("weight", default_state["scopes"][scope_key][agent_name]["weight"])),
                        4,
                    ),
                    "updated_at": stored_control.get("updated_at"),
                    "source": stored_control.get("source"),
                }

        default_state["updated_at"] = stored.get("updated_at")
        default_state["updated_by"] = stored.get("updated_by")
        return default_state

    def _default_runtime_state(self) -> dict[str, Any]:
        return {
            "updated_at": None,
            "updated_by": None,
            "scopes": {
                scope_key: {
                    agent_name: {
                        "enabled": True,
                        "weight": round(float(weight), 4),
                        "updated_at": None,
                        "source": "default",
                    }
                    for agent_name, weight in weights.items()
                }
                for scope_key, weights in DEFAULT_SCOPE_WEIGHTS.items()
            },
        }

    def _load_proposals(self) -> list[dict[str, Any]]:
        payload = self.repository.load_optimization_proposals()
        items = payload.get("items", [])
        if not isinstance(items, list):
            return []
        return items

    def _resolve_agent_status(
        self,
        *,
        enabled_scopes: int,
        last_record: StoredJsonRecord | None,
        avg_confidence: float | None,
        run_count: int,
    ) -> tuple[AgentHealthStatus, str]:
        if enabled_scopes == 0:
            return "disabled", "已在全部预测链路中停用"
        if run_count == 0 or last_record is None:
            return "idle", "尚未发现该智能体的历史运行记录"
        if avg_confidence is not None and avg_confidence < 0.35:
            return "attention", f"近几次运行平均可靠度仅 {avg_confidence:.2f}"
        return "online", f"近 {run_count} 次运行有产出，最近一次更新时间 {last_record.modified_at:%Y-%m-%d %H:%M}"

    def _resolve_chief_status(self, records: list[StoredJsonRecord]) -> tuple[AgentHealthStatus, str]:
        if not records:
            return "idle", "尚未发现主控编排记录"
        return "online", f"最近一次编排产出时间 {records[0].modified_at:%Y-%m-%d %H:%M}"

    def _prediction_from_record(self, record: StoredJsonRecord | None) -> PredictionResult | None:
        if record is None:
            return None
        try:
            return PredictionResult.model_validate(record.payload)
        except Exception:
            return None

    def _find_prediction_record(self, run_id: str) -> StoredJsonRecord | None:
        for record in self.repository.list_prediction_records(limit=500):
            if record.key == run_id:
                return record
        return None

    def _latest_backtest_snapshot(self) -> dict[str, Any]:
        records = self.repository.list_backtest_records(limit=1)
        if not records:
            return {}
        payload = records[0].payload
        comparison = payload.get("comparison") or {}
        return {
            "variant": payload.get("variant"),
            "sample_size": payload.get("sample_size"),
            "direction_accuracy": payload.get("direction_accuracy"),
            "mae": payload.get("mae"),
            "delta_direction_accuracy": comparison.get("delta_direction_accuracy"),
            "delta_mae": comparison.get("delta_mae"),
            "recorded_at": records[0].modified_at.isoformat(),
        }

    def _deep_copy_state(self, state: dict[str, Any]) -> dict[str, Any]:
        scopes = {
            scope_key: {
                agent_name: dict(control)
                for agent_name, control in scope_controls.items()
            }
            for scope_key, scope_controls in state["scopes"].items()
        }
        return {
            "updated_at": state.get("updated_at"),
            "updated_by": state.get("updated_by"),
            "scopes": scopes,
        }

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _float_or_none(self, value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return round(float(value), 4)
        except Exception:
            return None
