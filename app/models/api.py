from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.common import BacktestSummary, BusinessAdvice, PredictionResult


PredictHorizon = Literal["D1", "D3", "W1", "M1"]
AgentHealthStatus = Literal["online", "attention", "disabled", "idle"]
ProposalStatus = Literal["pending", "confirmed", "rejected", "superseded"]


class PredictRequest(BaseModel):
    horizon: PredictHorizon = "D1"
    horizons: list[PredictHorizon] = Field(default_factory=list)
    as_of_date: date | None = None
    scenario_text: str | None = None
    use_llm_explainer: bool = True
    enable_refined_news: bool = True
    enable_event_risk: bool = True
    persist_run: bool = False


class PredictResponse(BaseModel):
    prediction: PredictionResult


class RegionalSpreadPredictRequest(PredictRequest):
    region_codes: list[str] = Field(default_factory=list)


class MultiPredictResponse(BaseModel):
    predictions: list[PredictionResult]


class DashboardResponse(BaseModel):
    as_of_date: date
    selected_horizon: PredictHorizon = "D1"
    outright_prediction: PredictionResult
    outright_predictions: list[PredictionResult] = Field(default_factory=list)
    regional_spread_predictions: list[PredictionResult]
    regional_spread_predictions_by_horizon: dict[str, list[PredictionResult]] = Field(default_factory=dict)
    latest_prices: dict[str, float | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DashboardNarrativeResponse(BaseModel):
    as_of_date: date
    selected_horizon: PredictHorizon = "D1"
    outright_prediction: PredictionResult
    regional_spread_predictions: list[PredictionResult] = Field(default_factory=list)


class MarketSnapshotResponse(BaseModel):
    as_of_date: date
    generated_at: datetime
    latest_prices: dict[str, float | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrentLiveResponse(BaseModel):
    as_of_date: date
    generated_at: datetime
    latest_price: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PriceHistorySeries(BaseModel):
    key: str
    label: str
    unit: str = "元/吨"
    points: list[dict[str, Any]] = Field(default_factory=list)


class PriceHistoryResponse(BaseModel):
    start_date: date
    end_date: date
    generated_at: datetime
    available_series: list[dict[str, str]] = Field(default_factory=list)
    series: list[PriceHistorySeries] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyEventFeedResponse(BaseModel):
    news_date: date
    refined_news_date: date | None = None
    event_news_date: date | None = None
    policy_date: date
    sort_mode: Literal["importance", "time"] = "importance"
    available_news_dates: list[date] = Field(default_factory=list)
    available_refined_news_dates: list[date] = Field(default_factory=list)
    available_event_news_dates: list[date] = Field(default_factory=list)
    available_policy_dates: list[date] = Field(default_factory=list)
    refined_news_items: list[dict[str, Any]] = Field(default_factory=list)
    event_news_items: list[dict[str, Any]] = Field(default_factory=list)
    policy_items: list[dict[str, Any]] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)


class AlertCaseUpdateRequest(BaseModel):
    status: Literal["new", "reviewing", "tracking", "resolved", "dismissed"]
    note: str | None = None


class AlertCaseUpdateResponse(BaseModel):
    alert_id: str
    status: str
    note: str | None = None
    updated_at: datetime


class FreightComponentItem(BaseModel):
    component_key: str
    short_name: str | None = None
    route_name: str | None = None
    freight_value: float | None = None
    unit: str = "?/?"
    excel_column: int | None = None


class FreightSettingItem(BaseModel):
    region_code: str
    region_name: str
    freight_value: float
    unit: str = "?/?"
    source_type: str = "manual"
    updated_by: str | None = None
    updated_at: datetime | None = None
    as_of_date: str | None = None
    workbook_value: float | None = None
    excel_label: str | None = None
    calculation: str | None = None
    components: list[FreightComponentItem] = Field(default_factory=list)

class FreightSettingsResponse(BaseModel):
    items: list[FreightSettingItem] = Field(default_factory=list)


class FreightSettingUpdateRequest(BaseModel):
    freight_value: float = Field(ge=0, le=2000)


class FreightComponentUpdateRequest(BaseModel):
    component_key: str
    freight_value: float = Field(ge=0, le=2000)


class BacktestRequest(BaseModel):
    horizon: Literal["D1"] = "D1"
    start_date: date
    end_date: date
    max_rows: int = Field(default=30, ge=5, le=180)
    news_mode: Literal["off", "refined_news_archive"] = "off"
    enable_event_risk: bool = False
    compare_with_baseline: bool = False


class BacktestResponse(BaseModel):
    summary: BacktestSummary


class PredictionAccuracyItem(BaseModel):
    source: str
    run_id: str
    product_label: str
    horizon: str
    as_of_date: date
    target_date: date
    base_price_date: date | None = None
    actual_price_date: date | None = None
    predicted_direction: str
    predicted_point: float
    range_lower: float
    range_upper: float
    confidence_score: float | None = None
    actual_price: float | None = None
    base_price: float | None = None
    actual_change: float | None = None
    point_error: float | None = None
    absolute_error: float | None = None
    range_hit: bool | None = None
    direction_hit: bool | None = None
    status: str
    explanation: str | None = None
    generated_at: datetime | None = None


class PredictionAccuracySummary(BaseModel):
    sample_size: int = 0
    pending_size: int = 0
    mae: float | None = None
    direction_accuracy: float | None = None
    range_hit_rate: float | None = None
    within_50_rate: float | None = None


class PredictionAccuracyResponse(BaseModel):
    generated_at: datetime
    summary: PredictionAccuracySummary
    items: list[PredictionAccuracyItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentScopeControl(BaseModel):
    scope_key: str
    scope_label: str
    enabled: bool
    weight: float
    default_weight: float
    updated_at: datetime | None = None
    source: str | None = None


class AgentOverviewItem(BaseModel):
    agent_name: str
    label: str
    role: str
    layer: Literal["chief", "subagent", "llm_agent"]
    optimizable: bool = True
    status: AgentHealthStatus
    status_reason: str
    run_count: int = 0
    last_run_id: str | None = None
    last_seen_at: datetime | None = None
    recent_direction: str | None = None
    recent_confidence_label: str | None = None
    avg_confidence_score: float | None = None
    avg_abs_contribution: float | None = None
    recent_summary: str | None = None
    controls: list[AgentScopeControl] = Field(default_factory=list)
    downstream_targets: list[str] = Field(default_factory=list)


class AgentOverviewResponse(BaseModel):
    generated_at: datetime
    recent_run_count: int
    latest_backtest: dict[str, Any] = Field(default_factory=dict)
    agents: list[AgentOverviewItem] = Field(default_factory=list)


class AgentGraphNode(BaseModel):
    id: str
    label: str
    role: str
    layer: str
    status: str
    x: float
    y: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentGraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class AgentGraphResponse(BaseModel):
    generated_at: datetime
    nodes: list[AgentGraphNode] = Field(default_factory=list)
    edges: list[AgentGraphEdge] = Field(default_factory=list)


class AgentRunSummary(BaseModel):
    run_id: str
    run_type: Literal["outright", "regional_spread"]
    title: str
    product_label: str
    region_label: str
    as_of_date: date
    target_date: date
    horizon: str
    direction_label: str
    point_value: float
    range_lower: float
    range_upper: float
    confidence_label: str
    confidence_score: float
    created_at: datetime | None = None


class AgentRunListResponse(BaseModel):
    items: list[AgentRunSummary] = Field(default_factory=list)


class AgentRunOutput(BaseModel):
    agent_name: str
    label: str
    role: str
    scope_key: str
    enabled: bool
    weight: float | None = None
    raw_score: float | None = None
    contribution: float | None = None
    direction: str
    confidence_label: str
    confidence_score: float
    summary: str
    evidence: list[str] = Field(default_factory=list)
    numeric_signals: dict[str, float] = Field(default_factory=dict)
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class AgentRunDetailResponse(BaseModel):
    run: AgentRunSummary
    explanation: str
    driver_summary: list[str] = Field(default_factory=list)
    operating_advice: list[BusinessAdvice] = Field(default_factory=list)
    raw_context: dict[str, Any] = Field(default_factory=dict)
    factor_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    agent_outputs: list[AgentRunOutput] = Field(default_factory=list)


class AgentOutputHistoryItem(BaseModel):
    run: AgentRunSummary
    output: AgentRunOutput


class AgentOutputHistoryResponse(BaseModel):
    agent_name: str
    label: str
    items: list[AgentOutputHistoryItem] = Field(default_factory=list)


class AgentScopeControlRecord(BaseModel):
    agent_name: str
    label: str
    role: str
    enabled: bool
    weight: float
    default_weight: float
    updated_at: datetime | None = None
    source: str | None = None


class AgentControlScopeResponse(BaseModel):
    scope_key: str
    scope_label: str
    controls: list[AgentScopeControlRecord] = Field(default_factory=list)


class OptimizationSuggestion(BaseModel):
    scope_key: str
    scope_label: str
    agent_name: str
    label: str
    current_enabled: bool
    proposed_enabled: bool
    current_weight: float
    proposed_weight: float
    reason: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class OptimizationProposal(BaseModel):
    proposal_id: str
    status: ProposalStatus
    created_at: datetime
    confirmed_at: datetime | None = None
    reviewer: str | None = None
    note: str | None = None
    summary: str
    rationale: str
    backtest_snapshot: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[OptimizationSuggestion] = Field(default_factory=list)


class AgentOptimizationStateResponse(BaseModel):
    generated_at: datetime
    scopes: list[AgentControlScopeResponse] = Field(default_factory=list)
    latest_proposal: OptimizationProposal | None = None
    pending_proposals: list[OptimizationProposal] = Field(default_factory=list)


class ConfirmOptimizationProposalRequest(BaseModel):
    approved: bool = True
    reviewer: str | None = None
    note: str | None = None


class AgentOptimizationProposalResponse(BaseModel):
    proposal: OptimizationProposal
    state: AgentOptimizationStateResponse


class ChatPredictRequest(BaseModel):
    message: str
    as_of_date: date | None = None
    horizon: PredictHorizon | None = None
    use_llm_explainer: bool = True
    enable_refined_news: bool = True
    enable_event_risk: bool = True
    conversation_id: str | None = None


class ChatPredictResponse(BaseModel):
    message_id: str
    as_of_date: date
    selected_horizon: PredictHorizon
    answer: str
    answer_only: bool = False
    answer_source: str | None = None
    data_result: dict[str, Any] | None = None
    outright_prediction: PredictionResult | None = None
    regional_spread_predictions: list[PredictionResult] = Field(default_factory=list)


class MorningBriefingRequest(BaseModel):
    as_of_date: date | None = None
    use_llm_writer: bool = True


class MorningBriefingResponse(BaseModel):
    briefing_id: str
    title: str
    as_of_date: date
    generated_at: datetime
    content_markdown: str
    outright_predictions: list[PredictionResult] = Field(default_factory=list)
    regional_spread_predictions: list[PredictionResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class PermissionItem(BaseModel):
    permission_code: str
    permission_name: str
    module_code: str
    description: str | None = None


class RoleItem(BaseModel):
    role_id: int | None = None
    role_code: str
    role_name: str
    description: str | None = None
    is_system: bool = True
    is_active: bool = True
    permission_codes: list[str] = Field(default_factory=list)
    permissions: list[PermissionItem] = Field(default_factory=list)


class UserProfileResponse(BaseModel):
    user_id: int
    username: str
    display_name: str
    title: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None
    permission_codes: list[str] = Field(default_factory=list)
    permissions: list[PermissionItem] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)
    roles: list[RoleItem] = Field(default_factory=list)


class LoginResponse(BaseModel):
    user: UserProfileResponse
    expires_at: datetime


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    title: str | None = None
    password: str | None = None


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    title: str | None = None
    password: str
    is_active: bool = True
    permission_codes: list[str] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    title: str | None = None
    is_active: bool = True
    permission_codes: list[str] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)


class UserListResponse(BaseModel):
    items: list[UserProfileResponse] = Field(default_factory=list)


class UsageLogItem(BaseModel):
    usage_id: int
    user_id: int | None = None
    username: str | None = None
    action: str
    method: str | None = None
    path: str
    status_code: int | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    duration_ms: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class UsageLogListResponse(BaseModel):
    items: list[UsageLogItem] = Field(default_factory=list)


class PermissionCatalogResponse(BaseModel):
    items: list[PermissionItem] = Field(default_factory=list)


class RoleCatalogResponse(BaseModel):
    items: list[RoleItem] = Field(default_factory=list)


class SchedulerJobResponse(BaseModel):
    job_key: str
    label: str
    mode: Literal["interval", "daily"]
    schedule_value: str
    enabled: bool
    running: bool
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_summary: dict[str, Any] = Field(default_factory=dict)


class SchedulerStatusResponse(BaseModel):
    enabled: bool
    timezone: str
    started_at: datetime | None = None
    jobs: list[SchedulerJobResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app: str
