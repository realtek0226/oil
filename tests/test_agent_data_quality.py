import pandas as pd

from app.services.agents.deterministic_agents import BusinessScorecardAgent, CrudeCostAgent


def test_crude_cost_agent_marks_missing_inputs_instead_of_zero_values() -> None:
    claim = CrudeCostAgent().analyze(pd.Series(dtype=float), {"horizon": "D1", "report_payload": {}})

    quality = claim.structured_payload["data_quality"]

    assert claim.numeric_signals["score"] == 0.0
    assert "brent_change_usd" in quality["missing_fields"]
    assert claim.structured_payload["brent_change_usd"] is None
    assert "缺失" in claim.evidence[0]


def test_business_scorecard_agent_exposes_feature_level_status() -> None:
    claim = BusinessScorecardAgent("configs/scorecards/shandong_scorecards_v1.yaml").analyze(
        pd.Series(dtype=float),
        {"horizon": "D1", "report_payload": {}},
    )

    scorecard = claim.structured_payload["scorecard"]
    features = [feature for group in scorecard["groups"] for feature in group["features"]]

    assert features
    assert any(feature["status"] == "missing" for feature in features)
    assert scorecard["data_quality"]["missing_count"] > 0
    assert scorecard["data_quality"]["note"] == "缺失字段不做方向假设，按0分处理。"
