from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


WHITELIST_PATH = Path("artifacts/eta_p0_whitelist_2026-05-29.json")


@dataclass(frozen=True)
class IndicatorRef:
    key: str
    name: str
    unique_code: str
    edb_code: str
    source_name: str


EXTRA_INDICATORS: dict[str, IndicatorRef] = {
    "brent_active_settlement": IndicatorRef(
        key="brent_active_settlement",
        name="Brent futures active settlement",
        unique_code="2add80bcd631d8045510e8c0517d0746",
        edb_code="S004111387",
        source_name="Tonghuashun",
    ),
    "brent_spot_price": IndicatorRef(
        key="brent_spot_price",
        name="Brent spot price",
        unique_code="1cb5e358ba486829c2bf8897af98a2e3",
        edb_code="EUCRBRDT index",
        source_name="Bloomberg",
    ),
    "east_china_gas92_market": IndicatorRef(
        key="east_china_gas92_market",
        name="92# gasoline market price: East China",
        unique_code="df4bf315451e462a030e8465d01c1cc6",
        edb_code="ID00402382",
        source_name="Mysteel",
    ),
    "north_china_gas92_market": IndicatorRef(
        key="north_china_gas92_market",
        name="92# gasoline market price: North China",
        unique_code="4db236d8f70adc5a6e9fa40775937a99",
        edb_code="ID00397789",
        source_name="Mysteel",
    ),
    "south_china_gas92_market": IndicatorRef(
        key="south_china_gas92_market",
        name="92# gasoline market price: South China",
        unique_code="d9fe89e177f974aa237e3031ea33bd45",
        edb_code="ID00397791",
        source_name="Mysteel",
    ),
    "central_china_gas92_market": IndicatorRef(
        key="central_china_gas92_market",
        name="92# gasoline market price: Central China",
        unique_code="517f9e50c3b09b49253a9acdf9b8335a",
        edb_code="ID00397794",
        source_name="Mysteel",
    ),
    "northwest_gas92_market": IndicatorRef(
        key="northwest_gas92_market",
        name="92# gasoline market price: Northwest",
        unique_code="32129fdb9e6c953a2ae18f252d544147",
        edb_code="ID00397792",
        source_name="Mysteel",
    ),
    "southwest_gas92_market": IndicatorRef(
        key="southwest_gas92_market",
        name="92# gasoline market price: Southwest",
        unique_code="a37d73e55e8c4775a6e5f9cc4422b33f",
        edb_code="ID00397793",
        source_name="Mysteel",
    ),
    "northeast_gas92_market": IndicatorRef(
        key="northeast_gas92_market",
        name="92# gasoline market price: Northeast",
        unique_code="d2ae0690f74830c09a4988466cbca7fb",
        edb_code="ID00397790",
        source_name="Mysteel",
    ),
}


class IndicatorCatalog:
    def __init__(self, whitelist_path: Path = WHITELIST_PATH) -> None:
        if not whitelist_path.exists():
            raise FileNotFoundError(
                f"Missing whitelist file: {whitelist_path}. Run scripts/build_eta_p0_whitelist.py first."
            )
        payload = json.loads(whitelist_path.read_text(encoding="utf-8"))
        self._items: dict[str, IndicatorRef] = {}
        for item in payload["items"]:
            detail = item.get("detail") or {}
            if not detail:
                continue
            self._items[item["key"]] = IndicatorRef(
                key=item["key"],
                name=item["name"],
                unique_code=detail["UniqueCode"],
                edb_code=detail["EdbCode"],
                source_name=detail["SourceName"],
            )
        self._items.update(EXTRA_INDICATORS)

    def get(self, key: str) -> IndicatorRef:
        if key not in self._items:
            raise KeyError(f"Indicator key not found: {key}")
        return self._items[key]
