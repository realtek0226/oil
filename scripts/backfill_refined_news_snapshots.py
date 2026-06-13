from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients.cnenergy_refined_oil_client import CnEnergyRefinedOilClient
from app.clients.jlc_refined_oil_client import JlcRefinedOilClient
from app.clients.refined_oil_policy_client import RefinedOilPolicyClient
from app.core.settings import get_settings
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill refined-oil news snapshots into PostgreSQL.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--item-limit", type=int, default=120)
    parser.add_argument("--init-schema", action="store_true")
    return parser.parse_args()


def _dedupe(items: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("url") or item.get("headline") or item.get("title") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _extract_item_date(item: dict) -> date | None:
    for field in ("publish_time", "publish_date"):
        raw = str(item.get(field) or "").strip()
        if len(raw) < 10:
            continue
        try:
            return date.fromisoformat(raw[:10].replace("/", "-"))
        except ValueError:
            continue
    return None


def main() -> None:
    args = _parse_args()
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    settings = get_settings().database
    if not settings.url.strip():
        raise RuntimeError("database.url is empty in app/config/app_config.json")

    repository = PostgresSnapshotRepository(settings)
    if args.init_schema:
        repository.ensure_schema()

    jlc_client = JlcRefinedOilClient()
    cnenergy_client = CnEnergyRefinedOilClient()
    policy_client = RefinedOilPolicyClient()

    cnenergy_recent: list[dict] = []
    try:
        cnenergy_recent = cnenergy_client.fetch_recent(limit=80, list_limit=200)
    except Exception:
        cnenergy_recent = []

    recent_policy_items: list[dict] = []
    try:
        recent_policy_items = policy_client.fetch_recent_adjustments(limit=40)
    except Exception:
        recent_policy_items = []

    current_date = start_date
    while current_date <= end_date:
        jlc_items = jlc_client.fetch_archive_titles(
            start_date=current_date,
            end_date=current_date,
            max_pages=args.max_pages,
            item_limit=args.item_limit,
        )
        cnenergy_items = [
            item
            for item in cnenergy_recent
            if _extract_item_date(item) == current_date
        ]
        refined_news_items = _dedupe([*jlc_items, *cnenergy_items])
        policy_items = [
            item
            for item in recent_policy_items
            if _extract_item_date(item) == current_date
        ]

        saved_news = repository.save_refined_news_items(current_date, refined_news_items)
        saved_policy = repository.save_policy_items(current_date, policy_items)
        print(
            f"{current_date.isoformat()} news_items={len(refined_news_items)} saved_news={saved_news} "
            f"policy_items={len(policy_items)} saved_policy={saved_policy}"
        )
        current_date += timedelta(days=1)


if __name__ == "__main__":
    main()
