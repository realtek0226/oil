from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.clients.oilchem_request_guard import oilchem_post


DEFAULT_STORAGE_STATE = Path("configs/oilchem_storage_state.json")
PRICE_API_URL = "https://dc.oilchem.net/ndc/price/list/queryPricePage"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://dc.oilchem.net",
}


@dataclass(frozen=True)
class OilchemPriceRecord:
    observation_date: date
    publish_time: datetime
    product: str
    product_code: str
    indicator_code: str
    region: str
    region_code: str
    price: float | None
    price_text: str | None
    rise_or_fall: float | None
    rise_or_fall_text: str | None
    price_type: str
    standard: str
    specification: str
    unit: str
    internal_market: str
    business_id: str
    source: str = "oilchem_refined_oil_price_center"

    def model_dump(self) -> dict[str, Any]:
        return {
            "observation_date": self.observation_date.isoformat(),
            "publish_time": self.publish_time.isoformat(),
            "product": self.product,
            "product_code": self.product_code,
            "indicator_code": self.indicator_code,
            "region": self.region,
            "region_code": self.region_code,
            "price": self.price,
            "price_text": self.price_text,
            "rise_or_fall": self.rise_or_fall,
            "rise_or_fall_text": self.rise_or_fall_text,
            "price_type": self.price_type,
            "standard": self.standard,
            "specification": self.specification,
            "unit": self.unit,
            "internal_market": self.internal_market,
            "business_id": self.business_id,
            "source": self.source,
        }


class OilchemPriceClient:
    product_configs = [
        {
            "product": "汽油",
            "product_code": "gasoline92",
            "varieties_id": 3145,
            "specification": "92#",
            "referer": "https://dc.oilchem.net/page/#/list?channelIdNew=1694&name=%E6%B1%BD%E6%B2%B9&businessType=3",
            "indicator_prefix": "gas92",
        },
        {
            "product": "柴油",
            "product_code": "diesel0",
            "varieties_id": 115,
            "standard": "国Ⅵ",
            "referer": "https://dc.oilchem.net/page/#/list?channelIdNew=1695&name=%E6%9F%B4%E6%B2%B9&businessType=3",
            "indicator_prefix": "diesel0",
        },
    ]
    target_regions = [
        ("中国", "NATIONAL", "cn"),
        ("山东", "SHANDONG", "sd"),
        ("华东", "EAST_CHINA", "east_china"),
        ("华南", "SOUTH_CHINA", "south_china"),
        ("华北", "NORTH_CHINA", "north_china"),
        ("华中", "CENTRAL_CHINA", "central_china"),
        ("西北", "NORTHWEST", "northwest"),
        ("西南", "SOUTHWEST", "southwest"),
        ("东北", "NORTHEAST", "northeast"),
    ]

    def __init__(self, storage_state_path: Path | str = DEFAULT_STORAGE_STATE) -> None:
        self.storage_state_path = Path(storage_state_path)

    def fetch_latest_prices(self, *, products: list[str] | None = None, max_pages: int = 3) -> list[OilchemPriceRecord]:
        selected_products = set(products or ["gasoline92", "diesel0"])
        records: list[OilchemPriceRecord] = []
        for config in self.product_configs:
            if config["product_code"] not in selected_products:
                continue
            payloads = self._fetch_product_pages(config=config, max_pages=max_pages)
            rows = self._extract_rows(payloads=payloads, config=config)
            records.extend(rows)
        return records

    def _fetch_product_pages(self, *, config: dict[str, Any], max_pages: int) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for page_num in range(1, max_pages + 1):
            response = oilchem_post(
                PRICE_API_URL,
                headers={**HEADERS, "Referer": str(config["referer"])},
                cookies=self._load_cookies(),
                json={
                    "varietiesId": config["varieties_id"],
                    "businessType": "3",
                    "twoLevelBusinessType": 0,
                    "timeType": 0,
                    "pageNum": page_num,
                    "pageSize": 100,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            row_count = len(self._flatten_rows(payload))
            if row_count:
                payloads.append(payload)
            if row_count < 100:
                break
        return payloads

    def _extract_rows(self, *, payloads: list[dict[str, Any]], config: dict[str, Any]) -> list[OilchemPriceRecord]:
        merged_rows: list[dict[str, Any]] = []
        latest_date: str | None = None
        for payload in payloads:
            merged_rows.extend(self._flatten_rows(payload))
            payload_date = self._latest_date(payload)
            if payload_date and (latest_date is None or payload_date > latest_date):
                latest_date = payload_date
        if latest_date is None:
            return []

        selected: dict[str, tuple[int, OilchemPriceRecord]] = {}
        publish_time = datetime.now()
        observation_date = datetime.strptime(latest_date, "%Y/%m/%d").date()
        for row in merged_rows:
            if not self._row_matches_product(row, config):
                continue
            region = self._row_region(row)
            if not region or not self._row_matches_price_type(row, region):
                continue
            region_code, region_prefix = self._region_codes(region)
            rank = self._selection_rank(row, region)
            price_text, rise_text = self._price_cell(row, latest_date)
            record = OilchemPriceRecord(
                observation_date=observation_date,
                publish_time=publish_time,
                product=str(config["product"]),
                product_code=str(config["product_code"]),
                indicator_code=f"{region_prefix}_{config['indicator_prefix']}_market",
                region=region,
                region_code=region_code,
                price=self._to_float(price_text),
                price_text=price_text,
                rise_or_fall=self._to_float(rise_text),
                rise_or_fall_text=rise_text,
                price_type=str(row.get("priceTypeName") or ""),
                standard=str(row.get("standard") or ""),
                specification=str(row.get("specificationsName") or ""),
                unit=str(row.get("unitValuationName") or "元/吨"),
                internal_market=str(row.get("internalMarketName") or ""),
                business_id=str(row.get("businessId") or row.get("id") or ""),
            )
            current = selected.get(region)
            if current is None or rank < current[0]:
                selected[region] = (rank, record)
        return [selected[region][1] for region, _, _ in self.target_regions if region in selected]

    def _row_matches_product(self, row: dict[str, Any], config: dict[str, Any]) -> bool:
        if config["product_code"] == "gasoline92":
            return self._clean(row.get("specificationsName")) == "92#"
        return "国Ⅵ" in self._clean(row.get("standard")) or "0#" in self._clean(row.get("specificationsName"))

    def _row_matches_price_type(self, row: dict[str, Any], region: str) -> bool:
        price_type = self._clean(row.get("priceTypeName"))
        if region == "山东":
            return price_type == "库提现汇市场价"
        return price_type == "库提现汇"

    def _row_region(self, row: dict[str, Any]) -> str | None:
        for value in (row.get("internalMarketName"), row.get("regionName"), row.get("marketName")):
            region = self._normalize_region(value)
            if any(region == item[0] for item in self.target_regions):
                return region
        return None

    def _region_codes(self, region: str) -> tuple[str, str]:
        for name, region_code, prefix in self.target_regions:
            if name == region:
                return region_code, prefix
        return region.upper(), region.upper().lower()

    def _selection_rank(self, row: dict[str, Any], region: str) -> int:
        internal = str(row.get("internalMarketName") or "").strip()
        region_name = self._normalize_region(row.get("regionName"))
        if internal == region:
            return 0
        if internal.startswith(f"{region}-"):
            return 1
        if region_name == region:
            return 2
        return 3

    def _latest_date(self, payload: dict[str, Any]) -> str | None:
        dates: list[str] = []
        for item in payload.get("response", {}).get("priceHeadList") or []:
            for key in ("cnFiled", "cnField", "field", "name", "label"):
                value = str(item.get(key) or "")
                if self._is_date_key(value):
                    dates.append(value)
        for row in self._flatten_rows(payload):
            for key in row.keys():
                if self._is_date_key(str(key)):
                    dates.append(str(key))
        return sorted(dates)[-1] if dates else None

    def _price_cell(self, row: dict[str, Any], latest_date: str) -> tuple[str | None, str | None]:
        cell = row.get(latest_date) or {}
        price_map = cell.get("price") or {}
        rise_map = cell.get("dataRiseOrFall") or {}
        price = price_map.get("主流价") if isinstance(price_map, dict) else None
        rise = rise_map.get("主流价") if isinstance(rise_map, dict) else None
        if price is None and isinstance(price_map, dict) and price_map:
            price = next(iter(price_map.values()))
        if rise is None and isinstance(rise_map, dict) and rise_map:
            rise = next(iter(rise_map.values()))
        return (str(price) if price is not None else None, str(rise) if rise is not None else None)

    def _flatten_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        body = payload.get("response", {}).get("priceBodyMap") or {}
        rows: list[dict[str, Any]] = []
        for items in body.values():
            if isinstance(items, list):
                rows.extend([item for item in items if isinstance(item, dict)])
        return rows

    def _load_cookies(self) -> dict[str, str]:
        if not self.storage_state_path.exists():
            return {}
        try:
            payload = json.loads(self.storage_state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        cookies: dict[str, str] = {}
        for item in payload.get("cookies", []):
            domain = str(item.get("domain") or "")
            name = str(item.get("name") or "")
            value = str(item.get("value") or "")
            if name and value and "oilchem.net" in domain:
                cookies[name] = value
        return cookies

    def _normalize_region(self, value: Any) -> str:
        text = str(value or "").strip()
        for word in ("地区", "省", "市", "自治区", "回族", "维吾尔", "壮族"):
            text = text.replace(word, "")
        return text.split("-", 1)[0].strip()

    def _clean(self, value: Any) -> str:
        return "".join(str(value or "").split())

    def _is_date_key(self, value: str) -> bool:
        if len(value) != 10:
            return False
        try:
            datetime.strptime(value, "%Y/%m/%d")
            return True
        except ValueError:
            return False

    def _to_float(self, value: Any) -> float | None:
        try:
            if value in (None, "", "-", "询价中"):
                return None
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None
