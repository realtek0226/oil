from datetime import date, datetime

from app.services.market_dataset import MarketDatasetService


def _service() -> MarketDatasetService:
    return object.__new__(MarketDatasetService)


def test_news_cutoff_includes_same_day_items_before_seven() -> None:
    svc = _service()

    assert svc._is_news_item_available_by_cutoff(
        {"publish_time": "2026-06-06 06:59:00"},
        date(2026, 6, 6),
    )


def test_news_cutoff_includes_same_day_items_at_seven() -> None:
    svc = _service()

    assert svc._is_news_item_available_by_cutoff(
        {"publish_time": datetime(2026, 6, 6, 7, 0, 0).isoformat()},
        date(2026, 6, 6),
    )


def test_news_cutoff_excludes_same_day_items_after_seven() -> None:
    svc = _service()

    assert not svc._is_news_item_available_by_cutoff(
        {"publish_time": "2026-06-06 07:01:00"},
        date(2026, 6, 6),
    )


def test_news_cutoff_includes_previous_day_evening_report() -> None:
    svc = _service()

    assert svc._is_news_item_available_by_cutoff(
        {"publish_time": "2026-06-05 17:26:00"},
        date(2026, 6, 6),
    )


def test_news_cutoff_excludes_same_day_date_only_item() -> None:
    svc = _service()

    assert not svc._is_news_item_available_by_cutoff(
        {"publish_date": "2026-06-06"},
        date(2026, 6, 6),
    )


def test_news_cutoff_uses_title_date_only_for_previous_day() -> None:
    svc = _service()

    assert svc._is_news_item_available_by_cutoff(
        {"title": "山东成品油日评（20260605）"},
        date(2026, 6, 6),
    )
