#!/usr/bin/env bash
# One-time setup so .github/workflows/deploy-azure.yml can sign in to Azure without any GitHub secret.
#
# Creates (or reuses):
#   - an Entra app registration + service principal named wel3a-github-deploy,
#   - a federated credential that trusts GitHub Actions runs on the main branch of the repo,
#   - a Contributor role assignment on the resource group wel3a-rg only.
# Then prints the client ID to paste into AZURE_CLIENT_ID in .github/workflows/deploy-azure.yml.
#
# Safe to run again: existing pieces are found and reused, nothing is duplicated.
#
# Who can run it: someone signed in with `az login` who may create app registrations in the tenant
# and create role assignments on wel3a-rg (Owner or User Access Administrator on the group or above).
#
# Contributor on the resource group is enough for the workflow:
#   - az acr build      -> Microsoft.ContainerRegistry/registries/{listBuildSourceUploadUrl,scheduleRun}/action,
#                          runs/read, runs/listLogSasUrl/action
#   - az containerapp update/show -> Microsoft.App/containerApps/{read,write,listSecrets/action}
# The registry, both container apps and their environment are all in wel3a-rg. The apps pull from the
# registry with its admin credentials (already stored as a secret on each app), so no AcrPull role is needed.
set -euo pipefail

APP_NAME="wel3a-github-deploy"
REPO="klol120/nasa-harmonization"
BRANCH="main"
TENANT_ID="19c3c702-45a1-4697-919c-5e479f4a4b55"
SUBSCRIPTION_ID="8834278b-93b5-4626-8e51-3de2d007ebc2"
RESOURCE_GROUP="wel3a-rg"

ISSUER="https://token.actions.githubusercontent.com"
AUDIENCE="api://AzureADTokenExchange"
SUBJECT="repo:${REPO}:ref:refs/heads/${BRANCH}"
CREDENTIAL_NAME="github-${BRANCH}"

log() { printf '==> %s\n' "$*" >&2; }

if ! az account show -o none 2>/dev/null; then
  echo "Not signed in. Run: az login --tenant ${TENANT_ID}" >&2
  exit 1
fi
az account set --subscription "$SUBSCRIPTION_ID"

current_tenant=$(az account show --query tenantId -o tsv)
if [ "$current_tenant" != "$TENANT_ID" ]; then
  echo "Signed in to tenant ${current_tenant}, expected ${TENANT_ID}. Run: az login --tenant ${TENANT_ID}" >&2
  exit 1
fi

SCOPE=$(az group show --name "$RESOURCE_GROUP" --query id -o tsv)

# 1. App registration
APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  log "Creating app registration ${APP_NAME}"
  APP_ID=$(az ad app create --display-name "$APP_NAME" --sign-in-audience AzureADMyOrg --query appId -o tsv)
else
  log "Reusing app registration ${APP_NAME} (${APP_ID})"
fi

# 2. Service principal
SP_ID=$(az ad sp list --filter "appId eq '${APP_ID}'" --query "[0].id" -o tsv)
if [ -z "$SP_ID" ]; then
  log "Creating service principal"
  SP_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
else
  log "Reusing service principal (${SP_ID})"
fi

# 3. Federated credential for pushes to main (and "Run workflow" on main)
existing=$(az ad app federated-credential list --id "$APP_ID" \
  --query "[?subject=='${SUBJECT}' && issuer=='${ISSUER}'].name | [0]" -o tsv)
if [ -z "$existing" ]; then
  log "Adding federated credential for ${SUBJECT}"
  az ad app federated-credential create --id "$APP_ID" -o none --parameters "{
    \"name\": \"${CREDENTIAL_NAME}\",
    \"issuer\": \"${ISSUER}\",
    \"subject\": \"${SUBJECT}\",
    \"audiences\": [\"${AUDIENCE}\"],
    \"description\": \"GitHub Actions deploys from ${REPO} on ${BRANCH}\"
  }"
else
  log "Federated credential for ${SUBJECT} already exists (${existing})"
fi

# 4. Contributor on the resource group only
assigned=$(az role assignment list --assignee "$SP_ID" --role Contributor --scope "$SCOPE" \
  --query "[0].id" -o tsv)
if [ -z "$assigned" ]; then
  log "Granting Contributor on ${RESOURCE_GROUP}"
  # A brand-new service principal can take a little while to be visible to Azure RBAC; retry.
  for attempt in 1 2 3 4 5 6; do
    if az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
      --role Contributor --scope "$SCOPE" -o none; then
      break
    fi
    if [ "$attempt" -eq 6 ]; then
      echo "Could not create the role assignment." >&2
      exit 1
    fi
    log "Retrying in 15s (attempt ${attempt}/6)"
    sleep 15
  done
else
  log "Contributor on ${RESOURCE_GROUP} already granted"
fi

cat <<EOF

Done.
  Client ID (AZURE_CLIENT_ID): ${APP_ID}
  Tenant ID:                   ${TENANT_ID}
  Subscription ID:             ${SUBSCRIPTION_ID}
  Trusted subject:             ${SUBJECT}
  Role:                        Contributor on ${SCOPE}

Next: put the client ID into .github/workflows/deploy-azure.yml, replacing __AZURE_CLIENT_ID__
(env.AZURE_CLIENT_ID near the top). From the repo root, for example:

  sed -i.bak 's/__AZURE_CLIENT_ID__/${APP_ID}/' .github/workflows/deploy-azure.yml && rm .github/workflows/deploy-azure.yml.bak

Role assignments can take a few minutes to apply; if the first run fails at "az acr build" with an
authorization error, wait and use "Re-run jobs".
EOF
