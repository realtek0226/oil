from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


DirectionLabel = Literal["up", "down", "flat"]
ConfidenceLabel = Literal["low", "medium", "high"]
AgentStatus = Literal["success", "failed", "skipped"]
AdvicePriority = Literal["low", "medium", "high"]


class TimeSeriesPoint(BaseModel):
    data_time: date
    value: float
    update_time: datetime | None = None


class FeatureValue(BaseModel):
    name: str
    value_num: float | None = None
    value_text: str | None = None
    as_of_date: date
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentClaim(BaseModel):
    agent_name: str
    direction: DirectionLabel
    confidence_label: ConfidenceLabel
    confidence_score: float
    summary: str
    evidence: list[str] = Field(default_factory=list)
    numeric_signals: dict[str, float] = Field(default_factory=dict)
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class BusinessAdvice(BaseModel):
    title: str
    action: str
    rationale: str
    priority: AdvicePriority = "medium"
    action_type: str | None = None
    trigger_condition: str | None = None
    price_limit: float | None = None
    volume_suggestion: str | None = None
    valid_until: datetime | None = None
    risk_stop: str | None = None
    owner_role: str | None = None


class PredictionResult(BaseModel):
    run_id: str
    entity_code: str
    region_code: str
    product_code: str
    horizon: str
    as_of_date: date
    target_date: date
    direction_label: DirectionLabel
    point_value: float
    range_lower: float
    range_upper: float
    confidence_label: ConfidenceLabel
    confidence_score: float
    score_value: float
    degrade_flag: bool = False
    degrade_reason: str | None = None
    factor_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    agent_claims: list[AgentClaim] = Field(default_factory=list)
    driver_summary: list[str] = Field(default_factory=list)
    operating_advice: list[BusinessAdvice] = Field(default_factory=list)
    explanation: str
    raw_context: dict[str, Any] = Field(default_factory=dict)


class BacktestRow(BaseModel):
    as_of_date: date
    target_date: date
    predicted_direction: DirectionLabel
    actual_direction: DirectionLabel
    predicted_point: float
    actual_point: float
    abs_error: float
    hit_direction: bool


class BacktestVariantSummary(BaseModel):
    variant: str
    sample_size: int
    direction_accuracy: float
    mae: float
    context: dict[str, Any] = Field(default_factory=dict)


class BacktestComparison(BaseModel):
    baseline: BacktestVariantSummary
    candidate: BacktestVariantSummary
    delta_direction_accuracy: float
    delta_mae: float


class BacktestSummary(BaseModel):
    entity_code: str
    horizon: str
    sample_size: int
    direction_accuracy: float
    mae: float
    variant: str = "baseline_no_news"
    context: dict[str, Any] = Field(default_factory=dict)
    comparison: BacktestComparison | None = None
    notes: list[str] = Field(default_factory=list)
    rows: list[BacktestRow]
