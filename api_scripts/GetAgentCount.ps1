$statuses = @("active", "disabled")
$apiKey = "xxx"

$headers = @{
  "Authorization" = "Bearer $apiKey"
  "Accept"        = "application/json"
}

$allData = @()
$statusSummary = @{}

foreach ($status in $statuses) {
    Write-Host "`nProcessing status: $status" -ForegroundColor Cyan
    $apiUrl = "https://api.dnsfilter.com/v1/user_agents/all?status=$status"
    $response = Invoke-RestMethod -Uri $apiUrl -Headers $headers -Method Get

    if ($response -and $response.data) {
        foreach ($agent in $response.data) {
            $networkId = $agent.relationships.network.data.id
            $networkUrl = "https://api.dnsfilter.com/v1/networks/$networkId"
           try {
    $networkResponse = Invoke-RestMethod -Uri $networkUrl -Headers $headers -Method Get -ErrorAction Stop
    # Proceed with processing $networkResponse
} catch {
    Write-Host "Network ID $networkId not found. Skipping agent '$($agent.attributes.hostname)'." -ForegroundColor Yellow
    continue
}

            if ($networkResponse -and $networkResponse.data) {
                $deletedAt = $networkResponse.data.attributes.deleted_at
                if ([string]::IsNullOrEmpty($deletedAt)) {
                    $allData += $agent
                    if ($statusSummary.ContainsKey($status)) {
                        $statusSummary[$status] += 1
                    } else {
                        $statusSummary[$status] = 1
                    }
                } else {
                    Write-Host "Excluded agent '$($agent.attributes.hostname)' from deleted network ID $networkId." -ForegroundColor Yellow
                }
            } else {
                Write-Host "Failed to retrieve network details for network ID $networkId." -ForegroundColor Red
            }
        }
    } else {
        Write-Host "No data returned for status: $status" -ForegroundColor Magenta
        $statusSummary[$status] = 0
    }
}

if ($allData.Count -gt 0) {
    $sortedData = $allData | Sort-Object { $_.attributes.network_name }

    Write-Host "`nFiltered User Agents:" -ForegroundColor Green
    foreach ($agent in $sortedData) {
        Write-Host "Organization: $($agent.attributes.network_name), Hostname: $($agent.attributes.hostname), Status: $($agent.attributes.status)"
    }

    Write-Host "`nTotal number of hosts after filtering: $($sortedData.Count)" -ForegroundColor Green
    Write-Host "Summary by status after filtering:" -ForegroundColor Green
    foreach ($status in $statuses) {
        $count = if ($statusSummary.ContainsKey($status)) { $statusSummary[$status] } else { 0 }
        Write-Host "${status}: $count"
    }
} else {
    Write-Host "No data returned from API for any status after filtering." -ForegroundColor Red
}
