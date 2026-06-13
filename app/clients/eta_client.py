from __future__ import annotations

import base64
import hashlib
import hmac
import random
import string
import time
from datetime import date, datetime
from typing import Any

import pandas as pd
import requests

from app.core.settings import EtaSettings
from app.services.indicator_catalog import IndicatorRef


class EtaClient:
    def __init__(self, settings: EtaSettings) -> None:
        self.settings = settings

    def _nonce(self, length: int = 32) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    def _headers(self) -> dict[str, str]:
        nonce = self._nonce()
        timestamp = int(time.time())
        sign_str = f"appid={self.settings.appid}&nonce={nonce}&timestamp={timestamp}"
        digest = hmac.new(
            self.settings.secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.urlsafe_b64encode(digest).decode("utf-8")
        return {
            "AppId": self.settings.appid,
            "Nonce": nonce,
            "Timestamp": str(timestamp),
            "Signature": signature,
        }

    def _get(self, path: str, params: dict[str, Any], timeout_seconds: float | tuple[float, float] = 30) -> dict[str, Any]:
        response = requests.get(
            f"{self.settings.base_url.rstrip('/')}{path}",
            headers=self._headers(),
            params=params,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("Ret") != 200:
            raise RuntimeError(f"ETA API failed for {path}: {payload}")
        return payload

    def get_detail(
        self,
        indicator: IndicatorRef,
        timeout_seconds: float | tuple[float, float] = 30,
    ) -> dict[str, Any]:
        return self._get(
            "/v1/edb/detail",
            {"UniqueCode": indicator.unique_code, "EdbCode": indicator.edb_code},
            timeout_seconds=timeout_seconds,
        )["Data"]

    def get_series(
        self,
        indicator: IndicatorRef,
        start_date: date,
        end_date: date | None = None,
        timeout_seconds: float | tuple[float, float] = 30,
    ) -> pd.DataFrame:
        payload = self._get(
            "/v1/edb/data",
            {"UniqueCode": indicator.unique_code, "StartDate": start_date.isoformat()},
            timeout_seconds=timeout_seconds,
        )
        rows = payload.get("Data") or []
        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=["date", "value", "update_time"])
        frame = frame.rename(columns={"DataTime": "date", "Value": "value", "UpdateTime": "update_time"})
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        frame["value"] = frame["value"].astype(float)
        frame["update_time"] = pd.to_datetime(frame["update_time"], errors="coerce")
        if end_date is not None:
            frame = frame[frame["date"] <= end_date]
        return frame.sort_values("date").reset_index(drop=True)

    def get_latest_value(
        self,
        indicator: IndicatorRef,
        as_of_date: date,
        timeout_seconds: float | tuple[float, float] = 30,
    ) -> float | None:
        frame = self.get_series(
            indicator,
            start_date=as_of_date.replace(day=1),
            end_date=as_of_date,
            timeout_seconds=timeout_seconds,
        )
        if frame.empty:
            detail = self.get_detail(indicator, timeout_seconds=timeout_seconds)
            latest_date = datetime.strptime(detail["LatestDate"], "%Y-%m-%d").date()
            if latest_date <= as_of_date:
                return float(detail["LatestValue"])
            return None
        return float(frame.iloc[-1]["value"])
