"""Read-only personalized analysis of a single authorized replay snapshot."""

import sqlite3
from collections import defaultdict
from datetime import timedelta
from statistics import median

from astra.health_models import Coverage, CrewAnalysis, Finding, HabitatComparison, MonitoringSummary
from astra.health_statistics import (
    CABIN, CABIN_MIN_HOURS, CABIN_WINDOW_HOURS, MIN_COVERAGE, PERSON, PERSISTENT, POLICIES,
    SHARING_HOURS, UNITS, VERSION, Sample, baseline, buckets, compare, number, score, signal, utc,
)
from astra.models import DatasetMetadata, ReplayState
from astra.reads import ObservationFilters, visible_observations

EVIDENCE_LIMIT = 12
PRIORITY = {"FLAGGED": 0, "WATCH": 1, "INSUFFICIENT_DATA": 2, "STABLE": 3}
REST = "resting_heart_rate"
GROUPS = (
    (REST,), ("systolic_bp", "diastolic_bp"), ("body_temperature",), ("spo2",), ("sleep_duration",), ("fatigue",),
)
PAIR = ("systolic_bp", "diastolic_bp")


def inputs(connection, replay, *, scope, crew_id=None):
    sql, args = visible_observations(replay, ObservationFilters(crew_id=crew_id, scope=scope))
    return connection.execute(sql + " ORDER BY timestamp_utc, observation_id", args)


def compatible(row):
    policy = POLICIES.get(row["metric"])
    return policy is not None and (policy.context, policy.unit) == (row["activity_context"], row["unit"])


def split_samples(rows):
    result = defaultdict(list)
    for row in rows:
        if compatible(row):
            result[row["metric"]].append(Sample.from_row(row))
    return result


def paired_pressure(systolic, diastolic):
    if systolic is None or diastolic is None:
        return []
    if (systolic.timestamp_utc, systolic.source, systolic.context) != (
        diastolic.timestamp_utc, diastolic.source, diastolic.context,
    ):
        return []
    return [systolic, diastolic]


def evidence(samples):
    unique = {s.id: s for s in samples}
    return [s.evidence() for s in sorted(unique.values(), key=lambda s: (s.timestamp, s.id))[-EVIDENCE_LIMIT:]]


def description(metric, result, reference):
    policy = POLICIES[metric]
    unit = UNITS.get(policy.unit, policy.unit)
    text = f"{policy.label}: {result.current.value:g} {unit} versus a personal reference of {reference.median:g} {unit}."
    if result.persistent_days >= PERSISTENT:
        text += f" The deviation repeats on {result.persistent_days} recent measurement days."
    elif result.trend_direction == result.direction and result.trend_direction != "FLAT":
        text += " Recent readings also moved in that direction."
    else:
        text += " The persistence rule was not met."
    return text


def person_findings(crew_id, indicators, baselines, supporting):
    def level(metric, sign):
        result = indicators[metric]
        if result.availability != "CURRENT" or result.direction != sign:
            return 0
        return signal(result.current.value, baselines[metric], POLICIES[metric])[1]

    # More specific paired patterns take precedence over their matching single indicators.
    sleep = [metric for metric in ("sleep_duration", "sleep_quality") if level(metric, "DOWN")]
    groups = [
        ("CARDIO_THERMAL", "Resting heart rate and temperature increased", REST, "UP", ["body_temperature"], "UP", 24),
        ("CARDIO_RECOVERY", "Resting heart rate increased alongside sleep or fatigue changes", REST, "UP",
         [*sleep, "fatigue"], None, 36),
        ("SLEEP_FATIGUE", "Reduced sleep and increased reported fatigue", "fatigue", "UP", sleep, "DOWN", 36),
    ]
    result, covered = [], set()
    for rule, title, anchor, sign, candidates, other_sign, hours in groups:
        anchor_level = level(anchor, sign)
        if not anchor_level:
            continue
        aligned, elevated = [], False
        for other in candidates:
            candidate_level = level(other, other_sign or ("UP" if other == "fatigue" else "DOWN"))
            if not candidate_level:
                continue
            a, b = indicators[anchor], indicators[other]
            if abs(utc(a.current.timestamp_utc) - utc(b.current.timestamp_utc)) > timedelta(hours=hours):
                continue
            persistent = a.persistent_days >= PERSISTENT or b.persistent_days >= PERSISTENT
            if persistent or max(anchor_level, candidate_level) == 2:
                aligned.append(other)
                elevated |= persistent or min(anchor_level, candidate_level) == 2
        members = {anchor, *aligned}
        if not aligned or (rule == "SLEEP_FATIGUE" and members <= covered):
            continue
        metrics = [anchor, *aligned]
        result.append(Finding(
            rule_id=rule, type="CONTEXTUAL", crew_id=crew_id, status="FLAGGED" if elevated else "WATCH",
            title=title, explanation=" ".join(description(m, indicators[m], baselines[m]) for m in metrics),
            uncertainty=f"Current measurements occurred within {hours} hours of the anchor. Timing does not establish causation.",
            verification="Verify the readings and review their measurement and activity context.",
            evidence=evidence(s for m in metrics for s in supporting[m]),
        ))
        # Do not hide a strong single finding behind a lower priority combination.
        covered.update(m for m in members if elevated or indicators[m].status != "FLAGGED")
    for metric, item in indicators.items():
        if item.status not in ("WATCH", "FLAGGED") or metric in covered:
            continue
        policy = POLICIES[metric]
        result.append(Finding(
            rule_id="PERSONAL_DEVIATION", type="SINGLE_METRIC", crew_id=crew_id, status=item.status,
            title=f"{policy.label}: {'sustained change' if item.persistent_days >= PERSISTENT else 'verify reading'}",
            explanation=description(metric, item, baselines[metric]),
            uncertainty="This is a statistical comparison with synthetic personal history.",
            verification=f"Verify the observation in its {policy.context.replace('_', ' ')} context.",
            evidence=evidence(supporting[metric]),
        ))
    return sorted(result, key=lambda finding: (PRIORITY[finding.status], finding.type != "CONTEXTUAL"))


def person(crew_id, rows, cutoff, reference_period):
    samples = split_samples(rows)
    baselines = {m: baseline(m, samples[m], *reference_period) for m in PERSON}
    comparisons = {m: compare(samples[m], baselines[m], cutoff) for m in PERSON}
    indicators = {m: item for m, (item, _) in comparisons.items()}
    findings = person_findings(crew_id, indicators, baselines, {m: rows for m, (_, rows) in comparisons.items()})
    pair = paired_pressure(*(indicators[m].latest_valid for m in PAIR))
    current = sum(all(indicators[m].status in ("STABLE", "WATCH", "FLAGGED") for m in group)
                  and (group != PAIR or bool(pair)) for group in GROUPS)
    sufficient = current >= MIN_COVERAGE and indicators[REST].status in ("STABLE", "WATCH", "FLAGGED")
    coverage = Coverage(current_groups=current, required_groups=MIN_COVERAGE, total_groups=len(GROUPS), sufficient=sufficient)
    status = findings[0].status if findings else "STABLE" if sufficient else "INSUFFICIENT_DATA"
    if not sufficient:
        findings.append(Finding(
            rule_id="MONITORING_COVERAGE", type="DATA_QUALITY", crew_id=crew_id, status="INSUFFICIENT_DATA",
            title="Limited monitoring coverage",
            explanation=f"{current} primary indicator groups support a current comparison. At least {MIN_COVERAGE} groups, including resting heart rate, are required for a stable summary.",
            uncertainty="Missing or outdated measurements do not establish stability.",
            verification="Check which measurements are missing or stale before drawing conclusions.",
            evidence=[],
        ))
    return status, coverage, baselines, indicators, pair, findings


def authorized_reports(connection, replay, cutoff):
    """Only counts are returned. A latest valid zero or a loss of opt-in supersedes a prior report."""
    start = (cutoff - timedelta(hours=SHARING_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = 0
    for crew in connection.execute("SELECT crew_id FROM crew"):
        sql, args = visible_observations(replay, ObservationFilters(
            crew_id=crew["crew_id"], metric="headache", context="self_report", from_utc=start,
        ))
        for row in connection.execute(sql + " AND quality = 'VALID' ORDER BY timestamp_utc DESC, observation_id DESC", args):
            if compatible(row) and (value := Sample.from_row(row).value) is not None:
                count += value > 0 and bool(row["share_cabin_context"])
                break
    return count


def cabin_findings(connection, replay, cutoff, reference_period):
    samples = split_samples(inputs(connection, replay, scope="cabin"))
    findings = []
    for metric in CABIN:
        policy = POLICIES[metric]
        reference = baseline(metric, samples[metric], *reference_period)
        newest = samples[metric][-1] if samples[metric] else None
        if (reference.median is None or newest is None or newest.value is None
                or cutoff - utc(newest.timestamp) > timedelta(hours=policy.fresh)):
            continue
        recent = buckets([r for r in samples[metric] if utc(r.timestamp) > cutoff - timedelta(hours=CABIN_WINDOW_HOURS)],
                         lambda row: row.timestamp[:13])
        if len(recent) < CABIN_MIN_HOURS:
            continue
        current = median(hourly for _, hourly, _ in recent)
        _, level = signal(current, reference, policy)
        is_co2 = metric == "cabin_co2_partial_pressure"
        if level < (1 if is_co2 else 2):
            continue
        count = authorized_reports(connection, replay, cutoff) if is_co2 else 0
        unit = UNITS.get(policy.unit, policy.unit)
        text = (f"{policy.label}: the recent {CABIN_WINDOW_HOURS}-hour window median is {current:g} {unit}, "
                f"compared with a historical daily-median reference of {reference.median:g} {unit}.")
        if count >= 2:
            text += f" {count} different crew members opted in to share headache reports in the past {SHARING_HOURS} hours."
        findings.append(Finding(
            rule_id="SHARED_CO2_HEADACHE" if count >= 2 else "CABIN_REFERENCE_SHIFT",
            type="SHARED_CABIN" if count >= 2 else "CABIN", status="WATCH",
            title="Possible shared cabin contributor" if count >= 2 else f"{policy.label} differs from history",
            explanation=text,
            uncertainty="A synthetic statistical comparison, not an operational exposure limit. Coincidence does not establish causation.",
            verification="Verify recorded cabin telemetry and consult the applicable onboard environmental procedure.",
            evidence=evidence(s for _, _, rows in recent for s in rows),
            shared_report_count=count if count >= 2 else None,
            habitat_comparison=HabitatComparison(metric=metric, unit=policy.unit, window_median=current,
                                                historical_median=reference.median, effective_mad=reference.effective_mad,
                                                modified_z=number(score(current, reference)), window_hours=CABIN_WINDOW_HOURS,
                                                valid_hours=len(recent)),
        ))
    return sorted(findings, key=lambda item: item.type != "SHARED_CABIN")


class HealthSnapshot:
    def __init__(self, connection: sqlite3.Connection, replay: ReplayState):
        self.connection, self.replay = connection, replay
        row = connection.execute("SELECT metadata_json FROM datasets WHERE dataset_id = ?", (replay.dataset_id,)).fetchone()
        meta = DatasetMetadata.model_validate_json(row["metadata_json"])
        end = utc(meta.mission_start_utc) + timedelta(days=meta.historical_days, seconds=-1)
        self.cutoff = utc(replay.cursor_utc)
        self.period = (meta.mission_start_utc, end.strftime("%Y-%m-%dT%H:%M:%SZ"), meta.historical_days)
        self.cabin = cabin_findings(connection, replay, self.cutoff, self.period)

    def subject(self, crew_id, metric=None, context=None):
        status, coverage, baselines, indicators, pair, findings = person(
            crew_id, inputs(self.connection, self.replay, scope="person", crew_id=crew_id), self.cutoff, self.period,
        )
        keys = [m for m, r in baselines.items() if (metric is None or metric == m) and (context is None or context == r.context)]
        details = findings if metric is None and context is None else [
            f for f in findings if any(e.metric in keys for e in f.evidence)
        ]
        return CrewAnalysis(crew_id=crew_id, revision=self.replay.revision, cursor_utc=self.replay.cursor_utc,
                            method_version=VERSION, status=status, coverage=coverage,
                            baselines=[baselines[m] for m in keys], indicators=[indicators[m] for m in keys],
                            blood_pressure=pair, findings=details, cabin_findings=self.cabin)

    def mission(self, crew_ids):
        grouped = defaultdict(list)
        for row in inputs(self.connection, self.replay, scope="person"):
            grouped[row["crew_id"]].append(row)
        summaries, public_findings = {}, []
        for crew_id in crew_ids:
            status, coverage, _, _, _, findings = person(crew_id, grouped[crew_id], self.cutoff, self.period)
            concerns = [f for f in findings if f.type != "DATA_QUALITY"]
            headline = (concerns[0].title if concerns else "No detected deviation in monitored indicators."
                        if status == "STABLE" else "Not enough shared data for a current comparison.")
            summaries[crew_id] = MonitoringSummary(status=status, coverage=coverage, headline=headline)
            public_findings.extend(concerns[:1])
        return summaries, sorted(public_findings, key=lambda f: PRIORITY[f.status])
