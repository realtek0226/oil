from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LIST_URL = "https://oil.oilchem.net/oil/refinedoil.shtml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class RefinedOilNewsClient:
    allowed_section_tokens = (
        "成品油市场价格行情",
        "主营价格行情",
        "地炼价格行情",
        "贸易商报价",
        "隆众数据发布",
    )

    def __init__(self) -> None:
        self._cache_date: date | None = None
        self._cache_items: list[dict[str, Any]] = []

    def fetch_recent(self, total_limit: int = 24, per_section_limit: int = 6) -> list[dict[str, Any]]:
        today = date.today()
        if self._cache_date == today and len(self._cache_items) >= min(total_limit, len(self._cache_items)):
            return self._cache_items[:total_limit]

        response = requests.get(LIST_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for section in soup.select("div.channelmain3.left"):
            section_name = self._extract_section_name(section)
            if not section_name or not any(token in section_name for token in self.allowed_section_tokens):
                continue

            section_count = 0
            for anchor in section.find_all("a", href=True):
                headline = self._clean_text(anchor.get_text(" ", strip=True))
                url = urljoin(response.url, anchor["href"])
                if len(headline) < 8 or not url.endswith(".html"):
                    continue
                key = (headline, url)
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        "headline": headline,
                        "title": headline,
                        "url": url,
                        "section_name": section_name,
                        "source": "oilchem_refinedoil_channel",
                        "publish_hint": self._extract_publish_hint(anchor.parent.get_text(" ", strip=True)),
                        "priority_score": self._score_item(section_name, headline),
                    }
                )
                section_count += 1
                if section_count >= per_section_limit:
                    break

        items.sort(key=lambda item: item.get("priority_score", 0.0), reverse=True)
        items = items[:total_limit]

        self._cache_date = today
        self._cache_items = items
        return items[:total_limit]

    def _extract_section_name(self, section: BeautifulSoup) -> str:
        lines = [
            self._clean_text(line)
            for line in section.get_text("\n", strip=True).splitlines()
            if self._clean_text(line)
        ]
        return lines[0] if lines else ""

    def _extract_publish_hint(self, text: str) -> str | None:
        match = re.search(r"\[(\d{2}:\d{2}|\d{2}-\d{2})\]", text)
        if match:
            return match.group(1)
        return None

    def _score_item(self, section_name: str, headline: str) -> float:
        score = 0.0
        if "地炼价格行情" in section_name:
            score += 8.0
        elif "隆众数据发布" in section_name:
            score += 6.0
        elif "主营价格行情" in section_name:
            score += 4.0
        elif "成品油市场价格行情" in section_name:
            score += 2.0
        elif "贸易商报价" in section_name:
            score += 1.0

        if "山东" in headline:
            score += 10.0
        if "地炼" in headline:
            score += 6.0
        if "主营" in headline:
            score += 3.0
        if "产能利用率" in headline or "产量" in headline or "库存" in headline or "利润" in headline:
            score += 2.0
        if "截至9点30分" in headline:
            score += 1.5
        if "今日" in headline or "20260529" in headline:
            score += 1.0
        return score

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
