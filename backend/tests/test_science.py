import math

from fastapi.testclient import TestClient

from astra.config import Settings
from astra.main import create_app


def test_hypothetical_comparison_reuses_fixed_public_resting_references(tmp_path):
    with TestClient(create_app(Settings(environment="test", database_path=tmp_path / "science.sqlite3"))) as client:
        start = client.get("/api/replay").json()
        path = "/api/data/personalization"
        response = client.get(path, params={"bpm": 70})
        assert response.status_code == 200
        result = response.json()
        assert result["hypothetical_bpm"] == 70
        assert result["dataset_id"] == start["dataset_id"]
        assert len(result["comparisons"]) == 4
        first, second, third, fourth = result["comparisons"]
        assert [item["median_bpm"] for item in (first, second, third, fourth)] == [66, 71, 59, 62]
        assert first["absolute_difference_bpm"] == 4 and first["strength"] == "below_moderate"
        assert third["absolute_difference_bpm"] == 11 and third["strength"] == "strong"
        assert math.isclose(third["modified_z"], 3.70975)
        assert all(item["distinct_days"] >= 10 for item in result["comparisons"])
        assert not any({"observations", "findings", "timestamp_utc", "privacy"} & item.keys()
                       for item in result["comparisons"])
        assert client.get("/api/replay").json() == start

        advanced = client.post(
            "/api/replay", json={"command": "NEXT_DAY", "expected_revision": start["revision"]},
        )
        assert advanced.status_code == 200 and advanced.json()["mission_day"] == 46
        assert client.get(path, params={"bpm": 70}).json() == result

        for value in ("39", "121", "70.5", "invalid"):
            assert client.get(path, params={"bpm": value}).status_code == 422
