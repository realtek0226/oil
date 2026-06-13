from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.common import BacktestSummary, PredictionResult


PREDICTION_DIR = Path("artifacts/prediction_runs")
BACKTEST_DIR = Path("artifacts/backtests")
AGENT_CONTROL_DIR = Path("artifacts/agent_control")
BRIEFING_DIR = Path("artifacts/briefings")
CONTROL_STATE_PATH = AGENT_CONTROL_DIR / "runtime_state.json"
PROPOSALS_PATH = AGENT_CONTROL_DIR / "optimization_proposals.json"
ALERT_CASE_STATE_PATH = AGENT_CONTROL_DIR / "alert_case_state.json"


@dataclass(frozen=True)
class StoredJsonRecord:
    key: str
    path: Path
    modified_at: datetime
    payload: dict[str, Any]


class FileRunRepository:
    def save_prediction(self, prediction: PredictionResult) -> Path:
        path = PREDICTION_DIR / f"{prediction.run_id}.json"
        return self._write_json(path, prediction.model_dump(mode="json"))

    def load_prediction(self, run_id: str) -> PredictionResult | None:
        path = PREDICTION_DIR / f"{run_id}.json"
        payload = self._read_json(path)
        if payload is None:
            return None
        return PredictionResult.model_validate(payload)

    def list_prediction_records(self, limit: int = 50) -> list[StoredJsonRecord]:
        return self._list_json_records(PREDICTION_DIR, limit=limit)

    def save_backtest(self, summary: BacktestSummary, slug: str) -> Path:
        path = BACKTEST_DIR / f"{slug}.json"
        return self._write_json(path, summary.model_dump(mode="json"))

    def load_backtest(self, slug: str) -> BacktestSummary | None:
        path = BACKTEST_DIR / f"{slug}.json"
        payload = self._read_json(path)
        if payload is None:
            return None
        return BacktestSummary.model_validate(payload)

    def list_backtest_records(self, limit: int = 20) -> list[StoredJsonRecord]:
        return self._list_json_records(BACKTEST_DIR, limit=limit)

    def save_agent_control_state(self, payload: dict[str, Any]) -> Path:
        return self._write_json(CONTROL_STATE_PATH, payload)

    def load_agent_control_state(self) -> dict[str, Any] | None:
        return self._read_json(CONTROL_STATE_PATH)

    def save_optimization_proposals(self, payload: dict[str, Any]) -> Path:
        return self._write_json(PROPOSALS_PATH, payload)

    def load_optimization_proposals(self) -> dict[str, Any]:
        return self._read_json(PROPOSALS_PATH) or {"items": []}

    def update_alert_case_state(self, *, alert_id: str, status: str, note: str | None, actor: str | None) -> dict[str, Any]:
        payload = self._read_json(ALERT_CASE_STATE_PATH) or {"items": {}}
        items = payload.setdefault("items", {})
        record = {
            "alert_id": alert_id,
            "status": status,
            "note": note,
            "actor": actor,
            "updated_at": datetime.now().isoformat(),
        }
        items[alert_id] = record
        self._write_json(ALERT_CASE_STATE_PATH, payload)
        return record

    def load_alert_case_states(self) -> dict[str, dict[str, Any]]:
        payload = self._read_json(ALERT_CASE_STATE_PATH) or {"items": {}}
        items = payload.get("items") if isinstance(payload, dict) else {}
        return items if isinstance(items, dict) else {}

    def apply_alert_case_states(self, alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        states = self.load_alert_case_states()
        merged = []
        for alert in alerts:
            item = dict(alert)
            state = states.get(str(item.get("alert_id") or ""))
            if state:
                item["status"] = state.get("status", item.get("status"))
                item["review_note"] = state.get("note")
                item["review_actor"] = state.get("actor")
                item["review_updated_at"] = state.get("updated_at")
            merged.append(item)
        return merged

    def save_briefing(self, briefing_id: str, payload: dict[str, Any]) -> Path:
        path = BRIEFING_DIR / f"{briefing_id}.json"
        return self._write_json(path, payload)

    def load_latest_briefing(self) -> dict[str, Any] | None:
        records = self._list_json_records(BRIEFING_DIR, limit=1)
        if not records:
            return None
        return records[0].payload

    def _list_json_records(self, directory: Path, *, limit: int) -> list[StoredJsonRecord]:
        if not directory.exists():
            return []

        paths = sorted(
            directory.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )

        records: list[StoredJsonRecord] = []
        for path in paths[: max(limit, 0)]:
            payload = self._read_json(path)
            if payload is None:
                continue
            records.append(
                StoredJsonRecord(
                    key=path.stem,
                    path=path,
                    modified_at=datetime.fromtimestamp(path.stat().st_mtime),
                    payload=payload,
                )
            )
        return records

    def _write_json(self, path: Path, payload: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return path

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
