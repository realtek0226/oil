from app.clients.brent_report_client import BrentReportClient
from app.services.scorecard_engine import ScorecardEngine


def test_daily_forecast_keeps_anchor_close_change_when_realtime_price_exists():
    client = BrentReportClient()
    markdown = "| 当日 | 看涨 | $67.00 | $66.00 | $68.00 | high |"

    result = client._extract_daily_forecast(
        markdown,
        {"brent_settlement": 65.0, "realtime_price": 69.88},
    )

    assert result["change_usd"] == 2.0
    assert result["change_source"] == "daily_point_minus_report_settlement"
    assert result["anchor_close"] == 65.0
    assert result["change_vs_realtime_usd"] == -2.88


def test_scorecard_d1_uses_forecast_point_minus_report_settlement_first():
    engine = ScorecardEngine("unused.yaml")

    result = engine._resolve_brent_forecast_change(
        "brent_change_usd_d1",
        extra={
            "report_payload": {
                "signals": {
                    "brent_settlement": 93.09,
                    "brent_settlement_change_usd": -1.23,
                    "daily_forecast": {
                        "point_value": 95.02,
                        "change_usd": 2.0,
                        "change_source": "daily_point_minus_report_settlement",
                    },
                }
            }
        },
    )

    assert result == {
        "value": 1.9299999999999926,
        "source": "brent_daily_report",
        "note": "daily_point_minus_report_settlement",
    }


def test_scorecard_d1_ignores_realtime_daily_change_without_point_and_settlement():
    engine = ScorecardEngine("unused.yaml")

    result = engine._resolve_brent_forecast_change(
        "brent_change_usd_d1",
        extra={
            "report_payload": {
                "signals": {
                    "brent_settlement_change_usd": -1.23,
                    "daily_forecast": {
                        "change_usd": -2.88,
                        "change_source": "daily_point_minus_realtime",
                    },
                }
            }
        },
    )

    assert result == {
        "value": -1.23,
        "source": "brent_daily_report",
        "note": "settlement_change_vs_previous_settlement",
    }


def test_current_brent_report_table_shape_parses_point_and_range():
    client = BrentReportClient()
    markdown = """
| 品种 | 合约 | 收盘价 | 较昨日收盘价 | settlement价格 | 较昨日settlement | 收盘时间(BJT) |
|------|------|--------|------------|------------|----------|---------|
| Brent | BQ26E.IPE (2026-08) | $97.39 | 🔴 $+1.45 (+1.51%) | $97.81 | 🔴 $+1.81 (+1.89%) | 06:00 |

| 预测对象 | 点估计 | 价格预测区间 | 方向 | 交易节奏 | 核心驱动 |
|---------|--------|------------|------|---------|---------|
| 当日 (2026-06-04) | 🟡 $97.53 | $93.96 – $101.3 | neutral | 震荡观察 | brent_now=$97.81 |

> 当日预测锚定 6/3 Brent M1 settle $97.81
"""

    result = client._extract_signals(markdown)

    assert result["brent_settlement"] == 97.81
    assert result["brent_settlement_change_usd"] == 1.81
    assert result["daily_forecast"]["point_value"] == 97.53
    assert result["daily_forecast"]["range_lower"] == 93.96
    assert result["daily_forecast"]["range_upper"] == 101.3
    assert result["daily_forecast"]["change_usd"] == -0.28
    assert result["daily_forecast"]["change_source"] == "daily_point_minus_report_settlement"


def test_brent_m1_table_does_not_parse_remark_date_as_change():
    client = BrentReportClient()
    markdown = """
| 品种 | 合约 | 收盘价 | Settlement | 涨跌(vs前settlement) | 备注 |
|------|------|--------|------------|----------------------|------|
| Brent | M1 (BQ26E.IPE) | $95.25 | $94.98 | $0.00 (0.00%) | 6/2收盘；settlement与6/1持平 |

| 当日 | 看涨 | $95.00 | $92.00 | $98.00 | high |
"""

    result = client._extract_signals(markdown)

    assert result["brent_settlement"] == 94.98
    assert result["brent_settlement_change_usd"] == 0.0
    assert result["realtime_context"]["previous_settlement"] == 94.98
    assert result["daily_forecast"]["change_usd"] == 0.02


def test_brent_m1_table_with_close_change_parses_settlement_columns():
    client = BrentReportClient()
    markdown = """
| 品种 | 合约 | 收盘价 | 较昨日收盘 | settlement | 较昨日settlement | 时间 |
|------|------|--------|------------|------------|------------------|------|
| Brent | M1 BQ26E.IPE(Aug26) | $95.25 | 🔴+4.13(+4.53%) | $94.98 | 🔴+3.86(+4.24%) | 06-01 06:00 |

| 当日 Brent M1 (2026-06-02) | 🟡$95.4 | $91.5 - $99.5 | 震荡 | 震荡观察 | 新增推力净中性 |
"""

    result = client._extract_signals(markdown)

    assert result["brent_settlement"] == 94.98
    assert result["brent_settlement_change_usd"] == 3.86
    assert result["realtime_context"]["previous_settlement"] == 91.12
    assert result["daily_forecast"]["point_value"] == 95.4
    assert result["daily_forecast"]["change_usd"] == 0.42


def test_current_weekly_table_shape_parses_horizon_forecasts():
    client = BrentReportClient()
    markdown = """
| 预测周期 | 点估计 | 价格预测区间 | 方向 | 核心驱动 |
|---------|--------|------------|------|---------|
| 第1周 (2026-06-04 至 2026-06-05) | 🟡 $98.36 | $92.63 – $104.39 | neutral | W1 锚 $97.81 |
| 第4周 (2026-06-22 至 2026-06-26) | 🟢 $93.0 | $87.0 – $97.5 | bearish | backwardation收敛 |

> 当日预测锚定 6/3 Brent M1 settle $97.81
"""

    forecasts = client._extract_horizon_forecasts(markdown)

    assert forecasts["W1"]["point_value"] == 98.36
    assert forecasts["W1"]["range_lower"] == 92.63
    assert forecasts["W1"]["range_upper"] == 104.39
    assert forecasts["W1"]["change_usd"] == 0.55
    assert forecasts["W4"]["point_value"] == 93.0
    assert forecasts["W4"]["change_usd"] == -4.81


def test_scorecard_d3_prefers_d3_and_falls_back_to_w1():
    engine = ScorecardEngine("unused.yaml")

    direct_result = engine._resolve_brent_forecast_change(
        "brent_change_usd_d3",
        extra={"report_payload": {"signals": {"horizon_forecasts": {"D3": {"change_usd": 0.7}}}}},
    )
    fallback_result = engine._resolve_brent_forecast_change(
        "brent_change_usd_d3",
        extra={"report_payload": {"signals": {"horizon_forecasts": {"W1": {"change_usd": 0.55}}}}},
    )

    assert direct_result["value"] == 0.7
    assert fallback_result["value"] == 0.55


def test_brent_report_bullet_shape_parses_daily_and_weekly_changes():
    client = BrentReportClient()
    markdown = """
| 合约 | 收盘价 | 较昨日收盘价 | settlement价格 | 较昨日settlement | 收盘时间 |
|------|--------|----------|---------------|------------|----------|
| Brent C1 (BQ26E.IPE) | $95.36 | $-2.45/-2.50% 🟢 | $95.03 | $-2.78/-2.84% | 2026-06-05 06:00 |

#### 当日预测

- **point_usd**: $95.02
- **range**: $90.5 – $100.0
- **direction**: neutral
- **confidence**: low
- **driver**: brent_now=$95.36(6/4 close)

#### 周度预测

- **W1 (2026-06-05 至 2026-06-11)**: $95.15 [$90.0, $101.0] neutral — W1 锚 $95.36
- **W4 (2026-06-26 至 2026-07-02)**: $93.39 [$87.0, $100.5] bearish — backwardation收敛
"""

    result = client._extract_signals(markdown)

    assert result["brent_settlement"] == 95.03
    assert result["brent_settlement_change_usd"] == -2.78
    assert result["brent_settlement_change_pct"] == -2.84
    assert result["daily_forecast"]["point_value"] == 95.02
    assert result["daily_forecast"]["change_usd"] == -0.01
    assert result["daily_forecast"]["change_source"] == "daily_point_minus_report_settlement"
    assert result["horizon_forecasts"]["W1"]["change_usd"] == 0.12
    assert result["horizon_forecasts"]["W4"]["change_usd"] == -1.64


def test_scorecard_brent_change_does_not_fallback_to_feature_frame_zero():
    engine = ScorecardEngine("unused.yaml")
    row = {"brent_change_1d": 0.0}

    result = engine._resolve_feature(
        "brent_change_usd_d1",
        row=row,
        extra={"report_payload": {"signals": {"daily_forecast": {}}}},
    )

    assert result["value"] is None
    assert result["source"] == "feature_frame"


def test_current_vertical_daily_report_does_not_treat_point_as_settlement_change():
    client = BrentReportClient()
    markdown = """
| 品种 | 合约 | 收盘价 | 较昨日收盘价 | settlement 价格 | 较昨日 settlement | 收盘时间 |
| --- | --- | --- | --- | --- | --- | --- |
| Brent M1 | BQ26E.IPE (8月) | $89.13 | 🟢 -3.97 / -4.26% | $90.38 | -2.72 / -2.92% | — |
| Brent M2 | BU26E.IPE (9月) | $87.93 | 🟢 -3.54 / -3.87% | $89.11 | -2.36 / -2.58% | — |

### 1.3 Brent 预测

**当日预测 (2026-06-12)**

| 项目 | 数值 |
| --- | --- |
| 点估计 | **$88.32/桶** |
| 区间 | $84.5 — $91.5 |
| 方向 | 震荡 |
| 置信度 | low |
"""

    result = client._extract_signals(markdown)

    assert result["brent_settlement"] == 90.38
    assert result["brent_settlement_change_usd"] == -2.72
    assert result["brent_settlement_change_pct"] == -2.92
    assert result["realtime_context"]["previous_settlement"] == 93.1
    assert result["daily_forecast"]["forecast_date"] == "2026-06-12"
    assert result["daily_forecast"]["point_value"] == 88.32
    assert result["daily_forecast"]["range_lower"] == 84.5
    assert result["daily_forecast"]["range_upper"] == 91.5
    assert result["daily_forecast"]["change_usd"] == -2.06
    assert result["daily_forecast"]["change_source"] == "daily_point_minus_report_settlement"
