from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import requests


class ChinaMoneyCnyMidClient:
    BASE_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew"

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def get_usd_cny_mid_series(self, *, start_date: date, end_date: date) -> pd.DataFrame:
        rows = []
        page_num = 1
        page_size = 30
        while True:
            payload = self._fetch_page(
                start_date=start_date,
                end_date=end_date,
                page_num=page_num,
                page_size=page_size,
            )
            for record in payload.get("records") or []:
                values = record.get("values") or []
                if not values:
                    continue
                try:
                    rows.append(
                        {
                            "date": pd.Timestamp(record.get("date")).date(),
                            "cny_mid_rate": float(values[0]),
                        }
                    )
                except (TypeError, ValueError):
                    continue
            data = payload.get("data") or {}
            page_total = int(data.get("pageTotal") or 1)
            if page_num >= page_total:
                break
            page_num += 1
        if not rows:
            return pd.DataFrame(columns=["date", "cny_mid_rate"])
        frame = pd.DataFrame(rows).dropna(subset=["date", "cny_mid_rate"])
        return frame.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    def _fetch_page(self, *, start_date: date, end_date: date, page_num: int, page_size: int) -> dict[str, Any]:
        response = requests.get(
            self.BASE_URL,
            params={
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "currency": "USD/CNY",
                "pageNum": page_num,
                "pageSize": page_size,
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.chinamoney.com.cn/chinese/bkccpr/",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
