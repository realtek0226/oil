from datetime import date

import pandas as pd

from app.services.agents.deterministic_agents import RefinedOilNewsAgent


def test_refined_oil_news_agent_uses_as_of_date_for_recency() -> None:
    agent = RefinedOilNewsAgent()
    row = pd.Series(dtype=float)
    common_item = {
        "headline": "山东地炼汽柴油价格快报 上调",
        "title": "山东地炼汽柴油价格快报 上调",
        "content": "山东地炼汽柴油价格快报 上调",
        "direction_hint": "bullish_refined",
        "major_score": 3.0,
    }

    recent_claim = agent.analyze(
        row,
        {
            "as_of_date": date(2026, 5, 29),
            "enable_refined_news": True,
            "refined_news_items": [{**common_item, "publish_time": "2026-05-28 09:00"}],
        },
    )
    older_claim = agent.analyze(
        row,
        {
            "as_of_date": date(2026, 5, 29),
            "enable_refined_news": True,
            "refined_news_items": [{**common_item, "publish_time": "2026-05-10 09:00"}],
        },
    )

    assert recent_claim.numeric_signals["score"] > older_claim.numeric_signals["score"]


def test_refined_oil_news_agent_can_be_disabled() -> None:
    agent = RefinedOilNewsAgent()
    claim = agent.analyze(
        pd.Series(dtype=float),
        {
            "as_of_date": date(2026, 5, 29),
            "enable_refined_news": False,
            "refined_news_items": [{"headline": "山东地炼汽柴油价格快报 上调"}],
        },
    )

    assert claim.direction == "flat"
    assert claim.numeric_signals["score"] == 0.0
