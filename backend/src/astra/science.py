"""Read-only, shareable inputs for the Data & Science comparison."""

from collections import defaultdict
from datetime import timedelta
from sqlite3 import Connection
from typing import Literal

from pydantic import BaseModel, FiniteFloat

from astra.health_engine import REST, compatible
from astra.health_statistics import POLICIES, VERSION, Sample, baseline, number, score, signal, utc
from astra.models import DatasetMetadata, ReplayState
from astra.reads import ObservationFilters, visible_observations


class RestingComparison(BaseModel):
    crew_id: str
    display_name: str
    median_bpm: FiniteFloat | None
    mad_bpm: FiniteFloat | None
    effective_mad_bpm: FiniteFloat | None
    distinct_days: int
    absolute_difference_bpm: FiniteFloat | None = None
    modified_z: FiniteFloat | None = None
    strength: Literal["below_moderate", "moderate", "strong"] | None = None


class PersonalizationDemo(BaseModel):
    dataset_id: str
    method_version: str = VERSION
    hypothetical_bpm: int
    comparisons: list[RestingComparison]


def compare_hypothetical_resting_hr(
    connection: Connection, replay: ReplayState, bpm: int,
) -> PersonalizationDemo:
    stored = connection.execute(
        "SELECT metadata_json FROM datasets WHERE dataset_id = ?", (replay.dataset_id,),
    ).fetchone()
    dataset = DatasetMetadata.model_validate_json(stored["metadata_json"])
    start = dataset.mission_start_utc
    end = utc(start) + timedelta(days=dataset.historical_days, seconds=-1)
    end_utc = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    sql, args = visible_observations(
        replay, ObservationFilters(scope="person", metric=REST, context="rest", from_utc=start, to_utc=end_utc),
    )
    samples: dict[str, list[Sample]] = defaultdict(list)
    for row in connection.execute(sql + " ORDER BY timestamp_utc, observation_id", args):
        if compatible(row):
            samples[row["crew_id"]].append(Sample.from_row(row))

    comparisons = []
    for member in connection.execute("SELECT crew_id, display_name FROM crew ORDER BY crew_id"):
        reference = baseline(REST, samples[member["crew_id"]], start, end_utc, dataset.historical_days)
        comparison = RestingComparison(
            crew_id=member["crew_id"], display_name=member["display_name"], median_bpm=reference.median,
            mad_bpm=reference.mad, effective_mad_bpm=reference.effective_mad, distinct_days=reference.distinct_days,
        )
        z = score(bpm, reference)
        if z is not None and reference.median is not None:
            _, severity = signal(bpm, reference, POLICIES[REST])
            comparison.absolute_difference_bpm = number(abs(bpm - reference.median))
            comparison.modified_z = number(z)
            comparison.strength = ("below_moderate", "moderate", "strong")[severity]
        comparisons.append(comparison)

    return PersonalizationDemo(dataset_id=replay.dataset_id, hypothetical_bpm=bpm, comparisons=comparisons)
