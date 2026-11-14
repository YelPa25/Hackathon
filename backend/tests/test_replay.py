import csv
import shutil
import sqlite3
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from astra.config import Settings, default_dataset_dir
from astra.db import SCHEMA
from astra.importer import INPUTS
from astra.main import create_app
from astra.replay import FUTURE

CUTOFF = "2040-02-14T23:59:59Z"


@pytest.fixture
def settings(tmp_path):
    source = tmp_path / "bundle"
    source.mkdir()
    for name in (*INPUTS, "SHA256SUMS.txt", FUTURE):
        shutil.copyfile(default_dataset_dir() / name, source / name)
    return Settings(environment="test", database_path=tmp_path / "replay.sqlite3", dataset_dir=source)


def command(client, name, expected=None, **fields):
    revision = client.get("/api/replay").json()["revision"] if expected is None else expected
    return client.post("/api/replay", json={"command": name, "expected_revision": revision, **fields})


def move(client, name, **fields):
    response = command(client, name, **fields)
    assert response.status_code == 200, response.text
    return response.json()


def wait_for(client, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get("/api/replay").json()
        if predicate(state):
            return state
        time.sleep(0.025)
    pytest.fail("Replay timer did not reach expected state")


def future_rows(settings):
    with (settings.dataset_dir / FUTURE).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def source_record(row):
    return {key: (value or None) for key, value in row.items() if key != "note"} | {
        "mission_day": int(row["mission_day"]), "share_cabin_context": int(row["share_cabin_context"] == "true"),
    }


def test_sequential_replay_matches_source_for_every_day(settings):
    source = future_rows(settings)
    assert len(source) == 6239 and Counter(row["quality"] for row in source)["MISSING"] == 49
    by_day = Counter(int(row["mission_day"]) for row in source)
    with TestClient(create_app(settings)) as client:
        initial = client.get("/api/replay").json()
        assert initial["mission_day"] == 45 and initial["visible_count"] == 6252
        assert initial["cursor_utc"] == CUTOFF and initial["latest_activity"] is None
        assert command(client, "SET_SPEED", speed=3).status_code == 422
        count = 6252
        for day in range(46, 91):
            state = move(client, "NEXT_DAY")
            count += by_day[day]
            assert state["mission_day"] == day and state["visible_count"] == count
            activity = state["latest_activity"]
            assert activity["observation_count"] == by_day[day]
            assert activity["crew_count"] + activity["cabin_count"] == by_day[day]
            if day < 90:
                after = (date(2040, 1, 1) + timedelta(days=day)).isoformat() + "T00:00:00Z"
                for route, params in (
                    ("/api/observations", {"crew_id": "AST-001"}),
                    ("/api/observations/latest", {"scope": "cabin"}),
                    ("/api/observations/latest", {"crew_id": "AST-001"}),
                ):
                    assert client.get(route, params={**params, "from_utc": after}).json()["items"] == []
            if day in (46, 60, 90):
                mission = client.get("/api/mission").json()
                assert mission["mission_day"] == day
                cards = [*mission["cabin_readings"], *mission["crew_readings"].values()]
                assert cards and all(row["timestamp_utc"] <= state["cursor_utc"] for row in cards)
                assert all(row["privacy"] != "private_health" for row in cards)
        assert state["status"] == "COMPLETE" and state["visible_count"] == 12491
        assert state["cursor_utc"] == "2040-03-30T23:59:59Z"
        assert command(client, "NEXT_DAY").status_code == 409
        assert command(client, "NEXT_EVENT").status_code == 409
        assert command(client, "PLAY").status_code == 409
    with closing(sqlite3.connect(settings.database_path)) as db:
        db.row_factory = sqlite3.Row
        actual = [dict(row) for row in db.execute(
            """SELECT o.* FROM observations o JOIN replay_observations USING (observation_id)
               ORDER BY timestamp_utc, observation_id"""
        )]
        assert actual == [source_record(row) for row in sorted(source, key=lambda r: (r["timestamp_utc"], r["observation_id"]))]
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 12491


def test_next_event_publishes_timestamp_ties_then_day_and_rejects_overlap(settings):
    source = future_rows(settings)
    first = source[0]["timestamp_utc"]
    with TestClient(create_app(settings)) as client:
        event = move(client, "NEXT_EVENT")
        response = client.get("/api/observations", params={"from_utc": first}).json()
        ids = sorted(row["observation_id"] for row in source if row["timestamp_utc"] == first)
        assert [row["observation_id"] for row in response["items"]] == ids
        assert event["cursor_utc"] == first and event["visible_count"] == 6252 + len(ids)

        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(command, client, "NEXT_DAY", event["revision"]) for _ in range(2)]
            assert sorted(call.result().status_code for call in calls) == [200, 409]
        assert command(client, "NEXT_DAY", event["revision"]).status_code == 409
        state = client.get("/api/replay").json()
        assert state["mission_day"] == 47
        assert state["visible_count"] == 6252 + sum(int(row["mission_day"]) <= 47 for row in source)


def test_play_pause_resume_speed_restart_and_completion(settings):
    with TestClient(create_app(settings)) as client:
        assert move(client, "NEXT_EVENT")["cursor_utc"] == "2040-02-15T00:00:00Z"
        assert move(client, "SET_SPEED", speed=0.5)["speed"] == 0.5
        assert move(client, "PLAY")["status"] == "RUNNING"
        tick = wait_for(client, lambda s: s["mission_day"] >= 47)
        assert tick["cursor_utc"] == "2040-02-16T00:00:00Z"
        paused = move(client, "PAUSE")
        time.sleep(0.65)
        assert client.get("/api/replay").json() == paused
        running = move(client, "PLAY")
        assert running["cursor_utc"] == paused["cursor_utc"]
        wait_for(client, lambda s: s["mission_day"] > paused["mission_day"])
        # Preserve a running position across shutdown without waiting for another tick.
        running = move(client, "SET_SPEED", speed=5)
    with TestClient(create_app(settings)) as client:
        restored = client.get("/api/replay").json()
        assert restored["cursor_utc"] == running["cursor_utc"]
        assert restored["status"] == "PAUSED" and restored["revision"] == running["revision"] + 1
        while client.get("/api/replay").json()["mission_day"] < 89:
            move(client, "NEXT_DAY")
        move(client, "SET_SPEED", speed=0.5)
        move(client, "PLAY")
        end = wait_for(client, lambda s: s["status"] == "COMPLETE")
        assert end["mission_day"] == 90 and end["visible_count"] == 12491
        time.sleep(0.6)
        assert client.get("/api/replay").json() == end


def test_reset_preserves_history_user_rows_and_source(settings):
    source_bytes = (settings.dataset_dir / FUTURE).read_bytes()
    with TestClient(create_app(settings)) as client:
        move(client, "NEXT_DAY")
        with closing(sqlite3.connect(settings.database_path)) as db, db:
            db.execute(
                """INSERT INTO observations SELECT 'OTHER-1', mission_id, crew_id, subject_id, scope,
                   '2040-03-30T23:50:00Z', 90, metric, value, unit, activity_context, source, provenance,
                   quality, missing_reason, privacy, share_cabin_context FROM observations
                   WHERE observation_id = 'SIM-0000001'"""
            )
        reset = move(client, "RESET")
        assert reset["visible_count"] == 6252 and reset["cursor_utc"] == CUTOFF
        assert client.get("/api/observations", params={"from_utc": "2040-02-15T00:00:00Z"}).json()["items"] == []
        with closing(sqlite3.connect(settings.database_path)) as db:
            assert db.execute("SELECT COUNT(*) FROM replay_observations").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM observations WHERE observation_id='OTHER-1'").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM observations WHERE mission_day <= 45").fetchone()[0] == 6252
        assert move(client, "NEXT_DAY")["mission_day"] == 46
    assert (settings.dataset_dir / FUTURE).read_bytes() == source_bytes


def test_invalid_future_source_and_failed_publication_preserve_last_commit(settings):
    source = settings.dataset_dir / FUTURE
    original = source.read_bytes()
    with TestClient(create_app(settings)) as client:
        initial = client.get("/api/replay").json()
        source.write_bytes(original + b"\n")
        failed = command(client, "PLAY")
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "replay_source_unavailable"
        assert client.get("/api/replay").json() == initial
        source.write_bytes(original)
        with closing(sqlite3.connect(settings.database_path)) as db, db:
            db.execute(
                """CREATE TRIGGER simulated_conflict BEFORE INSERT ON observations
                   WHEN NEW.mission_day > 45 AND NEW.scope = 'person' BEGIN
                   SELECT RAISE(ABORT, 'test failure after earlier cabin rows'); END"""
            )
        move(client, "SET_SPEED", speed=0.5)
        move(client, "PLAY")
        paused = wait_for(client, lambda s: s["status"] == "PAUSED")
        assert paused["playback_error"] and paused["cursor_utc"] == initial["cursor_utc"]
        assert paused["visible_count"] == 6252
        with closing(sqlite3.connect(settings.database_path)) as db, db:
            assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 6252
            assert db.execute("SELECT COUNT(*) FROM replay_observations").fetchone()[0] == 0
            db.execute("DROP TRIGGER simulated_conflict")
        assert move(client, "NEXT_DAY")["mission_day"] == 46


def test_schema_one_migrates_in_place(settings):
    with closing(sqlite3.connect(settings.database_path)) as db, db:
        for statement in SCHEMA:
            db.execute(statement)
        db.execute("PRAGMA user_version = 1")
        db.execute("CREATE TABLE unrelated (message TEXT)")
        db.execute("INSERT INTO unrelated VALUES ('keep')")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/replay").json()["visible_count"] == 6252
        assert move(client, "NEXT_DAY")["mission_day"] == 46
    with closing(sqlite3.connect(settings.database_path)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT message FROM unrelated").fetchone()[0] == "keep"
