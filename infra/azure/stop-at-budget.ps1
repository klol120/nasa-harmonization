<#
  Spending guard for the Phoenical resources in wel3a-rg (Azure Automation runbook, PowerShell 7.2).

  Stops everything that costs money by the hour when the cost since 2026-11-01 reaches the limit:
    - PostgreSQL wel3a-pg-be616        stopped (Azure starts a stopped server again after 7 days;
                                        the scheduled run stops it again)
    - Container Apps wel3a-api, -web   stopped (the website goes offline)
    - Function app wel3a-live-be616    stopped (the live pipeline pauses)
    - Container instance wel3a-world   stopped
    - Event Hubs wel3a-events-be616    DELETED (it cannot be paused; recreate it with
                                        infra/azure/setup-live-pipeline.sh)
  Storage, the image registry and the database's disk keep their data (a few cents a day).

  Triggers: the budget's $150 alert calls this runbook's webhook; a schedule runs it every 6 hours as a
  backstop (it reads the cost itself); a one-off schedule runs it with -Force. -DryRun only reports.
#>
param(
  [object] $WebhookData,
  [bool]   $DryRun = $false,
  [bool]   $Force = $false,
  [double] $Limit = 150
)
$ErrorActionPreference = "Stop"
Connect-AzAccount -Identity | Out-Null
$sub = (Get-AzContext).Subscription.Id
$rg = "/subscriptions/$sub/resourceGroups/wel3a-rg/providers"

# Cost since 2026-11-01, all services (Cost Management; its figures lag by up to a day).
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$query = @{ type = "ActualCost"; timeframe = "Custom"; timePeriod = @{ from = "2026-11-01T00:00:00Z"; to = $now };
            dataset = @{ granularity = "None"; aggregation = @{ totalCost = @{ name = "Cost"; function = "Sum" } } } } | ConvertTo-Json -Depth 6
$cost = $null
foreach ($try in 1..5) {
  $r = Invoke-AzRestMethod -Method POST -Path "/subscriptions/$sub/providers/Microsoft.CostManagement/query?api-version=2023-11-01" -Payload $query
  if ($r.StatusCode -eq 200) { $cost = [double](($r.Content | ConvertFrom-Json).properties.rows[0][0]); break }
  Start-Sleep -Seconds (30 * $try)
}
$fromAlert = $null -ne $WebhookData
Write-Output ("cost since 2026-11-01: {0} USD, limit {1} USD, from budget alert: {2}, force: {3}" -f $(if ($null -eq $cost) { "unknown" } else { [math]::Round($cost, 2) }), $Limit, $fromAlert, $Force)

if (-not ($Force -or $fromAlert -or ($null -ne $cost -and $cost -ge $Limit))) {
  Write-Output "under the limit: nothing to do"
  return
}

$actions = @(
  @{ m = "POST";   p = "$rg/Microsoft.DBforPostgreSQL/flexibleServers/wel3a-pg-be616/stop?api-version=2022-12-01"; what = "stop the database" },
  @{ m = "POST";   p = "$rg/Microsoft.App/containerApps/wel3a-api/stop?api-version=2024-03-01";                  what = "stop the API" },
  @{ m = "POST";   p = "$rg/Microsoft.App/containerApps/wel3a-web/stop?api-version=2024-03-01";                  what = "stop the website" },
  @{ m = "POST";   p = "$rg/Microsoft.Web/sites/wel3a-live-be616/stop?api-version=2023-12-01";                   what = "stop the live functions" },
  @{ m = "POST";   p = "$rg/Microsoft.ContainerInstance/containerGroups/wel3a-world/stop?api-version=2023-05-01"; what = "stop the world pull container" },
  @{ m = "DELETE"; p = "$rg/Microsoft.EventHub/namespaces/wel3a-events-be616?api-version=2024-01-01";             what = "delete the Event Hubs namespace" }
)
foreach ($a in $actions) {
  if ($DryRun) { Write-Output "dry run: would $($a.what)"; continue }
  try {
    $r = Invoke-AzRestMethod -Method $a.m -Path $a.p
    Write-Output ("{0}: HTTP {1}" -f $a.what, $r.StatusCode)
  } catch {
    Write-Output ("{0}: failed ({1})" -f $a.what, $_.Exception.Message)
  }
}
Write-Output "spending guard: done"
