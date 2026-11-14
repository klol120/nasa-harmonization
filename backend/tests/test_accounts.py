"""Accounts and business features against a throwaway <name>_test database with Lebanon loaded.

Uses the local test sign-in (AUTH_DEV_LOGIN=1); Google sign-in is only checked for its refusals.
"""

import asyncio

import pytest

from .conftest import TEST_DB_URL
from .test_db_api import client, loaded  # noqa: F401  (shared fixtures)

pytestmark = pytest.mark.db

CHOUF = {"region": "lebanon", "name": "Chouf & Damour", "kind": "bbox", "bbox": [35.4, 33.55, 35.75, 33.8]}


@pytest.fixture(autouse=True)
def dev_env(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_LOGIN", "1")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")


def sign_in(client, email: str) -> dict:
    r = client.post("/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def db(sql: str, *args):
    import asyncpg

    async def go():
        conn = await asyncpg.connect(TEST_DB_URL)
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    return asyncio.run(go())


def test_data_stays_public(client):
    assert client.get("/regions").status_code == 200
    assert client.post("/regions/lebanon/aggregate", json={"bbox": CHOUF["bbox"]}).status_code == 200


def test_config_and_google_refusals(client, monkeypatch):
    assert client.get("/auth/config").json() == {"google_client_id": None, "dev_login": True}
    assert client.post("/auth/google", json={"credential": "x" * 40}).status_code == 503
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    assert client.post("/auth/google", json={"credential": "not-a-real-token-" * 3}).status_code == 401


def test_dev_login_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("AUTH_DEV_LOGIN")
    assert client.post("/auth/dev-login", json={"email": "a@example.com"}).status_code == 404
    assert client.get("/dev/outbox").status_code == 404


def test_session_lifecycle(client):
    assert client.get("/auth/me").status_code == 401
    h = sign_in(client, "Life.Cycle@Example.com")
    me = client.get("/auth/me", headers=h).json()
    assert me["user"]["email"] == "life.cycle@example.com"
    assert me["newsletter"]["status"] == "none"
    assert client.post("/auth/logout", headers=h).status_code == 204
    assert client.get("/auth/me", headers=h).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_newsletter_double_opt_in(client):
    r = client.post("/newsletter/subscribe", json={"email": "Reader@Example.org", "source": "landing"})
    assert r.json() == {"status": "check_email"}
    # Asking again gives the same answer and doesn't send a second confirmation within 10 minutes.
    assert client.post("/newsletter/subscribe", json={"email": "reader@example.org"}).json() == {"status": "check_email"}
    mails = db("select subject from email_outbox where lower(to_email) = 'reader@example.org'")
    assert len(mails) == 1
    token = db("select token from subscriber where lower(email) = 'reader@example.org'")[0]["token"]
    assert "Link not valid" in client.get("/newsletter/confirm", params={"token": "wrong"}).text
    assert "subscribed" in client.get("/newsletter/confirm", params={"token": token}).text
    assert db("select status from subscriber where token = $1", token)[0]["status"] == "confirmed"
    assert "unsubscribed" in client.get("/newsletter/unsubscribe", params={"token": token}).text
    assert db("select status from subscriber where token = $1", token)[0]["status"] == "unsubscribed"
    assert client.post("/newsletter/subscribe", json={"email": "not-an-email"}).status_code == 422


def test_signed_in_subscribe_is_confirmed_at_once(client):
    h = sign_in(client, "member@example.com")
    assert client.post("/me/newsletter", json={"subscribed": True}, headers=h).json() == {"status": "subscribed"}
    assert client.get("/auth/me", headers=h).json()["newsletter"]["status"] == "confirmed"
    assert client.post("/me/newsletter", json={"subscribed": False}, headers=h).json() == {"status": "unsubscribed"}


def test_saved_areas_and_isolation(client):
    h = sign_in(client, "owner@example.com")
    a = client.post("/me/areas", json=CHOUF, headers=h)
    assert a.status_code == 201, a.text
    area = a.json()
    assert area["status"]["ym"] and area["status"]["harmonized"] is not None
    poly = {**CHOUF, "name": "Triangle", "kind": "polygon", "ring": [[35.4, 33.55], [35.75, 33.55], [35.6, 33.8]]}
    assert client.post("/me/areas", json=poly, headers=h).status_code == 201
    names = [x["name"] for x in client.get("/me/areas", headers=h).json()]
    assert names == ["Triangle", "Chouf & Damour"]

    other = sign_in(client, "other@example.com")
    assert client.get("/me/areas", headers=other).json() == []
    assert client.patch(f"/me/areas/{area['id']}", json={"alert_enabled": True}, headers=other).status_code == 404
    assert client.delete(f"/me/areas/{area['id']}", headers=other).status_code == 404

    p = client.patch(f"/me/areas/{area['id']}", json={"alert_enabled": True, "alert_z": 1.5}, headers=h).json()
    assert p["alert_enabled"] and p["alert_z"] == 1.5
    assert client.delete(f"/me/areas/{area['id']}", headers=h).status_code == 204

    bad = [
        {**CHOUF, "bbox": [36, 33, 35, 34]},
        {**CHOUF, "kind": "polygon", "ring": [[35, 33]]},
        {**CHOUF, "alert_z": 9},
    ]
    for body in bad:
        assert client.post("/me/areas", json=body, headers=h).status_code == 422
    assert client.post("/me/areas", json={**CHOUF, "region": "mars"}, headers=h).status_code == 404
    assert client.post("/me/areas", json=CHOUF).status_code == 401


def test_alerts_fire_once_per_month(client):
    from firecal_api.alerts import run_alerts
    from firecal_api.db import connect

    h = sign_in(client, "alerts@example.com")
    whole = client.get("/regions").json()[0]["bbox"]
    area = client.post(
        "/me/areas", json={"region": "lebanon", "name": "All of Lebanon", "kind": "bbox", "bbox": whole, "alert_enabled": True, "alert_z": 0.5},
        headers=h,
    ).json()
    z = area["status"]["anomaly_z"]

    async def go():
        conn = await connect(TEST_DB_URL)
        try:
            first = [r for r in await run_alerts(conn) if r.area_id == area["id"]][0]
            second = [r for r in await run_alerts(conn) if r.area_id == area["id"]][0]
            return first, second
        finally:
            await conn.close()

    first, second = asyncio.run(go())
    if z is not None and z >= 0.5:
        assert first.sent and not second.sent and "already" in second.reason
        assert db("select count(*) n from email_outbox where kind = 'alert' and to_email = 'alerts@example.com'")[0]["n"] == 1
    else:
        assert not first.sent and "below threshold" in first.reason


def test_admin_and_delete(client, monkeypatch):
    assert client.post("/plans/interest", json={"plan": "pro", "email": "lead@example.com"}).status_code == 404
    h = sign_in(client, "boss@example.com")
    assert client.get("/admin/stats", headers=h).status_code == 403
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    stats = client.get("/admin/stats", headers=h).json()
    assert stats["users"] >= 1 and "plan_interest" not in stats

    client.post("/me/newsletter", json={"subscribed": True}, headers=h)
    client.post("/me/areas", json=CHOUF, headers=h)
    assert client.delete("/me", headers=h).status_code == 204
    assert client.get("/auth/me", headers=h).status_code == 401
    assert db("select count(*) n from app_user where email = 'boss@example.com'")[0]["n"] == 0
    assert db("select status from subscriber where email = 'boss@example.com'")[0]["status"] == "unsubscribed"
