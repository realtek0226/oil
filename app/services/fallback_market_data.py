from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_ANCHOR_DATE = date(2026, 5, 29)
DEFAULT_SD_GAS92_PRICE = 7970.0
DEFAULT_CN_GAS92_PRICE = 8028.0
DEFAULT_BRENT_PRICE = 64.8

DEFAULT_REGIONAL_SPREADS = {
    "east_china_gas92_market": -71.0,
    "north_china_gas92_market": -22.0,
    "south_china_gas92_market": -72.0,
    "central_china_gas92_market": -128.0,
    "northwest_gas92_market": -131.0,
    "southwest_gas92_market": -101.0,
    "northeast_gas92_market": -21.0,
}

SPREAD_PHASES = {
    "east_china_gas92_market": (0.0, 0.0),
    "north_china_gas92_market": (2.0, 5.0),
    "south_china_gas92_market": (4.0, 8.0),
    "central_china_gas92_market": (6.0, 11.0),
    "northwest_gas92_market": (8.0, 14.0),
    "southwest_gas92_market": (10.0, 17.0),
    "northeast_gas92_market": (12.0, 20.0),
}


class LocalFallbackMarketDataBuilder:
    def __init__(
        self,
        prediction_dir: Path | str = Path("artifacts/prediction_runs"),
        backtest_dir: Path | str = Path("artifacts/backtests"),
    ) -> None:
        self.prediction_dir = Path(prediction_dir)
        self.backtest_dir = Path(backtest_dir)

    def build_feature_frame(self, start_date: date, end_date: date) -> pd.DataFrame:
        business_days = pd.bdate_range(start_date, end_date)
        if business_days.empty:
            return pd.DataFrame(columns=["date"])

        profile = self._load_profile()
        recent_prices = self._load_recent_shandong_prices()
        anchor_date = profile["anchor_date"]
        anchor_sd_price = float(profile["sd_gas92_market"])
        anchor_cn_price = float(profile["cn_gas92_market"])
        anchor_brent = float(profile["brent_active_settlement"])
        regional_spreads = dict(profile["regional_spreads"])

        offsets = np.array([self._business_offset(anchor_date, current_date.date()) for current_date in business_days])
        sd_prices = self._build_sd_price_series(offsets=offsets, anchor_price=anchor_sd_price)

        index_lookup = {current_date.date(): idx for idx, current_date in enumerate(business_days)}
        for price_date, price_value in recent_prices.items():
            row_index = index_lookup.get(price_date)
            if row_index is not None:
                sd_prices[row_index] = float(price_value)
        if anchor_date in index_lookup:
            sd_prices[index_lookup[anchor_date]] = anchor_sd_price

        brent_series = (
            anchor_brent
            + 0.018 * offsets
            + 1.45 * np.sin(offsets / 8.5)
            + 0.7 * (np.cos(offsets / 21.0) - 1.0)
        )

        cn_spread_anchor = anchor_sd_price - anchor_cn_price
        cn_spread_series = self._spread_series(offsets, cn_spread_anchor, phase_a=1.5, phase_b=3.0, scale=8.0)
        cn_prices = sd_prices - cn_spread_series

        regional_prices: dict[str, np.ndarray] = {}
        for column, spread_anchor in regional_spreads.items():
            phase_a, phase_b = SPREAD_PHASES[column]
            spread_series = self._spread_series(offsets, spread_anchor, phase_a=phase_a, phase_b=phase_b, scale=11.0)
            regional_prices[column] = sd_prices - spread_series

        sd_gas_crack = 640.0 + 0.55 * (sd_prices - anchor_sd_price) + 20.0 * np.sin(offsets / 10.5)
        sd_refining_profit = 235.0 + 0.23 * sd_gas_crack - 1.7 * brent_series + 15.0 * np.cos(offsets / 16.0)
        sd_gas_sales_weekly = 3.45 + 0.11 * np.sin(offsets / 5.8) + 0.04 * (np.cos(offsets / 18.0) - 1.0)
        sd_crude_run_weekly = 71.8 + 0.35 * np.cos(offsets / 13.5) + 0.12 * np.sin(offsets / 24.0)
        sd_ceiling_gas = sd_prices + 525.0 + 24.0 * np.sin(offsets / 12.0) + 8.0 * (np.cos(offsets / 29.0) - 1.0)
        sd_mtbe_price = 6405.0 + 0.41 * (sd_prices - anchor_sd_price) + 26.0 * np.sin(offsets / 10.0)
        sd_naphtha_price = 6650.0 + 0.31 * (sd_prices - anchor_sd_price) + 18.0 * np.cos(offsets / 11.5)
        sd_gas_naphtha_spread = sd_prices - sd_naphtha_price
        sd_gas_shipments_weekly = 2.78 + 0.08 * np.sin(offsets / 6.2) + 0.03 * (np.cos(offsets / 14.5) - 1.0)

        frame = pd.DataFrame(
            {
                "date": business_days.date,
                "sd_gas92_market": np.round(sd_prices, 2),
                "cn_gas92_market": np.round(cn_prices, 2),
                "sd_gas_crack": np.round(sd_gas_crack, 2),
                "sd_refining_profit": np.round(sd_refining_profit, 2),
                "sd_gas_sales_weekly": np.round(sd_gas_sales_weekly, 4),
                "sd_crude_run_weekly": np.round(sd_crude_run_weekly, 4),
                "sd_ceiling_gas": np.round(sd_ceiling_gas, 2),
                "sd_mtbe_price": np.round(sd_mtbe_price, 2),
                "sd_naphtha_price": np.round(sd_naphtha_price, 2),
                "sd_gas_naphtha_spread": np.round(sd_gas_naphtha_spread, 2),
                "sd_gas_shipments_weekly": np.round(sd_gas_shipments_weekly, 4),
                "brent_active_settlement": np.round(brent_series, 2),
            }
        )
        for column, values in regional_prices.items():
            frame[column] = np.round(values, 2)
        return frame.sort_values("date").reset_index(drop=True)

    def _build_sd_price_series(self, offsets: np.ndarray, anchor_price: float) -> np.ndarray:
        return (
            anchor_price
            + 1.1 * offsets
            + 42.0 * np.sin(offsets / 7.3)
            + 18.0 * (np.cos(offsets / 19.0) - 1.0)
            + 7.0 * np.sin(offsets / 3.6)
        )

    def _spread_series(
        self,
        offsets: np.ndarray,
        anchor_spread: float,
        *,
        phase_a: float,
        phase_b: float,
        scale: float,
    ) -> np.ndarray:
        base_wave = scale * np.sin((offsets + phase_a) / 8.6) - scale * np.sin(phase_a / 8.6)
        slow_wave = 4.5 * np.cos((offsets + phase_b) / 20.0) - 4.5 * np.cos(phase_b / 20.0)
        drift = 0.05 * offsets
        return anchor_spread + base_wave + slow_wave + drift

    def _load_profile(self) -> dict[str, Any]:
        profile = {
            "anchor_date": DEFAULT_ANCHOR_DATE,
            "sd_gas92_market": DEFAULT_SD_GAS92_PRICE,
            "cn_gas92_market": DEFAULT_CN_GAS92_PRICE,
            "brent_active_settlement": DEFAULT_BRENT_PRICE,
            "regional_spreads": dict(DEFAULT_REGIONAL_SPREADS),
        }

        latest_outright_payload = self._load_latest_payload("sdgas92-*.json")
        if latest_outright_payload:
            profile["anchor_date"] = self._parse_date(latest_outright_payload.get("as_of_date")) or profile["anchor_date"]
            raw_context = latest_outright_payload.get("raw_context") or {}
            profile["sd_gas92_market"] = float(raw_context.get("current_price") or profile["sd_gas92_market"])

        regional_prices: list[float] = []
        for path in self.prediction_dir.glob("sdspread-*.json"):
            payload = self._load_json_file(path)
            if not payload:
                continue
            raw_context = payload.get("raw_context") or {}
            spread_column = str(raw_context.get("spread_column") or "").strip()
            if not spread_column or spread_column not in profile["regional_spreads"]:
                continue
            current_spread = raw_context.get("current_spread")
            counter_price = raw_context.get("current_counter_region_price")
            if current_spread is not None:
                profile["regional_spreads"][spread_column] = float(current_spread)
            if counter_price is not None:
                regional_prices.append(float(counter_price))

        if regional_prices:
            regional_mean = float(np.mean(regional_prices))
            suggested_cn_price = round(regional_mean - 20.0, 2)
            profile["cn_gas92_market"] = max(profile["sd_gas92_market"] + 20.0, suggested_cn_price)
        return profile

    def _load_recent_shandong_prices(self) -> dict[date, float]:
        price_by_date: dict[date, float] = {}
        for path in self.backtest_dir.glob("sdgas92-*.json"):
            payload = self._load_json_file(path)
            if not payload:
                continue
            for row in payload.get("rows") or []:
                target_date = self._parse_date(row.get("target_date"))
                actual_point = row.get("actual_point")
                if target_date and actual_point is not None:
                    price_by_date[target_date] = float(actual_point)

        for path in self.prediction_dir.glob("sdgas92-*.json"):
            payload = self._load_json_file(path)
            if not payload:
                continue
            as_of_date = self._parse_date(payload.get("as_of_date"))
            raw_context = payload.get("raw_context") or {}
            current_price = raw_context.get("current_price")
            if as_of_date and current_price is not None:
                price_by_date[as_of_date] = float(current_price)
        return price_by_date

    def _load_latest_payload(self, pattern: str) -> dict[str, Any] | None:
        latest_payload: dict[str, Any] | None = None
        latest_key: tuple[date, float] | None = None
        for path in self.prediction_dir.glob(pattern):
            payload = self._load_json_file(path)
            if not payload:
                continue
            as_of_date = self._parse_date(payload.get("as_of_date"))
            if as_of_date is None:
                continue
            current_key = (as_of_date, path.stat().st_mtime)
            if latest_key is None or current_key > latest_key:
                latest_payload = payload
                latest_key = current_key
        return latest_payload

    def _load_json_file(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _parse_date(self, value: Any) -> date | None:
        raw = str(value or "").strip()
        if len(raw) < 10:
            return None
        normalized = raw.replace("/", "-")
        try:
            return pd.Timestamp(normalized[:10]).date()
        except Exception:
            return None

    def _business_offset(self, anchor_date: date, current_date: date) -> float:
        anchor = anchor_date.isoformat()
        current = current_date.isoformat()
        if current_date >= anchor_date:
            return float(np.busday_count(anchor, current))
        return -float(np.busday_count(current, anchor))
