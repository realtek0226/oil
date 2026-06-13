import pandas as pd

from app.services.market_dataset import (
    BARREL_TO_TON_RATIO,
    DIESEL_CONSUMPTION_TAX_YUAN_PER_TON,
    GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON,
    INDICATOR_KEYS,
    VAT_RATE,
    MarketDatasetService,
)
from app.services.predictors.shandong_gas92 import ShandongGas92Predictor


def test_formula_crack_spread_overrides_existing_indicator_when_fx_exists():
    service = object.__new__(MarketDatasetService)
    frame = pd.DataFrame(
        {
            "sd_gas92_market": [8500.0],
            "sd_diesel0_market": [7600.0],
            "brent_active_settlement": [95.03],
            "usd_cny_mid_rate": [7.10],
            "sd_gas_crack": [1.0],
            "sd_diesel_crack": [2.0],
        }
    )

    result = service._attach_formula_crack_spreads(frame)

    expected_gas = (
        8500.0 / (1.0 + VAT_RATE)
        - GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON
        - 95.03 * BARREL_TO_TON_RATIO * 7.10
    )
    expected_diesel = (
        7600.0 / (1.0 + VAT_RATE)
        - DIESEL_CONSUMPTION_TAX_YUAN_PER_TON
        - 95.03 * BARREL_TO_TON_RATIO * 7.10
    )
    assert round(result.loc[0, "sd_gas_crack"], 2) == round(expected_gas, 2)
    assert round(result.loc[0, "sd_diesel_crack"], 2) == round(expected_diesel, 2)
    assert result.loc[0, "sd_gas_crack_formula_available"] == 1.0
    assert result.loc[0, "sd_diesel_crack_formula_available"] == 1.0


def test_formula_crack_spread_keeps_existing_indicator_when_fx_missing():
    service = object.__new__(MarketDatasetService)
    frame = pd.DataFrame(
        {
            "sd_gas92_market": [8500.0],
            "brent_active_settlement": [95.03],
            "sd_gas_crack": [123.0],
        }
    )

    result = service._attach_formula_crack_spreads(frame)

    assert result.loc[0, "sd_gas_crack"] == 123.0
    assert result.loc[0, "sd_gas_crack_formula_available"] == 0.0


def test_eta_indicator_keys_do_not_include_formula_crack_spreads():
    assert "sd_gas_crack" not in INDICATOR_KEYS
    assert "sd_diesel_crack" not in INDICATOR_KEYS
    assert "sd_gas92_market" in INDICATOR_KEYS


def test_direct_cny_mid_rate_is_attached_by_asof_date():
    service = object.__new__(MarketDatasetService)
    base = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-03", "2026-06-04"]),
            "sd_gas92_market": [8077.0, 8062.0],
        }
    )
    cny = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-03"]),
            "cny_mid_rate": [6.8184],
        }
    )

    result = service._attach_direct_cny_mid_rate(base=base, cny_mid_frame=cny)

    assert result.loc[0, "cny_mid_rate"] == 6.8184
    assert result.loc[1, "cny_mid_rate"] == 6.8184


def test_predicted_gasoline_crack_uses_predicted_price_and_brent_point():
    predictor = object.__new__(ShandongGas92Predictor)

    value = predictor._calculate_gasoline_crack_spread(
        market_price=8500.0,
        brent_price=96.2,
        cny_mid=7.10,
    )

    expected = (
        8500.0 / (1.0 + VAT_RATE)
        - GASOLINE_CONSUMPTION_TAX_YUAN_PER_TON
        - 96.2 * BARREL_TO_TON_RATIO * 7.10
    )
    assert round(value, 2) == round(expected, 2)
