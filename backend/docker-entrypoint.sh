#!/bin/sh
set -e

# Pipeline status file (docker compose): rewritten by the pipeline container at the end of every run.
status_mtime() { stat -c %Y "$PIPELINE_STATUS" 2>/dev/null || echo 0; }
[ -n "${PIPELINE_STATUS:-}" ] && seen=$(status_mtime)

# Create the database/schema and load any exports not yet loaded (re-loading is a no-op).
python -m firecal_api.cli init
if [ "${SKIP_INGEST:-0}" != "1" ]; then
  python -m firecal_api.cli ingest || echo "ingest reported problems; serving whatever is loaded"
fi

# When the pipeline finishes a run, load its new exports (each becomes the region's current release while
# the API keeps serving). Polls only the status file, so a half-written export is never read.
if [ -n "${PIPELINE_STATUS:-}" ] && [ "${SKIP_INGEST:-0}" != "1" ]; then
  (
    while sleep "${PIPELINE_POLL_S:-30}"; do
      now=$(status_mtime)
      if [ "$now" != "$seen" ]; then
        seen=$now
        echo "pipeline: a run finished; loading new exports"
        python -m firecal_api.cli ingest || echo "ingest reported problems; serving whatever is loaded"
      fi
    done
  ) &
fi

# Weather: first load files exported from another deployment (if any), then fetch whatever is still
# missing from Meteomatics. The fetch runs beside the API, fills only months not stored yet and stops
# at METEOMATICS_DAILY_CAP requests per day, so restarting the container is cheap.
if [ -n "${WEATHER_DIR:-}" ] && ls "$WEATHER_DIR"/*.json >/dev/null 2>&1; then
  python -m firecal_api.cli weather-import "$WEATHER_DIR" || echo "weather import reported problems"
fi
if [ -n "${METEOMATICS_USER:-}" ] && [ "${WEATHER_FETCH:-1}" != "0" ] && [ "${WEATHER_SCHEDULE:-0}" = "1" ]; then
  # docker compose: fetch once if never finished, then monthly, saving to WEATHER_DIR (firecal_api/schedule.py).
  python -m firecal_api.cli weather-schedule &
elif [ -n "${METEOMATICS_USER:-}" ] && [ "${WEATHER_FETCH:-1}" != "0" ]; then
  # During a deploy the old container may still hold the fetch lock for a while: wait for it, then continue.
  python -m firecal_api.cli weather-fetch --wait-lock 900 &
else
  echo "weather: METEOMATICS_USER not set (or WEATHER_FETCH=0); serving stored weather only"
fi

exec "$@"
