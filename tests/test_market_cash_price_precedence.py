from datetime import date, datetime

import pandas as pd

from app.services.market_dataset import MarketDatasetService


class _CashPriceRepository:
    enabled = True

    def load_market_timeseries_values(self, *, source_code, indicator_codes, start_date, end_date):
        if source_code == "oilchem_production_sales_ratio":
            return [
                {
                    "indicator_code": "oilchem_sd_gasoline_production_sales_ratio",
                    "entity_code": "SHANDONG_REFINERY_GASOLINE",
                    "dt": date(2026, 6, 12),
                    "value_num": 88.0,
                    "publish_time": datetime(2026, 6, 12, 20, 0),
                    "observation_time": datetime(2026, 6, 12, 0, 0),
                }
            ]
        if source_code == "ganglian_excel_import" and "sd_gas92_market" in indicator_codes:
            return [
                {
                    "indicator_code": "sd_gas92_market",
                    "entity_code": "SHANDONG",
                    "dt": date(2026, 6, 11),
                    "value_num": 8046.0,
                    "publish_time": datetime(2026, 6, 12, 8, 12),
                    "observation_time": datetime(2026, 6, 11, 0, 0),
                }
            ]
        return []


def _service() -> MarketDatasetService:
    svc = object.__new__(MarketDatasetService)
    svc.snapshot_repository = _CashPriceRepository()
    return svc


def test_default_prediction_date_waits_for_preferred_cash_price_date() -> None:
    svc = _service()

    result = svc.resolve_default_prediction_as_of(date(2026, 6, 12))

    assert result == date(2026, 6, 11)


def test_latest_snapshot_prefers_cash_price_over_eta_market_price() -> None:
    svc = _service()
    svc._eta_is_available = lambda: True
    svc._fetch_wind_brent_price = lambda: None
    svc._fallback_latest_prices = lambda as_of_date: {
        "brent_active_settlement": 95.0,
        "sd_gas92_market": 8000.0,
    }
    svc._fetch_eta_latest_value = lambda key, as_of_date: 8015.0 if key == "sd_gas92_market" else None

    latest_prices, mode, reason = svc._load_latest_price_snapshot(as_of_date=date(2026, 6, 12))

    assert latest_prices["sd_gas92_market"] == 8046.0
    assert "cash_overlay" in mode
    assert "sd_gas92_market@2026-06-11:ganglian_excel_import" in reason


def test_oilchem_production_sales_ratio_falls_back_by_product_independently() -> None:
    svc = object.__new__(MarketDatasetService)
    svc._load_archived_oilchem_records = lambda **_: [
        {
            "observation_date": date(2026, 6, 7),
            "gasoline_ratio": 108.0,
            "diesel_ratio": None,
            "source": "manual_latest_gasoline_only",
            "url": "https://example.com/latest",
            "publish_time": datetime(2026, 6, 7, 9, 0),
        },
        {
            "observation_date": date(2026, 6, 3),
            "gasoline_ratio": 49.0,
            "diesel_ratio": 56.0,
            "source": "crawler_with_diesel",
            "url": "https://example.com/diesel",
            "publish_time": datetime(2026, 6, 3, 9, 0),
        },
    ]

    base = pd.DataFrame({"date": [pd.Timestamp("2026-06-12")]})

    result = svc._attach_oilchem_production_sales_ratio(base=base, end_date=date(2026, 6, 12))
    latest = result.iloc[-1]

    assert latest["sales_production_ratio_d1"] == 108.0
    assert latest["diesel_sales_production_ratio_d1"] == 56.0
    assert latest["sales_production_ratio_stale_days"] == 5
    assert latest["diesel_sales_production_ratio_stale_days"] == 9
    assert latest["diesel_sales_production_ratio_source"] == "crawler_with_diesel"
