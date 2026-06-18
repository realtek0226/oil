from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.clients.oilchem_request_guard import oilchem_get


LIST_URL = "https://oil.oilchem.net/oil/refinedoil.shtml"
SEARCH_URL = "https://search.oilchem.net/article/search"
DEFAULT_STORAGE_STATE = Path("configs/oilchem_storage_state.json")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


@dataclass(frozen=True)
class ProductionSalesRatioRecord:
    observation_date: date
    publish_time: datetime | None
    title: str
    url: str
    gasoline_ratio: float | None
    gasoline_previous_ratio: float | None
    gasoline_change_pct: float | None
    diesel_ratio: float | None
    diesel_previous_ratio: float | None
    diesel_change_pct: float | None
    source: str = "oilchem_production_sales_ratio"

    def model_dump(self) -> dict[str, Any]:
        return {
            "observation_date": self.observation_date.isoformat(),
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "title": self.title,
            "url": self.url,
            "gasoline_ratio": self.gasoline_ratio,
            "gasoline_previous_ratio": self.gasoline_previous_ratio,
            "gasoline_change_pct": self.gasoline_change_pct,
            "diesel_ratio": self.diesel_ratio,
            "diesel_previous_ratio": self.diesel_previous_ratio,
            "diesel_change_pct": self.diesel_change_pct,
            "source": self.source,
        }


@dataclass(frozen=True)
class WeeklyRefineryMetricRecord:
    observation_date: date
    period_start: date | None
    period_end: date | None
    publish_time: datetime | None
    title: str
    url: str
    metric_type: str
    capacity_utilization: float | None = None
    capacity_utilization_wow_pct: float | None = None
    capacity_utilization_yoy_pct: float | None = None
    capacity_utilization_ex_large: float | None = None
    capacity_utilization_ex_large_wow_pct: float | None = None
    capacity_utilization_ex_large_yoy_pct: float | None = None
    refining_profit: float | None = None
    refining_profit_wow_pct: float | None = None
    refining_profit_yoy_pct: float | None = None
    crude_cost: float | None = None
    crude_cost_change: float | None = None
    comprehensive_revenue: float | None = None
    comprehensive_revenue_change: float | None = None
    source: str = "oilchem_weekly_refinery_metrics"

    def model_dump(self) -> dict[str, Any]:
        return {
            "observation_date": self.observation_date.isoformat(),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "title": self.title,
            "url": self.url,
            "metric_type": self.metric_type,
            "capacity_utilization": self.capacity_utilization,
            "capacity_utilization_wow_pct": self.capacity_utilization_wow_pct,
            "capacity_utilization_yoy_pct": self.capacity_utilization_yoy_pct,
            "capacity_utilization_ex_large": self.capacity_utilization_ex_large,
            "capacity_utilization_ex_large_wow_pct": self.capacity_utilization_ex_large_wow_pct,
            "capacity_utilization_ex_large_yoy_pct": self.capacity_utilization_ex_large_yoy_pct,
            "refining_profit": self.refining_profit,
            "refining_profit_wow_pct": self.refining_profit_wow_pct,
            "refining_profit_yoy_pct": self.refining_profit_yoy_pct,
            "crude_cost": self.crude_cost,
            "crude_cost_change": self.crude_cost_change,
            "comprehensive_revenue": self.comprehensive_revenue,
            "comprehensive_revenue_change": self.comprehensive_revenue_change,
            "source": self.source,
        }


@dataclass(frozen=True)
class MaintenancePlanRecord:
    observation_date: date
    publish_time: datetime | None
    title: str
    url: str
    refinery_scope: str
    active_capacity: float
    active_count: int
    next_30d_start_capacity: float
    next_30d_start_count: int
    next_30d_end_capacity: float
    next_30d_end_count: int
    rows: list[dict[str, Any]]
    source: str = "oilchem_refinery_maintenance_plan"

    def model_dump(self) -> dict[str, Any]:
        return {
            "observation_date": self.observation_date.isoformat(),
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "title": self.title,
            "url": self.url,
            "refinery_scope": self.refinery_scope,
            "active_capacity": self.active_capacity,
            "active_count": self.active_count,
            "next_30d_start_capacity": self.next_30d_start_capacity,
            "next_30d_start_count": self.next_30d_start_count,
            "next_30d_end_capacity": self.next_30d_end_capacity,
            "next_30d_end_count": self.next_30d_end_count,
            "rows": self.rows,
            "source": self.source,
        }


@dataclass(frozen=True)
class InventoryRecord:
    observation_date: date
    publish_time: datetime | None
    title: str
    url: str
    total_inventory: float | None
    gasoline_inventory: float | None
    gasoline_inventory_change_mom: float | None
    gasoline_inventory_capacity_rate: float | None
    diesel_inventory: float | None
    diesel_inventory_change_mom: float | None
    diesel_inventory_capacity_rate: float | None
    source: str = "oilchem_refinery_inventory"

    def model_dump(self) -> dict[str, Any]:
        return {
            "observation_date": self.observation_date.isoformat(),
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "title": self.title,
            "url": self.url,
            "total_inventory": self.total_inventory,
            "gasoline_inventory": self.gasoline_inventory,
            "gasoline_inventory_change_mom": self.gasoline_inventory_change_mom,
            "gasoline_inventory_capacity_rate": self.gasoline_inventory_capacity_rate,
            "diesel_inventory": self.diesel_inventory,
            "diesel_inventory_change_mom": self.diesel_inventory_change_mom,
            "diesel_inventory_capacity_rate": self.diesel_inventory_capacity_rate,
            "source": self.source,
        }


@dataclass(frozen=True)
class OilchemSpotDailyReportRecord:
    observation_date: date
    publish_time: datetime | None
    title: str
    url: str
    content: str
    labels: dict[str, Any]
    source: str = "oilchem_shandong_spot_daily_report"

    def model_dump(self) -> dict[str, Any]:
        return {
            "observation_date": self.observation_date.isoformat(),
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "publish_date": self.publish_time.isoformat() if self.publish_time else None,
            "headline": self.title,
            "title": self.title,
            "url": self.url,
            "summary": self.content[:300],
            "content": self.content,
            "labels": self.labels,
            "source": self.source,
            "category": "山东成品油日评",
        }


class OilchemProductionSalesClient:
    """Fetch Shandong independent refinery daily production-sales ratio from Oilchem."""

    title_pattern = re.compile(r"\[产销率\][:：]山东地炼成品油日度产销率数据（(?P<yyyymmdd>\d{8})）")
    capacity_title_pattern = re.compile(
        r"\[产能利用率\][:：]山东地炼周度产能利用率数据（(?P<start>\d{8})-(?P<end>\d{8})）"
    )
    profit_title_pattern = re.compile(
        r"\[炼油利润\][:：]山东地炼综合装置炼油利润周数据统计（(?P<yyyymmdd>\d{8})）"
    )
    maintenance_title_pattern = re.compile(
        "\\[\u88c5\u7f6e\u52a8\u6001\\][:\uFF1A]?(?P<scope>\u5c71\u4e1c\u5730\u70bc\u88c5\u7f6e|\u5730\u65b9\u70bc\u5382|\u4e3b\u8425\u70bc\u5382\u88c5\u7f6e)\u68c0\u4fee\u8ba1\u5212\u8868(?:[\uFF08(](?P<yyyymmdd>\\d{8})[\uFF09)])?"
    )
    inventory_title_pattern = re.compile(
        r"\[库存\][:：]山东独立炼厂成品油库存数据统计（(?P<yyyymmdd>\d{8})）"
    )

    def __init__(self, storage_state_path: Path | str = DEFAULT_STORAGE_STATE) -> None:
        self.storage_state_path = Path(storage_state_path)
        self._cache_date: date | None = None
        self._cache_records: list[ProductionSalesRatioRecord] = []
        self._weekly_cache_date: date | None = None
        self._weekly_cache_records: list[WeeklyRefineryMetricRecord] = []
        self._maintenance_cache_records_by_scope: dict[tuple[str, date], list[MaintenancePlanRecord]] = {}
        self._inventory_cache_date: date | None = None
        self._inventory_cache_records: list[InventoryRecord] = []

    def fetch_recent(self, limit: int = 10) -> list[ProductionSalesRatioRecord]:
        today = date.today()
        if self._cache_date == today and self._cache_records:
            return self._cache_records[:limit]

        links = self.fetch_recent_links(limit=limit)
        records: list[ProductionSalesRatioRecord] = []
        for item in links:
            record = self.fetch_detail(item["url"], title=item["title"], observation_date=item["observation_date"])
            if record:
                records.append(record)

        self._cache_date = today
        self._cache_records = records
        return records[:limit]

    def fetch_weekly_metrics(self, limit: int = 5) -> list[WeeklyRefineryMetricRecord]:
        today = date.today()
        if self._weekly_cache_date == today and self._weekly_cache_records:
            return self._weekly_cache_records[: limit * 2]

        records: list[WeeklyRefineryMetricRecord] = []
        for metric_type in ("capacity_utilization", "refining_profit"):
            for item in self.fetch_weekly_metric_links(metric_type=metric_type, limit=limit):
                record = self.fetch_weekly_metric_detail(
                    item["url"],
                    title=item["title"],
                    metric_type=metric_type,
                    observation_date=item["observation_date"],
                    period_start=item.get("period_start"),
                    period_end=item.get("period_end"),
                )
                if record:
                    records.append(record)

        records.sort(key=lambda item: (item.observation_date, item.metric_type), reverse=True)
        self._weekly_cache_date = today
        self._weekly_cache_records = records
        return records[: limit * 2]

    def fetch_maintenance_plans(self, limit: int = 3, refinery_scope: str = "independent") -> list[MaintenancePlanRecord]:
        today = date.today()
        cache_key = (refinery_scope, today)
        if cache_key in self._maintenance_cache_records_by_scope:
            return self._maintenance_cache_records_by_scope[cache_key][:limit]

        records: list[MaintenancePlanRecord] = []
        for item in self.fetch_maintenance_plan_links(limit=limit, refinery_scope=refinery_scope):
            record = self.fetch_maintenance_plan_detail(
                item["url"],
                title=item["title"],
                observation_date=item["observation_date"],
                refinery_scope=refinery_scope,
            )
            if record:
                records.append(record)
        records.sort(key=lambda item: item.observation_date, reverse=True)
        self._maintenance_cache_records_by_scope[cache_key] = records
        return records[:limit]

    def fetch_inventory_records(self, limit: int = 3) -> list[InventoryRecord]:
        today = date.today()
        if self._inventory_cache_date == today and self._inventory_cache_records:
            return self._inventory_cache_records[:limit]

        records: list[InventoryRecord] = []
        for item in self.fetch_inventory_links(limit=limit):
            record = self.fetch_inventory_detail(
                item["url"],
                title=item["title"],
                observation_date=item["observation_date"],
            )
            if record:
                records.append(record)
        records.sort(key=lambda item: item.observation_date, reverse=True)
        self._inventory_cache_date = today
        self._inventory_cache_records = records
        return records[:limit]

    def fetch_spot_daily_reports(self, limit: int = 5) -> list[OilchemSpotDailyReportRecord]:
        records: list[OilchemSpotDailyReportRecord] = []
        for item in self.fetch_spot_daily_report_links(limit=limit):
            record = self.fetch_spot_daily_report_detail(
                item["url"],
                title=item["title"],
                observation_date=item["observation_date"],
                publish_time=item.get("publish_time"),
            )
            if record:
                records.append(record)
        records.sort(key=lambda item: item.publish_time or datetime.combine(item.observation_date, datetime.min.time()), reverse=True)
        return records[:limit]

    def fetch_spot_daily_report_links(self, limit: int = 5) -> list[dict[str, Any]]:
        queries = [
            "山东成品油日评",
            "山东地炼汽柴油日评",
            "山东独立炼厂 汽柴油 日评",
            "山东地炼 成品油 日评 出货 成交",
        ]
        if limit <= 1:
            queries = queries[:1]
        links_by_url: dict[str, dict[str, Any]] = {}
        for query in queries:
            response = oilchem_get(
                SEARCH_URL,
                params={
                    "keyword": query,
                    "pageNo": 1,
                    "pageSize": 10,
                    "highlightFields": "title,content",
                },
                headers=HEADERS,
                cookies=self._load_cookies(),
                timeout=30,
            )
            response.raise_for_status()
            for item in response.json().get("response", {}).get("list", []):
                title = self._clean_text(re.sub(r"<[^>]+>", "", str(item.get("title") or "")))
                score = self._score_spot_daily_report_result(title, str(item.get("content") or ""))
                if score < 20:
                    continue
                raw_url = str(item.get("linkUrl") or item.get("url") or item.get("articleUrl") or "")
                url = urljoin("https://www.oilchem.net/", raw_url)
                if not url:
                    continue
                publish_time = self._timestamp_from_millis(item.get("publishTime"))
                observation_date = self._extract_spot_report_date(title) or (publish_time.date() if publish_time else date.today())
                current = links_by_url.get(url)
                if current and current.get("score", 0) >= score:
                    continue
                links_by_url[url] = {
                    "title": title,
                    "url": url,
                    "observation_date": observation_date,
                    "publish_time": publish_time,
                    "score": score,
                }
        links = list(links_by_url.values())
        links.sort(key=lambda item: item.get("publish_time") or datetime.combine(item["observation_date"], datetime.min.time()), reverse=True)
        return links[:limit]

    def fetch_spot_daily_report_detail(
        self,
        url: str,
        *,
        title: str,
        observation_date: date,
        publish_time: datetime | None = None,
    ) -> OilchemSpotDailyReportRecord | None:
        response = oilchem_get(url, headers=HEADERS, cookies=self._load_cookies(), timeout=30)
        response.raise_for_status()
        html = response.content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        text = self._extract_spot_report_main_text(soup.get_text(" ", strip=True))
        if len(text) < 200:
            return None
        effective_publish_time = publish_time or self._extract_spot_report_publish_time(text)
        return OilchemSpotDailyReportRecord(
            observation_date=observation_date,
            publish_time=effective_publish_time,
            title=title,
            url=url,
            content=text,
            labels=self._extract_spot_report_rule_labels(text),
        )

    def fetch_inventory_links(self, limit: int = 3) -> list[dict[str, Any]]:
        response = oilchem_get(
            SEARCH_URL,
            params={
                "keyword": "山东独立炼厂成品油库存数据统计",
                "pageNo": 1,
                "pageSize": max(limit, 1),
                "highlightFields": "title,content",
            },
            headers=HEADERS,
            cookies=self._load_cookies(),
            timeout=30,
        )
        response.raise_for_status()
        items = response.json().get("response", {}).get("list", [])

        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            title = self._clean_text(str(item.get("title") or ""))
            match = self.inventory_title_pattern.search(title)
            if not match:
                continue
            raw_url = str(item.get("linkUrl") or item.get("url") or item.get("articleUrl") or "")
            url = urljoin("https://www.oilchem.net/", raw_url)
            if url in seen:
                continue
            seen.add(url)
            links.append(
                {
                    "title": title,
                    "url": url,
                    "observation_date": datetime.strptime(match.group("yyyymmdd"), "%Y%m%d").date(),
                }
            )
        links.sort(key=lambda item: item["observation_date"], reverse=True)
        return links[:limit]

    def fetch_maintenance_plan_links(self, limit: int = 3, refinery_scope: str = "local") -> list[dict[str, Any]]:
        keyword_by_scope = {
            "main": "主营炼厂装置检修计划",
            "local": "地方炼厂检修计划",
        }
        keyword = keyword_by_scope.get(refinery_scope, "地方炼厂检修计划")
        response = oilchem_get(
            SEARCH_URL,
            params={
                "keyword": keyword,
                "pageNo": 1,
                "pageSize": max(limit, 1),
                "highlightFields": "title,content",
            },
            headers=HEADERS,
            cookies=self._load_cookies(),
            timeout=30,
        )
        response.raise_for_status()
        items = response.json().get("response", {}).get("list", [])

        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            title = self._clean_text(str(item.get("title") or ""))
            if refinery_scope == "main" and "主营炼厂装置检修计划表" not in title:
                continue
            if refinery_scope != "main" and "地方炼厂检修计划表" not in title:
                continue
            match = self.maintenance_title_pattern.search(title)
            publish_time = self._timestamp_from_millis(item.get("publishTime"))
            if match and match.group("yyyymmdd"):
                observation_date = datetime.strptime(match.group("yyyymmdd"), "%Y%m%d").date()
            else:
                observation_date = publish_time.date() if publish_time else date.today()
            raw_url = str(item.get("linkUrl") or item.get("url") or item.get("articleUrl") or "")
            url = urljoin("https://www.oilchem.net/", raw_url)
            if url in seen:
                continue
            seen.add(url)
            links.append(
                {
                    "title": title,
                    "url": url,
                    "observation_date": observation_date,
                }
            )
        links.sort(key=lambda item: item["observation_date"], reverse=True)
        return links[:limit]

    def fetch_weekly_metric_links(self, *, metric_type: str, limit: int = 5) -> list[dict[str, Any]]:
        keyword = (
            "山东地炼周度产能利用率数据"
            if metric_type == "capacity_utilization"
            else "山东地炼综合装置炼油利润周数据统计"
        )
        response = oilchem_get(
            SEARCH_URL,
            params={
                "keyword": keyword,
                "pageNo": 1,
                "pageSize": max(limit, 1),
                "highlightFields": "title,content",
            },
            headers=HEADERS,
            cookies=self._load_cookies(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("response", {}).get("list", [])

        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        title_pattern = self.capacity_title_pattern if metric_type == "capacity_utilization" else self.profit_title_pattern
        for item in items:
            title = self._clean_text(str(item.get("title") or ""))
            match = title_pattern.search(title)
            if not match:
                continue
            raw_url = str(item.get("linkUrl") or item.get("url") or item.get("articleUrl") or "")
            url = urljoin("https://www.oilchem.net/", raw_url)
            if url in seen:
                continue
            seen.add(url)
            if metric_type == "capacity_utilization":
                period_start = datetime.strptime(match.group("start"), "%Y%m%d").date()
                period_end = datetime.strptime(match.group("end"), "%Y%m%d").date()
                observation_date = period_end
            else:
                period_start = None
                period_end = None
                observation_date = datetime.strptime(match.group("yyyymmdd"), "%Y%m%d").date()
            links.append(
                {
                    "title": title,
                    "url": url,
                    "observation_date": observation_date,
                    "period_start": period_start,
                    "period_end": period_end,
                }
            )
        links.sort(key=lambda item: item["observation_date"], reverse=True)
        return links[:limit]

    def fetch_recent_links(self, limit: int = 20) -> list[dict[str, Any]]:
        response = oilchem_get(LIST_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        text = response.content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")

        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            title = self._clean_text(anchor.get_text(" ", strip=True))
            match = self.title_pattern.search(title)
            if not match:
                continue
            url = urljoin(response.url, anchor["href"])
            if url in seen:
                continue
            seen.add(url)
            links.append(
                {
                    "title": title,
                    "url": url,
                    "observation_date": datetime.strptime(match.group("yyyymmdd"), "%Y%m%d").date(),
                }
            )
            if len(links) >= limit:
                break
        links.sort(key=lambda item: item["observation_date"], reverse=True)
        return links[:limit]

    def fetch_detail(
        self,
        url: str,
        *,
        title: str | None = None,
        observation_date: date | None = None,
    ) -> ProductionSalesRatioRecord | None:
        response = oilchem_get(url, headers=HEADERS, cookies=self._load_cookies(), timeout=30)
        response.raise_for_status()
        text = response.content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")
        page_title = title or self._extract_title(soup)
        obs_date = observation_date or self._extract_observation_date(page_title)
        if obs_date is None:
            return None

        table_rows = self._extract_ratio_rows(soup)
        if not table_rows:
            return ProductionSalesRatioRecord(
                observation_date=obs_date,
                publish_time=self._extract_publish_time(soup),
                title=page_title,
                url=url,
                gasoline_ratio=None,
                gasoline_previous_ratio=None,
                gasoline_change_pct=None,
                diesel_ratio=None,
                diesel_previous_ratio=None,
                diesel_change_pct=None,
            )

        gasoline = table_rows.get("汽油", {})
        diesel = table_rows.get("柴油", {})
        return ProductionSalesRatioRecord(
            observation_date=obs_date,
            publish_time=self._extract_publish_time(soup),
            title=page_title,
            url=url,
            gasoline_ratio=gasoline.get("current"),
            gasoline_previous_ratio=gasoline.get("previous"),
            gasoline_change_pct=gasoline.get("change"),
            diesel_ratio=diesel.get("current"),
            diesel_previous_ratio=diesel.get("previous"),
            diesel_change_pct=diesel.get("change"),
        )

    def fetch_weekly_metric_detail(
        self,
        url: str,
        *,
        title: str,
        metric_type: str,
        observation_date: date,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> WeeklyRefineryMetricRecord | None:
        response = oilchem_get(url, headers=HEADERS, cookies=self._load_cookies(), timeout=30)
        response.raise_for_status()
        text = response.content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")
        page_text = self._clean_text(soup.get_text(" ", strip=True))
        publish_time = self._extract_publish_time(soup)

        if metric_type == "capacity_utilization":
            values = self._parse_capacity_utilization(page_text)
            return WeeklyRefineryMetricRecord(
                observation_date=observation_date,
                period_start=period_start,
                period_end=period_end,
                publish_time=publish_time,
                title=title,
                url=url,
                metric_type=metric_type,
                **values,
            )
        if metric_type == "refining_profit":
            values = self._parse_refining_profit(page_text)
            return WeeklyRefineryMetricRecord(
                observation_date=observation_date,
                period_start=period_start,
                period_end=period_end,
                publish_time=publish_time,
                title=title,
                url=url,
                metric_type=metric_type,
                **values,
            )
        return None

    def fetch_maintenance_plan_detail(
        self,
        url: str,
        *,
        title: str,
        observation_date: date,
        refinery_scope: str = "independent",
    ) -> MaintenancePlanRecord | None:
        response = oilchem_get(url, headers=HEADERS, cookies=self._load_cookies(), timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content.decode("utf-8", errors="ignore"), "html.parser")
        rows = self._extract_maintenance_rows(soup=soup, observation_date=observation_date)
        if not rows:
            return None
        active_rows = [row for row in rows if row["active"]]
        next_start_rows = [row for row in rows if row["next_30d_start"]]
        next_end_rows = [row for row in rows if row["next_30d_end"]]
        return MaintenancePlanRecord(
            observation_date=observation_date,
            publish_time=self._extract_publish_time(soup),
            title=title,
            url=url,
            refinery_scope=refinery_scope,
            active_capacity=round(sum(float(row["capacity"]) for row in active_rows), 4),
            active_count=len(active_rows),
            next_30d_start_capacity=round(sum(float(row["capacity"]) for row in next_start_rows), 4),
            next_30d_start_count=len(next_start_rows),
            next_30d_end_capacity=round(sum(float(row["capacity"]) for row in next_end_rows), 4),
            next_30d_end_count=len(next_end_rows),
            rows=rows,
            source=(
                "oilchem_main_refinery_maintenance_plan"
                if refinery_scope == "main"
                else "oilchem_local_refinery_maintenance_plan"
            ),
        )

    def fetch_inventory_detail(
        self,
        url: str,
        *,
        title: str,
        observation_date: date,
    ) -> InventoryRecord | None:
        response = oilchem_get(url, headers=HEADERS, cookies=self._load_cookies(), timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content.decode("utf-8", errors="ignore"), "html.parser")
        page_text = self._clean_text(soup.get_text(" ", strip=True))
        values = self._parse_inventory_text(page_text)
        if not any(value is not None for value in values.values()):
            return None
        return InventoryRecord(
            observation_date=observation_date,
            publish_time=self._extract_publish_time(soup),
            title=title,
            url=url,
            **values,
        )

    def _extract_ratio_rows(self, soup: BeautifulSoup) -> dict[str, dict[str, float | None]]:
        rows: dict[str, dict[str, float | None]] = {}
        for table in soup.find_all("table"):
            table_text = self._clean_text(table.get_text(" ", strip=True))
            if ("汽油" not in table_text and "柴油" not in table_text) or "%" not in table_text:
                continue
            for tr in table.find_all("tr"):
                cells = [self._clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
                if not cells:
                    continue
                product = cells[0]
                if product not in {"汽油", "柴油"}:
                    continue
                numeric_values = [self._parse_percent(cell) for cell in cells[1:]]
                numeric_values = [value for value in numeric_values if value is not None]
                if len(numeric_values) >= 2:
                    rows[product] = {
                        "previous": numeric_values[0],
                        "current": numeric_values[1],
                        "change": numeric_values[2] if len(numeric_values) >= 3 else numeric_values[1] - numeric_values[0],
                    }
        return rows

    def _extract_maintenance_rows(self, *, soup: BeautifulSoup, observation_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        horizon_end = observation_date + timedelta(days=30)
        for table in soup.find_all("table"):
            table_text = self._clean_text(table.get_text(" ", strip=True))
            if "检修装置" not in table_text or "检修产能" not in table_text:
                continue
            table_rows = table.find_all("tr")
            if not table_rows:
                continue
            headers = [
                self._clean_text(cell.get_text(" ", strip=True))
                for cell in table_rows[0].find_all(["td", "th"])
            ]
            refinery_index = self._find_header_index(headers, ("炼厂名称", "炼厂"))
            location_index = self._find_header_index(headers, ("所在地", "地区", "省份"))
            unit_index = self._find_header_index(headers, ("检修装置", "装置"))
            capacity_index = self._find_header_index(headers, ("检修产能",))
            start_index = self._find_header_index(headers, ("起始时间", "开始时间", "检修开始"))
            end_index = self._find_header_index(headers, ("结束时间", "检修结束"))
            if min(refinery_index, location_index, unit_index, capacity_index, start_index, end_index) < 0:
                continue
            for tr in table_rows[1:]:
                cells = [self._clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]
                if len(cells) <= max(refinery_index, location_index, unit_index, capacity_index, start_index, end_index):
                    continue
                start_date = self._parse_maintenance_date(cells[start_index], is_end=False)
                end_date = self._parse_maintenance_date(cells[end_index], is_end=True)
                capacity = self._parse_number(cells[capacity_index])
                active = bool(start_date and start_date <= observation_date and (end_date is None or end_date >= observation_date))
                next_30d_start = bool(start_date and observation_date < start_date <= horizon_end)
                next_30d_end = bool(end_date and observation_date < end_date <= horizon_end)
                rows.append(
                    {
                        "refinery": cells[refinery_index],
                        "location": cells[location_index],
                        "unit": cells[unit_index],
                        "capacity": capacity,
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None,
                        "active": active,
                        "next_30d_start": next_30d_start,
                        "next_30d_end": next_30d_end,
                    }
                )
        return rows

    def _find_header_index(self, headers: list[str], candidates: tuple[str, ...]) -> int:
        for candidate in candidates:
            for index, header in enumerate(headers):
                if candidate in header:
                    return index
        return -1

    def _parse_inventory_text(self, text: str) -> dict[str, float | None]:
        total_match = re.search(
            r"汽\s*柴油\s*库存总量为(?P<value>[+-]?\d+(?:\.\d+)?)万吨",
            text,
        )
        gasoline_match = re.search(
            r"汽油\s*库存为?(?P<value>[+-]?\d+(?:\.\d+)?)万吨"
            r"[,，；;]?\s*环比[^，；;。]*?(?P<direction>增加|上涨|下降|下跌|减少)"
            r"(?P<change>[+-]?\d+(?:\.\d+)?)万吨",
            text,
        )
        gasoline_rate_match = re.search(r"汽油库容率为?(?P<value>[+-]?\d+(?:\.\d+)?)%", text)
        diesel_match = re.search(
            r"柴油\s*库存为?(?P<value>[+-]?\d+(?:\.\d+)?)万吨"
            r"[,，；;]?\s*环比[^，；;。]*?(?P<direction>增加|上涨|下降|下跌|减少)"
            r"(?P<change>[+-]?\d+(?:\.\d+)?)万吨",
            text,
        )
        diesel_rate_match = re.search(r"柴油库容率为?(?P<value>[+-]?\d+(?:\.\d+)?)%", text)
        return {
            "total_inventory": float(total_match.group("value")) if total_match else None,
            "gasoline_inventory": float(gasoline_match.group("value")) if gasoline_match else None,
            "gasoline_inventory_change_mom": (
                self._signed_by_inventory_direction(
                    gasoline_match.group("direction"),
                    float(gasoline_match.group("change")),
                )
                if gasoline_match
                else None
            ),
            "gasoline_inventory_capacity_rate": (
                float(gasoline_rate_match.group("value")) if gasoline_rate_match else None
            ),
            "diesel_inventory": float(diesel_match.group("value")) if diesel_match else None,
            "diesel_inventory_change_mom": (
                self._signed_by_inventory_direction(
                    diesel_match.group("direction"),
                    float(diesel_match.group("change")),
                )
                if diesel_match
                else None
            ),
            "diesel_inventory_capacity_rate": float(diesel_rate_match.group("value")) if diesel_rate_match else None,
        }

    def _timestamp_from_millis(self, value: Any) -> datetime | None:
        try:
            if value in (None, ""):
                return None
            return datetime.fromtimestamp(float(value) / 1000)
        except (TypeError, ValueError, OSError):
            return None

    def _score_spot_daily_report_result(self, title: str, content: str) -> int:
        normalized_content = re.sub(r"<[^>]+>", "", content)
        score = 0
        if re.search(r"山东成品油日评|山东地炼汽柴油日评", title):
            score += 30
        if re.search(r"山东.*地炼|山东.*成品油|独立炼厂", title):
            score += 12
        if re.search(r"汽油|柴油|汽柴|成品油|地炼", title):
            score += 8
        if re.search(r"日评|日报|市场", title):
            score += 5
        if re.search(r"石油焦|甲苯|原油|沥青|船燃", title) and not re.search(r"汽柴|成品油|地炼", title):
            score -= 12
        for word in ("出货", "成交", "产销率", "贸易商", "观望", "降价", "上调", "下调"):
            if word in f"{title} {normalized_content}":
                score += 1
        return score

    def _extract_spot_report_date(self, title: str) -> date | None:
        match = re.search(r"[（(](?P<yyyymmdd>\d{8})[）)]", title)
        if not match:
            return None
        try:
            return datetime.strptime(match.group("yyyymmdd"), "%Y%m%d").date()
        except ValueError:
            return None

    def _extract_spot_report_publish_time(self, text: str) -> datetime | None:
        match = re.search(r"发布时间[:：]\s*(?P<value>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", text)
        if not match:
            return None
        try:
            return datetime.strptime(match.group("value"), "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def _extract_spot_report_main_text(self, text: str) -> str:
        normalized = self._clean_text(text)
        start_candidates = [
            normalized.find(marker)
            for marker in ("今日摘要", "市场摘要", "山东地炼价格", "山东独立炼厂汽油均价", "当前位置：")
            if normalized.find(marker) >= 0
        ]
        if start_candidates:
            normalized = normalized[min(start_candidates):]
        end_candidates = [
            normalized.find(marker)
            for marker in ("免责声明", "最新文章", "版权声明", "相关资讯")
            if normalized.find(marker) >= 0
        ]
        if end_candidates:
            normalized = normalized[: min(end_candidates)]
        return self._clean_text(normalized)

    def _extract_spot_report_rule_labels(self, text: str) -> dict[str, Any]:
        groups = {
            "low_price_resource": ("低价资源", "低价货源", "低端资源", "低价促销", "低端上移"),
            "trader_grab_or_restock": ("抢货", "抄底", "入市采购", "集中采购", "补货", "拿货积极"),
            "trader_dump_or_discount": ("抛货", "降价出货", "让利出货", "甩货", "高价抵触"),
            "wait_and_see": ("观望", "谨慎", "按需采购", "刚需采购"),
            "shipment_strong": ("出货顺畅", "出货较好", "出货好转", "出货量大增", "成交放量"),
            "shipment_weak": ("出货承压", "出货清淡", "出货放缓", "成交清淡", "成交一般", "交投清淡", "出货不佳"),
            "sealed_or_reluctant_sale": ("封单", "停售", "惜售", "控量", "限量", "暂停报价"),
            "deal_center": ("成交重心", "低端上移", "低端回落", "高端上移", "高端回落", "商谈重心"),
            "refinery_raise": ("炼厂推涨", "价格推涨", "上调", "涨价", "挺价"),
            "refinery_cut": ("下调", "跌价", "降价", "价格下跌", "让利"),
        }
        labels: dict[str, Any] = {}
        for key, words in groups.items():
            matched = [word for word in words if word in text]
            labels[key] = {"status": "hit" if matched else "missing", "matched_words": matched}
        return labels

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
            if not name or not value:
                continue
            if "oilchem.net" in domain:
                cookies[name] = value
        return cookies

    def _extract_title(self, soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return self._clean_text(soup.title.string.split("_")[0])
        h1 = soup.find(["h1", "h2"])
        return self._clean_text(h1.get_text(" ", strip=True)) if h1 else ""

    def _extract_observation_date(self, title: str) -> date | None:
        match = self.title_pattern.search(title)
        if not match:
            return None
        return datetime.strptime(match.group("yyyymmdd"), "%Y%m%d").date()

    def _extract_publish_time(self, soup: BeautifulSoup) -> datetime | None:
        text = soup.get_text(" ", strip=True)
        match = re.search(r"发布时间[:：]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", text)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def _parse_capacity_utilization(self, text: str) -> dict[str, float | None]:
        main = self._parse_utilization_sentence(text, prefix="山东地炼常减压周均产能利用率为")
        ex_large = self._parse_utilization_sentence(text, prefix="不含大炼化利用率为")
        return {
            "capacity_utilization": main.get("value"),
            "capacity_utilization_wow_pct": main.get("wow_pct"),
            "capacity_utilization_yoy_pct": main.get("yoy_pct"),
            "capacity_utilization_ex_large": ex_large.get("value"),
            "capacity_utilization_ex_large_wow_pct": ex_large.get("wow_pct"),
            "capacity_utilization_ex_large_yoy_pct": ex_large.get("yoy_pct"),
        }

    def _parse_utilization_sentence(self, text: str, *, prefix: str) -> dict[str, float | None]:
        pattern = (
            re.escape(prefix)
            + r"(?P<value>[+-]?\d+(?:\.\d+)?)%"
            + r"[,，]环比(?P<wow_dir>上涨|下跌)(?P<wow>[+-]?\d+(?:\.\d+)?)%"
            + r"[,，]同比(?P<yoy_dir>上涨|下跌)(?P<yoy>[+-]?\d+(?:\.\d+)?)%"
        )
        match = re.search(pattern, text)
        if not match:
            return {"value": None, "wow_pct": None, "yoy_pct": None}
        return {
            "value": float(match.group("value")),
            "wow_pct": self._signed_by_direction(match.group("wow_dir"), float(match.group("wow"))),
            "yoy_pct": self._signed_by_direction(match.group("yoy_dir"), float(match.group("yoy"))),
        }

    def _parse_refining_profit(self, text: str) -> dict[str, float | None]:
        profit_match = re.search(
            r"综合利润(?P<value>[+-]?\d+(?:\.\d+)?)元/吨"
            + r"[,，]环比(?P<wow_dir>上涨|下跌)(?P<wow>[+-]?\d+(?:\.\d+)?)%"
            + r"[,，]同比(?P<yoy_dir>上涨|下跌)(?P<yoy>[+-]?\d+(?:\.\d+)?)%",
            text,
        )
        cost_match = re.search(
            r"原油周均成本(?P<value>[+-]?\d+(?:\.\d+)?)元/吨[,，](?P<direction>涨|跌)(?P<change>[+-]?\d+(?:\.\d+)?)元/吨",
            text,
        )
        revenue_match = re.search(
            r"综合收入(?P<value>[+-]?\d+(?:\.\d+)?)元/吨[,，](?P<direction>涨|跌)(?P<change>[+-]?\d+(?:\.\d+)?)元/吨",
            text,
        )
        return {
            "refining_profit": float(profit_match.group("value")) if profit_match else None,
            "refining_profit_wow_pct": (
                self._signed_by_direction(profit_match.group("wow_dir"), float(profit_match.group("wow")))
                if profit_match
                else None
            ),
            "refining_profit_yoy_pct": (
                self._signed_by_direction(profit_match.group("yoy_dir"), float(profit_match.group("yoy")))
                if profit_match
                else None
            ),
            "crude_cost": float(cost_match.group("value")) if cost_match else None,
            "crude_cost_change": (
                self._signed_by_short_direction(cost_match.group("direction"), float(cost_match.group("change")))
                if cost_match
                else None
            ),
            "comprehensive_revenue": float(revenue_match.group("value")) if revenue_match else None,
            "comprehensive_revenue_change": (
                self._signed_by_short_direction(revenue_match.group("direction"), float(revenue_match.group("change")))
                if revenue_match
                else None
            ),
        }

    def _signed_by_direction(self, direction: str, value: float) -> float:
        return -abs(value) if direction == "下跌" else abs(value)

    def _signed_by_short_direction(self, direction: str, value: float) -> float:
        return -abs(value) if direction == "跌" else abs(value)

    def _signed_by_inventory_direction(self, direction: str, value: float) -> float:
        return -abs(value) if direction in {"下降", "下跌", "减少"} else abs(value)

    def _parse_percent(self, value: str) -> float | None:
        match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", value)
        if not match:
            return None
        return float(match.group(1))

    def _parse_number(self, value: str) -> float:
        normalized = re.sub(r"[^0-9.]", "", value)
        return float(normalized) if normalized else 0.0

    def _parse_slash_date(self, value: str) -> date | None:
        normalized = re.sub(r"\s+", "", value)
        if not re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", normalized):
            return None
        try:
            return datetime.strptime(normalized, "%Y/%m/%d").date()
        except ValueError:
            return None

    def _parse_maintenance_date(self, value: str, *, is_end: bool) -> date | None:
        normalized = re.sub(r"\s+", "", value or "")
        if not normalized or normalized in {"-", "--", "待定"}:
            return None
        exact = self._parse_slash_date(normalized)
        if exact:
            return exact
        month_match = re.search(r"(?P<year>\d{4})/(?P<month>\d{1,2})月?(?P<period>上旬|中旬|下旬)?", normalized)
        if not month_match:
            return None
        year = int(month_match.group("year"))
        month = int(month_match.group("month"))
        period = month_match.group("period")
        if period == "上旬":
            day = 10 if is_end else 1
        elif period == "中旬":
            day = 20 if is_end else 11
        elif period == "下旬":
            day = self._last_day_of_month(year, month) if is_end else 21
        else:
            day = self._last_day_of_month(year, month) if is_end else 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _last_day_of_month(self, year: int, month: int) -> int:
        if month == 12:
            return 31
        return (date(year, month + 1, 1) - timedelta(days=1)).day

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
