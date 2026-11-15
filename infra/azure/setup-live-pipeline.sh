#!/usr/bin/env bash
# One-time setup of the live pipeline on Azure (see functions/ and backend/firecal_api/live/).
#
#   FIRMS API --> poll_firms (Function, timer) --> Event Hubs "detections" --> harmonize (Function) --> PostgreSQL
#
# Creates (or reuses) in the resource group:
#   - an Event Hubs namespace (Basic, 1 throughput unit: about $0.015/hour) with the hub "detections",
#   - a storage account (needed by Azure Functions for its package and stream checkpoints),
#   - a Function app on the Flex Consumption plan (pay per execution; this workload stays in the free grant).
# Then stores the settings the functions need. Safe to run again.
#
# Needs: az login, and in the environment:
#   FIRMS_MAP_KEY   NASA FIRMS key (https://firms.modaps.eosdis.nasa.gov/api/map_key/)
#   DATABASE_URL    PostgreSQL of the API (with ?sslmode=require); default: the API container app's db-url secret
#
# To stop paying for the stream after an event: az eventhubs namespace delete -g "$RESOURCE_GROUP" -n "$NAMESPACE"
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-wel3a-rg}"
LOCATION="${LOCATION:-francecentral}"
SUFFIX="${SUFFIX:-be616}"
NAMESPACE="${NAMESPACE:-wel3a-events-$SUFFIX}"
HUB="${HUB:-detections}"
STORAGE="${STORAGE:-wel3a${SUFFIX}live}"
APP="${APP:-wel3a-live-$SUFFIX}"
API_APP="${API_APP:-wel3a-api}"
POLL_SCHEDULE="${POLL_SCHEDULE:-0 */15 * * * *}"

log() { printf '==> %s\n' "$*" >&2; }
: "${FIRMS_MAP_KEY:?set FIRMS_MAP_KEY}"

if [ -z "${DATABASE_URL:-}" ]; then
  log "reading the database URL from the $API_APP container app"
  DATABASE_URL=$(az containerapp secret show -n "$API_APP" -g "$RESOURCE_GROUP" --secret-name db-url --query value -o tsv)
fi

for p in Microsoft.EventHub Microsoft.Web Microsoft.Storage Microsoft.Insights; do
  [ "$(az provider show -n "$p" --query registrationState -o tsv)" = "Registered" ] || az provider register -n "$p" --wait -o none
done

log "Event Hubs namespace $NAMESPACE (Basic) and hub $HUB"
az eventhubs namespace show -g "$RESOURCE_GROUP" -n "$NAMESPACE" -o none 2>/dev/null ||
  az eventhubs namespace create -g "$RESOURCE_GROUP" -n "$NAMESPACE" -l "$LOCATION" --sku Basic --capacity 1 -o none
az eventhubs eventhub show -g "$RESOURCE_GROUP" --namespace-name "$NAMESPACE" --name "$HUB" -o none 2>/dev/null ||
  az eventhubs eventhub create -g "$RESOURCE_GROUP" --namespace-name "$NAMESPACE" --name "$HUB" --partition-count 1 \
    --cleanup-policy Delete --retention-time-in-hours 24 -o none
az eventhubs namespace authorization-rule show -g "$RESOURCE_GROUP" --namespace-name "$NAMESPACE" --name pipeline -o none 2>/dev/null ||
  az eventhubs namespace authorization-rule create -g "$RESOURCE_GROUP" --namespace-name "$NAMESPACE" --name pipeline --rights Send Listen -o none
EVENTHUB_CONNECTION=$(az eventhubs namespace authorization-rule keys list -g "$RESOURCE_GROUP" --namespace-name "$NAMESPACE" --name pipeline \
  --query primaryConnectionString -o tsv)

log "storage account $STORAGE"
az storage account show -g "$RESOURCE_GROUP" -n "$STORAGE" -o none 2>/dev/null ||
  az storage account create -g "$RESOURCE_GROUP" -n "$STORAGE" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 \
    --min-tls-version TLS1_2 --allow-blob-public-access false -o none

log "function app $APP (Flex Consumption, Python 3.12)"
az functionapp show -g "$RESOURCE_GROUP" -n "$APP" -o none 2>/dev/null ||
  az functionapp create -g "$RESOURCE_GROUP" -n "$APP" --storage-account "$STORAGE" \
    --flexconsumption-location "$LOCATION" --runtime python --runtime-version 3.12 -o none

log "settings"
az functionapp config appsettings set -g "$RESOURCE_GROUP" -n "$APP" -o none --settings \
  "DATABASE_URL=$DATABASE_URL" "FIRMS_MAP_KEY=$FIRMS_MAP_KEY" "EVENTHUB_CONNECTION=$EVENTHUB_CONNECTION" \
  "EVENTHUB_NAME=$HUB" "POLL_SCHEDULE=$POLL_SCHEDULE" "POLL_DAYS=2"

log "done. Deploy the code with: functions/build.sh && az functionapp deployment source config-zip -g $RESOURCE_GROUP -n $APP --src functions/.build.zip --build-remote true"
log "to send to the stream from a laptop (demo replay), put this in backend/.env:"
echo "EVENTHUB_NAME=$HUB"
echo "EVENTHUB_CONNECTION=<az eventhubs namespace authorization-rule keys list -g $RESOURCE_GROUP --namespace-name $NAMESPACE --name pipeline --query primaryConnectionString -o tsv>"
