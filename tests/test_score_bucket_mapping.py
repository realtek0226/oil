from datetime import date

import pandas as pd

from app.services.predictors.horizons import resolve_horizon_config
from app.services.predictors.shandong_gas92 import ShandongGas92Predictor


def test_business_scorecard_uses_own_bucket_thresholds() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    history = pd.DataFrame(
        {
            "business_scorecard_score": [15.0] * 20,
            "target_delta": [0.0] * 20,
        }
    )

    mapping = predictor._score_delta_mapping(
        frame=pd.DataFrame(),
        as_of_date=date(2026, 6, 11),
        horizon_config=resolve_horizon_config("D1"),
        score_column="business_scorecard_score",
        score_value=70.0,
        scored_history=history,
    )

    assert mapping["bucket_schema"] == "business_scorecard"
    assert mapping["bucket"] == "强多"
    assert mapping["bucket_range"] == ">=70"
    assert mapping["status"] == "cold_start"
    assert mapping["history_sample_size"] == 20
    assert mapping["predicted_delta"] == 45.0


def test_agent_composite_keeps_its_existing_bucket_thresholds() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    history = pd.DataFrame(
        {
            "agent_score": [0.15] * 20,
            "target_delta": [0.0] * 20,
        }
    )

    mapping = predictor._score_delta_mapping(
        frame=pd.DataFrame(),
        as_of_date=date(2026, 6, 11),
        horizon_config=resolve_horizon_config("D1"),
        score_column="agent_score",
        score_value=0.70,
        scored_history=history,
    )

    assert mapping["bucket_schema"] == "agent_composite"
    assert mapping["bucket"] == "强多"
    assert mapping["bucket_range"] == ">=12"
    assert mapping["status"] == "empirical"
    assert mapping["sample_size"] == 20
    assert mapping["predicted_delta"] == 0.0
    assert mapping["directional_fallback"]["applied"] is False


def test_directional_bucket_uses_conservative_same_direction_quantile_when_median_is_neutralized() -> None:
    predictor = object.__new__(ShandongGas92Predictor)
    history = pd.DataFrame(
        {
            "agent_score": [0.15] * 12,
            "target_delta": [-80.0, -60.0, -40.0, -20.0, -10.0, -5.0, -1.0, 20.0, 40.0, 80.0, 100.0, 120.0],
        }
    )

    mapping = predictor._score_delta_mapping(
        frame=pd.DataFrame(),
        as_of_date=date(2026, 6, 11),
        horizon_config=resolve_horizon_config("D3"),
        score_column="agent_score",
        score_value=0.15,
        scored_history=history,
    )

    assert mapping["bucket_schema"] == "agent_composite"
    assert mapping["bucket"] == "强多"
    assert mapping["semantic_constraint_applied"] is True
    assert mapping["directional_fallback"]["applied"] is True
    assert mapping["directional_fallback"]["quantile"] == 0.25
    assert mapping["directional_fallback"]["same_direction_sample_size"] == 5
    assert mapping["raw_p50_delta"] < 0
    assert mapping["predicted_delta"] == 40.0
    assert "同向样本" in mapping["reason"]
