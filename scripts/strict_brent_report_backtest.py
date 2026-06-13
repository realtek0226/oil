from __future__ import annotations

import json
import math
import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.clients.brent_report_client import BrentReportClient
from app.core.container import get_predictor, get_snapshot_repository


REPORT_START_DATE = date(2026, 6, 1)
REPORT_END_DATE = date(2026, 6, 5)
ACTUAL_PRICE_END_DATE = date(2026, 6, 8)
OUTPUT_JSON = Path("artifacts/strict_brent_report_d1_backtest_20260608.json")
OUTPUT_MD = Path("artifacts/strict_brent_report_d1_backtest_20260608.md")


def _round(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return round(numeric, digits)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _load_latest_same_day_reports() -> list[dict[str, Any]]:
    repository = get_snapshot_repository()
    if repository is None or repository.engine is None:
        raise RuntimeError("PostgreSQL snapshot repository is not configured.")

    statement = text(
        """
        with ranked as (
            select
                f.raw_id,
                f.report_date,
                f.report_title,
                f.source_record_id,
                f.fetched_at,
                f.dt,
                f.payload,
                f.markdown_body,
                row_number() over (
                    partition by f.report_date
                    order by
                        case
                            when (f.fetched_at at time zone 'Asia/Shanghai')::date <= f.report_date then 0
                            else 1
                        end,
                        case
                            when (f.fetched_at at time zone 'Asia/Shanghai')::date <= f.report_date then f.fetched_at
                            else null
                        end desc nulls last,
                        case
                            when (f.fetched_at at time zone 'Asia/Shanghai')::date > f.report_date then f.fetched_at
                            else null
                        end asc nulls last,
                        f.raw_id desc
                ) as rn
            from oil_research.ods_raw_forecast f
            join oil_research.dim_source ds
              on ds.source_id = f.source_id
            where ds.source_code = 'brent_daily_report'
              and f.report_date between :start_date and :end_date
        )
        select *
        from ranked
        where rn = 1
        order by report_date
        """
    )

    rows: list[dict[str, Any]] = []
    client = BrentReportClient()
    with repository.engine.begin() as connection:
        for row in connection.execute(
            statement,
            {"start_date": REPORT_START_DATE, "end_date": REPORT_END_DATE},
        ).mappings():
            payload = dict(row["payload"] or {})
            payload.setdefault("title", row["report_title"])
            payload.setdefault("markdown", row["markdown_body"])
            payload.setdefault("report_date", row["report_date"].isoformat())
            normalized = client.normalize_payload(payload)
            rows.append(
                {
                    "raw_id": row["raw_id"],
                    "report_date": row["report_date"],
                    "fetched_at": row["fetched_at"],
                    "dt": row["dt"],
                    "payload": normalized,
                }
            )
    return rows


def _strict_brent_basis(report_payload: dict[str, Any]) -> dict[str, Any]:
    signals = report_payload.get("signals") or {}
    daily = signals.get("daily_forecast") or {}
    settlement = _round(signals.get("brent_settlement"))
    settlement_change = _round(signals.get("brent_settlement_change_usd"))
    previous_settlement = None
    if settlement is not None and settlement_change is not None:
        previous_settlement = round(settlement - settlement_change, 4)
    forecast_point = _round(daily.get("point_value"))
    strict_change = None
    if forecast_point is not None and previous_settlement is not None:
        strict_change = round(forecast_point - previous_settlement, 4)

    daily["change_usd"] = strict_change
    daily["change_source"] = "daily_point_minus_previous_settlement"
    daily["anchor_close"] = previous_settlement
    signals["daily_forecast"] = daily
    report_payload["signals"] = signals
    return {
        "forecast_point": forecast_point,
        "settlement": settlement,
        "settlement_change": settlement_change,
        "previous_settlement": previous_settlement,
        "strict_forecast_change": strict_change,
        "parser_forecast_change_after_normalize": _round(daily.get("change_usd")),
        "change_source": daily.get("change_source"),
    }


def _direction(delta: float) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _agent_scores(prediction: Any) -> list[dict[str, Any]]:
    rows = []
    for claim in prediction.agent_claims:
        rows.append(
            {
                "agent_name": claim.agent_name,
                "direction": claim.direction,
                "raw_score": _round(claim.numeric_signals.get("raw_score")),
                "weighted_score": _round(claim.numeric_signals.get("weighted_score")),
                "summary": claim.summary,
            }
        )
    return rows


def run() -> dict[str, Any]:
    warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

    predictor = get_predictor()
    reports = _load_latest_same_day_reports()
    frame = predictor.dataset_service.build_feature_frame(
        start_date=date(2025, 6, 1),
        end_date=ACTUAL_PRICE_END_DATE,
    ).copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date

    policy_snapshot = predictor.dataset_service.build_archived_policy_snapshot(
        start_date=REPORT_START_DATE,
        end_date=REPORT_END_DATE,
    )
    refined_snapshot = predictor.dataset_service.build_archived_refined_news_snapshot(
        start_date=REPORT_START_DATE,
        end_date=REPORT_END_DATE,
    )
    event_snapshot = predictor.dataset_service.build_archived_event_risk_snapshot(
        start_date=REPORT_START_DATE,
        end_date=REPORT_END_DATE,
    )

    rows: list[dict[str, Any]] = []
    evaluated_rows: list[dict[str, Any]] = []
    reports_by_date = {report["report_date"]: report for report in reports}

    for report_date in _date_range(REPORT_START_DATE, REPORT_END_DATE):
        report = reports_by_date.get(report_date)
        current_rows = frame[frame["date"] == report_date]
        row = current_rows.iloc[-1] if not current_rows.empty else None
        current_price = _round(row.get("sd_gas92_market"), 2) if row is not None else None
        target_date = row.get("next_day_date") if row is not None else None
        if hasattr(target_date, "date"):
            target_date = target_date.date()
        actual_price = _round(row.get("next_day_price"), 2) if row is not None else None

        if report is None:
            rows.append(
                {
                    "as_of_date": report_date,
                    "status": "skipped",
                    "skip_reason": "brent_daily_report_missing",
                    "current_price": current_price,
                    "target_date": None if target_date is None or pd.isna(target_date) else target_date,
                    "actual_price": actual_price,
                }
            )
            continue

        report_payload = dict(report["payload"])
        basis = _strict_brent_basis(report_payload)
        if row is None:
            rows.append(
                {
                    "as_of_date": report_date,
                    "report_raw_id": report["raw_id"],
                    "status": "skipped",
                    "skip_reason": "feature_row_missing",
                    "brent_basis": basis,
                }
            )
            continue

        if target_date is None or pd.isna(target_date) or actual_price is None:
            rows.append(
                {
                    "as_of_date": report_date,
                    "report_raw_id": report["raw_id"],
                    "report_fetched_at": report["fetched_at"],
                    "status": "skipped",
                    "skip_reason": "next_day_formal_price_missing",
                    "current_price": current_price,
                    "target_date": None if target_date is None or pd.isna(target_date) else target_date,
                    "brent_basis": basis,
                }
            )
            continue

        strict_frame = frame.copy()
        if basis["strict_forecast_change"] is not None:
            strict_frame.loc[strict_frame["date"] == report_date, "brent_change_1d"] = basis[
                "strict_forecast_change"
            ]

        prediction = predictor.predict_from_frame(
            feature_frame=strict_frame,
            as_of_date=report_date,
            refined_news_items=refined_snapshot.items_by_date.get(report_date, []),
            report_payload=report_payload,
            news_items=event_snapshot.news_items_by_date.get(report_date, []),
            policy_items=policy_snapshot.items_by_date.get(report_date, []),
            enable_refined_news=True,
            enable_event_risk=True,
            refined_news_by_date=refined_snapshot.items_by_date,
            event_news_by_date=event_snapshot.news_items_by_date,
            event_report_by_date=event_snapshot.report_by_date,
        )

        actual_delta = actual_price - float(current_price)
        predicted_delta = prediction.point_value - float(current_price)
        raw_context = prediction.raw_context or {}
        result_row = {
            "as_of_date": report_date,
            "report_raw_id": report["raw_id"],
            "report_fetched_at": report["fetched_at"],
            "status": "evaluated",
            "current_price": current_price,
            "target_date": target_date,
            "actual_price": actual_price,
            "actual_delta": round(actual_delta, 2),
            "actual_direction": _direction(actual_delta),
            "predicted_point": prediction.point_value,
            "predicted_delta": round(predicted_delta, 2),
            "predicted_direction": prediction.direction_label,
            "range_lower": prediction.range_lower,
            "range_upper": prediction.range_upper,
            "hit_direction": prediction.direction_label == _direction(actual_delta),
            "hit_range": prediction.range_lower <= actual_price <= prediction.range_upper,
            "abs_error": round(abs(prediction.point_value - actual_price), 2),
            "brent_basis": basis,
            "score_value": raw_context.get("score_value"),
            "calibration_score_value": raw_context.get("calibration_score_value"),
            "point_mapping": raw_context.get("point_mapping", {}),
            "point_adjustments": raw_context.get("point_adjustments", {}),
            "event_gate": raw_context.get("event_gate", {}),
            "calibration": raw_context.get("calibration", {}),
            "business_scorecard_prediction": raw_context.get("business_scorecard_prediction", {}),
            "agent_scores": _agent_scores(prediction),
        }
        rows.append(result_row)
        evaluated_rows.append(result_row)

    sample_size = len(evaluated_rows)
    direction_accuracy = (
        round(sum(1 for row in evaluated_rows if row["hit_direction"]) / sample_size, 4)
        if sample_size
        else 0.0
    )
    range_hit_rate = (
        round(sum(1 for row in evaluated_rows if row["hit_range"]) / sample_size, 4)
        if sample_size
        else 0.0
    )
    mae = (
        round(sum(float(row["abs_error"]) for row in evaluated_rows) / sample_size, 4)
        if sample_size
        else 0.0
    )
    result = {
        "run_time": datetime.now().isoformat(timespec="seconds"),
        "variant": "strict_brent_report_d1",
        "definition": {
            "input_rule": "Use report date T feature row and same-day archived Brent report to predict next formal quote date T+1.",
            "brent_change_rule": "Brent forecast daily change = daily forecast point - previous settlement; previous settlement = settlement - settlement_change.",
            "report_selection_rule": "For each report_date, use the latest snapshot fetched on that report_date; if none exists, use the earliest later snapshot.",
            "actual_price_rule": "Use feature_frame.next_day_price generated from formal daily market series; do not use weekend/minute snapshots as actuals.",
            "actual_price_end_date": ACTUAL_PRICE_END_DATE.isoformat(),
        },
        "sample_size": sample_size,
        "direction_accuracy": direction_accuracy,
        "range_hit_rate": range_hit_rate,
        "mae": mae,
        "rows": rows,
    }
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    OUTPUT_MD.write_text(_to_markdown(result), encoding="utf-8")
    return result


def _to_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 严格 Brent 日报 D1 回测",
        "",
        f"- 运行时间：{result['run_time']}",
        f"- 有效样本数：{result['sample_size']}",
        f"- 方向准确率：{result['direction_accuracy']}",
        f"- 区间命中率：{result['range_hit_rate']}",
        f"- MAE：{result['mae']}",
        "",
        "## 口径",
    ]
    for value in result["definition"].values():
        lines.append(f"- {value}")

    lines.extend(
        [
            "",
            "## 逐日结果",
            "",
            "| T日 | 当前价 | 目标日 | 真实价 | Brent预测点 | settlement | 前一日settlement | Brent预测涨跌 | 综合分 | 状态桶 | 基础涨跌 | 修正项 | 预测点位 | 预测方向 | 真实方向 | 区间 | 命中方向 | 命中区间 | 误差 | 状态 |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---|---:|---|---|---|---|---|---:|---|",
        ]
    )

    for row in result["rows"]:
        basis = row.get("brent_basis") or {}
        if row["status"] != "evaluated":
            lines.append(
                "| {as_of} | {current} | {target} | {actual} | {point} | {settle} | {prev} | {chg} | - | - | - | - | - | - | - | - | - | - | - | {status}: {reason} |".format(
                    as_of=row.get("as_of_date"),
                    current=row.get("current_price", "-"),
                    target=row.get("target_date") or "-",
                    actual=row.get("actual_price", "-"),
                    point=basis.get("forecast_point", "-"),
                    settle=basis.get("settlement", "-"),
                    prev=basis.get("previous_settlement", "-"),
                    chg=basis.get("strict_forecast_change", "-"),
                    status=row.get("status"),
                    reason=row.get("skip_reason"),
                )
            )
            continue

        mapping = row.get("point_mapping") or {}
        adjustments = row.get("point_adjustments") or {}
        adjustment_text = ", ".join(f"{key}:{value}" for key, value in adjustments.items()) or "-"
        lines.append(
            "| {as_of} | {current} | {target} | {actual} | {point} | {settle} | {prev} | {chg} | {score} | {bucket} | {base} | {adjustment_text} | {pred} | {pdir} | {adir} | {lower}~{upper} | {hit_dir} | {hit_range} | {err} | evaluated |".format(
                as_of=row["as_of_date"],
                current=row["current_price"],
                target=row["target_date"],
                actual=row["actual_price"],
                point=basis.get("forecast_point"),
                settle=basis.get("settlement"),
                prev=basis.get("previous_settlement"),
                chg=basis.get("strict_forecast_change"),
                score=row.get("score_value"),
                bucket=mapping.get("bucket"),
                base=mapping.get("predicted_delta"),
                adjustment_text=adjustment_text,
                pred=row["predicted_point"],
                pdir=row["predicted_direction"],
                adir=row["actual_direction"],
                lower=row["range_lower"],
                upper=row["range_upper"],
                hit_dir="是" if row["hit_direction"] else "否",
                hit_range="是" if row["hit_range"] else "否",
                err=row["abs_error"],
            )
        )

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    output = run()
    print(json.dumps(output, ensure_ascii=False, indent=2, default=_json_default))
