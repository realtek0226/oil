from datetime import date
from pathlib import Path

import pandas as pd

from app.services.predictors.horizons import resolve_horizon_config
from app.services.predictors.shandong_gas92 import ShandongGas92Predictor
from app.services.agents.deterministic_agents import BusinessScorecardAgent


def test_business_scorecard_uses_own_bucket_thresholds() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    history = pd.DataFrame(
        {
            "business_scorecard_score": [0.0] * 20,
            "target_delta": [0.0] * 20,
        }
    )

    mapping = predictor._score_delta_mapping(
        frame=pd.DataFrame(),
        as_of_date=date(2026, 6, 11),
        horizon_config=resolve_horizon_config("D1"),
        score_column="business_scorecard_score",
        score_value=30.0,
        scored_history=history,
    )

    assert mapping["bucket_schema"] == "business_scorecard"
    assert mapping["bucket"] == "强多"
    assert mapping["bucket_range"] == ">=30"
    assert mapping["status"] == "cold_start"
    assert mapping["history_sample_size"] == 20
    assert mapping["predicted_delta"] == 45.0


def test_agent_composite_keeps_its_existing_bucket_thresholds() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    history = pd.DataFrame(
        {
            "agent_score": [0.38] * 20,
            "target_delta": [0.0] * 20,
        }
    )

    mapping = predictor._score_delta_mapping(
        frame=pd.DataFrame(),
        as_of_date=date(2026, 6, 11),
        horizon_config=resolve_horizon_config("D1"),
        score_column="agent_score",
        score_value=0.38,
        scored_history=history,
    )

    assert mapping["bucket_schema"] == "agent_composite"
    assert mapping["bucket"] == "强多"
    assert mapping["bucket_range"] == ">=38"
    assert mapping["status"] == "empirical"
    assert mapping["sample_size"] == 20
    assert mapping["predicted_delta"] == 0.0
    assert mapping["directional_fallback"]["applied"] is False


def test_directional_bucket_uses_bucket_quantile_rule_instead_of_same_direction_fallback() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    history = pd.DataFrame(
        {
            "agent_score": [0.38] * 12,
            "target_delta": [-80.0, -60.0, -40.0, -20.0, -10.0, -5.0, -1.0, 20.0, 40.0, 80.0, 100.0, 120.0],
        }
    )

    mapping = predictor._score_delta_mapping(
        frame=pd.DataFrame(),
        as_of_date=date(2026, 6, 11),
        horizon_config=resolve_horizon_config("D3"),
        score_column="agent_score",
        score_value=0.38,
        scored_history=history,
    )

    assert mapping["bucket_schema"] == "agent_composite"
    assert mapping["bucket"] == "强多"
    assert mapping["semantic_constraint_applied"] is False
    assert mapping["directional_fallback"]["applied"] is False
    assert mapping["directional_fallback"]["reason"] == "bucket_quantile_rule"
    assert mapping["selected_quantile"] == 0.75
    assert mapping["raw_p50_delta"] < 0
    assert mapping["predicted_delta"] == 50.0
    assert mapping["p50_delta"] == mapping["raw_p50_delta"]



def test_supply_relief_event_needs_confirmed_brent_drop_before_hard_overlay() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    event_text = "\u7f8e\u4f0a\u505c\u6218\u5ba3\u5e03\u970d\u5c14\u6728\u5179\u6d77\u5ce1\u89e3\u5c01"

    event_label = predictor._fallback_event_risk_label(news_items=[{"title": event_text}], report_payload=None)
    assert event_label["event_type"] == "supply_relief"
    assert event_label["direction"] == "down"
    assert event_label["severity"] == "high"

    weak_adjustment = predictor._event_cost_overlay_adjustment(
        base_predicted_delta=40.0,
        brent_change=-2.0,
        gate_level="high",
        gate_direction="down",
        horizon="D1",
        event_type="supply_relief",
    )

    assert weak_adjustment == 0.0

    confirmed_adjustment = predictor._event_cost_overlay_adjustment(
        base_predicted_delta=40.0,
        brent_change=-3.2,
        gate_level="high",
        gate_direction="down",
        horizon="D1",
        event_type="supply_relief",
    )

    assert confirmed_adjustment == -120.0
    assert 40.0 + confirmed_adjustment == -80.0


def test_business_event_review_does_not_mutate_business_delta() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    business_delta = -20.0
    event_overlay = predictor._event_cost_overlay_adjustment(
        base_predicted_delta=business_delta,
        brent_change=-3.2,
        gate_level="high",
        gate_direction="down",
        horizon="D1",
        event_type="supply_relief",
    )
    review = predictor._build_business_event_review(
        predicted_delta=business_delta,
        event_overlay_delta=event_overlay,
        event_gate={
            "level": "high",
            "label": "事件扰动中",
            "action": "人工复核",
            "llm_risk_gate": {
                "event_type": "supply_relief",
                "direction": "down",
                "severity": "high",
            },
        },
    )

    assert event_overlay == -60.0
    assert review["applied_to_business_prediction"] is False
    assert review["business_delta_before_event_review"] == business_delta
    assert review["suggested_delta_if_event_review_accepted"] == -80.0




def test_m1_maintenance_and_restocking_labels_match_scorecard_rules() -> None:
    import pandas as pd

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    row = pd.Series(
        {
            "restocking_rhythm_monthly_change": 4.0,
            "sd_crude_run_weekly": 51.09,
        }
    )
    claim = agent.analyze(
        row,
        {
            "horizon": "M1",
            "as_of_date": date(2026, 6, 12),
            "oilchem_maintenance_plan": {"summary": "\u4e0b\u6708\u96c6\u4e2d\u68c0\u4fee\uff0c\u70bc\u5382\u964d\u8d1f"},
        },
    )
    scorecard = claim.structured_payload["scorecard"]
    features = {
        feature["feature_name"]: feature
        for group in scorecard["groups"]
        for feature in group["features"]
    }

    assert features["next_month_maintenance_plan"]["value"] == "concentrated_maintenance_supply_tight"
    assert features["next_month_maintenance_plan"]["score"] == 15
    assert features["restocking_rhythm_monthly"]["value"] == "active_restocking"
    assert features["restocking_rhythm_monthly"]["score"] == 5



def test_business_scorecard_includes_crack_percentile_cost_adjustment() -> None:
    import pandas as pd

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    row = pd.Series(
        {
            "gasoline_crack_percentile": 20.0,
            "sd_crude_run_weekly": 50.0,
            "sales_production_ratio_d1": 96.0,
        }
    )
    claim = agent.analyze(
        row,
        {
            "horizon": "D1",
            "as_of_date": date(2026, 6, 12),
            "report_payload": {"signals": {"brent_settlement": 90.38, "daily_forecast": {"point_value": 90.38}}},
            "trade_sentiment": {"label": "neutral"},
        },
    )
    scorecard = claim.structured_payload["scorecard"]
    cost_group = next(group for group in scorecard["groups"] if group["group_code"] == "cost")
    crack_feature = next(feature for feature in cost_group["features"] if feature["feature_name"] == "gasoline_crack_percentile")

    assert crack_feature["score"] == 10
    assert crack_feature["matched_label"] == "low_crack_percentile"
    assert cost_group["score"] == 10


def test_business_scorecard_high_crack_percentile_is_bearish() -> None:
    import pandas as pd

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    row = pd.Series(
        {
            "gasoline_crack_percentile": 80.0,
            "sd_crude_run_weekly": 50.0,
            "sales_production_ratio_w1_avg": 96.0,
            "shandong_product_inventory_percentile_weekly": 50.0,
        }
    )
    claim = agent.analyze(
        row,
        {
            "horizon": "W1",
            "as_of_date": date(2026, 6, 12),
            "report_payload": {"signals": {"brent_settlement": 90.38, "horizon_forecasts": {"W1": {"point_value": 90.38}}}},
            "trade_sentiment": {"label": "neutral"},
        },
    )
    scorecard = claim.structured_payload["scorecard"]
    cost_group = next(group for group in scorecard["groups"] if group["group_code"] == "cost")
    crack_feature = next(feature for feature in cost_group["features"] if feature["feature_name"] == "gasoline_crack_percentile")

    assert crack_feature["score"] == -10
    assert crack_feature["matched_label"] == "high_crack_percentile"
    assert cost_group["score"] == -10


def test_weekly_inventory_uses_formal_combined_inventory_percentile_field() -> None:
    import pandas as pd

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    row = pd.Series(
        {
            "gasoline_crack_percentile": 50.0,
            "sd_crude_run_weekly": 50.0,
            "sales_production_ratio_w1_avg": 96.0,
            "shandong_product_inventory_percentile_weekly": 20.0,
            "shandong_product_inventory_total_formal": 123.0,
        }
    )
    claim = agent.analyze(
        row,
        {
            "horizon": "W1",
            "as_of_date": date(2026, 6, 12),
            "report_payload": {"signals": {"brent_settlement": 90.38, "horizon_forecasts": {"W1": {"point_value": 90.38}}}},
        },
    )
    scorecard = claim.structured_payload["scorecard"]
    inventory_group = next(group for group in scorecard["groups"] if group["group_code"] == "inventory")
    inventory_feature = inventory_group["features"][0]

    assert inventory_feature["feature_name"] == "shandong_product_inventory_percentile_weekly"
    assert inventory_feature["score"] == 15
    assert inventory_feature["matched_label"] == "low_percentile"



def test_inventory_feature_scores_zero_when_inventory_is_unchanged() -> None:
    import pandas as pd

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    row = pd.Series(
        {
            "gasoline_crack_percentile": 50.0,
            "sd_crude_run_weekly": 50.0,
            "sales_production_ratio_w1_avg": 96.0,
            "shandong_product_inventory_percentile_weekly": 20.0,
            "shandong_product_inventory_change_weekly": 0.0,
        }
    )
    claim = agent.analyze(
        row,
        {
            "horizon": "W1",
            "as_of_date": date(2026, 6, 12),
            "report_payload": {"signals": {"brent_settlement": 90.38, "horizon_forecasts": {"W1": {"point_value": 90.38}}}},
        },
    )
    scorecard = claim.structured_payload["scorecard"]
    inventory_group = next(group for group in scorecard["groups"] if group["group_code"] == "inventory")
    inventory_feature = inventory_group["features"][0]

    assert inventory_feature["score"] == 0
    assert inventory_feature["matched_label"] == "unchanged_from_previous"



def test_diesel_business_scorecard_uses_diesel_rules_and_fields() -> None:
    import pandas as pd

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    row = pd.Series(
        {
            "diesel_crack_percentile": 20.0,
            "sd_crude_run_weekly": 50.0,
            "diesel_sales_production_ratio_d1": 96.0,
        }
    )
    claim = agent.analyze(
        row,
        {
            "product_code": "DIESEL_0",
            "horizon": "D1",
            "as_of_date": date(2026, 6, 12),
            "report_payload": {"signals": {"brent_settlement": 90.38, "daily_forecast": {"point_value": 90.38}}},
            "trade_sentiment": {"label": "neutral_flat"},
        },
    )
    scorecard = claim.structured_payload["scorecard"]
    cost_group = next(group for group in scorecard["groups"] if group["group_code"] == "cost")
    demand_group = next(group for group in scorecard["groups"] if group["group_code"] == "demand")
    crack_feature = next(feature for feature in cost_group["features"] if feature["feature_name"] == "diesel_crack_percentile")
    ratio_feature = demand_group["features"][0]

    assert scorecard["scorecard_code"] == "sd_diesel0"
    assert crack_feature["score"] == 10
    assert ratio_feature["feature_name"] == "diesel_sales_production_ratio_d1"
    assert ratio_feature["score"] == 5


def test_scorecard_executes_calendar_and_price_window_enums() -> None:
    import pandas as pd

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    row = pd.Series(
        {
            "gasoline_crack_percentile": 50.0,
            "sd_crude_run_weekly": 50.0,
            "sales_production_ratio_monthly_change": 0.0,
            "shandong_refinery_inventory_percentile_monthly": 50.0,
            "shandong_main_company_inventory_percentile_monthly": 50.0,
            "price_adjustment_expected_yuan": 80.0,
        }
    )
    claim = agent.analyze(
        row,
        {
            "horizon": "M1",
            "as_of_date": date(2026, 6, 12),
            "report_payload": {"signals": {"brent_settlement": 90.38, "horizon_forecasts": {"M1": {"point_value": 90.38}}}},
            "monthly_market_sentiment": {"label": "neutral"},
        },
    )
    scorecard = claim.structured_payload["scorecard"]
    features = {
        feature["feature_name"]: feature
        for group in scorecard["groups"]
        for feature in group["features"]
    }

    assert features["monthly_seasonality_phase"]["value"] == "peak"
    assert features["monthly_seasonality_phase"]["score"] == 5
    assert features["price_window_expectation_monthly"]["value"] == "up_adjustment_expected"
    assert features["price_window_expectation_monthly"]["score"] == 5



def test_gasoline_scorecard_has_all_612_features_for_each_horizon() -> None:
    import yaml

    config = yaml.safe_load(Path("configs/scorecards/shandong_scorecards_v1.yaml").read_text(encoding="utf-8"))
    scorecard = next(item for item in config["scorecards"] if item["scorecard_code"] == "sd_gas92")
    expected = {
        "D1": {
            "brent_change_usd_d1",
            "gasoline_crack_percentile",
            "shandong_cdu_utilization_weekly",
            "shandong_refinery_load_news_adjustment_d1",
            "sales_production_ratio_d1",
            "trader_sentiment_label_d1",
        },
        "D3": {
            "brent_change_usd_d3",
            "gasoline_crack_percentile",
            "shandong_cdu_utilization_weekly",
            "shandong_refinery_load_news_adjustment_d3",
            "sales_production_ratio_d3_avg",
            "trader_sentiment_label_d3",
        },
        "W1": {
            "brent_change_usd_w1",
            "gasoline_crack_percentile",
            "shandong_cdu_utilization_weekly",
            "shandong_refinery_load_news_adjustment_w1",
            "sales_production_ratio_w1_avg",
            "shandong_product_inventory_percentile_weekly",
            "price_window_expectation_weekly",
        },
        "M1": {
            "brent_change_usd_mom",
            "gasoline_crack_percentile",
            "shandong_cdu_utilization_weekly",
            "next_month_maintenance_plan",
            "restocking_rhythm_monthly",
            "monthly_seasonality_phase",
            "holiday_demand_delta_monthly",
            "refinery_inventory_monthly",
            "main_company_inventory_monthly",
            "price_window_expectation_monthly",
            "market_sentiment_monthly",
        },
    }
    for horizon, expected_features in expected.items():
        groups = scorecard["horizons"][horizon]["factor_groups"]
        actual_features = {
            feature["feature_name"]
            for group in groups
            for feature in [*(group.get("features") or []), *(group.get("adjustments") or [])]
        }
        assert expected_features <= actual_features



def test_inventory_weekly_accepts_available_components_but_flags_regression_missing() -> None:
    from app.services.market_dataset import MarketDatasetService

    service = object.__new__(MarketDatasetService)
    dates = pd.date_range("2024-01-01", periods=12, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "sd_gas92_market": [7800.0] * 12,
            "cn_gas92_market": [7800.0] * 12,
            "sd_diesel0_market": [6900.0] * 12,
            "cn_diesel0_market": [6900.0] * 12,
            "east_china_gas92_market": [7800.0] * 12,
            "north_china_gas92_market": [7800.0] * 12,
            "south_china_gas92_market": [7800.0] * 12,
            "central_china_gas92_market": [7800.0] * 12,
            "northwest_gas92_market": [7800.0] * 12,
            "southwest_gas92_market": [7800.0] * 12,
            "northeast_gas92_market": [7800.0] * 12,
            "brent_active_settlement": [80.0] * 12,
            "sd_refining_profit": [100.0] * 12,
            "sd_gas_sales_weekly": [10.0] * 12,
            "sd_gas_production_weekly": [10.0] * 12,
            "sd_crude_run_weekly": [50.0] * 12,
            "sd_ceiling_gas": [9000.0] * 12,
            "sd_mtbe_price": [6500.0] * 12,
            "sd_naphtha_price": [6200.0] * 12,
            "sd_gas_naphtha_spread": [1000.0] * 12,
            "sd_gas_shipments_weekly": [10.0] * 12,
            "shandong_main_company_inventory": [20.0 + i for i in range(12)],
            "shandong_independent_refinery_inventory": [70.0 + i for i in range(12)],
        }
    )
    computed = service._compute_features(frame, policy_items=[])

    assert computed.loc[10, "shandong_product_inventory_total_formal"] == 110.0
    assert pd.notna(computed.loc[10, "shandong_product_inventory_percentile_weekly"])
    assert computed.loc[10, "shandong_product_inventory_missing_component_count"] == 0.0

    frame.loc[10, "shandong_main_company_inventory"] = float("nan")
    computed_missing = service._compute_features(frame, policy_items=[])
    assert computed_missing.loc[10, "shandong_product_inventory_total_formal"] == 80.0
    assert computed_missing.loc[10, "shandong_product_inventory_missing_component_count"] == 1.0


def test_m1_restocking_uses_previous_two_month_active_day_count() -> None:
    from app.services.market_dataset import MarketDatasetService

    service = object.__new__(MarketDatasetService)
    dates = pd.date_range("2026-04-01", "2026-06-12", freq="D")
    ratios = []
    for current in dates:
        if current.month == 4:
            ratios.append(95.0 if current.day <= 5 else 80.0)
        elif current.month == 5:
            ratios.append(95.0 if current.day <= 8 else 80.0)
        else:
            ratios.append(80.0)
    frame = pd.DataFrame({"date": dates, "sales_production_ratio_d1": ratios})

    previous = service._previous_month_active_day_count(frame, "sales_production_ratio_d1", month_offset=1, threshold=90.0)
    before_previous = service._previous_month_active_day_count(frame, "sales_production_ratio_d1", month_offset=2, threshold=90.0)
    june_row = frame.index[frame["date"] == pd.Timestamp("2026-06-12")][0]

    assert previous.iloc[june_row] == 8.0
    assert before_previous.iloc[june_row] == 5.0

    agent = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml")
    assert agent._feature_value(
        "restocking_rhythm_monthly",
        pd.Series({"restocking_rhythm_monthly_change": previous.iloc[june_row] - before_previous.iloc[june_row]}),
        {"horizon": "M1", "as_of_date": date(2026, 6, 12)},
    ) == "active_restocking"


def test_scorecard_yaml_has_chinese_labels_and_2024_percentile_notes() -> None:
    text = Path("configs/scorecards/shandong_scorecards_v1.yaml").read_text(encoding="utf-8")
    assert "Policy and sentiment" not in text
    assert "???" not in text
    assert "2025-01-01" not in text
    assert "\u653f\u7b56\u4e0e\u60c5\u7eea\u4fa7" in text
    assert "2024-01-01" in text


def test_event_risk_priority_detects_ceasefire_and_hormuz_reopen() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    predictor.llm_client = type("DummyLlm", (), {"enabled": True, "settings": type("S", (), {"model_name": "dummy"})()})()
    predictor._trade_sentiment_cache = {}
    event_text = "\u7f8e\u4f0a\u505c\u6218\u5ba3\u5e03\u970d\u5c14\u6728\u5179\u6d77\u5ce1\u89e3\u5c01\uff0c\u822a\u8fd0\u6062\u590d"

    result = predictor._build_event_risk_label_signal(
        as_of_date=date(2026, 6, 15),
        mode="predict",
        news_items=[{"title": event_text}],
        report_payload=None,
        scenario_text=None,
    )

    assert result["event_type"] == "supply_relief"
    assert result["direction"] == "down"
    assert result["severity"] == "high"
    assert result["manual_review_required"] is True


def test_event_relief_keyword_rule_handles_ceasefire_and_reopen_variants() -> None:
    predictor = object.__new__(ShandongGas92Predictor)

    assert predictor._event_relief_direction("美伊宣布停战，霍尔木兹海峡解封，航运恢复") == "down"
    assert predictor._event_relief_direction("霍尔木兹恢复通航，解除封锁") == "down"
    assert predictor._event_relief_direction("Strait of Hormuz reopened after ceasefire") == "down"
