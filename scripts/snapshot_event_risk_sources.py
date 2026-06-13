from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients.brent_report_client import BrentReportClient
from app.clients.jinshi_client import JinshiClient
from app.core.settings import get_settings
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Snapshot Jinshi crude news and Brent daily report into PostgreSQL.")
    parser.add_argument("--snapshot-date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--jinshi-days", type=int, default=2, help="How many recent days to request from Jinshi.")
    parser.add_argument("--init-schema", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    snapshot_date = date.fromisoformat(args.snapshot_date)
    settings = get_settings().database
    if not settings.url.strip():
        raise RuntimeError("database.url is empty in app/config/app_config.json")

    repository = PostgresSnapshotRepository(settings)
    if args.init_schema:
        repository.ensure_schema()

    brent_client = BrentReportClient()
    jinshi_client = JinshiClient()

    report_payload = brent_client.fetch_latest()
    news_items = jinshi_client.fetch_recent(days=args.jinshi_days)
    news_items = [{**item, "source": str(item.get("source") or "jinshi_crude_news")} for item in news_items]

    saved_report = repository.save_brent_report(snapshot_date=snapshot_date, report_payload=report_payload)
    saved_news = repository.save_jinshi_news_items(snapshot_date=snapshot_date, items=news_items)

    print(
        f"snapshot_date={snapshot_date.isoformat()} "
        f"report_saved={saved_report} "
        f"news_items={len(news_items)} "
        f"news_saved={saved_news}"
    )


if __name__ == "__main__":
    main()
