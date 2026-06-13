from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class LlmLabelCache:
    def __init__(self, cache_dir: Path | str = Path("artifacts/llm_label_cache")) -> None:
        self.cache_dir = Path(cache_dir)

    def load(self, cache_key: str) -> dict[str, Any] | None:
        path = self._path_for(cache_key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        result = payload.get("result")
        return dict(result) if isinstance(result, dict) else None

    def save(self, cache_key: str, result: dict[str, Any], *, task: str) -> None:
        path = self._path_for(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_key": cache_key,
            "task": task,
            "created_at": datetime.now().isoformat(),
            "result": result,
        }
        tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def _path_for(self, cache_key: str) -> Path:
        safe_key = "".join(char for char in cache_key if char.isalnum() or char in {"-", "_"})
        return self.cache_dir / f"{safe_key}.json"
