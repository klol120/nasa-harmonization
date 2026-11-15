# Live pipeline functions

Two Azure Functions that keep the calendar up to date after the last export:

| function | trigger | what it does |
|---|---|---|
| `poll_firms` | timer (`POLL_SCHEDULE`, default every 15 minutes) | asks the NASA FIRMS API for recent detections in every region, drops the ones already stored, sends the rest to the Event Hubs stream `detections` |
| `harmonize` | Event Hubs, in batches | stores the detections, counts fire-days per cell and month, converts them to S-NPP-equivalent, recomputes anomalies |

The logic is in [`backend/firecal_api/live/`](../backend/firecal_api/live) and is tested there
(`backend/tests/test_live.py`); `function_app.py` only wires it to the triggers. `build.sh` copies that
package next to `function_app.py` and zips the result.

## Azure resources

Created once by [`infra/azure/setup-live-pipeline.sh`](../infra/azure/setup-live-pipeline.sh) in `wel3a-rg`:

- Event Hubs namespace `wel3a-events-be616` (Basic: about $0.015/hour) with the hub `detections`,
- storage account `wel3abe616live` (function package and stream checkpoints),
- function app `wel3a-live-be616` (Flex Consumption, Python 3.12) with Application Insights for logs.

Settings of the function app: `DATABASE_URL`, `FIRMS_MAP_KEY`, `EVENTHUB_CONNECTION`, `EVENTHUB_NAME`,
`POLL_SCHEDULE`, `POLL_DAYS`.

## How often it runs

`POLL_SCHEDULE` is an NCRONTAB expression (second minute hour day month weekday). FIRMS publishes new
detections within about 3 hours of a satellite pass, so anything from minutes to days makes sense:

```bash
# every hour, on the hour (default: every 15 minutes, "0 */15 * * * *")
az functionapp config appsettings set -g wel3a-rg -n wel3a-live-be616 --settings "POLL_SCHEDULE=0 0 * * * *"
# once a day at 03:00 UTC: "0 0 3 * * *"     once a month, day 1 at 03:00 UTC: "0 0 3 1 * *"
```

Each poll reads from the day before the last one it covered (at least the last `POLL_DAYS` days, default
2), so a slow schedule catches up by itself and no detection is missed, whatever the interval.

## Deploying

Merging into `main` deploys the functions when `functions/` or `backend/firecal_api/live/` changed
(`.github/workflows/deploy-azure.yml`). By hand:

```bash
functions/build.sh
az functionapp deployment source config-zip -g wel3a-rg -n wel3a-live-be616 --src functions/.build.zip --build-remote true
```

## Stopping the costs

The stream is the only part with a fixed price. To remove it: `az eventhubs namespace delete -g wel3a-rg -n wel3a-events-be616`
(the poller then fails until the namespace exists again; `live-poll --direct` from a laptop still works).
