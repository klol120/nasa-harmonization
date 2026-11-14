"""Outgoing email: everything is written to the `email_outbox` table first.

With SMTP settings (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM) `deliver()` sends the
unsent rows; without them nothing leaves the server, which is what local development wants: the emails
can be read at /dev/outbox instead.
"""

import asyncio
import html
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import asyncpg


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    user: str
    password: str
    sender: str
    starttls: bool


def smtp_settings() -> SmtpSettings | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return None
    return SmtpSettings(
        host=host,
        port=int(os.environ.get("SMTP_PORT", "587")),
        user=os.environ.get("SMTP_USER", ""),
        password=os.environ.get("SMTP_PASSWORD", ""),
        sender=os.environ.get("MAIL_FROM", "Wel3a <no-reply@wel3a.app>"),
        starttls=os.environ.get("SMTP_STARTTLS", "1") != "0",
    )


def render_html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None, footer: str = "") -> str:
    """A small, email-client-safe HTML body. Paragraphs are plain text (escaped here)."""
    ps = "".join(f'<p style="margin:0 0 14px;line-height:1.5">{html.escape(p)}</p>' for p in paragraphs)
    btn = ""
    if button:
        label, url = button
        btn = (
            f'<p style="margin:22px 0"><a href="{html.escape(url, quote=True)}" '
            'style="background:#3d7bff;color:#fff;padding:11px 18px;border-radius:8px;text-decoration:none;font-weight:600">'
            f"{html.escape(label)}</a></p>"
        )
    foot = f'<p style="margin-top:28px;color:#8a93a6;font-size:12px;line-height:1.5">{footer}</p>' if footer else ""
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1b2333">'
        f'<h2 style="margin:0 0 18px;font-size:20px">{html.escape(title)}</h2>{ps}{btn}{foot}</div>'
    )


async def enqueue(conn: asyncpg.Connection, *, to: str, subject: str, text: str, html_body: str | None, kind: str) -> int:
    return await conn.fetchval(
        """insert into email_outbox (to_email, subject, body_text, body_html, kind)
           values ($1, $2, $3, $4, $5) returning email_id""",
        to, subject, text, html_body, kind,
    )


def _send_one(s: SmtpSettings, to: str, subject: str, text: str, html_body: str | None) -> None:
    msg = EmailMessage()
    msg["From"] = s.sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(s.host, s.port, timeout=20) as smtp:
        if s.starttls:
            smtp.starttls(context=ssl.create_default_context())
        if s.user:
            smtp.login(s.user, s.password)
        smtp.send_message(msg)


async def deliver(conn: asyncpg.Connection, limit: int = 100) -> tuple[int, int]:
    """Send unsent outbox rows over SMTP. Returns (sent, failed); (0, 0) when SMTP is not configured."""
    s = smtp_settings()
    if s is None:
        return 0, 0
    rows = await conn.fetch(
        "select email_id, to_email, subject, body_text, body_html from email_outbox where sent_at is null and error is null order by email_id limit $1",
        limit,
    )
    sent = failed = 0
    for r in rows:
        try:
            await asyncio.to_thread(_send_one, s, r["to_email"], r["subject"], r["body_text"], r["body_html"])
            await conn.execute("update email_outbox set sent_at = now() where email_id = $1", r["email_id"])
            sent += 1
        except Exception as e:  # keep going; the row records why it failed
            await conn.execute("update email_outbox set error = $2 where email_id = $1", r["email_id"], str(e)[:500])
            failed += 1
    return sent, failed
