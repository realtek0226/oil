from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
import numpy as np
import pandas as pd

from app.clients.brent_report_client import BrentReportClient
from app.clients.china_money_client import ChinaMoneyCnyMidClient
from app.clients.cnenergy_refined_oil_client import CnEnergyRefinedOilClient
from app.clients.competitor_price_client import CompetitorPriceClient
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
from app.services.refinery_region_map import match_refinery_regions, matched_region_names
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
LOCAL_CDU_UTILIZATION_COLUMN = "成品油：常减压：产能利用率：山东：独立炼厂（周）"
CDU_UTILIZATION_PERCENTILE_START = date(2024, 1, 1)
CDU_UTILIZATION_INDICATOR_KEYS = [
    "shandong_cdu_utilization_weekly",
    "east_china_cdu_utilization_weekly",
    "north_china_cdu_utilization_weekly",
    "south_china_cdu_utilization_weekly",
    "central_china_cdu_utilization_weekly",
    "northwest_cdu_utilization_weekly",
    "southwest_cdu_utilization_weekly",
    "northeast_cdu_utilization_weekly",
]

CDU_UTILIZATION_SOURCE_ALIASES = {
    "shandong_cdu_utilization_weekly": ("shandong_cdu_utilization_weekly", "sd_crude_run_weekly"),
    "east_china_cdu_utilization_weekly": ("east_china_cdu_utilization_weekly", "ganglian_id01374947"),
    "north_china_cdu_utilization_weekly": ("north_china_cdu_utilization_weekly", "ganglian_id01374957"),
    "south_china_cdu_utilization_weekly": ("south_china_cdu_utilization_weekly", "ganglian_id01374973"),
    "central_china_cdu_utilization_weekly": ("central_china_cdu_utilization_weekly", "ganglian_id01374954"),
    "northwest_cdu_utilization_weekly": ("northwest_cdu_utilization_weekly", "ganglian_id01374969"),
    "southwest_cdu_utilization_weekly": ("southwest_cdu_utilization_weekly", "ganglian_id01374968"),
    "northeast_cdu_utilization_weekly": ("northeast_cdu_utilization_weekly", "ganglian_id01374951"),
}
CDU_UTILIZATION_QUERY_KEYS = sorted({item for aliases in CDU_UTILIZATION_SOURCE_ALIASES.values() for item in aliases})
REGIONAL_SHIPMENTS_SOURCE_ALIASES = {
    "east_china_gasoline_shipments_weekly": ("east_china_gasoline_shipments_weekly", "ganglian_id01374888", "zhonglu_id01374888"),
    "north_china_gasoline_shipments_weekly": ("north_china_gasoline_shipments_weekly", "ganglian_id01374884", "zhonglu_id01374884"),
    "south_china_gasoline_shipments_weekly": ("south_china_gasoline_shipments_weekly", "ganglian_id01374889", "zhonglu_id01374889"),
    "central_china_gasoline_shipments_weekly": ("central_china_gasoline_shipments_weekly", "ganglian_id01374885", "zhonglu_id01374885"),
    "northwest_gasoline_shipments_weekly": ("northwest_gasoline_shipments_weekly", "ganglian_id01374892", "zhonglu_id01374892"),
    "southwest_gasoline_shipments_weekly": ("southwest_gasoline_shipments_weekly", "ganglian_id01374887", "zhonglu_id01374887"),
    "northeast_gasoline_shipments_weekly": ("northeast_gasoline_shipments_weekly", "ganglian_id01374908", "zhonglu_id01374908"),
    "east_china_diesel_shipments_weekly": ("east_china_diesel_shipments_weekly", "ganglian_id01374901", "zhonglu_id01374901"),
    "north_china_diesel_shipments_weekly": ("north_china_diesel_shipments_weekly", "ganglian_id01374886", "zhonglu_id01374886"),
    "south_china_diesel_shipments_weekly": ("south_china_diesel_shipments_weekly", "ganglian_id01374909", "zhonglu_id01374909"),
    "central_china_diesel_shipments_weekly": ("central_china_diesel_shipments_weekly", "ganglian_id01374890", "zhonglu_id01374890"),
    "northwest_diesel_shipments_weekly": ("northwest_diesel_shipments_weekly", "ganglian_id01374907", "zhonglu_id01374907"),
    "southwest_diesel_shipments_weekly": ("southwest_diesel_shipments_weekly", "ganglian_id01374893", "zhonglu_id01374893"),
    "northeast_diesel_shipments_weekly": ("northeast_diesel_shipments_weekly", "ganglian_id01374894", "zhonglu_id01374894"),
}
REGIONAL_SHIPMENTS_INDICATOR_KEYS = list(REGIONAL_SHIPMENTS_SOURCE_ALIASES.keys())
REGIONAL_SHIPMENTS_QUERY_KEYS = sorted({item for aliases in REGIONAL_SHIPMENTS_SOURCE_ALIASES.values() for item in aliases})
COMPETITOR_PRICE_HISTORY_ALIASES = {
    "sd_gas92_market": "competitor_sd_gas92_market_avg",
    "east_china_gas92_market": "competitor_east_china_gas92_market_avg",
    "north_china_gas92_market": "competitor_north_china_gas92_market_avg",
    "south_china_gas92_market": "competitor_south_china_gas92_market_avg",
    "central_china_gas92_market": "competitor_central_china_gas92_market_avg",
    "northwest_gas92_market": "competitor_northwest_gas92_market_avg",
    "southwest_gas92_market": "competitor_southwest_gas92_market_avg",
    "northeast_gas92_market": "competitor_northeast_gas92_market_avg",
    "sd_diesel0_market": "competitor_sd_diesel0_market_avg",
    "east_china_diesel0_market": "competitor_east_china_diesel0_market_avg",
    "north_china_diesel0_market": "competitor_north_china_diesel0_market_avg",
    "south_china_diesel0_market": "competitor_south_china_diesel0_market_avg",
    "central_china_diesel0_market": "competitor_central_china_diesel0_market_avg",
    "northwest_diesel0_market": "competitor_northwest_diesel0_market_avg",
    "southwest_diesel0_market": "competitor_southwest_diesel0_market_avg",
    "northeast_diesel0_market": "competitor_northeast_diesel0_market_avg",
}
SHANDONG_INVENTORY_SOURCE_ALIASES = {
    "shandong_independent_refinery_inventory": (
        "shandong_independent_refinery_inventory",
        "ganglian_id01374817",
        "zhonglu_id01374817",
    ),
    "shandong_diesel_inventory": (
        "shandong_diesel_inventory",
        "ganglian_id01374828",
        "zhonglu_id01374828",
    ),
}
SHANDONG_INVENTORY_QUERY_KEYS = sorted({item for aliases in SHANDONG_INVENTORY_SOURCE_ALIASES.values() for item in aliases})
PERCENTILE_HISTORY_START = date(2024, 1, 1)
CRACK_PERCENTILE_HISTORY_START = date(2025, 1, 1)
SCI99_REFINED_OIL_URL = "https://energy.sci99.com/product/refined_oil"

MAINTENANCE_REGION_PROVINCES = {
    "华东": ("上海", "江苏", "浙江", "山东"),
    "华南": ("广东", "海南", "福建"),
    "华北": ("北京", "天津", "山西", "河北", "河南", "内蒙古"),
    "华中": ("安徽", "江西", "湖南", "湖北"),
    "西北": ("陕西", "甘肃", "青海", "宁夏", "新疆"),
    "东北": ("黑龙江", "吉林", "辽宁"),
    "西南": ("重庆", "四川", "贵州", "云南", "广西", "西藏"),
}

PROVINCE_TO_MAINTENANCE_REGION = {
    province: region
    for region, provinces in MAINTENANCE_REGION_PROVINCES.items()
    for province in provinces
}


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

INDICATOR_KEYS = [
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
    "shandong_main_gasoline_inventory",
    "shandong_major_company_inventory",
    "shandong_independent_refinery_inventory",
    "shandong_diesel_inventory",
    "shandong_main_company_diesel_inventory",
    "shandong_main_diesel_inventory",
    "shandong_independent_refinery_diesel_inventory",
    "shandong_refinery_diesel_inventory",
    "shandong_diesel_inventory_change_mom",
    "shandong_diesel_inventory_capacity_rate",
    "price_adjustment_expected_yuan",
    "refined_oil_adjustment_expected_yuan",
    "oil_price_adjustment_forecast_yuan",
    "expected_price_adjustment_yuan_per_ton",
    "price_window_expected_adjustment",
    *CDU_UTILIZATION_INDICATOR_KEYS,
]

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
    "shandong_main_gasoline_inventory",
    "shandong_major_company_inventory",
    "shandong_independent_refinery_inventory",
    "shandong_diesel_inventory",
    "shandong_main_company_diesel_inventory",
    "shandong_main_diesel_inventory",
    "shandong_independent_refinery_diesel_inventory",
    "shandong_refinery_diesel_inventory",
    "shandong_diesel_inventory_change_mom",
    "shandong_diesel_inventory_capacity_rate",
    "price_adjustment_expected_yuan",
    "refined_oil_adjustment_expected_yuan",
    "oil_price_adjustment_forecast_yuan",
    "expected_price_adjustment_yuan_per_ton",
    "price_window_expected_adjustment",
    *CDU_UTILIZATION_INDICATOR_KEYS,
]

INDICATOR_KEYS = [
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
    "sd_diesel0_market",
    "cn_diesel0_market",
    "east_china_diesel0_market",
    "north_china_diesel0_market",
    "south_china_diesel0_market",
    "central_china_diesel0_market",
    "northwest_diesel0_market",
    "southwest_diesel0_market",
    "northeast_diesel0_market",
    "cny_mid_rate",
    "sd_gas_crack",
    "sd_diesel_crack",
    "shandong_main_company_inventory",
    "shandong_main_gasoline_inventory",
    "shandong_independent_refinery_inventory",
    "shandong_diesel_inventory",
    "shandong_main_company_diesel_inventory",
    "shandong_main_diesel_inventory",
    "shandong_independent_refinery_diesel_inventory",
    "shandong_refinery_diesel_inventory",
    *SHANDONG_INVENTORY_QUERY_KEYS,
    *CDU_UTILIZATION_INDICATOR_KEYS,
    *REGIONAL_SHIPMENTS_QUERY_KEYS,
]

SNAPSHOT_INDICATOR_KEYS = INDICATOR_KEYS

PREFERRED_CASH_PRICE_SOURCE_CODES = (
    "manual_prediction_template",
    "ganglian_excel_import",
    "oilchem_refined_oil_price_center",
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
    ("east_china_gas92_market", "sd_vs_east_china_spread", "sd_gas92_market"),
    ("north_china_gas92_market", "sd_vs_north_china_spread", "sd_gas92_market"),
    ("south_china_gas92_market", "sd_vs_south_china_spread", "sd_gas92_market"),
    ("central_china_gas92_market", "sd_vs_central_china_spread", "sd_gas92_market"),
    ("northwest_gas92_market", "sd_vs_northwest_spread", "sd_gas92_market"),
    ("southwest_gas92_market", "sd_vs_southwest_spread", "sd_gas92_market"),
    ("northeast_gas92_market", "sd_vs_northeast_spread", "sd_gas92_market"),
    ("east_china_diesel0_market", "sd_vs_east_china_diesel_spread", "sd_diesel0_market"),
    ("north_china_diesel0_market", "sd_vs_north_china_diesel_spread", "sd_diesel0_market"),
    ("south_china_diesel0_market", "sd_vs_south_china_diesel_spread", "sd_diesel0_market"),
    ("central_china_diesel0_market", "sd_vs_central_china_diesel_spread", "sd_diesel0_market"),
    ("northwest_diesel0_market", "sd_vs_northwest_diesel_spread", "sd_diesel0_market"),
    ("southwest_diesel0_market", "sd_vs_southwest_diesel_spread", "sd_diesel0_market"),
    ("northeast_diesel0_market", "sd_vs_northeast_diesel_spread", "sd_diesel0_market"),
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
    CONTEXT_CACHE_SECONDS = 600

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
        competitor_price_client: CompetitorPriceClient | None,
        oilchem_price_client: OilchemPriceClient,
        oilchem_production_sales_client: OilchemProductionSalesClient,
        cnenergy_refined_oil_client: CnEnergyRefinedOilClient,
        jlc_refined_oil_client: JlcRefinedOilClient,
        sci99_refinery_dynamic_client: Any | None,
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
        self.competitor_price_client = competitor_price_client
        self.oilchem_price_client = oilchem_price_client
        self.oilchem_production_sales_client = oilchem_production_sales_client
        self.cnenergy_refined_oil_client = cnenergy_refined_oil_client
        self.jlc_refined_oil_client = jlc_refined_oil_client
        self.sci99_refinery_dynamic_client = sci99_refinery_dynamic_client
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
        self._price_history_frame_cache: dict[date, tuple[datetime, date, pd.DataFrame]] = {}

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
        if report_date != as_of_date:
            if as_of_date < date.today():
                return None
            report_text = report_date.isoformat() if report_date else "\u672a\u53d6\u5230"
            return PredictionTimeAlignmentError(
                "\u9884\u6d4b\u524d\u65f6\u95f4\u7ef4\u5ea6\u672a\u5bf9\u9f50\uff1a\u5f53\u524d\u4ef7\u683c\u57fa\u51c6\u65e5\u4e3a"
                f"{as_of_date.isoformat()}\uff0cBrent\u65e5\u62a5\u65e5\u671f\u4e3a{report_text}\u3002"
                "\u7cfb\u7edf\u8981\u6c42Brent\u65e5\u62a5\u4e0e\u5f53\u524d\u4ef7\u683c\u57fa\u51c6\u65e5\u4e00\u81f4\u3002",
                as_of_date=as_of_date,
                report_date=report_date,
            )
        d1_target_date = resolve_horizon_config("D1").target_date_from(as_of_date)
        acceptable_forecast_dates = {as_of_date}
        if report_date is not None:
            acceptable_forecast_dates.add(report_date)
        if forecast_date not in acceptable_forecast_dates:
            # Historical dates may not have archived Brent reports yet; keep legacy fallback for backfills.
            # Current/future runs must have a Brent report aligned with the current price base date.
            if as_of_date < date.today():
                return None
            forecast_text = forecast_date.isoformat() if forecast_date else "未取到"
            return PredictionTimeAlignmentError(
                "预测前时间维度未对齐：当前价格基准日为"
                f"{as_of_date.isoformat()}，成品油D1目标日为{d1_target_date.isoformat()}，"
                f"但Brent日报预测日期为{forecast_text}。"
                "系统要求Brent日报与当前价格基准日一致后，"
                "才能用日报预测点位-日报settlement生成成本侧输入。",
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

    def _load_price_history_rows_from_archive(
        self,
        *,
        requested: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        if not self.snapshot_repository or not self.snapshot_repository.enabled or not requested:
            return pd.DataFrame(columns=["date", *requested])
        merged: dict[tuple[date, str], dict[str, Any]] = {}
        source_indicator_requests: list[tuple[str, dict[str, str]]] = [
            ("manual_prediction_template", {key: key for key in requested}),
            ("ganglian_excel_import", {key: key for key in requested}),
            ("oilchem_refined_oil_price_center", {key: key for key in requested}),
            ("zhonglu_excel_archive", {key: key for key in requested}),
        ]
        competitor_aliases = {
            COMPETITOR_PRICE_HISTORY_ALIASES[key]: key
            for key in requested
            if key in COMPETITOR_PRICE_HISTORY_ALIASES
        }
        if competitor_aliases:
            source_indicator_requests.append(("competitor_price_openapi", competitor_aliases))
        for source_code, indicator_aliases in source_indicator_requests:
            try:
                rows = self.snapshot_repository.load_market_timeseries_values(
                    source_code=source_code,
                    indicator_codes=list(indicator_aliases.keys()),
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                continue
            for row in rows:
                source_indicator_code = str(row.get("indicator_code") or "")
                indicator_code = indicator_aliases.get(source_indicator_code, source_indicator_code)
                dt_value = row.get("dt")
                value = row.get("value_num")
                if indicator_code not in requested or dt_value is None or value is None:
                    continue
                try:
                    row_date = pd.Timestamp(dt_value).date()
                    numeric_value = float(value)
                except Exception:
                    continue
                key = (row_date, indicator_code)
                current = merged.get(key)
                publish_time = row.get("publish_time")
                if current is None or str(publish_time or "") >= str(current.get("publish_time") or ""):
                    merged[key] = {"date": row_date, "indicator_code": indicator_code, "value": numeric_value, "publish_time": publish_time}
        if not merged:
            return pd.DataFrame(columns=["date", *requested])
        records: dict[date, dict[str, Any]] = {}
        for item in merged.values():
            row_date = item["date"]
            records.setdefault(row_date, {"date": pd.Timestamp(row_date)})[item["indicator_code"]] = item["value"]
        frame = pd.DataFrame(records.values()).sort_values("date").reset_index(drop=True)
        for key in requested:
            if key not in frame.columns:
                frame[key] = pd.NA
        frame.attrs["market_data_mode"] = "archive_timeseries"
        frame.attrs["market_data_reason"] = "price_history_fast_archive"
        return frame

    def _expand_base_with_archived_sd_price(
        self,
        *,
        base: pd.DataFrame,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame, int]:
        archive_price_base = self._load_price_history_rows_from_archive(
            requested=["sd_gas92_market"],
            start_date=start_date,
            end_date=end_date,
        )
        if archive_price_base.empty:
            return base, 0
        archive_price_base = archive_price_base[["date", "sd_gas92_market"]].dropna(subset=["sd_gas92_market"]).copy()
        if archive_price_base.empty:
            return base, 0
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        archive_price_base["date"] = pd.to_datetime(archive_price_base["date"]).astype("datetime64[ns]")
        archive_price_base = archive_price_base[
            (archive_price_base["date"] >= start_ts) & (archive_price_base["date"] <= end_ts)
        ].copy()
        if archive_price_base.empty:
            return base, 0

        work = base.copy()
        if work.empty:
            work = pd.DataFrame(columns=["date", "sd_gas92_market"])
        work["date"] = pd.to_datetime(work["date"]).astype("datetime64[ns]")
        work = work[(work["date"] >= start_ts) & (work["date"] <= end_ts)].copy()
        work = work.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        original_dates = set(pd.to_datetime(work["date"]).dt.date) if not work.empty else set()

        archive_price_base = archive_price_base.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        archive_dates = set(pd.to_datetime(archive_price_base["date"]).dt.date)
        union_dates = pd.DataFrame({"date": sorted(set(work["date"].tolist()) | set(archive_price_base["date"].tolist()))})
        expanded = union_dates.merge(work, on="date", how="left")
        archive_values = archive_price_base.set_index("date")["sd_gas92_market"]
        if "sd_gas92_market" not in expanded.columns:
            expanded["sd_gas92_market"] = np.nan
        mask = expanded["date"].isin(archive_values.index)
        expanded.loc[mask, "sd_gas92_market"] = expanded.loc[mask, "date"].map(archive_values)
        return expanded.sort_values("date").reset_index(drop=True), len(archive_dates - original_dates)

    def _forward_fill_market_inputs(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        fill_columns = [
            "brent_active_settlement",
            "cny_mid_rate",
            "usd_cny_mid_rate",
            "usdcny_mid",
            "sd_ceiling_gas",
            "sd_mtbe_price",
            "sd_naphtha_price",
            "sd_refining_profit",
        ]
        result = frame.sort_values("date").reset_index(drop=True).copy()
        for column in fill_columns:
            if column in result.columns:
                result[column] = pd.to_numeric(result[column], errors="coerce").ffill()
        return result

    def _get_price_history_frame(self, *, start_date: date, end_date: date) -> pd.DataFrame:
        now = datetime.now()
        cached = self._price_history_frame_cache.get(end_date)
        if cached and (now - cached[0]).total_seconds() <= self.CONTEXT_CACHE_SECONDS and cached[1] <= start_date:
            frame = cached[2]
            rows = frame[(frame["date"] >= pd.Timestamp(start_date)) & (frame["date"] <= pd.Timestamp(end_date))].copy()
            rows.attrs.update(frame.attrs)
            return rows
        cache_start = end_date - timedelta(days=365 - 1)
        frame = self.build_feature_frame(start_date=cache_start, end_date=end_date)
        if not frame.empty:
            frame = frame.copy()
            frame["date"] = pd.to_datetime(frame["date"])
            frame = frame.sort_values("date")
        self._price_history_frame_cache[end_date] = (now, cache_start, frame.copy())
        if len(self._price_history_frame_cache) > 4:
            oldest_key = min(self._price_history_frame_cache, key=lambda item: self._price_history_frame_cache[item][0])
            self._price_history_frame_cache.pop(oldest_key, None)
        rows = frame[(frame["date"] >= pd.Timestamp(start_date)) & (frame["date"] <= pd.Timestamp(end_date))].copy() if not frame.empty else frame
        rows.attrs.update(frame.attrs)
        return rows

    def _build_feature_frame_uncached(self, start_date: date, end_date: date) -> pd.DataFrame:
        fallback_frame = self.fallback_builder.build_feature_frame(start_date=start_date, end_date=end_date)
        fetch_start = start_date - timedelta(days=180)
        policy_items = self._load_policy_items(start_date=fetch_start, end_date=end_date)
        cny_mid_frame = self._fetch_china_money_cny_mid_series(start_date=fetch_start, end_date=end_date)
        brent_realtime = self._resolve_realtime_brent_value(end_date)
        if brent_realtime is not None:
            fallback_frame = self._override_brent_series_with_realtime(
                fallback_frame,
                as_of_date=end_date,
                brent_value=brent_realtime,
            )
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
        base["date"] = pd.to_datetime(base["date"])
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        base = base[(base["date"] >= start_ts) & (base["date"] <= end_ts)].copy()
        base = base.sort_values("date").reset_index(drop=True)
        base, archive_base_expand_count = self._expand_base_with_archived_sd_price(
            base=base,
            start_date=start_date,
            end_date=end_date,
        )
        if base.empty:
            return self._finalize_fallback_frame(
                fallback_frame=fallback_frame,
                policy_items=policy_items,
                mode="fallback_local_snapshot",
                reason="eta_empty_base_series",
            )
        base_forward_fill_count = 0
        base_price_anchor_date = None
        if not base.empty:
            base_price_anchor_date = pd.Timestamp(base["date"].max()).date().isoformat()
        if not base.empty and pd.Timestamp(base["date"].max()) < end_ts:
            latest_row = base.iloc[-1].copy()
            latest_row["date"] = end_ts
            base = pd.concat([base, latest_row.to_frame().T], ignore_index=True)
            base["date"] = pd.to_datetime(base["date"]).astype("datetime64[ns]")
            base = base.sort_values("date").reset_index(drop=True)
            base_forward_fill_count = 1

        for key, frame in series_map.items():
            if key == "sd_gas92_market" or frame.empty:
                continue
            tmp = frame[["date", "value"]].rename(columns={"value": key}).sort_values("date")
            tmp["date"] = pd.to_datetime(tmp["date"]).astype("datetime64[ns]")
            base = pd.merge_asof(base, tmp, on="date", direction="backward")

        missing_before_fill = sum(1 for key in eta_indicator_keys if key not in base.columns or base[key].isna().all())
        base = self._fill_missing_market_columns(
            base=base,
            fallback_frame=fallback_frame,
            indicator_keys=eta_indicator_keys,
        )
        if brent_realtime is not None and "brent_active_settlement" in base.columns:
            base.loc[base["date"] <= end_ts, "brent_active_settlement"] = float(brent_realtime)
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
        base = self._attach_cdu_utilization_weekly(base=base, end_date=end_date)
        base = self._attach_oilchem_openapi_inventory(base=base, end_date=end_date)
        base = self._attach_oilchem_inventory(base=base, end_date=end_date)
        base = self._forward_fill_market_inputs(base)
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
        if archive_base_expand_count:
            reason_parts.append(f"archive_price_base_expand={archive_base_expand_count}")
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
        result["date"] = pd.to_datetime(result["date"]).astype("datetime64[ns]")
        fx = cny_mid_frame[["date", "cny_mid_rate"]].copy()
        fx["date"] = pd.to_datetime(fx["date"]).astype("datetime64[ns]")
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
        product_code: str | None = None,
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
            {"key": "sd_diesel0_market", "label": "山东 0#柴油"},
            {"key": "cn_diesel0_market", "label": "全国 0#柴油"},
            {"key": "east_china_diesel0_market", "label": "华东 0#柴油"},
            {"key": "north_china_diesel0_market", "label": "华北 0#柴油"},
            {"key": "south_china_diesel0_market", "label": "华南 0#柴油"},
            {"key": "central_china_diesel0_market", "label": "华中 0#柴油"},
            {"key": "northwest_diesel0_market", "label": "西北 0#柴油"},
            {"key": "southwest_diesel0_market", "label": "西南 0#柴油"},
            {"key": "northeast_diesel0_market", "label": "东北 0#柴油"},
        ]
        label_map = {item["key"]: item["label"] for item in available_series}
        requested = [key for key in (series_keys or []) if key in label_map]
        normalized_product = str(product_code or "").upper()
        diesel_defaults = [
            "sd_diesel0_market",
            "cn_diesel0_market",
            "east_china_diesel0_market",
            "north_china_diesel0_market",
            "south_china_diesel0_market",
            "central_china_diesel0_market",
            "northwest_diesel0_market",
            "southwest_diesel0_market",
            "northeast_diesel0_market",
        ]
        gasoline_defaults = [
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
        if not requested:
            requested = diesel_defaults if normalized_product in {"DIESEL_0", "DIESEL", "0"} else gasoline_defaults
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        rows = self._load_price_history_rows_from_archive(
            requested=requested,
            start_date=start_date,
            end_date=end_date,
        )
        if rows.empty or any(key not in rows.columns or rows[key].dropna().empty for key in requested):
            rows = self._get_price_history_frame(start_date=start_date, end_date=end_date)
        if rows.empty:
            frame = pd.DataFrame(columns=["date"])
            rows = frame
        else:
            frame = rows
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
                "product_code": normalized_product or "GASOLINE_92",
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
        base["date"] = pd.to_datetime(base["date"]).astype("datetime64[ns]")
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
                    "date": pd.to_datetime([record["dt"] for record in rows]).astype("datetime64[ns]"),
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
            "shandong_main_gasoline_inventory",
            "shandong_major_company_inventory",
            "shandong_independent_refinery_inventory",
            "shandong_diesel_inventory",
            "shandong_main_company_diesel_inventory",
            "shandong_main_diesel_inventory",
            "shandong_independent_refinery_diesel_inventory",
            "shandong_refinery_diesel_inventory",
            *SHANDONG_INVENTORY_QUERY_KEYS,
            "shandong_diesel_inventory_change_mom",
            "shandong_diesel_inventory_capacity_rate",
            "price_adjustment_expected_yuan",
            "refined_oil_adjustment_expected_yuan",
            "oil_price_adjustment_forecast_yuan",
            "expected_price_adjustment_yuan_per_ton",
            "price_window_expected_adjustment",
            *CDU_UTILIZATION_INDICATOR_KEYS,
            *REGIONAL_SHIPMENTS_QUERY_KEYS,
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
            data["date"] = pd.to_datetime(data["dt"]).astype("datetime64[ns]")
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
        merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")
        merge_dates = merged[["date"]].sort_values("date")
        applied = 0
        for key in overlay_keys:
            aliases = REGIONAL_SHIPMENTS_SOURCE_ALIASES.get(key) or SHANDONG_INVENTORY_SOURCE_ALIASES.get(key) or (key,)
            source_column = next((alias for alias in aliases if alias in overlay_rows.columns), None)
            if source_column is None:
                continue
            series_frame = overlay_rows[["date", source_column]].rename(columns={source_column: key}).dropna(subset=[key]).copy()
            if series_frame.empty:
                continue
            series_frame = (
                series_frame.assign(date=pd.to_datetime(series_frame["date"]).astype("datetime64[ns]"))
                .sort_values("date")
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
            limit_per_source=120,
        )
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")

        def clean_metadata(value: Any, fallback: Any = None) -> Any:
            try:
                if value is None or pd.isna(value):
                    return fallback
            except (TypeError, ValueError):
                if value is None:
                    return fallback
            return value

        def build_ratio_frame(value_key: str, prefix: str) -> pd.DataFrame:
            rows = [
                {
                    "date": pd.Timestamp(record_date),
                    f"{prefix}_value": record.get(value_key),
                    f"{prefix}_observation_date": pd.Timestamp(record_date),
                    f"{prefix}_source": clean_metadata(
                        record.get("source"), clean_metadata(record.get("title"), "oilchem_production_sales_ratio")
                    ),
                    f"{prefix}_url": clean_metadata(record.get("url")),
                    f"{prefix}_publish_time": clean_metadata(record.get("publish_time")),
                }
                for record in records
                for record_date in [self._oilchem_record_date(record)]
                if record.get(value_key) is not None and record_date is not None and record_date <= end_date
            ]
            if not rows:
                return pd.DataFrame()
            frame = pd.DataFrame(rows)
            frame["date"] = pd.to_datetime(frame["date"]).astype("datetime64[ns]")
            frame[f"{prefix}_observation_date"] = pd.to_datetime(frame[f"{prefix}_observation_date"]).astype(
                "datetime64[ns]"
            )
            return frame.sort_values("date").groupby("date", as_index=False).last()

        def merge_ratio(value_key: str, target_column: str, prefix: str) -> None:
            nonlocal merged
            ratio_frame = build_ratio_frame(value_key=value_key, prefix=prefix)
            if ratio_frame.empty:
                return
            merged = pd.merge_asof(
                merged.sort_values("date"),
                ratio_frame,
                on="date",
                direction="backward",
            )
            value_column = f"{prefix}_value"
            if target_column in merged.columns:
                merged[target_column] = merged[value_column].combine_first(merged[target_column])
            else:
                merged[target_column] = merged[value_column]
            observation_column = f"{prefix}_observation_date"
            stale_column = f"{prefix}_stale_days"
            if observation_column in merged.columns:
                merged[stale_column] = (merged["date"] - merged[observation_column]).dt.days
            merged = merged.drop(columns=[value_column])

        merge_ratio(
            value_key="gasoline_ratio",
            target_column="sales_production_ratio_d1",
            prefix="gasoline_sales_production_ratio",
        )
        merge_ratio(
            value_key="diesel_ratio",
            target_column="diesel_sales_production_ratio_d1",
            prefix="diesel_sales_production_ratio",
        )
        metadata_pairs = [
            (
                "gasoline_sales_production_ratio",
                "sales_production_ratio",
            ),
            (
                "diesel_sales_production_ratio",
                "diesel_sales_production_ratio",
            ),
        ]
        for prefix, target_prefix in metadata_pairs:
            for suffix in ("source", "url", "publish_time", "observation_date", "stale_days"):
                source_column = f"{prefix}_{suffix}"
                target_column = f"{target_prefix}_{suffix}"
                if source_column not in merged.columns:
                    continue
                if target_column in merged.columns:
                    merged[target_column] = merged[source_column].combine_first(merged[target_column])
                else:
                    merged[target_column] = merged[source_column]
                if source_column != target_column:
                    merged = merged.drop(columns=[source_column])
        if "sales_production_ratio_observation_date" in merged.columns:
            merged["oilchem_production_sales_observation_date"] = merged["sales_production_ratio_observation_date"]
        if "sales_production_ratio_stale_days" in merged.columns:
            merged["oilchem_production_sales_stale_days"] = merged["sales_production_ratio_stale_days"]
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
        weekly_frame["date"] = pd.to_datetime(weekly_frame["date"]).astype("datetime64[ns]")
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")
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

    def _attach_cdu_utilization_weekly(self, base: pd.DataFrame, end_date: date) -> pd.DataFrame:
        if base.empty:
            return base
        archived = self._load_archived_cdu_utilization_weekly(end_date=end_date)
        if not archived.empty:
            return self._merge_cdu_utilization_weekly(base=base, weekly=archived)
        return self._attach_local_cdu_utilization_weekly(base=base, end_date=end_date)

    def _load_archived_cdu_utilization_weekly(self, end_date: date) -> pd.DataFrame:
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return pd.DataFrame()
        start_date = CDU_UTILIZATION_PERCENTILE_START
        merged_rows: dict[tuple[date, str], dict[str, Any]] = {}
        for source_code in ("ganglian_excel_import", "zhonglu_excel_archive"):
            try:
                rows = self.snapshot_repository.load_market_timeseries_values(
                    source_code=source_code,
                    indicator_codes=CDU_UTILIZATION_QUERY_KEYS,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                continue
            for row in rows:
                indicator_code = str(row.get("indicator_code") or "")
                value = row.get("value_num")
                dt_value = row.get("dt")
                target_code = next((target for target, aliases in CDU_UTILIZATION_SOURCE_ALIASES.items() if indicator_code in aliases), None)
                if target_code is None or value is None or dt_value is None:
                    continue
                try:
                    row_date = pd.Timestamp(dt_value).date()
                    numeric_value = float(value)
                except Exception:
                    continue
                key = (row_date, indicator_code)
                publish_time = row.get("publish_time")
                current = merged_rows.get(key)
                if current is None or str(publish_time or "") >= str(current.get("publish_time") or ""):
                    merged_rows[key] = {
                        "date": row_date,
                        "indicator_code": target_code,
                        "value": numeric_value,
                        "publish_time": publish_time,
                    }
        if not merged_rows:
            return pd.DataFrame()
        records: dict[date, dict[str, Any]] = {}
        for item in merged_rows.values():
            row_date = item["date"]
            record = records.setdefault(row_date, {"date": pd.Timestamp(row_date)})
            record[item["indicator_code"]] = item["value"]
            if item["indicator_code"] == "shandong_cdu_utilization_weekly":
                record["shandong_cdu_utilization_observation_date"] = pd.Timestamp(row_date)
                record["shandong_cdu_utilization_publish_time"] = item.get("publish_time")
        weekly = pd.DataFrame(records.values()).sort_values("date").reset_index(drop=True)
        if "shandong_cdu_utilization_weekly" in weekly.columns:
            weekly["shandong_cdu_utilization_weekly"] = pd.to_numeric(
                weekly["shandong_cdu_utilization_weekly"], errors="coerce"
            )
            weekly["sd_crude_run_weekly"] = weekly["shandong_cdu_utilization_weekly"]
            weekly["shandong_cdu_utilization_previous_value"] = weekly["shandong_cdu_utilization_weekly"].shift(1)
            weekly["shandong_cdu_utilization_previous_observation_date"] = weekly["date"].shift(1)
            weekly["shandong_cdu_utilization_wow_pct"] = weekly["shandong_cdu_utilization_weekly"].diff()
            weekly["shandong_cdu_utilization_observation_date"] = weekly["date"]
            weekly["shandong_cdu_utilization_percentile_weekly"] = self._expanding_percentile(
                weekly["shandong_cdu_utilization_weekly"],
                min_periods=5,
            )
        weekly["shandong_cdu_utilization_source"] = "ganglian_excel_import"
        return weekly

    def _merge_cdu_utilization_weekly(self, base: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
        if base.empty or weekly.empty:
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
            suffixes=("", "_cdu"),
        )
        merge_columns = [
            "sd_crude_run_weekly",
            "shandong_cdu_utilization_weekly",
            "shandong_cdu_utilization_wow_pct",
            "shandong_cdu_utilization_previous_value",
            "shandong_cdu_utilization_previous_observation_date",
            "shandong_cdu_utilization_percentile_weekly",
            "shandong_cdu_utilization_observation_date",
            "shandong_cdu_utilization_publish_time",
            *CDU_UTILIZATION_INDICATOR_KEYS,
        ]
        for column in dict.fromkeys(merge_columns):
            cdu_column = f"{column}_cdu"
            if cdu_column not in merged.columns:
                continue
            if column in {"shandong_cdu_utilization_observation_date", "shandong_cdu_utilization_publish_time"}:
                if column in merged.columns:
                    merged[column] = merged[cdu_column].combine_first(merged[column])
                else:
                    merged[column] = merged[cdu_column]
            elif column in merged.columns:
                merged[column] = pd.to_numeric(merged[cdu_column], errors="coerce").combine_first(
                    pd.to_numeric(merged[column], errors="coerce")
                )
            else:
                merged[column] = pd.to_numeric(merged[cdu_column], errors="coerce")
            merged = merged.drop(columns=[cdu_column])
        if "shandong_cdu_utilization_source_cdu" in merged.columns:
            merged["shandong_cdu_utilization_source"] = merged["shandong_cdu_utilization_source_cdu"].combine_first(
                merged["shandong_cdu_utilization_source"]
                if "shandong_cdu_utilization_source" in merged.columns
                else pd.Series(index=merged.index, dtype="object")
            )
            merged = merged.drop(columns=["shandong_cdu_utilization_source_cdu"])
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
            "shandong_cdu_utilization_previous_value_local_cdu": "shandong_cdu_utilization_previous_value",
            "shandong_cdu_utilization_previous_observation_date_local_cdu": "shandong_cdu_utilization_previous_observation_date",
            "shandong_cdu_utilization_percentile_weekly_local_cdu": "shandong_cdu_utilization_percentile_weekly",
            "shandong_cdu_utilization_observation_date_local_cdu": "shandong_cdu_utilization_observation_date",
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
        weekly.columns = ["date", "shandong_cdu_utilization_weekly"]
        weekly["date"] = pd.to_datetime(weekly["date"], errors="coerce")
        weekly["shandong_cdu_utilization_weekly"] = pd.to_numeric(
            weekly["shandong_cdu_utilization_weekly"], errors="coerce"
        )
        weekly = weekly.dropna(subset=["date", "shandong_cdu_utilization_weekly"])
        weekly["sd_crude_run_weekly"] = weekly["shandong_cdu_utilization_weekly"]
        if weekly.empty:
            return pd.DataFrame()
        weekly = weekly[
            (weekly["date"].dt.date >= CDU_UTILIZATION_PERCENTILE_START)
            & (weekly["date"].dt.date <= end_date)
        ].copy()
        if weekly.empty:
            return pd.DataFrame()
        weekly = weekly.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        weekly["shandong_cdu_utilization_previous_value"] = weekly["shandong_cdu_utilization_weekly"].shift(1)
        weekly["shandong_cdu_utilization_previous_observation_date"] = weekly["date"].shift(1)
        weekly["shandong_cdu_utilization_wow_pct"] = weekly["shandong_cdu_utilization_weekly"].diff()
        weekly["shandong_cdu_utilization_observation_date"] = weekly["date"]
        weekly["shandong_cdu_utilization_percentile_weekly"] = self._expanding_percentile(
            weekly["shandong_cdu_utilization_weekly"],
            min_periods=5,
        )
        weekly["shandong_cdu_utilization_source"] = "local_zhonglu_weekly_cdu_utilization"
        return weekly

    def _attach_oilchem_openapi_inventory(self, base: pd.DataFrame, end_date: date) -> pd.DataFrame:
        if base.empty or not self.snapshot_repository or not self.snapshot_repository.enabled:
            return base
        start_date = pd.to_datetime(base["date"]).min().date() if "date" in base.columns else end_date - timedelta(days=180)
        try:
            rows = self.snapshot_repository.load_oilchem_openapi_inventory_records(
                start_date=start_date,
                end_date=end_date,
            )
        except Exception:
            return base
        if not rows:
            return base

        mapped_rows: list[dict[str, Any]] = []
        for row in rows:
            dt_value = row.get("dt")
            record_date = dt_value if isinstance(dt_value, date) else None
            if record_date is None:
                try:
                    record_date = pd.Timestamp(dt_value).date()
                except Exception:
                    continue
            project_id = row.get("project_quota_id")
            entity_name = str(row.get("entity_name") or "")
            source_record_id = str(row.get("source_record_id") or "")
            entity_code = str(row.get("entity_code") or "")
            is_shandong_sample = (
                "山东" in entity_name
                or ":204456:" in source_record_id
                or ":204453:" in source_record_id
                or entity_code.endswith("010304")
            )
            value = row.get("value")
            if value is None:
                continue
            payload: dict[str, Any] = {"date": pd.Timestamp(record_date)}
            try:
                project_id_int = int(project_id)
            except Exception:
                continue
            if project_id_int == 12887 and is_shandong_sample:
                payload["shandong_main_company_inventory"] = value
                payload["shandong_main_gasoline_inventory"] = value
            elif project_id_int == 12891 and is_shandong_sample:
                payload["shandong_main_company_diesel_inventory"] = value
                payload["shandong_main_diesel_inventory"] = value
            elif project_id_int in {12975, 12944} and is_shandong_sample:
                payload["shandong_trader_inventory"] = value
            elif project_id_int in {12981, 12945} and is_shandong_sample:
                payload["shandong_diesel_trader_inventory"] = value
            else:
                continue
            mapped_rows.append(payload)
        if not mapped_rows:
            return base

        inventory_frame = pd.DataFrame(mapped_rows).sort_values("date").groupby("date", as_index=False).last()
        inventory_frame["date"] = pd.to_datetime(inventory_frame["date"]).astype("datetime64[ns]")
        value_columns = [column for column in inventory_frame.columns if column != "date"]
        inventory_frame = inventory_frame.rename(columns={column: f"__openapi_{column}" for column in value_columns})
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")
        merged = pd.merge_asof(merged.sort_values("date"), inventory_frame, on="date", direction="backward")
        for column in value_columns:
            openapi_column = f"__openapi_{column}"
            if openapi_column not in merged.columns:
                continue
            if column in merged.columns:
                merged[column] = merged[openapi_column].combine_first(merged[column])
            else:
                merged[column] = merged[openapi_column]
            merged = merged.drop(columns=[openapi_column])
        return merged

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
                "oilchem_shandong_refinery_total_inventory": record.get("total_inventory"),
                "oilchem_shandong_refinery_gasoline_inventory": record.get("gasoline_inventory"),
                "shandong_gasoline_inventory_change_mom": record.get("gasoline_inventory_change_mom"),
                "shandong_gasoline_inventory_capacity_rate": record.get("gasoline_inventory_capacity_rate"),
                "oilchem_shandong_refinery_diesel_inventory": record.get("diesel_inventory"),
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

        value_columns = [
            "oilchem_shandong_refinery_total_inventory",
            "oilchem_shandong_refinery_gasoline_inventory",
            "shandong_gasoline_inventory_change_mom",
            "shandong_gasoline_inventory_capacity_rate",
            "oilchem_shandong_refinery_diesel_inventory",
            "shandong_diesel_inventory_change_mom",
            "shandong_diesel_inventory_capacity_rate",
            "oilchem_inventory_source",
            "oilchem_inventory_url",
            "oilchem_inventory_publish_time",
        ]
        inventory_frame = pd.DataFrame(rows).sort_values("date").groupby("date", as_index=False).first()
        inventory_frame["date"] = pd.to_datetime(inventory_frame["date"]).astype("datetime64[ns]")
        inventory_frame = inventory_frame.rename(
            columns={column: f"__oilchem_{column}" for column in value_columns if column in inventory_frame.columns}
        )
        merged = base.copy()
        merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")
        merged = pd.merge_asof(
            merged.sort_values("date"),
            inventory_frame,
            on="date",
            direction="backward",
        )
        for column in value_columns:
            oilchem_column = f"__oilchem_{column}"
            if oilchem_column not in merged.columns:
                continue
            if column in merged.columns:
                merged[column] = merged[oilchem_column].combine_first(merged[column])
            else:
                merged[column] = merged[oilchem_column]
            merged = merged.drop(columns=[oilchem_column])
        return merged

    def _load_oilchem_maintenance_plan(self, as_of_date: date) -> dict[str, Any] | None:
        records = self._load_archived_oilchem_records(
            source_codes=[
                "oilchem_local_refinery_maintenance_plan",
                "oilchem_main_refinery_maintenance_plan",
            ],
            end_date=as_of_date,
            limit_per_source=5,
        )
        valid_records = [
            record for record in records if (self._oilchem_record_date(record) or date.max) <= as_of_date
        ]
        if not valid_records:
            return None
        return self._aggregate_maintenance_plan(records=valid_records, as_of_date=as_of_date, target_region="山东")

    def _aggregate_maintenance_plan(
        self,
        *,
        records: list[dict[str, Any]],
        as_of_date: date,
        target_region: str,
    ) -> dict[str, Any]:
        latest_records = self._latest_maintenance_records_by_source(records)
        latest_date = max((self._oilchem_record_date(record) or date.min for record in latest_records), default=None)
        if latest_date == date.min:
            latest_date = None
        current_month_start = date(as_of_date.year, as_of_date.month, 1)
        current_month_end = date(as_of_date.year, as_of_date.month, self._days_in_month(as_of_date.year, as_of_date.month))
        target_month_start = self._first_day_of_next_month(as_of_date)
        target_month_end = date(target_month_start.year, target_month_start.month, self._days_in_month(target_month_start.year, target_month_start.month))
        horizon_windows = {
            "d1": (as_of_date + timedelta(days=1), as_of_date + timedelta(days=1)),
            "d3": (as_of_date + timedelta(days=1), as_of_date + timedelta(days=3)),
            "w1": (as_of_date + timedelta(days=1), as_of_date + timedelta(days=7)),
            "m": (current_month_start, current_month_end),
            "m1": (target_month_start, target_month_end),
            "next_30d": (as_of_date + timedelta(days=1), as_of_date + timedelta(days=30)),
        }
        rows: list[dict[str, Any]] = []
        for record in latest_records:
            source = str(record.get("source_code") or record.get("source") or "")
            record_date = self._oilchem_record_date(record)
            for row in record.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                enriched = dict(row)
                enriched["source"] = source
                enriched["observation_date"] = record_date.isoformat() if record_date else None
                enriched["region"] = self._maintenance_row_region(row=row, source=source)
                rows.append(enriched)

        target_rows = [row for row in rows if self._maintenance_row_matches_target(row, target_region=target_region)]
        active_rows = [row for row in target_rows if row.get("active")]

        def summarize(window_key: str) -> dict[str, Any]:
            start_date, end_date = horizon_windows[window_key]
            start_rows: list[dict[str, Any]] = []
            end_rows: list[dict[str, Any]] = []
            active_rows_in_window: list[dict[str, Any]] = []
            start_effective_rows: list[dict[str, Any]] = []
            restart_effective_rows: list[dict[str, Any]] = []
            for row in target_rows:
                row_start = self._parse_iso_date(row.get("start_date"))
                row_end = self._parse_iso_date(row.get("end_date"))
                if row_start and start_date <= row_start <= end_date:
                    start_rows.append(row)
                if row_end and start_date <= row_end <= end_date:
                    end_rows.append(row)
                if self._maintenance_row_active_in_window(row_start=row_start, row_end=row_end, window_start=start_date, window_end=end_date):
                    active_rows_in_window.append(row)
                start_effective = self._maintenance_effective_shutdown_capacity(row=row, row_start=row_start, row_end=row_end, month_start=start_date, month_end=end_date)
                if start_effective > 0:
                    enriched_start = dict(row)
                    enriched_start["effective_capacity"] = round(start_effective, 4)
                    enriched_start["effective_days"] = self._maintenance_shutdown_days(row_start=row_start, row_end=row_end, month_start=start_date, month_end=end_date)
                    start_effective_rows.append(enriched_start)
                restart_effective = self._maintenance_effective_restart_capacity(row=row, row_start=row_start, row_end=row_end, month_start=start_date, month_end=end_date)
                if restart_effective > 0:
                    enriched_restart = dict(row)
                    enriched_restart["effective_capacity"] = round(restart_effective, 4)
                    enriched_restart["effective_days"] = self._maintenance_restart_days(row_end=row_end, month_start=start_date, month_end=end_date)
                    restart_effective_rows.append(enriched_restart)
            active_capacity = round(sum(self._safe_float(row.get("capacity")) or 0.0 for row in active_rows_in_window), 4)
            start_effective_capacity = round(sum(self._safe_float(row.get("effective_capacity")) or 0.0 for row in start_effective_rows), 4)
            restart_effective_capacity = round(sum(self._safe_float(row.get("effective_capacity")) or 0.0 for row in restart_effective_rows), 4)
            return {
                "start_capacity": round(sum(self._safe_float(row.get("capacity")) or 0.0 for row in start_rows), 4),
                "start_count": len(start_rows),
                "end_capacity": round(sum(self._safe_float(row.get("capacity")) or 0.0 for row in end_rows), 4),
                "end_count": len(end_rows),
                "active_capacity": active_capacity,
                "active_count": len(active_rows_in_window),
                "effective_shutdown_capacity": start_effective_capacity,
                "effective_restart_capacity": restart_effective_capacity,
                "net_effective_capacity": round(start_effective_capacity - restart_effective_capacity, 4),
                "effective_shutdown_rows": start_effective_rows[:20],
                "effective_restart_rows": restart_effective_rows[:20],
                "active_rows": active_rows_in_window[:20],
                "start_rows": start_rows[:20],
                "end_rows": end_rows[:20],
                "window_start": start_date.isoformat(),
                "window_end": end_date.isoformat(),
            }

        d1 = summarize("d1")
        d3 = summarize("d3")
        w1 = summarize("w1")
        current_month = summarize("m")
        m1 = summarize("m1")
        next_30d = summarize("next_30d")
        m1_effective_capacity_delta = round(m1["net_effective_capacity"] - current_month["net_effective_capacity"], 4)
        m1_effective_capacity_label = "stable_load"
        if m1_effective_capacity_delta > 1e-6:
            m1_effective_capacity_label = "concentrated_maintenance_supply_tight"
        elif m1_effective_capacity_delta < -1e-6:
            m1_effective_capacity_label = "restart_and_supply_surplus"
        return {
            "observation_date": latest_date.isoformat() if latest_date else None,
            "title": "\u5730\u65b9\u70bc\u5382\u68c0\u4fee\u8ba1\u5212\u8868 + \u4e3b\u8425\u70bc\u5382\u68c0\u4fee\u8ba1\u5212\u8868",
            "source": "oilchem_local_and_main_refinery_maintenance_plan",
            "target_region": target_region,
            "region_rule": "\u5730\u65b9\u70bc\u5382\u6309\u8868\u5185\u533a\u57df/\u6240\u5728\u5730\u8bc6\u522b\uff1b\u4e3b\u8425\u70bc\u5382\u6309\u7701\u4efd\u6620\u5c04\u5230\u534e\u4e1c\u3001\u534e\u5357\u3001\u534e\u5317\u3001\u534e\u4e2d\u3001\u897f\u5317\u3001\u4e1c\u5317\u3001\u897f\u5357\u3002",
            "active_capacity": round(sum(self._safe_float(row.get("capacity")) or 0.0 for row in active_rows), 4),
            "active_count": len(active_rows),
            "next_30d_start_capacity": next_30d["start_capacity"],
            "next_30d_start_count": next_30d["start_count"],
            "next_30d_end_capacity": next_30d["end_capacity"],
            "next_30d_end_count": next_30d["end_count"],
            "d1_start_capacity": d1["start_capacity"],
            "d1_start_count": d1["start_count"],
            "d1_end_capacity": d1["end_capacity"],
            "d1_end_count": d1["end_count"],
            "d1_active_capacity": d1["active_capacity"],
            "d1_active_count": d1["active_count"],
            "d3_start_capacity": d3["start_capacity"],
            "d3_start_count": d3["start_count"],
            "d3_end_capacity": d3["end_capacity"],
            "d3_end_count": d3["end_count"],
            "d3_active_capacity": d3["active_capacity"],
            "d3_active_count": d3["active_count"],
            "w1_start_capacity": w1["start_capacity"],
            "w1_start_count": w1["start_count"],
            "w1_end_capacity": w1["end_capacity"],
            "w1_end_count": w1["end_count"],
            "w1_active_capacity": w1["active_capacity"],
            "w1_active_count": w1["active_count"],
            "m_effective_shutdown_capacity": current_month["effective_shutdown_capacity"],
            "m_effective_restart_capacity": current_month["effective_restart_capacity"],
            "m_net_effective_capacity": current_month["net_effective_capacity"],
            "m_window_start": current_month["window_start"],
            "m_window_end": current_month["window_end"],
            "m1_start_capacity": m1["start_capacity"],
            "m1_start_count": m1["start_count"],
            "m1_end_capacity": m1["end_capacity"],
            "m1_end_count": m1["end_count"],
            "m1_active_capacity": m1["active_capacity"],
            "m1_active_count": m1["active_count"],
            "m1_effective_shutdown_capacity": m1["effective_shutdown_capacity"],
            "m1_effective_restart_capacity": m1["effective_restart_capacity"],
            "m1_net_effective_capacity": m1["net_effective_capacity"],
            "m1_effective_capacity_delta": m1_effective_capacity_delta,
            "m1_effective_capacity_label": m1_effective_capacity_label,
            "d1_rows": {"start": d1["start_rows"], "end": d1["end_rows"], "active": d1["active_rows"]},
            "d3_rows": {"start": d3["start_rows"], "end": d3["end_rows"], "active": d3["active_rows"]},
            "w1_rows": {"start": w1["start_rows"], "end": w1["end_rows"], "active": w1["active_rows"]},
            "m_rows": {"shutdown_effective": current_month["effective_shutdown_rows"], "restart_effective": current_month["effective_restart_rows"], "active": current_month["active_rows"]},
            "m1_rows": {"start": m1["start_rows"], "end": m1["end_rows"], "active": m1["active_rows"], "shutdown_effective": m1["effective_shutdown_rows"], "restart_effective": m1["effective_restart_rows"]},
            "m1_rule": "\u9884\u6d4bM+1\u65f6\uff0c\u5148\u6309\u88c5\u7f6e\u4ea7\u80fd/365*\u6708\u5185\u68c0\u4fee\u5929\u6570\u8ba1\u7b97\u5f00\u59cb\u68c0\u4fee\u6709\u6548\u4ea7\u80fd\uff0c\u518d\u6309\u88c5\u7f6e\u4ea7\u80fd/365*\u6708\u5185\u5f00\u5de5\u5929\u6570\u8ba1\u7b97\u590d\u5de5\u6709\u6548\u4ea7\u80fd\uff1bM+1\u6700\u7ec8\u6709\u6548\u4ea7\u80fd=\u5f00\u59cb\u68c0\u4fee\u6709\u6548\u4ea7\u80fd-\u590d\u5de5\u6709\u6548\u4ea7\u80fd\uff0c\u4e0eM\u6700\u7ec8\u6709\u6548\u4ea7\u80fd\u6bd4\u8f83\uff1aM+1\u5927\u4e8eM\u5f9715\u5206\uff0c\u65e0\u660e\u663e\u53d8\u53160\u5206\uff0cM+1\u5c0f\u4e8eM\u5f97-15\u5206\u3002",
            "rows": target_rows[:60],
        }

    def _latest_maintenance_records_by_source(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for record in records:
            source = str(record.get("source_code") or record.get("source") or "")
            group_key = "main" if source == "oilchem_main_refinery_maintenance_plan" else "local"
            current = grouped.get(group_key)
            record_date = self._oilchem_record_date(record) or date.min
            current_date = self._oilchem_record_date(current) if current else None
            if current is None or record_date > (current_date or date.min):
                grouped[group_key] = record
        return sorted(grouped.values(), key=lambda item: self._oilchem_record_date(item) or date.min, reverse=True)

    def _maintenance_row_region(self, *, row: dict[str, Any], source: str) -> str | None:
        if source == "oilchem_refinery_maintenance_plan":
            return "山东"
        text = " ".join(str(row.get(key) or "") for key in ("region", "location", "refinery"))
        for region in MAINTENANCE_REGION_PROVINCES:
            if region in text:
                return region
        for province, region in PROVINCE_TO_MAINTENANCE_REGION.items():
            if province in text:
                return region
        return None

    def _maintenance_row_matches_target(self, row: dict[str, Any], *, target_region: str) -> bool:
        text = " ".join(str(row.get(key) or "") for key in ("region", "location", "refinery"))
        if row.get("region") == target_region:
            return True
        if target_region in text:
            return True
        return False

    def _maintenance_shutdown_days(
        self,
        *,
        row_start: date | None,
        row_end: date | None,
        month_start: date,
        month_end: date,
    ) -> int:
        if row_start is None:
            return 0
        effective_start = max(row_start, month_start)
        effective_end = min(row_end or month_end, month_end)
        if effective_end < effective_start:
            return 0
        return (effective_end - effective_start).days + 1

    def _maintenance_restart_days(
        self,
        *,
        row_end: date | None,
        month_start: date,
        month_end: date,
    ) -> int:
        if row_end is None or row_end < month_start or row_end > month_end:
            return 0
        restart_start = row_end + timedelta(days=1)
        if restart_start > month_end:
            return 0
        return (month_end - restart_start).days + 1

    def _maintenance_effective_shutdown_capacity(
        self,
        *,
        row: dict[str, Any],
        row_start: date | None,
        row_end: date | None,
        month_start: date,
        month_end: date,
    ) -> float:
        capacity = self._safe_float(row.get("capacity")) or 0.0
        days = self._maintenance_shutdown_days(row_start=row_start, row_end=row_end, month_start=month_start, month_end=month_end)
        return capacity / 365.0 * days

    def _maintenance_effective_restart_capacity(
        self,
        *,
        row: dict[str, Any],
        row_start: date | None,
        row_end: date | None,
        month_start: date,
        month_end: date,
    ) -> float:
        capacity = self._safe_float(row.get("capacity")) or 0.0
        days = self._maintenance_restart_days(row_end=row_end, month_start=month_start, month_end=month_end)
        return capacity / 365.0 * days

    def _maintenance_row_active_in_window(
        self,
        *,
        row_start: date | None,
        row_end: date | None,
        window_start: date,
        window_end: date,
    ) -> bool:
        if row_start is None:
            return False
        effective_end = row_end or date.max
        return row_start <= window_end and effective_end >= window_start

    def _parse_iso_date(self, value: Any) -> date | None:
        if value in (None, ""):
            return None
        try:
            return pd.Timestamp(value).date()
        except Exception:
            return None

    def _safe_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _first_day_of_next_month(self, value: date) -> date:
        if value.month == 12:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)

    def _add_months(self, value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, self._days_in_month(year, month))
        return date(year, month, day)

    def _days_in_month(self, year: int, month: int) -> int:
        if month == 12:
            return 31
        return (date(year, month + 1, 1) - timedelta(days=1)).day

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
        frame_start_date = pd.to_datetime(frame["date"]).min().date() if not frame.empty else frame_end_date
        frame, archive_base_expand_count = self._expand_base_with_archived_sd_price(
            base=frame,
            start_date=frame_start_date,
            end_date=frame_end_date,
        )
        frame_start_date = pd.to_datetime(frame["date"]).min().date() if not frame.empty else frame_end_date
        frame_end_date = pd.to_datetime(frame["date"]).max().date() if not frame.empty else frame_end_date
        manual_override_count = self._apply_manual_market_overrides(
            base=frame,
            start_date=frame_start_date,
            end_date=frame_end_date,
            indicator_codes=[*INDICATOR_KEYS, *MANUAL_EXTRA_INDICATOR_KEYS],
        )
        local_factor_overlay_count = self._attach_local_market_factor_overlay(
            base=frame,
            start_date=frame_start_date,
            end_date=frame_end_date,
        )
        cash_price_overlay_count, cash_price_anchor_date = self._apply_preferred_cash_price_asof_overrides(
            base=frame,
            start_date=frame_start_date,
            end_date=frame_end_date,
        )
        frame = self._attach_oilchem_production_sales_ratio(base=frame, end_date=frame_end_date)
        frame = self._attach_oilchem_weekly_metrics(base=frame, end_date=frame_end_date)
        frame = self._attach_cdu_utilization_weekly(base=frame, end_date=frame_end_date)
        frame = self._attach_oilchem_openapi_inventory(base=frame, end_date=frame_end_date)
        frame = self._attach_oilchem_inventory(base=frame, end_date=frame_end_date)
        frame = self._forward_fill_market_inputs(frame)
        frame = self._compute_features(frame, policy_items=policy_items)
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        frame.attrs["market_data_mode"] = mode
        reason_parts = [reason]
        if manual_override_count:
            reason_parts.append(f"local_market_overrides={manual_override_count}")
        if local_factor_overlay_count:
            reason_parts.append(f"local_factor_overlay={local_factor_overlay_count}")
        if cash_price_overlay_count:
            reason_parts.append(f"cash_price_overlay={cash_price_overlay_count}")
        if archive_base_expand_count:
            reason_parts.append(f"archive_price_base_expand={archive_base_expand_count}")
        frame.attrs["market_data_reason"] = ";".join(reason_parts)
        frame.attrs["price_anchor_date"] = cash_price_anchor_date
        return frame

    def _resolve_realtime_brent_value(self, as_of_date: date) -> float | None:
        wind_payload = self._fetch_wind_brent_price()
        if wind_payload:
            value = self._safe_float(wind_payload.get("rt_latest"))
            if value is not None and value > 0:
                return value
        report_payload = self._load_report_payload(as_of_date)
        signals = report_payload.get("signals") if isinstance(report_payload, dict) else None
        value = self._safe_float((signals or {}).get("brent_settlement"))
        if value is not None and value > 0:
            return value
        value = self._fetch_eta_latest_value("brent_active_settlement", as_of_date)
        if value is not None and value > 0:
            return value
        return None

    def _override_brent_series_with_realtime(
        self,
        frame: pd.DataFrame,
        *,
        as_of_date: date,
        brent_value: float,
    ) -> pd.DataFrame:
        if frame.empty or "date" not in frame.columns:
            return frame
        next_frame = frame.copy()
        dates = pd.to_datetime(next_frame["date"], errors="coerce").dt.date
        next_frame.loc[dates <= as_of_date, "brent_active_settlement"] = float(brent_value)
        next_frame.attrs.update(frame.attrs)
        return next_frame

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
        if self.sci99_refinery_dynamic_client is not None:
            try:
                secondary_items.extend(self.sci99_refinery_dynamic_client.fetch_recent(limit=10))
            except Exception:
                pass
        primary_items = [item for item in primary_items if self._is_news_item_available_by_cutoff(item, as_of_date)]
        secondary_items = [item for item in secondary_items if self._is_news_item_available_by_cutoff(item, as_of_date)]
        merged = self._merge_refined_news_items(
            primary_items=primary_items,
            secondary_items=secondary_items,
            total_limit=36,
        )
        return [self._annotate_refinery_dynamic_item(item) for item in merged]

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
        self._fill_oilchem_ratio_from_timeseries(oilchem_metrics=oilchem_metrics, as_of_date=as_of_date)
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

    def _fill_oilchem_ratio_from_timeseries(self, *, oilchem_metrics: dict[str, Any], as_of_date: date) -> None:
        ratio = oilchem_metrics.get("production_sales_ratio")
        if not isinstance(ratio, dict):
            ratio = {}
            oilchem_metrics["production_sales_ratio"] = ratio
        needs_gasoline = ratio.get("gasoline_ratio") is None
        needs_diesel = ratio.get("diesel_ratio") is None
        if not needs_gasoline and not needs_diesel:
            return
        if not self.snapshot_repository or not self.snapshot_repository.enabled:
            return
        indicator_map = {
            "oilchem_sd_gasoline_production_sales_ratio": "gasoline_ratio",
            "oilchem_sd_diesel_production_sales_ratio": "diesel_ratio",
        }
        try:
            rows = self.snapshot_repository.load_market_timeseries_values(
                source_code="oilchem_production_sales_ratio",
                indicator_codes=list(indicator_map.keys()),
                start_date=as_of_date - timedelta(days=120),
                end_date=as_of_date,
            )
        except Exception:
            return
        latest_by_field: dict[str, dict[str, Any]] = {}
        for row in rows:
            field = indicator_map.get(str(row.get("indicator_code") or ""))
            row_date = row.get("dt")
            value = self._safe_float(row.get("value_num"))
            if not field or row_date is None or value is None:
                continue
            current = latest_by_field.get(field)
            if current is None or row_date > current.get("dt"):
                latest_by_field[field] = {"dt": row_date, "value": value}
        for field, item in latest_by_field.items():
            if ratio.get(field) is None:
                ratio[field] = round(float(item["value"]), 4)
        latest_dates = [item.get("dt") for item in latest_by_field.values() if item.get("dt") is not None]
        if latest_dates and not ratio.get("observation_date"):
            ratio["observation_date"] = max(latest_dates).isoformat()

    def _fill_oilchem_ratio_from_feature_frame(self, *, oilchem_metrics: dict[str, Any], as_of_date: date) -> None:
        ratio = oilchem_metrics.get("production_sales_ratio")
        if not isinstance(ratio, dict):
            ratio = {}
            oilchem_metrics["production_sales_ratio"] = ratio
        needs_gasoline = ratio.get("gasoline_ratio") is None
        needs_diesel = ratio.get("diesel_ratio") is None
        if not needs_gasoline and not needs_diesel:
            return
        try:
            frame = self.build_feature_frame(start_date=as_of_date - timedelta(days=35), end_date=as_of_date)
            frame_dates = pd.to_datetime(frame["date"], errors="coerce").dt.date
            current_frame = frame[frame_dates <= as_of_date]
            if current_frame.empty:
                return
            row = current_frame.iloc[-1]
        except Exception:
            return
        if needs_gasoline:
            value = self._safe_float(row.get("sales_production_ratio_d1"))
            if value is not None:
                ratio["gasoline_ratio"] = round(value, 4)
        if needs_diesel:
            value = self._safe_float(row.get("diesel_sales_production_ratio_d1"))
            if value is not None:
                ratio["diesel_ratio"] = round(value, 4)
        if not ratio.get("observation_date"):
            try:
                ratio["observation_date"] = pd.Timestamp(row.get("date")).date().isoformat()
            except Exception:
                ratio["observation_date"] = as_of_date.isoformat()

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
                    "oilchem_local_refinery_maintenance_plan",
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
        maintenance_items = (archived.get("oilchem_local_refinery_maintenance_plan") or []) or (archived.get("oilchem_refinery_maintenance_plan") or [])
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


    def refresh_sci99_price_adjustment_archive(self, *, as_of_date: date) -> dict[str, Any]:
        value = self._fetch_sci99_price_adjustment_expected_yuan()
        if value is None:
            return {
                "as_of_date": as_of_date.isoformat(),
                "status": "failed",
                "reason": "sci99_price_adjustment_unavailable",
                "saved_rows": 0,
            }
        saved_rows = self._persist_latest_price_snapshot(
            snapshot_date=as_of_date,
            latest_prices={"price_adjustment_expected_yuan": value},
            mode="sci99_refined_oil_price_adjustment",
            reason="\u5353\u521b\u8c03\u4ef7\u9884\u671f\u6293\u53d6",
        )
        return {
            "as_of_date": as_of_date.isoformat(),
            "status": "ok",
            "price_adjustment_expected_yuan": value,
            "saved_rows": saved_rows,
            "source": SCI99_REFINED_OIL_URL,
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

    def refresh_refined_news_archive(self, as_of_date: date) -> dict[str, Any]:
        if not self.refined_news_scraping_enabled:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "refined_news_scraping_disabled",
                "fetched_count": 0,
                "saved_refined_news_count": 0,
            }
        refined_news_items = self._load_refined_news_items(as_of_date=as_of_date, prefer_archive=False)
        saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled and refined_news_items:
            try:
                saved_count = self.snapshot_repository.save_refined_news_items(
                    snapshot_date=as_of_date,
                    items=refined_news_items,
                )
            except Exception:
                saved_count = 0
        self._context_cache.clear()
        return {
            "as_of_date": as_of_date,
            "status": "ok",
            "fetched_count": len(refined_news_items),
            "saved_refined_news_count": saved_count,
            "sources": sorted({str(item.get("source") or "unknown") for item in refined_news_items}),
        }

    def refresh_policy_event_archive(self, as_of_date: date) -> dict[str, Any]:
        report_payload = self._load_report_payload(as_of_date=as_of_date)
        news_items = self._load_event_news_items(as_of_date=as_of_date, prefer_archive=False)
        refined_news_items = self._load_refined_news_items(as_of_date=as_of_date, prefer_archive=True)
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
                "weekly_fetched_count": 0,
                "weekly_saved_timeseries_count": 0,
            }
        errors: dict[str, str] = {}
        try:
            weekly_records = self.oilchem_production_sales_client.fetch_weekly_metrics(limit=5)
        except Exception as exc:
            errors["weekly_metrics"] = str(exc)
            weekly_records = []
        weekly_payloads = [record.model_dump() for record in weekly_records]
        weekly_saved_count = 0
        if self.snapshot_repository and self.snapshot_repository.enabled and weekly_payloads:
            try:
                weekly_saved_count = self.snapshot_repository.save_oilchem_weekly_metric_records(weekly_payloads)
            except Exception as exc:
                return {
                    "as_of_date": as_of_date,
                    "status": "db_failed",
                    "reason": str(exc),
                    "weekly_fetched_count": len(weekly_payloads),
                    "weekly_saved_timeseries_count": 0,
                }
        latest_weekly = weekly_payloads[0] if weekly_payloads else None
        self._context_cache.clear()
        self._feature_frame_cache.clear()
        self._price_history_frame_cache.clear()
        return {
            "as_of_date": as_of_date,
            "status": "ok" if not errors else "partial" if weekly_payloads else "failed",
            "errors": errors,
            "weekly_fetched_count": len(weekly_payloads),
            "weekly_saved_timeseries_count": weekly_saved_count,
            "latest_weekly_observation_date": latest_weekly.get("observation_date") if latest_weekly else None,
            "latest_weekly_metric_type": latest_weekly.get("metric_type") if latest_weekly else None,
            "note": "oilchem_daily_fetch now only refreshes weekly operating metrics; production-sales, maintenance and inventory are handled by dedicated jobs.",
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
        self._price_history_frame_cache.clear()
        return {
            "as_of_date": as_of_date,
            "status": "ok" if payloads else "empty",
            "fetched_count": len(payloads),
            "saved_timeseries_count": saved_count,
            "latest_observation_date": max((item["observation_date"] for item in payloads), default=None),
            "gasoline_count": sum(1 for item in payloads if item.get("product_code") == "gasoline92"),
            "diesel_count": sum(1 for item in payloads if item.get("product_code") == "diesel0"),
        }

    def refresh_competitor_price_archive(self, as_of_date: date) -> dict[str, Any]:
        if self.competitor_price_client is None:
            return {
                "as_of_date": as_of_date,
                "status": "disabled",
                "reason": "competitor_price_client_missing",
                "fetched_count": 0,
                "saved_timeseries_count": 0,
            }
        try:
            records = self.competitor_price_client.fetch_day(as_of_date)
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
                saved_count = self.snapshot_repository.save_competitor_market_price_records(payloads)
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
        self._price_history_frame_cache.clear()
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
        self._price_history_frame_cache.clear()
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
                    saved_count = self.snapshot_repository.save_oilchem_maintenance_plan_records(
                        payloads,
                        source_code="oilchem_local_refinery_maintenance_plan",
                        entity_code="LOCAL_REFINERY",
                        entity_name="地方炼厂",
                        indicator_prefix="oilchem_local_maintenance",
                    )
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
        self._price_history_frame_cache.clear()
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
            self._enrich_latest_price_formula_values(latest_prices=fallback_prices, as_of_date=as_of_date)
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
        self._enrich_latest_price_formula_values(latest_prices=latest_prices, as_of_date=as_of_date)
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

    def _enrich_latest_price_formula_values(self, *, latest_prices: dict[str, float | None], as_of_date: date) -> None:
        cny_mid = latest_prices.get("cny_mid_rate")
        if cny_mid is None:
            cny_mid_frame = self._fetch_china_money_cny_mid_series(
                start_date=as_of_date - timedelta(days=10),
                end_date=as_of_date,
            )
            if not cny_mid_frame.empty:
                dated_rows = cny_mid_frame[pd.to_datetime(cny_mid_frame["date"]).dt.date <= as_of_date]
                if not dated_rows.empty:
                    cny_mid = self._round_or_none(dated_rows.sort_values("date").iloc[-1].get("cny_mid_rate"), digits=4)
                    latest_prices["cny_mid_rate"] = cny_mid
        brent = latest_prices.get("brent_active_settlement")
        gas_crack = self._calculate_latest_crack_value(
            market_price=latest_prices.get("sd_gas92_market"),
            brent_price=brent,
            cny_mid=cny_mid,
            consumption_tax=GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON,
        )
        if gas_crack is not None:
            latest_prices["sd_gas_crack"] = gas_crack
        diesel_crack = self._calculate_latest_crack_value(
            market_price=latest_prices.get("sd_diesel0_market"),
            brent_price=brent,
            cny_mid=cny_mid,
            consumption_tax=DIESEL_CONSUMPTION_TAX_YUAN_PER_TON,
        )
        if diesel_crack is not None:
            latest_prices["sd_diesel_crack"] = diesel_crack

    def _calculate_latest_crack_value(
        self,
        *,
        market_price: float | None,
        brent_price: float | None,
        cny_mid: float | None,
        consumption_tax: float,
    ) -> float | None:
        if market_price is None or brent_price is None or cny_mid is None:
            return None
        try:
            value = float(market_price) / (1.0 + VAT_RATE) - consumption_tax - float(brent_price) * BARREL_TO_TON_RATIO * float(cny_mid)
        except (TypeError, ValueError):
            return None
        return self._round_or_none(value)

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
        if "shandong_cdu_utilization_weekly" in frame.columns:
            frame["shandong_cdu_utilization_weekly"] = pd.to_numeric(
                frame["shandong_cdu_utilization_weekly"],
                errors="coerce",
            ).combine_first(pd.to_numeric(frame["sd_crude_run_weekly"], errors="coerce"))
        else:
            frame["shandong_cdu_utilization_weekly"] = pd.to_numeric(
                frame["sd_crude_run_weekly"],
                errors="coerce",
            )
        frame = self._attach_formula_crack_spreads(frame)
        frame = frame.copy()
        frame["gas_price_change_1d"] = frame["sd_gas92_market"].diff(1)
        frame["gas_price_change_3d"] = frame["sd_gas92_market"].diff(3)
        frame["diesel_price_change_1d"] = frame["sd_diesel0_market"].diff(1)
        frame["diesel_price_change_3d"] = frame["sd_diesel0_market"].diff(3)
        frame["gas_price_ma5"] = frame["sd_gas92_market"].rolling(5).mean()
        frame["gas_price_ma10"] = frame["sd_gas92_market"].rolling(10).mean()
        frame["gasoline_crack_change_3d"] = frame["sd_gas_crack"].diff(3)
        frame["gasoline_crack_trend"] = np.sign(frame["gasoline_crack_change_3d"]).fillna(0.0)
        frame["gasoline_crack_percentile"] = self._expanding_percentile_since(frame, "sd_gas_crack", start_date=CRACK_PERCENTILE_HISTORY_START)
        frame["diesel_crack_change_3d"] = frame["sd_diesel_crack"].diff(3)
        frame["diesel_crack_trend"] = np.sign(frame["diesel_crack_change_3d"]).fillna(0.0)
        frame["diesel_crack_percentile"] = self._expanding_percentile_since(frame, "sd_diesel_crack", start_date=CRACK_PERCENTILE_HISTORY_START)
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
        if frame["price_adjustment_expected_yuan"].isna().all():
            sci99_adjustment = self._fetch_sci99_price_adjustment_expected_yuan()
            if sci99_adjustment is not None:
                frame["price_adjustment_expected_yuan"] = sci99_adjustment
        frame = frame.copy()
        frame["sd_cn_spread"] = frame["sd_gas92_market"] - frame["cn_gas92_market"]
        for price_column, spread_column, shandong_price_column in REGIONAL_SPREAD_SPECS:
            frame[spread_column] = frame[shandong_price_column] - frame[price_column]
            frame[f"{spread_column}_change_1d"] = frame[spread_column].diff(1)
            frame[f"{spread_column}_change_3d"] = frame[spread_column].diff(3)
        frame["profit_change_1w"] = self._change_from_previous_observation(frame["sd_refining_profit"])
        frame["sales_change_1w"] = self._change_from_previous_observation(frame["sd_gas_sales_weekly"])
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
        frame["sales_production_ratio_d1"] = external_sales_production_ratio.combine_first(
            computed_sales_production_ratio
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
            frame["sales_production_ratio_d1"].rolling(3, min_periods=3).mean()
        )
        frame["sales_production_ratio_w1_avg"] = manual_ratio_w1_avg.combine_first(
            frame["sales_production_ratio_d1"].rolling(7, min_periods=7).mean()
        )
        frame["sales_production_ratio_monthly_avg"] = frame["sales_production_ratio_d1"].rolling(30, min_periods=1).mean()
        frame["sales_production_ratio_monthly_change"] = frame["sales_production_ratio_monthly_avg"] - frame[
            "sales_production_ratio_monthly_avg"
        ].shift(30)
        frame["shandong_restocking_active_days_prev_month"] = self._previous_month_active_day_count(
            frame,
            "sales_production_ratio_d1",
            month_offset=1,
            threshold=90.0,
        )
        frame["shandong_restocking_active_days_month_before_prev"] = self._previous_month_active_day_count(
            frame,
            "sales_production_ratio_d1",
            month_offset=2,
            threshold=90.0,
        )
        frame["restocking_rhythm_monthly_change"] = (
            frame["shandong_restocking_active_days_prev_month"]
            - frame["shandong_restocking_active_days_month_before_prev"]
        )
        if "diesel_sales_production_ratio_d1" not in frame.columns:
            frame["diesel_sales_production_ratio_d1"] = np.nan
        frame["diesel_sales_production_ratio_d3_avg"] = frame["diesel_sales_production_ratio_d1"].rolling(3, min_periods=3).mean()
        frame["diesel_sales_production_ratio_w1_avg"] = frame["diesel_sales_production_ratio_d1"].rolling(7, min_periods=7).mean()
        frame["diesel_sales_production_ratio_monthly_avg"] = frame["diesel_sales_production_ratio_d1"].rolling(30, min_periods=1).mean()
        frame["diesel_sales_production_ratio_monthly_change"] = frame["diesel_sales_production_ratio_monthly_avg"] - frame[
            "diesel_sales_production_ratio_monthly_avg"
        ].shift(30)
        frame["crude_run_change_1w"] = self._change_from_previous_observation(frame["sd_crude_run_weekly"])
        existing_utilization_percentile = (
            pd.to_numeric(frame["shandong_cdu_utilization_percentile_weekly"], errors="coerce")
            if "shandong_cdu_utilization_percentile_weekly" in frame.columns
            else pd.Series(np.nan, index=frame.index)
        )
        fallback_utilization_percentile = self._expanding_percentile_since(frame, "sd_crude_run_weekly")
        frame["shandong_cdu_utilization_percentile_weekly"] = existing_utilization_percentile.combine_first(
            fallback_utilization_percentile
        )
        frame["shandong_cdu_utilization_percentile_monthly"] = frame[
            "shandong_cdu_utilization_percentile_weekly"
        ].rolling(20, min_periods=5).mean()
        empty_series = pd.Series(np.nan, index=frame.index)
        trader_inventory_level = empty_series
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
                "shandong_gasoline_inventory",
                "shandong_independent_refinery_gasoline_inventory",
                "shandong_refinery_gasoline_inventory",
                "shandong_independent_refinery_inventory",
                "shandong_refinery_inventory",
            ],
        )
        inventory_components = pd.concat(
            [trader_inventory_level, main_inventory_level, refinery_inventory_level],
            axis=1,
            keys=["trader", "main", "refinery"],
        )
        observed_inventory_total = pd.concat(
            [main_inventory_level, refinery_inventory_level],
            axis=1,
        ).sum(axis=1, min_count=1)
        formal_inventory_total = inventory_components.sum(axis=1, min_count=1)
        component_present = inventory_components.notna()
        previous_component_present = component_present.shift(5).fillna(False)
        current_missing_after_previous_present = previous_component_present & ~component_present
        frame["shandong_product_inventory_missing_component_count"] = current_missing_after_previous_present.sum(axis=1).astype(float)
        frame["shandong_product_inventory_available_component_count"] = component_present.sum(axis=1).astype(float)
        frame["shandong_product_inventory_total_observed"] = observed_inventory_total
        frame["shandong_product_inventory_total_formal"] = formal_inventory_total
        frame["shandong_product_inventory_change_weekly"] = self._change_from_previous_observation(formal_inventory_total)
        frame["shandong_refinery_inventory_change_weekly"] = self._change_from_previous_observation(refinery_inventory_level)
        frame["shandong_main_company_inventory_change_weekly"] = self._change_from_previous_observation(main_inventory_level)
        frame["shandong_product_inventory_percentile_weekly"] = self._expanding_percentile_since(frame, formal_inventory_total)
        frame["shandong_refinery_inventory_percentile_monthly"] = self._expanding_percentile_since(
            frame,
            refinery_inventory_level,
        )
        frame["shandong_main_company_inventory_percentile_monthly"] = self._expanding_percentile_since(
            frame,
            main_inventory_level,
        )
        diesel_main_inventory_level = self._first_available_series(
            frame,
            [
                "shandong_main_company_diesel_inventory",
                "shandong_main_diesel_inventory",
            ],
        )
        diesel_refinery_inventory_level = self._first_available_series(
            frame,
            [
                "shandong_diesel_inventory",
                "shandong_independent_refinery_diesel_inventory",
                "shandong_refinery_diesel_inventory",
            ],
        )
        diesel_trader_inventory_level = empty_series
        diesel_inventory_components = pd.concat(
            [diesel_trader_inventory_level, diesel_main_inventory_level, diesel_refinery_inventory_level],
            axis=1,
            keys=["trader", "main", "refinery"],
        )
        diesel_formal_inventory_total = diesel_inventory_components.sum(axis=1, min_count=1)
        frame["shandong_diesel_product_inventory_total_formal"] = diesel_formal_inventory_total
        frame["shandong_diesel_product_inventory_change_weekly"] = self._change_from_previous_observation(diesel_formal_inventory_total)
        frame["shandong_diesel_product_inventory_percentile_weekly"] = self._expanding_percentile_since(frame, diesel_formal_inventory_total)
        frame["shandong_diesel_inventory_percentile_monthly"] = self._expanding_percentile_since(
            frame,
            diesel_refinery_inventory_level,
        )
        frame["shandong_diesel_inventory_change_weekly"] = self._change_from_previous_observation(diesel_refinery_inventory_level)
        frame["shandong_diesel_refinery_inventory_percentile_monthly"] = frame[
            "shandong_diesel_inventory_percentile_monthly"
        ]
        frame["shandong_diesel_refinery_inventory_change_weekly"] = frame[
            "shandong_diesel_inventory_change_weekly"
        ]
        frame["shandong_diesel_main_company_inventory_percentile_monthly"] = self._expanding_percentile_since(
            frame,
            diesel_main_inventory_level,
        )
        frame["shandong_diesel_main_company_inventory_change_weekly"] = self._change_from_previous_observation(diesel_main_inventory_level)
        frame["shipments_change_1w"] = self._change_from_previous_observation(frame["sd_gas_shipments_weekly"])
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


    def _change_from_previous_observation(self, series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        observed_mask = numeric.notna() & numeric.ne(numeric.shift())
        observed = numeric.where(observed_mask)
        previous_observed = observed.ffill().shift()
        return (observed - previous_observed).where(observed_mask)

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

    def _previous_month_active_day_count(
        self,
        frame: pd.DataFrame,
        column: str,
        *,
        month_offset: int,
        threshold: float,
    ) -> pd.Series:
        result = pd.Series(np.nan, index=frame.index, dtype="float64")
        if "date" not in frame.columns or column not in frame.columns:
            return result
        dates = pd.to_datetime(frame["date"], errors="coerce")
        values = pd.to_numeric(frame[column], errors="coerce")
        period = dates.dt.to_period("M")
        monthly_counts = (values > threshold).groupby(period).sum(min_count=1)
        target_periods = period - month_offset
        mapped = target_periods.map(monthly_counts)
        return pd.Series(mapped.to_numpy(dtype="float64"), index=frame.index)

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

    def _expanding_percentile_since(
        self,
        frame: pd.DataFrame,
        column_or_series: str | pd.Series,
        *,
        start_date: date = PERCENTILE_HISTORY_START,
        min_periods: int = 5,
    ) -> pd.Series:
        source = (
            pd.to_numeric(frame[column_or_series], errors="coerce")
            if isinstance(column_or_series, str)
            else pd.to_numeric(column_or_series, errors="coerce")
        )
        result = pd.Series(np.nan, index=frame.index, dtype="float64")
        if "date" not in frame.columns:
            return self._expanding_percentile(source, min_periods=min_periods)
        dates = pd.to_datetime(frame["date"], errors="coerce").dt.date
        mask = dates >= start_date
        if not bool(mask.any()):
            return result
        result.loc[mask] = self._expanding_percentile(source.loc[mask], min_periods=min_periods)
        return result

    def _fetch_sci99_price_adjustment_expected_yuan(self) -> float | None:
        try:
            response = requests.get(
                SCI99_REFINED_OIL_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
                timeout=20,
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        except Exception:
            return None
        page_text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        page_text = re.sub(r"\s+", " ", page_text)
        expected = "\u9884\u8ba1"
        forecast_width = "\u9884\u6d4b\u5e45\u5ea6"
        up = "\u4e0a\u8c03"
        down = "\u4e0b\u8c03"
        no_adjust = "\u6401\u6d45"
        yuan_per_ton = "\u5143/\u5428"
        direction_pattern = f"({up}|{down}|{no_adjust})?"
        forecast_match = re.search(
            rf"{expected}\s*{direction_pattern}\s*([+-]?\d+(?:\.\d+)?)\s*{yuan_per_ton}",
            page_text,
        )
        if not forecast_match:
            forecast_match = re.search(
                rf"{forecast_width}[^-+\d]*{direction_pattern}[^-+\d]*([+-]?\d+(?:\.\d+)?)\s*{yuan_per_ton}",
                page_text,
            )
        if not forecast_match:
            return None
        direction = forecast_match.group(1) or ""
        value = float(forecast_match.group(2))
        if direction == down and value > 0:
            value = -value
        if direction == up and value < 0:
            value = abs(value)
        if direction == no_adjust:
            value = 0.0
        return value

    def _first_available_series(self, frame: pd.DataFrame, columns: list[str]) -> pd.Series:
        result = pd.Series(np.nan, index=frame.index)
        for column in columns:
            if column in frame.columns:
                result = result.combine_first(pd.to_numeric(frame[column], errors="coerce"))
        return result

    def _annotate_refinery_dynamic_item(self, item: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(str(item.get(key) or "") for key in ("headline", "title", "summary", "content"))
        matches = match_refinery_regions(text)
        regions = []
        refineries = []
        for row in matches:
            region = row.get("region") or ""
            name = row.get("short_name") or row.get("full_name") or ""
            if region and region not in regions:
                regions.append(region)
            if name and name not in refineries:
                refineries.append(name)
        if not matches and any(region in text for region in MAINTENANCE_REGION_PROVINCES):
            regions = matched_region_names(text) or [region for region in MAINTENANCE_REGION_PROVINCES if region in text]
        load_adjustment = 0.0
        tightening_words = (
            "\u964d\u8d1f",
            "\u964d\u8d1f\u8377",
            "\u505c\u5de5",
            "\u68c0\u4fee",
            "\u9650\u4ea7",
            "\u505c\u4ea7",
            "\u964d\u91cf",
            "\u51cf\u4ea7",
        )
        loosening_words = (
            "\u590d\u5de5",
            "\u5f00\u5de5\u63d0\u5347",
            "\u63d0\u8d1f",
            "\u63d0\u8d1f\u8377",
            "\u6062\u590d\u751f\u4ea7",
            "\u91cd\u542f",
            "\u5f00\u8f66",
        )
        if any(word in text for word in tightening_words):
            load_adjustment += 1.5
        if any(word in text for word in loosening_words):
            load_adjustment -= 1.5
        annotated = dict(item)
        if regions:
            annotated["refinery_regions"] = regions
        if refineries:
            annotated["matched_refineries"] = refineries[:8]
        if abs(load_adjustment) > 1e-9:
            annotated["refinery_load_adjustment"] = max(-5.0, min(5.0, load_adjustment))
            annotated["topic"] = annotated.get("topic") or "refinery_dynamic"
        return annotated

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
        return datetime.combine(as_of_date, time(hour=8, minute=30))

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

    def _round_or_none(self, value: Any, *, digits: int = 2) -> float | None:
        try:
            if value is None:
                return None
            if pd.isna(value):
                return None
            return round(float(value), digits)
        except Exception:
            return None

    def _infer_affected_product(self, text: str) -> str:
        normalized = text.replace("０", "0").replace("＃", "#")
        if any(keyword in normalized for keyword in ("汽柴油", "成品油")):
            return "92#汽油 / 0#柴油"
        products: list[str] = []
        if any(keyword in normalized for keyword in ("92#", "92号", "汽油")):
            products.append("92#汽油")
        if any(keyword in normalized for keyword in ("0#柴油", "0号柴油", "柴油")):
            products.append("0#柴油")
        return " / ".join(products) if products else "成品油"

    def _fmt_policy_delta(self, value: Any) -> str:
        try:
            delta = float(value or 0.0)
        except Exception:
            delta = 0.0
        direction = "上调" if delta > 0 else "下调" if delta < 0 else "持平"
        return f"{direction}{abs(delta):.0f}元/吨"

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
        delta = max(
            abs(float(item.get("gasoline_change_yuan_per_ton") or 0.0)),
            abs(float(item.get("diesel_change_yuan_per_ton") or 0.0)),
        )
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
            gasoline_delta = item.get("gasoline_change_yuan_per_ton")
            diesel_delta = item.get("diesel_change_yuan_per_ton")
            alert_context = self._build_policy_alert_context(item=item)
            candidates.append(
                {
                    "title": (
                        f"{item.get('title')} | 汽油{self._fmt_policy_delta(gasoline_delta)} / "
                        f"柴油{self._fmt_policy_delta(diesel_delta)}"
                    ),
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

    def _build_policy_alert_context(self, *, item: dict[str, Any]) -> dict[str, Any]:
        gasoline_delta = float(item.get("gasoline_change_yuan_per_ton") or 0.0)
        diesel_delta = float(item.get("diesel_change_yuan_per_ton") or 0.0)
        delta = gasoline_delta if abs(gasoline_delta) >= abs(diesel_delta) else diesel_delta
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
            "affected_product": "92#汽油 / 0#柴油",
            "direction": direction,
            "expected_impact": f"汽油 {gasoline_delta:+.0f} / 柴油 {diesel_delta:+.0f} 元/吨",
            "confidence": "高",
            "status": "待确认",
            "action": action,
        }

    def _is_supply_relief_alert(self, text: str) -> bool:
        relief_keywords = (
            "\u6d77\u5ce1\u5f00\u653e",
            "\u6d77\u5ce1\u5f00\u53d1",
            "\u91cd\u65b0\u5f00\u653e",
            "\u6062\u590d\u5f00\u653e",
            "\u6062\u590d\u901a\u822a",
            "\u6062\u590d\u822a\u884c",
            "\u89e3\u9664\u5c01\u9501",
            "\u5c01\u9501\u89e3\u9664",
            "\u822a\u8fd0\u6062\u590d",
            "\u901a\u884c\u6062\u590d",
            "\u5c40\u52bf\u7f13\u548c",
            "\u505c\u706b",
            "\u8fbe\u6210\u534f\u8bae",
            "reopen",
            "re-open",
            "reopened",
            "open strait",
            "strait open",
            "peace deal",
            "deal with iran",
            "deal is now complete",
            "ceasefire",
            "oil slips",
            "oil falls",
        )
        normalized = text.lower()
        return any(keyword in normalized for keyword in relief_keywords)

    def _build_alert_context(self, *, item: dict[str, Any], category: str) -> dict[str, Any]:
        text = f"{item.get('headline') or item.get('title') or ''} {item.get('summary') or ''} {item.get('content') or ''}"
        base_score = float(item.get("_importance_score") or item.get("importance_score") or 0.0)
        up_keywords = ("袭击", "制裁", "减产", "供应中断", "检修", "停工", "运费上涨", "红海", "霍尔木兹", "库存下降", "地缘")
        down_keywords = ("停火", "增产", "复产", "库存增加", "需求疲软", "降价", "下跌")
        supply_relief = self._is_supply_relief_alert(text)
        up_hits = sum(1 for keyword in up_keywords if keyword in text)
        down_hits = sum(1 for keyword in down_keywords if keyword in text)
        if supply_relief:
            down_hits = max(down_hits, up_hits + 1, 2)
        direction = "\u63a8\u6da8" if up_hits > down_hits else "\u538b\u8dcc" if down_hits > up_hits else "\u6270\u52a8"
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
            "affected_product": self._infer_affected_product(text),
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
