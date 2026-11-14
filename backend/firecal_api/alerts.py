"""Scheduled emails: fire alerts for saved areas, and the monthly digest for the email list.

Both only write to the outbox (then deliver over SMTP when it is configured), so they are safe to run
locally. Run them from cron / a scheduled job, e.g. daily for alerts and monthly for the digest:

    python -m firecal_api.cli send-alerts
    python -m firecal_api.cli send-digest
"""

from dataclasses import dataclass

import asyncpg

from . import accounts as AC
from . import contract as C
from . import mailer


@dataclass
class AlertResult:
    area_id: int
    email: str
    area: str
    ym: str | None
    z: float | None
    sent: bool
    reason: str


def _fmt_z(z: float) -> str:
    return f"{z:+.1f}"


async def run_alerts(conn: asyncpg.Connection, dry_run: bool = False) -> list[AlertResult]:
    """Email each user whose saved area's newest month is unusually high (z >= the area's threshold).

    An area is alerted at most once per month: `last_alerted_ym` remembers the newest month sent.
    """
    rows = await conn.fetch(
        """select a.*, u.email, u.name as user_name from saved_area a join app_user u using (user_id)
           where a.alert_enabled order by a.region_id, a.area_id"""
    )
    cache: dict = {}
    out: list[AlertResult] = []
    for a in rows:
        st = await AC.area_status(conn, a, cache)
        if st is None:
            out.append(AlertResult(a["area_id"], a["email"], a["name"], None, None, False, "no data for this area"))
            continue
        ym, z = st["ym"], st["anomaly_z"]
        if z is None or z < a["alert_z"]:
            out.append(AlertResult(a["area_id"], a["email"], a["name"], ym, z, False, f"below threshold {a['alert_z']}"))
            continue
        if a["last_alerted_ym"] is not None and C.ym_str(a["last_alerted_ym"]) >= ym:
            out.append(AlertResult(a["area_id"], a["email"], a["name"], ym, z, False, "already alerted for this month"))
            continue
        if not dry_run:
            month = AC.ym_label(ym)
            link = AC.dashboard_link(a, ym)
            kind = "Modelled estimate" if st["is_estimate"] else "Satellite detections"
            subject = f"Fire alert: {a['name']} had unusually high burning in {month}"
            region = AC.region_name(a["region_id"])
            where = a["name"] if region.lower() in a["name"].lower() else f"{a['name']} ({region})"
            lines = [
                f"{where} recorded {st['harmonized']:.1f} fire-days in {month}, "
                f"an anomaly of z = {_fmt_z(z)} against its normal for that month (your alert threshold is {a['alert_z']:.1f}).",
                f"{kind}. Fire-days count 0.05° cells with at least one active-fire detection per day: they measure burning "
                "activity, not burned area.",
            ]
            if st["partial_month"]:
                lines.append("The month is not complete yet, so the value may still change.")
            text = "\n\n".join([*lines, f"Open the area: {link}", "Turn this alert off under My areas on the website."])
            body = mailer.render_html(
                subject, lines, ("Open this area", link),
                "You get this because you turned on alerts for this saved area. Turn them off under My areas.",
            )
            async with conn.transaction():
                await mailer.enqueue(conn, to=a["email"], subject=subject, text=text, html_body=body, kind="alert")
                await conn.execute(
                    "update saved_area set last_alerted_ym = $2 where area_id = $1", a["area_id"], C.parse_ym(ym)
                )
        out.append(AlertResult(a["area_id"], a["email"], a["name"], ym, z, not dry_run, "alert" + (" (dry run)" if dry_run else "")))
    if not dry_run:
        await mailer.deliver(conn)
    return out


async def digest_lines(conn: asyncpg.Connection) -> list[tuple[str, str]]:
    """One line per region: its newest month with data, fire-days and how it compares with normal."""
    rows = await conn.fetch(
        """select distinct on (r.region_id) r.region_id, m.ym, m.harmonized, m.anomaly_z, m.partial_month
           from release r join region_month m using (release_id)
           where r.is_current and m.data_available and m.harmonized is not null
           order by r.region_id, m.ym desc"""
    )
    lines = []
    for r in rows:
        z = r["anomaly_z"]
        verdict = "about normal" if z is None or abs(z) < 1 else ("above normal" if z > 0 else "below normal")
        if z is not None and z >= 2:
            verdict = "far above normal"
        partial = " (month in progress)" if r["partial_month"] else ""
        lines.append((
            r["region_id"],
            f"{AC.region_name(r['region_id'])}, {r['ym']:%B %Y}{partial}: {r['harmonized']:.0f} fire-days, {verdict}"
            + (f" (z {_fmt_z(z)})" if z is not None else ""),
        ))
    return lines


async def run_digest(conn: asyncpg.Connection, dry_run: bool = False) -> int:
    """Queue the monthly digest for every confirmed subscriber with the 'digest' topic. Returns how many."""
    lines = await digest_lines(conn)
    if not lines:
        return 0
    subs = await conn.fetch(
        "select email, token from subscriber where status = 'confirmed' and 'digest' = any(topics) order by subscriber_id"
    )
    if dry_run:
        for _, line in lines:
            print("  " + line)
        return len(subs)
    subject = "Wel3a monthly burning digest"
    intro = "The newest month of harmonized MODIS + VIIRS burning activity in each region we cover:"
    for s in subs:
        unsub = AC.unsubscribe_link(s["token"])
        text = "\n".join([intro, "", *[f"- {line}" for _, line in lines], "", f"Explore: {AC.web_url()}", "", f"Unsubscribe: {unsub}"])
        body = mailer.render_html(
            subject, [intro, *[line for _, line in lines]], ("Open the burning calendar", AC.web_url()),
            f'You get this because you joined the Wel3a email list. <a href="{unsub}">Unsubscribe</a>.',
        )
        await mailer.enqueue(conn, to=s["email"], subject=subject, text=text, html_body=body, kind="digest")
    await mailer.deliver(conn)
    return len(subs)
