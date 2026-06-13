from __future__ import annotations

from datetime import date, datetime
from typing import Any

import requests


class WindPriceClient:
    def __init__(
        self,
        base_url: str,
        default_code: str = "B.IPE",
        default_fields: str = "rt_latest,rt_chg,rt_pct_chg",
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_code = default_code
        self.default_fields = default_fields
        self.timeout_seconds = timeout_seconds

    def get_price(self, code: str | None = None, fields: str | None = None) -> dict[str, Any]:
        price_code = code or self.default_code
        field_value = fields or self.default_fields
        response = requests.get(
            f"{self.base_url}/price",
            params={"code": price_code, "field": field_value},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Wind price API returned non-object payload: {payload!r}")
        latest = self._float_or_none(payload.get("rt_latest"))
        if latest is None:
            raise RuntimeError(f"Wind price API missing rt_latest: {payload!r}")
        return {
            "code": str(payload.get("code") or price_code),
            "rt_latest": latest,
            "rt_chg": self._float_or_none(payload.get("rt_chg")),
            "rt_pct_chg": self._float_or_none(payload.get("rt_pct_chg")),
            "time": self._parse_time(payload.get("time")),
            "cached": bool(payload.get("cached", False)),
            "raw": payload,
        }

    def get_history(
        self,
        *,
        code: str | None = None,
        fields: str = "settle",
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        price_code = code or self.default_code
        response = requests.get(
            f"{self.base_url}/wsd",
            params={
                "code": price_code,
                "fields": fields,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            timeout=max(float(self.timeout_seconds), 20.0),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Wind WSD API returned non-object payload: {payload!r}")
        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"Wind WSD API missing data list: {payload!r}")
        records: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            record_date = self._parse_date(item.get("date"))
            if record_date is None:
                continue
            record: dict[str, Any] = {
                "code": str(payload.get("code") or price_code),
                "date": record_date,
                "raw": item,
            }
            for field in [part.strip() for part in fields.split(",") if part.strip()]:
                record[field] = self._float_or_none(item.get(field))
            records.append(record)
        return records

    def _float_or_none(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_time(self, value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _parse_date(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).strip()[:10]).date()
        except ValueError:
            return None
