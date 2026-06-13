from __future__ import annotations

import csv
import io
from datetime import date, timedelta
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
from app.services.predictors.horizons import DEFAULT_HORIZONS
from app.services.predictors.shandong_regional_spreads import attach_regional_price_forecasts, build_freight_settings_from_components
from app.services.prediction_accuracy import PredictionAccuracyService
from app.core.settings import get_settings


router = APIRouter()
STATIC_INDEX_PATH = Path("app/static/index.html")
LOGIN_PAGE_PATH = Path("app/static/login.html")


def _round_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 2)
    except Exception:
        return None


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
    try:
        payload = get_dataset_service().get_market_snapshot(as_of_date=as_of_date or date.today())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
            horizon=request.horizon,
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
            horizon=request.horizon,
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


def _dashboard_from_predictions(
    *,
    outright_predictions: list[Any],
    regional_predictions: list[Any],
    selected_horizon: str,
    metadata: dict[str, Any] | None = None,
) -> DashboardResponse:
    outright_by_horizon: dict[str, Any] = {}
    for prediction in sorted(outright_predictions, key=lambda item: str(item.as_of_date), reverse=True):
        outright_by_horizon.setdefault(prediction.horizon, prediction)
    if not outright_by_horizon:
        raise HTTPException(status_code=404, detail="暂无历史预测，请点击生成新预测。")
    requested_horizons = [horizon for horizon in DEFAULT_HORIZONS if horizon in outright_by_horizon] or list(outright_by_horizon)
    selected = selected_horizon if selected_horizon in outright_by_horizon else requested_horizons[0]
    outright_list = [outright_by_horizon[horizon] for horizon in requested_horizons]
    regional_by_horizon: dict[str, list[Any]] = {horizon: [] for horizon in requested_horizons}
    seen_regions: dict[str, set[str]] = {horizon: set() for horizon in requested_horizons}
    for prediction in sorted(regional_predictions, key=lambda item: str(item.as_of_date), reverse=True):
        horizon = prediction.horizon
        if horizon not in regional_by_horizon:
            continue
        region_key = (prediction.raw_context or {}).get("counter_region_code") or prediction.region_code
        if region_key in seen_regions[horizon]:
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
        "brent_active_settlement": _round_or_none((outright_prediction.raw_context or {}).get("brent_settlement")),
    }
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
    regional_predictions = []
    for record in records:
        try:
            prediction = PredictionResult.model_validate(record.payload)
        except Exception:
            continue
        if prediction.entity_code == "SD_GAS92" or prediction.region_code == "SHANDONG":
            outright_predictions.append(prediction)
        elif str(prediction.entity_code).endswith("_VS_SD_GAS92_SPREAD"):
            regional_predictions.append(prediction)
    return _dashboard_from_predictions(
        outright_predictions=outright_predictions,
        regional_predictions=regional_predictions,
        selected_horizon=horizon,
    )


@router.post("/api/v1/dashboard/shandong-gasoline-92", response_model=DashboardResponse)
def dashboard_prediction(request: PredictRequest, http_request: Request) -> DashboardResponse:
    _require_permission(http_request, "workbench.view")
    dataset_service = get_dataset_service()
    predictor = get_predictor()
    spread_predictor = get_regional_spread_predictor()
    repository = get_repository()
    selected_horizon = request.horizon
    requested_horizons = request.horizons or DEFAULT_HORIZONS
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
        regional_error: str | None = None
        try:
            regional_predictions_by_horizon = spread_predictor.run_multi_horizon_predictions_from_context(
                context=context,
                as_of_date=target_date,
                horizons=requested_horizons,
                use_llm_explainer=False,
                scenario_text=request.scenario_text,
                enable_refined_news=request.enable_refined_news,
                enable_event_risk=request.enable_event_risk,
            )
            regional_predictions_by_horizon = {
                horizon: attach_regional_price_forecasts(predictions, outright_predictions)
                for horizon, predictions in regional_predictions_by_horizon.items()
            }
        except Exception as exc:
            regional_error = str(exc)
            regional_predictions_by_horizon = {horizon: [] for horizon in requested_horizons}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outright_prediction = next(
        (prediction for prediction in outright_predictions if prediction.horizon == selected_horizon),
        outright_predictions[0],
    )
    regional_predictions = regional_predictions_by_horizon.get(selected_horizon, [])
    current_row = context.current_row
    brent_live_payload: dict[str, Any] | None = None
    try:
        brent_live_payload = dataset_service.get_brent_realtime_snapshot(as_of_date=target_date)
    except Exception:
        brent_live_payload = None

    if request.persist_run:
        repository.save_prediction(outright_prediction)
        _persist_prediction_audit(outright_prediction)
        for item in regional_predictions:
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
    }

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
        },
    )


@router.post("/api/v1/dashboard/shandong-gasoline-92/narrative", response_model=DashboardNarrativeResponse)
def dashboard_narrative(request: PredictRequest, http_request: Request) -> DashboardNarrativeResponse:
    _require_permission(http_request, "workbench.view")
    dataset_service = get_dataset_service()
    predictor = get_predictor()
    spread_predictor = get_regional_spread_predictor()
    selected_horizon = request.horizon
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
            horizon=request.horizon,
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
            horizon=request.horizon,
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
