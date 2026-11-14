from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Scope = Literal["person", "cabin"]
Context = Literal["rest", "exercise", "recovery", "sleep", "self_report", "unspecified"]
SourceStatus = Literal["VERIFIED", "UNAVAILABLE", "INVALID"]


def parse_utc(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("Timestamp must use YYYY-MM-DDTHH:MM:SSZ.")
    return parsed.replace(tzinfo=timezone.utc)


class Crew(BaseModel):
    crew_id: str
    display_name: str
    role: str


class CrewProfile(Crew):
    age_years: int
    activity_pref: str


class CrewList(BaseModel):
    items: list[Crew]


class Observation(BaseModel):
    observation_id: str
    mission_id: str
    crew_id: str | None
    subject_id: str
    scope: Scope
    timestamp_utc: str
    mission_day: int
    metric: str
    value: FiniteFloat | None
    unit: str
    activity_context: Context
    source: str
    provenance: Literal["SYNTHETIC"]
    quality: Literal["VALID", "MISSING"]
    missing_reason: str | None
    privacy: Literal["crew", "private_health", "shared_environment"]
    share_cabin_context: bool


class ObservationPage(BaseModel):
    revision: int
    cursor_utc: str
    items: list[Observation]
    next_cursor: str | None


class LatestObservations(ObservationPage):
    latest_missing: list[Observation]


class ReplayState(BaseModel):
    dataset_id: str
    revision: int
    status: Literal["PAUSED", "RUNNING", "COMPLETE"]
    cursor_utc: str
    mission_day: int
    visible_count: int
    speed: Literal[0.5, 2, 5]


class ReplayActivity(BaseModel):
    mission_day: int
    observation_count: int
    crew_count: int
    cabin_count: int
    first_utc: str | None
    last_utc: str | None


class ReplayView(ReplayState):
    historical_days: int
    mission_days: int
    latest_activity: ReplayActivity | None
    playback_error: str | None


class ReplayCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: Literal["PLAY", "PAUSE", "NEXT_DAY", "NEXT_EVENT", "RESET", "SET_SPEED"]
    expected_revision: int = Field(ge=0, strict=True)
    speed: Literal[0.5, 2, 5] | None = None

    @model_validator(mode="after")
    def check_speed(self) -> "ReplayCommand":
        if (self.command == "SET_SPEED") != (self.speed is not None):
            raise ValueError("SET_SPEED requires speed and other commands do not accept it.")
        return self


class Mission(BaseModel):
    revision: int
    cursor_utc: str
    mission_day: int
    replay_status: Literal["PAUSED", "RUNNING", "COMPLETE"]
    synthetic: Literal[True] = True
    crew_summaries: list[Crew]
    crew_readings: dict[str, Observation]
    cabin_readings: list[Observation]
    cabin_latest_missing: list[Observation]
    insights: list[str]


class Metric(BaseModel):
    metric: str
    unit: str
    description: str
    scope: Scope
    provenance: Literal["SYNTHETIC"]
    measurement_cadence: str
    is_nasa_measured: Literal[False]


class Reference(BaseModel):
    source_id: str
    organization: str
    title: str
    url: str
    use: str
    direct_raw_data_fitted: Literal["No"]


class DatasetMetadata(BaseModel):
    dataset_id: str
    version: str
    mission_type: str
    mission_days: int
    historical_days: int
    mission_start_utc: str
    provenance: Literal["SYNTHETIC"] = "SYNTHETIC"
    cabin_total_pressure_assumed_mmhg: FiniteFloat
    references: list[Reference]


class DatasetInfo(DatasetMetadata):
    initialized: Literal[True] = True
    imported_at_utc: str
    historical_count: int
    historical_missing_count: int
    source_status: SourceStatus
    replay: ReplayState
    metrics: list[Metric]
