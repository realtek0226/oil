from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients.wind_price_client import WindPriceClient
from app.core.settings import DatabaseSettings, get_settings
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository


DEFAULT_START_DATE = date(2025, 1, 1)
DEFAULT_SUMMARY_OUTPUT = "artifacts/wind_brent_settlement_import_summary.json"


def parse_date(value: str) -> date:
    return datetime.fromisoformat(value.strip()[:10]).date()


def resolve_database_settings(args: argparse.Namespace) -> DatabaseSettings:
    database_url = args.database_url or os.getenv("OIL_RESEARCH_DB_URL")
    schema = args.schema or os.getenv("OIL_RESEARCH_DB_SCHEMA")
    if database_url:
        return DatabaseSettings(url=database_url, schema=schema or "oil_research", echo=False)
    settings = get_settings()
    if schema and schema != settings.database.schema:
        return DatabaseSettings(url=settings.database.url, schema=schema, echo=settings.database.echo)
    return settings.database


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def fetch_history_in_chunks(
    client: WindPriceClient,
    *,
    code: str,
    start_date: date,
    end_date: date,
    chunk_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records_by_date: dict[date, dict[str, Any]] = {}
    chunks: list[dict[str, Any]] = []
    cursor = start_date
    chunk_days = max(1, min(int(chunk_days), 365))
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end_date)
        chunk_records = client.get_history(
            code=code,
            fields="settle",
            start_date=cursor,
            end_date=chunk_end,
        )
        chunk_records = [record for record in chunk_records if record.get("settle") is not None]
        chunks.append(
            {
                "start_date": cursor,
                "end_date": chunk_end,
                "fetched_count": len(chunk_records),
            }
        )
        for record in chunk_records:
            records_by_date[record["date"]] = record
        cursor = chunk_end + timedelta(days=1)
    records = [records_by_date[key] for key in sorted(records_by_date)]
    return records, chunks


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Import Wind Brent historical settlement into PostgreSQL.")
    parser.add_argument("--base-url", default=os.getenv("WIND_BASE_URL") or settings.wind.base_url)
    parser.add_argument("--code", default=os.getenv("WIND_BRENT_CODE") or settings.wind.brent_code)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--database-url", default="")
    parser.add_argument("--schema", default="")
    parser.add_argument("--chunk-days", type=int, default=365)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if start_date > end_date:
        raise ValueError("start-date cannot be later than end-date")

    client = WindPriceClient(
        base_url=args.base_url,
        default_code=args.code,
        default_fields="settle",
        timeout_seconds=settings.wind.timeout_seconds,
    )
    records, chunks = fetch_history_in_chunks(
        client,
        code=args.code,
        start_date=start_date,
        end_date=end_date,
        chunk_days=args.chunk_days,
    )
    summary: dict[str, Any] = {
        "source": "wind_brent_settlement",
        "endpoint": f"{args.base_url.rstrip('/')}/wsd",
        "code": args.code,
        "field": "settle",
        "start_date": start_date,
        "end_date": end_date,
        "fetched_count": len(records),
        "chunk_days": max(1, min(int(args.chunk_days), 365)),
        "chunks": chunks,
        "date_min": min((record["date"] for record in records), default=None),
        "date_max": max((record["date"] for record in records), default=None),
        "latest_record": records[-1] if records else None,
        "dry_run": bool(args.dry_run),
    }

    if args.dry_run:
        summary["saved_count"] = 0
    else:
        database_settings = resolve_database_settings(args)
        repository = PostgresSnapshotRepository(database_settings)
        repository.ensure_schema()
        summary["saved_count"] = repository.save_wind_brent_settlement_records(records)

    output_path = (ROOT / args.summary_output).resolve()
    write_summary(output_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
