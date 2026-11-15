"""Azure Functions of the live pipeline.

    poll_firms  (timer)        FIRMS API  -> new detections -> Event Hubs
    harmonize   (Event Hubs)   detections -> fire-days, harmonized, anomalies -> PostgreSQL

All the logic is in backend/firecal_api/live (copied next to this file by build.sh); these functions
only connect it to the triggers. Settings (application settings of the function app):

    DATABASE_URL         PostgreSQL of the API
    FIRMS_MAP_KEY        NASA FIRMS key
    EVENTHUB_CONNECTION  Event Hubs namespace connection string (send + listen)
    EVENTHUB_NAME        the event hub, e.g. "detections"
    POLL_SCHEDULE        NCRONTAB, e.g. "0 */15 * * * *"
    POLL_DAYS            days to look back on each poll (default 2)
"""

import logging
import os
from typing import List

import azure.functions as func

from firecal_api.db import connect
from firecal_api.live import consumer, eventhub, firms, poller

app = func.FunctionApp()


@app.timer_trigger(schedule="%POLL_SCHEDULE%", arg_name="timer", run_on_startup=False)
async def poll_firms(timer: func.TimerRequest) -> None:
    hub = eventhub.parse_connection(os.environ["EVENTHUB_CONNECTION"], os.environ.get("EVENTHUB_NAME"))

    def publish(events: list[dict]) -> None:
        eventhub.send(hub, [firms.dumps(e) for e in events])

    conn = await connect(os.environ["DATABASE_URL"])
    try:
        summary = await poller.poll(conn, os.environ["FIRMS_MAP_KEY"], publish,
                                    days=int(os.environ.get("POLL_DAYS", "2")), log=logging.info)
        logging.info("poll: %s", summary)
    finally:
        await conn.close()


@app.event_hub_message_trigger(arg_name="events", event_hub_name="%EVENTHUB_NAME%", connection="EVENTHUB_CONNECTION",
                               cardinality="many")
async def harmonize(events: List[func.EventHubEvent]) -> None:  # typing.List: the worker rejects list[...]
    decoded, unreadable = consumer.decode(e.get_body().decode("utf-8", "replace") for e in events)
    conn = await connect(os.environ["DATABASE_URL"])
    try:
        summary = await consumer.process(conn, decoded)
        logging.info("harmonize: %s (unreadable bodies: %d)", summary, unreadable)
    finally:
        await conn.close()
