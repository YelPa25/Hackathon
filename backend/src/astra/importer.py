"""Stage 02 ingest. This module opens only the historical partition and its metadata."""

import csv
import hashlib
import io
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from astra.db import connect_database
from astra.models import CrewProfile, DatasetMetadata, Metric, Observation, Reference, parse_utc

HISTORY = "replay_history_DAY01_to_DAY45.csv"
INPUTS = ("dataset_manifest.json", "crew_profiles.csv", "metric_dictionary.csv", "scientific_sources.csv", HISTORY)
HISTORICAL_COUNT = 6252
MISSING_COUNT = 18
CREW_IDS = {f"AST-{index:03}" for index in range(1, 5)}
CONTEXTS = {
    "resting_heart_rate": "rest",
    "exercise_heart_rate": "exercise",
    "recovery_heart_rate": "recovery",
    "sleep_duration": "sleep",
    "sleep_quality": "self_report",
    "fatigue": "self_report",
    "mood": "self_report",
    "perceived_stress": "self_report",
    "headache": "self_report",
    "systolic_bp": "rest",
    "diastolic_bp": "rest",
    "body_temperature": "rest",
    "spo2": "rest",
    "exercise_duration": "exercise",
    "cabin_co2_partial_pressure": "unspecified",
    "cabin_co2_concentration": "unspecified",
    "cabin_temperature": "unspecified",
    "cabin_relative_humidity": "unspecified",
}
OBSERVATION_FIELDS = tuple(Observation.model_fields)


class DatasetError(ValueError):
    """The source bundle cannot be safely installed."""


def verified_inputs(directory: Path) -> tuple[dict[str, bytes], dict[str, str]]:
    listed = {}
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]) or parts[1] in listed:
            raise DatasetError("Malformed checksum list")
        listed[parts[1]] = parts[0]
    inputs = {}
    hashes = {}
    for name in INPUTS:
        try:
            data = (directory / name).read_bytes()
        except FileNotFoundError as exc:
            raise DatasetError(f"Missing required input: {name}") from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest != listed.get(name):
            raise DatasetError(f"SHA-256 mismatch for {name}")
        inputs[name] = data
        hashes[name] = digest
    return inputs, hashes


def csv_rows(data: bytes, fields: tuple[str, ...], filename: str):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    if tuple(reader.fieldnames or ()) != fields:
        raise DatasetError(f"Unexpected header: {filename}")
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise DatasetError(f"Unexpected column count: {filename}:{reader.line_num}")
        yield row


def load_metadata(inputs: dict[str, bytes]) -> DatasetMetadata:
    manifest = json.loads(inputs["dataset_manifest.json"])
    if not isinstance(manifest, dict):
        raise DatasetError("Invalid manifest object")
    expected = {
        "dataset_id": "ASTRA-SYN-90D-01",
        "generator_version": "1.0.0",
        "mission_type": "FICTIONAL_90_DAY_TRANSIT",
        "mission_start_utc": "2040-01-01T00:00:00Z",
        "days": 90, "historical_days": 45, "replay_days": 45, "crew_count": 4,
    }
    if (any(manifest.get(key) != value for key, value in expected.items())
            or manifest.get("all_records_are_synthetic") is not True
            or manifest.get("no_real_astronaut_medical_records") is not True
            or manifest.get("observation_quality_values") != ["VALID", "MISSING"]
            or manifest.get("provenance_values") != ["SYNTHETIC"]):
        raise DatasetError("Unsupported dataset manifest")
    policy = manifest.get("replay_policy")
    if not isinstance(policy, dict) or policy.get("start_day") != 45 or policy.get("historical_file") != HISTORY:
        raise DatasetError("Unexpected history partition")
    references = []
    for row in csv_rows(inputs["scientific_sources.csv"], tuple(Reference.model_fields), "scientific_sources.csv"):
        url = urlsplit(row["url"])
        if (not all(row.values()) or url.scheme != "https" or url.username or url.password
                or url.hostname not in {"www.nasa.gov", "ntrs.nasa.gov", "wwwn.cdc.gov"}):
            raise DatasetError("Invalid source catalog entry")
        references.append(Reference.model_validate(row))
    if (len({ref.source_id for ref in references}) != 4 or len(references) != 4
            or [ref.model_dump() for ref in references] != manifest.get("references")):
        raise DatasetError("Reference catalog differs from the manifest")
    pressure = manifest.get("cabin_total_pressure_assumed_mmhg")
    if pressure != 760.0:
        raise DatasetError("Unexpected assumed cabin pressure")
    return DatasetMetadata(
        dataset_id=manifest["dataset_id"], version=manifest["generator_version"], mission_type=manifest["mission_type"],
        mission_days=manifest["days"], historical_days=manifest["historical_days"],
        mission_start_utc=manifest["mission_start_utc"], cabin_total_pressure_assumed_mmhg=pressure,
        references=references,
    )


def load_crew(data: bytes) -> list[CrewProfile]:
    columns = ("crew_id", "display_name", "role", "age_years", "rest_hr_ref_bpm", "sys_ref_mmhg",
               "dia_ref_mmhg", "sleep_tendency_h", "activity_pref", "baseline_stress")
    crew = []
    for row in csv_rows(data, columns, "crew_profiles.csv"):
        profile = CrewProfile.model_validate({key: row[key] for key in CrewProfile.model_fields})
        if not profile.display_name.strip() or not profile.role.strip() or not profile.activity_pref.strip() or profile.age_years <= 0:
            raise DatasetError("Invalid crew profile")
        crew.append(profile)
    if len(crew) != 4 or {profile.crew_id for profile in crew} != CREW_IDS:
        raise DatasetError("Expected four unique crew profiles")
    return crew


def load_metrics(data: bytes) -> dict[str, Metric]:
    columns = ("metric", "unit", "description", "provenance", "measurement_cadence", "is_nasa_measured")
    metrics = {}
    for row in csv_rows(data, columns, "metric_dictionary.csv"):
        key = row["metric"]
        if (not all(row.values()) or key not in CONTEXTS or key in metrics
                or row["is_nasa_measured"] != "NO"):
            raise DatasetError("Invalid metric dictionary entry")
        scope = "cabin" if key.startswith("cabin_") else "person"
        metrics[key] = Metric.model_validate({**row, "scope": scope, "is_nasa_measured": False})
    if metrics.keys() != CONTEXTS.keys():
        raise DatasetError("Metric dictionary has incomplete coverage")
    return metrics


def load_history(data: bytes, metadata: DatasetMetadata, metrics: dict[str, Metric]) -> list[tuple]:
    start = parse_utc(metadata.mission_start_utc)
    previous = start
    observed_ids = set()
    records = []
    missing_count = 0
    for row in csv_rows(data, (*OBSERVATION_FIELDS, "note"), HISTORY):
        observation_id = row["observation_id"]
        metric = metrics.get(row["metric"])
        if (not re.fullmatch(r"SIM-[0-9]+", observation_id) or observation_id in observed_ids
                or row["mission_id"] != metadata.dataset_id or not row["source"].strip()
                or metric is None or (row["unit"], row["scope"]) != (metric.unit, metric.scope)
                or row["activity_context"] != CONTEXTS[metric.metric]):
            raise DatasetError(f"Invalid observation identity or metric: {observation_id}")
        timestamp = parse_utc(row["timestamp_utc"])
        day = (timestamp.date() - start.date()).days + 1
        if timestamp < previous or not 1 <= day <= metadata.historical_days or row["mission_day"] != str(day):
            raise DatasetError(f"Unexpected timestamp or mission day: {observation_id}")
        cabin = metric.scope == "cabin"
        if (cabin and (row["crew_id"], row["subject_id"], row["privacy"]) != ("", "CABIN-01", "shared_environment")
                or not cabin and (row["crew_id"] not in CREW_IDS or row["subject_id"] != row["crew_id"]
                                 or row["privacy"] != ("private_health" if row["activity_context"] in {"sleep", "self_report"} else "crew"))):
            raise DatasetError(f"Invalid observation subject or privacy: {observation_id}")
        sharing = row["share_cabin_context"]
        if sharing not in {"true", "false"} or sharing == "true" and (
            metric.metric != "headache" or row["quality"] != "VALID"
        ):
            raise DatasetError(f"Invalid cabin sharing flag: {observation_id}")
        raw = row["value"]
        reason = row["missing_reason"]
        if row["quality"] == "MISSING":
            if raw or not reason.strip():
                raise DatasetError(f"Invalid missing reading: {observation_id}")
            missing_count += 1
        else:
            if row["quality"] != "VALID" or reason or not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", raw):
                raise DatasetError(f"Invalid numeric reading: {observation_id}")
            value = Decimal(raw)
            if (metric.unit == "score_0_4" and not (0 <= value <= 4 and value == value.to_integral_value())
                    or metric.unit == "percent" and not 0 <= value <= 100):
                raise DatasetError(f"Reading outside representation constraints: {observation_id}")
            # Preserve the source decimal text in SQLite, with numeric values in the JSON contract.
        observation = Observation.model_validate({
            **row, "value": raw or None, "crew_id": row["crew_id"] or None,
            "missing_reason": reason or None, "share_cabin_context": sharing == "true",
        })
        payload = observation.model_dump()
        payload["value"] = raw or None
        records.append(tuple(payload[field] for field in OBSERVATION_FIELDS))
        observed_ids.add(observation_id)
        previous = timestamp
    if len(records) != HISTORICAL_COUNT or missing_count != MISSING_COUNT:
        raise DatasetError("Unexpected historical or missing row count")
    return records


def install_history(path: Path, directory: Path) -> str:
    inputs, hashes = verified_inputs(directory)
    metadata = load_metadata(inputs)
    hashes_json = json.dumps(hashes, sort_keys=True)
    with closing(connect_database(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT dataset_id, input_hashes_json FROM datasets").fetchall()
        if previous:
            if [tuple(row) for row in previous] != [(metadata.dataset_id, hashes_json)]:
                raise DatasetError("Installed dataset inputs have changed")
            return "already present"

        crew = load_crew(inputs["crew_profiles.csv"])
        metrics = load_metrics(inputs["metric_dictionary.csv"])
        records = load_history(inputs[HISTORY], metadata, metrics)
        cutoff = parse_utc(metadata.mission_start_utc) + timedelta(days=metadata.historical_days, seconds=-1)
        imported = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        connection.execute(
            "INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?)",
            (metadata.dataset_id, metadata.model_dump_json(), hashes_json, imported, len(records), MISSING_COUNT),
        )
        connection.executemany(
            "INSERT INTO crew VALUES (:crew_id, :display_name, :role, :age_years, :activity_pref)",
            [profile.model_dump() for profile in crew],
        )
        connection.executemany(
            """INSERT INTO metrics (metric, unit, description, scope, provenance, measurement_cadence, is_nasa_measured)
                VALUES (:metric, :unit, :description, :scope, :provenance, :measurement_cadence, :is_nasa_measured)""",
            [metric.model_dump() for metric in metrics.values()],
        )
        fields = ", ".join(OBSERVATION_FIELDS)
        placeholders = ", ".join("?" for _ in OBSERVATION_FIELDS)
        connection.executemany(f"INSERT INTO observations ({fields}) VALUES ({placeholders})", records)
        connection.execute(
            "INSERT INTO replay_state VALUES (1, ?, 0, 'PAUSED', ?, ?, ?)",
            (metadata.dataset_id, cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"), metadata.historical_days, len(records)),
        )
    return "imported"
