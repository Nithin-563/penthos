"""Tests for the local HTTP wrapper (no model, no network services)."""

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.server import (
    RequestError,
    completion_response,
    is_authorized,
    make_server,
    models_response,
    parse_chat_request,
    sse_delta,
    sse_event,
    with_system_prompt,
)
from inference.prompt import PARI_SYSTEM_PROMPT


class FakeBackend:
    def __init__(self, pieces=("Hello", " from Pari")):
        self.pieces = pieces
        self.calls = []

    def stream(self, messages, temperature, top_p, max_tokens):
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        })
        yield from self.pieces


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

def test_parse_chat_request_defaults():
    request = parse_chat_request({"messages": [{"role": "user", "content": "hi"}]})
    assert request["messages"] == [{"role": "user", "content": "hi"}]
    assert request["stream"] is False
    assert request["model"] == "pari"
    assert request["max_tokens"] > 0


def test_parse_chat_request_custom_options():
    request = parse_chat_request({
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.1,
        "top_p": 0.8,
        "max_tokens": 128,
        "stream": True,
        "model": "pari-4b",
    })
    assert request["temperature"] == pytest.approx(0.1)
    assert request["top_p"] == pytest.approx(0.8)
    assert request["max_tokens"] == 128
    assert request["stream"] is True
    assert request["model"] == "pari-4b"


def test_parse_chat_request_maps_developer_role():
    request = parse_chat_request({
        "messages": [{"role": "developer", "content": "be terse"}],
    })
    assert request["messages"][0]["role"] == "user"


@pytest.mark.parametrize("payload", [
    None,
    {},
    {"messages": []},
    {"messages": "hi"},
    {"messages": [{"role": "tool", "content": "x"}]},
    {"messages": [{"role": "user"}]},
    {"messages": [{"role": "user", "content": 5}]},
    {"messages": [{"role": "user", "content": "hi"}], "temperature": 9},
    {"messages": [{"role": "user", "content": "hi"}], "top_p": 0},
    {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 0},
    {"messages": [{"role": "user", "content": "hi"}], "temperature": "hot"},
])
def test_parse_chat_request_rejects_bad_input(payload):
    with pytest.raises(RequestError):
        parse_chat_request(payload)


def test_parse_chat_request_caps_max_tokens():
    request = parse_chat_request({
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 10_000_000,
    })
    assert request["max_tokens"] == 16384


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_with_system_prompt_adds_identity_once():
    messages = with_system_prompt([{"role": "user", "content": "hi"}])
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == PARI_SYSTEM_PROMPT

    custom = with_system_prompt([
        {"role": "system", "content": "custom"},
        {"role": "user", "content": "hi"},
    ])
    assert custom[0]["content"] == "custom"
    assert sum(1 for m in custom if m["role"] == "system") == 1


def test_completion_response_shape():
    body = completion_response("hello", "pari")
    assert body["object"] == "chat.completion"
    assert body["model"] == "pari"
    assert body["choices"][0]["message"]["content"] == "hello"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["total_tokens"] >= 1


def test_models_response():
    body = models_response("pari")
    assert body["data"][0]["id"] == "pari"


def test_sse_framing():
    delta = sse_delta("hi", "pari", role="assistant")
    assert delta.startswith("data: ")
    assert delta.endswith("\n\n")
    parsed = json.loads(delta[len("data: "):].strip())
    assert parsed["object"] == "chat.completion.chunk"
    assert parsed["choices"][0]["delta"]["content"] == "hi"
    assert sse_event("[DONE]") == "data: [DONE]\n\n"


def test_is_authorized():
    assert is_authorized(None, None) is True
    assert is_authorized(None, "secret") is False
    assert is_authorized("Bearer secret", "secret") is True
    assert is_authorized("Bearer wrong", "secret") is False
    assert is_authorized("Basic secret", "secret") is False


# ---------------------------------------------------------------------------
# End-to-end over a real local socket with a fake backend
# ---------------------------------------------------------------------------

@pytest.fixture()
def live_server():
    backend = FakeBackend()
    server = make_server("127.0.0.1", 0, backend=backend, api_key=None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", backend
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post(url, payload, headers=None):
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=10)


def test_health_and_models(live_server):
    base, _ = live_server
    with urllib.request.urlopen(base + "/health", timeout=5) as response:
        health = json.loads(response.read())
    assert health["status"] == "ok"
    assert health["display"] == "Pari"

    with urllib.request.urlopen(base + "/v1/models", timeout=5) as response:
        models = json.loads(response.read())
    assert models["data"][0]["id"] == "pari"


def test_chat_completion_uses_local_backend(live_server):
    base, backend = live_server
    with _post(
        base + "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "hi"}]},
    ) as response:
        body = json.loads(response.read())

    assert body["choices"][0]["message"]["content"] == "Hello from Pari"
    call = backend.calls[0]
    assert call["messages"][0]["content"] == PARI_SYSTEM_PROMPT
    assert call["messages"][-1]["content"] == "hi"


def test_streaming_completion(live_server):
    base, _ = live_server
    with _post(
        base + "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "hi"}], "stream": True},
    ) as response:
        raw = response.read().decode()

    events = [line[len("data: "):] for line in raw.splitlines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    text = "".join(
        json.loads(event)["choices"][0]["delta"].get("content", "")
        for event in events
        if event != "[DONE]"
    )
    assert text == "Hello from Pari"


def test_api_key_enforced():
    backend = FakeBackend()
    server = make_server("127.0.0.1", 0, backend=backend, api_key="k3y")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _post(base + "/v1/chat/completions", {"messages": [{"role": "user", "content": "hi"}]})
        assert excinfo.value.code == 401

        with _post(
            base + "/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer k3y"},
        ) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bad_json_returns_400(live_server):
    base, _ = live_server
    request = urllib.request.Request(
        base + "/v1/chat/completions",
        data=b"{not json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request, timeout=5)
    assert excinfo.value.code == 400
