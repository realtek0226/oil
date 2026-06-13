from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.container import get_dataset_service, get_regional_spread_predictor
from app.services.market_dataset import PredictionContext
from app.services.predictors.horizons import resolve_horizon_config
from app.services.predictors.shandong_regional_spreads import REGIONAL_SPREAD_CONFIGS


def parse_date(value: str) -> date:
    return pd.Timestamp(value).date()


def direction_from_delta(delta: float, threshold: float) -> str:
    if delta > threshold:
        return "up"
    if delta < -threshold:
        return "down"
    return "flat"


def spread_for_row(row: pd.Series, region_code: str) -> float | None:
    config = REGIONAL_SPREAD_CONFIGS[region_code]
    target_price = row.get(config.price_column)
    shandong_price = row.get("sd_gas92_market")
    if pd.isna(target_price) or pd.isna(shandong_price):
        return None
    return float(target_price) - float(shandong_price)


def build_context(frame: pd.DataFrame, as_of_date: date) -> PredictionContext:
    current = frame[frame["date"] <= as_of_date].iloc[-1]
    return PredictionContext(
        feature_frame=frame,
        current_row=current,
        report_payload=None,
        news_items=[],
        refined_news_items=[],
        policy_items=[],
        metadata={"market_data_mode": "backtest", "market_data_reason": "regional_spread_backtest"},
    )


def run_backtest(
    *,
    start_date: date,
    end_date: date,
    horizon: str,
    region_codes: list[str],
    max_rows: int,
    direction_threshold: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    dataset_service = get_dataset_service()
    predictor = get_regional_spread_predictor()
    horizon_config = resolve_horizon_config(horizon)
    frame = dataset_service.build_feature_frame(start_date=start_date - timedelta(days=365), end_date=end_date)
    frame = frame.sort_values("date").reset_index(drop=True)
    eval_frame = frame[(frame["date"] >= start_date) & (frame["date"] <= end_date)].copy()
    if max_rows > 0:
        eval_frame = eval_frame.tail(max_rows)

    rows: list[dict[str, Any]] = []
    date_index = {row["date"]: row for _, row in frame.iterrows()}

    for _, row in eval_frame.iterrows():
        as_of_date = row["date"]
        if not isinstance(as_of_date, date):
            as_of_date = pd.Timestamp(as_of_date).date()
        target_date = horizon_config.target_date_from(as_of_date)
        target_row = date_index.get(target_date)
        if target_row is None:
            continue
        context = build_context(frame, as_of_date)
        for region_code in region_codes:
            current_spread = spread_for_row(row, region_code)
            actual_spread = spread_for_row(target_row, region_code)
            if current_spread is None or actual_spread is None:
                continue
            try:
                prediction = predictor.run_prediction_from_context(
                    context=context,
                    region_code=region_code,
                    as_of_date=as_of_date,
                    horizon=horizon,
                    use_llm_explainer=False,
                    enable_refined_news=False,
                    enable_event_risk=False,
                )
            except Exception as exc:
                rows.append(
                    {
                        "as_of_date": as_of_date,
                        "target_date": target_date,
                        "region_code": region_code,
                        "region_name": REGIONAL_SPREAD_CONFIGS[region_code].region_name,
                        "error": str(exc),
                    }
                )
                continue
            predicted_delta = float(prediction.raw_context.get("predicted_delta") or 0.0)
            actual_delta = actual_spread - current_spread
            actual_direction = direction_from_delta(actual_delta, direction_threshold)
            spread_error = float(prediction.point_value) - actual_spread
            target_shandong_price = float(target_row["sd_gas92_market"])
            predicted_region_price = target_shandong_price + float(prediction.point_value)
            actual_region_price = float(target_row[REGIONAL_SPREAD_CONFIGS[region_code].price_column])
            rows.append(
                {
                    "as_of_date": as_of_date,
                    "target_date": target_date,
                    "horizon": horizon,
                    "region_code": region_code,
                    "region_name": REGIONAL_SPREAD_CONFIGS[region_code].region_name,
                    "current_spread": round(current_spread, 2),
                    "predicted_spread": round(float(prediction.point_value), 2),
                    "actual_spread": round(actual_spread, 2),
                    "predicted_delta": round(predicted_delta, 2),
                    "actual_delta": round(actual_delta, 2),
                    "predicted_direction": prediction.direction_label,
                    "actual_direction": actual_direction,
                    "hit_direction": prediction.direction_label == actual_direction,
                    "abs_spread_error": round(abs(spread_error), 2),
                    "predicted_region_price_with_actual_sd": round(predicted_region_price, 2),
                    "actual_region_price": round(actual_region_price, 2),
                    "abs_region_price_error_with_actual_sd": round(abs(predicted_region_price - actual_region_price), 2),
                    "score_value": prediction.score_value,
                    "inventory_subject": (prediction.raw_context.get("regional_inventory") or {}).get("subject"),
                    "inventory_date": (prediction.raw_context.get("regional_inventory") or {}).get("latest_date"),
                    "inventory_ratio_to_median": (prediction.raw_context.get("regional_inventory") or {}).get(
                        "ratio_to_median"
                    ),
                }
            )

    result_frame = pd.DataFrame(rows)
    valid = result_frame[result_frame.get("error").isna()] if "error" in result_frame.columns else result_frame
    summary: dict[str, Any] = {
        "horizon": horizon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "sample_size": int(len(valid)),
        "direction_threshold": direction_threshold,
        "direction_accuracy": round(float(valid["hit_direction"].mean()), 4) if not valid.empty else 0.0,
        "mae_spread": round(float(valid["abs_spread_error"].mean()), 4) if not valid.empty else 0.0,
        "mae_region_price_with_actual_sd": round(float(valid["abs_region_price_error_with_actual_sd"].mean()), 4)
        if not valid.empty
        else 0.0,
        "by_region": [],
    }
    if not valid.empty:
        for region_code, group in valid.groupby("region_code"):
            summary["by_region"].append(
                {
                    "region_code": region_code,
                    "region_name": REGIONAL_SPREAD_CONFIGS[region_code].region_name,
                    "sample_size": int(len(group)),
                    "direction_accuracy": round(float(group["hit_direction"].mean()), 4),
                    "mae_spread": round(float(group["abs_spread_error"].mean()), 4),
                }
            )
    return result_frame, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest Shandong regional spread predictor.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--horizon", default="D1")
    parser.add_argument("--regions", default=",".join(REGIONAL_SPREAD_CONFIGS))
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--direction-threshold", type=float, default=0.5)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    region_codes = [item.strip().upper() for item in args.regions.split(",") if item.strip()]
    result_frame, summary = run_backtest(
        start_date=parse_date(args.start_date),
        end_date=parse_date(args.end_date),
        horizon=args.horizon,
        region_codes=region_codes,
        max_rows=args.max_rows,
        direction_threshold=args.direction_threshold,
    )
    if args.output:
        output = Path(args.output)
    else:
        output = Path("data") / "backtests" / (
            f"regional_spread_backtest_{args.start_date}_{args.end_date}_{args.horizon}.csv"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    result_frame.to_csv(output, index=False, encoding="utf-8-sig")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(f"saved_csv={output}")


if __name__ == "__main__":
    main()
