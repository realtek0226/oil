from app.models.common import AgentClaim
from app.services.predictors.confidence_engine import build_reliability_score


def _claim(name: str, score: float, available: int, missing: int) -> AgentClaim:
    return AgentClaim(
        agent_name=name,
        direction="up" if score > 0 else "down" if score < 0 else "flat",
        confidence_label="medium",
        confidence_score=0.6,
        summary=name,
        numeric_signals={"weighted_score": score, "score": score},
        structured_payload={
            "data_quality": {
                "available_count": available,
                "missing_count": missing,
                "missing_fields": ["x"] * missing,
                "coverage_ratio": available / (available + missing) if available + missing else 1.0,
            }
        },
    )


def test_reliability_uses_agent_input_quality() -> None:
    _, _, components = build_reliability_score(
        claims=[
            _claim("crude_cost_agent", 0.2, 1, 1),
            _claim("market_structure_agent", 0.1, 1, 1),
            _claim("business_scorecard_agent", -80.0, 0, 10),
        ],
        predicted_delta=30.0,
        direction_label="up",
        range_half_width=50.0,
        direction_threshold=3.0,
        calibration_rmse=50.0,
        sample_size=0,
        context_metadata={"market_data_mode": "eta"},
    )

    assert components["source_data_quality"] == 1.0
    assert components["agent_input_quality"] == 0.5
    assert components["data_quality"] == 0.5
