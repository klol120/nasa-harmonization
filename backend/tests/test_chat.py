"""The assistant endpoint, with OpenRouter's HTTP API replaced by a canned stream (no key, no network)."""

import json

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from firecal_api import chat


def or_body(parts: list[str], finish: str = "stop") -> bytes:
    chunks = [{"choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]} for p in parts]
    chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    lines = [": OPENROUTER PROCESSING"] + [f"data: {json.dumps(c)}" for c in chunks] + ["data: [DONE]"]
    return ("\n\n".join(lines) + "\n\n").encode()


@pytest.fixture
def api(monkeypatch):
    """A client for the chat routes plus the list of requests the fake OpenRouter API received."""
    sent: list[httpx2.Request] = []
    reply = {"status": 200, "body": or_body(["Aug 2021 was ", "**unusual**."])}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        if reply["status"] != 200:
            return httpx2.Response(reply["status"], json={"error": {"code": reply["status"], "message": "nope"}})
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=reply["body"])

    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    fake = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    monkeypatch.setattr(chat, "http", lambda: fake)
    chat._recent.clear()
    chat._day.update(date="", count=0)
    app = FastAPI()
    app.include_router(chat.router)
    return TestClient(app), sent, reply


def events_of(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        out.append((lines["event"], json.loads(lines["data"])))
    return out


ASK = {"messages": [{"role": "user", "content": "Was Aug 2021 unusual?"}], "context": {"page": "Overview", "selected_month": {"month": "Aug 2021", "value": 412}}}


def test_config_reports_whether_a_key_is_set(api, monkeypatch):
    c, _, _ = api
    assert c.get("/chat/config").json() == {"enabled": True, "model": "openrouter/free"}
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
    assert c.get("/chat/config").json()["model"] == "google/gemma-4-31b-it:free"
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert c.get("/chat/config").json()["enabled"] is False
    r = c.post("/chat", json=ASK)
    assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]


def test_streams_the_answer_and_sends_the_view(api):
    c, sent, _ = api
    r = c.post("/chat", json=ASK, headers={"origin": "http://localhost:5173"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = events_of(r.text)
    assert "".join(d["text"] for e, d in ev if e == "delta") == "Aug 2021 was **unusual**."
    assert ev[-1] == ("done", {"truncated": False})
    req = sent[0]
    assert str(req.url) == chat.OPENROUTER_URL
    assert req.headers["authorization"] == "Bearer or-test" and req.headers["http-referer"] == "http://localhost:5173"
    body = json.loads(req.content)
    assert body["model"] == "openrouter/free" and body["stream"] is True
    # Fixed instructions first, the view snapshot after them, in one system message.
    system = body["messages"][0]
    assert system["role"] == "system" and system["content"].startswith(chat.SYSTEM) and '"value":412' in system["content"]
    assert body["messages"][1:] == [{"role": "user", "content": "Was Aug 2021 unusual?"}]


def test_length_limit_and_errors(api):
    c, _, reply = api
    reply["body"] = or_body(["Half an ans"], "length")
    assert events_of(c.post("/chat", json=ASK).text)[-1] == ("done", {"truncated": True})
    reply["body"] = or_body([], "content_filter")
    assert events_of(c.post("/chat", json=ASK).text)[-1][0] == "error"
    reply["body"] = b'data: {"error": {"code": 429, "message": "rate limited"}}\n\n'
    assert "busy" in events_of(c.post("/chat", json=ASK).text)[-1][1]["message"]


def test_api_errors_reach_the_visitor_without_details(api):
    c, _, reply = api
    reply["status"] = 401
    ev = events_of(c.post("/chat", json=ASK).text)
    assert ev == [("error", {"message": "The assistant's API key was rejected. Check OPENROUTER_API_KEY on the server."})]


def test_history_must_end_with_a_question(api):
    c, sent, _ = api
    turns = [{"role": "assistant", "content": "Hello"}, {"role": "user", "content": "Hi"}]
    assert c.post("/chat", json={"messages": turns}).status_code == 200
    assert json.loads(sent[0].content)["messages"][1:] == [{"role": "user", "content": "Hi"}]  # a leading answer is dropped
    assert c.post("/chat", json={"messages": turns[:1]}).status_code == 422
    assert c.post("/chat", json={"messages": [{"role": "user", "content": "x" * 7000}]}).status_code == 422
    assert c.post("/chat", json={**ASK, "context": {"blob": "x" * 40_000}}).status_code == 413


def test_rate_limit_per_visitor_and_per_day(api, monkeypatch):
    c, _, _ = api
    for _ in range(chat.RATE_LIMIT):
        assert c.post("/chat", json=ASK).status_code == 200
    r = c.post("/chat", json=ASK)
    assert r.status_code == 429 and "Retry-After" in r.headers
    chat._recent.clear()
    monkeypatch.setenv("CHAT_DAILY_CAP", str(chat.RATE_LIMIT))
    assert c.post("/chat", json=ASK).status_code == 429
