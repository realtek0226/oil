from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
LIVE_HOT_URL = "https://oil.315i.com/cmlc/001002-jdxw-hy"
ARCHIVE_FIRST_PAGE_URL = "https://oil.315i.com/cmlc/Nav-001002001-qcy"
ARCHIVE_PAGE_TEMPLATE = (
    "https://oil.315i.com/common/goArticleList?pageIndex={page_index}"
    "&productIds=001002&columnIds=001007,001009,001015,001016"
    "&clickable=1&type=1&pageId=41&staticUrls=http://oil.315i.com&"
)
SCRIPT_PATH = Path("scripts/jlc_browser_fetch.js")


class JlcRefinedOilClient:
    def __init__(self) -> None:
        self._live_cache_date: date | None = None
        self._live_cache_items: list[dict[str, Any]] = []

    def fetch_live_hot(self, limit: int = 12, probe_detail: bool = False) -> list[dict[str, Any]]:
        today = date.today()
        if not probe_detail and self._live_cache_date == today and len(self._live_cache_items) >= limit:
            return self._live_cache_items[:limit]

        if not SCRIPT_PATH.exists():
            raise FileNotFoundError(f"Missing browser fetch script: {SCRIPT_PATH}")

        command = [
            "node",
            str(SCRIPT_PATH),
            "--limit",
            str(limit),
            "--probe-detail",
            "true" if probe_detail else "false",
        ]
        completed = subprocess.run(
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "JLC browser fetch failed: "
                f"exit={completed.returncode}, stderr={completed.stderr.strip() or completed.stdout.strip()}"
            )

        payload = json.loads(completed.stdout)
        items = payload.get("items") or []
        if not probe_detail:
            self._live_cache_date = today
            self._live_cache_items = items
        return items[:limit]

    def fetch_archive_titles(
        self,
        start_date: date,
        end_date: date,
        max_pages: int = 40,
        item_limit: int = 200,
    ) -> list[dict[str, Any]]:
        if not SCRIPT_PATH.exists():
            raise FileNotFoundError(f"Missing browser fetch script: {SCRIPT_PATH}")

        command = [
            "node",
            str(SCRIPT_PATH),
            "--mode",
            "archive",
            "--start-date",
            start_date.isoformat(),
            "--end-date",
            end_date.isoformat(),
            "--max-pages",
            str(max_pages),
            "--item-limit",
            str(item_limit),
        ]
        completed = subprocess.run(
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=240,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "JLC archive browser fetch failed: "
                f"exit={completed.returncode}, stderr={completed.stderr.strip() or completed.stdout.strip()}"
            )

        payload = json.loads(completed.stdout)
        items = payload.get("items") or []
        return items[:item_limit]

    def _parse_archive_page(self, html: str, base_url: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, Any]] = []
        for listing in soup.select("ul.list.list14time li"):
            anchors = [
                anchor
                for anchor in listing.find_all("a", href=True)
                if anchor.get("href") and not anchor["href"].startswith("javascript:")
            ]
            anchor = anchors[-1] if anchors else None
            date_node = listing.select_one("span.fr")
            if anchor is None or date_node is None:
                continue
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not self._is_relevant_title(title):
                continue

            publish_date_text = self._clean_text(date_node.get_text(" ", strip=True))
            try:
                publish_date_obj = date.fromisoformat(publish_date_text[:10])
            except ValueError:
                continue

            full_url = urljoin(base_url, anchor["href"])
            direction_hint, major_score = self._build_direction_hint(title)
            items.append(
                {
                    "headline": title,
                    "title": title,
                    "url": full_url,
                    "source": "jlc_refinedoil_archive_titles",
                    "section_name": "金联创-汽柴油归档标题",
                    "publish_date": publish_date_obj.isoformat(),
                    "publish_time": f"{publish_date_obj.isoformat()} 08:00",
                    "priority_score": float(self._score_title(title)),
                    "direction_hint": direction_hint,
                    "major_score": float(major_score),
                    "publish_date_obj": publish_date_obj,
                }
            )
        return items

    def _is_relevant_title(self, title: str) -> bool:
        if not title:
            return False
        required_tokens = (
            "汽柴油",
            "成品油",
            "汽油",
            "柴油",
            "地炼",
            "主营",
            "价格汇总表",
            "价格快报",
            "市场概况",
            "船单报价",
        )
        return any(token in title for token in required_tokens)

    def _score_title(self, title: str) -> int:
        score = 0
        if "山东" in title:
            score += 12
        if "地炼" in title:
            score += 10
        if "汽柴油" in title:
            score += 8
        if "成品油" in title:
            score += 8
        if "市场概况" in title:
            score += 6
        if "价格汇总表" in title:
            score += 6
        if "价格快报" in title:
            score += 5
        if "批发价格明细表" in title:
            score += 4
        if "船单报价" in title:
            score += 4
        if "主营" in title:
            score += 3
        return score

    def _build_direction_hint(self, text: str) -> tuple[str, int]:
        positive_keywords = ("上调", "上涨", "推涨", "挺价", "支撑", "偏强", "去库", "检修", "停工")
        negative_keywords = ("下调", "下跌", "回落", "承压", "促销", "宽松", "累库", "疲弱", "下行")
        positive = sum(text.count(keyword) for keyword in positive_keywords)
        negative = sum(text.count(keyword) for keyword in negative_keywords)
        if positive > negative:
            return "bullish_refined", min(positive - negative, 5)
        if negative > positive:
            return "bearish_refined", min(negative - positive, 5)
        return "flat_refined", 0

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
