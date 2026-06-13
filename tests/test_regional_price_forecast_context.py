from datetime import date

from app.models.common import PredictionResult
from app.services.predictors.shandong_regional_spreads import attach_regional_price_forecasts


def _prediction(**overrides):
    payload = {
        "run_id": "run-1",
        "entity_code": "SD_GAS92",
        "region_code": "SHANDONG",
        "product_code": "GASOLINE_92",
        "horizon": "D1",
        "as_of_date": date(2026, 6, 12),
        "target_date": date(2026, 6, 15),
        "direction_label": "flat",
        "point_value": 8000.0,
        "range_lower": 7970.0,
        "range_upper": 8030.0,
        "confidence_label": "medium",
        "confidence_score": 0.65,
        "score_value": 0.0,
        "explanation": "test",
        "raw_context": {},
    }
    payload.update(overrides)
    return PredictionResult(**payload)


def test_attach_regional_price_forecasts_adds_display_shandong_minus_region_spread():
    shandong = _prediction(
        point_value=8000.0,
        range_lower=7970.0,
        range_upper=8030.0,
        raw_context={
            "business_scorecard_prediction": {
                "point_value": 7992.0,
            }
        },
    )
    regional = _prediction(
        run_id="regional-1",
        entity_code="EAST_CHINA_VS_SD_GAS92_SPREAD",
        region_code="EAST_CHINA_VS_SHANDONG",
        product_code="GASOLINE_92_SPREAD",
        point_value=82.0,
        range_lower=70.0,
        range_upper=94.0,
        raw_context={
            "current_spread": 73.0,
            "current_shandong_price": 7990.0,
            "current_counter_region_price": 8063.0,
            "counter_region_name": "华东",
            "regional_baseline_prediction": {
                "model_name": "区域业务基准预测",
                "prediction_type": "regional_baseline",
                "direction_label": "down",
                "predicted_delta": -6.0,
                "predicted_region_minus_shandong_spread": 76.0,
                "predicted_region_minus_shandong_spread_range_lower": 60.0,
                "predicted_region_minus_shandong_spread_range_upper": 92.0,
            },
        },
    )

    attach_regional_price_forecasts([regional], [shandong])

    assert regional.raw_context["predicted_shandong_price"] == 8000.0
    assert regional.raw_context["predicted_region_minus_shandong_spread"] == 82.0
    assert regional.raw_context["predicted_region_price"] == 8082.0
    assert regional.raw_context["actual_region_minus_shandong_spread"] == 73.0
    assert regional.raw_context["predicted_shandong_minus_region_spread"] == -82.0
    assert regional.raw_context["predicted_shandong_minus_region_spread_range_lower"] == -94.0
    assert regional.raw_context["predicted_shandong_minus_region_spread_range_upper"] == -70.0
    assert regional.raw_context["actual_shandong_minus_region_spread"] == -73.0
    assert regional.raw_context["predicted_spread_formula"] == "预测展示价差=山东92#预测价-预测区域单价"
    assert len(regional.raw_context["regional_prediction_variants"]) == 2
    composite = regional.raw_context["regional_composite_prediction"]
    baseline = regional.raw_context["regional_baseline_prediction"]
    assert composite["model_name"] == "区域智能体综合预测"
    assert composite["predicted_shandong_price"] == 8000.0
    assert composite["predicted_region_price"] == 8082.0
    assert composite["predicted_shandong_minus_region_spread"] == -82.0
    assert baseline["model_name"] == "区域业务基准预测"
    assert baseline["predicted_shandong_price"] == 7992.0
    assert baseline["shandong_prediction_source"] == "山东成品油市场价预测打分模型"
    assert baseline["predicted_region_price"] == 8068.0
    assert baseline["predicted_shandong_minus_region_spread"] == -76.0
