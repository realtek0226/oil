from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.clients.brent_report_client import BrentReportClient
from app.clients.china_money_client import ChinaMoneyCnyMidClient
from app.clients.cnenergy_refined_oil_client import CnEnergyRefinedOilClient
from app.clients.eta_client import EtaClient
from app.clients.jinshi_client import JinshiClient
from app.clients.jlc_refined_oil_client import JlcRefinedOilClient
from app.clients.oilchem_openapi_client import OilchemOpenApiClient
from app.clients.oilchem_price_client import OilchemPriceClient
from app.clients.oilchem_production_sales_client import OilchemProductionSalesClient
from app.clients.refined_oil_news_client import RefinedOilNewsClient
from app.clients.refined_oil_policy_client import RefinedOilPolicyClient
from app.clients.wind_price_client import WindPriceClient
from app.services.fallback_market_data import LocalFallbackMarketDataBuilder
from app.services.indicator_catalog import IndicatorCatalog
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository
from app.services.predictors.horizons import resolve_horizon_config


INDICATOR_KEYS = [
    "sd_gas92_market",
    "cn_gas92_market",
    "east_china_gas92_market",
    "north_china_gas92_market",
    "south_china_gas92_market",
    "central_china_gas92_market",
    "northwest_gas92_market",
    "southwest_gas92_market",
    "northeast_gas92_market",
    "sd_diesel0_market",
    "cn_diesel0_market",
    "east_china_diesel0_market",
    "north_china_diesel0_market",
    "south_china_diesel0_market",
    "central_china_diesel0_market",
    "northwest_diesel0_market",
    "southwest_diesel0_market",
    "northeast_diesel0_market",
    "sd_refining_profit",
    "sd_gas_sales_weekly",
    "sd_crude_run_weekly",
    "sd_ceiling_gas",
    "sd_mtbe_price",
    "sd_naphtha_price",
    "sd_gas_naphtha_spread",
    "sd_gas_shipments_weekly",
    "brent_active_settlement",
]

VAT_RATE = 0.13
BARREL_TO_TON_RATIO = 6.77
GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON = 2109.76
DIESEL_CONSUMPTION_TAX_YUAN_PER_TON = 1411.20
LOCAL_CDU_UTILIZATION_WORKBOOK = Path("数据清单及打分逻辑") / "中鲁" / "成品油周度数据（勿动）.xlsx"
LOCAL_CDU_UTILIZATION_COLUMN = "原油：常减压：产能利用率：山东：独立炼厂（周）"
CDU_UTILIZATION_PERCENTILE_START = date(2024, 1, 1)

GASOLINE_CRACK_PRICE_COLUMNS = {
    "sd_gas92_market": "sd_gas_crack",
    "cn_gas92_market": "cn_gas_crack",
    "east_china_gas92_market": "east_china_gas_crack",
    "north_china_gas92_market": "north_china_gas_crack",
    "south_china_gas92_market": "south_china_gas_crack",
    "central_china_gas92_market": "central_china_gas_crack",
    "northwest_gas92_market": "northwest_gas_crack",
    "southwest_gas92_market": "southwest_gas_crack",
    "northeast_gas92_market": "northeast_gas_crack",
}

DIESEL_CRACK_PRICE_COLUMNS = {
    "sd_diesel0_market": "sd_diesel_crack",
    "cn_diesel0_market": "cn_diesel_crack",
    "east_china_diesel0_market": "east_china_diesel_crack",
    "north_china_diesel0_market": "north_china_diesel_crack",
    "south_china_diesel0_market": "south_china_diesel_crack",
    "central_china_diesel0_market": "central_china_diesel_crack",
    "northwest_diesel0_market": "northwest_diesel_crack",
    "southwest_diesel0_market": "southwest_diesel_crack",
    "northeast_diesel0_market": "northeast_diesel_crack",
}

MANUAL_EXTRA_INDICATOR_KEYS = [
    "cny_mid_rate",
    "usd_cny_mid_rate",
    "usdcny_mid",
    "sales_production_ratio_weekly",
    "sales_production_ratio_d1",
    "sales_production_ratio_d3_avg",
    "sales_production_ratio_w1_avg",
    "shandong_commercial_gasoline_inventory",
    "shandong_trader_inventory",
    "shandong_trade_company_inventory",
    "shandong_main_company_inventory",
    "shandong_independent_refinery_inventory",
    "price_adjustment_expected_yuan",
    "refined_oil_adjustment_expected_yuan",
    "oil_price_adjustment_forecast_yuan",
    "expected_price_adjustment_yuan_per_ton",
    "price_window_expected_adjustment",
]

SNAPSHOT_INDICATOR_KEYS = [
    "brent_active_settlement",
    "sd_gas92_market",
    "cn_gas92_market",
    "east_china_gas92_market",
    "north_china_gas92_market",
    "south_china_gas92_market",
    "central_china_gas92_market",
    "northwest_gas92_market",
    "southwest_gas92_market",
    "northeast_gas92_market",
]

PREFERRED_CASH_PRICE_SOURCE_CODES = (
    "manual_prediction_template",
    "oilchem_refined_oil_price_center",
    "ganglian_excel_import",
    "zhonglu_excel_archive",
)

PREFERRED_CASH_PRICE_INDICATOR_KEYS = (
    "sd_gas92_market",
    "cn_gas92_market",
    "east_china_gas92_market",
    "north_china_gas92_market",
    "south_china_gas92_market",
    "central_china_gas92_market",
    "northwest_gas92_market",
    "southwest_gas92_market",
    "northeast_gas92_market",
    "sd_diesel0_market",
    "cn_diesel0_market",
    "east_china_diesel0_market",
    "north_china_diesel0_market",
    "south_china_diesel0_market",
    "central_china_diesel0_market",
    "northwest_diesel0_market",
    "southwest_diesel0_market",
    "northeast_diesel0_market",
)

PREFERRED_CASH_PRICE_MAX_STALENESS_DAYS = 7


REGIONAL_SPREAD_SPECS = [
    ("east_china_gas92_market", "sd_vs_east_china_spread"),
    ("north_china_gas92_market", "sd_vs_north_china_spread"),
    ("south_china_gas92_market", "sd_vs_south_china_spread"),
    ("central_china_gas92_market", "sd_vs_central_china_spread"),
    ("northwest_gas92_market", "sd_vs_northwest_spread"),
    ("southwest_gas92_market", "sd_vs_southwest_spread"),
    ("northeast_gas92_market", "sd_vs_northeast_spread"),
]


@dataclass
class PredictionContext:
    feature_frame: pd.DataFrame
    current_row: pd.Series
    report_payload: dict[str, Any] | None
    news_items: list[dict[str, Any]]
    refined_news_items: list[dict[str, Any]]
    policy_items: list[dict[str, Any]]
    metadata: dict[str, Any]


class PredictionTimeAlignmentError(RuntimeError):
    def __init__(self, message: str, *, as_of_date: date, report_date: date | None = None) -> None:
        super().__init__(message)
        self.as_of_date = as_of_date
        self.report_date = report_date



@dataclass
class ArchivedRefinedNewsSnapshot:
    items_by_date: dict[date, list[dict[str, Any]]]
    source_counts: dict[str, int]
    archive_start: date | None
    archive_end: date | None


@dataclass
class ArchivedPolicySnapshot:
    items_by_date: dict[date, list[dict[str, Any]]]
    source_counts: dict[str, int]
    archive_start: date | None
    archive_end: date | None


@dataclass
class ArchivedEventRiskSnapshot:
    news_items_by_date: dict[date, list[dict[str, Any]]]
    report_by_date: dict[date, dict[str, Any] | None]
    news_source_counts: dict[str, int]
    report_source_counts: dict[str, int]
    news_archive_start: date | None
    news_archive_end: date | None
    report_archive_start: date | None
    report_archive_end: date | None


class MarketDatasetService:
    ETA_FAST_TIMEOUT = (1.5, 3.0)
    FAST_CONTEXT_NEWS_DAYS = 2
    FEED_LOOKBACK_DAYS = 14
    POLICY_LOOKBACK_DAYS = 120
    CONTEXT_CACHE_SECONDS = 60

    def __init__(
        self,
        eta_client: EtaClient,
        catalog: IndicatorCatalog,
        china_money_client: ChinaMoneyCnyMidClient | None,
        wind_price_client: WindPriceClient,
        brent_report_client: BrentReportClient,
        jinshi_client: JinshiClient,
        refined_oil_news_client: RefinedOilNewsClient,
        oilchem_openapi_client: OilchemOpenApiClient | None,
        oilchem_price_client: OilchemPriceClient,
        oilchem_production_sales_client: OilchemProductionSalesClient,
        cnenergy_refined_oil_client: CnEnergyRefinedOilClient,
        jlc_refined_oil_client: JlcRefinedOilClient,
        policy_client: RefinedOilPolicyClient,
        snapshot_repository: PostgresSnapshotRepository | None = None,
        *,
        web_scraping_enabled: bool = False,
        refined_news_scraping_enabled: bool = False,
        policy_scraping_enabled: bool = False,
        oilchem_spot_report_scraping_enabled: bool = False,
        oilchem_scraping_enabled: bool = False,
    ) -> None:
        self.eta_client = eta_client
        self.catalog = catalog
        self.china_money_client = china_money_client
        self.wind_price_client = wind_price_client
        self.brent_report_client = brent_report_client
        self.jinshi_client = jinshi_client
        self.refined_oil_news_client = refined_oil_news_client
        self.oilchem_openapi_client = oilchem_openapi_client
        self.oilchem_price_client = oilchem_price_client
        self.oilchem_production_sales_client = oilchem_production_sales_client
        self.cnenergy_refined_oil_client = cnenergy_refined_oil_client
        self.jlc_refined_oil_client = jlc_refined_oil_client
        self.policy_client = policy_client
        self.snapshot_repository = snapshot_repository
        self.fallback_builder = LocalFallbackMarketDataBuilder()
        self._eta_availability_cache: tuple[datetime, bool] | None = None
        self.web_scraping_enabled = web_scraping_enabled
        self.refined_news_scraping_enabled = web_scraping_enabled and refined_news_scraping_enabled
        self.policy_scraping_enabled = web_scraping_enabled and policy_scraping_enabled
        self.oilchem_spot_report_scraping_enabled = web_scraping_enabled and oilchem_spot_report_scraping_enabled
        self.oilchem_scraping_enabled = web_scraping_enabled and oilchem_scraping_enabled
        self._context_cache: dict[date, tuple[datetime, PredictionContext]] = {}
        self._feature_frame_cache: dict[tuple[date, date], tuple[datetime, pd.DataFrame]] = {}

    def _report_date_from_payload(self, report_payload: dict[str, Any] | None) -> date | None:
        if not report_payload:
            return None
        report_date_raw = report_payload.get("report_date")
        if isinstance(report_date_raw, date):
            return report_date_raw
        if report_date_raw:
            try:
                return date.fromisoformat(str(report_date_raw)[:10])
            except ValueError:
                return None
        return None

    def _prediction_time_alignment_error(
        self,
        *,
        as_of_date: date,
        report_payload: dict[str, Any] | None,
    ) -> PredictionTimeAlignmentError | None:
        signals = report_payload.get("signals") if report_payload else None
        daily = (signals or {}).get("daily_forecast") or {}
        settlement = (signals or {}).get("brent_settlement")
        report_date = self._report_date_from_payload(report_payload)
        forecast_date = None
        forecast_date_raw = daily.get("forecast_date")
        if forecast_date_raw:
            try:
                forecast_date = date.fromisoformat(str(forecast_date_raw)[:10])
            except ValueError:
                forecast_date = None
        d1_target_date = resolve_horizon_config("D1").target_date_from(as_of_date)
        if forecast_date != d1_target_date:
            # Historical dates may not have archived Brent reports yet; keep legacy fallback for backfills.
            # Current/future runs must have a Brent forecast that covers the D1 target date.
            if as_of_date < date.today():
                return None
            forecast_text = forecast_date.isoformat() if forecast_date else "未取到"
            return PredictionTimeAlignmentError(
                "预测前时间维度未对齐：当前价格基准日为"
                f"{as_of_date.isoformat()}，D1目标日为{d1_target_date.isoformat()}，"
                f"但Brent日报预测日期为{forecast_text}。"
                "系统不能用今天的Brent结算价和今天的Brent预测去生成明天92#油价预测；"
                "请等待拿到覆盖目标日的Brent结算价与预测点位后再生成新预测。",
                as_of_date=as_of_date,
                report_date=report_date,
            )
        if daily.get("point_value") is None or settlement is None:
            return PredictionTimeAlignmentError(
                "预测前数据不完整：Brent日报缺少结算价或目标日预测点位，暂不能生成下一交易日92#油价预测。",
                as_of_date=as_of_date,
                report_date=report_date,
            )
        return None

    def build_context(self, as_of_date: date) -> PredictionContext:
        cached = self._context_cache.get(as_of_date)
        now = datetime.now()
        if cached and (now - cached[0]).total_seconds() <= self.CONTEXT_CACHE_SECONDS:
            return cached[1]
        start_date = as_of_date - timedelta(days=365)
        frame = self.build_feature_frame(start_date=start_date, end_date=as_of_date)
        if frame.empty:
            raise RuntimeError("No feature frame available for requested as_of_date.")
        current_frame = frame[frame["date"] <= as_of_date]
        if current_frame.empty:
            raise RuntimeError("No features available on or before requested as_of_date.")
        report_payload = self._load_report_payload(as_of_date=as_of_date)
        alignment_error = self._prediction_time_alignment_error(as_of_date=as_of_date, report_payload=report_payload)
        if alignment_error is not None:
            raise alignment_error
        news_items = self._load_event_news_items(as_of_date=as_of_date)
        refined_news_items = self._load_refined_news_items(as_of_date=as_of_date)
        policy_items = self._load_policy_items_fast(as_of_date=as_of_date)
        maintenance_plan = self._load_oilchem_maintenance_plan(as_of_date=as_of_date)
        inventory_snapshot = self._load_oilchem_inventory_snapshot(as_of_date=as_of_date)
        self._persist_current_snapshots(
            snapshot_date=as_of_date,
            report_payload=report_payload,
            news_items=news_items,
            refined_news_items=refined_news_items,
            policy_items=policy_items,
        )
        context = PredictionContext(
            feature_frame=frame,
            current_row=current_frame.iloc[-1],
            report_payload=report_payload,
            news_items=news_items,
            refined_news_items=refined_news_items,
            policy_items=policy_items,
            metadata={
                "market_data_mode": frame.attrs.get("market_data_mode", "eta"),
                "market_data_reason": frame.attrs.get("market_data_reason"),
                "price_anchor_date": frame.attrs.get("price_anchor_date"),
                "oilchem_maintenance_plan": maintenance_plan,
                "oilchem_inventory": inventory_snapshot,
            },
        )
        self._context_cache[as_of_date] = (now, context)
        if len(self._context_cache) > 8:
            oldest_key = min(self._context_cache, key=lambda item: self._context_cache[item][0])
            self._context_cache.pop(oldest_key, None)
        return context

    def resolve_default_prediction_as_of(self, run_date: date | None = None) -> date:
        run_date = run_date or date.today()
        if self.snapshot_repository is None:
            return run_date
        start_date = run_date - timedelta(days=10)
        rows = self.snapshot_repository.load_market_timeseries_values(
            source_code="oilchem_production_sales_ratio",
            indicator_codes=["oilchem_sd_gasoline_production_sales_ratio"],
            start_date=start_date,
            end_date=run_date,
        )
        candidate_dates = [
            item["dt"]
            for item in rows
            if item.get("dt") is not None and item.get("dt") <= run_date and item.get("value_num") is not None
        ]
        factor_candidate_date = run_date
        if candidate_dates:
            latest_factor_date = max(candidate_dates)
            if latest_factor_date < run_date:
                next_business_day = (pd.Timestamp(latest_factor_date) + pd.offsets.BDay(1)).date()
                if next_business_day == run_date:
                    factor_candidate_date = latest_factor_date
        latest_cash_price_date = self._latest_preferred_cash_price_date(
            start_date=start_date,
            end_date=run_date,
            indicator_code="sd_gas92_market",
        )
        if latest_cash_price_date is not None and latest_cash_price_date < factor_candidate_date:
            factor_candidate_date = latest_cash_price_date
        report_payload = self._load_report_payload(as_of_date=factor_candidate_date)
        alignment_error = self._prediction_time_alignment_error(
            as_of_date=factor_candidate_date,
            report_payload=report_payload,
        )
        if alignment_error is None:
            return factor_candidate_date
        report_date = alignment_error.report_date
        if report_date is not None and report_date < factor_candidate_date:
            return report_date
        return (pd.Timestamp(factor_candidate_date) - pd.offsets.BDay(1)).date()

    def build_feature_frame(self, start_date: date, end_date: date) -> pd.DataFrame:
        cache_key = (start_date, end_date)
        now = datetime.now()
        cached = self._feature_frame_cache.get(cache_key)
        if cached and (now - cached[0]).total_seconds() <= self.CONTEXT_CACHE_SECONDS:
            return cached[1].copy()
        frame = self._build_feature_frame_uncached(start_date=start_date, end_date=end_date)
        self._feature_frame_cache[cache_key] = (now, frame.copy())
        if len(self._feature_frame_cache) > 12:
            oldest_key = min(self._feature_frame_cache, key=lambda item: self._feature_frame_cache[item][0])
            self._feature_frame_cache.pop(oldest_key, None)
        return frame

    def _build_feature_frame_uncached(self, start_date: date, end_date: date) -> pd.DataFrame:
        fallback_frame = self.fallback_builder.build_feature_frame(start_date=start_date, end_date=end_date)
        fetch_start = start_date - timedelta(days=180)
        policy_items = self._load_policy_items(start_date=fetch_start, end_date=end_date)
        cny_mid_frame = self._fetch_china_money_cny_mid_series(start_date=fetch_start, end_date=end_date)
        if not self._eta_is_available():
            fallback_frame = self._attach_direct_cny_mid_rate(base=fallback_frame, cny_mid_frame=cny_mid_frame)
            return self._finalize_fallback_frame(
                fallback_frame=fallback_frame,
                policy_items=policy_items,
                mode="fallback_local_snapshot",
                reason="eta_unavailable",
            )

        eta_indicator_keys = INDICATOR_KEYS
        series_map = {}
        try:
            base_indicator = self.catalog.get("sd_gas92_market")
            base_frame = self.eta_client.get_series(
                base_indicator,
                start_date=fetch_start,
                end_date=end_date,
                timeout_seconds=self.ETA_FAST_TIMEOUT,
            )
        except Exception:
            base_frame = pd.DataFrame(columns=["date", "value", "update_time"])
        series_map["sd_gas92_market"] = base_frame
        remaining_keys = [key for key in eta_indicator_keys if key != "sd_gas92_market"]
        with ThreadPoolExecutor(max_workers=min(6, len(remaining_keys))) as executor:
            future_map = {
                executor.submit(self._fetch_eta_series, key, fetch_start, end_date): key for key in remaining_keys
            }
            for future in as_completed(future_map):
                key = future_map[future]
                try:
                    series_map[key] = future.result()
                except Exception:
                    series_map[key] = pd.DataFrame(columns=["date", "value", "update_time"])

        base = series_map["sd_gas92_market"][["date", "value"]].rename(columns={"value": "sd_gas92_market"})
        if base.empty:
            return self._finalize_fallback_frame(
                fallback_frame=fallback_frame,
                policy_items=policy_items,
                mode="fallback_local_snapshot",
                reason="eta_empty_base_series",
            )
        base["date"] = pd.to_datetime(base["date"])
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        base = base[(base["date"] >= start_ts) & (base["date"] <= end_ts)].copy()
        base = base.sort_values("date").reset_index(drop=True)
        base_forward_fill_count = 0
        base_price_anchor_date = None
        if not base.empty:
            base_price_anchor_date = pd.Timestamp(base["date"].max()).date().isoformat()
        if not base.empty and pd.Timestamp(base["date"].max()) < end_ts:
            latest_row = base.iloc[-1].copy()
            latest_row["date"] = end_ts
            base = pd.concat([base, latest_row.to_frame().T], ignore_index=True)
            base["date"] = pd.to_datetime(base["date"])
            base = base.sort_values("date").reset_index(drop=True)
            base_forward_fill_count = 1

        for key, frame in series_map.items():
            if key == "sd_gas92_market" or frame.empty:
                continue
            tmp = frame[["date", "value"]].rename(columns={"value": key}).sort_values("date")
            tmp["date"] = pd.to_datetime(tmp["date"])
            base = pd.merge_asof(base, tmp, on="date", direction="backward")

        missing_before_fill = sum(1 for key in eta_indicator_keys if key not in base.columns or base[key].isna().all())
        base = self._fill_missing_market_columns(
            base=base,
            fallback_frame=fallback_frame,
            indicator_keys=eta_indicator_keys,
        )
        base = self._attach_direct_cny_mid_rate(base=base, cny_mid_frame=cny_mid_frame)
        manual_override_count = self._apply_manual_market_overrides(
            base=base,
            start_date=start_date,
            end_date=end_date,
            indicator_codes=[*eta_indicator_keys, *MANUAL_EXTRA_INDICATOR_KEYS],
        )
        if base_forward_fill_count and base_price_anchor_date:
            self._align_forward_filled_market_row_to_anchor(
                base=base,
                synthetic_date=end_ts,
                anchor_date=pd.Timestamp(base_price_anchor_date),
                indicator_keys=eta_indicator_keys,
            )
        cash_price_overlay_count, cash_price_anchor_date = self._apply_preferred_cash_price_asof_overrides(
            base=base,
            start_date=start_date,
            end_date=end_date,
        )
        if cash_price_anchor_date:
            base_price_anchor_date = cash_price_anchor_date
        manual_overlay_count = self._attach_local_market_factor_overlay(
            base=base,
            start_date=fetch_start,
            end_date=end_date,
        )
        base = self._attach_oilchem_production_sales_ratio(base=base, end_date=end_date)
        base = self._attach_oilchem_weekly_metrics(base=base, end_date=end_date)
        base = self._attach_local_cdu_utilization_weekly(base=base, end_date=end_date)
        base = self._attach_oilchem_inventory(base=base, end_date=end_date)
        base = self._compute_features(base, policy_items=policy_items)
        base["date"] = pd.to_datetime(base["date"]).dt.date
        base.attrs["market_data_mode"] = "eta_manual_overlay" if manual_override_count else (
            "eta_with_fallback_fill" if missing_before_fill or base_forward_fill_count else "eta"
        )
        reason_parts = []
        if manual_override_count:
            reason_parts.append(f"local_market_overrides={manual_override_count}")
        if manual_overlay_count:
            reason_parts.append(f"local_factor_overlay={manual_overlay_count}")
        if cash_price_overlay_count:
            reason_parts.append(f"cash_price_overlay={cash_price_overlay_count}")
        if not cny_mid_frame.empty:
            reason_parts.append("cny_mid_source=china_money")
        if base_forward_fill_count:
            reason_parts.append(f"base_price_forward_fill={base_forward_fill_count}")
        base.attrs["market_data_reason"] = ";".join(reason_parts) if reason_parts else None
        base.attrs["price_anchor_date"] = base_price_anchor_date
        return base

    def _fetch_china_money_cny_mid_series(self, *, start_date: date, end_date: date) -> pd.DataFrame:
        if self.china_money_client is None:
            return pd.DataFrame(columns=["date", "cny_mid_rate"])
        try:
            return self.china_money_client.get_usd_cny_mid_series(start_date=start_date, end_date=end_date)
        except Exception:
            return pd.DataFrame(columns=["date", "cny_mid_rate"])

    def _attach_direct_cny_mid_rate(self, *, base: pd.DataFrame, cny_mid_frame: pd.DataFrame) -> pd.DataFrame:
        if base.empty or cny_mid_frame.empty:
            return base
        result = base.copy()
        result["date"] = pd.to_datetime(result["date"])
        fx = cny_mid_frame[["date", "cny_mid_rate"]].copy()
        fx["date"] = pd.to_datetime(fx["date"])
        fx = fx.sort_values("date")
        merged = pd.merge_asof(
            result.sort_values("date"),
            fx,
            on="date",
            direction="backward",
            suffixes=("", "_china_money"),
        )
        if "cny_mid_rate_china_money" in merged.columns:
            merged["cny_mid_rate"] = pd.to_numeric(
                merged["cny_mid_rate_china_money"],
                errors="coerce",
            ).combine_first(pd.to_numeric(merged.get("cny_mid_rate"), errors="coerce"))
            merged = merged.drop(columns=["cny_mid_rate_china_money"])
        return merged.sort_values("date").reset_index(drop=True)

    def get_price_history(
        self,
        *,
        start_date: date,
        end_date: date,
        series_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        available_series = [
            {"key": "sd_gas92_market", "label": "山东 92#"},
            {"key": "cn_gas92_market", "label": "全国 92#"},
            {"key": "east_china_gas92_market", "label": "华东 92#"},
            {"key": "north_china_gas92_market", "label": "华北 92#"},
            {"key": "south_china_gas92_market", "label": "华南 92#"},
            {"key": "central_china_gas92_market", "label": "华中 92#"},
            {"key": "northwest_gas92_market", "label": "西北 92#"},
            {"key": "southwest_gas92_market", "label": "西南 92#"},
            {"key": "northeast_gas92_market", "label": "东北 92#"},
        ]
        label_map = {item["key"]: item["label"] for item in available_series}
        requested = [key for key in (series_keys or []) if key in label_map]
        if not requested:
            requested = ["sd_gas92_market", "cn_gas92_market", "east_china_gas92_market"]
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        frame = self.build_feature_frame(start_date=start_date, end_date=end_date)
        if frame.empty:
            rows = pd.DataFrame(columns=["date"])
        else:
            frame = frame.copy()
            frame["date"] = pd.to_datetime(frame["date"])
            rows = frame[(frame["date"] >= pd.Timestamp(start_date)) & (frame["date"] <= pd.Timestamp(end_date))].copy()
            rows = rows.sort_values("date")

        series = []
        for key in requested:
            if key not in rows.columns:
                points = []
            else:
                points = [
                    {
                        "date": item["date"].date().isoformat() if hasattr(item["date"], "date") else str(item["date"])[:10],
                        "value": self._round_or_none(item[key]),
                    }
                    for _, item in rows[["date", key]].dropna(subset=[key]).iterrows()
                ]
            series.append({"key": key, "label": label_map[key], "unit": "元/吨", "points": points})

        return {
            "start_date": start_date,
            "end_date": end_date,
            "generated_at": datetime.now(),
            "available_series": available_series,
            "series": series,
            "metadata": {
                "market_data_mode": frame.attrs.get("market_data_mode", "eta") if not frame.empty else "empty",
                "market_data_reason": frame.attrs.get("market_data_reason") if not frame.empty else "empty_frame",
            },
        }

    def build_archived_refined_news_snapshot(
        self,
        start_date: date,
        end_date: date,
        lookback_days: int = 3,
        per_day_limit: int = 16,
    ) -> ArchivedRefinedNewsSnapshot:
        archive_fetch_start = start_date - timedelta(days=lookback_days)
        if self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_refined_news_items(
                    start_date=archive_fetch_start,
                    end_date=end_date,
                )
                if load_result.items:
                    return self._build_archived_snapshot_from_items(
                        archive_items=load_result.items,
                        start_date=start_date,
                        end_date=end_date,
                        lookback_days=lookback_days,
                        per_day_limit=per_day_limit,
                        source_counts=load_result.source_counts,
                        archive_start=load_result.archive_start,
                        archive_end=load_result.archive_end,
                    )
            except Exception:
                pass

        if not self.refined_news_scraping_enabled:
            return self._build_archived_snapshot_from_items(
                archive_items=[],
                start_date=start_date,
                end_date=end_date,
                lookback_days=lookback_days,
                per_day_limit=per_day_limit,
            )

        jlc_max_pages = min(max(((end_date - archive_fetch_start).days + 1) * 3, 10), 90)
        archive_items: list[dict[str, Any]] = []
        try:
            archive_items.extend(
                self.jlc_refined_oil_client.fetch_archive_titles(
                    start_date=archive_fetch_start,
                    end_date=end_date,
                    max_pages=jlc_max_pages,
                    item_limit=600,
                )
            )
        except Exception:
            pass
        try:
            archive_items.extend(self.cnenergy_refined_oil_client.fetch_recent(limit=80, list_limit=200))
        except Exception:
            pass

        return self._build_archived_snapshot_from_items(
            archive_items=archive_items,
            start_date=start_date,
            end_date=end_date,
            lookback_days=lookback_days,
            per_day_limit=per_day_limit,
        )

    def build_archived_policy_snapshot(
        self,
        start_date: date,
        end_date: date,
        lookback_days: int = 45,
        per_day_limit: int = 6,
    ) -> ArchivedPolicySnapshot:
        archive_fetch_start = start_date - timedelta(days=lookback_days)
        if self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_policy_items(
                    start_date=archive_fetch_start,
                    end_date=end_date,
                )
                if load_result.items:
                    return self._build_archived_policy_snapshot_from_items(
                        archive_items=load_result.items,
                        start_date=start_date,
                        end_date=end_date,
                        lookback_days=lookback_days,
                        per_day_limit=per_day_limit,
                        source_counts=load_result.source_counts,
                        archive_start=load_result.archive_start,
                        archive_end=load_result.archive_end,
                    )
            except Exception:
                pass

        archive_items = self._load_policy_items(start_date=archive_fetch_start, end_date=end_date)
        return self._build_archived_policy_snapshot_from_items(
            archive_items=archive_items,
            start_date=start_date,
            end_date=end_date,
            lookback_days=lookback_days,
            per_day_limit=per_day_limit,
        )

    def _eta_is_available(self) -> bool:
        return False

    def _fetch_eta_series(self, key: str, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            indicator = self.catalog.get(key)
            return self.eta_client.get_series(
                indicator,
                start_date=start_date,
                end_date=end_date,
                timeout_seconds=self.ETA_FAST_TIMEOUT,
            )
        except Exception:
            return pd.DataFrame(columns=["date", "value", "update_time"])

    def _fill_missing_market_columns(
        self,
        base: pd.DataFrame,
        fallback_frame: pd.DataFrame,
        indicator_keys: list[str],
    ) -> pd.DataFrame:
        if base.empty or fallback_frame.empty:
            return base
        fallback = fallback_frame.copy()
        fallback["date"] = pd.to_datetime(fallback["date"])
        merged = base.copy()
        for key in indicator_keys:
            if key not in fallback.columns:
                continue
            fill_column = f"__fallback_{key}"
            merged = merged.merge(
                fallback[["date", key]].rename(columns={key: fill_column}),
                on="date",
                how="left",
            )
            if key not in merged.columns:
                merged[key] = merged[fill_column]
            else:
                merged[key] = pd.to_numeric(merged[key], errors="coerce").fillna(merged[fill_column])
            merged = merged.drop(columns=[fill_column])
        return merged

    def _apply_manual_market_overrides(
        self,
        base: pd.DataFrame,
        start_date: date,
        end_date: date,
        indicator_codes: list[str],
    ) -> int:
        if base.empty or not self.snapshot_repository or not self.snapshot_repository.enabled:
            return 0
        override_count = 0
        base["date"] = pd.to_datetime(base["date"])
        for source_code in (
            "oilchem_refined_oil_price_center",
            "zhonglu_excel_archive",
            "ganglian_excel_import",
            "wind_brent_settlement",
            "manual_prediction_template",
        ):
            try:
                rows = self.snapshot_repository.load_market_timeseries_values(
                    source_code=source_code,
                    indicator_codes=indicator_codes,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                continue
            if not rows:
                continue
            manual = pd.DataFrame(rows)
            manual = manual[manual["value_num"].notna()].copy()
            if manual.empty:
                continue
            manual["date"] = pd.to_datetime(manual["dt"])
            pivot = (
                manual.sort_values(["date", "indicator_code", "publish_time"])
                .drop_duplicates(subset=["date", "indicator_code"], keep="last")
                .pivot(index="date", columns="indicator_code", values="value_num")
                .reset_index()
            )
            for _, manual_row in pivot.iterrows():
                mask = base["date"] == pd.Timestamp(manual_row["date"])
                if not bool(mask.any()):
                    continue
                for key in indicator_codes:
                    if key not in pivot.columns or pd.isna(manual_row.get(key)):
                        continue
                    if key not in base.columns:
                        base[key] = np.nan
                    base.loc[mask, key] = float(manual_row[key])
                    override_count += int(mask.sum())
        return override_count

    def _load_preferred_cash_price_records(
        self,
        *,
        indicator_codes: list[str] | tuple[str, ...],
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return []
        records: list[dict[str, Any]] = []
        requested = [key for key in indicator_codes if key in PREFERRED_CASH_PRICE_INDICATOR_KEYS]
        if not requested:
            return records
        for source_priority, source_code in enumerate(PREFERRED_CASH_PRICE_SOURCE_CODES):
            try:
                rows = self.snapshot_repository.load_market_timeseries_values(
                    source_code=source_code,
                    indicator_codes=requested,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                continue
            for row in rows:
                if row.get("dt") is None or row.get("value_num") is None:
                    continue
                records.append({**row, "source_code": source_code, "source_priority": source_priority})
        return records

    def _cash_record_is_better(self, candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
        if current is None:
            return True
        candidate_key = (
            candidate.get("dt"),
            -int(candidate.get("source_priority") or 0),
            str(candidate.get("publish_time") or ""),
        )
        current_key = (
            current.get("dt"),
            -int(current.get("source_priority") or 0),
            str(current.get("publish_time") or ""),
        )
        return candidate_key > current_key

    def _latest_preferred_cash_price_date(
        self,
        *,
        start_date: date,
        end_date: date,
        indicator_code: str,
    ) -> date | None:
        records = self._load_preferred_cash_price_records(
            indicator_codes=[indicator_code],
            start_date=start_date,
            end_date=end_date,
        )
        dates = [item["dt"] for item in records if item.get("dt") is not None]
        return max(dates) if dates else None

    def _select_preferred_cash_price_records_asof(
        self,
        *,
        as_of_date: date,
        indicator_codes: list[str] | tuple[str, ...],
    ) -> dict[str, dict[str, Any]]:
        records = self._load_preferred_cash_price_records(
            indicator_codes=indicator_codes,
            start_date=as_of_date - timedelta(days=PREFERRED_CASH_PRICE_MAX_STALENESS_DAYS),
            end_date=as_of_date,
        )
        selected: dict[str, dict[str, Any]] = {}
        for record in records:
            record_date = record.get("dt")
            if record_date is None or record_date > as_of_date:
                continue
            key = str(record.get("indicator_code") or "")
            if self._cash_record_is_better(record, selected.get(key)):
                selected[key] = record
        return selected

    def _apply_preferred_cash_price_asof_overrides(
        self,
        *,
        base: pd.DataFrame,
        start_date: date,
        end_date: date,
    ) -> tuple[int, str | None]:
        if base.empty:
            return 0, None
        records = self._load_preferred_cash_price_records(
            indicator_codes=PREFERRED_CASH_PRICE_INDICATOR_KEYS,
            start_date=start_date - timedelta(days=PREFERRED_CASH_PRICE_MAX_STALENESS_DAYS),
            end_date=end_date,
        )
        if not records:
            return 0, None

        best_by_day: dict[tuple[str, date], dict[str, Any]] = {}
        for record in records:
            record_date = record.get("dt")
            key = str(record.get("indicator_code") or "")
            if record_date is None or not key:
                continue
            record_key = (key, record_date)
            if self._cash_record_is_better(record, best_by_day.get(record_key)):
                best_by_day[record_key] = record

        base["date"] = pd.to_datetime(base["date"])
        base_dates = base[["date"]].sort_values("date")
        applied = 0
        anchor_date: str | None = None
        for key in PREFERRED_CASH_PRICE_INDICATOR_KEYS:
            rows = [record for (indicator_code, _), record in best_by_day.items() if indicator_code == key]
            if not rows:
                continue
            series = pd.DataFrame(
                {
                    "date": pd.to_datetime([record["dt"] for record in rows]),
                    "__cash_value": [float(record["value_num"]) for record in rows],
                    "__cash_source": [record["source_code"] for record in rows],
                }
            ).sort_values("date")
            merged = pd.merge_asof(
                base_dates,
                series,
                on="date",
                direction="backward",
                tolerance=pd.Timedelta(days=PREFERRED_CASH_PRICE_MAX_STALENESS_DAYS),
            )
            value_by_date = merged.dropna(subset=["__cash_value"]).set_index("date")["__cash_value"]
            if value_by_date.empty:
                continue
            if key not in base.columns:
                base[key] = np.nan
            mask = base["date"].isin(value_by_date.index)
            base.loc[mask, key] = base.loc[mask, "date"].map(value_by_date)
            applied += int(mask.sum())
            if key == "sd_gas92_market":
                anchor_rows = merged[merged["date"] <= pd.Timestamp(end_date)].dropna(subset=["__cash_value"])
                if not anchor_rows.empty:
                    cash_date = pd.Timestamp(anchor_rows.iloc[-1]["date"]).date()
                    latest_source_date = max(
                        record["dt"]
                        for record in rows
                        if record.get("dt") is not None and record["dt"] <= cash_date
                    )
                    anchor_date = latest_source_date.isoformat()
        return applied, anchor_date

    def _overlay_preferred_cash_price_snapshot(
        self,
        *,
        latest_prices: dict[str, float | None],
        as_of_date: date,
    ) -> str | None:
        selected = self._select_preferred_cash_price_records_asof(
            as_of_date=as_of_date,
            indicator_codes=[key for key in latest_prices if key in PREFERRED_CASH_PRICE_INDICATOR_KEYS],
        )
        if not selected:
            return None
        reason_parts: list[str] = []
        for key, record in sorted(selected.items()):
            latest_prices[key] = self._round_or_none(record.get("value_num"))
            reason_parts.append(f"{key}@{record.get('dt')}:{record.get('source_code')}")
        return "cash_price_overlay=" + ",".join(reason_parts)

    def _align_forward_filled_market_row_to_anchor(
        self,
        *,
        base: pd.DataFrame,
        synthetic_date: pd.Timestamp,
        anchor_date: pd.Timestamp,
        indicator_keys: list[str],
    ) -> None:
        if base.empty:
            return
        base["date"] = pd.to_datetime(base["date"])
        synthetic_mask = base["date"] == synthetic_date
        anchor_mask = base["date"] == anchor_date
        if not bool(synthetic_mask.any()) or not bool(anchor_mask.any()):
            return
        anchor_row = base.loc[anchor_mask].iloc[-1]
        for key in indicator_keys:
            if key not in base.columns or key not in anchor_row.index or pd.isna(anchor_row.get(key)):
                continue
            synthetic_value = base.loc[synthetic_mask, key].iloc[-1]
            if not pd.isna(synthetic_value) and not np.isclose(float(synthetic_value), float(anchor_row[key])):
                continue
            base.loc[synthetic_mask, key] = anchor_row[key]

    def _attach_local_market_factor_overlay(self, base: pd.DataFrame, start_date: date, end_date: date) -> int:
        if base.empty or not self.snapshot_repository or not self.snapshot_repository.enabled:
            return 0
        overlay_keys = [
            "sales_production_ratio_weekly",
            "sales_production_ratio_d1",
            "sales_production_ratio_d3_avg",
            "sales_production_ratio_w1_avg",
            "sd_gas_production_weekly",
            "sd_gas_sales_weekly",
            "sd_crude_run_weekly",
            "shandong_commercial_gasoline_inventory",
            "shandong_trader_inventory",
            "shandong_trade_company_inventory",
            "shandong_main_company_inventory",
            "shandong_independent_refinery_inventory",
            "price_adjustment_expected_yuan",
            "refined_oil_adjustment_expected_yuan",
            "oil_price_adjustment_forecast_yuan",
            "expected_price_adjustment_yuan_per_ton",
            "price_window_expected_adjustment",
        ]
        overlays: list[pd.DataFrame] = []
        for source_code in (
            "zhonglu_excel_archive",
            "ganglian_excel_import",
            "wind_brent_settlement",
            "manual_prediction_template",
        ):
            try:
                rows = self.snapshot_repository.load_market_timeseries_values(
                    source_code=source_code,
                    indicator_codes=overlay_keys,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                continue
            if not rows:
                continue
            data = pd.DataFrame(rows)
            data = data[data["value_num"].notna()].copy()
            if data.empty:
                continue
            data["date"] = pd.to_datetime(data["dt"])
            pivot = (
                data.sort_values(["date", "indicator_code", "publish_time"])
                .drop_duplicates(subset=["date", "indicator_code"], keep="last")
                .pivot(index="date", columns="indicator_code", values="value_num")
                .reset_index()
            )
            if not pivot.empty:
                overlays.append(pivot)
        if not overlays:
            return 0

        overlay_rows = pd.concat(overlays, ignore_index=True, sort=False)
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"])
        merge_dates = merged[["date"]].sort_values("date")
        applied = 0
        for key in overlay_keys:
            if key not in overlay_rows.columns:
                continue
            series_frame = overlay_rows[["date", key]].dropna(subset=[key]).copy()
            if series_frame.empty:
                continue
            series_frame = (
                series_frame.sort_values("date")
                .drop_duplicates(subset=["date"], keep="last")
                .rename(columns={key: "__overlay_value"})
            )
            aligned = pd.merge_asof(
                merge_dates,
                series_frame,
                on="date",
                direction="backward",
            )["__overlay_value"]
            aligned.index = base.index
            if key in base.columns:
                new_series = aligned.combine_first(pd.Series(base[key], index=base.index))
            else:
                new_series = aligned
            base[key] = new_series.to_numpy()
            applied += int(pd.Series(new_series).notna().sum())
        if "sales_production_ratio_weekly" in base.columns:
            if "sales_production_ratio_d1" not in base.columns:
                base["sales_production_ratio_d1"] = np.nan
            base["sales_production_ratio_d1"] = pd.Series(base["sales_production_ratio_d1"]).combine_first(
                pd.Series(base["sales_production_ratio_weekly"])
            ).to_numpy()
        return applied

    def _attach_oilchem_production_sales_ratio(self, base: pd.DataFrame, end_date: date) -> pd.DataFrame:
        if base.empty:
            return base
        records = self._load_archived_oilchem_records(
            source_codes=["oilchem_production_sales_ratio"],
            end_date=end_date,
            limit_per_source=20,
        )
        rows = [
            {
                "date": pd.Timestamp(record_date),
                "sales_production_ratio_d1": record.get("gasoline_ratio"),
                "sales_production_ratio_source": record.get("source"),
                "sales_production_ratio_url": record.get("url"),
                "sales_production_ratio_publish_time": record.get("publish_time"),
            }
            for record in records
            for record_date in [self._oilchem_record_date(record)]
            if record.get("gasoline_ratio") is not None and record_date is not None and record_date <= end_date
        ]
        if not rows:
            return base
        ratio_frame = pd.DataFrame(rows).sort_values("date")
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"])
        merged = pd.merge_asof(
            merged.sort_values("date"),
            ratio_frame,
            on="date",
            direction="backward",
            tolerance=pd.Timedelta(days=1),
            suffixes=("", "_oilchem"),
        )
        oilchem_ratio_col = "sales_production_ratio_d1_oilchem"
        if oilchem_ratio_col in merged.columns:
            if "sales_production_ratio_d1" in merged.columns:
                merged["sales_production_ratio_d1"] = merged[oilchem_ratio_col].combine_first(
                    merged["sales_production_ratio_d1"]
                )
            else:
                merged["sales_production_ratio_d1"] = merged[oilchem_ratio_col]
            merged = merged.drop(columns=[oilchem_ratio_col])
        for column in (
            "sales_production_ratio_source",
            "sales_production_ratio_url",
            "sales_production_ratio_publish_time",
        ):
            oilchem_column = f"{column}_oilchem"
            if oilchem_column in merged.columns:
                if column in merged.columns:
                    merged[column] = merged[oilchem_column].combine_first(merged[column])
                else:
                    merged[column] = merged[oilchem_column]
                merged = merged.drop(columns=[oilchem_column])
        return merged

    def _attach_oilchem_weekly_metrics(self, base: pd.DataFrame, end_date: date) -> pd.DataFrame:
        if base.empty:
            return base
        records = self._load_archived_oilchem_records(
            source_codes=["oilchem_weekly_refinery_metrics"],
            end_date=end_date,
            limit_per_source=8,
        )

        rows: list[dict[str, Any]] = []
        for record in records:
            record_date = self._oilchem_record_date(record)
            if record_date is None or record_date > end_date:
                continue
            row: dict[str, Any] = {
                "date": pd.Timestamp(record_date),
                "oilchem_weekly_metric_source": record.get("source"),
                "oilchem_weekly_metric_url": record.get("url"),
                "oilchem_weekly_metric_publish_time": record.get("publish_time"),
            }
            if record.get("capacity_utilization") is not None:
                row["sd_crude_run_weekly"] = record.get("capacity_utilization")
                row["shandong_cdu_utilization_ex_large_weekly"] = record.get("capacity_utilization_ex_large")
                row["shandong_cdu_utilization_wow_pct"] = record.get("capacity_utilization_wow_pct")
                row["shandong_cdu_utilization_yoy_pct"] = record.get("capacity_utilization_yoy_pct")
            if record.get("refining_profit") is not None:
                row["sd_refining_profit"] = record.get("refining_profit")
                row["shandong_refining_profit_wow_pct"] = record.get("refining_profit_wow_pct")
                row["shandong_refining_profit_yoy_pct"] = record.get("refining_profit_yoy_pct")
                row["shandong_crude_cost_weekly"] = record.get("crude_cost")
                row["shandong_crude_cost_change_weekly"] = record.get("crude_cost_change")
                row["shandong_comprehensive_revenue_weekly"] = record.get("comprehensive_revenue")
                row["shandong_comprehensive_revenue_change_weekly"] = record.get("comprehensive_revenue_change")
            rows.append(row)
        if not rows:
            return base

        weekly_frame = pd.DataFrame(rows).sort_values("date").groupby("date", as_index=False).first()
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"])
        merged = pd.merge_asof(
            merged.sort_values("date"),
            weekly_frame,
            on="date",
            direction="backward",
            suffixes=("", "_oilchem"),
        )
        for column in ("sd_crude_run_weekly", "sd_refining_profit"):
            oilchem_column = f"{column}_oilchem"
            if oilchem_column in merged.columns:
                merged[column] = merged[oilchem_column].combine_first(merged[column])
                merged = merged.drop(columns=[oilchem_column])
        return merged

    def _attach_local_cdu_utilization_weekly(self, base: pd.DataFrame, end_date: date) -> pd.DataFrame:
        if base.empty:
            return base
        weekly = self._load_local_cdu_utilization_weekly(end_date=end_date)
        if weekly.empty:
            return base
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")
        weekly = weekly.copy()
        weekly["date"] = pd.to_datetime(weekly["date"]).astype("datetime64[ns]")
        merged = pd.merge_asof(
            merged.sort_values("date"),
            weekly.sort_values("date"),
            on="date",
            direction="backward",
            suffixes=("", "_local_cdu"),
        )
        local_columns = {
            "sd_crude_run_weekly_local_cdu": "sd_crude_run_weekly",
            "shandong_cdu_utilization_wow_pct_local_cdu": "shandong_cdu_utilization_wow_pct",
            "shandong_cdu_utilization_percentile_weekly_local_cdu": "shandong_cdu_utilization_percentile_weekly",
        }
        for local_column, target_column in local_columns.items():
            if local_column not in merged.columns:
                continue
            if target_column in merged.columns:
                merged[target_column] = merged[local_column].combine_first(merged[target_column])
            else:
                merged[target_column] = merged[local_column]
            merged = merged.drop(columns=[local_column])
        if "shandong_cdu_utilization_source_local_cdu" in merged.columns:
            current_source = (
                merged["shandong_cdu_utilization_source"]
                if "shandong_cdu_utilization_source" in merged.columns
                else pd.Series(np.nan, index=merged.index)
            )
            merged["shandong_cdu_utilization_source"] = merged[
                "shandong_cdu_utilization_source_local_cdu"
            ].combine_first(current_source)
            merged = merged.drop(columns=["shandong_cdu_utilization_source_local_cdu"])
        return merged

    def _load_local_cdu_utilization_weekly(self, end_date: date) -> pd.DataFrame:
        path = LOCAL_CDU_UTILIZATION_WORKBOOK
        if not path.exists():
            return pd.DataFrame()
        try:
            workbook = pd.ExcelFile(path)
            sheet_name = next((name for name in workbook.sheet_names if name == "开工率"), workbook.sheet_names[4])
            raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
        except Exception:
            return pd.DataFrame()
        if raw.empty or raw.shape[0] < 5:
            return pd.DataFrame()
        header = raw.iloc[1].astype(str)
        target_columns = [idx for idx, value in header.items() if value == LOCAL_CDU_UTILIZATION_COLUMN]
        if not target_columns:
            return pd.DataFrame()
        target_column = target_columns[0]
        weekly = raw.iloc[4:, [0, target_column]].copy()
        weekly.columns = ["date", "sd_crude_run_weekly"]
        weekly["date"] = pd.to_datetime(weekly["date"], errors="coerce")
        weekly["sd_crude_run_weekly"] = pd.to_numeric(weekly["sd_crude_run_weekly"], errors="coerce")
        weekly = weekly.dropna(subset=["date", "sd_crude_run_weekly"])
        if weekly.empty:
            return pd.DataFrame()
        weekly = weekly[
            (weekly["date"].dt.date >= CDU_UTILIZATION_PERCENTILE_START)
            & (weekly["date"].dt.date <= end_date)
        ].copy()
        if weekly.empty:
            return pd.DataFrame()
        weekly = weekly.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        weekly["shandong_cdu_utilization_wow_pct"] = weekly["sd_crude_run_weekly"].diff()
        weekly["shandong_cdu_utilization_percentile_weekly"] = self._expanding_percentile(
            weekly["sd_crude_run_weekly"],
            min_periods=5,
        )
        weekly["shandong_cdu_utilization_source"] = "local_zhonglu_weekly_cdu_utilization"
        return weekly

    def _attach_oilchem_inventory(self, base: pd.DataFrame, end_date: date) -> pd.DataFrame:
        if base.empty:
            return base
        records = self._load_archived_oilchem_records(
            source_codes=["oilchem_refinery_inventory"],
            end_date=end_date,
            limit_per_source=6,
        )

        rows = [
            {
                "date": pd.Timestamp(record_date),
                "shandong_product_inventory_total": record.get("total_inventory"),
                "shandong_gasoline_inventory": record.get("gasoline_inventory"),
                "shandong_gasoline_inventory_change_mom": record.get("gasoline_inventory_change_mom"),
                "shandong_gasoline_inventory_capacity_rate": record.get("gasoline_inventory_capacity_rate"),
                "shandong_diesel_inventory": record.get("diesel_inventory"),
                "shandong_diesel_inventory_change_mom": record.get("diesel_inventory_change_mom"),
                "shandong_diesel_inventory_capacity_rate": record.get("diesel_inventory_capacity_rate"),
                "oilchem_inventory_source": record.get("source"),
                "oilchem_inventory_url": record.get("url"),
                "oilchem_inventory_publish_time": record.get("publish_time"),
            }
            for record in records
            for record_date in [self._oilchem_record_date(record)]
            if record_date is not None and record_date <= end_date
        ]
        if not rows:
            return base

        inventory_frame = pd.DataFrame(rows).sort_values("date").groupby("date", as_index=False).first()
        inventory_frame["date"] = pd.to_datetime(inventory_frame["date"]).astype("datetime64[ns]")
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")
        return pd.merge_asof(
            merged.sort_values("date"),
            inventory_frame,
            on="date",
            direction="backward",
        )

    def _load_oilchem_maintenance_plan(self, as_of_date: date) -> dict[str, Any] | None:
        records = self._load_archived_oilchem_records(
            source_codes=["oilchem_refinery_maintenance_plan"],
            end_date=as_of_date,
            limit_per_source=5,
        )
        valid_records = [
            record for record in records if (self._oilchem_record_date(record) or date.max) <= as_of_date
        ]
        if not valid_records:
            return None
        return sorted(valid_records, key=lambda item: self._oilchem_record_date(item) or date.min, reverse=True)[0]

    def _load_oilchem_inventory_snapshot(self, as_of_date: date) -> dict[str, Any] | None:
        records = self._load_archived_oilchem_records(
            source_codes=["oilchem_refinery_inventory"],
            end_date=as_of_date,
            limit_per_source=5,
        )
        valid_records = [
            record for record in records if (self._oilchem_record_date(record) or date.max) <= as_of_date
        ]
        if not valid_records:
            return None
        return sorted(valid_records, key=lambda item: self._oilchem_record_date(item) or date.min, reverse=True)[0]

    def _load_archived_oilchem_records(
        self,
        *,
        source_codes: list[str],
        end_date: date,
        limit_per_source: int,
    ) -> list[dict[str, Any]]:
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return []
        try:
            archived = self.snapshot_repository.load_latest_raw_market_payloads(
                source_codes=source_codes,
                end_date=end_date,
                limit_per_source=limit_per_source,
            )
        except Exception:
            return []
        records: list[dict[str, Any]] = []
        for source_code in source_codes:
            for item in archived.get(source_code) or []:
                record = dict(item)
                record.setdefault("source", source_code)
                records.append(record)
        return records

    def _oilchem_record_date(self, record: dict[str, Any]) -> date | None:
        raw_value = record.get("observation_date") or record.get("publish_time") or record.get("date")
        if isinstance(raw_value, datetime):
            return raw_value.date()
        if isinstance(raw_value, date):
            return raw_value
        value = str(raw_value or "").replace("/", "-").strip()
        if len(value) < 10:
            return None
        try:
            return pd.Timestamp(value[:10]).date()
        except Exception:
            return None

    def _finalize_fallback_frame(
        self,
        *,
        fallback_frame: pd.DataFrame,
        policy_items: list[dict[str, Any]],
        mode: str,
        reason: str,
    ) -> pd.DataFrame:
        frame = fallback_frame.copy()
        frame_end_date = pd.to_datetime(frame["date"]).max().date() if not frame.empty else date.today()
        manual_override_count = self._apply_manual_market_overrides(
            base=frame,
            start_date=pd.to_datetime(frame["date"]).min().date() if not frame.empty else frame_end_date,
            end_date=frame_end_date,
            indicator_codes=[*INDICATOR_KEYS, *MANUAL_EXTRA_INDICATOR_KEYS],
        )
        cash_price_overlay_count, cash_price_anchor_date = self._apply_preferred_cash_price_asof_overrides(
            base=frame,
            start_date=pd.to_datetime(frame["date"]).min().date() if not frame.empty else frame_end_date,
            end_date=frame_end_date,
        )
        frame = self._attach_oilchem_production_sales_ratio(base=frame, end_date=frame_end_date)
        frame = self._attach_oilchem_weekly_metrics(base=frame, end_date=frame_end_date)
        frame = self._attach_local_cdu_utilization_weekly(base=frame, end_date=frame_end_date)
        frame = self._attach_oilchem_inventory(base=frame, end_date=frame_end_date)
        frame = self._compute_features(frame, policy_items=policy_items)
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        frame.attrs["market_data_mode"] = mode
        reason_parts = [reason]
        if manual_override_count:
            reason_parts.append(f"local_market_overrides={manual_override_count}")
        if cash_price_overlay_count:
            reason_parts.append(f"cash_price_overlay={cash_price_overlay_count}")
        frame.attrs["market_data_reason"] = ";".join(reason_parts)
        frame.attrs["price_anchor_date"] = cash_price_anchor_date
        return frame

    def _load_report_payload(self, as_of_date: date) -> dict[str, Any] | None:
        archived_payload: dict[str, Any] | None = None
        if self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_brent_reports(
                    start_date=as_of_date - timedelta(days=7),
                    end_date=as_of_date,
                )
                if load_result.items:
                    latest_item = load_result.items[0]
                    normalized = dict(latest_item)
                    normalized = self.brent_report_client.normalize_payload(normalized)
                    normalized["source"] = str(normalized.get("source") or "brent_daily_report")
                    if str(normalized.get("report_date") or "") == as_of_date.isoformat():
                        return normalized
                    archived_payload = normalized
            except Exception:
                pass
        if as_of_date < date.today():
            return archived_payload
        try:
            payload = self.brent_report_client.fetch_latest()
            return {**payload, "source": "brent_daily_report"}
        except Exception:
            return archived_payload

    def _load_event_news_items(self, as_of_date: date, *, prefer_archive: bool = True) -> list[dict[str, Any]]:
        if prefer_archive and self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_jinshi_news_items(
                    start_date=as_of_date - timedelta(days=self.FAST_CONTEXT_NEWS_DAYS),
                    end_date=as_of_date,
                )
                if load_result.items:
                    deduped = self._dedupe_news_items(
                        [
                            {**item, "source": str(item.get("source") or "jinshi_crude_news")}
                            for item in load_result.items
                            if self._is_news_item_available_by_cutoff(item, as_of_date)
                        ]
                    )
                    return deduped[:40]
            except Exception:
                pass
        try:
            return self._dedupe_news_items(
                [
                    {**item, "source": str(item.get("source") or "jinshi_crude_news")}
                    for item in self.jinshi_client.fetch_recent(days=self.FAST_CONTEXT_NEWS_DAYS)
                    if self._is_news_item_available_by_cutoff(item, as_of_date)
                ]
            )[:40]
        except Exception:
            return []

    def _load_refined_news_items(self, as_of_date: date, *, prefer_archive: bool = True) -> list[dict[str, Any]]:
        if prefer_archive and self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_refined_news_items(
                    start_date=as_of_date - timedelta(days=3),
                    end_date=as_of_date,
                )
                if load_result.items:
                    eligible_items = [
                        item for item in load_result.items if self._is_news_item_available_by_cutoff(item, as_of_date)
                    ]
                    merged = self._merge_refined_news_items(
                        primary_items=eligible_items,
                        secondary_items=[],
                        total_limit=36,
                    )
                    if merged:
                        return merged
            except Exception:
                pass

        if not self.refined_news_scraping_enabled:
            return []

        primary_items: list[dict[str, Any]] = []
        secondary_items: list[dict[str, Any]] = []
        try:
            primary_items = self.refined_oil_news_client.fetch_recent(total_limit=24, per_section_limit=6)
        except Exception:
            primary_items = []
        try:
            secondary_items.extend(self.cnenergy_refined_oil_client.fetch_recent(limit=8, list_limit=200))
        except Exception:
            pass
        try:
            secondary_items.extend(self.jlc_refined_oil_client.fetch_live_hot(limit=10))
        except Exception:
            pass
        primary_items = [item for item in primary_items if self._is_news_item_available_by_cutoff(item, as_of_date)]
        secondary_items = [item for item in secondary_items if self._is_news_item_available_by_cutoff(item, as_of_date)]
        return self._merge_refined_news_items(
            primary_items=primary_items,
            secondary_items=secondary_items,
            total_limit=36,
        )

    def _load_policy_items_fast(self, as_of_date: date, *, prefer_archive: bool = True) -> list[dict[str, Any]]:
        if prefer_archive and self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_policy_items(
                    start_date=as_of_date - timedelta(days=45),
                    end_date=as_of_date,
                )
                if load_result.items:
                    return self._dedupe_policy_items(load_result.items)[:12]
            except Exception:
                pass
        if not self.policy_scraping_enabled:
            return []
        try:
            return self._dedupe_policy_items(self.policy_client.fetch_recent_adjustments(limit=12))[:12]
        except Exception:
            return []

    def build_archived_event_risk_snapshot(
        self,
        start_date: date,
        end_date: date,
        news_lookback_days: int = 2,
        report_lookback_days: int = 7,
        per_day_limit: int = 20,
    ) -> ArchivedEventRiskSnapshot:
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return self._empty_event_risk_snapshot(start_date=start_date, end_date=end_date)

        news_fetch_start = start_date - timedelta(days=news_lookback_days)
        report_fetch_start = start_date - timedelta(days=report_lookback_days)
        try:
            news_load_result = self.snapshot_repository.load_jinshi_news_items(
                start_date=news_fetch_start,
                end_date=end_date,
            )
        except Exception:
            news_load_result = None
        try:
            report_load_result = self.snapshot_repository.load_brent_reports(
                start_date=report_fetch_start,
                end_date=end_date,
            )
        except Exception:
            report_load_result = None

        return self._build_archived_event_risk_snapshot_from_items(
            start_date=start_date,
            end_date=end_date,
            news_items=(news_load_result.items if news_load_result else []),
            report_items=(report_load_result.items if report_load_result else []),
            news_lookback_days=news_lookback_days,
            report_lookback_days=report_lookback_days,
            per_day_limit=per_day_limit,
            news_source_counts=(news_load_result.source_counts if news_load_result else None),
            report_source_counts=(report_load_result.source_counts if report_load_result else None),
            news_archive_start=(news_load_result.archive_start if news_load_result else None),
            news_archive_end=(news_load_result.archive_end if news_load_result else None),
            report_archive_start=(report_load_result.archive_start if report_load_result else None),
            report_archive_end=(report_load_result.archive_end if report_load_result else None),
        )

    def get_market_snapshot(self, as_of_date: date) -> dict[str, Any]:
        latest_prices, mode, reason = self._load_latest_price_snapshot(as_of_date=as_of_date)
        generated_at = datetime.now()
        oilchem_metrics = self._load_oilchem_operating_metrics(as_of_date=as_of_date)
        return {
            "as_of_date": as_of_date,
            "generated_at": generated_at,
            "latest_prices": latest_prices,
            "metadata": {
                "market_data_mode": mode,
                "market_data_reason": reason,
                "oilchem_metrics": oilchem_metrics,
                "quality": self._build_price_quality(
                    latest_prices=latest_prices,
                    mode=mode,
                    reason=reason,
                    generated_at=generated_at,
                    as_of_date=as_of_date,
                ),
            },
        }

    def refresh_oilchem_openapi_inventory_archive(
        self,
        *,
        as_of_date: date,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        if not self.oilchem_openapi_client or not self.oilchem_openapi_client.enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "oilchem_openapi_disabled",
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "database_disabled",
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        target_end = end_date or as_of_date
        target_start = start_date or (target_end - timedelta(days=180))
        try:
            records = self.oilchem_openapi_client.fetch_inventory_records(
                start_date=target_start,
                end_date=target_end,
            )
        except Exception as exc:
            return {
                "as_of_date": as_of_date,
                "status": "failed",
                "reason": str(exc),
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        payloads = [record.model_dump() for record in records]
        try:
            saved_count = self.snapshot_repository.save_oilchem_openapi_inventory_records(payloads)
        except Exception as exc:
            return {
                "as_of_date": as_of_date,
                "status": "db_failed",
                "reason": str(exc),
                "fetched_count": len(payloads),
                "saved_timeseries_count": 0,
            }
        dates = [record.observation_date for record in records]
        return {
            "as_of_date": as_of_date,
            "status": "ok",
            "start_date": target_start,
            "end_date": target_end,
            "fetched_count": len(payloads),
            "saved_timeseries_count": saved_count,
            "latest_observation_date": max(dates).isoformat() if dates else None,
        }

    def get_oilchem_openapi_inventory(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        generated_at = datetime.now()
        rows: list[dict[str, Any]] = []
        if self.snapshot_repository and self.snapshot_repository.enabled:
            rows = self.snapshot_repository.load_oilchem_openapi_inventory_records(
                start_date=start_date,
                end_date=end_date,
            )
        normalized_rows = [self._normalize_oilchem_inventory_row(row) for row in rows]
        latest_date = max((row["date"] for row in normalized_rows if row.get("date")), default=None)
        latest_items = [row for row in normalized_rows if row.get("date") == latest_date] if latest_date else []
        return {
            "start_date": start_date,
            "end_date": end_date,
            "generated_at": generated_at,
            "latest_date": latest_date,
            "summary_cards": self._build_oilchem_inventory_summary_cards(latest_items),
            "latest_items": latest_items,
            "items": normalized_rows,
            "metadata": {
                "source": "oilchem_openapi_inventory",
                "item_count": len(normalized_rows),
                "latest_item_count": len(latest_items),
            },
        }

    def _load_oilchem_operating_metrics(self, as_of_date: date) -> dict[str, Any]:
        payload: dict[str, Any] = self._load_archived_oilchem_operating_metrics(as_of_date=as_of_date)
        payload["collection_status"] = (
            "archive_only_scheduled_scraping_enabled"
            if self.oilchem_scraping_enabled
            else "web_scraping_disabled"
        )
        return payload

    def _load_archived_oilchem_operating_metrics(self, as_of_date: date) -> dict[str, Any]:
        empty_payload: dict[str, Any] = {
            "production_sales_ratio": None,
            "capacity_utilization": None,
            "refining_profit": None,
            "maintenance_plan": None,
            "main_maintenance_plan": None,
            "inventory": None,
            "purchased_inventory": None,
        }
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return empty_payload
        try:
            archived = self.snapshot_repository.load_latest_raw_market_payloads(
                source_codes=[
                    "oilchem_production_sales_ratio",
                    "oilchem_weekly_refinery_metrics",
                    "oilchem_refinery_maintenance_plan",
                    "oilchem_main_refinery_maintenance_plan",
                    "oilchem_refinery_inventory",
                ],
                end_date=as_of_date,
                limit_per_source=8,
                lookback_days=120,
            )
        except Exception:
            return empty_payload

        ratio_items = archived.get("oilchem_production_sales_ratio") or []
        weekly_items = archived.get("oilchem_weekly_refinery_metrics") or []
        maintenance_items = archived.get("oilchem_refinery_maintenance_plan") or []
        main_maintenance_items = archived.get("oilchem_main_refinery_maintenance_plan") or []
        inventory_items = archived.get("oilchem_refinery_inventory") or []

        payload = dict(empty_payload)
        if ratio_items:
            payload["production_sales_ratio"] = ratio_items[0]
        capacity_items = [item for item in weekly_items if item.get("metric_type") == "capacity_utilization"]
        profit_items = [item for item in weekly_items if item.get("metric_type") == "refining_profit"]
        if capacity_items:
            payload["capacity_utilization"] = capacity_items[0]
        if profit_items:
            payload["refining_profit"] = profit_items[0]
        if maintenance_items:
            payload["maintenance_plan"] = maintenance_items[0]
        if main_maintenance_items:
            payload["main_maintenance_plan"] = main_maintenance_items[0]
        if inventory_items:
            inventory_payload = dict(inventory_items[0])
            for field_name in (
                "gasoline_inventory_capacity_rate",
                "diesel_inventory_capacity_rate",
            ):
                if inventory_payload.get(field_name) is not None:
                    continue
                fallback_item = next(
                    (
                        item
                        for item in inventory_items
                        if item.get(field_name) is not None
                    ),
                    None,
                )
                if fallback_item:
                    inventory_payload[field_name] = fallback_item.get(field_name)
                    inventory_payload[f"{field_name}_date"] = fallback_item.get("observation_date")
            payload["inventory"] = inventory_payload
        try:
            inventory_payload = self.get_oilchem_openapi_inventory(
                start_date=as_of_date - timedelta(days=180),
                end_date=as_of_date,
            )
            if inventory_payload.get("summary_cards"):
                payload["purchased_inventory"] = {
                    "latest_date": inventory_payload.get("latest_date"),
                    "summary_cards": inventory_payload.get("summary_cards"),
                    "latest_item_count": inventory_payload.get("metadata", {}).get("latest_item_count"),
                    "item_count": inventory_payload.get("metadata", {}).get("item_count"),
                    "source": "oilchem_openapi_inventory",
                }
        except Exception:
            pass
        return payload

    def _normalize_oilchem_inventory_row(self, row: dict[str, Any]) -> dict[str, Any]:
        project_quota_id = row.get("project_quota_id")
        source_indicator_name = str(row.get("indicator_name") or "")
        project_label = self._oilchem_inventory_display_label(project_quota_id)
        product = "汽油" if "汽油" in project_label else "柴油" if "柴油" in project_label else ""
        owner = self._oilchem_inventory_owner_label(project_quota_id)
        dt_value = row.get("dt")
        date_text = dt_value.isoformat() if isinstance(dt_value, date) else str(dt_value or "")[:10]
        publish_time = row.get("publish_time")
        publish_text = publish_time.isoformat() if isinstance(publish_time, datetime) else str(publish_time or "")
        return {
            "date": date_text,
            "publish_time": publish_text,
            "project_quota_id": project_quota_id,
            "indicator_code": row.get("indicator_code"),
            "indicator_name": source_indicator_name,
            "source_indicator_name": source_indicator_name,
            "project_label": project_label,
            "product": product,
            "owner": owner,
            "region": row.get("entity_name"),
            "entity_code": row.get("entity_code"),
            "value": row.get("value"),
            "unit": row.get("unit") or "万吨",
            "freq": row.get("freq") or "weekly",
        }

    def _oilchem_inventory_display_label(self, project_quota_id: Any) -> str:
        mapping = {
            12975: "汽油周度贸易商库存量（区域）",
            12981: "柴油周度贸易商库存量（区域）",
            12944: "部分社会油库汽油周度贸易商库存量（区域）",
            12945: "部分社会油库柴油周度贸易商库存量（区域）",
            12887: "汽油主营库存量（山东）",
            12891: "柴油主营库存量（山东）",
        }
        try:
            return mapping.get(int(project_quota_id), f"库存指标 {project_quota_id}")
        except Exception:
            return f"库存指标 {project_quota_id}"

    def _oilchem_inventory_owner_label(self, project_quota_id: Any) -> str:
        mapping = {
            12975: "贸易商",
            12981: "贸易商",
            12944: "部分社会油库",
            12945: "部分社会油库",
            12887: "主营销售公司",
            12891: "主营销售公司",
        }
        try:
            return mapping.get(int(project_quota_id), "")
        except Exception:
            return ""

    def _build_oilchem_inventory_summary_cards(self, latest_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not latest_items:
            return []

        def sum_projects(project_quota_ids: set[int]) -> float | None:
            values = [
                float(item["value"])
                for item in latest_items
                if item.get("project_quota_id") in project_quota_ids and item.get("value") is not None
            ]
            return round(sum(values), 4) if values else None

        def preferred_sum(primary_id: int, fallback_id: int) -> float | None:
            primary_value = sum_projects({primary_id})
            if primary_value is not None:
                return primary_value
            return sum_projects({fallback_id})

        def shandong_value(project_quota_id: int) -> float | None:
            for item in latest_items:
                if item.get("project_quota_id") == project_quota_id and "山东" in str(item.get("region") or ""):
                    return item.get("value")
            return None

        cards = [
            {
                "label": "汽油周度贸易商库存量（区域）",
                "value": preferred_sum(12975, 12944),
                "unit": "万吨",
                "sub": "七大区域合计",
            },
            {
                "label": "柴油周度贸易商库存量（区域）",
                "value": preferred_sum(12981, 12945),
                "unit": "万吨",
                "sub": "七大区域合计",
            },
            {
                "label": "汽油主营库存量（山东）",
                "value": shandong_value(12887),
                "unit": "万吨",
                "sub": "山东样本",
            },
            {
                "label": "柴油主营库存量（山东）",
                "value": shandong_value(12891),
                "unit": "万吨",
                "sub": "山东样本",
            },
        ]
        return [card for card in cards if card["value"] is not None]

    def get_brent_realtime_snapshot(self, as_of_date: date) -> dict[str, Any]:
        mode = "wind_price_api"
        reason = None
        value = None
        update_time = datetime.now()
        wind_payload = self._fetch_wind_brent_price()
        if wind_payload:
            value = wind_payload["rt_latest"]
            update_time = wind_payload.get("time") or update_time
        elif self._eta_is_available():
            mode = "eta"
            reason = "wind_unavailable"
            value = self._fetch_eta_latest_value("brent_active_settlement", as_of_date)
        if value is None:
            mode = "fallback_local_snapshot"
            reason = "wind_eta_unavailable"
            value = self._fallback_latest_prices(as_of_date=as_of_date).get("brent_active_settlement")
        return {
            "as_of_date": as_of_date,
            "generated_at": update_time,
            "latest_price": self._round_or_none(value),
            "metadata": {
                "market_data_mode": mode,
                "market_data_reason": reason,
                "indicator_key": "brent_active_settlement",
                "source": "Wind实时价格接口" if mode == "wind_price_api" else None,
                "wind": wind_payload,
                "quality": self._build_price_quality(
                    latest_prices={"brent_active_settlement": value},
                    mode=mode,
                    reason=reason,
                    generated_at=update_time,
                    as_of_date=as_of_date,
                ),
            },
        }

    def refresh_market_snapshot_archive(self, as_of_date: date) -> dict[str, Any]:
        latest_prices, mode, reason = self._load_latest_price_snapshot(as_of_date=as_of_date)
        saved_rows = self._persist_latest_price_snapshot(
            snapshot_date=as_of_date,
            latest_prices=latest_prices,
            mode=mode,
            reason=reason,
        )
        return {
            "saved_rows": saved_rows,
            "market_data_mode": mode,
            "market_data_reason": reason,
            "latest_prices": latest_prices,
            "quality": self._build_price_quality(
                latest_prices=latest_prices,
                mode=mode,
                reason=reason,
                generated_at=datetime.now(),
                as_of_date=as_of_date,
            ),
        }

    def refresh_brent_report_archive(self, as_of_date: date) -> dict[str, Any]:
        report_payload = None
        try:
            report_payload = self.brent_report_client.fetch_latest()
        except Exception as exc:
            return {
                "report_saved": False,
                "saved_report_count": 0,
                "error": str(exc),
            }
        saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                saved_count = self.snapshot_repository.save_brent_report(
                    snapshot_date=as_of_date,
                    report_payload=report_payload,
                )
            except Exception as exc:
                return {
                    "report_saved": False,
                    "saved_report_count": 0,
                    "report_date": report_payload.get("report_date"),
                    "error": str(exc),
                }
        return {
            "report_saved": bool(report_payload),
            "saved_report_count": saved_count,
            "report_date": report_payload.get("report_date") if report_payload else None,
            "title": report_payload.get("title") if report_payload else None,
        }

    def refresh_policy_event_archive(self, as_of_date: date) -> dict[str, Any]:
        report_payload = self._load_report_payload(as_of_date=as_of_date)
        news_items = self._load_event_news_items(as_of_date=as_of_date, prefer_archive=False)
        refined_news_items = self._load_refined_news_items(as_of_date=as_of_date, prefer_archive=False)
        policy_items = self._load_policy_items_fast(as_of_date=as_of_date, prefer_archive=False)
        saved_counts = self._persist_current_snapshots(
            snapshot_date=as_of_date,
            report_payload=report_payload,
            news_items=news_items,
            refined_news_items=refined_news_items,
            policy_items=policy_items,
        )
        return {
            "report_saved": bool(report_payload),
            "event_news_count": len(news_items),
            "refined_news_count": len(refined_news_items),
            "policy_count": len(policy_items),
            "saved_event_news_count": saved_counts.get("event_news", 0),
            "saved_refined_news_count": saved_counts.get("refined_news", 0),
            "saved_policy_count": saved_counts.get("policy", 0),
        }

    def refresh_oilchem_daily_archive(self, as_of_date: date) -> dict[str, Any]:
        if not self.oilchem_scraping_enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "web_scraping_disabled",
                "fetched_count": 0,
                "weekly_fetched_count": 0,
                "maintenance_fetched_count": 0,
                "inventory_fetched_count": 0,
                "saved_timeseries_count": 0,
                "weekly_saved_timeseries_count": 0,
                "maintenance_saved_timeseries_count": 0,
                "inventory_saved_timeseries_count": 0,
            }
        errors: dict[str, str] = {}
        try:
            records = self.oilchem_production_sales_client.fetch_recent(limit=1)
        except Exception as exc:
            errors["production_sales_ratio"] = str(exc)
            records = []
        try:
            weekly_records = self.oilchem_production_sales_client.fetch_weekly_metrics(limit=5)
        except Exception as exc:
            errors["weekly_metrics"] = str(exc)
            weekly_records = []
        try:
            maintenance_records = self.oilchem_production_sales_client.fetch_maintenance_plans(limit=5)
        except Exception as exc:
            errors["maintenance_plan"] = str(exc)
            maintenance_records = []
        try:
            inventory_records = self.oilchem_production_sales_client.fetch_inventory_records(limit=5)
        except Exception as exc:
            errors["inventory"] = str(exc)
            inventory_records = []
        record_payloads = [record.model_dump() for record in records]
        weekly_payloads = [record.model_dump() for record in weekly_records]
        maintenance_payloads = [record.model_dump() for record in maintenance_records]
        inventory_payloads = [record.model_dump() for record in inventory_records]
        saved_count = 0
        weekly_saved_count = 0
        maintenance_saved_count = 0
        inventory_saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                if record_payloads:
                    saved_count = self.snapshot_repository.save_oilchem_production_sales_records(record_payloads)
                if weekly_payloads:
                    weekly_saved_count = self.snapshot_repository.save_oilchem_weekly_metric_records(weekly_payloads)
                if maintenance_payloads:
                    maintenance_saved_count = self.snapshot_repository.save_oilchem_maintenance_plan_records(maintenance_payloads)
                if inventory_payloads:
                    inventory_saved_count = self.snapshot_repository.save_oilchem_inventory_records(inventory_payloads)
            except Exception as exc:
                return {
                    "as_of_date": as_of_date,
                    "status": "db_failed",
                    "reason": str(exc),
                    "fetched_count": len(record_payloads),
                    "weekly_fetched_count": len(weekly_payloads),
                    "maintenance_fetched_count": len(maintenance_payloads),
                    "inventory_fetched_count": len(inventory_payloads),
                    "saved_timeseries_count": 0,
                    "weekly_saved_timeseries_count": 0,
                    "maintenance_saved_timeseries_count": 0,
                    "inventory_saved_timeseries_count": 0,
                }
        latest = record_payloads[0] if record_payloads else None
        latest_weekly = weekly_payloads[0] if weekly_payloads else None
        latest_maintenance = maintenance_payloads[0] if maintenance_payloads else None
        latest_inventory = inventory_payloads[0] if inventory_payloads else None
        return {
            "as_of_date": as_of_date,
            "status": "ok" if not errors else "partial" if any(
                [record_payloads, weekly_payloads, maintenance_payloads, inventory_payloads]
            ) else "failed",
            "errors": errors,
            "fetched_count": len(record_payloads),
            "weekly_fetched_count": len(weekly_payloads),
            "maintenance_fetched_count": len(maintenance_payloads),
            "inventory_fetched_count": len(inventory_payloads),
            "saved_timeseries_count": saved_count,
            "weekly_saved_timeseries_count": weekly_saved_count,
            "maintenance_saved_timeseries_count": maintenance_saved_count,
            "inventory_saved_timeseries_count": inventory_saved_count,
            "latest_observation_date": latest.get("observation_date") if latest else None,
            "latest_gasoline_ratio": latest.get("gasoline_ratio") if latest else None,
            "latest_diesel_ratio": latest.get("diesel_ratio") if latest else None,
            "latest_weekly_observation_date": latest_weekly.get("observation_date") if latest_weekly else None,
            "latest_weekly_metric_type": latest_weekly.get("metric_type") if latest_weekly else None,
            "latest_maintenance_observation_date": latest_maintenance.get("observation_date") if latest_maintenance else None,
            "latest_maintenance_active_capacity": latest_maintenance.get("active_capacity") if latest_maintenance else None,
            "latest_inventory_observation_date": latest_inventory.get("observation_date") if latest_inventory else None,
            "latest_gasoline_inventory": latest_inventory.get("gasoline_inventory") if latest_inventory else None,
            "latest_gasoline_inventory_change_mom": (
                latest_inventory.get("gasoline_inventory_change_mom") if latest_inventory else None
            ),
            "latest_gasoline_inventory_capacity_rate": (
                latest_inventory.get("gasoline_inventory_capacity_rate") if latest_inventory else None
            ),
        }

    def refresh_oilchem_price_archive(self, as_of_date: date) -> dict[str, Any]:
        if not self.oilchem_scraping_enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "web_scraping_disabled",
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        try:
            records = self.oilchem_price_client.fetch_latest_prices(products=["gasoline92", "diesel0"])
        except Exception as exc:
            return {
                "as_of_date": as_of_date,
                "status": "failed",
                "reason": str(exc),
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        payloads = [record.model_dump() for record in records]
        saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled and payloads:
            try:
                saved_count = self.snapshot_repository.save_oilchem_price_records(payloads)
            except Exception as exc:
                return {
                    "as_of_date": as_of_date,
                    "status": "db_failed",
                    "reason": str(exc),
                    "fetched_count": len(payloads),
                    "saved_timeseries_count": 0,
                }
        self._context_cache.clear()
        self._feature_frame_cache.clear()
        return {
            "as_of_date": as_of_date,
            "status": "ok" if payloads else "empty",
            "fetched_count": len(payloads),
            "saved_timeseries_count": saved_count,
            "latest_observation_date": max((item["observation_date"] for item in payloads), default=None),
            "gasoline_count": sum(1 for item in payloads if item.get("product_code") == "gasoline92"),
            "diesel_count": sum(1 for item in payloads if item.get("product_code") == "diesel0"),
        }

    def refresh_oilchem_production_sales_archive(self, as_of_date: date) -> dict[str, Any]:
        if not self.oilchem_scraping_enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "web_scraping_disabled",
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        try:
            records = self.oilchem_production_sales_client.fetch_recent(limit=10)
        except Exception as exc:
            return {
                "as_of_date": as_of_date,
                "status": "failed",
                "reason": str(exc),
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        payloads = [record.model_dump() for record in records]
        saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled and payloads:
            try:
                saved_count = self.snapshot_repository.save_oilchem_production_sales_records(payloads)
            except Exception as exc:
                return {
                    "as_of_date": as_of_date,
                    "status": "db_failed",
                    "reason": str(exc),
                    "fetched_count": len(payloads),
                    "saved_timeseries_count": 0,
                }
        self._context_cache.clear()
        self._feature_frame_cache.clear()
        latest = payloads[0] if payloads else None
        return {
            "as_of_date": as_of_date,
            "status": "ok" if payloads else "empty",
            "fetched_count": len(payloads),
            "saved_timeseries_count": saved_count,
            "latest_observation_date": latest.get("observation_date") if latest else None,
            "latest_gasoline_ratio": latest.get("gasoline_ratio") if latest else None,
            "latest_diesel_ratio": latest.get("diesel_ratio") if latest else None,
        }

    def refresh_oilchem_maintenance_archive(self, as_of_date: date, *, refinery_scope: str) -> dict[str, Any]:
        if not self.oilchem_scraping_enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "web_scraping_disabled",
                "scope": refinery_scope,
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        try:
            records = self.oilchem_production_sales_client.fetch_maintenance_plans(
                limit=1,
                refinery_scope=refinery_scope,
            )
        except Exception as exc:
            return {
                "as_of_date": as_of_date,
                "status": "failed",
                "reason": str(exc),
                "scope": refinery_scope,
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        payloads = [record.model_dump() for record in records]
        saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled and payloads:
            try:
                if refinery_scope == "main":
                    saved_count = self.snapshot_repository.save_oilchem_maintenance_plan_records(
                        payloads,
                        source_code="oilchem_main_refinery_maintenance_plan",
                        entity_code="MAIN_REFINERY",
                        entity_name="国内主营炼厂",
                        indicator_prefix="oilchem_main_maintenance",
                    )
                else:
                    saved_count = self.snapshot_repository.save_oilchem_maintenance_plan_records(payloads)
            except Exception as exc:
                return {
                    "as_of_date": as_of_date,
                    "status": "db_failed",
                    "reason": str(exc),
                    "scope": refinery_scope,
                    "fetched_count": len(payloads),
                    "saved_timeseries_count": 0,
                }
        self._context_cache.clear()
        self._feature_frame_cache.clear()
        latest = payloads[0] if payloads else None
        return {
            "as_of_date": as_of_date,
            "status": "ok" if payloads else "empty",
            "scope": refinery_scope,
            "fetched_count": len(payloads),
            "saved_timeseries_count": saved_count,
            "latest_observation_date": latest.get("observation_date") if latest else None,
            "latest_active_capacity": latest.get("active_capacity") if latest else None,
            "latest_active_count": latest.get("active_count") if latest else None,
        }

    def refresh_oilchem_spot_report_archive(self, as_of_date: date) -> dict[str, Any]:
        if not self.oilchem_spot_report_scraping_enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "oilchem_spot_report_scraping_disabled",
                "fetched_count": 0,
                "saved_refined_news_count": 0,
            }
        try:
            records = self.oilchem_production_sales_client.fetch_spot_daily_reports(limit=1)
        except Exception as exc:
            return {
                "as_of_date": as_of_date,
                "status": "failed",
                "reason": str(exc),
                "fetched_count": 0,
                "saved_refined_news_count": 0,
            }

        payloads = [record.model_dump() for record in records]
        saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled and payloads:
            try:
                saved_count = self.snapshot_repository.save_refined_news_items(
                    snapshot_date=as_of_date,
                    items=payloads,
                )
            except Exception as exc:
                return {
                    "as_of_date": as_of_date,
                    "status": "db_failed",
                    "reason": str(exc),
                    "fetched_count": len(payloads),
                    "saved_refined_news_count": 0,
                }
        latest = payloads[0] if payloads else None
        return {
            "as_of_date": as_of_date,
            "status": "ok" if payloads else "empty",
            "fetched_count": len(payloads),
            "saved_refined_news_count": saved_count,
            "latest_observation_date": latest.get("observation_date") if latest else None,
            "latest_publish_time": latest.get("publish_time") if latest else None,
            "latest_title": latest.get("title") if latest else None,
        }

    def build_policy_event_feed(
        self,
        *,
        news_date: date | None = None,
        policy_date: date | None = None,
        sort_mode: str = "importance",
    ) -> dict[str, Any]:
        today = date.today()
        news_items = self._load_refined_news_archive_for_feed(end_date=today)
        event_items = self._load_event_news_archive_for_feed(end_date=today)
        policy_items = self._load_policy_archive_for_feed(end_date=today)

        available_refined_news_dates = sorted({item["_item_date"] for item in news_items}, reverse=True)
        available_event_news_dates = sorted({item["_item_date"] for item in event_items}, reverse=True)
        available_news_dates = sorted({*available_refined_news_dates, *available_event_news_dates}, reverse=True)
        available_policy_dates = sorted({item["_item_date"] for item in policy_items}, reverse=True)

        selected_refined_news_date = news_date or (
            available_refined_news_dates[0] if available_refined_news_dates else today
        )
        selected_event_news_date = news_date or (available_event_news_dates[0] if available_event_news_dates else today)
        selected_policy_date = policy_date or (available_policy_dates[0] if available_policy_dates else today)

        filtered_news_items = [item for item in news_items if item["_item_date"] == selected_refined_news_date]
        filtered_event_items = [item for item in event_items if item["_item_date"] == selected_event_news_date]
        filtered_policy_items = [item for item in policy_items if item["_item_date"] == selected_policy_date]

        self._sort_feed_items(filtered_news_items, sort_mode=sort_mode)
        self._sort_feed_items(filtered_event_items, sort_mode=sort_mode)
        self._sort_feed_items(filtered_policy_items, sort_mode=sort_mode)

        alerts = self._build_alert_items(
            refined_news_items=filtered_news_items,
            event_news_items=filtered_event_items,
            policy_items=filtered_policy_items,
        )
        return {
            "news_date": news_date or selected_refined_news_date,
            "refined_news_date": selected_refined_news_date,
            "event_news_date": selected_event_news_date,
            "policy_date": selected_policy_date,
            "sort_mode": sort_mode,
            "available_news_dates": available_news_dates[:14],
            "available_refined_news_dates": available_refined_news_dates[:14],
            "available_event_news_dates": available_event_news_dates[:14],
            "available_policy_dates": available_policy_dates[:20],
            "refined_news_items": [self._strip_feed_meta(item) for item in filtered_news_items[:20]],
            "event_news_items": [self._strip_feed_meta(item) for item in filtered_event_items[:20]],
            "policy_items": [self._strip_feed_meta(item) for item in filtered_policy_items[:20]],
            "alerts": alerts[:6],
        }

    def _load_latest_price_snapshot(self, as_of_date: date) -> tuple[dict[str, float | None], str, str | None]:
        fallback_prices = self._fallback_latest_prices(as_of_date=as_of_date)
        wind_payload = self._fetch_wind_brent_price()
        if not self._eta_is_available():
            if wind_payload:
                fallback_prices["brent_active_settlement"] = self._round_or_none(wind_payload["rt_latest"])
                mode = "wind_with_local_snapshot"
            else:
                mode = "fallback_local_snapshot"
            cash_reason = self._overlay_preferred_cash_price_snapshot(
                latest_prices=fallback_prices,
                as_of_date=as_of_date,
            )
            reason = "eta_unavailable"
            if cash_reason:
                mode = f"{mode}_cash_overlay"
                reason = f"{reason};{cash_reason}"
            return fallback_prices, mode, reason

        latest_prices = dict(fallback_prices)
        if wind_payload:
            latest_prices["brent_active_settlement"] = self._round_or_none(wind_payload["rt_latest"])
        missing_keys: list[str] = []
        with ThreadPoolExecutor(max_workers=min(6, len(SNAPSHOT_INDICATOR_KEYS))) as executor:
            future_map = {
                executor.submit(self._fetch_eta_latest_value, key, as_of_date): key
                for key in SNAPSHOT_INDICATOR_KEYS
                if not (key == "brent_active_settlement" and wind_payload)
            }
            for future in as_completed(future_map):
                key = future_map[future]
                try:
                    value = future.result()
                except Exception:
                    value = None
                if value is None:
                    missing_keys.append(key)
                    continue
                latest_prices[key] = self._round_or_none(value)

        cash_reason = self._overlay_preferred_cash_price_snapshot(
            latest_prices=latest_prices,
            as_of_date=as_of_date,
        )
        if not wind_payload and len(missing_keys) == len(SNAPSHOT_INDICATOR_KEYS):
            mode = "fallback_local_snapshot"
            reason = "eta_snapshot_empty"
            if cash_reason:
                mode = f"{mode}_cash_overlay"
                reason = f"{reason};{cash_reason}"
            return latest_prices, mode, reason
        if missing_keys:
            mode = "wind_eta_with_fallback_fill" if wind_payload else "eta_with_fallback_fill"
            reason = f"missing:{','.join(sorted(missing_keys))}"
            if cash_reason:
                mode = f"{mode}_cash_overlay"
                reason = f"{reason};{cash_reason}"
            return latest_prices, mode, reason
        mode = "wind_eta" if wind_payload else "eta"
        if cash_reason:
            return latest_prices, f"{mode}_cash_overlay", cash_reason
        return latest_prices, mode, None

    def _fetch_wind_brent_price(self) -> dict[str, Any] | None:
        try:
            return self.wind_price_client.get_price()
        except Exception:
            return None

    def _fetch_eta_latest_value(self, key: str, as_of_date: date) -> float | None:
        try:
            indicator = self.catalog.get(key)
            return self.eta_client.get_latest_value(
                indicator,
                as_of_date=as_of_date,
                timeout_seconds=self.ETA_FAST_TIMEOUT,
            )
        except Exception:
            return None

    def _build_price_quality(
        self,
        *,
        latest_prices: dict[str, float | None],
        mode: str,
        reason: str | None,
        generated_at: datetime,
        as_of_date: date,
    ) -> dict[str, dict[str, Any]]:
        missing_keys: set[str] = set()
        if reason and reason.startswith("missing:"):
            missing_keys = {item.strip() for item in reason.replace("missing:", "", 1).split(",") if item.strip()}
        quality: dict[str, dict[str, Any]] = {}
        source_name = "ETA指标库" if "eta" in mode else "本地降级快照"
        for key, value in latest_prices.items():
            is_missing = value is None
            if key == "brent_active_settlement" and mode.startswith("wind"):
                is_fallback = is_missing
                source = "本地补值" if is_missing else "Wind实时价格接口"
            elif mode in {"fallback_local_snapshot", "wind_with_local_snapshot"}:
                is_fallback = True
                source = "本地补值"
            else:
                is_fallback = key in missing_keys or is_missing
                source = "本地补值" if is_fallback else source_name
            quality[key] = {
                "indicator_key": key,
                "source": source,
                "source_update_time": as_of_date.isoformat(),
                "collect_time": generated_at.isoformat(),
                "staleness_hours": max((generated_at.date() - as_of_date).days * 24, 0),
                "quality_flag": "missing" if is_missing else "fallback" if is_fallback else "ok",
                "is_fallback": is_fallback,
                "missing_reason": reason if is_fallback else None,
                "confidence": "低" if is_missing else "中" if is_fallback else "高",
            }
        return quality

    def _fallback_latest_prices(self, as_of_date: date) -> dict[str, float | None]:
        start_date = as_of_date - timedelta(days=20)
        frame = self.fallback_builder.build_feature_frame(start_date=start_date, end_date=as_of_date)
        current_frame = frame[frame["date"] <= as_of_date]
        if current_frame.empty:
            return {key: None for key in SNAPSHOT_INDICATOR_KEYS}
        current_row = current_frame.iloc[-1]
        return {key: self._round_or_none(current_row.get(key)) for key in SNAPSHOT_INDICATOR_KEYS}

    def _build_archived_snapshot_from_items(
        self,
        archive_items: list[dict[str, Any]],
        start_date: date,
        end_date: date,
        lookback_days: int,
        per_day_limit: int,
        source_counts: dict[str, int] | None = None,
        archive_start: date | None = None,
        archive_end: date | None = None,
    ) -> ArchivedRefinedNewsSnapshot:
        archive_fetch_start = start_date - timedelta(days=lookback_days)
        normalized_items: list[dict[str, Any]] = []
        effective_source_counts: dict[str, int] = dict(source_counts or {})
        for item in archive_items:
            publish_date = self._extract_item_date(item)
            if publish_date is None:
                continue
            if publish_date < archive_fetch_start or publish_date > end_date:
                continue
            normalized = dict(item)
            normalized["_publish_date"] = publish_date
            normalized_items.append(normalized)
            if not source_counts:
                source = str(item.get("source") or "unknown")
                effective_source_counts[source] = effective_source_counts.get(source, 0) + 1

        deduped_items = self._dedupe_news_items(normalized_items)
        deduped_items.sort(
            key=lambda item: (
                item["_publish_date"],
                float(item.get("priority_score") or 0.0),
                str(item.get("publish_time") or item.get("publish_date") or ""),
            ),
            reverse=True,
        )

        items_by_date: dict[date, list[dict[str, Any]]] = {}
        current_date = start_date
        while current_date <= end_date:
            window_start = current_date - timedelta(days=lookback_days)
            day_items = [
                self._drop_internal_fields(item)
                for item in deduped_items
                if window_start <= item["_publish_date"] <= current_date
                and self._is_news_item_available_by_cutoff(item, current_date)
            ]
            items_by_date[current_date] = day_items[:per_day_limit]
            current_date += timedelta(days=1)

        archive_dates = [item["_publish_date"] for item in deduped_items]
        return ArchivedRefinedNewsSnapshot(
            items_by_date=items_by_date,
            source_counts=effective_source_counts,
            archive_start=archive_start or (min(archive_dates) if archive_dates else None),
            archive_end=archive_end or (max(archive_dates) if archive_dates else None),
        )

    def _build_archived_policy_snapshot_from_items(
        self,
        archive_items: list[dict[str, Any]],
        start_date: date,
        end_date: date,
        lookback_days: int,
        per_day_limit: int,
        source_counts: dict[str, int] | None = None,
        archive_start: date | None = None,
        archive_end: date | None = None,
    ) -> ArchivedPolicySnapshot:
        archive_fetch_start = start_date - timedelta(days=lookback_days)
        normalized_items: list[dict[str, Any]] = []
        effective_source_counts: dict[str, int] = dict(source_counts or {})
        for item in archive_items:
            event_date = self._extract_policy_item_date(item)
            if event_date is None:
                continue
            if event_date < archive_fetch_start or event_date > end_date:
                continue
            normalized = dict(item)
            normalized["_event_date"] = event_date
            normalized_items.append(normalized)
            if not source_counts:
                source = str(item.get("source") or "unknown")
                effective_source_counts[source] = effective_source_counts.get(source, 0) + 1

        deduped_items = self._dedupe_policy_items(normalized_items)
        deduped_items.sort(
            key=lambda item: (
                item["_event_date"],
                str(item.get("effective_time") or item.get("publish_date") or ""),
            ),
            reverse=True,
        )

        items_by_date: dict[date, list[dict[str, Any]]] = {}
        current_date = start_date
        while current_date <= end_date:
            window_start = current_date - timedelta(days=lookback_days)
            day_items = [
                self._drop_internal_policy_fields(item)
                for item in deduped_items
                if window_start <= item["_event_date"] <= current_date
            ]
            items_by_date[current_date] = day_items[:per_day_limit]
            current_date += timedelta(days=1)

        archive_dates = [item["_event_date"] for item in deduped_items]
        return ArchivedPolicySnapshot(
            items_by_date=items_by_date,
            source_counts=effective_source_counts,
            archive_start=archive_start or (min(archive_dates) if archive_dates else None),
            archive_end=archive_end or (max(archive_dates) if archive_dates else None),
        )

    def _persist_current_snapshots(
        self,
        snapshot_date: date,
        report_payload: dict[str, Any] | None,
        news_items: list[dict[str, Any]],
        refined_news_items: list[dict[str, Any]],
        policy_items: list[dict[str, Any]],
    ) -> dict[str, int]:
        saved_counts = {"report": 0, "event_news": 0, "refined_news": 0, "policy": 0}
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return saved_counts
        try:
            saved_counts["report"] = self.snapshot_repository.save_brent_report(
                snapshot_date=snapshot_date,
                report_payload=report_payload,
            )
            saved_counts["event_news"] = self.snapshot_repository.save_jinshi_news_items(
                snapshot_date=snapshot_date,
                items=news_items,
            )
            saved_counts["refined_news"] = self.snapshot_repository.save_refined_news_items(
                snapshot_date=snapshot_date,
                items=refined_news_items,
            )
            saved_counts["policy"] = self.snapshot_repository.save_policy_items(
                snapshot_date=snapshot_date,
                items=policy_items,
            )
        except Exception:
            return saved_counts
        return saved_counts

    def _persist_latest_price_snapshot(
        self,
        *,
        snapshot_date: date,
        latest_prices: dict[str, float | None],
        mode: str,
        reason: str | None,
    ) -> int:
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return 0
        try:
            return self.snapshot_repository.save_market_snapshot(
                snapshot_date=snapshot_date,
                latest_prices=latest_prices,
                mode=mode,
                reason=reason,
            )
        except Exception:
            return 0

    def _build_archived_event_risk_snapshot_from_items(
        self,
        start_date: date,
        end_date: date,
        news_items: list[dict[str, Any]],
        report_items: list[dict[str, Any]],
        news_lookback_days: int,
        report_lookback_days: int,
        per_day_limit: int,
        news_source_counts: dict[str, int] | None = None,
        report_source_counts: dict[str, int] | None = None,
        news_archive_start: date | None = None,
        news_archive_end: date | None = None,
        report_archive_start: date | None = None,
        report_archive_end: date | None = None,
    ) -> ArchivedEventRiskSnapshot:
        news_fetch_start = start_date - timedelta(days=news_lookback_days)
        report_fetch_start = start_date - timedelta(days=report_lookback_days)

        normalized_news_items: list[dict[str, Any]] = []
        effective_news_source_counts: dict[str, int] = dict(news_source_counts or {})
        for item in news_items:
            publish_date = self._extract_item_date(item)
            if publish_date is None or publish_date < news_fetch_start or publish_date > end_date:
                continue
            normalized = dict(item)
            normalized["_publish_date"] = publish_date
            normalized_news_items.append(normalized)
            if not news_source_counts:
                source = str(item.get("source") or "unknown")
                effective_news_source_counts[source] = effective_news_source_counts.get(source, 0) + 1

        deduped_news_items = self._dedupe_news_items(normalized_news_items)
        deduped_news_items.sort(
            key=lambda item: (
                item["_publish_date"],
                float(item.get("major_score") or item.get("relevance_score") or 0.0),
                str(item.get("publish_time") or item.get("publish_date") or ""),
            ),
            reverse=True,
        )

        normalized_report_items: list[dict[str, Any]] = []
        effective_report_source_counts: dict[str, int] = dict(report_source_counts or {})
        for item in report_items:
            report_date = self._extract_report_date(item)
            if report_date is None or report_date < report_fetch_start or report_date > end_date:
                continue
            normalized = dict(item)
            normalized["_report_date"] = report_date
            normalized_report_items.append(normalized)
            if not report_source_counts:
                source = str(item.get("source") or "unknown")
                effective_report_source_counts[source] = effective_report_source_counts.get(source, 0) + 1

        normalized_report_items.sort(
            key=lambda item: (
                item["_report_date"],
                len(str(item.get("markdown") or "")),
            ),
            reverse=True,
        )

        news_items_by_date: dict[date, list[dict[str, Any]]] = {}
        report_by_date: dict[date, dict[str, Any] | None] = {}
        current_date = start_date
        while current_date <= end_date:
            news_window_start = current_date - timedelta(days=news_lookback_days)
            day_news_items = [
                self._drop_internal_fields(item)
                for item in deduped_news_items
                if news_window_start <= item["_publish_date"] <= current_date
            ]
            report_window_start = current_date - timedelta(days=report_lookback_days)
            day_report = next(
                (
                    self._drop_internal_report_fields(item)
                    for item in normalized_report_items
                    if report_window_start <= item["_report_date"] <= current_date
                ),
                None,
            )
            news_items_by_date[current_date] = day_news_items[:per_day_limit]
            report_by_date[current_date] = day_report
            current_date += timedelta(days=1)

        computed_news_dates = [item["_publish_date"] for item in deduped_news_items]
        computed_report_dates = [item["_report_date"] for item in normalized_report_items]
        return ArchivedEventRiskSnapshot(
            news_items_by_date=news_items_by_date,
            report_by_date=report_by_date,
            news_source_counts=effective_news_source_counts,
            report_source_counts=effective_report_source_counts,
            news_archive_start=news_archive_start or (min(computed_news_dates) if computed_news_dates else None),
            news_archive_end=news_archive_end or (max(computed_news_dates) if computed_news_dates else None),
            report_archive_start=report_archive_start or (min(computed_report_dates) if computed_report_dates else None),
            report_archive_end=report_archive_end or (max(computed_report_dates) if computed_report_dates else None),
        )

    def _empty_event_risk_snapshot(self, start_date: date, end_date: date) -> ArchivedEventRiskSnapshot:
        news_items_by_date = {current_date: [] for current_date in pd.date_range(start_date, end_date).date}
        report_by_date = {current_date: None for current_date in pd.date_range(start_date, end_date).date}
        return ArchivedEventRiskSnapshot(
            news_items_by_date=news_items_by_date,
            report_by_date=report_by_date,
            news_source_counts={},
            report_source_counts={},
            news_archive_start=None,
            news_archive_end=None,
            report_archive_start=None,
            report_archive_end=None,
        )

    def _compute_features(self, frame: pd.DataFrame, policy_items: list[dict[str, Any]]) -> pd.DataFrame:
        frame = frame.copy()
        non_numeric_cols = {
            "date",
            "sales_production_ratio_source",
            "sales_production_ratio_url",
            "sales_production_ratio_publish_time",
            "last_ceiling_adjust_date",
            "next_price_adjustment_window_date",
        }
        numeric_cols = [column for column in frame.columns if column not in non_numeric_cols]
        for column in numeric_cols:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame["brent_change_1d"] = frame["brent_active_settlement"].diff(1)
        frame["brent_change_3d"] = frame["brent_active_settlement"].diff(3)
        frame["brent_change_5d"] = frame["brent_active_settlement"].diff(5)
        frame["brent_change_20d"] = frame["brent_active_settlement"].diff(20)
        frame = self._attach_formula_crack_spreads(frame)
        frame = frame.copy()
        frame["gas_price_change_1d"] = frame["sd_gas92_market"].diff(1)
        frame["gas_price_change_3d"] = frame["sd_gas92_market"].diff(3)
        frame["gas_price_ma5"] = frame["sd_gas92_market"].rolling(5).mean()
        frame["gas_price_ma10"] = frame["sd_gas92_market"].rolling(10).mean()
        frame["gasoline_crack_change_3d"] = frame["sd_gas_crack"].diff(3)
        frame["gasoline_crack_trend"] = np.sign(frame["gasoline_crack_change_3d"]).fillna(0.0)
        frame["gasoline_crack_percentile"] = self._expanding_percentile(frame["sd_gas_crack"])
        frame["ceiling_change_1d"] = frame["sd_ceiling_gas"].diff(1)
        frame["ceiling_gap"] = frame["sd_ceiling_gas"] - frame["sd_gas92_market"]
        frame["price_adjustment_expected_yuan"] = self._first_available_series(
            frame,
            [
                "price_adjustment_expected_yuan",
                "refined_oil_adjustment_expected_yuan",
                "oil_price_adjustment_forecast_yuan",
                "expected_price_adjustment_yuan_per_ton",
                "price_window_expected_adjustment",
            ],
        )
        frame = frame.copy()
        frame["sd_cn_spread"] = frame["sd_gas92_market"] - frame["cn_gas92_market"]
        for price_column, spread_column in REGIONAL_SPREAD_SPECS:
            frame[spread_column] = frame["sd_gas92_market"] - frame[price_column]
            frame[f"{spread_column}_change_1d"] = frame[spread_column].diff(1)
            frame[f"{spread_column}_change_3d"] = frame[spread_column].diff(3)
        frame["profit_change_1w"] = frame["sd_refining_profit"].diff(5)
        frame["sales_change_1w"] = frame["sd_gas_sales_weekly"].diff(5)
        sales_base = frame["sd_gas_sales_weekly"].rolling(20, min_periods=5).mean()
        frame["sales_ratio_d1"] = (frame["sd_gas_sales_weekly"] / sales_base * 100.0).replace([np.inf, -np.inf], np.nan)
        frame["sales_ratio_d3_avg"] = frame["sales_ratio_d1"].rolling(3, min_periods=1).mean()
        frame["sales_ratio_w1_avg"] = frame["sales_ratio_d1"].rolling(5, min_periods=1).mean()
        external_sales_production_ratio = (
            frame["sales_production_ratio_d1"].copy()
            if "sales_production_ratio_d1" in frame.columns
            else pd.Series(np.nan, index=frame.index)
        )
        if "sd_gas_production_weekly" in frame.columns:
            production_base = frame["sd_gas_production_weekly"].replace(0, np.nan)
            computed_sales_production_ratio = (
                frame["sd_gas_sales_weekly"] / production_base * 100.0
            ).replace([np.inf, -np.inf], np.nan)
        else:
            computed_sales_production_ratio = pd.Series(np.nan, index=frame.index)
        frame["sales_production_ratio_d1"] = computed_sales_production_ratio.combine_first(
            external_sales_production_ratio
        )
        manual_ratio_d3_avg = (
            pd.to_numeric(frame["sales_production_ratio_d3_avg"], errors="coerce")
            if "sales_production_ratio_d3_avg" in frame.columns
            else pd.Series(np.nan, index=frame.index)
        )
        manual_ratio_w1_avg = (
            pd.to_numeric(frame["sales_production_ratio_w1_avg"], errors="coerce")
            if "sales_production_ratio_w1_avg" in frame.columns
            else pd.Series(np.nan, index=frame.index)
        )
        frame["sales_production_ratio_d3_avg"] = manual_ratio_d3_avg.combine_first(
            frame["sales_production_ratio_d1"].rolling(3, min_periods=1).mean()
        )
        frame["sales_production_ratio_w1_avg"] = manual_ratio_w1_avg.combine_first(
            frame["sales_production_ratio_d1"].rolling(7, min_periods=1).mean()
        )
        frame["sales_production_ratio_monthly_avg"] = frame["sales_production_ratio_d1"].rolling(30, min_periods=1).mean()
        frame["sales_production_ratio_monthly_change"] = frame["sales_production_ratio_monthly_avg"] - frame[
            "sales_production_ratio_monthly_avg"
        ].shift(30)
        frame["crude_run_change_1w"] = frame["sd_crude_run_weekly"].diff(5)
        existing_utilization_percentile = (
            pd.to_numeric(frame["shandong_cdu_utilization_percentile_weekly"], errors="coerce")
            if "shandong_cdu_utilization_percentile_weekly" in frame.columns
            else pd.Series(np.nan, index=frame.index)
        )
        fallback_utilization_percentile = self._expanding_percentile(frame["sd_crude_run_weekly"])
        frame["shandong_cdu_utilization_percentile_weekly"] = existing_utilization_percentile.combine_first(
            fallback_utilization_percentile
        )
        frame["shandong_cdu_utilization_percentile_monthly"] = frame[
            "shandong_cdu_utilization_percentile_weekly"
        ].rolling(20, min_periods=5).mean()
        empty_series = pd.Series(np.nan, index=frame.index)
        trader_inventory_level = self._first_available_series(
            frame,
            [
                "shandong_trade_company_inventory",
                "shandong_trader_inventory",
                "shandong_trader_gasoline_inventory",
            ],
        )
        main_inventory_level = self._first_available_series(
            frame,
            [
                "shandong_main_company_inventory",
                "shandong_main_gasoline_inventory",
                "shandong_major_company_inventory",
            ],
        )
        refinery_inventory_level = self._first_available_series(
            frame,
            [
                "shandong_independent_refinery_inventory",
                "shandong_refinery_inventory",
                "shandong_product_inventory_total",
                "shandong_gasoline_inventory",
            ],
        )
        observed_inventory_total = pd.concat(
            [trader_inventory_level, refinery_inventory_level],
            axis=1,
        ).sum(axis=1, min_count=2)
        formal_inventory_total = pd.concat(
            [trader_inventory_level, main_inventory_level, refinery_inventory_level],
            axis=1,
        ).sum(axis=1, min_count=3)
        frame["shandong_product_inventory_total_observed"] = observed_inventory_total
        frame["shandong_product_inventory_total_formal"] = formal_inventory_total
        frame["shandong_product_inventory_change_weekly"] = formal_inventory_total.diff(5)
        frame["shandong_product_inventory_percentile_weekly"] = self._expanding_percentile(formal_inventory_total)
        frame["shandong_refinery_inventory_percentile_monthly"] = self._expanding_percentile(
            refinery_inventory_level
        )
        frame["shandong_main_company_inventory_percentile_monthly"] = self._expanding_percentile(
            main_inventory_level
        )
        frame["shipments_change_1w"] = frame["sd_gas_shipments_weekly"].diff(5)
        frame["mtbe_change_3d"] = frame["sd_mtbe_price"].diff(3)
        frame["naphtha_change_3d"] = frame["sd_naphtha_price"].diff(3)
        frame["gas_naphtha_spread_change_3d"] = frame["sd_gas_naphtha_spread"].diff(3)
        frame = self._attach_policy_cycle_features(frame, policy_items=policy_items)
        frame["next_day_price"] = frame["sd_gas92_market"].shift(-1)
        frame["next_day_date"] = frame["date"].shift(-1)
        frame["next_day_delta"] = frame["next_day_price"] - frame["sd_gas92_market"]
        frame["next_day_direction"] = frame["next_day_delta"].apply(
            lambda value: "up" if value > 0 else "down" if value < 0 else "flat"
        )
        return frame

    def _attach_formula_crack_spreads(self, frame: pd.DataFrame) -> pd.DataFrame:
        cny_mid = self._resolve_cny_mid_series(frame)
        crude_cost = frame["brent_active_settlement"] * BARREL_TO_TON_RATIO * cny_mid
        for price_column, crack_column in GASOLINE_CRACK_PRICE_COLUMNS.items():
            if price_column not in frame.columns:
                continue
            formula = self._calculate_crack_spread(
                market_price=frame[price_column],
                crude_cost=crude_cost,
                consumption_tax=GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON,
            )
            frame[f"{crack_column}_formula"] = formula
            frame[f"{crack_column}_formula_available"] = formula.notna().astype(float)
            if crack_column in frame.columns:
                frame[crack_column] = formula.combine_first(frame[crack_column])
            else:
                frame[crack_column] = formula
        for price_column, crack_column in DIESEL_CRACK_PRICE_COLUMNS.items():
            if price_column not in frame.columns:
                continue
            formula = self._calculate_crack_spread(
                market_price=frame[price_column],
                crude_cost=crude_cost,
                consumption_tax=DIESEL_CONSUMPTION_TAX_YUAN_PER_TON,
            )
            frame[f"{crack_column}_formula"] = formula
            frame[f"{crack_column}_formula_available"] = formula.notna().astype(float)
            if crack_column in frame.columns:
                frame[crack_column] = formula.combine_first(frame[crack_column])
            else:
                frame[crack_column] = formula
        return frame

    def _calculate_crack_spread(
        self,
        *,
        market_price: pd.Series,
        crude_cost: pd.Series,
        consumption_tax: float,
    ) -> pd.Series:
        return market_price / (1.0 + VAT_RATE) - consumption_tax - crude_cost

    def _resolve_cny_mid_series(self, frame: pd.DataFrame) -> pd.Series:
        candidates = [
            "cny_mid_rate",
            "usd_cny_mid_rate",
            "usdcny_mid",
            "usd_cny",
            "cny_exchange_rate",
            "rmb_exchange_rate_mid",
            "人民币汇率中间价",
        ]
        for column in candidates:
            if column in frame.columns:
                return pd.to_numeric(frame[column], errors="coerce")
        return pd.Series(np.nan, index=frame.index)

    def _expanding_percentile(self, series: pd.Series, min_periods: int = 5) -> pd.Series:
        def percentile(values: np.ndarray) -> float:
            current = values[-1]
            if np.isnan(current):
                return np.nan
            valid = values[~np.isnan(values)]
            if len(valid) < min_periods:
                return np.nan
            return float(np.sum(valid <= current) / len(valid) * 100.0)

        return series.astype(float).expanding(min_periods=min_periods).apply(percentile, raw=True)

    def _first_available_series(self, frame: pd.DataFrame, columns: list[str]) -> pd.Series:
        result = pd.Series(np.nan, index=frame.index)
        for column in columns:
            if column in frame.columns:
                result = result.combine_first(pd.to_numeric(frame[column], errors="coerce"))
        return result

    def _merge_refined_news_items(
        self,
        primary_items: list[dict[str, Any]],
        secondary_items: list[dict[str, Any]],
        total_limit: int,
    ) -> list[dict[str, Any]]:
        merged = self._dedupe_news_items([*(secondary_items or []), *(primary_items or [])])
        merged.sort(
            key=lambda item: (
                float(item.get("priority_score") or 0.0),
                str(item.get("publish_time") or item.get("publish_hint") or ""),
            ),
            reverse=True,
        )
        protected_sources = {"oilchem_shandong_spot_daily_report"}
        protected_items = [item for item in merged if str(item.get("source") or "") in protected_sources][:5]
        protected_urls = {str(item.get("url") or item.get("headline") or item.get("title") or "") for item in protected_items}
        regular_items = [
            item
            for item in merged
            if str(item.get("url") or item.get("headline") or item.get("title") or "") not in protected_urls
        ]
        return [*protected_items, *regular_items][:total_limit]

    def _dedupe_news_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            key = str(item.get("url") or item.get("headline") or item.get("title") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _extract_item_date(self, item: dict[str, Any]) -> date | None:
        for field in ("publish_time", "publish_date"):
            raw_value = str(item.get(field) or "").strip()
            if len(raw_value) < 10:
                continue
            normalized = raw_value.replace("/", "-")
            try:
                return pd.Timestamp(normalized[:10]).date()
            except Exception:
                continue
        text = " ".join(str(item.get(field) or "") for field in ("title", "headline", "content"))
        for match in re.finditer(r"(?<!\d)(20\d{2})[-/.年]?\s?([01]\d)[-/.月]?\s?([0-3]\d)(?:日)?(?!\d)", text):
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                continue
        return None

    def _prediction_news_cutoff(self, as_of_date: date) -> datetime:
        return datetime.combine(as_of_date, time(hour=7, minute=0))

    def _is_news_item_available_by_cutoff(self, item: dict[str, Any], as_of_date: date) -> bool:
        cutoff = self._prediction_news_cutoff(as_of_date)
        raw_value = str(item.get("publish_time") or item.get("publish_date") or "").strip()
        if len(raw_value) < 10:
            item_date = self._extract_item_date(item)
            return bool(item_date and item_date < as_of_date)
        try:
            timestamp = pd.Timestamp(raw_value.replace("/", "-"))
        except Exception:
            item_date = self._extract_item_date(item)
            return bool(item_date and item_date < as_of_date)
        item_date = timestamp.date()
        if item_date < as_of_date:
            return True
        if item_date > as_of_date:
            return False
        if len(raw_value) <= 10:
            return False
        try:
            if timestamp.tzinfo is not None:
                timestamp = timestamp.tz_convert(None)
        except Exception:
            try:
                timestamp = timestamp.tz_localize(None)
            except Exception:
                pass
        return timestamp.to_pydatetime().replace(tzinfo=None) <= cutoff

    def _drop_internal_fields(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        normalized.pop("_publish_date", None)
        return normalized

    def _dedupe_policy_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            key = str(item.get("url") or item.get("title") or item.get("effective_time") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _drop_internal_policy_fields(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        normalized.pop("_event_date", None)
        return normalized

    def _drop_internal_report_fields(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        normalized.pop("_report_date", None)
        return normalized

    def _load_policy_items(self, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
        if start_date and end_date and self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_policy_items(start_date=start_date, end_date=end_date)
                if load_result.items:
                    return self._dedupe_policy_items(load_result.items)
            except Exception:
                pass
        if not self.policy_scraping_enabled:
            return []
        try:
            return self._dedupe_policy_items(self.policy_client.fetch_recent_adjustments(limit=40))
        except Exception:
            return []

    def _load_refined_news_archive_for_feed(self, end_date: date) -> list[dict[str, Any]]:
        start_date = end_date - timedelta(days=self.FEED_LOOKBACK_DAYS)
        items: list[dict[str, Any]] = []
        if self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_refined_news_items(start_date=start_date, end_date=end_date)
                items = load_result.items
            except Exception:
                items = []
        if not items:
            items = self._load_refined_news_items(as_of_date=end_date)
        normalized = []
        for item in items:
            item_date = self._extract_item_date(item)
            if item_date is None:
                continue
            normalized_item = dict(item)
            normalized_item["_item_date"] = item_date
            normalized_item["_importance_score"] = self._score_news_importance(item)
            normalized.append(normalized_item)
        return self._dedupe_news_items(normalized)

    def _load_event_news_archive_for_feed(self, end_date: date) -> list[dict[str, Any]]:
        start_date = end_date - timedelta(days=self.FEED_LOOKBACK_DAYS)
        items: list[dict[str, Any]] = []
        if self.snapshot_repository and self.snapshot_repository.enabled:
            try:
                load_result = self.snapshot_repository.load_jinshi_news_items(start_date=start_date, end_date=end_date)
                items = load_result.items
            except Exception:
                items = []
        if not items:
            items = self._load_event_news_items(as_of_date=end_date)
        normalized = []
        for item in items:
            item_date = self._extract_item_date(item)
            if item_date is None:
                continue
            normalized_item = dict(item)
            normalized_item["_item_date"] = item_date
            normalized_item["_importance_score"] = self._score_event_importance(item)
            normalized.append(normalized_item)
        return self._dedupe_news_items(normalized)

    def _load_policy_archive_for_feed(self, end_date: date) -> list[dict[str, Any]]:
        start_date = end_date - timedelta(days=self.POLICY_LOOKBACK_DAYS)
        items = self._load_policy_items(start_date=start_date, end_date=end_date)
        normalized = []
        for item in items:
            item_date = self._extract_policy_item_date(item)
            if item_date is None:
                continue
            normalized_item = dict(item)
            normalized_item["_item_date"] = item_date
            normalized_item["_importance_score"] = self._score_policy_importance(item, end_date=end_date)
            normalized.append(normalized_item)
        return self._dedupe_policy_items(normalized)

    def _extract_policy_item_date(self, item: dict[str, Any]) -> date | None:
        for field in ("effective_time", "publish_date"):
            raw_value = str(item.get(field) or "").strip()
            if len(raw_value) < 10:
                continue
            normalized = raw_value.replace("/", "-")
            try:
                return pd.Timestamp(normalized[:10]).date()
            except Exception:
                continue
        return None

    def _extract_report_date(self, item: dict[str, Any]) -> date | None:
        raw_value = str(item.get("report_date") or "").strip()
        if len(raw_value) < 10:
            return None
        normalized = raw_value.replace("/", "-")
        try:
            return pd.Timestamp(normalized[:10]).date()
        except Exception:
            return None

    def _round_or_none(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            if pd.isna(value):
                return None
            return round(float(value), 2)
        except Exception:
            return None

    def _score_news_importance(self, item: dict[str, Any]) -> float:
        title = str(item.get("headline") or item.get("title") or "")
        content = str(item.get("summary") or item.get("content") or "")
        base = float(item.get("priority_score") or 0.0)
        if "山东" in title or "山东" in content:
            base += 8.0
        if "地炼" in title or "地炼" in content:
            base += 5.0
        if "调价" in title or "调价" in content:
            base += 4.0
        if "停工" in title or "检修" in title or "停工" in content or "检修" in content:
            base += 3.0
        if str(item.get("content") or "").strip():
            base += 1.5
        return round(base, 4)

    def _score_event_importance(self, item: dict[str, Any]) -> float:
        title = str(item.get("headline") or item.get("title") or "")
        content = str(item.get("content") or "")
        major_score = float(item.get("major_score") or 0.0)
        relevance_score = float(item.get("relevance_score") or 0.0)
        base = major_score * 2.0 + relevance_score * 1.5
        for keyword in ("地缘", "袭击", "制裁", "停火", "OPEC", "产量", "库存", "运费", "红海", "霍尔木兹"):
            if keyword in title or keyword in content:
                base += 2.5
        return round(base, 4)

    def _score_policy_importance(self, item: dict[str, Any], end_date: date) -> float:
        delta = abs(float(item.get("gasoline_change_yuan_per_ton") or 0.0))
        item_date = self._extract_policy_item_date(item)
        recency_bonus = 0.0
        if item_date is not None:
            days = max((end_date - item_date).days, 0)
            recency_bonus = max(8.0 - days * 0.4, 0.0)
        return round(delta / 15.0 + recency_bonus, 4)

    def _sort_feed_items(self, items: list[dict[str, Any]], sort_mode: str) -> None:
        if sort_mode == "time":
            items.sort(
                key=lambda item: (
                    item.get("_item_date"),
                    str(item.get("publish_time") or item.get("publish_date") or item.get("effective_time") or ""),
                ),
                reverse=True,
            )
            return
        items.sort(
            key=lambda item: (
                float(item.get("_importance_score") or 0.0),
                str(item.get("publish_time") or item.get("publish_date") or item.get("effective_time") or ""),
            ),
            reverse=True,
        )

    def _build_alert_items(
        self,
        *,
        refined_news_items: list[dict[str, Any]],
        event_news_items: list[dict[str, Any]],
        policy_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in event_news_items[:12]:
            alert_context = self._build_alert_context(item=item, category="事件")
            candidates.append(
                {
                    "title": str(item.get("headline") or item.get("title") or ""),
                    "time": str(item.get("publish_time") or item.get("publish_date") or ""),
                    "source": str(item.get("source") or "事件"),
                    "importance_score": round(float(item.get("_importance_score") or 0.0), 2),
                    "category": "事件",
                    "url": item.get("url"),
                    **alert_context,
                }
            )
        for item in policy_items[:8]:
            delta = item.get("gasoline_change_yuan_per_ton")
            direction_text = "上调" if (delta or 0) > 0 else "下调" if (delta or 0) < 0 else "持平"
            alert_context = self._build_policy_alert_context(item=item, delta=float(delta or 0.0))
            candidates.append(
                {
                    "title": f"{item.get('title')} | 汽油{direction_text}{delta or 0}元/吨",
                    "time": str(item.get("effective_time") or item.get("publish_date") or ""),
                    "source": "政策",
                    "importance_score": round(float(item.get("_importance_score") or 0.0), 2),
                    "category": "政策",
                    "url": item.get("url"),
                    **alert_context,
                }
            )
        for item in refined_news_items[:10]:
            score = float(item.get("_importance_score") or 0.0)
            if score < 8.0:
                continue
            alert_context = self._build_alert_context(item=item, category="资讯")
            candidates.append(
                {
                    "title": str(item.get("headline") or item.get("title") or ""),
                    "time": str(item.get("publish_time") or item.get("publish_date") or ""),
                    "source": str(item.get("source") or "资讯"),
                    "importance_score": round(score, 2),
                    "category": "资讯",
                    "url": item.get("url"),
                    **alert_context,
                }
            )
        severity_rank = {"高": 3, "中": 2, "低": 1}
        candidates.sort(
            key=lambda item: (
                str(item.get("status") or "") != "已解除",
                severity_rank.get(str(item.get("severity") or "中"), 2),
                float(item.get("alert_score") or item.get("importance_score") or 0.0),
            ),
            reverse=True,
        )
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            key = str(item.get("title") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            item["alert_id"] = self._build_alert_id(item)
            deduped.append(item)
        return deduped

    def _build_alert_id(self, item: dict[str, Any]) -> str:
        raw = "|".join(
            [
                str(item.get("category") or ""),
                str(item.get("event_type") or ""),
                str(item.get("title") or ""),
                str(item.get("time") or ""),
                str(item.get("source") or ""),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def _build_policy_alert_context(self, *, item: dict[str, Any], delta: float) -> dict[str, Any]:
        abs_delta = abs(delta)
        direction = "推涨" if delta > 0 else "压跌" if delta < 0 else "扰动"
        severity = "高" if abs_delta >= 80 else "中"
        action = (
            "临近调价窗口，报价有效期缩短；跨窗口库存和锁单需人工确认。"
            if abs_delta >= 80
            else "跟踪调价兑现节奏，维持滚动报价，避免跨窗口重仓。"
        )
        if delta < 0:
            action = (
                "控制高位库存，加快弱势订单出货；跨窗口采购以销定采。"
                if abs_delta >= 80
                else "关注终端补库放缓，报价保留小步让利空间。"
            )
        return {
            "severity": severity,
            "alert_score": round(float(item.get("_importance_score") or 0.0) + abs_delta / 12.0, 2),
            "event_type": "政策调价",
            "affected_region": "全国 / 山东",
            "affected_product": "92#汽油",
            "direction": direction,
            "expected_impact": f"{delta:+.0f} 元/吨",
            "confidence": "高",
            "status": "待确认",
            "action": action,
        }

    def _build_alert_context(self, *, item: dict[str, Any], category: str) -> dict[str, Any]:
        text = f"{item.get('headline') or item.get('title') or ''} {item.get('summary') or ''} {item.get('content') or ''}"
        base_score = float(item.get("_importance_score") or item.get("importance_score") or 0.0)
        up_keywords = ("袭击", "制裁", "减产", "供应中断", "检修", "停工", "运费上涨", "红海", "霍尔木兹", "库存下降", "地缘")
        down_keywords = ("停火", "增产", "复产", "库存增加", "需求疲软", "降价", "下跌")
        up_hits = sum(1 for keyword in up_keywords if keyword in text)
        down_hits = sum(1 for keyword in down_keywords if keyword in text)
        direction = "推涨" if up_hits > down_hits else "压跌" if down_hits > up_hits else "扰动"
        impact_score = base_score + max(up_hits, down_hits) * 1.8
        severity = "高" if impact_score >= 10.0 else "中"
        region = self._infer_alert_region(text)
        event_type = self._infer_alert_type(text, category)
        expected_impact = self._estimate_alert_impact(direction=direction, score=impact_score)
        confidence = "高" if max(up_hits, down_hits) >= 2 else "中"
        action = self._build_alert_action(direction=direction, event_type=event_type, severity=severity)
        return {
            "severity": severity,
            "alert_score": round(impact_score, 2),
            "event_type": event_type,
            "affected_region": region,
            "affected_product": "92#汽油",
            "direction": direction,
            "expected_impact": expected_impact,
            "confidence": confidence,
            "status": "新触发" if severity == "高" else "跟踪中",
            "action": action,
        }

    def _infer_alert_region(self, text: str) -> str:
        for region in ("山东", "华东", "华北", "华南", "华中", "西北", "西南", "东北"):
            if region in text:
                return region
        return "全国 / 山东联动"

    def _infer_alert_type(self, text: str, category: str) -> str:
        if any(keyword in text for keyword in ("检修", "停工", "复产", "炼厂", "装置")):
            return "炼厂事件"
        if any(keyword in text for keyword in ("运费", "物流", "限行", "港口", "红海", "霍尔木兹")):
            return "物流扰动"
        if any(keyword in text for keyword in ("地缘", "袭击", "制裁", "停火", "冲突")):
            return "地缘事件"
        if any(keyword in text for keyword in ("库存", "OPEC", "产量", "需求")):
            return "供需事件"
        return "成品油资讯" if category == "资讯" else "市场事件"

    def _estimate_alert_impact(self, *, direction: str, score: float) -> str:
        if direction == "扰动":
            return "需复核"
        if score >= 12.0:
            band = "30~80"
        elif score >= 8.0:
            band = "20~50"
        else:
            band = "10~30"
        prefix = "+" if direction == "推涨" else "-"
        return f"{prefix}{band} 元/吨"

    def _build_alert_action(self, *, direction: str, event_type: str, severity: str) -> str:
        if direction == "推涨":
            return "关注Brent跳涨与山东炼厂报价，缩短报价有效期；高优先时打开夜盘锁单预案。"
        if direction == "压跌":
            return "控制高位库存，以销定采；弱势区域保留小步让利和加快出货方案。"
        if event_type in {"炼厂事件", "物流扰动"}:
            return "人工复核影响区域和持续时间，必要时暂停跨区报价或调整发运节奏。"
        return "保留跟踪，不直接改变挂牌；等待价格或政策信号二次确认。"

    def _strip_feed_meta(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        normalized["importance_score"] = round(float(normalized.get("_importance_score") or 0.0), 2)
        normalized.pop("_item_date", None)
        normalized.pop("_importance_score", None)
        return normalized

    def _attach_policy_cycle_features(self, frame: pd.DataFrame, policy_items: list[dict[str, Any]]) -> pd.DataFrame:
        policy_events = self._build_policy_events(policy_items)
        if policy_events:
            return self._attach_policy_cycle_from_events(frame, policy_events)
        return self._attach_policy_cycle_from_ceiling(frame)

    def _build_policy_events(self, policy_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for item in policy_items:
            event_date = None
            effective_time = str(item.get("effective_time") or "").strip()
            publish_date = str(item.get("publish_date") or "").strip()
            if len(effective_time) >= 10:
                try:
                    event_date = pd.Timestamp(effective_time[:10]).date()
                except Exception:
                    event_date = None
            if event_date is None and publish_date:
                normalized = publish_date.replace("/", "-")
                try:
                    event_date = pd.Timestamp(normalized[:10]).date()
                except Exception:
                    event_date = None

            delta = item.get("gasoline_change_yuan_per_ton")
            if event_date is None or delta is None:
                continue
            events.append({"event_date": event_date, "delta": float(delta), "item": item})
        events.sort(key=lambda item: item["event_date"])
        return events

    def _attach_policy_cycle_from_events(self, frame: pd.DataFrame, policy_events: list[dict[str, Any]]) -> pd.DataFrame:
        frame = frame.copy()
        last_adjust_delta = 0.0
        last_adjust_date: date | None = None
        event_index = 0

        last_adjust_deltas: list[float] = []
        days_since_adjust: list[float] = []
        business_days_since_adjust: list[float] = []
        days_to_next_window: list[float] = []
        last_adjust_dates: list[str | None] = []
        next_window_dates: list[str | None] = []

        for _, row in frame.iterrows():
            current_ts = pd.Timestamp(row["date"])
            current_date = current_ts.date()

            while event_index < len(policy_events) and policy_events[event_index]["event_date"] <= current_date:
                last_adjust_date = policy_events[event_index]["event_date"]
                last_adjust_delta = float(policy_events[event_index]["delta"])
                event_index += 1

            last_adjust_deltas.append(last_adjust_delta)
            if last_adjust_date is None:
                days_since_adjust.append(np.nan)
                business_days_since_adjust.append(np.nan)
                days_to_next_window.append(np.nan)
                last_adjust_dates.append(None)
                next_window_dates.append(None)
                continue

            calendar_days = float((current_date - last_adjust_date).days)
            business_days = float(
                np.busday_count(
                    last_adjust_date.strftime("%Y-%m-%d"),
                    current_date.strftime("%Y-%m-%d"),
                )
            )
            days_since_adjust.append(calendar_days)
            business_days_since_adjust.append(business_days)
            days_to_next_window.append(float(max(10.0 - business_days, 0.0)))
            last_adjust_dates.append(last_adjust_date.isoformat())
            next_window_dates.append(self._add_business_days(last_adjust_date, 10).isoformat())

        frame["last_ceiling_adjust_delta"] = last_adjust_deltas
        frame["last_ceiling_adjust_date"] = last_adjust_dates
        frame["next_price_adjustment_window_date"] = next_window_dates
        frame["days_since_ceiling_adjust"] = days_since_adjust
        frame["business_days_since_ceiling_adjust"] = business_days_since_adjust
        frame["days_to_next_window"] = days_to_next_window
        frame["cycle_day_index"] = frame["business_days_since_ceiling_adjust"]
        return frame

    def _attach_policy_cycle_from_ceiling(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        last_adjust_delta = 0.0
        last_adjust_date: date | None = None

        last_adjust_deltas: list[float] = []
        days_since_adjust: list[float] = []
        business_days_since_adjust: list[float] = []
        days_to_next_window: list[float] = []
        last_adjust_dates: list[str | None] = []
        next_window_dates: list[str | None] = []

        for _, row in frame.iterrows():
            current_ts = pd.Timestamp(row["date"])
            current_date = current_ts.date()
            current_change = row.get("ceiling_change_1d")

            if pd.notna(current_change) and abs(float(current_change)) >= 1.0:
                last_adjust_delta = float(current_change)
                last_adjust_date = current_date

            last_adjust_deltas.append(last_adjust_delta)
            if last_adjust_date is None:
                days_since_adjust.append(np.nan)
                business_days_since_adjust.append(np.nan)
                days_to_next_window.append(np.nan)
                last_adjust_dates.append(None)
                next_window_dates.append(None)
                continue

            calendar_days = float((current_date - last_adjust_date).days)
            business_days = float(
                np.busday_count(
                    last_adjust_date.strftime("%Y-%m-%d"),
                    current_date.strftime("%Y-%m-%d"),
                )
            )
            days_since_adjust.append(calendar_days)
            business_days_since_adjust.append(business_days)
            days_to_next_window.append(float(max(10.0 - business_days, 0.0)))
            last_adjust_dates.append(last_adjust_date.isoformat())
            next_window_dates.append(self._add_business_days(last_adjust_date, 10).isoformat())

        frame["last_ceiling_adjust_delta"] = last_adjust_deltas
        frame["last_ceiling_adjust_date"] = last_adjust_dates
        frame["next_price_adjustment_window_date"] = next_window_dates
        frame["days_since_ceiling_adjust"] = days_since_adjust
        frame["business_days_since_ceiling_adjust"] = business_days_since_adjust
        frame["days_to_next_window"] = days_to_next_window
        frame["cycle_day_index"] = frame["business_days_since_ceiling_adjust"]
        return frame

    def _add_business_days(self, start_date: date, business_days: int) -> date:
        current = start_date
        added = 0
        while added < business_days:
            current += timedelta(days=1)
            if np.is_busday(current.strftime("%Y-%m-%d")):
                added += 1
        return current
