"""Live pipeline: NASA FIRMS near-real-time detections -> event stream -> harmonized fire-days.

    FIRMS API --(poller)--> Azure Event Hubs --(consumer)--> PostgreSQL live tables --> API (?live=1)

- firms.py      reads detections from the FIRMS API and turns them into events
- eventhub.py   sends events to Azure Event Hubs (plain HTTPS, no SDK)
- poller.py     one polling pass: fetch, drop what is stored already, publish
- consumer.py   handles a batch of events: store detections, recompute the months they touch
- harmonize.py  PLACEHOLDER: which detections count and how they convert to S-NPP-equivalent fire-days
- store.py      the live tables: counting fire-days, anomalies, status
- replay.py     demo mode: replays a past outbreak as if it were happening now (marked simulated)

This package imports only the standard library and asyncpg so the Azure Functions in functions/ can use it.
"""
