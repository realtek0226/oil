from app.models.common import AgentClaim
from app.services.predictors.agent_judgement import build_agent_judgement_review


def _claim(agent_name: str, direction: str, weighted_score: float) -> AgentClaim:
    return AgentClaim(
        agent_name=agent_name,
        direction=direction,
        confidence_label="medium",
        confidence_score=0.7,
        summary=agent_name,
        evidence=[],
        numeric_signals={
            "weighted_score": weighted_score,
        },
        structured_payload={
            "data_quality": {
                "available_count": 1,
                "missing_count": 0,
            }
        },
    )


def test_pressure_review_does_not_change_flat_point_forecast() -> None:
    review = build_agent_judgement_review(
        claims=[
            _claim("crude_cost_agent", "up", 0.35),
            _claim("demand_seasonality_agent", "up", 0.24),
            _claim("supply_inventory_agent", "down", -0.02),
        ],
        predicted_delta=0.0,
        direction_label="flat",
        direction_threshold=12.0,
    )

    assert review["verdict"] == "hard_pressure_attention"
    assert review["adjustment_delta"] == 0.0
    assert "不直接改预测点位" in "；".join(review["reasons"])
