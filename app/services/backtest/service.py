from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.models.common import (
    BacktestComparison,
    BacktestRow,
    BacktestSummary,
    BacktestVariantSummary,
)
from app.services.predictors.shandong_gas92 import ShandongGas92Predictor


class BacktestService:
    def __init__(self, predictor: ShandongGas92Predictor) -> None:
        self.predictor = predictor

    def run(
        self,
        start_date: date,
        end_date: date,
        horizon: str,
        max_rows: int,
        news_mode: str = "off",
        enable_event_risk: bool = False,
        compare_with_baseline: bool = False,
    ) -> BacktestSummary:
        if horizon != "D1":
            raise ValueError("Backtest currently supports D1 only.")
        if news_mode not in {"off", "refined_news_archive"}:
            raise ValueError(f"Unsupported news_mode={news_mode}")

        frame = self.predictor.dataset_service.build_feature_frame(
            start_date=start_date - timedelta(days=365),
            end_date=end_date,
        )
        eval_frame = frame[(frame["date"] >= start_date) & (frame["date"] <= end_date)].copy()
        eval_frame = eval_frame.dropna(subset=["next_day_price"])
        eval_frame = eval_frame.tail(max_rows).reset_index(drop=True)

        policy_snapshot = self.predictor.dataset_service.build_archived_policy_snapshot(
            start_date=start_date,
            end_date=end_date,
        )
        refined_news_snapshot = None
        if news_mode == "refined_news_archive" or compare_with_baseline:
            refined_news_snapshot = self.predictor.dataset_service.build_archived_refined_news_snapshot(
                start_date=start_date,
                end_date=end_date,
            )
        event_snapshot = None
        if enable_event_risk:
            event_snapshot = self.predictor.dataset_service.build_archived_event_risk_snapshot(
                start_date=start_date,
                end_date=end_date,
            )

        summary = self._run_single_variant(
            frame=frame,
            eval_frame=eval_frame,
            horizon=horizon,
            variant=self._build_variant_name(
                news_mode=news_mode,
                enable_event_risk=enable_event_risk,
            ),
            refined_news_by_date=(
                refined_news_snapshot.items_by_date if news_mode == "refined_news_archive" and refined_news_snapshot else None
            ),
            event_news_by_date=(event_snapshot.news_items_by_date if event_snapshot else None),
            event_report_by_date=(event_snapshot.report_by_date if event_snapshot else None),
            policy_items_by_date=policy_snapshot.items_by_date,
            enable_refined_news=news_mode == "refined_news_archive",
            enable_event_risk=enable_event_risk,
            context=self._build_context(
                news_mode=news_mode,
                enable_event_risk=enable_event_risk,
                refined_news_snapshot=refined_news_snapshot,
                policy_snapshot=policy_snapshot,
                event_snapshot=event_snapshot,
            ),
            notes=self._build_notes(
                news_mode=news_mode,
                enable_event_risk=enable_event_risk,
                refined_news_snapshot=refined_news_snapshot,
                policy_snapshot=policy_snapshot,
                event_snapshot=event_snapshot,
            ),
        )

        if compare_with_baseline:
            baseline = self._run_single_variant(
                frame=frame,
                eval_frame=eval_frame,
                horizon=horizon,
                variant="baseline_no_news",
                refined_news_by_date=None,
                event_news_by_date=None,
                event_report_by_date=None,
                policy_items_by_date=policy_snapshot.items_by_date,
                enable_refined_news=False,
                enable_event_risk=False,
                context={
                    "news_mode": "off",
                    "enable_event_risk": False,
                    "archived_policy_sources": policy_snapshot.source_counts,
                },
                notes=[],
            )
            candidate = summary
            summary.comparison = BacktestComparison(
                baseline=BacktestVariantSummary(
                    variant=baseline.variant,
                    sample_size=baseline.sample_size,
                    direction_accuracy=baseline.direction_accuracy,
                    mae=baseline.mae,
                    context=baseline.context,
                ),
                candidate=BacktestVariantSummary(
                    variant=candidate.variant,
                    sample_size=candidate.sample_size,
                    direction_accuracy=candidate.direction_accuracy,
                    mae=candidate.mae,
                    context=candidate.context,
                ),
                delta_direction_accuracy=round(candidate.direction_accuracy - baseline.direction_accuracy, 4),
                delta_mae=round(candidate.mae - baseline.mae, 4),
            )

        return summary

    def _run_single_variant(
        self,
        frame: pd.DataFrame,
        eval_frame: pd.DataFrame,
        horizon: str,
        variant: str,
        refined_news_by_date: dict[date, list[dict[str, Any]]] | None,
        event_news_by_date: dict[date, list[dict[str, Any]]] | None,
        event_report_by_date: dict[date, dict[str, Any] | None] | None,
        policy_items_by_date: dict[date, list[dict[str, Any]]] | None,
        enable_refined_news: bool,
        enable_event_risk: bool,
        context: dict[str, Any],
        notes: list[str],
    ) -> BacktestSummary:
        rows: list[BacktestRow] = []
        for idx, row in eval_frame.iterrows():
            as_of_date = row["date"]
            refined_news_items = refined_news_by_date.get(as_of_date, []) if refined_news_by_date else []
            event_news_items = event_news_by_date.get(as_of_date, []) if event_news_by_date else []
            event_report = event_report_by_date.get(as_of_date) if event_report_by_date else None
            policy_items = policy_items_by_date.get(as_of_date, []) if policy_items_by_date else []
            prediction = self.predictor.predict_from_frame(
                feature_frame=frame,
                as_of_date=as_of_date,
                refined_news_items=refined_news_items,
                report_payload=event_report,
                news_items=event_news_items,
                policy_items=policy_items,
                enable_refined_news=enable_refined_news,
                enable_event_risk=enable_event_risk,
                refined_news_by_date=refined_news_by_date,
                event_news_by_date=event_news_by_date,
                event_report_by_date=event_report_by_date,
            )
            actual_point = float(row["next_day_price"])
            actual_delta = actual_point - float(row["sd_gas92_market"])
            actual_direction = "up" if actual_delta > 0 else "down" if actual_delta < 0 else "flat"
            abs_error = abs(prediction.point_value - actual_point)
            target_date = row.get("next_day_date") or as_of_date
            rows.append(
                BacktestRow(
                    as_of_date=as_of_date,
                    target_date=target_date,
                    predicted_direction=prediction.direction_label,
                    actual_direction=actual_direction,
                    predicted_point=prediction.point_value,
                    actual_point=round(actual_point, 2),
                    abs_error=round(abs_error, 2),
                    hit_direction=prediction.direction_label == actual_direction,
                )
            )

        sample_size = len(rows)
        direction_accuracy = round(sum(1 for row in rows if row.hit_direction) / sample_size, 4) if rows else 0.0
        mae = round(sum(row.abs_error for row in rows) / sample_size, 4) if rows else 0.0
        return BacktestSummary(
            entity_code="SD_GAS92",
            horizon=horizon,
            sample_size=sample_size,
            direction_accuracy=direction_accuracy,
            mae=mae,
            variant=variant,
            context=context,
            notes=notes,
            rows=rows,
        )

    def _build_variant_name(self, news_mode: str, enable_event_risk: bool) -> str:
        if news_mode == "refined_news_archive" and enable_event_risk:
            return "refined_news_plus_event_archive"
        if news_mode == "refined_news_archive":
            return "refined_news_archive"
        if enable_event_risk:
            return "event_risk_archive"
        return "baseline_no_news"

    def _build_context(
        self,
        news_mode: str,
        enable_event_risk: bool,
        refined_news_snapshot: Any,
        policy_snapshot: Any,
        event_snapshot: Any,
    ) -> dict[str, Any]:
        return {
            "news_mode": news_mode,
            "enable_event_risk": enable_event_risk,
            "archived_refined_news_sources": (
                refined_news_snapshot.source_counts if refined_news_snapshot else {}
            ),
            "archive_start": (
                refined_news_snapshot.archive_start.isoformat()
                if refined_news_snapshot and refined_news_snapshot.archive_start
                else None
            ),
            "archive_end": (
                refined_news_snapshot.archive_end.isoformat()
                if refined_news_snapshot and refined_news_snapshot.archive_end
                else None
            ),
            "archived_policy_sources": policy_snapshot.source_counts,
            "policy_archive_start": policy_snapshot.archive_start.isoformat() if policy_snapshot.archive_start else None,
            "policy_archive_end": policy_snapshot.archive_end.isoformat() if policy_snapshot.archive_end else None,
            "archived_event_news_sources": event_snapshot.news_source_counts if event_snapshot else {},
            "event_news_archive_start": (
                event_snapshot.news_archive_start.isoformat() if event_snapshot and event_snapshot.news_archive_start else None
            ),
            "event_news_archive_end": (
                event_snapshot.news_archive_end.isoformat() if event_snapshot and event_snapshot.news_archive_end else None
            ),
            "archived_event_report_sources": event_snapshot.report_source_counts if event_snapshot else {},
            "event_report_archive_start": (
                event_snapshot.report_archive_start.isoformat()
                if event_snapshot and event_snapshot.report_archive_start
                else None
            ),
            "event_report_archive_end": (
                event_snapshot.report_archive_end.isoformat()
                if event_snapshot and event_snapshot.report_archive_end
                else None
            ),
        }

    def _build_notes(
        self,
        news_mode: str,
        enable_event_risk: bool,
        refined_news_snapshot: Any,
        policy_snapshot: Any,
        event_snapshot: Any,
    ) -> list[str]:
        notes: list[str] = []
        if policy_snapshot and policy_snapshot.source_counts:
            notes.append("历史回测已接入发改委成品油调价公告归档，并按 as_of_date 回放政策上下文。")
        else:
            notes.append("当前回测窗口未命中足够的历史政策公告归档，政策解释信息可能退化。")

        if news_mode == "refined_news_archive":
            notes.append("新闻回测使用公开可追溯的成品油资讯归档，不包含需要登录的付费正文。")
            if refined_news_snapshot and not refined_news_snapshot.source_counts:
                notes.append("当前时间窗未抓到足够的历史成品油资讯，结果可能退化为近似基线。")

        if enable_event_risk:
            notes.append("事件风险历史回放使用已落库的 Jinshi 快讯和 Brent 日报快照，不使用 LLM 的裸记忆。")
            if event_snapshot and not event_snapshot.news_source_counts and not event_snapshot.report_source_counts:
                notes.append("当前回测窗口还没有足够的历史事件快照，事件层影响可能接近关闭状态。")

        return notes
