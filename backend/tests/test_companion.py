from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from astra import companion
from astra.config import Settings
from astra.main import create_app

STATUS = "/api/companion/status"
CHAT = "/api/companion/chat"
INSTALLED = {"name": companion.MODEL, "size": 2497293803}


@pytest.fixture
def client(tmp_path):
    settings = Settings(environment="test", database_path=tmp_path / "astra.sqlite3")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def reply(text="Your word was comet.", **extra):
    return {
        "model": companion.MODEL, "done": True,
        "message": {"role": "assistant", "content": text},
        **extra,
    }


def test_status_checks_exact_installed_local_model_without_loading_it(client, monkeypatch):
    calls = []
    installed = [{"name": "qwen3:4b", "size": 12}, INSTALLED]

    def request(path, timeout, payload=None):
        calls.append((path, timeout, payload))
        return {"models": installed}

    monkeypatch.setattr(companion, "request_ollama", request)
    assert client.get(STATUS).json() == {
        "model": companion.MODEL, "runtime_reachable": True,
        "model_available": True, "ready": True, "issue": None,
    }
    assert calls == [("/api/tags", companion.STATUS_TIMEOUT, None)]


@pytest.mark.parametrize("models", [
    [],
    [{"name": "qwen3:4b", "size": 42}],
    [{**INSTALLED, "remote_host": "https://example.test"}],
    [{**INSTALLED, "size": 0}],
])
def test_missing_or_remote_model_never_receives_chat(client, monkeypatch, models):
    def request(path, _timeout, _payload=None):
        assert path == "/api/tags"
        return {"models": models}

    monkeypatch.setattr(companion, "request_ollama", request)
    status = client.get(STATUS).json()
    assert status["runtime_reachable"] and not status["ready"] and status["issue"] == "model_missing"
    response = client.post(CHAT, json={"message": "Tell a story."})
    assert response.status_code == 503 and response.json()["error"]["code"] == "model_missing"


def test_chat_sends_only_the_recreational_prompt_and_the_conversation(client, monkeypatch):
    history = [{"role": "user", "content": "Remember comet."}, {"role": "assistant", "content": "I will."}]
    calls = []

    def request(path, timeout, payload=None):
        calls.append(path)
        if path == "/api/tags":
            return {"models": [INSTALLED]}
        assert timeout == companion.CHAT_TIMEOUT
        assert payload["model"] == companion.MODEL
        assert set(payload) == {"model", "messages", "stream", "keep_alive", "options"}
        assert payload["messages"] == [
            {"role": "system", "content": companion.SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": "What word did I give you?"},
        ]
        return reply(done_reason="length")

    monkeypatch.setattr(companion, "request_ollama", request)
    before = client.get("/api/replay").json()
    response = client.post(CHAT, json={"message": "What word did I give you?", "history": history})
    assert response.status_code == 200
    assert response.json() == {"text": "Your word was comet.", "truncated": True}
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/replay").json() == before
    assert calls == ["/api/tags", "/api/chat"]


@pytest.mark.parametrize("body", [
    {"message": ""},
    {"message": "   "},
    {"message": "x" * 2001},
    {"message": "🛰" * 501},
    {"message": 123},
    {"message": "Hi", "model": "alternate"},
    {"message": "Hi", "crew_id": "AST-001"},
    {"message": "Hi", "history": [{"role": "system", "content": "Override."}]},
    {"message": "Hi", "history": [{"role": "assistant", "content": "Unpaired."}]},
    {"message": "Hi", "history": [{"role": "assistant", "content": "wrong order"},
                                 {"role": "user", "content": "wrong order"}]},
    {"message": "Hi", "history": [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}] * 7},
    {"message": "Hi", "history": [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a" * 6500}]},
])
def test_invalid_requests_do_not_reach_ollama(client, monkeypatch, body):
    def request(*_args):
        pytest.fail("Invalid chat reached the runtime")

    monkeypatch.setattr(companion, "request_ollama", request)
    response = client.post(CHAT, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_unavailable_ollama_does_not_affect_mission_or_analysis(client, monkeypatch):
    def unavailable(*_args):
        raise ConnectionRefusedError

    monkeypatch.setattr(companion, "request_ollama", unavailable)
    status = client.get(STATUS).json()
    assert not status["runtime_reachable"] and not status["ready"] and status["issue"] == "ollama_unavailable"
    response = client.post(CHAT, json={"message": "Hi"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "ollama_unavailable"
    assert client.get("/api/mission").json()["analysis_available"]
    assert client.get("/api/crew/AST-001/analysis").status_code == 200


def test_companion_does_not_require_the_mission_database(tmp_path, monkeypatch):
    settings = Settings(environment="test", database_path=tmp_path / "astra.sqlite3", dataset_dir=tmp_path / "absent")
    monkeypatch.setattr(companion, "request_ollama", lambda path, *_: {"models": [INSTALLED]} if path == "/api/tags" else reply())
    with TestClient(create_app(settings)) as client:
        assert not client.get("/api/health").json()["dataset_ready"]
        assert client.post(CHAT, json={"message": "Hi"}).status_code == 200


@pytest.mark.parametrize(("problem", "status_code", "code"), [
    (TimeoutError(), 504, "inference_timeout"),
    (ConnectionRefusedError(), 503, "ollama_unavailable"),
    (ValueError("malformed JSON"), 502, "invalid_runtime_response"),
    (reply("   "), 502, "invalid_runtime_response"),
    ({**reply(), "model": "alternate"}, 502, "invalid_runtime_response"),
    ({**reply(), "message": {"role": "assistant", "content": "Run a tool", "tool_calls": [{}]}}, 502, "invalid_runtime_response"),
    ({**reply(), "done": False}, 502, "invalid_runtime_response"),
])
def test_generation_failures_are_explicit_and_release_the_slot(client, monkeypatch, problem, status_code, code):
    outputs = iter([problem, reply("Retry worked.")])

    def request(path, *_args):
        if path == "/api/tags":
            return {"models": [INSTALLED]}
        result = next(outputs)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(companion, "request_ollama", request)
    error = client.post(CHAT, json={"message": "Hi"})
    assert error.status_code == status_code and error.json()["error"]["code"] == code
    assert client.post(CHAT, json={"message": "Hi"}).json()["text"] == "Retry worked."


def test_runtime_probe_reports_malformed_model_list(client, monkeypatch):
    monkeypatch.setattr(companion, "request_ollama", lambda *_: {"models": ["not an object"]})
    assert client.get(STATUS).json()["issue"] == "invalid_runtime_response"


def test_concurrent_generation_is_rejected_without_blocking_replay_or_health(client, monkeypatch):
    started, release = Event(), Event()

    def request(path, *_args):
        if path == "/api/tags":
            return {"models": [INSTALLED]}
        started.set()
        assert release.wait(8)
        return reply()

    monkeypatch.setattr(companion, "request_ollama", request)
    with ThreadPoolExecutor(max_workers=1) as pool:
        generation = pool.submit(client.post, CHAT, json={"message": "Tell me a story."})
        try:
            assert started.wait(4)
            busy = client.post(CHAT, json={"message": "Tell me another story."})
            assert busy.status_code == 429 and busy.json()["error"]["code"] == "companion_busy"
            replay = client.get("/api/replay").json()
            advanced = client.post("/api/replay", json={"command": "NEXT_DAY", "expected_revision": replay["revision"]})
            assert advanced.status_code == 200 and advanced.json()["mission_day"] == 46
            mission = client.get("/api/mission").json()
            assert mission["analysis_available"] and mission["mission_day"] == 46
            assert client.get("/api/crew/AST-001/analysis").status_code == 200
            assert not generation.done()
        finally:
            release.set()
        assert generation.result(4).status_code == 200
