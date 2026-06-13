from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.settings import get_settings
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository


def main() -> None:
    settings = get_settings().database
    if not settings.url.strip():
        raise RuntimeError("database.url is empty in app/config/app_config.json")
    repository = PostgresSnapshotRepository(settings)
    repository.ensure_schema()
    print(f"schema initialized: {settings.schema}")


if __name__ == "__main__":
    main()
