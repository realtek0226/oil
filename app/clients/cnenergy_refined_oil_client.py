from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.cnenergynews.cn"
NAVIGATE_API = f"{BASE_URL}/api/navigate"
LIST_API = f"{BASE_URL}/api/list"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class CnEnergyRefinedOilClient:
    channel_paths = ("www.cnenergynews.cn/yq",)
    primary_keywords = (
        "\u6210\u54c1\u6cb9",
        "\u6c7d\u67f4\u6cb9",
        "\u5730\u70bc",
        "\u70bc\u5382",
        "\u8c03\u4ef7",
        "\u53d1\u6539\u59d4",
        "\u5f00\u5de5\u7387",
        "\u88c2\u89e3",
        "92#",
        "95#",
        "0#",
    )
    secondary_keywords = (
        "\u6c7d\u6cb9",
        "\u67f4\u6cb9",
        "\u6cb9\u4ef7",
        "\u539f\u6cb9",
        "\u5e93\u5b58",
        "\u9700\u6c42",
        "\u914d\u989d",
        "\u5229\u6da6",
        "\u590d\u5de5",
        "\u7269\u6d41",
    )
    context_keywords = (
        "\u56fd\u5185",
        "\u5c71\u4e1c",
        "\u5730\u70bc",
        "\u70bc\u5382",
        "\u6210\u54c1\u6cb9",
        "\u6c7d\u67f4\u6cb9",
        "\u8c03\u4ef7",
        "\u53d1\u6539\u59d4",
    )
    bullish_keywords = (
        "\u4e0a\u6da8",
        "\u4e0a\u8c03",
        "\u56de\u5347",
        "\u63d0\u632f",
        "\u652f\u6491",
        "\u8d70\u5f3a",
        "\u4e09\u8fde\u6da8",
        "\u7d27\u5f20",
        "\u53bb\u5e93",
    )
    bearish_keywords = (
        "\u4e0b\u8dcc",
        "\u4e0b\u8c03",
        "\u56de\u843d",
        "\u627f\u538b",
        "\u75b2\u5f31",
        "\u56de\u8c03",
        "\u5bbd\u677e",
        "\u505c\u5de5",
        "\u5e93\u5b58\u538b\u529b",
    )
    stop_markers = (
        "\u6295\u7a3f\u4e0e\u65b0\u95fb\u7ebf\u7d22",
        "\u6b22\u8fce\u5173\u6ce8\u4e2d\u56fd\u80fd\u6e90\u5b98\u65b9\u7f51\u7ad9",
        "\u5206\u4eab\u8ba9\u66f4\u591a\u4eba\u770b\u5230",
        "\u4e2d\u56fd\u80fd\u6e90\u7f51\u7248\u6743\u4f5c\u54c1",
        "\u5373\u65f6\u65b0\u95fb",
        "\u8981\u95fb\u63a8\u8350",
    )

    def __init__(self) -> None:
        self._cache_date: date | None = None
        self._cache_items: list[dict[str, Any]] = []

    def fetch_recent(self, limit: int = 6, list_limit: int = 200) -> list[dict[str, Any]]:
        today = date.today()
        if self._cache_date == today and len(self._cache_items) >= min(limit, len(self._cache_items)):
            return self._cache_items[:limit]

        items: list[dict[str, Any]] = []
        seen_aids: set[str] = set()
        for channel_path in self.channel_paths:
            node = self._get_channel_node(channel_path)
            if not node:
                continue
            for record in self._fetch_channel_records(node=node, list_limit=list_limit):
                aid = str(record.get("aid") or "").strip()
                if not aid or aid in seen_aids:
                    continue
                seen_aids.add(aid)
                if not self._is_relevant_record(record):
                    continue

                article = self._fetch_article(aid=aid)
                if not article:
                    continue

                title = article["title"] or str(record.get("title") or "").strip()
                summary = self._clean_text(str(record.get("summary") or "").strip())
                content = article["content"]
                direction_hint, major_score = self._build_direction_hint(f"{title}\n{summary}\n{content}")
                priority_score = self._score_item(title=title, summary=summary, content=content)
                if major_score > 0:
                    priority_score += min(major_score, 5.0) * 0.4

                items.append(
                    {
                        "headline": title,
                        "title": title,
                        "summary": summary,
                        "content": content,
                        "url": f"{BASE_URL}/article/{aid}",
                        "section_name": "\u4e2d\u56fd\u80fd\u6e90\u7f51-\u6cb9\u6c14",
                        "source": "cnenergy_oil_gas_fulltext",
                        "publish_time": article["publish_time"] or self._format_millis(record.get("ext_xtime")),
                        "source_name": article["source_name"],
                        "priority_score": round(priority_score, 4),
                        "major_score": round(major_score, 4),
                        "direction_hint": direction_hint,
                    }
                )

        items.sort(
            key=lambda item: (
                float(item.get("priority_score") or 0.0),
                str(item.get("publish_time") or ""),
            ),
            reverse=True,
        )
        self._cache_date = today
        self._cache_items = items
        return items[:limit]

    def _get_channel_node(self, channel_path: str) -> str | None:
        response = requests.get(
            NAVIGATE_API,
            params={"type": "column", "path": channel_path},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or []
        if not data:
            return None
        catnodes = data[-1].get("catnode") or []
        if not catnodes:
            return None
        node = str(catnodes[0].get("catnode") or "").strip()
        return node or None

    def _fetch_channel_records(self, node: str, list_limit: int) -> list[dict[str, Any]]:
        response = requests.get(
            LIST_API,
            params={"node": f"\"{node}\"", "offset": 0, "limit": list_limit},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        records = payload.get("list") or []
        return [record for record in records if isinstance(record, dict) and record.get("aid")]

    def _fetch_article(self, aid: str) -> dict[str, str] | None:
        response = requests.get(
            f"{BASE_URL}/article/{aid}",
            headers={"User-Agent": HEADERS["User-Agent"], "Accept-Language": HEADERS["Accept-Language"]},
            timeout=30,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        title = self._clean_text(
            (soup.select_one("h1.article_content_title") or soup.title).get_text(" ", strip=True)
            if (soup.select_one("h1.article_content_title") or soup.title)
            else ""
        )
        source_name = self._clean_text(
            (soup.select_one(".article_source_web .source") or "").get_text(" ", strip=True)
            if soup.select_one(".article_source_web .source")
            else ""
        ).removeprefix("\u6765\u6e90\uff1a")
        publish_time = self._normalize_publish_time(
            self._clean_text(
                soup.select_one(".article_source_web .time").get_text(" ", strip=True)
                if soup.select_one(".article_source_web .time")
                else ""
            )
        )

        body_node = (
            soup.select_one(".article_group article")
            or soup.select_one(".article_group")
            or soup.select_one(".article_detail_content article")
            or soup.select_one(".article_detail")
        )
        if body_node is None:
            return None

        paragraphs = [
            self._clean_text(paragraph.get_text(" ", strip=True))
            for paragraph in body_node.select("p")
            if self._clean_text(paragraph.get_text(" ", strip=True))
        ]
        content = "\n".join(paragraphs) if paragraphs else body_node.get_text("\n", strip=True)
        content = self._clean_article_body(content)
        if len(content) < 60:
            return None

        return {
            "title": title,
            "source_name": source_name,
            "publish_time": publish_time,
            "content": content,
        }

    def _is_relevant_record(self, record: dict[str, Any]) -> bool:
        if str(record.get("addltype") or "").strip().lower() == "link":
            return False
        text = self._compose_text(record)
        if any(keyword in text for keyword in self.primary_keywords):
            return True
        secondary_hit = any(keyword in text for keyword in self.secondary_keywords)
        context_hit = any(keyword in text for keyword in self.context_keywords)
        return secondary_hit and context_hit

    def _score_item(self, title: str, summary: str, content: str) -> float:
        text = f"{title}\n{summary}\n{content}"
        score = 0.0
        if "\u5c71\u4e1c" in text:
            score += 10.0
        if "\u5730\u70bc" in text:
            score += 8.0
        if "\u70bc\u5382" in text:
            score += 4.0
        if "\u6210\u54c1\u6cb9" in text:
            score += 6.0
        if "\u6c7d\u67f4\u6cb9" in text:
            score += 6.0
        if "\u6c7d\u6cb9" in text:
            score += 3.0
        if "\u67f4\u6cb9" in text:
            score += 3.0
        if "\u8c03\u4ef7" in text or "\u53d1\u6539\u59d4" in text:
            score += 5.0
        if "\u5f00\u5de5\u7387" in text:
            score += 4.0
        if "\u5e93\u5b58" in text or "\u9700\u6c42" in text or "\u5229\u6da6" in text:
            score += 2.5
        if "\u914d\u989d" in text or "\u88c2\u89e3" in text:
            score += 2.0
        if "\u56fd\u5185\u6cb9\u4ef7" in text or "\u6cb9\u4ef7" in title:
            score += 1.5
        if len(content) >= 350:
            score += 0.5
        return score

    def _build_direction_hint(self, text: str) -> tuple[str, float]:
        positive = sum(text.count(keyword) for keyword in self.bullish_keywords)
        negative = sum(text.count(keyword) for keyword in self.bearish_keywords)
        if positive > negative:
            return "bullish_refined", float(min(positive - negative, 5))
        if negative > positive:
            return "bearish_refined", float(min(negative - positive, 5))
        return "flat_refined", 0.0

    def _compose_text(self, record: dict[str, Any]) -> str:
        text_parts = [
            str(record.get("title") or ""),
            str(record.get("summary") or ""),
        ]
        keywords = record.get("keywords") or []
        if isinstance(keywords, list):
            text_parts.extend(str(keyword) for keyword in keywords)
        return "\n".join(text_parts)

    def _clean_article_body(self, text: str) -> str:
        cleaned = text
        for marker in self.stop_markers:
            if marker in cleaned:
                cleaned = cleaned.split(marker, 1)[0]
        cleaned = cleaned.replace("\r", "\n")
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)
        return self._clean_text(cleaned)

    def _normalize_publish_time(self, value: str) -> str:
        match = re.search(r"(20\d{2})\D(\d{1,2})\D(\d{1,2})\D+(\d{1,2}):(\d{2})", value)
        if not match:
            return value
        return (
            f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d} "
            f"{int(match.group(4)):02d}:{int(match.group(5)):02d}"
        )

    def _format_millis(self, value: Any) -> str | None:
        try:
            millis = int(str(value))
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(millis / 1000).strftime("%Y-%m-%d %H:%M")

    def _clean_text(self, value: str) -> str:
        return re.sub(r"[ \t\f\v]+", " ", value.replace("\xa0", " ")).strip()
