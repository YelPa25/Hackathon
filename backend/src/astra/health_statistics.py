"""Fixed historical references and cadence-aware statistics. No storage access."""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from statistics import median, median_low
from typing import Literal

from astra.health_models import Baseline, Comparison, Direction, Evidence

VERSION = "astra-native-v1"
MIN_DAYS = 10
MODERATE = 2.0
STRONG = 3.5
PERSISTENT = 3
RECENT_DAYS = 5
MIN_COVERAGE = 3
CABIN_WINDOW_HOURS = 6
CABIN_MIN_HOURS = 4
SHARING_HOURS = 36

Kind = Literal["continuous", "ordinal", "context_only"]


@dataclass(frozen=True)
class Policy:
    unit: str
    context: str
    label: str
    fresh: int
    window: int
    floor: float = 0
    direction: str = "both"
    kind: Kind = "continuous"


POLICIES = {
    "resting_heart_rate": Policy("bpm", "rest", "Resting heart rate", 48, 7, 2),
    "exercise_heart_rate": Policy("bpm", "exercise", "Exercise heart rate", 72, 14, 5),
    "recovery_heart_rate": Policy("bpm", "recovery", "Recovery heart rate", 72, 14, 3),
    "systolic_bp": Policy("mmHg", "rest", "Systolic blood pressure", 120, 14, 3),
    "diastolic_bp": Policy("mmHg", "rest", "Diastolic blood pressure", 120, 14, 3),
    "body_temperature": Policy("degC", "rest", "Body temperature", 120, 14, .12),
    "spo2": Policy("percent", "rest", "Oxygen saturation", 144, 21, 1, "DOWN"),
    "sleep_duration": Policy("h", "sleep", "Sleep duration", 48, 7, .5, "DOWN"),
    "sleep_quality": Policy("score_0_4", "self_report", "Reported sleep quality", 48, 7, direction="DOWN", kind="ordinal"),
    "fatigue": Policy("score_0_4", "self_report", "Reported fatigue", 48, 7, direction="UP", kind="ordinal"),
    "mood": Policy("score_0_4", "self_report", "Reported mood", 48, 7, direction="DOWN", kind="ordinal"),
    "perceived_stress": Policy("score_0_4", "self_report", "Reported stress", 48, 7, direction="UP", kind="ordinal"),
    "headache": Policy("score_0_4", "self_report", "Reported headache", 48, 7, kind="context_only"),
    "exercise_duration": Policy("min", "exercise", "Exercise duration", 72, 14, kind="context_only"),
    "cabin_temperature": Policy("degC", "unspecified", "Cabin temperature", 3, 1, .2),
    "cabin_relative_humidity": Policy("percent", "unspecified", "Cabin humidity", 3, 1, 1),
    "cabin_co2_partial_pressure": Policy("mmHg", "unspecified", "Cabin CO₂ partial pressure", 3, 1, .1, "UP"),
    "cabin_co2_concentration": Policy("ppm", "unspecified", "Derived cabin CO₂ concentration", 3, 1, kind="context_only"),
}
CABIN = tuple(metric for metric in POLICIES if metric.startswith("cabin_"))
PERSON = tuple(metric for metric in POLICIES if metric not in CABIN)
UNITS = {"score_0_4": "out of 4", "percent": "%", "degC": "°C"}


def utc(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp)


@dataclass(frozen=True)
class Sample:
    id: str
    metric: str
    timestamp: str
    day: int
    unit: str
    context: str
    value: float | None
    source: str
    quality: str

    @classmethod
    def from_row(cls, row):
        value = row["value"]
        policy = POLICIES[row["metric"]]
        if isinstance(value, str) and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
            value = float(value)
        # This representation guard keeps arithmetic finite even if storage is malformed.
        valid = row["quality"] == "VALID" and type(value) in (float, int) and abs(value) <= 1e100 and isfinite(value)
        if policy.unit == "percent":
            valid = valid and 0 <= value <= 100
        if policy.unit == "score_0_4":
            valid = valid and 0 <= value <= 4 and int(value) == value
        return cls(row["observation_id"], row["metric"], row["timestamp_utc"], row["mission_day"],
                   row["unit"], row["activity_context"], value if valid else None, row["source"],
                   "VALID" if valid else "MISSING")

    def evidence(self) -> Evidence:
        return Evidence(observation_id=self.id, metric=self.metric, timestamp_utc=self.timestamp,
                        value=self.value, unit=self.unit, source=self.source, context=self.context, quality=self.quality)


def direction(delta: float) -> Direction:
    return "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT"


def number(value: float) -> float:
    return round(value, 6)


def buckets(samples: list[Sample], key, *, ordinal=False):
    groups = defaultdict(list)
    for row in samples:
        if row.value is not None:
            groups[key(row)].append(row)
    aggregate = median_low if ordinal else median
    return [(utc(rows[-1].timestamp), aggregate(row.value for row in rows), rows)
            for _, rows in sorted(groups.items())]


def baseline(metric: str, samples: list[Sample], start: str, end: str, historical_days: int) -> Baseline:
    policy = POLICIES[metric]
    days = buckets([row for row in samples if start <= row.timestamp <= end and 1 <= row.day <= historical_days],
                   lambda row: row.timestamp[:10], ordinal=policy.kind == "ordinal")
    values = [value for _, value, _ in days]
    state = "NOT_APPLICABLE" if policy.kind == "context_only" else (
        "AVAILABLE" if len(values) >= MIN_DAYS else "INSUFFICIENT_DATA")
    center = (median_low if policy.kind == "ordinal" else median)(values) if state == "AVAILABLE" else None
    mad = median(abs(value - center) for value in values) if center is not None and policy.kind == "continuous" else None
    return Baseline(metric=metric, context=policy.context, unit=policy.unit, kind=policy.kind,
                    availability=state, median=center, mad=mad, effective_mad=max(mad, policy.floor) if mad is not None else None,
                    valid_sample_count=sum(len(rows) for _, _, rows in days), distinct_days=len(days),
                    required_days=MIN_DAYS, calibration_start_utc=start, calibration_end_utc=end)


def score(value: float, reference: Baseline) -> float | None:
    if reference.median is None or reference.effective_mad is None:
        return None
    return 0.6745 * (value - reference.median) / reference.effective_mad


def signal(value: float, reference: Baseline, policy: Policy) -> tuple[Direction, int]:
    if reference.median is None:
        return "FLAT", 0
    delta = value - reference.median
    sign = direction(delta)
    if policy.direction not in ("both", sign):
        return sign, 0
    z = score(value, reference)
    magnitude = abs(z) if z is not None else abs(delta)
    moderate, strong = (MODERATE, STRONG) if z is not None else (1, 2)
    return sign, 2 if magnitude >= strong else 1 if magnitude >= moderate else 0


def recent_trend(points, reference: Baseline, policy: Policy) -> tuple[float | None, Direction | None]:
    if reference.median is None or len(points) < 3:
        return None, None
    if policy.kind == "ordinal":
        change = median_low(p[1] for p in points[-3:]) - median_low(p[1] for p in points[:3])
        return None, direction(change)
    x = [(p[0] - points[0][0]).total_seconds() / 86400 for p in points]
    y = [p[1] for p in points]
    x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
    denominator = sum((v - x_mean) ** 2 for v in x)
    if denominator <= 0:
        return None, None
    slope = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True)) / denominator
    meaningful = abs(slope * x[-1]) >= 2 * reference.effective_mad
    return number(slope), direction(slope) if meaningful else "FLAT"


def compare(samples: list[Sample], reference: Baseline, cutoff: datetime):
    policy = POLICIES[reference.metric]
    newest = samples[-1] if samples else None
    valid = next((row for row in reversed(samples) if row.value is not None), None)
    age = (cutoff - utc(valid.timestamp)).total_seconds() / 3600 if valid else None
    availability = ("UNAVAILABLE" if newest is None else "MISSING" if newest.value is None else
                    "STALE" if age > policy.fresh else "CURRENT")
    recent = buckets([r for r in samples if utc(r.timestamp) >= cutoff - timedelta(days=policy.window)],
                     lambda row: row.timestamp[:10], ordinal=policy.kind == "ordinal")
    slope, trend = recent_trend(recent, reference, policy)
    rolling = (median_low if policy.kind == "ordinal" else median)(p[1] for p in recent[-3:]) if len(recent) >= 3 else None
    result = Comparison(metric=reference.metric, context=policy.context, current=newest.evidence() if newest else None,
                        latest_valid=valid.evidence() if valid else None, availability=availability,
                        age_hours=number(age) if age is not None else None, freshness_hours=policy.fresh,
                        rolling_median=rolling, trend_direction=trend, slope_per_day=slope,
                        trend_window_days=policy.window, recent_days=len(recent), unusual_ids=[])
    if policy.kind == "context_only":
        return result, []
    result.status = "INSUFFICIENT_DATA"
    if reference.median is None:
        return result, []
    # Chart markers use source observations, never daily aggregates or invented samples.
    if policy.kind == "continuous":
        result.unusual_ids = [r.id for r in samples if r.value is not None
                              and utc(r.timestamp) >= cutoff - timedelta(days=45)
                              and signal(r.value, reference, policy)[1] >= 2]
    if availability != "CURRENT":
        return result, []
    value = valid.value
    delta = value - reference.median
    sign, level = signal(value, reference, policy)
    result.difference = number(delta)
    result.absolute_difference = number(abs(delta))
    if reference.metric in ("resting_heart_rate", "exercise_heart_rate", "recovery_heart_rate",
                            "systolic_bp", "diastolic_bp", "sleep_duration") and reference.median > 0:
        result.relative_percent = number(100 * delta / reference.median)
    z = score(value, reference)
    result.modified_z = number(z) if z is not None else None
    result.direction = sign
    evidence = [valid]
    if level:
        for _, daily, rows in recent[-RECENT_DAYS:]:
            day_sign, day_level = signal(daily, reference, policy)
            if day_sign == sign and day_level:
                result.persistent_days += 1
                result.strong_days += day_level == 2
                evidence.extend(rows)
    result.status = (
        "FLAGGED" if result.strong_days >= PERSISTENT else
        "WATCH" if level == 2 or result.persistent_days >= PERSISTENT or (level == 1 and trend == sign) else "STABLE"
    )
    return result, evidence
