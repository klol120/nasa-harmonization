#!/bin/sh
set -e

# Create the database/schema and load any exports not yet loaded (re-loading is a no-op).
python -m firecal_api.cli init
if [ "${SKIP_INGEST:-0}" != "1" ]; then
  python -m firecal_api.cli ingest || echo "ingest reported problems; serving whatever is loaded"
fi

# Weather: first load files exported from another deployment (if any), then fetch whatever is still
# missing from Meteomatics. The fetch runs beside the API, fills only months not stored yet and stops
# at METEOMATICS_DAILY_CAP requests per day, so restarting the container is cheap.
if [ -n "${WEATHER_DIR:-}" ] && ls "$WEATHER_DIR"/*.json >/dev/null 2>&1; then
  python -m firecal_api.cli weather-import "$WEATHER_DIR" || echo "weather import reported problems"
fi
if [ -n "${METEOMATICS_USER:-}" ] && [ "${WEATHER_FETCH:-1}" != "0" ]; then
  python -m firecal_api.cli weather-fetch &
else
  echo "weather: METEOMATICS_USER not set (or WEATHER_FETCH=0); serving stored weather only"
fi

exec "$@"
