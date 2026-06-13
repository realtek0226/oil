from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any

from app.clients.llm_client import LlmClient
from app.models.common import PredictionResult
from app.services.chat_data_resolver import ChatDataResolver
from app.services.market_dataset import MarketDatasetService
from app.services.predictors.horizons import DEFAULT_HORIZONS
from app.services.predictors.shandong_gas92 import ShandongGas92Predictor
from app.services.predictors.shandong_regional_spreads import (
    ShandongRegionalSpreadPredictor,
    attach_regional_price_forecasts,
)
from app.services.run_repository import FileRunRepository


REGION_KEYWORDS = {
    "华东": "EAST_CHINA",
    "华北": "NORTH_CHINA",
    "华南": "SOUTH_CHINA",
    "华中": "CENTRAL_CHINA",
    "西北": "NORTHWEST",
    "西南": "SOUTHWEST",
    "东北": "NORTHEAST",
}


class WorkbenchService:
    def __init__(
        self,
        dataset_service: MarketDatasetService,
        predictor: ShandongGas92Predictor,
        spread_predictor: ShandongRegionalSpreadPredictor,
        llm_client: LlmClient,
        repository: FileRunRepository,
        data_resolver: ChatDataResolver | None = None,
    ) -> None:
        self.dataset_service = dataset_service
        self.predictor = predictor
        self.spread_predictor = spread_predictor
        self.llm_client = llm_client
        self.repository = repository
        self.data_resolver = data_resolver or ChatDataResolver(dataset_service)

    def chat_predict(
        self,
        *,
        message: str,
        as_of_date: date | None,
        horizon: str | None,
        use_llm_explainer: bool,
        enable_refined_news: bool,
        enable_event_risk: bool,
        user_context: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        run_date = date.today()
        target_date = as_of_date or self.dataset_service.resolve_default_prediction_as_of(run_date)
        data_query_date = as_of_date or run_date
        selected_horizon = horizon or self._infer_horizon(message)
        scenario_text = message.strip()
        request_id = f"chat-{uuid.uuid4().hex[:10]}"
        if self._is_identity_question(scenario_text):
            return {
                "message_id": request_id,
                "as_of_date": target_date,
                "selected_horizon": selected_horizon,
                "answer_only": True,
                "answer_source": "identity",
                "answer": (
                    "我是成品油研究智能体里的对话式研究助手，不是单独的定价模型。"
                    "价格结论由业务基准打分模型和多智能体综合模型共同校验生成；"
                    "我负责按你的问题调用研判结果，解释驱动原因，并给出经营建议。"
                ),
                "data_result": None,
                "outright_prediction": None,
                "regional_spread_predictions": [],
            }

        data_result = self.data_resolver.resolve(message=scenario_text, as_of_date=data_query_date)
        if data_result.answered and not self._requires_prediction_answer(scenario_text):
            return {
                "message_id": request_id,
                "as_of_date": data_query_date,
                "selected_horizon": selected_horizon,
                "answer_only": True,
                "answer_source": "database",
                "answer": self._compose_data_answer(
                    message=scenario_text,
                    data_result=data_result.to_dict(),
                    request_id=request_id,
                    user_context=user_context,
                ),
                "data_result": data_result.to_dict(),
                "outright_prediction": None,
                "regional_spread_predictions": [],
            }

        if self._is_general_llm_question(scenario_text):
            return {
                "message_id": request_id,
                "as_of_date": target_date,
                "selected_horizon": selected_horizon,
                "answer_only": True,
                "answer_source": "llm",
                "answer": self._compose_general_llm_answer(
                    message=scenario_text,
                    request_id=request_id,
                    user_context=user_context,
                ),
                "data_result": None,
                "outright_prediction": None,
                "regional_spread_predictions": [],
            }
        context = self.dataset_service.build_context(target_date)

        outright = self.predictor.run_prediction_from_context(
            context=context,
            as_of_date=target_date,
            horizon=selected_horizon,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
        )
        outright.raw_context["run_source"] = "chat"
        outright.raw_context["conversation_id"] = conversation_id
        outright.raw_context["request_user_id"] = (user_context or {}).get("user_id")
        regional = self._build_chat_regional_predictions(
            message=message,
            context=context,
            as_of_date=target_date,
            horizon=selected_horizon,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
        )
        regional = attach_regional_price_forecasts(regional, [outright])
        for prediction in regional:
            prediction.raw_context["run_source"] = "chat"
            prediction.raw_context["conversation_id"] = conversation_id
            prediction.raw_context["request_user_id"] = (user_context or {}).get("user_id")

        self.repository.save_prediction(outright)
        for prediction in regional:
            self.repository.save_prediction(prediction)

        return {
            "message_id": request_id,
            "as_of_date": target_date,
            "selected_horizon": selected_horizon,
            "answer_source": "prediction",
            "answer": self._compose_chat_answer(
                message=message,
                horizon=selected_horizon,
                outright=outright,
                regional=regional,
                request_id=request_id,
                user_context=user_context,
            ),
            "data_result": None,
            "outright_prediction": outright,
            "regional_spread_predictions": regional,
        }

    def generate_morning_briefing(self, *, as_of_date: date | None, use_llm_writer: bool) -> dict[str, Any]:
        run_date = date.today()
        target_date = as_of_date or self.dataset_service.resolve_default_prediction_as_of(run_date)
        context = self.dataset_service.build_context(target_date)

        outright_predictions = self.predictor.run_multi_horizon_predictions_from_context(
            context=context,
            as_of_date=target_date,
            horizons=DEFAULT_HORIZONS,
            use_llm_explainer=False,
            scenario_text=None,
            enable_refined_news=True,
            enable_event_risk=True,
        )
        if use_llm_writer and self.llm_client.enabled:
            try:
                d1_prediction = self.predictor.run_prediction_from_context(
                    context=context,
                    as_of_date=target_date,
                    horizon="D1",
                    use_llm_explainer=True,
                    scenario_text=None,
                    enable_refined_news=True,
                    enable_event_risk=True,
                )
                outright_predictions = [
                    d1_prediction if item.horizon == "D1" else item for item in outright_predictions
                ]
            except Exception:
                pass
        regional_predictions = self.spread_predictor.run_all_predictions_from_context(
            context=context,
            as_of_date=target_date,
            horizon="D1",
            use_llm_explainer=False,
            scenario_text=None,
            enable_refined_news=True,
            enable_event_risk=True,
        )
        regional_predictions = attach_regional_price_forecasts(regional_predictions, outright_predictions)
        policy_highlights = self._latest_policy_highlights(context.policy_items)
        event_highlights = self._event_highlights(context.news_items)

        briefing_id = f"brief-{target_date.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
        base_markdown = self._build_briefing_markdown(
            as_of_date=target_date,
            outright_predictions=outright_predictions,
            regional_predictions=regional_predictions,
            context=context.current_row.to_dict(),
            policy_items=policy_highlights,
            event_items=event_highlights,
        )

        content_markdown = base_markdown
        if use_llm_writer and self.llm_client.enabled:
            try:
                content_markdown = self.llm_client.summarize(
                    system_prompt=(
                        "你是国内成品油研究主管，请把输入的结构化晨报整理成适合业务晨会直接阅读的 Markdown。"
                        "不要改动数值结论，只重写表达，保留标题和项目符号。"
                    ),
                    user_prompt=base_markdown,
                )
            except Exception:
                content_markdown = base_markdown

        generated_at = datetime.now()
        payload = {
            "briefing_id": briefing_id,
            "title": f"成品油晨报 | {target_date.isoformat()}",
            "as_of_date": target_date.isoformat(),
            "generated_at": generated_at.isoformat(),
            "content_markdown": content_markdown,
            "outright_predictions": [item.model_dump(mode="json") for item in outright_predictions],
            "regional_spread_predictions": [item.model_dump(mode="json") for item in regional_predictions],
            "metadata": {
                "policy_count": len(context.policy_items),
                "event_news_count": len(context.news_items),
                "refined_news_count": len(context.refined_news_items),
                "market_data_reason": context.metadata.get("market_data_reason"),
                "prediction_run_date": run_date.isoformat(),
                "prediction_input_date": target_date.isoformat(),
                "price_anchor_date": context.metadata.get("price_anchor_date"),
                "snapshot_price_date": target_date.isoformat(),
                "snapshot_price_time": generated_at.isoformat(),
                "snapshot_prices": {
                    "brent_active_settlement": context.current_row.get("brent_active_settlement"),
                    "sd_gas92_market": context.current_row.get("sd_gas92_market"),
                    "cn_gas92_market": context.current_row.get("cn_gas92_market"),
                    "east_china_gas92_market": context.current_row.get("east_china_gas92_market"),
                },
                "policy_highlights": policy_highlights,
                "event_highlights": event_highlights,
            },
        }
        self.repository.save_briefing(briefing_id, payload)
        return payload

    def load_latest_briefing(self) -> dict[str, Any] | None:
        return self.repository.load_latest_briefing()

    def _build_chat_regional_predictions(
        self,
        *,
        message: str,
        context: Any,
        as_of_date: date,
        horizon: str,
        use_llm_explainer: bool,
        scenario_text: str,
        enable_refined_news: bool,
        enable_event_risk: bool,
    ) -> list[PredictionResult]:
        matched_regions = [code for keyword, code in REGION_KEYWORDS.items() if keyword in message]
        if matched_regions:
            return [
                self.spread_predictor.run_prediction_from_context(
                    context=context,
                    region_code=region_code,
                    as_of_date=as_of_date,
                    horizon=horizon,
                    use_llm_explainer=use_llm_explainer,
                    scenario_text=scenario_text,
                    enable_refined_news=enable_refined_news,
                    enable_event_risk=enable_event_risk,
                )
                for region_code in matched_regions
            ]

        predictions = self.spread_predictor.run_all_predictions_from_context(
            context=context,
            as_of_date=as_of_date,
            horizon=horizon,
            use_llm_explainer=use_llm_explainer,
            scenario_text=scenario_text,
            enable_refined_news=enable_refined_news,
            enable_event_risk=enable_event_risk,
        )
        return sorted(predictions, key=lambda item: abs(item.point_value), reverse=True)[:3]

    def _compose_chat_answer(
        self,
        *,
        message: str,
        horizon: str,
        outright: PredictionResult,
        regional: list[PredictionResult],
        request_id: str | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> str:
        fallback = self._fallback_chat_answer(horizon=horizon, outright=outright, regional=regional)
        if not self.llm_client.enabled:
            return fallback

        payload = {
            "question": message,
            "horizon": horizon,
            "outright": outright.model_dump(mode="json"),
            "regional": [item.model_dump(mode="json") for item in regional],
        }
        try:
            narrative = self.llm_client.summarize(
                system_prompt=(
                    "你是成品油研究工作台里的对话式研究助手。"
                    "请只解释原因和经营动作，不要输出新的点位、区间或方向，不得擅自改数。"
                    "输出 3 段以内的中文短答，最后补 1 条可执行经营建议。"
                ),
                user_prompt=json.dumps(payload, ensure_ascii=False),
                request_id=request_id,
                user_context=user_context,
            ).strip()
            return self._guarded_chat_answer(
                horizon=horizon,
                outright=outright,
                regional=regional,
                narrative=narrative,
            )
        except Exception:
            return fallback

    def _compose_data_answer(
        self,
        *,
        message: str,
        data_result: dict[str, Any],
        request_id: str | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> str:
        return self._fallback_data_answer(data_result)

    def _fallback_data_answer(self, data_result: dict[str, Any]) -> str:
        rows = data_result.get("rows") or []
        summary = str(data_result.get("summary") or "数据库没有查到可用数据。")
        if not rows:
            return summary
        latest = rows[-1]
        field_labels = ((data_result.get("metadata") or {}).get("field_labels") or {})
        units = ((data_result.get("metadata") or {}).get("units") or {})
        lines = [summary, "最新一条："]
        for key, value in latest.items():
            if key in {"date", "generated_at", "time"} or value is None:
                continue
            lines.append(f"- {field_labels.get(key, key)}：{value}{units.get(key, '')}")
        return "\n".join(lines[:10])

    def _compose_general_llm_answer(
        self,
        *,
        message: str,
        request_id: str | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> str:
        if not self.llm_client.enabled:
            return "当前模型未配置，系统数据库也没有命中可回答的数据，暂时不能继续回答这个问题。"
        try:
            return self.llm_client.summarize(
                system_prompt=(
                    "你是成品油研究工作台的通用问答助手。"
                    "优先说明系统数据库未命中。若当前模型接口支持联网搜索，可以使用模型自身联网能力回答；"
                    "若不支持联网，必须明确说明无法联网，不要编造新闻、价格或政策事实。"
                    "回答控制在 4 段以内。"
                ),
                user_prompt=message,
                request_id=request_id,
                user_context=user_context,
            ).strip()
        except Exception as exc:
            return f"系统数据库没有命中该问题，且当前模型调用失败：{exc}"

    def _guarded_chat_answer(
        self,
        *,
        horizon: str,
        outright: PredictionResult,
        regional: list[PredictionResult],
        narrative: str,
    ) -> str:
        deterministic_head = (
            f"按 {horizon} 口径，山东92#判断为{self._direction_text(outright.direction_label)}，"
            f"点位 {outright.point_value:.2f}，区间 {outright.range_lower:.2f}~{outright.range_upper:.2f}。"
        )
        regional_text = "；".join(
            f"{str(item.raw_context.get('counter_region_name') or item.region_code)}-山东 "
            f"{item.point_value:.2f}（{item.range_lower:.2f}~{item.range_upper:.2f}）"
            for item in regional[:3]
        )
        suffix = f"\n\n区域价差：{regional_text}" if regional_text else ""
        return f"{deterministic_head}\n\n{narrative}{suffix}"

    def _fallback_chat_answer(
        self,
        *,
        horizon: str,
        outright: PredictionResult,
        regional: list[PredictionResult],
    ) -> str:
        regional_lines = []
        for item in regional[:3]:
            region_name = str(item.raw_context.get("counter_region_name") or item.region_code)
            regional_lines.append(
                f"{region_name}-山东价差{self._direction_text(item.direction_label, is_spread=True)}，"
                f"点位 {item.point_value:.2f}，区间 {item.range_lower:.2f}~{item.range_upper:.2f}"
            )
        regional_text = "；".join(regional_lines) if regional_lines else "当前未额外返回区域价差结果。"
        advice = outright.operating_advice[0].action if outright.operating_advice else "保持滚动补库和快进快出。"
        return (
            f"问题已按 {horizon} 口径重算。山东92#现货判断为{self._direction_text(outright.direction_label)}，"
            f"点位 {outright.point_value:.2f}，区间 {outright.range_lower:.2f}~{outright.range_upper:.2f}。"
            f"{outright.explanation} 区域方面：{regional_text} 经营上建议：{advice}"
        )

    def _build_briefing_markdown(
        self,
        *,
        as_of_date: date,
        outright_predictions: list[PredictionResult],
        regional_predictions: list[PredictionResult],
        context: dict[str, Any],
        policy_items: list[dict[str, Any]],
        event_items: list[dict[str, Any]],
    ) -> str:
        price_lines = [
            f"- Brent: {self._fmt(context.get('brent_active_settlement'))}",
            f"- 山东92#: {self._fmt(context.get('sd_gas92_market'))}",
            f"- 全国92#: {self._fmt(context.get('cn_gas92_market'))}",
            f"- 华东92#: {self._fmt(context.get('east_china_gas92_market'))}",
        ]
        outlook_lines = [
            f"- {item.horizon}: {self._direction_text(item.direction_label)}，点位 {item.point_value:.2f}，区间 {item.range_lower:.2f}~{item.range_upper:.2f}"
            for item in outright_predictions
        ]
        spread_lines = [
            f"- {item.raw_context.get('counter_region_name')}-山东: {self._direction_text(item.direction_label, is_spread=True)}，点位 {item.point_value:.2f}"
            for item in regional_predictions[:4]
        ]
        advice_lines = [
            f"- {advice.title}: {advice.action}"
            for advice in (outright_predictions[0].operating_advice if outright_predictions else [])[:3]
        ]
        policy_lines = [
            f"- 政策 | {item.get('time') or '-'} | {item.get('impact') or item.get('title') or '-'} | {item.get('action') or '-'}"
            for item in policy_items[:3]
        ]
        risk_lines = [
            f"- 事件 | {item.get('time') or '-'} | {item.get('impact') or item.get('title') or '-'} | {item.get('action') or '-'} | {item.get('title') or '-'}"
            for item in event_items[:3]
        ]
        sections = [
            f"# 成品油晨报 | {as_of_date.isoformat()}",
            "## 价格快照",
            *price_lines,
            "## 多周期判断",
            *outlook_lines,
            "## 区域价差观察",
            *(spread_lines or ["- 暂无新增区域价差重点。"]),
            "## 经营建议",
            *(advice_lines or ["- 暂无新增经营建议。"]),
            "## 政策与风险",
            *(policy_lines or ["- 暂无新增政策更新。"]),
            *(risk_lines or ["- 暂无新增事件风险提示。"]),
        ]
        return "\n".join(sections)

    def _infer_horizon(self, message: str) -> str:
        text = message.upper()
        if "M1" in text or "一个月" in message or "一月" in message:
            return "M1"
        if "D3" in text or "三日" in message or "3日" in message or "三天" in message:
            return "D3"
        if "W1" in text or "下周" in message or "一周" in message:
            return "W1"
        return "D1"

    def _is_identity_question(self, message: str) -> bool:
        normalized = message.strip().lower()
        identity_patterns = (
            "你是什么模型",
            "你是啥模型",
            "你是谁",
            "介绍一下你",
            "你是什么",
            "what model are you",
            "who are you",
        )
        return any(pattern in normalized for pattern in identity_patterns)

    def _is_general_llm_question(self, message: str) -> bool:
        upper = message.upper()
        prediction_keywords = ("预测", "研判", "点位", "区间", "趋势", "经营建议", "D1", "D3", "W1", "M1")
        data_keywords = ("价格", "数据", "产销率", "开工率", "库存", "利润", "调价", "价差", "裂解", "新闻", "政策", "事件")
        if any(keyword in message or keyword in upper for keyword in prediction_keywords):
            return False
        return not any(keyword in message for keyword in data_keywords)

    def _requires_prediction_answer(self, message: str) -> bool:
        text = message.strip()
        if not text:
            return False
        upper = text.upper()
        decision_keywords = (
            "操作",
            "经营",
            "建议",
            "策略",
            "怎么办",
            "怎么操作",
            "如何处理",
            "如果",
            "继续",
            "走扩",
            "走窄",
            "补库",
            "出货",
            "锁价",
            "抢货",
            "抛货",
        )
        forecast_keywords = ("预测", "研判", "点位", "区间", "趋势", "D1", "D3", "W1", "M1")
        return any(keyword in text for keyword in decision_keywords) or any(
            keyword in text or keyword in upper for keyword in forecast_keywords
        )

    def _policy_impact_text(self, item: dict[str, Any]) -> str:
        gasoline_delta = item.get("gasoline_change_yuan_per_ton")
        diesel_delta = item.get("diesel_change_yuan_per_ton")
        impact_time = item.get("effective_time") or item.get("publish_date") or "-"
        if gasoline_delta is None and diesel_delta is None:
            return f"{impact_time} 调价窗口信息需人工核对，对现货报价有政策锚定作用"
        direction = "上调" if float(gasoline_delta or 0) > 0 else "下调" if float(gasoline_delta or 0) < 0 else "持平"
        return (
            f"{impact_time} 起发改委调价影响终端限价，"
            f"汽油{direction}{abs(float(gasoline_delta or 0)):.0f}元/吨，"
            f"柴油{direction}{abs(float(diesel_delta or 0)):.0f}元/吨"
        )

    def _policy_action_text(self, item: dict[str, Any]) -> str:
        gasoline_delta = float(item.get("gasoline_change_yuan_per_ton") or 0)
        if gasoline_delta > 0:
            return "关注零售限价兑现，窗口前后减少低价放量"
        if gasoline_delta < 0:
            return "关注终端补库延后，库存和报价从严"
        return "维持跨窗口谨慎，等待新一轮调价指引"

    def _event_impact_text(self, item: dict[str, Any]) -> str:
        direction = str(item.get("direction_hint") or "").lower()
        score = item.get("relevance_score") or item.get("major_score") or 0
        impact_time = item.get("publish_time") or item.get("publish_date") or "-"
        title = item.get("headline") or item.get("title") or "事件快讯"
        if direction == "bullish":
            direction_text = "偏利多油价"
        elif direction == "bearish":
            direction_text = "偏利空油价"
        else:
            direction_text = "方向待确认"
        return f"{impact_time} 发布：{title}，判断{direction_text}，相关度 {self._fmt(score)}"

    def _event_action_text(self, item: dict[str, Any]) -> str:
        text = f"{item.get('headline') or item.get('title') or ''}{item.get('content') or ''}"
        if any(keyword in text for keyword in ("EIA", "API", "库存", "OPEC", "欧佩克", "非农")):
            return "列入日内盯盘，触发Brent急动时同步复核现货报价"
        if any(keyword in text for keyword in ("地缘", "袭击", "制裁", "红海", "霍尔木兹")):
            return "按黑天鹅预案观察，必要时保留夜盘调价权限"
        return "作为背景风险跟踪，暂不直接改变现货执行"

    def _latest_policy_highlights(self, policy_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest_by_direction: dict[str, dict[str, Any]] = {}
        for item in policy_items:
            gasoline_delta = float(item.get("gasoline_change_yuan_per_ton") or 0)
            if gasoline_delta > 0:
                direction_key = "up"
            elif gasoline_delta < 0:
                direction_key = "down"
            else:
                continue
            current = latest_by_direction.get(direction_key)
            if current is None or self._policy_sort_time(item) > self._policy_sort_time(current):
                latest_by_direction[direction_key] = item

        selected = sorted(latest_by_direction.values(), key=self._policy_sort_time, reverse=True)
        return [
            {
                "title": item.get("title"),
                "time": item.get("effective_time") or item.get("publish_date") or "-",
                "impact": self._policy_impact_text(item),
                "action": self._policy_action_text(item),
            }
            for item in selected
        ]

    def _event_highlights(self, event_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": item.get("headline") or item.get("title"),
                "time": item.get("publish_time") or item.get("publish_date") or "-",
                "source": item.get("source") or "-",
                "impact": self._event_impact_text(item),
                "action": self._event_action_text(item),
            }
            for item in event_items[:3]
        ]

    def _policy_sort_time(self, item: dict[str, Any]) -> str:
        return str(item.get("effective_time") or item.get("publish_date") or "")

    def _fmt(self, value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except Exception:
            return "-"

    def _direction_text(self, value: str, is_spread: bool = False) -> str:
        if is_spread:
            return {"up": "走扩", "down": "收敛", "flat": "震荡"}.get(value, "波动")
        return {"up": "上行", "down": "下行", "flat": "震荡"}.get(value, "波动")
