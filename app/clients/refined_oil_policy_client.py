from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LIST_URL = "https://www.ndrc.gov.cn/xwdt/xwfb/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class RefinedOilPolicyClient:
    def __init__(self) -> None:
        self._cache_date: date | None = None
        self._cache_items: list[dict[str, Any]] = []

    def fetch_recent_adjustments(self, limit: int = 12) -> list[dict[str, Any]]:
        today = date.today()
        if self._cache_date == today and len(self._cache_items) >= limit:
            return self._cache_items[:limit]

        response = requests.get(LIST_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        candidates: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for anchor in soup.find_all("a", href=True):
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if "成品油" not in title:
                continue
            url = urljoin(response.url, anchor["href"])
            if not url.startswith("https://www.ndrc.gov.cn/"):
                continue
            key = (title, url)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({"title": title, "url": url})

        items: list[dict[str, Any]] = []
        for candidate in candidates[:limit]:
            try:
                items.append(self._parse_notice(candidate["url"], default_title=candidate["title"]))
            except Exception:
                continue

        self._cache_date = today
        self._cache_items = items
        return items[:limit]

    def _parse_notice(self, url: str, default_title: str) -> dict[str, Any]:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        body = self._clean_text(soup.get_text("\n", strip=True))

        publish_date = None
        publish_match = re.search(r"(\d{4}/\d{2}/\d{2})", body)
        if publish_match:
            publish_date = publish_match.group(1)

        source_org = None
        source_match = re.search(r"来源[:：]?\s*([^\n\[]+)", body)
        if source_match:
            source_org = self._clean_text(source_match.group(1))

        gasoline_delta = None
        diesel_delta = None
        change_match = re.search(
            r"(?:每吨|价格每吨)\s*分别(?:提高|上调|下调|降低)\s*([0-9]+)\s*元[、和]\s*([0-9]+)\s*元",
            body,
        )
        if change_match:
            gasoline_delta = int(change_match.group(1))
            diesel_delta = int(change_match.group(2))
            change_snippet = change_match.group(0)
            if "下调" in change_snippet or "降低" in change_snippet:
                gasoline_delta *= -1
                diesel_delta *= -1

        effective_time = None
        effective_match = re.search(r"自\s*(\d{1,2})月(\d{1,2})日24时起", body)
        if effective_match and publish_date:
            effective_time = (
                f"{publish_date[:4]}-{int(effective_match.group(1)):02d}-"
                f"{int(effective_match.group(2)):02d} 24:00"
            )
        else:
            effective_match = re.search(r"自\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日24时起", body)
            if effective_match:
                effective_time = (
                    f"{effective_match.group(1)}-{int(effective_match.group(2)):02d}-"
                    f"{int(effective_match.group(3)):02d} 24:00"
                )

        title = default_title
        for line in soup.get_text("\n", strip=True).splitlines():
            cleaned = self._clean_text(line)
            if "成品油价格" in cleaned:
                title = cleaned
                break

        return {
            "title": title,
            "url": response.url,
            "publish_date": publish_date,
            "effective_time": effective_time,
            "source_org": source_org,
            "gasoline_change_yuan_per_ton": gasoline_delta,
            "diesel_change_yuan_per_ton": diesel_delta,
            "content_preview": body[:400],
        }

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
