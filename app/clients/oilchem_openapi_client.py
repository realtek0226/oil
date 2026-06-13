from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any

import requests

from app.core.settings import OilchemOpenApiSettings


FREQUENCY_LABELS = {
    1: "daily",
    2: "weekly",
    3: "monthly",
    4: "quarterly",
    5: "yearly",
    99: "irregular",
}


@dataclass(frozen=True)
class OilchemOpenApiResearchProduct:
    project_quota_id: int
    quota_sample_id: int
    breed_name: str
    quota_name: str
    unit_name: str
    sample_id: str
    sample_name: str
    frequency: int | None
    custom: str | None = None
    custom_id: str | None = None


@dataclass(frozen=True)
class OilchemOpenApiInventoryRecord:
    project_quota_id: int
    quota_sample_id: int
    breed_name: str
    quota_name: str
    unit_name: str
    sample_id: str
    sample_name: str
    frequency: int | None
    value: float | None
    period_start: date | None
    period_end: date | None
    publish_time: datetime | None
    custom: str | None
    custom_id: str | None
    raw_payload: dict[str, Any]
    source: str = "oilchem_openapi_inventory"

    @property
    def observation_date(self) -> date:
        return self.period_end or self.period_start or date.today()

    @property
    def freq_label(self) -> str:
        return FREQUENCY_LABELS.get(int(self.frequency or 99), "irregular")

    def model_dump(self) -> dict[str, Any]:
        return {
            "project_quota_id": self.project_quota_id,
            "quota_sample_id": self.quota_sample_id,
            "breed_name": self.breed_name,
            "quota_name": self.quota_name,
            "unit_name": self.unit_name,
            "sample_id": self.sample_id,
            "sample_name": self.sample_name,
            "frequency": self.frequency,
            "freq_label": self.freq_label,
            "value": self.value,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "observation_date": self.observation_date.isoformat(),
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "custom": self.custom,
            "custom_id": self.custom_id,
            "raw_payload": self.raw_payload,
            "source": self.source,
        }


class OilchemOpenApiClient:
    def __init__(self, settings: OilchemOpenApiSettings) -> None:
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enabled and self.settings.username and self.settings.password)

    def fetch_research_products(self, *, page_size: int = 100) -> list[OilchemOpenApiResearchProduct]:
        products: list[OilchemOpenApiResearchProduct] = []
        page_num = 1
        while True:
            payload = self._get(
                "/research/getProduct",
                {
                    "userName": self.settings.username,
                    "passWord": self.settings.password,
                    "pageNum": page_num,
                    "pageSize": page_size,
                },
            )
            rows = self._extract_list(payload)
            products.extend(self._parse_product(row) for row in rows)
            if len(rows) < page_size:
                break
            page_num += 1
        return products

    def fetch_inventory_records(
        self,
        *,
        start_date: date,
        end_date: date,
        page_size: int = 100,
    ) -> list[OilchemOpenApiInventoryRecord]:
        products = [
            product
            for product in self.fetch_research_products()
            if "库存" in product.quota_name
        ]
        records: list[OilchemOpenApiInventoryRecord] = []
        for product in products:
            page_num = 1
            while True:
                payload = self._post(
                    "/research/productPage",
                    {
                        "pageNum": page_num,
                        "pageSize": page_size,
                        "userName": self.settings.username,
                        "passWord": self.settings.password,
                        "projectQuotaId": product.project_quota_id,
                        "quotaSampleId": product.quota_sample_id,
                        "researchStartDateTime": self._date_to_millis(start_date),
                        "researchEndDateTime": self._date_to_millis(end_date),
                    },
                )
                rows = self._extract_list(payload)
                for row in rows:
                    records.append(self._parse_inventory_record(row, product=product))
                if len(rows) < page_size:
                    break
                page_num += 1
        return records

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.settings.timeout_seconds,
            headers={"User-Agent": "oil-research-openapi/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        self._raise_for_api_error(path, payload)
        return payload

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=self.settings.timeout_seconds,
            headers={"User-Agent": "oil-research-openapi/1.0"},
        )
        response.raise_for_status()
        data = response.json()
        self._raise_for_api_error(path, data)
        return data

    def _raise_for_api_error(self, path: str, payload: dict[str, Any]) -> None:
        status = str(payload.get("status") or payload.get("code") or "")
        if status in {"1", "200"}:
            return
        message = payload.get("message") or payload.get("msg") or payload
        raise RuntimeError(f"OilChem OpenAPI failed for {path}: {message}")

    def _extract_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = payload.get("response")
        if isinstance(response, dict) and isinstance(response.get("list"), list):
            return list(response["list"])
        data = payload.get("data")
        if isinstance(data, list):
            return list(data)
        return []

    def _parse_product(self, row: dict[str, Any]) -> OilchemOpenApiResearchProduct:
        return OilchemOpenApiResearchProduct(
            project_quota_id=int(row.get("projectQuotaId")),
            quota_sample_id=int(row.get("quotaSampleId")),
            breed_name=str(row.get("breedName") or ""),
            quota_name=str(row.get("quotaName") or ""),
            unit_name=str(row.get("unitName") or ""),
            sample_id=str(row.get("sampleId") or ""),
            sample_name=str(row.get("sampleName") or ""),
            frequency=self._int_or_none(row.get("frequency")),
            custom=str(row.get("custom") or "") or None,
            custom_id=str(row.get("customId") or "") or None,
        )

    def _parse_inventory_record(
        self,
        row: dict[str, Any],
        *,
        product: OilchemOpenApiResearchProduct,
    ) -> OilchemOpenApiInventoryRecord:
        return OilchemOpenApiInventoryRecord(
            project_quota_id=int(row.get("projectQuotaId") or product.project_quota_id),
            quota_sample_id=int(row.get("quotaSampleId") or product.quota_sample_id),
            breed_name=str(row.get("breedName") or product.breed_name),
            quota_name=str(row.get("quotaName") or product.quota_name),
            unit_name=str(row.get("unitName") or product.unit_name),
            sample_id=str(row.get("sampleId") or product.sample_id),
            sample_name=str(row.get("sampleName") or product.sample_name),
            frequency=self._int_or_none(row.get("frequency")) or product.frequency,
            value=self._float_or_none(row.get("inputValue")),
            period_start=self._parse_yyyymmdd(row.get("researchStartDate")),
            period_end=self._parse_yyyymmdd(row.get("researchStopDate")),
            publish_time=self._parse_millis(row.get("taskActualFinishTime") or row.get("taskShouldFinishTime")),
            custom=str(row.get("custom") or product.custom or "") or None,
            custom_id=str(row.get("customId") or product.custom_id or "") or None,
            raw_payload=dict(row),
        )

    def _date_to_millis(self, value: date) -> int:
        dt = datetime.combine(value, time(0, 0)).replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    def _parse_yyyymmdd(self, value: Any) -> date | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        try:
            return datetime.strptime(text[:8], "%Y%m%d").date()
        except ValueError:
            return None

    def _parse_millis(self, value: Any) -> datetime | None:
        try:
            if value is None:
                return None
            millis = int(float(value))
            if millis <= 0:
                return None
            return datetime.fromtimestamp(millis / 1000)
        except Exception:
            return None

    def _float_or_none(self, value: Any) -> float | None:
        try:
            if value is None or str(value).strip() == "":
                return None
            return float(str(value).replace(",", ""))
        except Exception:
            return None

    def _int_or_none(self, value: Any) -> int | None:
        try:
            if value is None or str(value).strip() == "":
                return None
            return int(float(value))
        except Exception:
            return None
