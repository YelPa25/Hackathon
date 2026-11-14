import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from astra.config import Settings
from astra.main import create_app


def test_health_initializes_schema_without_source_data(tmp_path):
    path = tmp_path / "new" / "astra.sqlite3"
    assert not path.parent.exists()
    settings = Settings(environment="test", database_path=path, dataset_dir=tmp_path / "absent-dataset")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database_ready": True, "dataset_ready": False}
        assert response.headers["cache-control"] == "no-store"
        assert path.is_file()
        with closing(sqlite3.connect(path)) as connection:
            tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")}
            assert tables == {"crew", "datasets", "metrics", "observations", "replay_state", "replay_observations"}
            assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        for route in ("/api/replay", "/api/observations", "/api/crew", "/api/mission", "/api/data"):
            response = client.get(route)
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "dataset_unavailable"


def test_probe_detects_database_lost_after_startup(tmp_path):
    path = tmp_path / "astra.sqlite3"
    with TestClient(create_app(Settings(environment="test", database_path=path))) as client:
        assert client.get("/api/health").status_code == 200
        path.rename(tmp_path / "saved.sqlite3")
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "database_ready": False, "dataset_ready": False}
        assert not path.exists()


def test_invalid_database_starts_with_honest_health(tmp_path):
    path = tmp_path / "astra.sqlite3"
    path.write_bytes(b"not a sqlite database" * 25)
    with TestClient(create_app(Settings(environment="test", database_path=path))) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json()["database_ready"] is False
        assert str(path) not in response.text


def test_error_contract_and_private_routes(tmp_path):
    with TestClient(create_app(Settings(environment="test", database_path=tmp_path / "astra.db"))) as client:
        for path in ("/api/crew/AST-001/analysis", "/replay_future_HIDDEN_DAY46_to_DAY90.csv",
                     "/EVALUATION_ONLY_scenario_truth_NOT_FOR_LIVE_APP.csv"):
            response = client.get(path)
            assert response.status_code == 404
            assert response.json() == {"error": {"code": "not_found", "message": "Endpoint not found."}}
        response = client.post("/api/health")
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"


def test_cors_only_allows_configured_local_development_origins(tmp_path):
    origin = "http://127.0.0.1:5180"
    for environment in ("test", "development"):
        settings = Settings(environment=environment, database_path=tmp_path / "astra.db")
        with TestClient(create_app(settings)) as client:
            headers = client.get("/api/health", headers={"Origin": origin}).headers
            assert headers.get("access-control-allow-origin") == (origin if environment == "development" else None)
            headers = client.get("/api/health", headers={"Origin": "https://example.com"}).headers
            assert "access-control-allow-origin" not in headers


def test_settings_reject_dataset_writes_and_nonlocal_origins(tmp_path):
    with pytest.raises(ValidationError):
        Settings(database_path=tmp_path / "input" / "astra.db", dataset_dir=tmp_path / "input")
    with pytest.raises(ValidationError):
        Settings(cors_origins=("https://example.com",))
