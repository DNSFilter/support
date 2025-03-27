 $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$apiUrl = "https://api.dnsfilter.com/v1"
$apiKey = "API-Token"

# Authenticate
Invoke-WebRequest -UseBasicParsing -Uri "$apiUrl/authenticate" `
    -Method "POST" `
    -WebSession $session `
    -Headers @{
    "authority"     = "api.dnsfilter.com"
    "method"        = "POST"
    "path"          = "/v1/authenticate"
    "accept"        = "application/json, text/plain, */*"
    "authorization" = "Bearer $apiKey"
};

# Read the network IDs from a CSV file
$csvData = Import-Csv -Path "path\to\networkids.csv"

# Loop through each network ID and perform the API call
#$csvData | ForEach-Object {
    $networkId = 7854800

    # Get the current local domains for the network
    $response = Invoke-RestMethod -Uri "$apiUrl/networks/$networkId" -Method GET -Headers @{"Authorization" = "Bearer $apiKey"}
    $localDomains = $response.data.attributes.local_domains

    # Add the new local domains to the existing ones
    $localDomains += @("apdev.hasbrodev.com",
  "aptest.hasbrotest.com",
  "arc.azure.com",
  "azmk8s.io",
  "azure-automation.net",
  "azure.com",
  "azure.net",
  "azuredatabricks.net",
  "azurewebsites.net",
  "blob.core.windows.net",
  "bouldermedia.tv",
  "Core.windows.net",
  "documents.azure.com",
  "dp.kubernetesconfiguration.azure.com",
  "entertainmentone.ca",
  "eudev.hasbrodev.com",
  "guestconfiguration.azure.com",
  "hasb.ro",
  "hasbro.com",
  "hasbrodev.com",
  "hasbroiberia.com",
  "hasbrotest.com",
  "hosting-hasbro.com",
  "hweb.com",
  "na.hasbro.com",
  "nadev.hasbrodev.com",
  "natest.hasbrotest.com",
  "onlinegaming.local",
  "privatelink.5.azurestaticapps.net",
  "privatelink.api.azureml.ms",
  "privatelink.azurewebsites.net",
  "privatelink.blob.core.windows.net",
  "privatelink.database.windows.net",
  "privatelink.documents.azure.com",
  "privatelink.notebooks.azure.net",
  "privatelink.servicebus.windows.net",
  "privatelink.vaultcore.azure.com",
  "saucelabs.com",
  "scm.azurewebsites.net",
  "scm.privatelink.azurewebsites.net",
  "servicebus.windows.net",
  "vault.azure.net",
  "windows.net",
  "wzdev.hasbrodev.com",
  "wztest.hasbrotest.com")

    # Create the API request to update the network with the new data
    $networkBody = @{
        "network" = @{
            "id" = $networkId
            "type" = "networks"
            "local_domains" = $localDomains
        }
    }

    # Send the API request to update the network
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/networks/$networkId" -Method PUT -Headers @{"Authorization" = "Bearer $apiKey"} -Body ($networkBody | ConvertTo-Json -Depth 10) -ContentType "application/json"
    } catch {
        Write-Host "Status code: $($_.Exception.Response.StatusCode.value__)"
        Write-Host "Status description: $($_.Exception.Response.StatusDescription)"
        Write-Host "Error message: $($_.Exception.Message)"
        $streamReader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        Write-Host "Response content: $($streamReader.ReadToEnd())"
    }


# Print the response
$response
 
