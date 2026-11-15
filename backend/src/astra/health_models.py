from typing import Literal

from pydantic import BaseModel, FiniteFloat

Status = Literal["STABLE", "WATCH", "FLAGGED", "INSUFFICIENT_DATA"]
Direction = Literal["UP", "DOWN", "FLAT"]
Availability = Literal["CURRENT", "STALE", "MISSING", "UNAVAILABLE"]
Kind = Literal["SINGLE_METRIC", "CONTEXTUAL", "CABIN", "SHARED_CABIN", "DATA_QUALITY"]


class Evidence(BaseModel):
    observation_id: str
    metric: str
    timestamp_utc: str
    value: FiniteFloat | None
    unit: str
    source: str
    context: str
    quality: Literal["VALID", "MISSING"]
    provenance: Literal["SYNTHETIC"] = "SYNTHETIC"


class Baseline(BaseModel):
    metric: str
    context: str
    unit: str
    kind: Literal["continuous", "ordinal", "context_only"]
    availability: Literal["AVAILABLE", "INSUFFICIENT_DATA", "NOT_APPLICABLE"]
    median: FiniteFloat | None = None
    mad: FiniteFloat | None = None
    effective_mad: FiniteFloat | None = None
    valid_sample_count: int
    distinct_days: int
    required_days: int
    calibration_start_utc: str
    calibration_end_utc: str


class Comparison(BaseModel):
    metric: str
    context: str
    current: Evidence | None
    latest_valid: Evidence | None
    availability: Availability
    age_hours: FiniteFloat | None = None
    freshness_hours: int
    status: Status | None = None
    difference: FiniteFloat | None = None
    absolute_difference: FiniteFloat | None = None
    relative_percent: FiniteFloat | None = None
    modified_z: FiniteFloat | None = None
    direction: Direction | None = None
    rolling_median: FiniteFloat | None = None
    trend_direction: Direction | None = None
    slope_per_day: FiniteFloat | None = None
    trend_window_days: int
    recent_days: int
    persistent_days: int = 0
    strong_days: int = 0
    unusual_ids: list[str]


class HabitatComparison(BaseModel):
    metric: str
    unit: str
    window_median: FiniteFloat
    historical_median: FiniteFloat
    effective_mad: FiniteFloat
    modified_z: FiniteFloat
    window_hours: int
    valid_hours: int


class Finding(BaseModel):
    rule_id: str
    type: Kind
    crew_id: str | None = None
    status: Status
    title: str
    explanation: str
    uncertainty: str
    verification: str
    evidence: list[Evidence]
    shared_report_count: int | None = None
    habitat_comparison: HabitatComparison | None = None


class Coverage(BaseModel):
    current_groups: int
    required_groups: int
    total_groups: int
    sufficient: bool


class MonitoringSummary(BaseModel):
    status: Status
    coverage: Coverage
    headline: str


class CrewAnalysis(BaseModel):
    crew_id: str
    revision: int
    cursor_utc: str
    method_version: str
    provenance: Literal["SYNTHETIC"] = "SYNTHETIC"
    status: Status
    coverage: Coverage
    baselines: list[Baseline]
    indicators: list[Comparison]
    blood_pressure: list[Evidence]
    findings: list[Finding]
    cabin_findings: list[Finding]
