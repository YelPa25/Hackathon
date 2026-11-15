from datetime import timedelta
from statistics import median

import pytest

from astra.health_engine import paired_pressure, person
from astra.health_statistics import POLICIES, Sample, baseline, compare, score, signal, utc

START = "2040-01-01T00:00:00Z"
END = "2040-02-14T23:59:59Z"
CUTOFF = utc("2040-02-19T20:00:00Z")
REST = "resting_heart_rate"


def row(metric, day, value, *, hour=8, context=None, observation_id=None, source="fixture"):
    policy = POLICIES[metric]
    return {
        "observation_id": observation_id or f"{metric}/{day}/{hour}", "mission_day": day, "metric": metric,
        "timestamp_utc": (utc(START) + timedelta(days=day - 1, hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "unit": policy.unit, "activity_context": context or policy.context, "value": value, "source": source,
        "quality": "MISSING" if value is None else "VALID",
    }


def analyze(metric, values, recent=(), *, cutoff=CUTOFF):
    hist = [Sample.from_row(row(metric, day + 1, value)) for day, value in enumerate(values)]
    samples = hist + [Sample.from_row(row(metric, day, value)) for day, value in recent]
    ref = baseline(metric, samples, START, END, 45)
    return ref, compare(samples, ref, cutoff)[0]


def test_median_mad_and_score_are_exact():
    values = [60, 60, 61, 63, 64, 66, 67, 68, 70, 72, 90]
    ref, result = analyze(REST, values, [(50, "96.00")])
    assert ref.median == median(values) == 66
    assert ref.mad == ref.effective_mad == 4
    assert result.difference == result.absolute_difference == 30
    assert result.modified_z == pytest.approx(0.6745 * 30 / 4)
    assert result.relative_percent == pytest.approx(100 * 30 / 66)
    assert result.current.value == 96
    assert result.direction == "UP" and result.status == "WATCH"


def test_zero_mad_uses_floor_and_respects_threshold_boundaries():
    ref, item = analyze(REST, [60] * 10, [(50, 61)])
    assert ref.mad == 0 and ref.effective_mad == 2 and item.status == "STABLE"
    exact = ref.model_copy(update={"median": 0, "effective_mad": .6745})
    assert signal(1.999, exact, POLICIES[REST]) == ("UP", 0)
    assert signal(2, exact, POLICIES[REST]) == ("UP", 1)
    assert signal(-3.5, exact, POLICIES[REST]) == ("DOWN", 2)
    assert score(3.5, exact) == 3.5


def test_reference_counts_days_instead_of_dense_samples_and_never_recalibrates():
    rows = [Sample.from_row(row(REST, 1, 60, hour=i)) for i in range(24)]
    rows.extend(Sample.from_row(row(REST, 46, 150, hour=i)) for i in range(24))
    ref = baseline(REST, rows, START, END, 45)
    assert ref.valid_sample_count == 24 and ref.distinct_days == 1
    assert ref.availability == "INSUFFICIENT_DATA" and ref.median is None
    assert compare(rows, ref, CUTOFF)[0].status == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("bad", ["", "NaN", "Infinity", "1e9", True, float("inf"), float("nan"), 10 ** 350])
def test_invalid_values_cannot_become_numeric_evidence(bad):
    sample = Sample.from_row(row(REST, 45, bad))
    assert sample.value is None and sample.quality == "MISSING"


def test_freshness_and_missing_are_not_stability():
    _, missing = analyze(REST, [70] * 10, [(49, 95), (50, None)])
    assert missing.availability == "MISSING" and missing.current.value is None
    assert missing.latest_valid.value == 95 and missing.modified_z is None
    assert missing.status == "INSUFFICIENT_DATA"
    _, stale = analyze(REST, [60] * 10, [(47, 100)])
    assert stale.availability == "STALE" and stale.status == "INSUFFICIENT_DATA" and stale.persistent_days == 0


def test_persistence_excludes_missing_days_and_one_strong_reading_is_only_watch():
    _, isolated = analyze(REST, [70] * 10, [(50, 54)])
    assert (isolated.status, isolated.direction) == ("WATCH", "DOWN")
    _, sustained = analyze(REST, [70] * 10, [(45, 55), (47, 57), (48, None), (50, 58)])
    assert (sustained.status, sustained.strong_days, sustained.persistent_days) == ("FLAGGED", 3, 3)
    assert sustained.rolling_median == 57
    _, old = analyze(REST, [70] * 10, [(40, 55), (41, 55), (50, 58)])
    assert (old.status, old.persistent_days) == ("WATCH", 1)


def test_slopes_use_elapsed_sample_time_and_ignore_tiny_movements():
    _, result = analyze("body_temperature", [36.6] * 10, [(43, 36.6), (45, 36.8), (50, 37.3)])
    assert result.slope_per_day == pytest.approx(.1) and result.trend_direction == "UP"
    _, small = analyze("body_temperature", [36.6] * 10, [(43, 36.6), (45, 36.62), (50, 36.67)])
    assert small.slope_per_day == pytest.approx(.01) and small.trend_direction == "FLAT"


def test_directions_use_original_ordinal_scale_and_oxygen_direction():
    ref, item = analyze("fatigue", [0, 1] * 5, [(50, 2)])
    assert ref.median == 0 and ref.mad is None and item.modified_z is None
    assert item.status == "WATCH" and item.difference == 2 and item.relative_percent is None
    assert analyze("sleep_quality", [2] * 10, [(50, 4)])[1].status == "STABLE"
    assert analyze("sleep_quality", [2] * 10, [(50, 0)])[1].status == "WATCH"
    assert analyze("spo2", [92] * 10, [(50, 99)])[1].status == "STABLE"
    assert analyze("spo2", [99] * 10, [(50, 91)])[1].status == "WATCH"
    assert Sample.from_row(row("fatigue", 50, 4.2)).value is None
    assert Sample.from_row(row("headache", 50, 0)).value == 0


def profile(recent, references=None):
    refs = references or {REST: 65, "sleep_duration": 8, "fatigue": 1, "body_temperature": 36.7,
                          "spo2": 98, "exercise_heart_rate": 130, "recovery_heart_rate": 90}
    rows = [row(m, d, v) for m, v in refs.items() for d in range(1, 11)] + recent
    rows.sort(key=lambda item: (item["timestamp_utc"], item["observation_id"]))
    return person("unit-test", rows, CUTOFF, (START, END, 45))


def test_contexts_and_subject_specific_reference():
    _, _, bases, indicators, _, _ = profile([row(REST, 50, 150, context="exercise"),
                                             row("exercise_heart_rate", 50, 150),
                                             row("recovery_heart_rate", 50, 90), row(REST, 49, 65)])
    assert [bases[m].median for m in (REST, "exercise_heart_rate", "recovery_heart_rate")] == [65, 130, 90]
    assert indicators[REST].current.value == 65
    assert profile([], {REST: 73})[2][REST].median == 73


def test_blood_pressure_requires_same_source_time_and_context():
    s = Sample.from_row(row("systolic_bp", 50, 116)).evidence()
    d = Sample.from_row(row("diastolic_bp", 50, 73)).evidence()
    assert paired_pressure(s, d) == [s, d]
    assert paired_pressure(s, d.model_copy(update={"source": "another cuff"})) == []
    assert paired_pressure(s, d.model_copy(update={"timestamp_utc": "2040-02-19T08:01:00Z"})) == []
    assert paired_pressure(s, d.model_copy(update={"context": "recovery"})) == []


def test_stability_requires_coverage_while_concerns_survive_missing_data():
    assert profile([])[0] == "INSUFFICIENT_DATA"
    assert profile([row(REST, 50, 65), row("spo2", 50, 98), row("body_temperature", 50, 36.7)])[0] == "STABLE"
    status, coverage, _, _, _, findings = profile([row(REST, 50, 80)])
    assert status == "WATCH" and not coverage.sufficient and findings[-1].type == "DATA_QUALITY"
    assert "80 bpm" in findings[0].explanation and "65 bpm" in findings[0].explanation


def test_context_rules_require_real_aligned_signals_and_deduplicate():
    sleep, fatigue, hr, temp = row("sleep_duration", 50, 5), row("fatigue", 50, 4), row(REST, 50, 85), row("body_temperature", 50, 37.5)
    isolated = profile([sleep])[-1]
    assert not any(f.type == "CONTEXTUAL" for f in isolated)
    assert "fatigue" not in isolated[0].explanation.lower()
    sleep_fatigue = profile([sleep, fatigue])[-1]
    assert sleep_fatigue[0].rule_id == "SLEEP_FATIGUE" and sleep_fatigue[0].status == "FLAGGED"
    assert {e.metric for e in sleep_fatigue[0].evidence} == {"sleep_duration", "fatigue"}
    combined = profile([sleep, fatigue, hr, temp])[-1]
    assert {f.rule_id for f in combined if f.type != "DATA_QUALITY"} == {"CARDIO_RECOVERY", "CARDIO_THERMAL"}
    early = dict(temp, timestamp_utc="2040-02-17T08:00:00Z")
    assert not any(f.rule_id == "CARDIO_THERMAL" for f in profile([hr, early])[-1])
