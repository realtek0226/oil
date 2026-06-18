from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse

from app.core.container import (
    get_agent_control_service,
    get_auth_service,
    get_backtest_service,
    get_dataset_service,
    get_predictor,
    get_regional_spread_predictor,
    get_repository,
    get_scheduler_service,
    get_snapshot_repository,
    get_workbench_service,
)
from app.models.api import (
    AgentGraphResponse,
    AgentOptimizationProposalResponse,
    AgentOptimizationStateResponse,
    AgentOutputHistoryResponse,
    AgentOverviewResponse,
    AgentRunDetailResponse,
    AgentRunListResponse,
    AlertCaseUpdateRequest,
    AlertCaseUpdateResponse,
    BacktestRequest,
    BacktestResponse,
    BrentLiveResponse,
    ChatPredictRequest,
    ChatPredictResponse,
    CreateUserRequest,
    ConfirmOptimizationProposalRequest,
    DashboardNarrativeResponse,
    DashboardResponse,
    FreightComponentUpdateRequest,
    FreightSettingUpdateRequest,
    FreightSettingsResponse,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    MarketSnapshotResponse,
    MorningBriefingRequest,
    MorningBriefingResponse,
    MultiPredictResponse,
    PermissionCatalogResponse,
    PolicyEventFeedResponse,
    PredictionAccuracyResponse,
    PriceHistoryResponse,
    PredictRequest,
    PredictResponse,
    RegionalSpreadPredictRequest,
    RoleCatalogResponse,
    SchedulerStatusResponse,
    UpdateProfileRequest,
    UpdateUserRequest,
    UsageLogListResponse,
    UserListResponse,
    UserProfileResponse,
)
from app.models.common import PredictionResult
from app.services.predictors.horizons import ACTIVE_HORIZONS, DEFAULT_HORIZONS
from app.services.predictors.shandong_regional_spreads import attach_regional_price_forecasts, build_freight_settings_from_components
from app.services.prediction_accuracy import PredictionAccuracyService
from app.core.settings import get_settings


router = APIRouter()
STATIC_INDEX_PATH = Path("app/static/index.html")
LOGIN_PAGE_PATH = Path("app/static/login.html")




def _active_horizon(horizon: str | None = None) -> str:
    normalized = str(horizon or "D1").strip().upper()
    return normalized if normalized in ACTIVE_HORIZONS else DEFAULT_HORIZONS[0]

def _active_horizons(horizons: list[str] | None = None) -> list[str]:
    requested = list(horizons or DEFAULT_HORIZONS)
    selected = [horizon for horizon in requested if horizon in ACTIVE_HORIZONS]
    return selected or list(DEFAULT_HORIZONS)



CACHE_FINGERPRINT_FEATURES = {
    "brent_active_settlement",
    "cny_mid_rate",
    "sd_gas92_market",
    "sd_diesel0_market",
    "shandong_cdu_utilization_weekly",
    "shandong_cdu_utilization_percentile_weekly",
    "sd_refining_profit",
    "sd_gas_crack",
    "sd_diesel_crack",
    "gasoline_crack_percentile",
    "diesel_crack_percentile",
    "sales_production_ratio_d1",
    "sales_production_ratio_d3_avg",
    "sales_production_ratio_w1_avg",
    "shandong_independent_refinery_inventory",
    "shandong_main_company_inventory",
    "shandong_diesel_inventory",
    "price_adjustment_expected_yuan",
    "refined_oil_adjustment_expected_yuan",
}
CACHE_FINGERPRINT_TOLERANCE = 0.01
MARKET_SNAPSHOT_CACHE_SECONDS = 60
_MARKET_SNAPSHOT_CACHE: dict[date, tuple[datetime, dict[str, Any]]] = {}


def _safe_float_for_cache(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _prediction_scorecard_features(prediction: Any) -> list[dict[str, Any]]:
    raw_context = getattr(prediction, "raw_context", None) or {}
    scorecard = (raw_context.get("business_scorecard") or {}) if isinstance(raw_context, dict) else {}
    groups = scorecard.get("groups") or scorecard.get("group_scores") or []
    return [
        feature
        for group in groups
        if isinstance(group, dict)
        for feature in (group.get("features") or [])
        if isinstance(feature, dict)
    ]


def _feature_cache_value(feature: dict[str, Any]) -> float | None:
    for key in ("value", "score_value"):
        parsed = _safe_float_for_cache(feature.get(key))
        if parsed is not None:
            return parsed
    return None


def _current_feature_value(row: Any, feature_name: str) -> float | None:
    aliases = {
        "brent_settlement": "brent_active_settlement",
        "gasoline_crack_percentile_monthly": "gasoline_crack_percentile",
        "diesel_crack_percentile_monthly": "diesel_crack_percentile",
    }
    candidates = [feature_name]
    if feature_name in aliases:
        candidates.append(aliases[feature_name])
    if feature_name == "shandong_cdu_utilization_weekly":
        candidates.append("sd_crude_run_weekly")
    for key in candidates:
        try:
            parsed = _safe_float_for_cache(row.get(key))
        except Exception:
            parsed = None
        if parsed is not None:
            return parsed
    return None


def _prediction_data_fingerprint_is_current(prediction: Any, flat_features: list[dict[str, Any]]) -> bool:
    comparable = [
        feature
        for feature in flat_features
        if str(feature.get("feature_name") or "") in CACHE_FINGERPRINT_FEATURES
        and feature.get("matched_label") != "missing"
        and _feature_cache_value(feature) is not None
    ]
    if not comparable:
        return True
    try:
        dataset_service = get_dataset_service()
        frame = dataset_service.build_feature_frame(
            start_date=prediction.as_of_date - timedelta(days=35),
            end_date=prediction.as_of_date,
        )
    except Exception:
        return True
    if frame.empty:
        return True
    row = frame.iloc[-1]
    stale_items: list[dict[str, Any]] = []
    for feature in comparable:
        feature_name = str(feature.get("feature_name") or "")
        cached_value = _feature_cache_value(feature)
        current_value = _current_feature_value(row, feature_name)
        if cached_value is None or current_value is None:
            continue
        if abs(current_value - cached_value) >= CACHE_FINGERPRINT_TOLERANCE:
            stale_items.append(
                {
                    "feature_name": feature_name,
                    "cached_value": round(cached_value, 6),
                    "current_value": round(current_value, 6),
                }
            )
    if stale_items:
        raw_context = getattr(prediction, "raw_context", None)
        if isinstance(raw_context, dict):
            raw_context["cache_stale_reason"] = "\u7f13\u5b58\u6253\u5206\u4e0e\u5f53\u524d\u89c4\u5219\u4e0d\u4e00\u81f4"
            raw_context["cache_stale_items"] = stale_items[:20]
        return False
    return True

def _round_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 2)
    except Exception:
        return None


def _direction_from_delta(value: float | None, threshold: float = 3.0) -> str:
    if value is None:
        return "flat"
    if value > threshold:
        return "up"
    if value < -threshold:
        return "down"
    return "flat"


def _safe_delta(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _build_diesel0_monitor(
    *,
    current_row: Any | None = None,
    latest_prices: dict[str, Any] | None = None,
    outright_prediction: Any | None = None,
    data_quality: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    latest_prices = latest_prices or {}

    def pick(key: str) -> float | None:
        row_value = current_row.get(key) if current_row is not None and hasattr(current_row, "get") else None
        return _round_or_none(row_value if row_value is not None else latest_prices.get(key))

    current_price = pick("sd_diesel0_market")
    if current_price is None:
        return None
    raw_context = getattr(outright_prediction, "raw_context", None) or {}
    prediction_quality = raw_context.get("product_data_quality") if isinstance(raw_context, dict) else None
    is_diesel_prediction = getattr(outright_prediction, "product_code", None) == "DIESEL_0"
    if is_diesel_prediction:
        projected_delta = round(float(raw_context.get("predicted_delta") or 0.0), 2)
        point_value = _round_or_none(getattr(outright_prediction, "point_value", None)) or round(current_price + projected_delta, 2)
        range_lower = _round_or_none(getattr(outright_prediction, "range_lower", None))
        range_upper = _round_or_none(getattr(outright_prediction, "range_upper", None))
    else:
        gasoline_delta = _safe_delta(raw_context.get("predicted_delta"))
        if gasoline_delta is None and outright_prediction is not None:
            gasoline_current = _safe_delta(raw_context.get("current_price"))
            gasoline_point = _safe_delta(getattr(outright_prediction, "point_value", None))
            if gasoline_current is not None and gasoline_point is not None:
                gasoline_delta = gasoline_point - gasoline_current
        projected_delta = round(float(gasoline_delta or 0.0) * 0.75, 2)
        point_value = round(current_price + projected_delta, 2)
        range_half_width = max(35.0, abs(projected_delta) * 1.6)
        range_lower = round(point_value - range_half_width, 2)
        range_upper = round(point_value + range_half_width, 2)
    diesel_crack = pick("sd_diesel_crack")
    gas_price = pick("sd_gas92_market")
    gas_spread = round(current_price - gas_price, 2) if gas_price is not None else None
    direction = _direction_from_delta(projected_delta)
    direction_label = {"up": "跟随偏强", "down": "跟随偏弱", "flat": "震荡观望"}[direction]
    return {
        "product_code": "DIESEL_0",
        "label": "山东0#柴油",
        "status": "同逻辑预测已接入，待复盘校准" if is_diesel_prediction else "监测已接入，轻量预测待校准",
        "model_stage": "same_bucket_prediction" if is_diesel_prediction else "lightweight_transmission",
        "release_gate_status": "not_released",
        "release_gate_label": "待回测校准",
        "current_price": current_price,
        "projected_delta": projected_delta,
        "point_value": point_value,
        "range_lower": range_lower,
        "range_upper": range_upper,
        "direction_label": direction_label,
        "diesel_crack_spread": diesel_crack,
        "diesel_minus_gas92_spread": gas_spread,
        "basis": "柴油已使用与92#相同的智能体综合预测和业务打分模型映射逻辑，目标涨跌改为山东0#柴油自身历史价格。",
        "action_boundary": "发布闸门通过前用于经营参考和人工复核，不进入自动放量或自动锁价。",
        "data_quality": {
            **(data_quality or {}),
            "prediction_view": prediction_quality or {},
        },
    }


def _build_product_scope(diesel0_monitor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    diesel_status = "同逻辑预测已接入，待复盘校准" if diesel0_monitor else "数据展示支持，预测模型待接入"
    return [
        {
            "product_code": "GASOLINE_92",
            "label": "山东92#汽油",
            "status": "正式支持",
            "display_code": "92#汽油",
            "detail": "价格预测、区域价差、动作卡、复盘闸门已接入。",
        },
        {
            "product_code": "DIESEL_0",
            "label": "山东0#柴油",
            "status": diesel_status,
            "display_code": "0#柴油",
            "detail": "现货、历史曲线、裂解价差和轻量传导参考已接入；正式发布前需柴油独立回测。",
        },
    ]


def _build_diesel0_data_quality(current_row: Any, feature_frame: Any | None = None) -> dict[str, Any]:
    required = [
        ("sd_diesel0_market", "山东0#柴油现货"),
        ("brent_active_settlement", "Brent价格"),
        ("sd_diesel_crack", "山东柴油裂解价差"),
    ]
    supporting = [
        ("diesel_price_change_1d", "柴油日涨跌"),
        ("diesel_price_change_3d", "柴油三日涨跌"),
        ("diesel_crack_percentile", "柴油裂解分位"),
        ("diesel_sales_production_ratio_d1", "柴油产销率"),
        ("diesel_sales_production_ratio_d3_avg", "柴油三日产销均值"),
        ("diesel_sales_production_ratio_w1_avg", "柴油周度产销均值"),
        ("diesel_sales_production_ratio_monthly_avg", "柴油月度产销均值"),
        ("diesel_sales_production_ratio_monthly_change", "柴油月度产销变化"),
        ("shandong_diesel_inventory", "山东柴油库存"),
        ("shandong_diesel_inventory_change_mom", "山东柴油库存环比"),
        ("shandong_diesel_inventory_capacity_rate", "山东柴油库容率"),
        ("shandong_diesel_inventory_percentile_monthly", "山东柴油库存分位"),
    ]
    all_items = [*required, *supporting]
    missing = [
        {"key": key, "label": label}
        for key, label in all_items
        if _round_or_none(current_row.get(key) if hasattr(current_row, "get") else None) is None
    ]
    missing_required = [item for item in missing if item["key"] in {key for key, _label in required}]
    coverage: dict[str, Any] = {}
    if feature_frame is not None and not getattr(feature_frame, "empty", True):
        total = int(len(feature_frame.tail(180)))
        if total:
            for key, label in all_items:
                if key in feature_frame.columns:
                    available = int(feature_frame.tail(180)[key].notna().sum())
                    coverage[key] = {
                        "label": label,
                        "available": available,
                        "total": total,
                        "rate": round(available / total, 4),
                    }
    freshness: dict[str, Any] = {}
    diesel_ratio_stale_days = _round_or_none(
        current_row.get("diesel_sales_production_ratio_stale_days") if hasattr(current_row, "get") else None
    )
    if diesel_ratio_stale_days is not None:
        diesel_ratio_value = _round_or_none(
            current_row.get("diesel_sales_production_ratio_d1") if hasattr(current_row, "get") else None
        )
        observation_value = (
            current_row.get("diesel_sales_production_ratio_observation_date") if hasattr(current_row, "get") else None
        )
        observation_date = None
        if observation_value is not None:
            if hasattr(observation_value, "date"):
                observation_date = observation_value.date().isoformat()
            else:
                try:
                    numeric_value = float(observation_value)
                    if numeric_value == numeric_value:
                        if abs(numeric_value) > 10_000_000_000:
                            numeric_value = numeric_value / 1_000_000_000
                        observation_date = datetime.fromtimestamp(numeric_value).date().isoformat()
                except Exception:
                    text_value = str(observation_value or "")
                    observation_date = text_value[:10] if text_value and text_value.lower() != "nan" else None
        source_value = current_row.get("diesel_sales_production_ratio_source") if hasattr(current_row, "get") else None
        try:
            if source_value is not None and source_value != source_value:
                source_value = None
        except Exception:
            pass
        freshness["diesel_sales_production_ratio"] = {
            "label": "柴油产销率",
            "value": diesel_ratio_value,
            "stale_days": diesel_ratio_stale_days,
            "status": "fresh" if diesel_ratio_stale_days <= 7 else "stale",
            "source": source_value,
            "observation_date": observation_date,
        }
    return {
        "status": "ready" if not missing_required else "partial",
        "missing": missing,
        "missing_required": missing_required,
        "coverage": coverage,
        "freshness": freshness,
        "message": (
            "柴油预测核心数据齐备；部分辅助因子如产销率或库容率缺失时按0分降级。"
            if not missing_required
            else "柴油预测核心数据存在缺失项，需人工复核。"
        ),
    }


def _build_cached_diesel0_data_quality(prediction: Any | None) -> dict[str, Any] | None:
    if prediction is None:
        return None
    raw_context = getattr(prediction, "raw_context", None) or {}
    prediction_quality = raw_context.get("product_data_quality") if isinstance(raw_context, dict) else None
    scorecard = raw_context.get("business_scorecard") if isinstance(raw_context, dict) else None
    ratio_value = None
    if isinstance(scorecard, dict):
        for group in scorecard.get("group_scores") or scorecard.get("groups") or []:
            for feature in group.get("features") or []:
                if feature.get("feature_name") == "sales_production_ratio_d1":
                    ratio_value = _round_or_none(feature.get("value"))
                    break
            if ratio_value is not None:
                break
    freshness = {}
    if ratio_value is not None:
        freshness["diesel_sales_production_ratio"] = {
            "label": "柴油产销率",
            "value": ratio_value,
            "stale_days": None,
            "status": "cached",
            "source": "cached_prediction_scorecard",
            "observation_date": None,
        }
    return {
        "status": (prediction_quality or {}).get("status") or "ready",
        "missing": [],
        "missing_required": [],
        "coverage": {},
        "freshness": freshness,
        "message": (prediction_quality or {}).get("note") or "柴油预测使用缓存结果；点击刷新可重新计算数据新鲜度。",
    }


def _build_data_gate(
    *,
    target_date: date,
    latest_prices: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    prediction: Any | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    raw_context = getattr(prediction, "raw_context", None) or {}
    checks: list[dict[str, Any]] = []

    def add_check(code: str, label: str, status: str, detail: str, required: bool = True) -> None:
        checks.append(
            {
                "code": code,
                "label": label,
                "status": status,
                "required": required,
                "detail": detail,
            }
        )

    market_mode = str(metadata.get("market_data_mode") or raw_context.get("market_data_mode") or "")
    market_reason = str(metadata.get("market_data_reason") or raw_context.get("market_data_reason") or "")
    fallback_used = "fallback" in market_mode or "fallback" in market_reason
    add_check(
        "market_price",
        "山东92#现货价格",
        "pass" if latest_prices.get("sd_gas92_market") is not None and not fallback_used else "warn",
        "已取得山东92#现货价格。" if latest_prices.get("sd_gas92_market") is not None and not fallback_used else "现货价格缺失或使用本地降级快照，经营动作需人工复核。",
    )
    add_check(
        "diesel0_price",
        "山东0#柴油现货",
        "pass" if latest_prices.get("sd_diesel0_market") is not None and not fallback_used else "warn",
        "已取得山东0#柴油现货价格。" if latest_prices.get("sd_diesel0_market") is not None and not fallback_used else "0#柴油价格缺失或使用降级快照，柴油动作只允许人工观察。",
        required=False,
    )
    add_check(
        "brent",
        "Brent价格/日报",
        "pass" if latest_prices.get("brent_active_settlement") is not None and "brent_daily_report_missing" not in market_reason else "warn",
        "已取得Brent价格或日报锚点。" if latest_prices.get("brent_active_settlement") is not None else "Brent价格缺失，成本端判断需降级。",
    )
    add_check(
        "regional_prices",
        "区域92#价格",
        "pass" if any(key.endswith("_gas92_market") and key != "sd_gas92_market" and value is not None for key, value in latest_prices.items()) else "warn",
        "已取得至少一个区域92#价格。" if any(key.endswith("_gas92_market") and key != "sd_gas92_market" and value is not None for key, value in latest_prices.items()) else "区域价格不足，区域价差和外发建议需人工复核。",
        required=False,
    )
    add_check(
        "news_policy",
        "资讯/政策事件",
        "pass" if (raw_context.get("refined_news_count") or metadata.get("refined_news_items") or metadata.get("policy_items")) else "warn",
        "已纳入资讯或政策事件。" if (raw_context.get("refined_news_count") or metadata.get("refined_news_items") or metadata.get("policy_items")) else "资讯/政策样本不足，预警和事件解释可能降级。",
        required=False,
    )
    failed_required = [item for item in checks if item["required"] and item["status"] == "fail"]
    warned_required = [item for item in checks if item["required"] and item["status"] == "warn"]
    if failed_required:
        status, label = "blocked", "禁止自动经营使用"
        reason = "、".join(item["label"] for item in failed_required) + "未通过。"
    elif warned_required:
        status, label = "degraded", "降级可参考"
        reason = "、".join(item["label"] for item in warned_required) + "需要人工复核。"
    else:
        status, label = "ready", "可用于经营参考"
        reason = "核心价格数据通过检查。"
    return {
        "status": status,
        "label": label,
        "reason": reason,
        "as_of_date": target_date.isoformat(),
        "checks": checks,
    }


def _session_token_from_request(request: Request) -> str:
    cookie_name = get_settings().auth.cookie_name
    token = request.cookies.get(cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    return token


def _session_hash_from_request(request: Request) -> str | None:
    token = request.cookies.get(get_settings().auth.cookie_name)
    if not token:
        return None
    return sha256(token.encode("utf-8")).hexdigest()[:16]


def _require_user(request: Request) -> dict[str, Any]:
    try:
        return get_auth_service().get_current_user(_session_token_from_request(request))
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _require_permission(request: Request, permission_code: str) -> dict[str, Any]:
    user = _require_user(request)
    if not get_auth_service().user_has_permission(user, permission_code):
        raise HTTPException(status_code=403, detail="无权限访问该模块")
    return user


def _persist_prediction_audit(prediction: Any) -> None:
    snapshot_repository = get_snapshot_repository()
    if not snapshot_repository or not snapshot_repository.enabled:
        return
    try:
        snapshot_repository.save_prediction_run(prediction)
    except Exception:
        return


@router.get("/", include_in_schema=False, response_model=None)
def root_page(request: Request) -> Response:
    try:
        _require_user(request)
        return RedirectResponse(url="/workbench", status_code=302)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=302)


@router.get("/login", include_in_schema=False, response_model=None)
def login_page(request: Request) -> Response:
    try:
        _require_user(request)
        return RedirectResponse(url="/workbench", status_code=302)
    except HTTPException:
        return FileResponse(LOGIN_PAGE_PATH)


@router.get("/workbench", include_in_schema=False, response_model=None)
def workbench_page(request: Request) -> Response:
    try:
        _require_user(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(STATIC_INDEX_PATH)


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", app="shandong-oil-agent-lab")


@router.post("/api/v1/auth/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response, http_request: Request) -> LoginResponse:
    try:
        payload = get_auth_service().login(
            username=request.username,
            password=request.password,
            remember_me=request.remember_me,
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
        )
    except ValueError as exc:
        snapshot_repository = get_snapshot_repository()
        if snapshot_repository and snapshot_repository.enabled:
            try:
                snapshot_repository.save_usage_log(
                    user_id=None,
                    username=request.username,
                    action="login_failed",
                    method=http_request.method,
                    path=str(http_request.url.path),
                    status_code=401,
                    ip_address=http_request.client.host if http_request.client else None,
                    user_agent=http_request.headers.get("user-agent"),
                    duration_ms=None,
                    detail={},
                )
            except Exception:
                pass
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    settings = get_settings().auth
    max_age = settings.remember_me_ttl_hours * 3600 if request.remember_me else settings.session_ttl_hours * 3600
    response.set_cookie(
        key=settings.cookie_name,
        value=payload["token"],
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    snapshot_repository = get_snapshot_repository()
    if snapshot_repository and snapshot_repository.enabled:
        try:
            user = payload["user"]
            snapshot_repository.save_usage_log(
                user_id=int(user["user_id"]),
                username=str(user.get("username") or request.username),
                action="login",
                method=http_request.method,
                path=str(http_request.url.path),
                status_code=200,
                ip_address=http_request.client.host if http_request.client else None,
                user_agent=http_request.headers.get("user-agent"),
                duration_ms=None,
                detail={"remember_me": request.remember_me},
            )
        except Exception:
            pass
    return LoginResponse(user=UserProfileResponse.model_validate(payload["user"]), expires_at=payload["expires_at"])


@router.post("/api/v1/auth/logout")
def logout(response: Response, http_request: Request) -> dict[str, str]:
    token = http_request.cookies.get(get_settings().auth.cookie_name)
    if token:
        get_auth_service().logout(token)
    response.delete_cookie(get_settings().auth.cookie_name, path="/")
    return {"status": "ok"}


@router.get("/api/v1/auth/me", response_model=UserProfileResponse)
def auth_me(http_request: Request) -> UserProfileResponse:
    return UserProfileResponse.model_validate(_require_user(http_request))


@router.patch("/api/v1/auth/me", response_model=UserProfileResponse)
def update_profile(request: UpdateProfileRequest, http_request: Request) -> UserProfileResponse:
    user = _require_permission(http_request, "profile.view")
    payload = get_auth_service().update_personal_profile(
        user_id=int(user["user_id"]),
        display_name=request.display_name,
        title=request.title,
        password=request.password,
    )
    return UserProfileResponse.model_validate(payload)


@router.get("/api/v1/permissions/catalog", response_model=PermissionCatalogResponse)
def permission_catalog(http_request: Request) -> PermissionCatalogResponse:
    _require_permission(http_request, "permissions.manage")
    return PermissionCatalogResponse(items=[item for item in get_auth_service().list_permissions()])


@router.get("/api/v1/roles/catalog", response_model=RoleCatalogResponse)
def role_catalog(http_request: Request) -> RoleCatalogResponse:
    _require_permission(http_request, "permissions.manage")
    return RoleCatalogResponse(items=[item for item in get_auth_service().list_roles()])


@router.get("/api/v1/users", response_model=UserListResponse)
def list_users(http_request: Request) -> UserListResponse:
    _require_permission(http_request, "permissions.manage")
    return UserListResponse(items=[UserProfileResponse.model_validate(item) for item in get_auth_service().list_users()])


@router.post("/api/v1/users", response_model=UserProfileResponse)
def create_user(request: CreateUserRequest, http_request: Request) -> UserProfileResponse:
    actor = _require_permission(http_request, "permissions.manage")
    try:
        payload = get_auth_service().create_user(
            actor_user_id=int(actor["user_id"]),
            username=request.username,
            display_name=request.display_name,
            title=request.title,
            password=request.password,
            is_active=request.is_active,
            permission_codes=request.permission_codes,
            role_codes=request.role_codes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UserProfileResponse.model_validate(payload)


@router.patch("/api/v1/users/{user_id}", response_model=UserProfileResponse)
def update_user(user_id: int, request: UpdateUserRequest, http_request: Request) -> UserProfileResponse:
    actor = _require_permission(http_request, "permissions.manage")
    payload = get_auth_service().update_user_permissions(
        actor_user_id=int(actor["user_id"]),
        target_user_id=user_id,
        permission_codes=request.permission_codes,
        role_codes=request.role_codes,
        is_active=request.is_active,
        display_name=request.display_name,
        title=request.title,
    )
    return UserProfileResponse.model_validate(payload)


@router.get("/api/v1/system/usage-logs", response_model=UsageLogListResponse)
def system_usage_logs(
    limit: int = Query(default=100, ge=10, le=500),
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    http_request: Request = None,
) -> UsageLogListResponse:
    _require_permission(http_request, "permissions.manage")
    items = get_snapshot_repository().list_usage_logs(limit=limit, user_id=user_id, action=action)
    return UsageLogListResponse.model_validate({"items": items})


@router.get("/api/v1/market/snapshot", response_model=MarketSnapshotResponse)
def market_snapshot(
    as_of_date: date | None = Query(default=None),
    http_request: Request = None,
) -> MarketSnapshotResponse:
    _require_permission(http_request, "workbench.view")
    target_date = as_of_date or date.today()
    now = datetime.now()
    cached = _MARKET_SNAPSHOT_CACHE.get(target_date)
    if cached and (now - cached[0]).total_seconds() <= MARKET_SNAPSHOT_CACHE_SECONDS:
        return MarketSnapshotResponse.model_validate(cached[1])
    try:
        payload = get_dataset_service().get_market_snapshot(as_of_date=target_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload.setdefault("metadata", {})
    payload["metadata"]["data_gate"] = _build_data_gate(
        target_date=payload.get("as_of_date") or target_date,
        latest_prices=payload.get("latest_prices") or {},
        metadata=payload.get("metadata") or {},
    )
    _MARKET_SNAPSHOT_CACHE[target_date] = (now, payload)
    if len(_MARKET_SNAPSHOT_CACHE) > 4:
        oldest_key = min(_MARKET_SNAPSHOT_CACHE, key=lambda key: _MARKET_SNAPSHOT_CACHE[key][0])
        _MARKET_SNAPSHOT_CACHE.pop(oldest_key, None)
    return MarketSnapshotResponse.model_validate(payload)


@router.get("/api/v1/market/brent-live", response_model=BrentLiveResponse)
def brent_live_snapshot(
    as_of_date: date | None = Query(default=None),
    http_request: Request = None,
) -> BrentLiveResponse:
    _require_permission(http_request, "workbench.view")
    try:
        payload = get_dataset_service().get_brent_realtime_snapshot(as_of_date=as_of_date or date.today())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BrentLiveResponse.model_validate(payload)


@router.get("/api/v1/market/price-history", response_model=PriceHistoryResponse)
def market_price_history(
    days: int = Query(default=30, ge=7, le=365),
    end_date: date | None = Query(default=None),
    series: list[str] = Query(default_factory=list),
    product: str | None = Query(default=None),
    http_request: Request = None,
) -> PriceHistoryResponse:
    _require_permission(http_request, "workbench.view")
    target_end = end_date or date.today()
    start_date = target_end - timedelta(days=days - 1)
    try:
        payload = get_dataset_service().get_price_history(
            start_date=start_date,
            end_date=target_end,
            series_keys=series,
            product_code=product,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PriceHistoryResponse.model_validate(payload)


def _inventory_date_range(
    *,
    start_date: date | None,
    end_date: date | None,
    days: int,
) -> tuple[date, date]:
    target_end = end_date or date.today()
    target_start = start_date or (target_end - timedelta(days=days - 1))
    if target_start > target_end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    return target_start, target_end


@router.get("/api/v1/oilchem-openapi/inventory")
def oilchem_openapi_inventory(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    days: int = Query(default=180, ge=7, le=1095),
    http_request: Request = None,
) -> dict[str, Any]:
    _require_permission(http_request, "workbench.view")
    target_start, target_end = _inventory_date_range(start_date=start_date, end_date=end_date, days=days)
    try:
        return get_dataset_service().get_oilchem_openapi_inventory(
            start_date=target_start,
            end_date=target_end,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/oilchem-openapi/inventory/refresh")
def refresh_oilchem_openapi_inventory(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    days: int = Query(default=180, ge=7, le=1095),
    http_request: Request = None,
) -> dict[str, Any]:
    _require_permission(http_request, "agents.view")
    target_start, target_end = _inventory_date_range(start_date=start_date, end_date=end_date, days=days)
    try:
        return get_dataset_service().refresh_oilchem_openapi_inventory_archive(
            as_of_date=target_end,
            start_date=target_start,
            end_date=target_end,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/oilchem-openapi/inventory/export")
def export_oilchem_openapi_inventory(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    days: int = Query(default=180, ge=7, le=1095),
    http_request: Request = None,
) -> Response:
    _require_permission(http_request, "workbench.view")
    target_start, target_end = _inventory_date_range(start_date=start_date, end_date=end_date, days=days)
    try:
        payload = get_dataset_service().get_oilchem_openapi_inventory(
            start_date=target_start,
            end_date=target_end,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "date",
            "project_label",
            "product",
            "owner",
            "region",
            "value",
            "unit",
            "freq",
            "publish_time",
            "project_quota_id",
            "entity_code",
        ],
    )
    writer.writeheader()
    for row in payload.get("items", []):
        writer.writerow({key: row.get(key) for key in writer.fieldnames})
    content = "\ufeff" + buffer.getvalue()
    filename = f"oilchem_inventory_{target_start.isoformat()}_{target_end.isoformat()}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/v1/prediction-accuracy", response_model=PredictionAccuracyResponse)
def prediction_accuracy_dashboard(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=120, ge=10, le=500),
    http_request: Request = None,
) -> PredictionAccuracyResponse:
    _require_permission(http_request, "workbench.view")
    try:
        payload = PredictionAccuracyService(
            repository=get_repository(),
            dataset_service=get_dataset_service(),
        ).build_dashboard(days=days, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PredictionAccuracyResponse.model_validate(payload)


@router.get("/api/v1/regional-freight-settings", response_model=FreightSettingsResponse)
def regional_freight_settings(http_request: Request) -> FreightSettingsResponse:
    _require_permission(http_request, "workbench.view")
    items = build_freight_settings_from_components(get_snapshot_repository())
    for item in items:
        item["source_type"] = "database_components_route"
    return FreightSettingsResponse.model_validate({"items": items})


@router.patch("/api/v1/regional-freight-settings/{region_code}", response_model=FreightSettingsResponse)
def update_regional_freight_setting(
    region_code: str,
    request: FreightSettingUpdateRequest,
    http_request: Request,
) -> FreightSettingsResponse:
    actor = _require_permission(http_request, "workbench.view")
    try:
        get_regional_spread_predictor().update_freight_setting(
            region_code=region_code,
            freight_value=request.freight_value,
            updated_by=str(actor.get("username") or actor.get("display_name") or ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = {"items": get_regional_spread_predictor().list_freight_settings()}
    return FreightSettingsResponse.model_validate(payload)


@router.get("/api/v1/regional-freight-components/settings", response_model=FreightSettingsResponse)
def regional_freight_component_settings(http_request: Request) -> FreightSettingsResponse:
    _require_permission(http_request, "workbench.view")
    items = build_freight_settings_from_components(get_snapshot_repository())
    for item in items:
        item["source_type"] = "database_components_route"
    return FreightSettingsResponse.model_validate({"items": items})


@router.patch("/api/v1/regional-freight-components", response_model=FreightSettingsResponse)
def update_regional_freight_component(
    request: FreightComponentUpdateRequest,
    http_request: Request,
) -> FreightSettingsResponse:
    actor = _require_permission(http_request, "workbench.view")
    try:
        items = get_regional_spread_predictor().update_freight_component(
            component_key=request.component_key,
            freight_value=request.freight_value,
            updated_by=str(actor.get("username") or actor.get("display_name") or ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FreightSettingsResponse.model_validate({"items": items})


@router.get("/api/v1/policy-events", response_model=PolicyEventFeedResponse)
def policy_event_feed(
    news_date: date | None = Query(default=None),
    policy_date: date | None = Query(default=None),
    sort_mode: str = Query(default="importance", pattern="^(importance|time)$"),
    http_request: Request = None,
) -> PolicyEventFeedResponse:
    _require_permission(http_request, "policy.view")
    try:
        payload = get_dataset_service().build_policy_event_feed(
            news_date=news_date,
            policy_date=policy_date,
            sort_mode=sort_mode,
        )
        payload["alerts"] = get_repository().apply_alert_case_states(payload.get("alerts", []))
        for item in payload["alerts"]:
            status = str(item.get("status") or "new")
            item.setdefault(
                "state_machine",
                {
                    "current": status,
                    "current_label": {
                        "new": "新触发",
                        "reviewing": "待确认",
                        "tracking": "跟踪中",
                        "resolved": "已解除",
                        "dismissed": "误报",
                    }.get(status, status),
                    "allowed_transitions": ["tracking", "resolved", "dismissed"],
                    "next_action": "跟踪研判" if status in {"new", "reviewing"} else "保持复核",
                },
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PolicyEventFeedResponse.model_validate(payload)


@router.patch("/api/v1/alerts/{alert_id}", response_model=AlertCaseUpdateResponse)
def update_alert_case(alert_id: str, request: AlertCaseUpdateRequest, http_request: Request) -> AlertCaseUpdateResponse:
    actor = _require_permission(http_request, "policy.view")
    payload = get_repository().update_alert_case_state(
        alert_id=alert_id,
        status=request.status,
        note=request.note,
        actor=str(actor.get("username") or actor.get("display_name") or ""),
    )
    return AlertCaseUpdateResponse.model_validate(payload)


@router.get("/api/v1/agents/catalog")
def agent_catalog(http_request: Request) -> dict[str, Any]:
    _require_permission(http_request, "agents.view")
    return get_agent_control_service().get_catalog()


@router.get("/api/v1/agents/overview", response_model=AgentOverviewResponse)
def agent_overview(limit_runs: int = Query(default=40, ge=10, le=200), http_request: Request = None) -> AgentOverviewResponse:
    _require_permission(http_request, "agents.view")
    return AgentOverviewResponse.model_validate(get_agent_control_service().get_overview(limit_runs=limit_runs))


@router.get("/api/v1/agents/graph", response_model=AgentGraphResponse)
def agent_graph(http_request: Request) -> AgentGraphResponse:
    _require_permission(http_request, "agents.view")
    return AgentGraphResponse.model_validate(get_agent_control_service().get_graph())


@router.get("/api/v1/agents/runs", response_model=AgentRunListResponse)
def agent_runs(limit: int = Query(default=30, ge=5, le=200), http_request: Request = None) -> AgentRunListResponse:
    _require_permission(http_request, "agents.view")
    return AgentRunListResponse.model_validate(get_agent_control_service().list_runs(limit=limit))


@router.get("/api/v1/agents/runs/{run_id}", response_model=AgentRunDetailResponse)
def agent_run_detail(run_id: str, http_request: Request) -> AgentRunDetailResponse:
    _require_permission(http_request, "agents.view")
    try:
        payload = get_agent_control_service().get_run_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc
    return AgentRunDetailResponse.model_validate(payload)


@router.get("/api/v1/agents/optimization/state", response_model=AgentOptimizationStateResponse)
def agent_optimization_state(http_request: Request) -> AgentOptimizationStateResponse:
    _require_permission(http_request, "agents.view")
    return AgentOptimizationStateResponse.model_validate(get_agent_control_service().get_optimization_state())


@router.post(
    "/api/v1/agents/optimization/proposals/generate",
    response_model=AgentOptimizationProposalResponse,
)
def generate_agent_optimization_proposal(http_request: Request) -> AgentOptimizationProposalResponse:
    _require_permission(http_request, "agents.view")
    payload = get_agent_control_service().generate_optimization_proposal()
    return AgentOptimizationProposalResponse.model_validate(payload)


@router.post(
    "/api/v1/agents/optimization/proposals/{proposal_id}/confirm",
    response_model=AgentOptimizationProposalResponse,
)
def confirm_agent_optimization_proposal(
    proposal_id: str,
    request: ConfirmOptimizationProposalRequest,
    http_request: Request,
) -> AgentOptimizationProposalResponse:
    _require_permission(http_request, "agents.view")
    service = get_agent_control_service()
    try:
        payload = service.confirm_optimization_proposal(
            proposal_id,
            approved=request.approved,
            reviewer=request.reviewer,
            note=request.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AgentOptimizationProposalResponse.model_validate(payload)


@router.get("/api/v1/agents/{agent_name}/outputs", response_model=AgentOutputHistoryResponse)
def agent_output_history(
    agent_name: str,
    limit: int = Query(default=20, ge=5, le=100),
    http_request: Request = None,
) -> AgentOutputHistoryResponse:
    _require_permission(http_request, "agents.view")
    try:
        payload = get_agent_control_service().get_agent_output_history(agent_name, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_name}") from exc
    return AgentOutputHistoryResponse.model_validate(payload)


@router.post("/api/v1/predictions/shandong-gasoline-92/run", response_model=PredictResponse)
def run_prediction(request: PredictRequest, http_request: Request) -> PredictResponse:
    _require_permission(http_request, "workbench.view")
    predictor = get_predictor()
    repository = get_repository()
    try:
        as_of_date = request.as_of_date or get_dataset_service().resolve_default_prediction_as_of(date.today())
        prediction = predictor.run_prediction(
            as_of_date=as_of_date,
            horizon=_active_horizon(request.horizon),
            use_llm_explainer=request.use_llm_explainer,
            scenario_text=request.scenario_text,
            enable_refined_news=request.enable_refined_news,
            enable_event_risk=request.enable_event_risk,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository.save_prediction(prediction)
    _persist_prediction_audit(prediction)
    return PredictResponse(prediction=prediction)


@router.post("/api/v1/predictions/shandong-regional-spreads/run", response_model=MultiPredictResponse)
def run_regional_spread_predictions(request: RegionalSpreadPredictRequest, http_request: Request) -> MultiPredictResponse:
    _require_permission(http_request, "workbench.view")
    predictor = get_regional_spread_predictor()
    repository = get_repository()
    try:
        as_of_date = request.as_of_date or get_dataset_service().resolve_default_prediction_as_of(date.today())
        predictions = predictor.run_all_predictions(
            as_of_date=as_of_date,
            horizon=_active_horizon(request.horizon),
            use_llm_explainer=request.use_llm_explainer,
            scenario_text=request.scenario_text,
            enable_refined_news=request.enable_refined_news,
            enable_event_risk=request.enable_event_risk,
            region_codes=request.region_codes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for prediction in predictions:
        repository.save_prediction(prediction)
        _persist_prediction_audit(prediction)
    return MultiPredictResponse(predictions=predictions)



def _scorecard_has_current_config(prediction: Any) -> bool:
    raw_context = getattr(prediction, "raw_context", None) or {}
    switches = raw_context.get("switches") if isinstance(raw_context, dict) else {}
    if isinstance(switches, dict) and switches.get("enable_refined_news") is False:
        return False
    event_gate = raw_context.get("event_gate") if isinstance(raw_context, dict) else {}
    event_risk_gate = event_gate.get("llm_risk_gate") if isinstance(event_gate, dict) else {}
    brent_change = event_gate.get("brent_change_1d") if isinstance(event_gate, dict) else None
    try:
        brent_change_value = float(brent_change)
    except (TypeError, ValueError):
        brent_change_value = 0.0
    if (
        brent_change_value <= -3.0
        and isinstance(event_risk_gate, dict)
        and str(event_risk_gate.get("direction") or "").lower() == "up"
        and str(event_gate.get("level") or "").lower() in {"high", "extreme"}
    ):
        return False
    flat_features = _prediction_scorecard_features(prediction)
    feature_names = {str(feature.get("feature_name") or "") for feature in flat_features}
    if prediction.horizon in ACTIVE_HORIZONS:
        expected = "diesel_crack_percentile" if getattr(prediction, "product_code", None) == "DIESEL_0" else "gasoline_crack_percentile"
        if expected not in feature_names:
            return False
    stale_required_values = {
        "price_window_expectation_weekly",
        "price_window_expectation_monthly",
        "main_company_inventory_monthly",
        "monthly_market_sentiment",
    }
    for feature in flat_features:
        name = str(feature.get("feature_name") or "")
        if name in stale_required_values and (feature.get("value") is None or feature.get("matched_label") == "missing"):
            return False
    if not _prediction_data_fingerprint_is_current(prediction, flat_features):
        return False
    return True


def _refresh_cached_prediction_if_scorecard_stale(prediction: Any) -> Any:
    if _scorecard_has_current_config(prediction):
        return prediction
    try:
        dataset_service = get_dataset_service()
        predictor = get_predictor()
        context = dataset_service.build_context(prediction.as_of_date)
        if getattr(prediction, "product_code", None) == "DIESEL_0" or getattr(prediction, "entity_code", None) == "SD_DIESEL0":
            refreshed = predictor.run_diesel0_prediction_from_context(
                context=context,
                as_of_date=prediction.as_of_date,
                horizon=prediction.horizon,
                use_llm_explainer=False,
                enable_refined_news=True,
                enable_event_risk=True,
            )
        else:
            refreshed = predictor.run_prediction_from_context(
                context=context,
                as_of_date=prediction.as_of_date,
                horizon=prediction.horizon,
                use_llm_explainer=False,
                enable_refined_news=True,
                enable_event_risk=True,
            )
        get_repository().save_prediction(refreshed)
        return refreshed
    except Exception:
        return prediction


def _prediction_recency_key(prediction: Any) -> tuple[Any, Any]:
    """Prefer the newest prediction input date, then the newest created time."""
    created_at = getattr(prediction, "created_at", None)
    return (getattr(prediction, "as_of_date", None) or date.min, created_at or datetime.min)


def _latest_by_horizon(predictions: list[Any]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for prediction in predictions:
        horizon = getattr(prediction, "horizon", None)
        if not horizon:
            continue
        current = selected.get(horizon)
        if current is None or _prediction_recency_key(prediction) > _prediction_recency_key(current):
            selected[horizon] = prediction
    return selected

def _dashboard_from_predictions(
    *,
    outright_predictions: list[Any],
    diesel0_predictions: list[Any] | None = None,
    regional_predictions: list[Any],
    selected_horizon: str,
    metadata: dict[str, Any] | None = None,
    refresh_stale_scorecards: bool = False,
) -> DashboardResponse:
    raw_outright_by_horizon = _latest_by_horizon(outright_predictions)
    outright_by_horizon: dict[str, Any] = {
        horizon: (_refresh_cached_prediction_if_scorecard_stale(prediction) if refresh_stale_scorecards else prediction)
        for horizon, prediction in raw_outright_by_horizon.items()
    }
    if not outright_by_horizon:
        raise HTTPException(status_code=404, detail="暂无历史预测，请点击生成新预测。")
    requested_horizons = [horizon for horizon in DEFAULT_HORIZONS if horizon in outright_by_horizon and horizon in ACTIVE_HORIZONS] or [horizon for horizon in outright_by_horizon if horizon in ACTIVE_HORIZONS]
    selected = selected_horizon if selected_horizon in requested_horizons and selected_horizon in outright_by_horizon else requested_horizons[0]
    outright_list = [outright_by_horizon[horizon] for horizon in requested_horizons]
    raw_diesel0_by_horizon = _latest_by_horizon(diesel0_predictions or [])
    diesel0_by_horizon: dict[str, Any] = {
        horizon: (_refresh_cached_prediction_if_scorecard_stale(prediction) if refresh_stale_scorecards else prediction)
        for horizon, prediction in raw_diesel0_by_horizon.items()
    }
    diesel0_list = [diesel0_by_horizon[horizon] for horizon in requested_horizons if horizon in diesel0_by_horizon]
    regional_by_horizon: dict[str, list[Any]] = {horizon: [] for horizon in requested_horizons}
    seen_regions: dict[str, set[str]] = {horizon: set() for horizon in requested_horizons}
    for prediction in regional_predictions:
        raw_context = getattr(prediction, "raw_context", None) or {}
        if raw_context.get("regional_price_prediction_mode") != "regionalized_shandong_market_logic":
            continue
        variants = raw_context.get("regional_prediction_variants") or []
        if not variants and not raw_context.get("regional_composite_prediction"):
            continue
        horizon = prediction.horizon
        if horizon not in regional_by_horizon:
            continue
        region_key = (prediction.raw_context or {}).get("counter_region_code") or prediction.region_code
        existing_index = next(
            (
                index
                for index, item in enumerate(regional_by_horizon[horizon])
                if ((item.raw_context or {}).get("counter_region_code") or item.region_code) == region_key
            ),
            None,
        )
        if existing_index is not None:
            if _prediction_recency_key(prediction) > _prediction_recency_key(regional_by_horizon[horizon][existing_index]):
                regional_by_horizon[horizon][existing_index] = prediction
            continue
        seen_regions[horizon].add(region_key)
        regional_by_horizon[horizon].append(prediction)
    regional_by_horizon = {
        horizon: attach_regional_price_forecasts(items, outright_list)
        for horizon, items in regional_by_horizon.items()
    }
    outright_prediction = outright_by_horizon[selected]
    latest_prices = {
        "sd_gas92_market": _round_or_none((outright_prediction.raw_context or {}).get("current_price")),
        "sd_gas_crack": _round_or_none((outright_prediction.raw_context or {}).get("current_gasoline_crack_spread")),
        "sd_diesel0_market": _round_or_none(
            (diesel0_by_horizon.get(selected).raw_context or {}).get("current_price")
            if diesel0_by_horizon.get(selected)
            else (outright_prediction.raw_context or {}).get("current_diesel0_price")
        ),
        "sd_diesel_crack": _round_or_none(
            (diesel0_by_horizon.get(selected).raw_context or {}).get("current_diesel_crack_spread")
            if diesel0_by_horizon.get(selected)
            else (outright_prediction.raw_context or {}).get("current_diesel_crack_spread")
        ),
        "cny_mid_rate": _round_or_none((outright_prediction.raw_context or {}).get("cny_mid")),
        "brent_active_settlement": _round_or_none((outright_prediction.raw_context or {}).get("brent_settlement")),
    }
    selected_diesel0 = diesel0_by_horizon.get(selected)
    diesel0_monitor = _build_diesel0_monitor(
        latest_prices=latest_prices,
        outright_prediction=selected_diesel0 or outright_prediction,
    )
    diesel0_quality = _build_cached_diesel0_data_quality(selected_diesel0)
    data_gate = _build_data_gate(
        target_date=outright_prediction.as_of_date,
        latest_prices=latest_prices,
        metadata=metadata or {},
        prediction=outright_prediction,
    )
    return DashboardResponse(
        as_of_date=outright_prediction.as_of_date,
        selected_horizon=selected,
        outright_prediction=outright_prediction,
        outright_predictions=outright_list,
        regional_spread_predictions=regional_by_horizon.get(selected, []),
        regional_spread_predictions_by_horizon=regional_by_horizon,
        latest_prices=latest_prices,
        metadata={
            "available_horizons": requested_horizons,
            "loaded_from_cache": True,
            "cache_note": "页面刷新优先展示最近一次已生成预测；点击生成新预测才重新计算。",
            "data_gate": data_gate,
            "product_scope": _build_product_scope(diesel0_monitor),
            "diesel0_monitor": diesel0_monitor,
            "diesel0_prediction": selected_diesel0,
            "diesel0_predictions": diesel0_list,
            "diesel0_data_quality": diesel0_quality,
            **(metadata or {}),
        },
    )



@router.get("/api/v1/dashboard/shandong-gasoline-92/latest", response_model=DashboardResponse)
def latest_dashboard_prediction(
    horizon: str = Query(default="D1"),
    http_request: Request = None,
) -> DashboardResponse:
    _require_permission(http_request, "workbench.view")
    records = get_repository().list_prediction_records(limit=400)
    outright_predictions = []
    diesel0_predictions = []
    regional_predictions = []
    for record in records:
        try:
            prediction = PredictionResult.model_validate(record.payload)
        except Exception:
            continue
        if prediction.entity_code == "SD_DIESEL0" or prediction.product_code == "DIESEL_0":
            diesel0_predictions.append(prediction)
        elif prediction.entity_code == "SD_GAS92" or prediction.product_code == "GASOLINE_92":
            outright_predictions.append(prediction)
        elif str(prediction.entity_code).endswith("_VS_SD_GAS92_SPREAD"):
            regional_predictions.append(prediction)
    return _dashboard_from_predictions(
        outright_predictions=outright_predictions,
        diesel0_predictions=diesel0_predictions,
        regional_predictions=regional_predictions,
        selected_horizon=horizon,
        refresh_stale_scorecards=False,
    )


@router.post("/api/v1/dashboard/shandong-gasoline-92", response_model=DashboardResponse)
def dashboard_prediction(request: PredictRequest, http_request: Request) -> DashboardResponse:
    _require_permission(http_request, "workbench.view")
    dataset_service = get_dataset_service()
    predictor = get_predictor()
    spread_predictor = get_regional_spread_predictor()
    repository = get_repository()
    selected_horizon = _active_horizon(request.horizon)
    requested_horizons = _active_horizons(request.horizons)
    try:
        run_date = date.today()
        target_date = request.as_of_date or dataset_service.resolve_default_prediction_as_of(run_date)
        context = dataset_service.build_context(target_date)
        outright_predictions = predictor.run_multi_horizon_predictions_from_context(
            context=context,
            as_of_date=target_date,
            horizons=requested_horizons,
            use_llm_explainer=False,
            scenario_text=request.scenario_text,
            enable_refined_news=request.enable_refined_news,
            enable_event_risk=request.enable_event_risk,
        )
        diesel0_error: str | None = None
        diesel0_predictions: list[Any] = []
        try:
            diesel0_predictions = predictor.run_diesel0_multi_horizon_predictions_from_context(
                context=context,
                as_of_date=target_date,
                horizons=requested_horizons,
                use_llm_explainer=False,
                scenario_text=request.scenario_text,
                enable_refined_news=request.enable_refined_news,
                enable_event_risk=request.enable_event_risk,
            )
        except Exception as exc:
            diesel0_error = str(exc)
        regional_error: str | None = None
        diesel0_regional_error: str | None = None
        try:
            regional_predictions_by_horizon = spread_predictor.run_multi_horizon_predictions_from_context(
                context=context,
                as_of_date=target_date,
                horizons=requested_horizons,
                use_llm_explainer=False,
                scenario_text=request.scenario_text,
                enable_refined_news=request.enable_refined_news,
                enable_event_risk=request.enable_event_risk,
                product_code="GASOLINE_92",
            )
            regional_predictions_by_horizon = {
                horizon: attach_regional_price_forecasts(predictions, outright_predictions)
                for horizon, predictions in regional_predictions_by_horizon.items()
            }
        except Exception as exc:
            regional_error = str(exc)
            regional_predictions_by_horizon = {horizon: [] for horizon in requested_horizons}
        try:
            diesel0_regional_predictions_by_horizon = spread_predictor.run_multi_horizon_predictions_from_context(
                context=context,
                as_of_date=target_date,
                horizons=requested_horizons,
                use_llm_explainer=False,
                scenario_text=request.scenario_text,
                enable_refined_news=request.enable_refined_news,
                enable_event_risk=request.enable_event_risk,
                product_code="DIESEL_0",
            )
            diesel0_regional_predictions_by_horizon = {
                horizon: attach_regional_price_forecasts(predictions, diesel0_predictions)
                for horizon, predictions in diesel0_regional_predictions_by_horizon.items()
            }
        except Exception as exc:
            diesel0_regional_error = str(exc)
            diesel0_regional_predictions_by_horizon = {horizon: [] for horizon in requested_horizons}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outright_prediction = next(
        (prediction for prediction in outright_predictions if prediction.horizon == selected_horizon),
        outright_predictions[0],
    )
    diesel0_prediction = next(
        (prediction for prediction in diesel0_predictions if prediction.horizon == selected_horizon),
        diesel0_predictions[0] if diesel0_predictions else None,
    )
    regional_predictions = regional_predictions_by_horizon.get(selected_horizon, [])
    current_row = context.current_row
    brent_live_payload: dict[str, Any] | None = None
    try:
        brent_live_payload = dataset_service.get_brent_realtime_snapshot(as_of_date=target_date)
    except Exception:
        brent_live_payload = None

    if request.persist_run:
        for item in outright_predictions:
            repository.save_prediction(item)
            _persist_prediction_audit(item)
        for item in diesel0_predictions:
            repository.save_prediction(item)
            _persist_prediction_audit(item)
        for horizon_items in regional_predictions_by_horizon.values():
            for item in horizon_items:
                repository.save_prediction(item)
                _persist_prediction_audit(item)
        for horizon_items in diesel0_regional_predictions_by_horizon.values():
            for item in horizon_items:
                repository.save_prediction(item)
                _persist_prediction_audit(item)

    brent_live_price = brent_live_payload.get("latest_price") if brent_live_payload else None
    latest_prices = {
        "brent_active_settlement": _round_or_none(
            brent_live_price if brent_live_price is not None else current_row.get("brent_active_settlement")
        ),
        "sd_gas92_market": _round_or_none(current_row.get("sd_gas92_market")),
        "cn_gas92_market": _round_or_none(current_row.get("cn_gas92_market")),
        "east_china_gas92_market": _round_or_none(current_row.get("east_china_gas92_market")),
        "north_china_gas92_market": _round_or_none(current_row.get("north_china_gas92_market")),
        "south_china_gas92_market": _round_or_none(current_row.get("south_china_gas92_market")),
        "central_china_gas92_market": _round_or_none(current_row.get("central_china_gas92_market")),
        "northwest_gas92_market": _round_or_none(current_row.get("northwest_gas92_market")),
        "southwest_gas92_market": _round_or_none(current_row.get("southwest_gas92_market")),
        "northeast_gas92_market": _round_or_none(current_row.get("northeast_gas92_market")),
        "sd_diesel0_market": _round_or_none(current_row.get("sd_diesel0_market")),
        "cn_diesel0_market": _round_or_none(current_row.get("cn_diesel0_market")),
        "east_china_diesel0_market": _round_or_none(current_row.get("east_china_diesel0_market")),
        "north_china_diesel0_market": _round_or_none(current_row.get("north_china_diesel0_market")),
        "south_china_diesel0_market": _round_or_none(current_row.get("south_china_diesel0_market")),
        "central_china_diesel0_market": _round_or_none(current_row.get("central_china_diesel0_market")),
        "northwest_diesel0_market": _round_or_none(current_row.get("northwest_diesel0_market")),
        "southwest_diesel0_market": _round_or_none(current_row.get("southwest_diesel0_market")),
        "northeast_diesel0_market": _round_or_none(current_row.get("northeast_diesel0_market")),
        "cny_mid_rate": _round_or_none(current_row.get("cny_mid_rate")),
        "sd_gas_crack": _round_or_none(current_row.get("sd_gas_crack")),
        "sd_diesel_crack": _round_or_none(current_row.get("sd_diesel_crack")),
    }
    diesel0_quality = _build_diesel0_data_quality(current_row, context.feature_frame)
    diesel0_monitor = _build_diesel0_monitor(
        current_row=current_row,
        latest_prices=latest_prices,
        outright_prediction=diesel0_prediction or outright_prediction,
        data_quality=diesel0_quality,
    )
    data_gate = _build_data_gate(
        target_date=target_date,
        latest_prices=latest_prices,
        metadata={
            "market_data_mode": context.metadata.get("market_data_mode"),
            "market_data_reason": context.metadata.get("market_data_reason"),
            "refined_news_items": context.refined_news_items,
            "policy_items": context.policy_items,
        },
        prediction=outright_prediction,
    )

    return DashboardResponse(
        as_of_date=target_date,
        selected_horizon=selected_horizon,
        outright_prediction=outright_prediction,
        outright_predictions=outright_predictions,
        regional_spread_predictions=regional_predictions,
        regional_spread_predictions_by_horizon=regional_predictions_by_horizon,
        latest_prices=latest_prices,
        metadata={
            "refined_news_items": context.refined_news_items[:8],
            "event_news_items": context.news_items[:8],
            "policy_items": context.policy_items[:5],
            "available_regions": spread_predictor.list_regions(),
            "available_diesel0_regions": spread_predictor.list_regions(product_code="DIESEL_0"),
            "available_horizons": requested_horizons,
            "market_data_mode": context.metadata.get("market_data_mode"),
            "market_data_reason": context.metadata.get("market_data_reason"),
            "prediction_run_date": run_date.isoformat(),
            "prediction_input_date": target_date.isoformat(),
            "price_anchor_date": context.metadata.get("price_anchor_date"),
            "brent_live": brent_live_payload,
            "crude_report_horizons": (
                context.report_payload.get("signals", {}).get("horizon_forecasts", {}) if context.report_payload else {}
            ),
            "regional_spread_error": regional_error,
            "diesel0_regional_spread_error": diesel0_regional_error,
            "diesel0_regional_spread_predictions_by_horizon": diesel0_regional_predictions_by_horizon,
            "diesel0_error": diesel0_error,
            "data_gate": data_gate,
            "product_scope": _build_product_scope(diesel0_monitor),
            "diesel0_monitor": diesel0_monitor,
            "diesel0_prediction": diesel0_prediction,
            "diesel0_predictions": diesel0_predictions,
            "diesel0_data_quality": diesel0_quality,
        },
    )


@router.post("/api/v1/dashboard/shandong-gasoline-92/narrative", response_model=DashboardNarrativeResponse)
def dashboard_narrative(request: PredictRequest, http_request: Request) -> DashboardNarrativeResponse:
    _require_permission(http_request, "workbench.view")
    dataset_service = get_dataset_service()
    predictor = get_predictor()
    spread_predictor = get_regional_spread_predictor()
    selected_horizon = _active_horizon(request.horizon)
    try:
        target_date = request.as_of_date or dataset_service.resolve_default_prediction_as_of(date.today())
        context = dataset_service.build_context(target_date)
        outright_prediction = predictor.run_prediction_from_context(
            context=context,
            as_of_date=target_date,
            horizon=selected_horizon,
            use_llm_explainer=request.use_llm_explainer,
            scenario_text=request.scenario_text,
            enable_refined_news=request.enable_refined_news,
            enable_event_risk=request.enable_event_risk,
        )
        regional_predictions = spread_predictor.run_all_predictions_from_context(
            context=context,
            as_of_date=target_date,
            horizon=selected_horizon,
            use_llm_explainer=False,
            scenario_text=request.scenario_text,
            enable_refined_news=request.enable_refined_news,
            enable_event_risk=request.enable_event_risk,
        )
        regional_predictions = attach_regional_price_forecasts(regional_predictions, [outright_prediction])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    get_repository().save_prediction(outright_prediction)
    _persist_prediction_audit(outright_prediction)
    return DashboardNarrativeResponse(
        as_of_date=target_date,
        selected_horizon=selected_horizon,
        outright_prediction=outright_prediction,
        regional_spread_predictions=regional_predictions,
    )


@router.post("/api/v1/backtest/shandong-gasoline-92", response_model=BacktestResponse)
def run_backtest(request: BacktestRequest, http_request: Request) -> BacktestResponse:
    _require_permission(http_request, "agents.view")
    service = get_backtest_service()
    repository = get_repository()
    try:
        summary = service.run(
            start_date=request.start_date,
            end_date=request.end_date,
            horizon=_active_horizon(request.horizon),
            max_rows=request.max_rows,
            news_mode=request.news_mode,
            enable_event_risk=request.enable_event_risk,
            compare_with_baseline=request.compare_with_baseline,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository.save_backtest(summary, slug=f"sdgas92-{request.start_date}-{request.end_date}")
    return BacktestResponse(summary=summary)


@router.post("/api/v1/chat/predict", response_model=ChatPredictResponse)
def chat_predict(request: ChatPredictRequest, http_request: Request) -> ChatPredictResponse:
    user = _require_permission(http_request, "chat.use")
    try:
        payload = get_workbench_service().chat_predict(
            message=request.message,
            as_of_date=request.as_of_date,
            horizon=_active_horizon(request.horizon),
            use_llm_explainer=request.use_llm_explainer,
            enable_refined_news=request.enable_refined_news,
            enable_event_risk=request.enable_event_risk,
            conversation_id=request.conversation_id,
            user_context={
                "user_id": user.get("user_id"),
                "username": user.get("username"),
                "session_hash": _session_hash_from_request(http_request),
            },
        )
        _persist_prediction_audit(payload.get("outright_prediction"))
        for item in payload.get("regional_spread_predictions", []):
            _persist_prediction_audit(item)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatPredictResponse.model_validate(payload)


@router.post("/api/v1/briefings/morning", response_model=MorningBriefingResponse)
def generate_morning_briefing(request: MorningBriefingRequest, http_request: Request) -> MorningBriefingResponse:
    _require_permission(http_request, "briefing.generate")
    try:
        payload = get_workbench_service().generate_morning_briefing(
            as_of_date=request.as_of_date,
            use_llm_writer=request.use_llm_writer,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MorningBriefingResponse.model_validate(payload)


@router.get("/api/v1/briefings/latest", response_model=MorningBriefingResponse)
def latest_morning_briefing(http_request: Request) -> MorningBriefingResponse:
    _require_permission(http_request, "workbench.view")
    payload = get_workbench_service().load_latest_briefing()
    if payload is None:
        payload = get_workbench_service().generate_morning_briefing(as_of_date=date.today(), use_llm_writer=False)
    return MorningBriefingResponse.model_validate(payload)


@router.get("/api/v1/system/scheduler", response_model=SchedulerStatusResponse)
def scheduler_status(http_request: Request) -> SchedulerStatusResponse:
    _require_permission(http_request, "agents.view")
    return SchedulerStatusResponse.model_validate(get_scheduler_service().get_status())
