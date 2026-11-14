#!/bin/sh
set -e

# Create the database/schema and load any exports not yet loaded (re-loading is a no-op).
python -m firecal_api.cli init
if [ "${SKIP_INGEST:-0}" != "1" ]; then
  python -m firecal_api.cli ingest || echo "ingest reported problems; serving whatever is loaded"
fi

exec "$@"
