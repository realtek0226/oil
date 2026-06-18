from datetime import date
from types import SimpleNamespace

from app.api.routes import _build_data_gate, _build_diesel0_monitor, _build_product_scope
from app.services.prediction_accuracy import PredictionAccuracyService


def test_data_gate_includes_optional_diesel0_price_check():
    gate = _build_data_gate(
        target_date=date(2026, 6, 12),
        latest_prices={
            "sd_gas92_market": 8060.0,
            "sd_diesel0_market": 7210.0,
            "brent_active_settlement": 76.5,
        },
        metadata={"market_data_mode": "eta"},
    )

    diesel_check = next(item for item in gate["checks"] if item["code"] == "diesel0_price")
    assert diesel_check["status"] == "pass"
    assert diesel_check["required"] is False
    assert gate["status"] == "ready"


def test_diesel0_monitor_marks_lightweight_prediction_as_not_released():
    prediction = SimpleNamespace(product_code="DIESEL_0", point_value=7240.0, range_lower=7205.0, range_upper=7275.0, raw_context={"predicted_delta": 30.0})

    monitor = _build_diesel0_monitor(
        latest_prices={
            "sd_gas92_market": 8060.0,
            "sd_diesel0_market": 7210.0,
            "sd_diesel_crack": -120.0,
        },
        outright_prediction=prediction,
    )

    assert monitor["label"] == "山东0#柴油"
    assert monitor["point_value"] == 7240.0
    assert monitor["release_gate_status"] == "not_released"
    assert monitor["model_stage"] == "same_bucket_prediction"
    assert "自动放量" in monitor["action_boundary"]


def test_product_scope_uses_chinese_display_labels_for_diesel0():
    scope = _build_product_scope({"label": "山东0#柴油"})

    diesel = next(item for item in scope if item["product_code"] == "DIESEL_0")
    assert diesel["display_code"] == "0#柴油"
    assert "同逻辑预测已接入" in diesel["status"]
    assert "DIESEL_0" not in diesel["detail"]


def test_prediction_accuracy_release_gate_passes_only_after_all_thresholds():
    service = object.__new__(PredictionAccuracyService)

    passed = service._build_release_gate(
        sample_size=24,
        mae=70.0,
        direction_accuracy=0.58,
        range_hit_rate=0.62,
        within_50_rate=0.5,
    )
    blocked = service._build_release_gate(
        sample_size=24,
        mae=95.0,
        direction_accuracy=0.58,
        range_hit_rate=0.62,
        within_50_rate=0.5,
    )

    assert passed["release_gate_passed"] is True
    assert passed["release_gate_label"] == "允许发布"
    assert blocked["release_gate_passed"] is False
    assert blocked["release_gate_label"] == "暂缓发布"
