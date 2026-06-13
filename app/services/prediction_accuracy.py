from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.market_dataset import MarketDatasetService
from app.services.run_repository import FileRunRepository


DELETED_ACCURACY_RECORDS_PATH = Path("artifacts/agent_control/prediction_accuracy_deleted.json")


@dataclass(frozen=True)
class AccuracyRow:
    source: str
    run_id: str
    product_label: str
    horizon: str
    as_of_date: date
    target_date: date
    predicted_direction: str
    predicted_point: float
    range_lower: float
    range_upper: float
    confidence_score: float | None
    actual_price: float | None
    base_price: float | None
    actual_change: float | None
    point_error: float | None
    absolute_error: float | None
    range_hit: bool | None
    direction_hit: bool | None
    status: str
    explanation: str | None = None
    generated_at: datetime | None = None


class PredictionAccuracyService:
    def __init__(self, repository: FileRunRepository, dataset_service: MarketDatasetService) -> None:
        self.repository = repository
        self.dataset_service = dataset_service

    def build_dashboard(self, *, days: int = 30, limit: int = 120) -> dict[str, Any]:
        today = date.today()
        cutoff = today - timedelta(days=max(days, 1))
        rows = self._load_briefing_rows(cutoff=cutoff)
        if not rows:
            rows = self._load_prediction_rows(cutoff=cutoff, limit=limit)
        rows.extend(self._load_roundtable_rows(cutoff=cutoff))
        deleted_run_ids = self._load_deleted_run_ids()
        rows = [row for row in rows if row.run_id not in deleted_run_ids]
        rows = self._dedupe_rows(rows)

        if rows:
            min_date = min(min(row.as_of_date, row.target_date) for row in rows)
            max_date = min(today, max(max(row.as_of_date, row.target_date) for row in rows))
            price_frame = self.dataset_service.build_feature_frame(start_date=min_date - timedelta(days=3), end_date=max_date)
        else:
            price_frame = pd.DataFrame(columns=["date", "sd_gas92_market"])

        actual_lookup = self._build_actual_lookup(price_frame)
        evaluated = [self._evaluate_row(row, actual_lookup) for row in rows]
        evaluated.sort(
            key=lambda item: (
                item.status == "evaluated",
                item.target_date,
                item.as_of_date,
                item.run_id,
            ),
            reverse=True,
        )
        items = [self._row_to_payload(item) for item in evaluated[:limit]]
        evaluated_items = [item for item in evaluated if item.status == "evaluated"]

        mae = (
            round(sum(float(item.absolute_error or 0.0) for item in evaluated_items) / len(evaluated_items), 2)
            if evaluated_items
            else None
        )
        direction_accuracy = (
            round(sum(1 for item in evaluated_items if item.direction_hit) / len(evaluated_items), 4)
            if evaluated_items
            else None
        )
        range_hit_rate = (
            round(sum(1 for item in evaluated_items if item.range_hit) / len(evaluated_items), 4)
            if evaluated_items
            else None
        )
        within_50_rate = (
            round(sum(1 for item in evaluated_items if (item.absolute_error or 0) <= 50) / len(evaluated_items), 4)
            if evaluated_items
            else None
        )

        return {
            "generated_at": datetime.now(),
            "summary": {
                "sample_size": len(evaluated_items),
                "pending_size": sum(1 for item in evaluated if item.status == "pending"),
                "mae": mae,
                "direction_accuracy": direction_accuracy,
                "range_hit_rate": range_hit_rate,
                "within_50_rate": within_50_rate,
            },
            "items": items,
            "metadata": {
                "days": days,
                "limit": limit,
                "actual_price_field": "sd_gas92_market",
                "actual_scope": "山东92#国VI库提现汇市场价",
                "evaluation_rule": "真实价格按山东92#国VI库提现汇市场价日期列对齐；目标日期无价格时仅展示为待验证。",
            },
        }

    def _load_prediction_rows(self, *, cutoff: date, limit: int) -> list[AccuracyRow]:
        rows: list[AccuracyRow] = []
        for record in self.repository.list_prediction_records(limit=max(limit * 3, 200)):
            payload = record.payload
            if payload.get("product_code") != "GASOLINE_92":
                continue
            if (payload.get("raw_context") or {}).get("run_source") == "chat":
                continue
            as_of_date = self._parse_date(payload.get("as_of_date"))
            target_date = self._parse_date(payload.get("target_date"))
            if as_of_date is None or target_date is None or target_date < cutoff:
                continue
            rows.append(
                AccuracyRow(
                    source="规则智能体综合",
                    run_id=str(payload.get("run_id") or record.key),
                    product_label="山东92#",
                    horizon=str(payload.get("horizon") or "D1"),
                    as_of_date=as_of_date,
                    target_date=target_date,
                    predicted_direction=str(payload.get("direction_label") or "flat"),
                    predicted_point=float(payload.get("point_value") or 0.0),
                    range_lower=float(payload.get("range_lower") or 0.0),
                    range_upper=float(payload.get("range_upper") or 0.0),
                    confidence_score=self._float_or_none(payload.get("confidence_score")),
                    actual_price=None,
                    base_price=self._float_or_none(payload.get("raw_context", {}).get("current_price")),
                    actual_change=None,
                    point_error=None,
                    absolute_error=None,
                    range_hit=None,
                    direction_hit=None,
                    status="pending",
                    explanation=str(payload.get("explanation") or ""),
                    generated_at=record.modified_at,
                )
            )
        return rows

    def _load_briefing_rows(self, *, cutoff: date) -> list[AccuracyRow]:
        latest_by_key: dict[tuple[date, str], tuple[datetime, dict[str, Any]]] = {}
        for path in Path("artifacts/briefings").glob("brief-*.json"):
            payload = self._read_json(path)
            if not payload:
                continue
            briefing_date = self._parse_date(payload.get("as_of_date"))
            generated_at = self._parse_datetime(payload.get("generated_at")) or datetime.fromtimestamp(path.stat().st_mtime)
            if briefing_date is None or briefing_date < cutoff:
                continue
            for prediction in payload.get("outright_predictions") or []:
                if prediction.get("product_code") != "GASOLINE_92":
                    continue
                horizon = str(prediction.get("horizon") or "D1")
                key = (briefing_date, horizon)
                existing = latest_by_key.get(key)
                if existing is None or generated_at > existing[0]:
                    latest_by_key[key] = (generated_at, prediction)

        rows: list[AccuracyRow] = []
        for (briefing_date, _horizon), (generated_at, prediction) in latest_by_key.items():
            as_of_date = self._parse_date(prediction.get("as_of_date")) or briefing_date
            target_date = self._parse_date(prediction.get("target_date")) or as_of_date
            rows.append(
                AccuracyRow(
                    source="晨报最终展示",
                    run_id=str(prediction.get("run_id") or f"briefing-{briefing_date}-{_horizon}"),
                    product_label="山东92#",
                    horizon=str(prediction.get("horizon") or "D1"),
                    as_of_date=as_of_date,
                    target_date=target_date,
                    predicted_direction=str(prediction.get("direction_label") or "flat"),
                    predicted_point=float(prediction.get("point_value") or 0.0),
                    range_lower=float(prediction.get("range_lower") or 0.0),
                    range_upper=float(prediction.get("range_upper") or 0.0),
                    confidence_score=self._float_or_none(prediction.get("confidence_score")),
                    actual_price=None,
                    base_price=self._float_or_none((prediction.get("raw_context") or {}).get("current_price")),
                    actual_change=None,
                    point_error=None,
                    absolute_error=None,
                    range_hit=None,
                    direction_hit=None,
                    status="pending",
                    explanation=str(prediction.get("explanation") or ""),
                    generated_at=generated_at,
                )
            )
        return rows

    def _load_roundtable_rows(self, *, cutoff: date) -> list[AccuracyRow]:
        rows: list[AccuracyRow] = []
        for path in Path("artifacts").glob("llm_roundtable_*_to_*.json"):
            payload = self._read_json(path)
            if not payload:
                continue
            source_date = self._parse_date(payload.get("source_date") or payload.get("factor_pack", {}).get("source_date"))
            target_date = self._parse_date(payload.get("target_date") or payload.get("factor_pack", {}).get("target_date"))
            final = payload.get("final") or {}
            evaluation = payload.get("evaluation") or {}
            if source_date is None or target_date is None or target_date < cutoff:
                continue
            predicted_point = self._float_or_none(final.get("final_point"))
            if predicted_point is None:
                continue
            rows.append(
                AccuracyRow(
                    source="LLM硬机制圆桌",
                    run_id=path.stem,
                    product_label="山东92#",
                    horizon="D1",
                    as_of_date=source_date,
                    target_date=target_date,
                    predicted_direction=self._normalize_direction(final.get("final_direction")),
                    predicted_point=predicted_point,
                    range_lower=float(final.get("final_range_low") or predicted_point),
                    range_upper=float(final.get("final_range_high") or predicted_point),
                    confidence_score=self._confidence_to_score(final.get("confidence")),
                    actual_price=self._float_or_none(evaluation.get("actual_price")),
                    base_price=self._float_or_none(payload.get("factor_pack", {}).get("current_price")),
                    actual_change=self._float_or_none(evaluation.get("actual_change")),
                    point_error=self._float_or_none(evaluation.get("point_error")),
                    absolute_error=self._float_or_none(evaluation.get("absolute_error")),
                    range_hit=evaluation.get("range_hit") if isinstance(evaluation.get("range_hit"), bool) else None,
                    direction_hit=evaluation.get("direction_hit") if isinstance(evaluation.get("direction_hit"), bool) else None,
                    status="evaluated" if evaluation.get("available") else "pending",
                    explanation=str(final.get("accepted_arguments_zh") or final.get("audit_note_zh") or ""),
                    generated_at=datetime.fromtimestamp(path.stat().st_mtime),
                )
            )
        return rows

    def _evaluate_row(self, row: AccuracyRow, actual_lookup: dict[date, float]) -> AccuracyRow:
        adjusted_row = self._align_row_to_actual_dates(row, actual_lookup)
        if adjusted_row.actual_price is not None:
            return adjusted_row
        actual_price = actual_lookup.get(adjusted_row.target_date)
        if actual_price is None:
            return adjusted_row
        base_price = adjusted_row.base_price if adjusted_row.base_price is not None else actual_lookup.get(adjusted_row.as_of_date)
        actual_change = actual_price - base_price if base_price is not None else None
        actual_direction = self._direction_from_delta(actual_change)
        point_error = adjusted_row.predicted_point - actual_price
        return AccuracyRow(
            **{
                **adjusted_row.__dict__,
                "actual_price": round(actual_price, 2),
                "base_price": round(base_price, 2) if base_price is not None else None,
                "actual_change": round(actual_change, 2) if actual_change is not None else None,
                "point_error": round(point_error, 2),
                "absolute_error": round(abs(point_error), 2),
                "range_hit": adjusted_row.range_lower <= actual_price <= adjusted_row.range_upper,
                "direction_hit": adjusted_row.predicted_direction == actual_direction if actual_direction else None,
                "status": "evaluated",
            }
        )

    def _align_row_to_actual_dates(self, row: AccuracyRow, actual_lookup: dict[date, float]) -> AccuracyRow:
        if row.source != "晨报最终展示" or row.horizon != "D1" or row.base_price is None:
            return row
        base_date = self._find_price_date(row.base_price, actual_lookup, latest_on_or_before=row.as_of_date)
        if base_date is None:
            return row
        target_date = self._next_price_date(base_date, actual_lookup) or row.target_date
        if base_date == row.as_of_date and target_date == row.target_date:
            return row
        return AccuracyRow(**{**row.__dict__, "as_of_date": base_date, "target_date": target_date})

    def _build_actual_lookup(self, frame: pd.DataFrame) -> dict[date, float]:
        if frame.empty or "sd_gas92_market" not in frame.columns:
            return {}
        lookup: dict[date, float] = {}
        rows = frame[["date", "sd_gas92_market"]].dropna(subset=["sd_gas92_market"])
        for _, item in rows.iterrows():
            item_date = item["date"]
            if hasattr(item_date, "date"):
                item_date = item_date.date()
            else:
                item_date = self._parse_date(item_date)
            if item_date is not None:
                lookup[item_date] = float(item["sd_gas92_market"])
        return lookup

    def _row_to_payload(self, row: AccuracyRow) -> dict[str, Any]:
        return {
            "source": row.source,
            "run_id": row.run_id,
            "product_label": row.product_label,
            "horizon": row.horizon,
            "as_of_date": row.as_of_date,
            "target_date": row.target_date,
            "base_price_date": row.as_of_date if row.base_price is not None else None,
            "actual_price_date": row.target_date if row.actual_price is not None else None,
            "predicted_direction": row.predicted_direction,
            "predicted_point": round(row.predicted_point, 2),
            "range_lower": round(row.range_lower, 2),
            "range_upper": round(row.range_upper, 2),
            "confidence_score": row.confidence_score,
            "actual_price": row.actual_price,
            "base_price": row.base_price,
            "actual_change": row.actual_change,
            "point_error": row.point_error,
            "absolute_error": row.absolute_error,
            "range_hit": row.range_hit,
            "direction_hit": row.direction_hit,
            "status": row.status,
            "explanation": row.explanation,
            "generated_at": row.generated_at,
        }

    def _dedupe_rows(self, rows: list[AccuracyRow]) -> list[AccuracyRow]:
        seen: set[str] = set()
        result: list[AccuracyRow] = []
        for row in sorted(rows, key=lambda item: (item.generated_at or datetime.min, item.target_date, item.run_id), reverse=True):
            key = f"{row.source}|{row.as_of_date}|{row.target_date}|{row.horizon}"
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_deleted_run_ids(self) -> set[str]:
        payload = self._read_json(DELETED_ACCURACY_RECORDS_PATH) or {}
        items = payload.get("deleted_run_ids") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return set()
        return {str(item) for item in items if item}

    def _parse_date(self, value: Any) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except Exception:
            return None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    def _float_or_none(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _normalize_direction(self, value: Any) -> str:
        text = str(value or "").lower()
        if "涨" in text or "up" in text:
            return "up"
        if "跌" in text or "down" in text:
            return "down"
        return "flat"

    def _direction_from_delta(self, value: float | None) -> str | None:
        if value is None:
            return None
        if value > 0:
            return "up"
        if value < 0:
            return "down"
        return "flat"

    def _confidence_to_score(self, value: Any) -> float | None:
        text = str(value or "")
        if "高" in text:
            return 0.75
        if "低" in text:
            return 0.35
        if "中" in text:
            return 0.55
        return None

    def _find_price_date(
        self,
        price: float,
        actual_lookup: dict[date, float],
        *,
        latest_on_or_before: date,
        tolerance: float = 0.01,
    ) -> date | None:
        candidates = [
            item_date
            for item_date, item_price in actual_lookup.items()
            if item_date <= latest_on_or_before and abs(float(item_price) - price) <= tolerance
        ]
        return max(candidates) if candidates else None

    def _next_price_date(self, base_date: date, actual_lookup: dict[date, float]) -> date | None:
        candidates = [item_date for item_date in actual_lookup if item_date > base_date]
        return min(candidates) if candidates else None
