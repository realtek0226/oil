from datetime import date, datetime

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
