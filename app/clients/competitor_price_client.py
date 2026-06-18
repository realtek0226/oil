from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests


DEFAULT_COMPETITOR_PRICE_URL = "http://10.189.2.50:8087/price/openapi/competitorPrice"


@dataclass(frozen=True)
class CompetitorPriceItem:
    observation_date: date
    product: str
    product_code: str
    company: str
    yesterday_price: float | None
    today_price: float | None
    source: str = "competitor_price_openapi"

    def model_dump(self) -> dict[str, Any]:
        return {
            "observation_date": self.observation_date.isoformat(),
            "product": self.product,
            "product_code": self.product_code,
            "company": self.company,
            "yesterday_price": self.yesterday_price,
            "today_price": self.today_price,
            "source": self.source,
        }


class CompetitorPriceClient:
    def __init__(self, base_url: str = DEFAULT_COMPETITOR_PRICE_URL, timeout_seconds: float = 20.0) -> None:
        self.base_url = base_url.strip() or DEFAULT_COMPETITOR_PRICE_URL
        self.timeout_seconds = timeout_seconds

    def fetch_day(self, target_date: date) -> list[CompetitorPriceItem]:
        response = requests.get(
            self.base_url,
            params={"day": target_date.isoformat()},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(str(payload.get("msg") or "competitor price api failed"))

        data = payload.get("data") or {}
        observation_date = self._parse_date(data.get("day")) or target_date
        items: list[CompetitorPriceItem] = []
        for product_entry in data.get("products") or []:
            product = str(product_entry.get("product") or "").strip()
            product_code = self._product_code(product)
            if not product_code:
                continue
            for row in product_entry.get("items") or []:
                company = str(row.get("company") or "").strip()
                if not company:
                    continue
                items.append(
                    CompetitorPriceItem(
                        observation_date=observation_date,
                        product=product,
                        product_code=product_code,
                        company=company,
                        yesterday_price=self._to_float(row.get("yesterdayPrice")),
                        today_price=self._to_float(row.get("todayPrice")),
                    )
                )
        return items

    def _product_code(self, product: str) -> str | None:
        if product.startswith("92#"):
            return "gasoline92"
        if product.startswith("0#"):
            return "diesel0"
        return None

    def _parse_date(self, value: Any) -> date | None:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def _to_float(self, value: Any) -> float | None:
        try:
            if value in (None, "", "-"):
                return None
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None
