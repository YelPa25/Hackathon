import csv
import hashlib
import shutil
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from astra.config import Settings, default_dataset_dir
from astra.db import initialize_database
from astra.importer import HISTORY, INPUTS
from astra.main import create_app

CUTOFF = "2040-02-14T23:59:59Z"
DAY46 = "2040-02-15T00:00:00Z"


@pytest.fixture
def source_dir():
    return default_dataset_dir()


@pytest.fixture
def settings(tmp_path, source_dir):
    return Settings(environment="test", database_path=tmp_path / "astra.sqlite3", dataset_dir=source_dir)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def csv_source(directory, name):
    with (directory / name).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def copy_runtime_inputs(source, destination):
    destination.mkdir()
    for name in (*INPUTS, "SHA256SUMS.txt"):
        shutil.copyfile(source / name, destination / name)
    return destination


def repin_checksum(directory, name):
    checksums = directory / "SHA256SUMS.txt"
    digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
    lines = checksums.read_text().splitlines()
    checksums.write_text("\n".join(
        f"{digest}  {name}" if line.split(maxsplit=1)[1] == name else line for line in lines
    ) + "\n")


def test_import_matches_every_source_record_and_profile(client, settings, source_dir):
    source = {row["observation_id"]: row for row in csv_source(source_dir, HISTORY)}
    profiles = csv_source(source_dir, "crew_profiles.csv")
    assert client.get("/api/crew").json() == {"items": [
        {key: row[key] for key in ("crew_id", "display_name", "role")} for row in profiles
    ]}
    for profile in profiles:
        assert client.get(f"/api/crew/{profile['crew_id']}").json() == {
            **{key: profile[key] for key in ("crew_id", "display_name", "role", "activity_pref")},
            "age_years": int(profile["age_years"]),
        }
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute("SELECT ALL * FROM observations")]
    assert len(rows) == len(source) == 6252
    for row in rows:
        expected = source[row["observation_id"]].copy()
        expected.pop("note")
        for key in ("value", "crew_id", "missing_reason"):
            expected[key] = expected[key] or None
        expected["mission_day"] = int(expected["mission_day"])
        expected["share_cabin_context"] = int(expected["share_cabin_context"] == "true")
        assert row == expected
    assert sum(row["value"] is None and row["quality"] == "MISSING" for row in rows) == 18
    assert max(row["timestamp_utc"] for row in rows) == "2040-02-14T23:00:00Z"


def test_restart_keeps_ids_count_and_import_timestamp(settings, source_dir, tmp_path, caplog):
    local = copy_runtime_inputs(source_dir, tmp_path / "minimal-source")
    settings.dataset_dir = local
    caplog.set_level("INFO", logger="astra")
    with TestClient(create_app(settings)) as client:
        first = client.get("/api/data").json()
        history = client.get("/api/observations?limit=500").json()
        assert client.get("/api/health").json() == {"status": "ok", "database_ready": True, "dataset_ready": True}
        assert first["historical_count"] == first["replay"]["visible_count"] == 6252
        assert first["historical_missing_count"] == 18
        assert first["initialized"] is True and first["provenance"] == "SYNTHETIC"
        assert len(first["references"]) == 4 and len(first["metrics"]) == 18
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/data").json() == first
        assert client.get("/api/observations?limit=500").json() == history
    assert "Historical mission dataset: imported" in caplog.messages
    assert "Historical mission dataset: already present" in caplog.messages
    with closing(sqlite3.connect(settings.database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 6252


def test_every_observation_endpoint_respects_persisted_cutoff(client, settings):
    assert client.get("/api/replay").json() == {
        "dataset_id": "ASTRA-SYN-90D-01", "revision": 0, "status": "PAUSED",
        "cursor_utc": CUTOFF, "mission_day": 45, "visible_count": 6252, "speed": 2,
        "historical_days": 45, "mission_days": 90, "latest_activity": None, "playback_error": None,
    }
    cases = [("/api/observations", {}), ("/api/observations/latest", {"scope": "cabin"}),
             ("/api/observations/latest", {"crew_id": "AST-001"})]
    for path, filters in cases:
        params = {**filters, "from_utc": DAY46, "to_utc": "2040-03-30T23:59:59Z"}
        assert client.get(path, params=params).json()["items"] == []
    # Simulate an accidentally published late row to exercise the independent SQL cutoff.
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute(
            """INSERT INTO observations
            SELECT 'SIM-LATE-TEST', mission_id, crew_id, subject_id, scope, ?, 46, metric, value, unit,
            activity_context, source, provenance, quality, missing_reason, privacy, share_cabin_context
            FROM observations WHERE observation_id = 'SIM-0000001'""", (DAY46,),
        )
    for path, filters in cases:
        params = {**filters, "from_utc": "2040-02-14T23:00:00Z", "to_utc": DAY46}
        response = client.get(path, params=params)
        assert response.status_code == 200
        assert all(row["timestamp_utc"] <= CUTOFF for row in response.json()["items"])
        assert "SIM-LATE-TEST" not in response.text
    mission = client.get("/api/mission").json()
    assert len(mission["cabin_readings"]) == 4
    assert all(row["timestamp_utc"] <= CUTOFF for row in mission["cabin_readings"])
    assert not mission["insights"]
    for path in ("/api/archive", "/all_observations_FULL_ARCHIVE.csv",
                 "/EVALUATION_ONLY_scenario_truth_NOT_FOR_LIVE_APP.csv", "/replay_future_HIDDEN_DAY46_to_DAY90.csv"):
        assert client.get(path).status_code == 404
    assert client.post("/api/replay", json={"command": "NEXT_DAY", "expected_revision": 1}).status_code == 409
    for path in ("/api/mission", "/api/replay", "/api/data", "/api/observations"):
        body = client.get(path).text
        for forbidden in ("EVALUATION_ONLY", "rest_hr_ref_bpm", "hidden_future_file", '"note"', "future_replay_records"):
            assert forbidden not in body


def test_cabin_and_crew_filters_privacy_and_pagination(client, settings, source_dir):
    assert client.get("/api/crew/AST-404").status_code == 404
    for filters in ({"scope": "cabin", "crew_id": "AST-001"}, {"metric": "invented"},
                    {"from_utc": "2040-02-01"}, {"limit": 501},
                    {"from_utc": CUTOFF, "to_utc": "2040-02-10T00:00:00Z"}):
        assert client.get("/api/observations", params=filters).status_code == 422
    assert client.get("/api/observations", params={"metric": "headache"}).json()["items"] == []
    scoped = client.get("/api/observations", params={"crew_id": "AST-001", "metric": "headache"}).json()["items"]
    assert len(scoped) == 45 and all(row["privacy"] == "private_health" and row["crew_id"] == "AST-001" for row in scoped)
    # A small page forces continuation across same-timestamp rows.
    params = {"scope": "cabin", "from_utc": "2040-01-01T00:00:00Z", "to_utc": "2040-01-01T02:00:00Z", "limit": 3}
    expected = sorted((row["timestamp_utc"], row["observation_id"]) for row in csv_source(source_dir, HISTORY)
                      if row["scope"] == "cabin" and params["from_utc"] <= row["timestamp_utc"] <= params["to_utc"])
    page = client.get("/api/observations", params=params).json()
    first_cursor = page["next_cursor"]
    seen = []
    while True:
        seen.extend((row["timestamp_utc"], row["observation_id"]) for row in page["items"])
        if page["next_cursor"] is None:
            break
        page = client.get("/api/observations", params={**params, "cursor": page["next_cursor"]}).json()
    assert seen == expected
    assert client.get("/api/observations", params={**params, "cursor": "bad-token"}).status_code == 422
    assert client.get("/api/observations", params={**params, "cursor": first_cursor, "metric": "cabin_temperature"}).status_code == 422
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute("UPDATE replay_state SET revision = 1")
    assert client.get("/api/observations", params={**params, "cursor": first_cursor}).status_code == 409


def test_latest_valid_and_explicit_gap_are_distinct(client, source_dir):
    rows = csv_source(source_dir, HISTORY)
    gap = next(row for row in rows if row["quality"] == "MISSING" and row["scope"] == "cabin")
    filters = {"scope": "cabin", "metric": gap["metric"], "to_utc": gap["timestamp_utc"]}
    response = client.get("/api/observations/latest", params=filters).json()
    assert response["items"][0]["quality"] == "VALID"
    assert response["items"][0]["timestamp_utc"] < gap["timestamp_utc"]
    assert response["latest_missing"][0]["value"] is None
    assert response["latest_missing"][0]["missing_reason"] == gap["missing_reason"]
    response = client.get("/api/observations/latest", params={**filters, "from_utc": gap["timestamp_utc"]}).json()
    assert response["items"] == []
    assert response["latest_missing"][0]["observation_id"] == gap["observation_id"]
    history = client.get("/api/observations", params={**filters, "from_utc": gap["timestamp_utc"]}).json()
    assert history["items"] == response["latest_missing"]


@pytest.mark.parametrize("repin", [False, True], ids=["checksum-mismatch", "invalid-repinned-history"])
def test_failed_validation_leaves_no_partial_import(settings, source_dir, tmp_path, repin):
    local = copy_runtime_inputs(source_dir, tmp_path / "invalid-source")
    settings.dataset_dir = local
    history = local / HISTORY
    original = history.read_bytes()
    assert b"2040-02-14T23:00:00Z" in original
    history.write_bytes(original.replace(b"2040-02-14T23:00:00Z", DAY46.encode()))
    if repin:
        repin_checksum(local, HISTORY)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json() == {"status": "ok", "database_ready": True, "dataset_ready": False}
        assert client.get("/api/data").json()["error"]["code"] == "dataset_unavailable"
    with closing(sqlite3.connect(settings.database_path)) as connection:
        for table in ("observations", "crew", "metrics", "datasets", "replay_state"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_changed_input_cannot_replace_known_good_import(settings, source_dir, tmp_path):
    local = copy_runtime_inputs(source_dir, tmp_path / "changed-source")
    settings.dataset_dir = local
    with TestClient(create_app(settings)) as client:
        first = client.get("/api/data").json()
        assert first["source_status"] == "VERIFIED"
    crew = local / "crew_profiles.csv"
    crew.write_bytes(crew.read_bytes().replace(b"Daniel Okafor", b"Changed Name"))
    repin_checksum(local, crew.name)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["dataset_ready"] is True
        assert client.get("/api/data").json() == {**first, "source_status": "INVALID"}
        assert client.get("/api/crew/AST-001").json()["display_name"] == "Daniel Okafor"


def test_insert_failure_rolls_back_all_history_writes(settings):
    initialize_database(settings.database_path)
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute("""
            CREATE TRIGGER reject_late_history BEFORE INSERT ON observations
            WHEN NEW.mission_day = 45 BEGIN
                SELECT RAISE(ABORT, 'test database write failure');
            END
        """)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["dataset_ready"] is False
        assert client.get("/api/mission").json()["error"]["code"] == "dataset_unavailable"
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        for table in ("observations", "crew", "metrics", "datasets", "replay_state"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        connection.execute("DROP TRIGGER reject_late_history")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["dataset_ready"] is True
        assert client.get("/api/replay").json()["visible_count"] == 6252
