from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd

from app.models.common import AgentClaim
from app.services.market_dataset import PredictionContext
from app.services.predictors.shandong_gas92 import ShandongGas92Predictor


def _claim(name: str, score: float) -> AgentClaim:
    return AgentClaim(
        agent_name=name,
        direction="up" if score > 0 else "down" if score < 0 else "flat",
        confidence_label="medium",
        confidence_score=0.8,
        summary=name,
        evidence=[f"{name} evidence"],
        numeric_signals={
            "raw_score": score,
            "weighted_score": score,
            "score": score,
            "standalone_score": score * 100,
        },
    )


def test_diesel0_prediction_uses_same_bucket_logic_with_diesel_target_column(monkeypatch):
    start = date(2026, 1, 1)
    dates = [start + timedelta(days=index) for index in range(45)]
    frame = pd.DataFrame(
        {
            "date": dates,
            "sd_gas92_market": [8000.0 + index for index in range(45)],
            "sd_diesel0_market": [7000.0 + index * 10.0 for index in range(45)],
            "gas_price_change_1d": [1.0] * 45,
            "diesel_price_change_1d": [10.0] * 45,
            "diesel_price_change_3d": [30.0] * 45,
            "gasoline_crack_percentile": [20.0] * 45,
            "diesel_crack_change_3d": [50.0] * 45,
            "diesel_crack_trend": [1.0] * 45,
            "diesel_crack_percentile": [80.0] * 45,
            "sales_production_ratio_d1": [90.0] * 45,
            "diesel_sales_production_ratio_d1": [115.0] * 45,
            "diesel_sales_production_ratio_d3_avg": [112.0] * 45,
            "diesel_sales_production_ratio_w1_avg": [110.0] * 45,
            "diesel_sales_production_ratio_monthly_avg": [108.0] * 45,
            "diesel_sales_production_ratio_monthly_change": [4.0] * 45,
            "shandong_gasoline_inventory_change_mom": [2.0] * 45,
            "shandong_diesel_inventory_change_mom": [-2.0] * 45,
            "shandong_diesel_inventory_capacity_rate": [34.0] * 45,
            "shandong_diesel_inventory_percentile_monthly": [25.0] * 45,
            "shandong_diesel_inventory_change_weekly": [-1.5] * 45,
            "brent_active_settlement": [75.0] * 45,
            "usd_cny_mid_rate": [7.1] * 45,
        }
    )
    context = PredictionContext(
        feature_frame=frame,
        current_row=frame.iloc[30],
        report_payload=None,
        news_items=[],
        refined_news_items=[],
        policy_items=[],
        metadata={"market_data_mode": "eta"},
    )
    predictor = object.__new__(ShandongGas92Predictor)
    predictor.llm_client = SimpleNamespace(enabled=False)
    predictor._trade_sentiment_cache = {}
    predictor._monthly_sentiment_cache = {}

    monkeypatch.setattr(predictor, "_build_trade_sentiment_signal", lambda **_: {})
    monkeypatch.setattr(predictor, "_build_monthly_market_sentiment_signal", lambda **_: {})
    monkeypatch.setattr(predictor, "_build_refined_news_label_signal", lambda **_: {})
    monkeypatch.setattr(predictor, "_build_event_risk_label_signal", lambda **_: {})
    seen_rows = []

    def fake_business_scorecard(row, extra):
        seen_rows.append(row)
        assert row.get("gas_price_change_1d") == 10.0
        assert row.get("gasoline_crack_percentile") == 80.0
        assert row.get("sales_production_ratio_d1") == 115.0
        assert row.get("shandong_gasoline_inventory_change_mom") == -2.0
        return _claim("business_scorecard_agent", 0.6)

    monkeypatch.setattr(predictor, "_score_business_scorecard", fake_business_scorecard)
    monkeypatch.setattr(predictor, "_score_row", lambda row, extra: ([_claim("crude_cost_agent", 0.2)], 0.15))
    monkeypatch.setattr(predictor, "_score_calibration_row", lambda row, extra: ([], 0.15))
    monkeypatch.setattr(predictor, "_build_event_gate", lambda **_: {"level": "low", "label": "低", "action": "模型正常展示"})
    monkeypatch.setattr(predictor, "_point_adjustments", lambda **_: {})
    monkeypatch.setattr(predictor, "_range_half_width", lambda **_: 40.0)

    result = predictor.run_diesel0_prediction_from_context(
        context=context,
        as_of_date=dates[30],
        horizon="D1",
        use_llm_explainer=False,
    )

    assert result.entity_code == "SD_DIESEL0"
    assert result.product_code == "DIESEL_0"
    assert result.raw_context["current_price"] == 7300.0
    assert result.raw_context["current_price_column"] == "sd_diesel0_market"
    assert result.raw_context["point_mapping"]["predicted_delta"] == 10.0
    assert result.point_value == 7310.0
    assert result.raw_context["business_scorecard_prediction"]["current_price"] == 7300.0
    assert result.raw_context["business_scorecard_prediction"]["point_value"] == 7310.0
    assert result.raw_context["product_data_quality"]["status"] == "ready"
    assert result.raw_context["product_data_quality"]["applied_overrides"]
    assert seen_rows
