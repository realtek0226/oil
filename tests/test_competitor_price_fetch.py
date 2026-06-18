from datetime import date

from app.clients.competitor_price_client import CompetitorPriceClient
from app.services.market_dataset import MarketDatasetService
from app.services.scheduler_service import SchedulerService


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "day": "2026-06-18",
                "products": [
                    {
                        "product": "92#VI",
                        "items": [
                            {"company": "\u91d1\u8bda", "yesterdayPrice": 8053, "todayPrice": 8023},
                            {"company": "\u5bcc\u6d77", "yesterdayPrice": 8003, "todayPrice": 7943},
                            {"company": "\u76db\u9a6c\u5316\u5de5-\u897f\u5357", "todayPrice": 8050},
                        ],
                    },
                    {
                        "product": "0#VI",
                        "items": [
                            {"company": "\u91d1\u8bda", "todayPrice": 7073},
                            {"company": "\u6d77\u79d1", "todayPrice": 6990},
                        ],
                    },
                ],
            },
        }


class _Repository:
    enabled = True

    def __init__(self) -> None:
        self.saved_records = []

    def save_competitor_market_price_records(self, records):
        self.saved_records = records
        return 3


class _HistoryRepository:
    enabled = True

    def load_market_timeseries_values(self, *, source_code, indicator_codes, start_date, end_date):
        if source_code == "ganglian_excel_import":
            return [
                {
                    "indicator_code": "sd_gas92_market",
                    "entity_code": "SHANDONG",
                    "dt": date(2026, 6, 17),
                    "value_num": 7905.22,
                    "publish_time": "2026-06-17T18:00:00",
                }
            ]
        if source_code == "competitor_price_openapi":
            assert indicator_codes == ["competitor_sd_gas92_market_avg"]
            return [
                {
                    "indicator_code": "competitor_sd_gas92_market_avg",
                    "entity_code": "COMPETITOR_SHANDONG_GASOLINE_92",
                    "dt": date(2026, 6, 18),
                    "value_num": 7877.44,
                    "publish_time": "2026-06-18T15:00:00",
                }
            ]
        return []


class _Settings:
    enabled = True
    timezone = "Asia/Shanghai"
    snapshot_interval_seconds = 0
    policy_event_interval_seconds = 0
    morning_briefing_time = ""
    brent_report_fetch_time = ""
    oilchem_spot_report_fetch_time = ""
    oilchem_price_fetch_time = ""
    oilchem_production_sales_fetch_time = ""
    oilchem_independent_maintenance_fetch_time = ""
    oilchem_main_maintenance_fetch_time = ""
    oilchem_daily_fetch_time = ""
    competitor_price_fetch_time = "15:00"
    oilchem_openapi_inventory_fetch_time = ""
    sci99_price_adjustment_fetch_time = ""
    refined_news_fetch_time = ""


def test_competitor_price_client_parses_products(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.competitor_price_client.requests.get", lambda *_, **__: _Response())

    records = CompetitorPriceClient().fetch_day(date(2026, 6, 18))

    assert len(records) == 5
    assert records[0].product_code == "gasoline92"
    assert records[0].company == "\u91d1\u8bda"
    assert records[0].today_price == 8023.0
    assert records[-1].product_code == "diesel0"


def test_dataset_refresh_saves_competitor_records(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.competitor_price_client.requests.get", lambda *_, **__: _Response())
    repository = _Repository()
    svc = object.__new__(MarketDatasetService)
    svc.competitor_price_client = CompetitorPriceClient()
    svc.snapshot_repository = repository
    svc._context_cache = {}
    svc._feature_frame_cache = {}
    svc._price_history_frame_cache = {}

    summary = svc.refresh_competitor_price_archive(date(2026, 6, 18))

    assert summary["status"] == "ok"
    assert summary["fetched_count"] == 5
    assert summary["saved_timeseries_count"] == 3
    assert repository.saved_records[0]["company"] == "\u91d1\u8bda"


def test_scheduler_registers_competitor_price_at_1500() -> None:
    svc = object.__new__(MarketDatasetService)
    svc.web_scraping_enabled = False
    svc.oilchem_scraping_enabled = False
    svc.oilchem_spot_report_scraping_enabled = False
    svc.oilchem_openapi_client = None
    svc.competitor_price_client = object()

    scheduler = SchedulerService(settings=_Settings(), dataset_service=svc, workbench_service=object())
    job = scheduler.get_status()["jobs"]
    competitor_job = next(item for item in job if item["job_key"] == "competitor_price_fetch")

    assert competitor_job["enabled"] is True
    assert competitor_job["mode"] == "daily"
    assert competitor_job["schedule_value"] == "15:00"


def test_price_history_uses_competitor_archive_alias_for_today() -> None:
    svc = object.__new__(MarketDatasetService)
    svc.snapshot_repository = _HistoryRepository()

    rows = svc._load_price_history_rows_from_archive(
        requested=["sd_gas92_market"],
        start_date=date(2026, 6, 17),
        end_date=date(2026, 6, 18),
    )

    points = {item["date"].date(): item["sd_gas92_market"] for _, item in rows.iterrows()}
    assert points[date(2026, 6, 17)] == 7905.22
    assert points[date(2026, 6, 18)] == 7877.44
