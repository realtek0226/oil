from __future__ import annotations

import base64
from datetime import datetime, timedelta
import re
from typing import Any

from Crypto.Cipher import AES
import requests

from app.core.settings import JinshiSettings


class JinshiClient:
    def __init__(self, settings: JinshiSettings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.api_url and self.settings.auth_token and self.settings.secret_key_b64)

    def _encrypt_key(self) -> str:
        plaintext = datetime.now().strftime("%Y-%m-%d %H:%M:%S").encode("utf-8")
        key = base64.b64decode(self.settings.secret_key_b64)
        padding_len = AES.block_size - (len(plaintext) % AES.block_size)
        padded = plaintext + bytes([padding_len] * padding_len)
        iv = b"\x00" * 16
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(padded)
        return base64.b64encode(iv + ciphertext).decode("utf-8")

    def fetch_recent(self, days: int = 2) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        payload = {
            "inputs": {
                "type": "数据查询",
                "key": self._encrypt_key(),
                "startdate": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "enddate": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "response_mode": "blocking",
            "user": "oil-research-agent",
        }
        response = requests.post(
            self.settings.api_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": self.settings.auth_token,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        return self._normalize(payload)

    def _normalize(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data") or {}
        outputs = data.get("outputs") or {}
        news_block = outputs.get("text") or outputs.get("result") or outputs.get("output") or ""
        if isinstance(news_block, str):
            items = []
            for raw_line in news_block.splitlines():
                line = raw_line.strip().replace("\u200b", "")
                if not line:
                    continue
                items.append({"headline": line})
            return items
        if isinstance(news_block, list):
            normalized: list[dict[str, Any]] = []
            for item in news_block:
                if isinstance(item, dict):
                    title = str(item.get("title", "")).strip()
                    content = self._strip_html(str(item.get("content", ""))).strip()
                    headline = title or self._compact_text(content)
                    normalized.append(
                        {
                            "headline": headline,
                            "title": title,
                            "content": content,
                            "author": item.get("author"),
                            "publish_time": item.get("publish_time"),
                            "direction_hint": item.get("direction_hint"),
                            "direction_strength": self._to_float(item.get("direction_strength")),
                            "relevance_score": self._to_float(item.get("relevance_score")),
                            "major_event_candidate": item.get("major_event_candidate"),
                            "major_score": self._to_float(item.get("major_score")),
                        }
                    )
                else:
                    normalized.append({"headline": str(item)})
            return normalized
        return []

    def _strip_html(self, value: str) -> str:
        return re.sub(r"<[^>]+>", " ", value).replace("\u200b", "").strip()

    def _compact_text(self, value: str, limit: int = 120) -> str:
        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact
        return compact[:limit].rstrip() + "..."

    def _to_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
