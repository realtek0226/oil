from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class HorizonConfig:
    code: str
    label: str
    steps: int
    direction_threshold: float

    def target_date_from(self, as_of_date: date) -> date:
        if self.steps <= 1:
            return (pd.Timestamp(as_of_date) + pd.offsets.BDay(1)).date()
        return (pd.Timestamp(as_of_date) + pd.offsets.BDay(self.steps)).date()


# System default display deadbands. These are not business-confirmed thresholds yet.
HORIZON_CONFIGS: dict[str, HorizonConfig] = {
    "D1": HorizonConfig(code="D1", label="次日", steps=1, direction_threshold=3.0),
    "D3": HorizonConfig(code="D3", label="3日", steps=3, direction_threshold=8.0),
    "W1": HorizonConfig(code="W1", label="1周", steps=5, direction_threshold=12.0),
    "M1": HorizonConfig(code="M1", label="1月", steps=20, direction_threshold=32.0),
}


DEFAULT_HORIZONS = ["D1", "W1", "M1"]
ACTIVE_HORIZONS = set(DEFAULT_HORIZONS)


def resolve_horizon_config(horizon: str) -> HorizonConfig:
    normalized = horizon.strip().upper()
    if normalized not in HORIZON_CONFIGS:
        supported = ", ".join(HORIZON_CONFIGS)
        raise ValueError(f"Unsupported horizon={horizon}. Supported: {supported}")
    return HORIZON_CONFIGS[normalized]
