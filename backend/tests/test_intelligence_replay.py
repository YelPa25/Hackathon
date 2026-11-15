import csv
import hashlib
import json
from collections import Counter
from contextlib import closing
from math import isfinite
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter

from fastapi.testclient import TestClient

from astra.config import Settings, default_dataset_dir
from astra.db import connect_database
from astra.health_statistics import CABIN, PERSON, POLICIES
from astra.main import create_app
from astra.replay import FUTURE
from test_replay import CUTOFF, move

BUNDLE = default_dataset_dir()
HISTORY = "replay_history_DAY01_to_DAY45.csv"


def isolated_settings(tmp_path: Path):
    return Settings(environment="test", database_path=tmp_path / "stage04.sqlite3", dataset_dir=BUNDLE)


def rows(name):
    with (BUNDLE / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def hashes():
    return {name: hashlib.sha256((BUNDLE / name).read_bytes()).hexdigest()
            for name in (HISTORY, FUTURE, "SHA256SUMS.txt", "crew_profiles.csv", "metric_dictionary.csv")}


def without_revision(value):
    return {key: item for key, item in value.items() if key != "revision"}


def check_finite(value):
    if isinstance(value, float):
        assert isfinite(value)
    if isinstance(value, list):
        for child in value:
            check_finite(child)
    if isinstance(value, dict):
        for child in value.values():
            check_finite(child)


def check_evidence(item, source, cutoff, *, crew_id=None):
    raw = source[item["observation_id"]]
    assert raw["timestamp_utc"] == item["timestamp_utc"] <= cutoff
    assert raw["metric"] == item["metric"] and raw["unit"] == item["unit"] and raw["source"] == item["source"]
    assert raw["activity_context"] == item["context"] and raw["quality"] == item["quality"]
    assert item["value"] == (float(raw["value"]) if raw["value"] else None)
    assert item["provenance"] == "SYNTHETIC"
    if crew_id is not None:
        assert raw["crew_id"] == crew_id
    return raw


def test_all_46_snapshots_are_finite_fixed_and_replay_safe(tmp_path):
    before = hashes()
    historical, future = rows(HISTORY), rows(FUTURE)
    assert (len(historical), len(future)) == (6252, 6239)
    source = {record["observation_id"]: record for record in historical + future}
    states, public_states, types, cabin_by_type, unavailable, missing = (Counter() for _ in range(6))
    durations = {"crew": [], "mission": []}
    settings = isolated_settings(tmp_path)
    refs, first_day = {}, {}
    events = {}
    with TestClient(create_app(settings)) as client:
        crew_ids = [row["crew_id"] for row in client.get("/api/crew").json()["items"]]
        assert len(crew_ids) == 4
        for day in range(45, 91):
            state = move(client, "NEXT_DAY") if day > 45 else client.get("/api/replay").json()
            assert state["mission_day"] == day
            now = perf_counter()
            mission = client.get("/api/mission").json()
            durations["mission"].append(1000 * (perf_counter() - now))
            assert mission["analysis_available"]
            assert mission["cursor_utc"] == state["cursor_utc"]
            assert set(mission["crew_monitoring"]) == set(crew_ids)
            public_states.update(item["status"] for item in mission["crew_monitoring"].values())
            for f in mission["health_findings"]:
                for item in f["evidence"]:
                    assert check_evidence(item, source, state["cursor_utc"])["privacy"] != "private_health"
                assert all(word not in f["explanation"].lower() for word in ("fatigue", "sleep", "stress", "headache", "mood"))
            for f in mission["cabin_findings"]:
                for item in f["evidence"]:
                    assert check_evidence(item, source, state["cursor_utc"])["scope"] == "cabin"
                cabin_by_type[f["rule_id"]] += 1
            assert sum(f["type"] == "SHARED_CABIN" for f in mission["cabin_findings"]) <= 1
            events[day] = {"cabin": [f["rule_id"] for f in mission["cabin_findings"]], "crew": {}}
            for crew_id in crew_ids:
                now = perf_counter()
                response = client.get(f"/api/crew/{crew_id}/analysis")
                durations["crew"].append(1000 * (perf_counter() - now))
                assert response.status_code == 200, response.text
                a = response.json()
                assert a["cursor_utc"] == mission["cursor_utc"] and a["revision"] == state["revision"]
                check_finite(a)
                states[a["status"]] += 1
                types.update(f["rule_id"] for f in a["findings"])
                events[day]["crew"][crew_id] = [f["rule_id"] for f in a["findings"] if f["type"] != "DATA_QUALITY"]
                if day == 45:
                    first_day[crew_id] = without_revision(a)
                    refs[crew_id] = a["baselines"]
                    assert len([b for b in refs[crew_id] if b["availability"] == "AVAILABLE"]) == 12
                    assert {b["metric"] for b in refs[crew_id] if b["availability"] == "NOT_APPLICABLE"} == {"headache", "exercise_duration"}
                    real_hr = [float(row["value"]) for row in historical if row["crew_id"] == crew_id
                               and row["metric"] == "resting_heart_rate" and row["quality"] == "VALID"]
                    assert next(b for b in refs[crew_id] if b["metric"] == "resting_heart_rate")["median"] == median(real_hr)
                assert a["baselines"] == refs[crew_id]
                assert all(b["calibration_end_utc"] == CUTOFF and b["context"] == POLICIES[b["metric"]].context
                           for b in a["baselines"])
                assert a["cabin_findings"] == mission["cabin_findings"]
                assert {i["metric"] for i in a["indicators"]} == set(PERSON)
                for item in a["blood_pressure"]:
                    check_evidence(item, source, state["cursor_utc"], crew_id=crew_id)
                for ind in a["indicators"]:
                    for entry in (ind["current"], ind["latest_valid"]):
                        if entry:
                            check_evidence(entry, source, state["cursor_utc"], crew_id=crew_id)
                    for key in ind["unusual_ids"]:
                        assert source[key]["timestamp_utc"] <= state["cursor_utc"]
                        assert source[key]["quality"] == "VALID" and source[key]["crew_id"] == crew_id
                    if ind["status"] == "INSUFFICIENT_DATA":
                        unavailable[ind["metric"]] += 1
                    if ind["availability"] == "MISSING":
                        assert ind["current"]["value"] is None
                        missing[ind["metric"]] += 1
                for f in a["findings"]:
                    for item in f["evidence"]:
                        check_evidence(item, source, state["cursor_utc"], crew_id=crew_id)
        assert state["visible_count"] == 12491 and state["status"] == "COMPLETE"
        url = f"/api/crew/{crew_ids[0]}/analysis"
        end = client.get(url).json()
        assert end == client.get(url).json()
    with TestClient(create_app(settings)) as client:
        assert without_revision(client.get(url).json()) == without_revision(end)
        assert move(client, "RESET")["cursor_utc"] == CUTOFF
        assert all(without_revision(client.get(f"/api/crew/{crew_id}/analysis").json()) == first
                   for crew_id, first in first_day.items())
        assert client.get(url, params={"from_utc": "2040-03-10T00:00:00Z"}).json()["cursor_utc"] == CUTOFF
    assert hashes() == before
    metrics = rows("metric_dictionary.csv")
    assert {r["metric"] for r in metrics} == set(PERSON + CABIN)
    print("STAGE04_EVALUATION", json.dumps({
        "states": states, "mission_card_states": public_states, "finding_occurrences": types,
        "cabin_occurrences": cabin_by_type, "unavailable": unavailable, "missing_snapshots": missing,
        "elapsed_endpoint_ms": {key: [round(median(times), 1), round(quantiles(times, n=20)[18], 1)]
                                for key, times in durations.items()},
        "reference_resting_heart_rate": {c: next(b["median"] for b in values if b["metric"] == "resting_heart_rate")
                                         for c, values in refs.items()},
        "daily": events,
    }))


def insert_health(db, observation_id, dataset, day, timestamp, metric, value, *, who=None, opted_in=False, missing=False):
    p = POLICIES[metric]
    db.execute("""INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNTHETIC', ?, ?, ?, ?)""",
               (observation_id, dataset, who, who or "CABIN-01", "person" if who else "cabin",
                timestamp, day, metric, None if missing else str(value), p.unit, p.context, "isolated-test",
                "MISSING" if missing else "VALID", "fixture" if missing else None,
                "private_health" if who and p.context == "self_report" else "crew" if who else "shared_environment",
                int(opted_in)))


def test_same_day_cutoff_and_aggregate_opt_in(tmp_path):
    settings = isolated_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        state = move(client, "NEXT_EVENT")
        assert state["mission_day"] == 46 and state["cursor_utc"] < "2040-02-15T08:00:00Z"
        with closing(connect_database(settings.database_path)) as db, db:
            d = state["dataset_id"]
            insert_health(db, "TEST-FUTURE", d, 46, "2040-02-15T23:10:00Z", "resting_heart_rate", 192, who="AST-001")
        a = client.get("/api/crew/AST-001/analysis").json()
        assert "TEST-FUTURE" not in json.dumps(a)
        assert client.get("/api/mission").json()["cursor_utc"] == state["cursor_utc"]
        with closing(connect_database(settings.database_path)) as db, db:
            db.execute("DELETE FROM observations WHERE observation_id = 'TEST-FUTURE'")
        move(client, "RESET")
        state = move(client, "NEXT_DAY")
        assert state["mission_day"] == 46
        near = "2040-02-15T22:50:00Z"
        with closing(connect_database(settings.database_path)) as db, db:
            for hour in range(18, 24):
                insert_health(db, f"TEST-CO2-{hour}", d, 46, f"2040-02-15T{hour}:55:00Z",
                              "cabin_co2_partial_pressure", 5)
                insert_health(db, f"TEST-PPM-{hour}", d, 46, f"2040-02-15T{hour}:55:00Z",
                              "cabin_co2_concentration", 6000)
            insert_health(db, "TEST-FIRST", d, 46, near, "headache", 3, who="AST-001", opted_in=True)
            insert_health(db, "TEST-DUP", d, 46, "2040-02-15T22:51:00Z", "headache", 3, who="AST-001", opted_in=True)
            insert_health(db, "TEST-NO", d, 46, near, "headache", 4, who="AST-002")
            insert_health(db, "TEST-OLD", d, 44, "2040-02-13T23:30:00Z", "headache", 4, who="AST-003", opted_in=True)
        isolated = client.get("/api/mission").json()
        prior = isolated["crew_monitoring"]
        assert [x["rule_id"] for x in isolated["cabin_findings"] if "CO₂" in x["explanation"]] == ["CABIN_REFERENCE_SHIFT"]
        with closing(connect_database(settings.database_path)) as db, db:
            insert_health(db, "TEST-YES", d, 46, "2040-02-15T22:52:00Z", "headache", 2, who="AST-002", opted_in=True)
            insert_health(db, "TEST-MISSING", d, 46, "2040-02-15T23:01:00Z", "headache", None, who="AST-002", missing=True)
        mission = client.get("/api/mission").json()
        shared = [f for f in mission["cabin_findings"] if f["type"] == "SHARED_CABIN"]
        assert len(shared) == 1 and shared[0]["shared_report_count"] == 2 and shared[0]["crew_id"] is None
        assert {e["metric"] for e in shared[0]["evidence"]} == {"cabin_co2_partial_pressure"}
        assert not any(name in json.dumps(shared) for name in ("AST-001", "AST-002", "TEST-YES", "TEST-FIRST", "6000"))
        assert mission["crew_monitoring"] == prior
        assert "TEST-YES" not in client.get("/api/crew/AST-001/analysis").text
        with closing(connect_database(settings.database_path)) as db, db:
            insert_health(db, "TEST-ZERO", d, 46, "2040-02-15T23:00:00Z", "headache", 0, who="AST-002", opted_in=True)
        assert not any(f["type"] == "SHARED_CABIN" for f in client.get("/api/mission").json()["cabin_findings"])


def test_analysis_errors_preserve_raw_reading_routes(tmp_path, monkeypatch):
    with TestClient(create_app(isolated_settings(tmp_path))) as client:
        subject = "/api/crew/AST-001/analysis"
        response = client.get(subject, params={"metric": "resting_heart_rate", "context": "rest"})
        assert [i["metric"] for i in response.json()["indicators"]] == ["resting_heart_rate"]
        assert client.get(subject, params={"metric": "cabin_temperature"}).status_code == 422
        assert client.get("/api/crew/not-a-crew-member/analysis").status_code == 404

        def fail(*_):
            raise RuntimeError("simulated internal analytical error")

        monkeypatch.setattr("astra.routes.HealthSnapshot", fail)
        failed = client.get(subject)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "analysis_unavailable"
        mission = client.get("/api/mission").json()
        assert not mission["analysis_available"] and len(mission["crew_readings"]) == 4 and mission["cabin_readings"]
        assert client.get("/api/observations/latest", params={"crew_id": "AST-001"}).json()["items"]
