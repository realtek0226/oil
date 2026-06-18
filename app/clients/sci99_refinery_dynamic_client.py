from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.core.settings import Sci99Settings
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://energy.sci99.com"
REFINED_OIL_URL = f"{BASE_URL}/product/refined_oil"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class Sci99RefineryDynamicClient:
    dynamic_keywords = (
        "\u88c5\u7f6e\u52a8\u6001",
        "\u88c5\u7f6e\u68c0\u4fee",
        "\u88c5\u7f6e\u5f00\u5de5",
        "\u5f00\u5de5\u7387",
        "\u964d\u8d1f\u8377",
        "\u63d0\u8d1f\u8377",
        "\u590d\u5de5",
        "\u505c\u5de5",
        "\u68c0\u4fee",
        "\u70bc\u5382",
        "\u5730\u70bc",
        "\u4e3b\u8425\u70bc\u5382",
    )
    product_keywords = ("\u6210\u54c1\u6cb9", "\u6c7d\u6cb9", "\u67f4\u6cb9", "\u6c7d\u67f4", "\u5730\u70bc", "\u70bc\u5382")
    negative_keywords = ("\u5316\u5de5", "\u7532\u9187", "PVC", "\u7eaf\u82ef", "\u6ca5\u9752", "\u77f3\u6cb9\u7126")

    def __init__(self, settings: Sci99Settings | None = None) -> None:
        self.settings = settings or Sci99Settings()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        if self.settings.cookie:
            self.session.headers.update({"Cookie": self.settings.cookie})
        self._cache_date: date | None = None
        self._cache_items: list[dict[str, Any]] = []

    def fetch_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        today = date.today()
        if self._cache_date == today and len(self._cache_items) >= limit:
            return self._cache_items[:limit]
        try:
            response = self.session.get(REFINED_OIL_URL, timeout=self.settings.timeout_seconds)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        except Exception:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not title or len(title) < 6:
                continue
            score = self._score_title(title)
            if score < 6:
                continue
            url = urljoin(response.url, anchor.get("href") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            item = {
                "headline": title,
                "title": title,
                "summary": title,
                "content": title,
                "url": url,
                "section_name": "\u5353\u521b\u8d44\u8baf-\u6210\u54c1\u6cb9",
                "source": "sci99_refinery_dynamics",
                "publish_time": self._extract_publish_hint(anchor.parent.get_text(" ", strip=True) if anchor.parent else ""),
                "priority_score": float(score),
                "topic": "refinery_dynamic",
            }
            detail = self._fetch_detail(url)
            if detail:
                item.update(detail)
                item["priority_score"] = float(score + self._score_title(str(detail.get("content") or "")) * 0.2)
            items.append(item)
            if len(items) >= max(limit * 2, limit):
                break
        items.sort(key=lambda item: (float(item.get("priority_score") or 0.0), str(item.get("publish_time") or "")), reverse=True)
        self._cache_date = today
        self._cache_items = items[:limit]
        return self._cache_items

    def _fetch_detail(self, url: str) -> dict[str, Any] | None:
        try:
            response = self.session.get(url, timeout=self.settings.timeout_seconds)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        except Exception:
            return None
        soup = BeautifulSoup(response.text, "html.parser")
        title_node = soup.find(["h1", "h2"])
        title = self._clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
        content_node = soup.select_one("article") or soup.select_one(".article") or soup.select_one(".content") or soup.body
        content = self._clean_text(content_node.get_text(" ", strip=True)) if content_node else ""
        if len(content) > 1500:
            content = content[:1500]
        publish_time = self._extract_publish_hint(soup.get_text(" ", strip=True))
        result: dict[str, Any] = {}
        if title:
            result["headline"] = title
            result["title"] = title
        if content:
            result["content"] = content
            result["summary"] = content[:240]
        if publish_time:
            result["publish_time"] = publish_time
        return result or None

    def _score_title(self, text: str) -> int:
        score = 0
        if any(keyword in text for keyword in self.dynamic_keywords):
            score += 8
        if any(keyword in text for keyword in self.product_keywords):
            score += 5
        if "\u5c71\u4e1c" in text:
            score += 4
        if any(keyword in text for keyword in ("\u964d\u8d1f", "\u505c\u5de5", "\u68c0\u4fee", "\u590d\u5de5", "\u5f00\u5de5", "\u8d1f\u8377")):
            score += 4
        if any(keyword in text for keyword in self.negative_keywords) and not any(keyword in text for keyword in self.product_keywords):
            score -= 8
        return score

    def _extract_publish_hint(self, text: str) -> str | None:
        match = re.search(r"(20\d{2})[-/.?](\d{1,2})[-/.?](\d{1,2})??\s*(\d{1,2}:\d{2})?", text)
        if not match:
            return None
        try:
            value = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            if match.group(4):
                value = f"{value} {match.group(4)}"
            return value
        except Exception:
            return None

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
