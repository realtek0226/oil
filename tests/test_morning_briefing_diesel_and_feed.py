from datetime import date
from types import SimpleNamespace

from app.services.market_dataset import MarketDatasetService
from app.services.workbench_service import WorkbenchService


def _prediction(horizon: str, point: float) -> SimpleNamespace:
    return SimpleNamespace(
        horizon=horizon,
        direction_label="up",
        point_value=point,
        range_lower=point - 20,
        range_upper=point + 20,
        operating_advice=[
            SimpleNamespace(title="经营动作分层", action="小批滚动补库"),
        ],
    )


def test_morning_briefing_markdown_includes_diesel_predictions_and_prices() -> None:
    service = object.__new__(WorkbenchService)

    markdown = service._build_briefing_markdown(
        as_of_date=date(2026, 6, 12),
        outright_predictions=[_prediction("D1", 8000.0)],
        diesel0_predictions=[_prediction("D1", 7100.0)],
        regional_predictions=[],
        context={
            "brent_active_settlement": 75.0,
            "sd_gas92_market": 8050.0,
            "cn_gas92_market": 8200.0,
            "east_china_gas92_market": 8150.0,
            "sd_diesel0_market": 7200.0,
            "cn_diesel0_market": 7300.0,
            "east_china_diesel0_market": 7250.0,
        },
        policy_items=[],
        event_items=[],
    )

    assert "山东0#柴油: 7200.00" in markdown
    assert "0#柴油 D1" in markdown
    assert "0#柴油 | 经营动作分层" in markdown


def test_market_feed_alerts_infer_diesel_product_scope() -> None:
    service = object.__new__(MarketDatasetService)

    alerts = service._build_alert_items(
        refined_news_items=[
            {
                "headline": "山东地炼柴油价格快报 上调",
                "publish_time": "2026-06-12 06:30:00",
                "source": "oilchem_shandong_spot_daily_report",
                "_importance_score": 12.0,
            }
        ],
        event_news_items=[],
        policy_items=[],
    )

    assert alerts
    assert alerts[0]["affected_product"] == "0#柴油"


def test_policy_alerts_show_gasoline_and_diesel_adjustment_scope() -> None:
    service = object.__new__(MarketDatasetService)

    alerts = service._build_alert_items(
        refined_news_items=[],
        event_news_items=[],
        policy_items=[
            {
                "title": "国内成品油价格调整",
                "effective_time": "2026-06-12 24:00",
                "gasoline_change_yuan_per_ton": 120,
                "diesel_change_yuan_per_ton": 110,
                "_importance_score": 9.0,
            }
        ],
    )

    assert alerts
    assert "柴油上调110元/吨" in alerts[0]["title"]
    assert alerts[0]["affected_product"] == "92#汽油 / 0#柴油"
    assert alerts[0]["expected_impact"] == "汽油 +120 / 柴油 +110 元/吨"
