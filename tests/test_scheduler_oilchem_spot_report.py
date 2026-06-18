from datetime import date, datetime

from app.services.market_dataset import MarketDatasetService, PredictionTimeAlignmentError
from app.services.scheduler_service import SchedulerJobState, SchedulerService


class _NewsLoadResult:
    def __init__(self, items: list[dict], source_counts: dict[str, int] | None = None) -> None:
        self.items = items
        self.source_counts = source_counts or {}


class _FakeNewsRepository:
    enabled = True

    def __init__(self, items: list[dict], source_counts: dict[str, int] | None = None) -> None:
        self.result = _NewsLoadResult(items=items, source_counts=source_counts)

    def load_jinshi_news_items(self, start_date: date, end_date: date) -> _NewsLoadResult:
        return self.result

    def load_refined_news_items(self, start_date: date, end_date: date) -> _NewsLoadResult:
        return self.result


class _FakeJinshiClient:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    def fetch_recent(self, days: int) -> list[dict]:
        return self.items


def _market_service() -> MarketDatasetService:
    return object.__new__(MarketDatasetService)


def _oilchem_job() -> SchedulerJobState:
    return SchedulerJobState(
        job_key="oilchem_spot_report_fetch",
        label="OilChem spot report",
        mode="daily",
        schedule_value="06:00",
        enabled=True,
        job_func=lambda: {},
    )


def _morning_briefing_job() -> SchedulerJobState:
    return SchedulerJobState(
        job_key="morning_briefing",
        label="Morning briefing",
        mode="daily",
        schedule_value="08:05",
        enabled=True,
        job_func=lambda: {},
    )


def _brent_report_job() -> SchedulerJobState:
    return SchedulerJobState(
        job_key="brent_report_fetch",
        label="Brent report",
        mode="daily",
        schedule_value="08:00",
        enabled=True,
        job_func=lambda: {},
    )


def test_event_news_archive_path_excludes_items_after_prediction_cutoff() -> None:
    svc = _market_service()
    svc.snapshot_repository = _FakeNewsRepository(
        [
            {"headline": "after cutoff", "publish_time": "2026-06-06 07:01:00"},
            {"headline": "at cutoff", "publish_time": "2026-06-06 07:00:00"},
            {"headline": "previous day", "publish_time": "2026-06-05 18:00:00"},
        ]
    )

    items = svc._load_event_news_items(as_of_date=date(2026, 6, 6))
    headlines = {item["headline"] for item in items}

    assert "after cutoff" not in headlines
    assert "at cutoff" in headlines
    assert "previous day" in headlines


def test_event_news_live_path_excludes_items_after_prediction_cutoff() -> None:
    svc = _market_service()
    svc.snapshot_repository = None
    svc.jinshi_client = _FakeJinshiClient(
        [
            {"headline": "after cutoff", "publish_time": "2026-06-06 08:30:00"},
            {"headline": "before cutoff", "publish_time": "2026-06-06 06:30:00"},
        ]
    )

    items = svc._load_event_news_items(as_of_date=date(2026, 6, 6))
    headlines = {item["headline"] for item in items}

    assert "after cutoff" not in headlines
    assert "before cutoff" in headlines


def test_oilchem_spot_report_daily_job_does_not_catch_up_after_schedule_when_archive_missing() -> None:
    svc = object.__new__(SchedulerService)
    svc.dataset_service = type(
        "Dataset",
        (),
        {"snapshot_repository": _FakeNewsRepository([], source_counts={})},
    )()
    svc._local_today = lambda: date(2026, 6, 6)

    scheduled = svc._initial_daily_run(job=_oilchem_job(), now=datetime(2026, 6, 6, 8, 0))

    assert scheduled == datetime(2026, 6, 7, 6, 0)


def test_oilchem_spot_report_daily_job_does_not_catch_up_when_today_archive_exists() -> None:
    svc = object.__new__(SchedulerService)
    svc.dataset_service = type(
        "Dataset",
        (),
        {
            "snapshot_repository": _FakeNewsRepository(
                [],
                source_counts={"oilchem_shandong_spot_daily_report": 1},
            )
        },
    )()
    svc._local_today = lambda: date(2026, 6, 6)

    scheduled = svc._initial_daily_run(job=_oilchem_job(), now=datetime(2026, 6, 6, 8, 0))

    assert scheduled == datetime(2026, 6, 7, 6, 0)


def test_morning_briefing_daily_job_runs_at_0805_before_schedule() -> None:
    svc = object.__new__(SchedulerService)
    svc._local_today = lambda: date(2026, 6, 6)
    svc._has_today_briefing = lambda: False

    scheduled = svc._initial_daily_run(job=_morning_briefing_job(), now=datetime(2026, 6, 6, 8, 4))

    assert scheduled == datetime(2026, 6, 6, 8, 5)


def test_morning_briefing_daily_job_next_day_after_schedule_when_exists() -> None:
    svc = object.__new__(SchedulerService)
    svc._local_today = lambda: date(2026, 6, 6)
    svc._has_today_briefing = lambda: True

    scheduled = svc._initial_daily_run(job=_morning_briefing_job(), now=datetime(2026, 6, 6, 8, 6))

    assert scheduled == datetime(2026, 6, 7, 8, 5)


def test_brent_report_daily_job_runs_at_0800_before_briefing() -> None:
    svc = object.__new__(SchedulerService)

    scheduled = svc._initial_daily_run(job=_brent_report_job(), now=datetime(2026, 6, 6, 7, 59))

    assert scheduled == datetime(2026, 6, 6, 8, 0)


def test_prediction_time_alignment_blocks_current_date_with_stale_brent_report(monkeypatch) -> None:
    svc = _market_service()
    monkeypatch.setattr("app.services.market_dataset.date", type("FixedDate", (date,), {"today": classmethod(lambda cls: date(2026, 6, 12))}))

    error = svc._prediction_time_alignment_error(
        as_of_date=date(2026, 6, 12),
        report_payload={
            "report_date": "2026-06-11",
            "signals": {
                "brent_settlement": 93.1,
                "daily_forecast": {"point_value": 94.78, "forecast_date": "2026-06-11"},
            },
        },
    )

    assert isinstance(error, PredictionTimeAlignmentError)
    assert error.report_date == date(2026, 6, 11)


def test_prediction_time_alignment_allows_report_for_current_price_base_date(monkeypatch) -> None:
    svc = _market_service()
    monkeypatch.setattr("app.services.market_dataset.date", type("FixedDate", (date,), {"today": classmethod(lambda cls: date(2026, 6, 16))}))

    error = svc._prediction_time_alignment_error(
        as_of_date=date(2026, 6, 16),
        report_payload={
            "report_date": "2026-06-16",
            "signals": {
                "brent_settlement": 83.17,
                "daily_forecast": {"point_value": 81.78, "forecast_date": "2026-06-16"},
            },
        },
    )

    assert error is None


def test_prediction_time_alignment_allows_current_date_with_complete_brent_report(monkeypatch) -> None:
    svc = _market_service()
    monkeypatch.setattr("app.services.market_dataset.date", type("FixedDate", (date,), {"today": classmethod(lambda cls: date(2026, 6, 12))}))

    error = svc._prediction_time_alignment_error(
        as_of_date=date(2026, 6, 11),
        report_payload={
            "report_date": "2026-06-12",
            "signals": {
                "brent_settlement": 90.38,
                "daily_forecast": {"point_value": 88.32, "forecast_date": "2026-06-12"},
            },
        },
    )

    assert error is None
