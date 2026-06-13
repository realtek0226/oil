from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.container import get_dataset_service, get_snapshot_repository
from app.core.settings import get_settings


FORBIDDEN_STAGE1_KEY_PARTS = ("point", "range", "change", "score", "forecast", "expected")


EXPERT_ROLES = [
    (
        "refinery_pricing",
        "山东地炼报价负责人：只讨论炼厂挂牌、暗降、成交优惠和挺价/走量选择。",
    ),
    (
        "buyer_terminal",
        "下游贸易商与终端采购：只讨论买方是否接货、压价、观望、补库。",
    ),
    (
        "regional_flow",
        "区域套利物流：只讨论山东资源外流、运费后净回款、区域倒挂。",
    ),
    (
        "cost_floor",
        "原油与调和成本：只讨论Brent日报、实时原油、石脑油、MTBE、裂解对价格底部的约束。",
    ),
    (
        "supply_inventory",
        "供应库存：只讨论开工、库存、库容率、炼厂利润和排库压力。",
    ),
    (
        "skeptic_auditor",
        "反方审稿：只找其他专家可能忽略的证据和最可能误判点。",
    ),
]


STAGE1_SYSTEM_PROMPT = """
你是国内成品油圆桌专家。硬约束：本阶段禁止输出任何预测点位、价格区间、涨跌金额，禁止使用五类打分法。
你只能基于指定角色，输出“目标日市场参与者会怎么行动”的情景判断。
必须返回JSON对象，且只能包含这些字段：
expert_id, role_focus, likely_behavior_zh, direction_bias, decisive_evidence_zh, counter_evidence_zh, blind_spot_zh, confidence_zh
direction_bias 只能是：上涨、下跌、稳定、震荡。
如果输出 point/range/change/score/forecast/expected 等价格预测字段，视为失败。
""".strip()


CROSS_EXAMINATION_SYSTEM_PROMPT = """
你是圆桌交叉质询专家。硬约束：禁止输出最终点位、区间、涨跌金额，禁止打分。
阅读所有专家第一轮意见，只做质询：指出最强共识、最大分歧、哪些证据不足、哪些结论可能是角色偏见。
必须返回JSON对象，只包含这些字段：
strong_consensus_zh, core_disagreement_zh, weak_evidence_zh, role_bias_risks_zh, evidence_needed_zh
""".strip()


CHAIR_SYSTEM_PROMPT = """
你是圆桌主持人。你现在才允许输出最终价格预测。
硬机制：
1. 不允许机械平均专家结果，因为专家第一轮没有点位。
2. 必须先选择主导情景：走量修复/成本托底/区域外流/高位僵持/继续推涨。
3. 必须用“价格调整台账”从 current_price 推导最终点位。台账项目必须是交易行为，不是五类因子分：
   - 成交修复折让
   - 区域外流修复折让或溢价
   - 成本托底修正
   - 库存/利润托底修正
   - 风险缓冲修正
4. 台账每项可为正负数，但必须说明业务含义；最终点位 = current_price + 各项合计。
5. 必须说明这套结论是否与规则模型同构；如果像规则模型，要直说。
必须返回JSON对象，只包含这些字段：
dominant_scenario_zh, adjustment_ledger, total_adjustment, final_point, final_range_low, final_range_high,
final_direction, confidence, why_this_is_not_factor_score_zh, accepted_arguments_zh, rejected_arguments_zh,
operating_advice_zh, audit_note_zh
adjustment_ledger 每项必须包含 item, adjustment, business_meaning_zh。
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a hard-gated LLM expert roundtable forecast.")
    parser.add_argument("--source-date", required=True, help="Input date, for example 2026-06-02.")
    parser.add_argument("--target-date", required=True, help="Forecast target date, for example 2026-06-03.")
    parser.add_argument("--output-dir", default="artifacts", help="Directory for JSON and Markdown outputs.")
    parser.add_argument("--max-retries", type=int, default=3, help="Retry count for invalid LLM JSON.")
    parser.add_argument("--no-evaluate", action="store_true", help="Do not compare with target-date actual price.")
    return parser.parse_args()


def to_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
        if hasattr(value, "item"):
            return value.item()
        return round(value, 4) if isinstance(value, float) else value
    except Exception:
        return value


def normalize_json_result(result: Any) -> dict[str, Any]:
    if isinstance(result, list) and result:
        result = result[0]
    if not isinstance(result, dict):
        raise ValueError(f"LLM returned {type(result).__name__}, expected JSON object.")
    return result


class RoundtableRunner:
    def __init__(self, max_retries: int) -> None:
        self.settings = get_settings()
        self.max_retries = max_retries
        self.base_url = self.settings.llm.base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.settings.llm.api_key}",
            "Content-Type": "application/json",
        }

    def ask_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self.headers,
            json={
                "model": self.settings.llm.model_name,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
                ],
            },
            timeout=self.settings.llm.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"].strip()
        return normalize_json_result(json.loads(content))

    def ask_validated(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        validator,
        label: str,
    ) -> tuple[dict[str, Any], list[str]]:
        errors: list[str] = []
        prompt = system_prompt
        for attempt in range(1, self.max_retries + 1):
            result = self.ask_json(prompt, user_payload)
            try:
                validator(result)
                return result, errors
            except ValueError as exc:
                errors.append(f"{label} attempt {attempt}: {exc}")
                prompt = (
                    f"{system_prompt}\n\n上一次输出不合规，错误：{exc}\n"
                    "请严格修正，只返回允许字段，不要解释。"
                )
        raise RuntimeError(f"{label} failed validation after {self.max_retries} attempts: {errors}")


def latest_brent_report_context(source_date: date) -> dict[str, Any] | None:
    repository = get_snapshot_repository()
    if not repository or not repository.enabled:
        return None
    result = repository.load_brent_reports(start_date=source_date - timedelta(days=10), end_date=source_date)
    if not result.items:
        return None
    item = dict(result.items[0])
    signals = item.get("signals") or {}
    return {
        "report_date": item.get("report_date"),
        "title": item.get("title"),
        "brent_settlement": signals.get("brent_settlement"),
        "daily_forecast": signals.get("daily_forecast"),
        "horizon_forecasts": signals.get("horizon_forecasts"),
        "realtime_context": signals.get("realtime_context"),
        "bullish_hits": signals.get("bullish_hits"),
        "bearish_hits": signals.get("bearish_hits"),
    }


def build_factor_pack(source_date: date, target_date: date) -> dict[str, Any]:
    dataset_service = get_dataset_service()
    dataset_service.web_scraping_enabled = False
    dataset_service.refined_news_scraping_enabled = False
    dataset_service.policy_scraping_enabled = False
    dataset_service.oilchem_scraping_enabled = False

    frame = dataset_service.build_feature_frame(start_date=source_date - timedelta(days=20), end_date=source_date)
    visible = frame[frame["date"] <= source_date].copy()
    if visible.empty:
        raise RuntimeError(f"No visible feature data found on or before {source_date}.")
    row = visible.iloc[-1]
    fields = [
        "sd_gas92_market",
        "cn_gas92_market",
        "east_china_gas92_market",
        "north_china_gas92_market",
        "south_china_gas92_market",
        "central_china_gas92_market",
        "northwest_gas92_market",
        "southwest_gas92_market",
        "northeast_gas92_market",
        "brent_active_settlement",
        "sd_gas_crack",
        "sd_refining_profit",
        "sales_production_ratio_d1",
        "sd_crude_run_weekly",
        "shandong_gasoline_inventory",
        "shandong_gasoline_inventory_change_mom",
        "shandong_gasoline_inventory_capacity_rate",
        "sd_mtbe_price",
        "sd_naphtha_price",
        "sd_gas_naphtha_spread",
        "sd_ceiling_gas",
    ]
    history: list[dict[str, Any]] = []
    previous_price: float | None = None
    daily_changes: list[float] = []
    for _, history_row in visible.tail(7).iterrows():
        price = float(history_row.get("sd_gas92_market"))
        change = None if previous_price is None else round(price - previous_price, 2)
        if change is not None:
            daily_changes.append(change)
        item = {"date": history_row["date"].isoformat(), "sd_gas92_change": change}
        item.update({key: clean(history_row.get(key)) for key in fields})
        history.append(item)
        previous_price = price

    regions = [
        "east_china_gas92_market",
        "north_china_gas92_market",
        "south_china_gas92_market",
        "central_china_gas92_market",
        "northwest_gas92_market",
        "southwest_gas92_market",
        "northeast_gas92_market",
    ]
    return {
        "source_date": source_date.isoformat(),
        "target_date": target_date.isoformat(),
        "target": "Shandong 92# gasoline spot price, CNY/ton",
        "current_price": clean(row.get("sd_gas92_market")),
        "current_factors": {key: clean(row.get(key)) for key in fields},
        "regional_prices_minus_shandong": {
            key: clean(row.get(key) - row.get("sd_gas92_market")) for key in regions
        },
        "visible_history": history,
        "visible_daily_changes": daily_changes,
        "brent_report": latest_brent_report_context(source_date),
        "withheld": "Target-date actual price is not provided to the LLM. Do not infer it from outside knowledge.",
    }


def validate_stage1(result: dict[str, Any]) -> None:
    allowed = {
        "expert_id",
        "role_focus",
        "likely_behavior_zh",
        "direction_bias",
        "decisive_evidence_zh",
        "counter_evidence_zh",
        "blind_spot_zh",
        "confidence_zh",
    }
    extra = set(result) - allowed
    if extra:
        raise ValueError(f"stage1 has extra fields: {sorted(extra)}")
    for key in result:
        lowered = key.lower()
        if any(part in lowered for part in FORBIDDEN_STAGE1_KEY_PARTS):
            raise ValueError(f"stage1 contains forbidden key: {key}")
    if result.get("direction_bias") not in {"上涨", "下跌", "稳定", "震荡"}:
        raise ValueError(f"invalid direction_bias: {result.get('direction_bias')}")


def validate_cross_examination(result: dict[str, Any]) -> None:
    allowed = {
        "strong_consensus_zh",
        "core_disagreement_zh",
        "weak_evidence_zh",
        "role_bias_risks_zh",
        "evidence_needed_zh",
    }
    extra = set(result) - allowed
    if extra:
        raise ValueError(f"cross examination has extra fields: {sorted(extra)}")


def as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not numeric: {value}") from exc


def validate_final(result: dict[str, Any], current_price: float) -> None:
    required = {
        "dominant_scenario_zh",
        "adjustment_ledger",
        "total_adjustment",
        "final_point",
        "final_range_low",
        "final_range_high",
        "final_direction",
        "confidence",
        "why_this_is_not_factor_score_zh",
        "accepted_arguments_zh",
        "rejected_arguments_zh",
        "operating_advice_zh",
        "audit_note_zh",
    }
    missing = required - set(result)
    if missing:
        raise ValueError(f"final missing fields: {sorted(missing)}")
    ledger = result.get("adjustment_ledger")
    if not isinstance(ledger, list) or not ledger:
        raise ValueError("adjustment_ledger must be a non-empty list")
    ledger_sum = 0.0
    for item in ledger:
        if not isinstance(item, dict):
            raise ValueError("adjustment_ledger item must be object")
        for field in ("item", "adjustment", "business_meaning_zh"):
            if field not in item:
                raise ValueError(f"adjustment_ledger item missing {field}")
        ledger_sum += as_float(item.get("adjustment"), "ledger adjustment")
    total = as_float(result.get("total_adjustment"), "total_adjustment")
    point = as_float(result.get("final_point"), "final_point")
    low = as_float(result.get("final_range_low"), "final_range_low")
    high = as_float(result.get("final_range_high"), "final_range_high")
    if abs(ledger_sum - total) > 0.01:
        raise ValueError(f"ledger sum {ledger_sum} != total_adjustment {total}")
    if abs((current_price + total) - point) > 0.01:
        raise ValueError(f"current_price + total_adjustment != final_point: {current_price} + {total} vs {point}")
    if low > point or high < point or low > high:
        raise ValueError("final range must include final point")


def run_roundtable(source_date: date, target_date: date, max_retries: int) -> dict[str, Any]:
    factor_pack = build_factor_pack(source_date=source_date, target_date=target_date)
    runner = RoundtableRunner(max_retries=max_retries)
    validation_errors: list[str] = []

    def run_expert(role: tuple[str, str]) -> dict[str, Any]:
        expert_id, role_focus = role
        result, errors = runner.ask_validated(
            system_prompt=STAGE1_SYSTEM_PROMPT,
            user_payload={"expert_id": expert_id, "role_focus": role_focus, "data": factor_pack},
            validator=validate_stage1,
            label=f"stage1:{expert_id}",
        )
        validation_errors.extend(errors)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(EXPERT_ROLES)) as executor:
        stage1_outputs = list(executor.map(run_expert, EXPERT_ROLES))

    stage2, stage2_errors = runner.ask_validated(
        system_prompt=CROSS_EXAMINATION_SYSTEM_PROMPT,
        user_payload={"data": factor_pack, "stage1_expert_opinions": stage1_outputs},
        validator=validate_cross_examination,
        label="cross_examination",
    )
    validation_errors.extend(stage2_errors)

    current_price = as_float(factor_pack["current_price"], "current_price")
    final, final_errors = runner.ask_validated(
        system_prompt=CHAIR_SYSTEM_PROMPT,
        user_payload={
            "data": factor_pack,
            "stage1_expert_opinions": stage1_outputs,
            "cross_examination": stage2,
        },
        validator=lambda result: validate_final(result, current_price=current_price),
        label="final",
    )
    validation_errors.extend(final_errors)

    return {
        "run_type": "llm_hard_roundtable_forecast",
        "model": runner.settings.llm.model_name,
        "source_date": source_date.isoformat(),
        "target_date": target_date.isoformat(),
        "factor_pack": factor_pack,
        "stage1_expert_opinions": stage1_outputs,
        "stage2_cross_examination": stage2,
        "final": final,
        "validation_errors": validation_errors,
    }


def add_evaluation(payload: dict[str, Any], target_date: date) -> None:
    dataset_service = get_dataset_service()
    frame = dataset_service.build_feature_frame(start_date=target_date - timedelta(days=3), end_date=target_date)
    target_rows = frame[frame["date"] == target_date]
    if target_rows.empty:
        payload["evaluation"] = {"available": False, "reason": "target_date_actual_not_found"}
        return
    actual = float(target_rows.iloc[-1].get("sd_gas92_market"))
    current = as_float(payload["factor_pack"]["current_price"], "current_price")
    final = payload["final"]
    point = as_float(final["final_point"], "final_point")
    low = as_float(final["final_range_low"], "final_range_low")
    high = as_float(final["final_range_high"], "final_range_high")
    payload["evaluation"] = {
        "available": True,
        "actual_price": actual,
        "actual_change": round(actual - current, 2),
        "point_error": round(point - actual, 2),
        "absolute_error": round(abs(point - actual), 2),
        "range_hit": bool(low <= actual <= high),
    }


def write_outputs(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_slug = payload["source_date"].replace("-", "")
    target_slug = payload["target_date"].replace("-", "")
    json_path = output_dir / f"llm_roundtable_{source_slug}_to_{target_slug}.json"
    md_path = output_dir / f"llm_roundtable_{source_slug}_to_{target_slug}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    final = payload["final"]
    lines = [
        "# LLM硬机制圆桌预测结果",
        "",
        f"- 模型：{payload['model']}",
        f"- 输入日：{payload['source_date']}",
        f"- 预测日：{payload['target_date']}",
        f"- 当前价：{payload['factor_pack']['current_price']} 元/吨",
        f"- 方向：{final['final_direction']}",
        f"- 预计调整：{final['total_adjustment']} 元/吨",
        f"- 点位：{final['final_point']} 元/吨",
        f"- 区间：{final['final_range_low']} - {final['final_range_high']} 元/吨",
        f"- 置信度：{final['confidence']}",
        "",
        "## 主导情景",
        str(final["dominant_scenario_zh"]),
        "",
        "## 价格调整台账",
    ]
    for item in final["adjustment_ledger"]:
        lines.append(f"- {item['item']}：{item['adjustment']} 元/吨；{item['business_meaning_zh']}")
    lines.extend(
        [
            "",
            "## 交叉质询",
            f"- 强共识：{payload['stage2_cross_examination']['strong_consensus_zh']}",
            f"- 核心分歧：{payload['stage2_cross_examination']['core_disagreement_zh']}",
            f"- 证据弱点：{payload['stage2_cross_examination']['weak_evidence_zh']}",
            "",
            "## 经营建议",
            str(final["operating_advice_zh"]),
            "",
            "## 审计说明",
            str(final["audit_note_zh"]),
        ]
    )
    evaluation = payload.get("evaluation") or {}
    if evaluation.get("available"):
        lines.extend(
            [
                "",
                "## 结果评估",
                f"- 实际价：{evaluation['actual_price']} 元/吨",
                f"- 实际涨跌：{evaluation['actual_change']} 元/吨",
                f"- 点位误差：{evaluation['point_error']} 元/吨",
                f"- 区间命中：{evaluation['range_hit']}",
            ]
        )
    if payload["validation_errors"]:
        lines.extend(["", "## 校验重跑记录"])
        lines.extend(f"- {item}" for item in payload["validation_errors"])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    args = parse_args()
    source_date = to_date(args.source_date)
    target_date = to_date(args.target_date)
    payload = run_roundtable(source_date=source_date, target_date=target_date, max_retries=args.max_retries)
    if not args.no_evaluate:
        add_evaluation(payload, target_date=target_date)
    json_path, md_path = write_outputs(payload, output_dir=Path(args.output_dir))
    final = payload["final"]
    print(json.dumps(
        {
            "json_path": str(json_path),
            "markdown_path": str(md_path),
            "source_date": payload["source_date"],
            "target_date": payload["target_date"],
            "final_direction": final["final_direction"],
            "final_point": final["final_point"],
            "final_range": [final["final_range_low"], final["final_range_high"]],
            "validation_retry_count": len(payload["validation_errors"]),
            "evaluation": payload.get("evaluation"),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
