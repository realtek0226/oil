from __future__ import annotations

from app.services.predictors.llm_label_cache import LlmLabelCache


def test_llm_label_cache_persists_by_input_hash(tmp_path) -> None:
    cache_key = "abc123"
    result = {
        "label": "bullish_active",
        "reason": "成交活跃，贸易商接货积极",
        "source": "llm_trade_sentiment",
        "_cache_key": cache_key,
        "_determinism": "input_hash_persistent_cache_temperature_0",
    }

    first_cache = LlmLabelCache(cache_dir=tmp_path)
    first_cache.save(cache_key, result, task="trade_sentiment")

    second_cache = LlmLabelCache(cache_dir=tmp_path)

    assert second_cache.load(cache_key) == result


def test_llm_label_cache_ignores_invalid_json(tmp_path) -> None:
    cache_key = "broken"
    (tmp_path / f"{cache_key}.json").write_text("{bad json", encoding="utf-8")

    cache = LlmLabelCache(cache_dir=tmp_path)

    assert cache.load(cache_key) is None
