"""Accounts and business features: sign-in, email list, saved areas, admin stats.

Nothing here gates the data. Every region endpoint stays public; an account only adds things on top
(saved areas, alerts). Settings (environment variables):

- GOOGLE_CLIENT_ID   OAuth client id of the "Sign in with Google" button (not a secret).
- AUTH_DEV_LOGIN=1   local development only: a test sign-in without Google, and the /dev/outbox page.
- PUBLIC_WEB_URL     where the website is, for links in emails (default http://localhost:5173).
- PUBLIC_API_URL     where this API is, for confirm/unsubscribe links (default http://127.0.0.1:8000).
- ADMIN_EMAILS       comma-separated emails allowed to read /admin/stats.
"""

import asyncio
import hashlib
import html
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import quote, urlencode

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from . import contract as C
from . import mailer

router = APIRouter()

SESSION_DAYS = 30
MAX_AREAS_PER_USER = 50
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,63}$")
REGION_NAMES = {"lebanon": "Lebanon", "greece": "Greece", "eastmed": "Eastern Mediterranean"}


# ---------------------------------------------------------------- settings


def google_client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def dev_login_enabled() -> bool:
    return os.environ.get("AUTH_DEV_LOGIN", "") == "1"


def web_url() -> str:
    return os.environ.get("PUBLIC_WEB_URL", "http://localhost:5173").rstrip("/")


def api_url() -> str:
    return os.environ.get("PUBLIC_API_URL", "http://127.0.0.1:8000").rstrip("/")


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def region_name(region_id: str) -> str:
    return REGION_NAMES.get(region_id, region_id.capitalize())


# ---------------------------------------------------------------- plumbing


async def conn(request: Request):
    async with request.app.state.pool.acquire() as c:
        yield c


Conn = Annotated[asyncpg.Connection, Depends(conn)]


def jsonr(obj, status: int = 200) -> Response:
    return Response(json.dumps(obj, separators=(",", ":"), default=str), status, media_type="application/json")


def normalize_email(v: str) -> str:
    v = v.strip()
    if not EMAIL_RE.match(v):
        raise ValueError("not a valid email address")
    return v.lower()


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def user_out(u: asyncpg.Record) -> dict:
    return {
        "id": u["user_id"],
        "email": u["email"],
        "name": u["name"],
        "picture": u["picture_url"],
        "is_admin": u["email"].lower() in admin_emails(),
        "created_at": u["created_at"].isoformat(),
    }


async def _session_user(c: asyncpg.Connection, authorization: str | None) -> asyncpg.Record | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    return await c.fetchrow(
        """select u.* from user_session s join app_user u using (user_id)
           where s.token_hash = $1 and s.expires_at > now()""",
        token_hash(token),
    )


async def optional_user(c: Conn, authorization: Annotated[str | None, Header()] = None) -> asyncpg.Record | None:
    return await _session_user(c, authorization)


async def current_user(c: Conn, authorization: Annotated[str | None, Header()] = None) -> asyncpg.Record:
    u = await _session_user(c, authorization)
    if u is None:
        raise HTTPException(401, "sign in required")
    return u


OptUser = Annotated[asyncpg.Record | None, Depends(optional_user)]
User = Annotated[asyncpg.Record, Depends(current_user)]


async def start_session(c: asyncpg.Connection, user_id: int, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    await c.execute(
        "insert into user_session (token_hash, user_id, expires_at, user_agent) values ($1, $2, $3, $4)",
        token_hash(token), user_id, datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS), (user_agent or "")[:300],
    )
    await c.execute("delete from user_session where expires_at < now()")
    return token


async def upsert_user(
    c: asyncpg.Connection, *, email: str, name: str | None, picture: str | None, google_sub: str | None, verified: bool,
) -> asyncpg.Record:
    """Find the user by Google id, else by email; create them if new. Updates name/picture on each sign-in."""
    async with c.transaction():
        u = None
        if google_sub:
            u = await c.fetchrow("select * from app_user where google_sub = $1", google_sub)
        if u is None:
            u = await c.fetchrow("select * from app_user where lower(email) = lower($1)", email)
        if u is None:
            u = await c.fetchrow(
                """insert into app_user (email, email_verified, name, picture_url, google_sub, last_login_at)
                   values ($1, $2, $3, $4, $5, now()) returning *""",
                email, verified, name, picture, google_sub,
            )
        else:
            u = await c.fetchrow(
                """update app_user set email = $2, email_verified = email_verified or $3, name = coalesce($4, name),
                          picture_url = coalesce($5, picture_url), google_sub = coalesce(google_sub, $6), last_login_at = now()
                   where user_id = $1 returning *""",
                u["user_id"], email, verified, name, picture, google_sub,
            )
        # Someone who joined the email list before signing up is linked to their account.
        await c.execute(
            "update subscriber set user_id = $1 where lower(email) = lower($2) and user_id is null", u["user_id"], email
        )
    return u


# ---------------------------------------------------------------- sign-in


@router.get("/auth/config", tags=["accounts"])
async def auth_config():
    """What the website should offer: the Google button (when configured) and/or the local test sign-in."""
    return {"google_client_id": google_client_id() or None, "dev_login": dev_login_enabled()}


class GoogleSignIn(BaseModel):
    credential: str = Field(..., min_length=20, max_length=5000, description="ID token from Google Identity Services")


def _verify_google(credential: str, client_id: str) -> dict:
    from google.auth.transport import requests as grequests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(credential, grequests.Request(), client_id)


@router.post("/auth/google", tags=["accounts"])
async def auth_google(body: GoogleSignIn, request: Request, c: Conn):
    client_id = google_client_id()
    if not client_id:
        raise HTTPException(503, "Google sign-in is not configured on this server (GOOGLE_CLIENT_ID)")
    try:
        info = await asyncio.to_thread(_verify_google, body.credential, client_id)
    except ValueError as e:
        raise HTTPException(401, f"Google sign-in failed: {e}") from None
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(401, "Google sign-in failed: unexpected issuer")
    email = info.get("email")
    if not email or not info.get("email_verified"):
        raise HTTPException(401, "Google account has no verified email")
    u = await upsert_user(
        c, email=email.lower(), name=info.get("name"), picture=info.get("picture"), google_sub=info["sub"], verified=True
    )
    token = await start_session(c, u["user_id"], request.headers.get("user-agent"))
    return {"token": token, "user": user_out(u)}


class DevSignIn(BaseModel):
    email: str
    name: str | None = Field(None, max_length=120)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v):
        return normalize_email(v)


@router.post("/auth/dev-login", tags=["accounts"])
async def auth_dev_login(body: DevSignIn, request: Request, c: Conn):
    """Local development only (AUTH_DEV_LOGIN=1): sign in as any email without Google."""
    if not dev_login_enabled():
        raise HTTPException(404, "Not Found")
    u = await upsert_user(c, email=body.email, name=body.name or body.email.split("@")[0], picture=None, google_sub=None, verified=True)
    token = await start_session(c, u["user_id"], request.headers.get("user-agent"))
    return {"token": token, "user": user_out(u)}


@router.get("/auth/me", tags=["accounts"])
async def auth_me(u: User, c: Conn):
    sub = await c.fetchrow("select status, topics from subscriber where lower(email) = lower($1)", u["email"])
    n_areas = await c.fetchval("select count(*) from saved_area where user_id = $1", u["user_id"])
    return {
        "user": user_out(u),
        "newsletter": {"status": sub["status"], "topics": list(sub["topics"])} if sub else {"status": "none", "topics": []},
        "n_areas": n_areas,
    }


@router.post("/auth/logout", status_code=204, tags=["accounts"])
async def auth_logout(c: Conn, authorization: Annotated[str | None, Header()] = None):
    if authorization and authorization.lower().startswith("bearer "):
        await c.execute("delete from user_session where token_hash = $1", token_hash(authorization[7:].strip()))
    return Response(status_code=204)


@router.delete("/me", status_code=204, tags=["accounts"])
async def delete_account(u: User, c: Conn):
    """Delete the account, its sessions and saved areas, and take it off the email list."""
    async with c.transaction():
        await c.execute(
            "update subscriber set status = 'unsubscribed', unsubscribed_at = now(), user_id = null where user_id = $1 or lower(email) = lower($2)",
            u["user_id"], u["email"],
        )
        await c.execute("delete from app_user where user_id = $1", u["user_id"])
    return Response(status_code=204)


# ---------------------------------------------------------------- email list


class Subscribe(BaseModel):
    email: str | None = None
    topics: list[Literal["news", "digest"]] = Field(default_factory=lambda: ["news", "digest"])
    source: str | None = Field(None, max_length=40)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return None if v is None else normalize_email(v)


def _confirm_email(email: str, token: str) -> tuple[str, str, str]:
    link = f"{api_url()}/newsletter/confirm?{urlencode({'token': token})}"
    subject = "Confirm your Wel3a subscription"
    text = (
        "Thanks for joining the Wel3a email list.\n\n"
        f"Confirm your subscription: {link}\n\n"
        "You'll get project news and a monthly digest of burning activity in the Eastern Mediterranean.\n"
        "If you didn't ask for this, ignore this email and nothing will happen."
    )
    body = mailer.render_html(
        "Confirm your subscription",
        ["Thanks for joining the Wel3a email list. You'll get project news and a monthly digest of burning activity "
         "in Lebanon, Greece and the Eastern Mediterranean."],
        ("Confirm subscription", link),
        "If you didn't ask for this, ignore this email and nothing will happen.",
    )
    return subject, text, body


@router.post("/newsletter/subscribe", tags=["email list"])
async def newsletter_subscribe(body: Subscribe, request: Request, c: Conn, u: OptUser):
    """Join the email list. Signed-in users (verified email) are confirmed at once; others get a confirmation link."""
    email = body.email or (u["email"] if u else None)
    if not email:
        raise HTTPException(422, "email is required")
    verified_now = u is not None and u["email_verified"] and email.lower() == u["email"].lower()
    async with c.transaction():
        row = await c.fetchrow("select * from subscriber where lower(email) = lower($1) for update", email)
        if row and row["status"] == "confirmed":
            await c.execute("update subscriber set topics = $2 where subscriber_id = $1", row["subscriber_id"], body.topics)
            return {"status": "subscribed"}
        status = "confirmed" if verified_now else "pending"
        token = row["token"] if row else secrets.token_urlsafe(24)
        await c.execute(
            """insert into subscriber (email, user_id, status, topics, token, source, confirmed_at)
               values ($1, $2, $3, $4, $5, $6, case when $3 = 'confirmed' then now() end)
               on conflict ((lower(email))) do update set status = excluded.status, topics = excluded.topics,
                   user_id = coalesce(subscriber.user_id, excluded.user_id), source = coalesce(excluded.source, subscriber.source),
                   confirmed_at = excluded.confirmed_at, unsubscribed_at = null""",
            email, u["user_id"] if u else None, status, body.topics, token, body.source,
        )
        recently_sent = await c.fetchval(
            """select 1 from email_outbox where lower(to_email) = lower($1) and kind = 'newsletter_confirm'
               and created_at > now() - interval '10 minutes'""",
            email,
        )
        if status == "pending" and not recently_sent:
            subject, text, html_body = _confirm_email(email, token)
            await mailer.enqueue(c, to=email, subject=subject, text=text, html_body=html_body, kind="newsletter_confirm")
    await mailer.deliver(c)
    # Same answer whether or not the address was already on the list, so the form reveals nothing.
    return {"status": "subscribed" if status == "confirmed" else "check_email"}


def _page(title: str, message: str) -> HTMLResponse:
    back = html.escape(web_url(), quote=True)
    return HTMLResponse(
        f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Wel3a</title>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0f19;color:#e8ecf4;font-family:-apple-system,Segoe UI,Roboto,sans-serif;padding:16px">
<main style="max-width:440px;text-align:center"><h1 style="font-size:22px">{html.escape(title)}</h1>
<p style="color:#9aa4b8;line-height:1.5">{html.escape(message)}</p>
<p><a href="{back}" style="display:inline-block;margin-top:10px;background:#3d7bff;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none">Open the burning calendar</a></p></main>"""
    )


@router.get("/newsletter/confirm", response_class=HTMLResponse, tags=["email list"])
async def newsletter_confirm(token: Annotated[str, Query(max_length=100)], c: Conn):
    row = await c.fetchrow(
        """update subscriber set status = 'confirmed', confirmed_at = coalesce(confirmed_at, now()), unsubscribed_at = null
           where token = $1 returning email""",
        token,
    )
    if not row:
        return _page("Link not valid", "This confirmation link is not valid any more. You can sign up again on the website.")
    return _page("You're subscribed", f"{row['email']} will get Wel3a news and the monthly burning digest.")


@router.get("/newsletter/unsubscribe", response_class=HTMLResponse, tags=["email list"])
async def newsletter_unsubscribe(token: Annotated[str, Query(max_length=100)], c: Conn):
    row = await c.fetchrow(
        "update subscriber set status = 'unsubscribed', unsubscribed_at = now() where token = $1 returning email", token
    )
    if not row:
        return _page("Link not valid", "This unsubscribe link is not valid.")
    return _page("You're unsubscribed", f"{row['email']} won't get Wel3a emails any more.")


class MyNewsletter(BaseModel):
    subscribed: bool
    topics: list[Literal["news", "digest"]] = Field(default_factory=lambda: ["news", "digest"])


@router.post("/me/newsletter", tags=["email list"])
async def my_newsletter(body: MyNewsletter, request: Request, c: Conn, u: User):
    if body.subscribed:
        return await newsletter_subscribe(Subscribe(email=u["email"], topics=body.topics, source="account"), request, c, u)
    await c.execute(
        "update subscriber set status = 'unsubscribed', unsubscribed_at = now() where lower(email) = lower($1)", u["email"]
    )
    return {"status": "unsubscribed"}


def unsubscribe_link(token: str) -> str:
    return f"{api_url()}/newsletter/unsubscribe?{urlencode({'token': token})}"


# ---------------------------------------------------------------- saved areas


class AreaIn(BaseModel):
    region: str = Field(..., pattern=r"^[a-z0-9_-]{1,64}$")
    name: str = Field(..., min_length=1, max_length=120)
    kind: Literal["bbox", "polygon"]
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    ring: list[list[float]] | None = Field(None, max_length=2000)
    exclude_persistent: bool = False
    alert_enabled: bool = False
    alert_z: float = Field(2.0, ge=0.5, le=5)

    @model_validator(mode="after")
    def _check(self):
        w, s, e, n = self.bbox
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("bbox must be [west, south, east, north] with west < east and south < north")
        if self.kind == "polygon" and (not self.ring or len(self.ring) < 3 or any(len(p) != 2 for p in self.ring)):
            raise ValueError("a polygon needs a ring of at least 3 [lon, lat] points")
        return self


class AreaPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    alert_enabled: bool | None = None
    alert_z: float | None = Field(None, ge=0.5, le=5)
    exclude_persistent: bool | None = None


def area_polygon(a: asyncpg.Record | dict) -> list[list[list[float]]] | None:
    """The saved ring as a closed GeoJSON polygon, for cell selection."""
    if a["kind"] != "polygon" or not a["ring"]:
        return None
    ring = a["ring"] if isinstance(a["ring"], list) else json.loads(a["ring"])
    if ring[0] != ring[-1]:
        ring = [*ring, ring[0]]
    return [ring]


def dashboard_link(a: asyncpg.Record | dict, ym: str | None = None) -> str:
    """Link that opens the dashboard on this area (same hash format as the website's shareable links)."""
    p = {"src": f"api:{a['region_id']}", "s": "harmonized", "m": "cell_days", "n": a["name"]}
    ring = a["ring"] if isinstance(a["ring"], list) or a["ring"] is None else json.loads(a["ring"])
    if a["kind"] == "polygon" and ring:
        p["p"] = ";".join(f"{x:.3f},{y:.3f}" for x, y in ring)
    else:
        p["b"] = ",".join(f"{v:.3f}" for v in a["bbox"])
    if ym:
        p["t"] = ym
    return f"{web_url()}/#{urlencode(p, quote_via=quote)}"


async def area_status(c: asyncpg.Connection, a: asyncpg.Record, cache: dict) -> dict | None:
    """Latest month with data for a saved area: value, anomaly z and whether it is unusual."""
    from .api import area_months, fetch_cells  # late import: api includes this router

    region = a["region_id"]
    if region not in cache:
        r = await c.fetchrow("select * from release where region_id = $1 and is_current", region)
        cache[region] = (r, await fetch_cells(c, r["release_id"]) if r else None)
    r, cells = cache[region]
    if r is None:
        return None
    try:
        _, months = await area_months(
            c, r, cells, bbox=list(a["bbox"]), polygon=area_polygon(a), exclude_persistent=a["exclude_persistent"]
        )
    except HTTPException:
        return None
    latest = next((m for m in reversed(months) if m["data_available"] and m["harmonized"] is not None), None)
    if latest is None:
        return None
    return {
        "ym": latest["ym"],
        "harmonized": latest["harmonized"],
        "anomaly_z": latest["anomaly_z"],
        "is_estimate": latest["is_estimate"],
        "partial_month": latest["partial_month"],
        "unusual": latest["anomaly_z"] is not None and latest["anomaly_z"] >= a["alert_z"],
    }


def area_out(a: asyncpg.Record, status: dict | None = None) -> dict:
    ring = a["ring"] if isinstance(a["ring"], list) or a["ring"] is None else json.loads(a["ring"])
    return {
        "id": a["area_id"],
        "region": a["region_id"],
        "name": a["name"],
        "kind": a["kind"],
        "bbox": list(a["bbox"]),
        "ring": ring,
        "exclude_persistent": a["exclude_persistent"],
        "alert_enabled": a["alert_enabled"],
        "alert_z": a["alert_z"],
        "created_at": a["created_at"].isoformat(),
        "status": status,
    }


@router.get("/me/areas", tags=["saved areas"])
async def my_areas(u: User, c: Conn, status: bool = True):
    rows = await c.fetch("select * from saved_area where user_id = $1 order by created_at desc", u["user_id"])
    cache: dict = {}
    return [area_out(a, await area_status(c, a, cache) if status else None) for a in rows]


@router.post("/me/areas", status_code=201, tags=["saved areas"])
async def create_area(body: AreaIn, u: User, c: Conn):
    if not await c.fetchval("select 1 from region where region_id = $1", body.region):
        raise HTTPException(404, f"unknown region {body.region!r}")
    if await c.fetchval("select count(*) from saved_area where user_id = $1", u["user_id"]) >= MAX_AREAS_PER_USER:
        raise HTTPException(409, f"you can save up to {MAX_AREAS_PER_USER} areas")
    a = await c.fetchrow(
        """insert into saved_area (user_id, region_id, name, kind, bbox, ring, exclude_persistent, alert_enabled, alert_z)
           values ($1, $2, $3, $4, $5, $6, $7, $8, $9) returning *""",
        u["user_id"], body.region, body.name.strip(), body.kind, body.bbox,
        body.ring, body.exclude_persistent, body.alert_enabled, body.alert_z,
    )
    return jsonr(area_out(a, await area_status(c, a, {})), 201)


@router.patch("/me/areas/{area_id}", tags=["saved areas"])
async def update_area(area_id: int, body: AreaPatch, u: User, c: Conn):
    a = await c.fetchrow(
        """update saved_area set name = coalesce($3, name), alert_enabled = coalesce($4, alert_enabled),
                  alert_z = coalesce($5, alert_z), exclude_persistent = coalesce($6, exclude_persistent), updated_at = now()
           where area_id = $1 and user_id = $2 returning *""",
        area_id, u["user_id"], body.name.strip() if body.name else None, body.alert_enabled, body.alert_z, body.exclude_persistent,
    )
    if not a:
        raise HTTPException(404, "area not found")
    return area_out(a, await area_status(c, a, {}))


@router.delete("/me/areas/{area_id}", status_code=204, tags=["saved areas"])
async def delete_area(area_id: int, u: User, c: Conn):
    n = await c.execute("delete from saved_area where area_id = $1 and user_id = $2", area_id, u["user_id"])
    if n.endswith(" 0"):
        raise HTTPException(404, "area not found")
    return Response(status_code=204)


# ---------------------------------------------------------------- admin


@router.get("/admin/stats", tags=["admin"])
async def admin_stats(u: User, c: Conn):
    if u["email"].lower() not in admin_emails():
        raise HTTPException(403, "admins only (ADMIN_EMAILS)")
    q = lambda sql: c.fetchval(sql)  # noqa: E731
    return {
        "users": await q("select count(*) from app_user"),
        "users_last_7_days": await q("select count(*) from app_user where created_at > now() - interval '7 days'"),
        "active_last_7_days": await q("select count(*) from app_user where last_login_at > now() - interval '7 days'"),
        "subscribers": {r["status"]: r["n"] for r in await c.fetch("select status, count(*) n from subscriber group by status")},
        "saved_areas": await q("select count(*) from saved_area"),
        "areas_with_alerts": await q("select count(*) from saved_area where alert_enabled"),
        "emails": {
            "queued": await q("select count(*) from email_outbox where sent_at is null and error is null"),
            "sent": await q("select count(*) from email_outbox where sent_at is not null"),
            "failed": await q("select count(*) from email_outbox where error is not null"),
        },
    }


# ---------------------------------------------------------------- local development


@router.get("/dev/outbox", response_class=HTMLResponse, include_in_schema=False)
async def dev_outbox(c: Conn):
    """Local development only: the emails the app would have sent, newest first."""
    if not dev_login_enabled():
        raise HTTPException(404, "Not Found")
    rows = await c.fetch("select * from email_outbox order by email_id desc limit 50")
    items = "".join(
        f"""<article style="background:#fff;border-radius:10px;margin:0 0 18px;overflow:hidden">
<header style="padding:10px 14px;background:#eef1f7;font:13px -apple-system,sans-serif;color:#333">
<b>{html.escape(r['subject'])}</b><br>To {html.escape(r['to_email'])} · {html.escape(r['kind'])} · {r['created_at']:%Y-%m-%d %H:%M}</header>
<div>{r['body_html'] or '<pre style="padding:14px;white-space:pre-wrap">' + html.escape(r['body_text']) + '</pre>'}</div></article>"""
        for r in rows
    ) or '<p style="color:#9aa4b8">No emails yet.</p>'
    return HTMLResponse(
        '<!doctype html><meta charset=utf-8><title>Outbox · Wel3a dev</title>'
        '<body style="background:#0b0f19;margin:0;padding:24px;font-family:-apple-system,sans-serif">'
        '<h1 style="color:#e8ecf4;font-size:20px">Email outbox <small style="color:#9aa4b8;font-weight:400">'
        "(local development: nothing is really sent)</small></h1>"
        f'<div style="max-width:720px">{items}</div>'
    )


def ym_label(ym: str) -> str:
    d = C.parse_ym(ym)
    return d.strftime("%B %Y")
