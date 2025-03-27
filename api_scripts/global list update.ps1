# Define the API endpoints
$baseURL = "https://api.dnsfilter.com/v1/organizations/"
$orgID = "ORGID HERE" 
$getURL = $baseURL + $orgID + "/global_lists"
$patchURL = $baseURL + $orgID + "/update_global_lists"

# --- Authentication ---
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$apiUrl = "https://api.dnsfilter.com/v1"
$apiKey = "Token HERE"

# Authenticate
Invoke-WebRequest -UseBasicParsing -Uri "$apiUrl/authenticate" `
    -Method "POST" `
    -WebSession $session `
    -Headers @{
        "authority"    = "api.dnsfilter.com"
        "method"       = "POST"
        "path"         = "/v1/authenticate"
        "accept"       = "application/json, text/plain, */*"
        "authorization" = "Bearer $apiKey"
    }
# --- End Authentication ---

# Define the domains to add 
$newDomains = @(
    "newdomain1.com",
    "newdomain2.net",
    "newdomain3.org"
)

# Get the current allow list domains
$response = Invoke-RestMethod -Uri $getURL -Method Get -WebSession $session
$currentDomains = $response.data.attributes.whitelist_domains

# Add the new domains to the current list
$updatedDomains = $currentDomains + $newDomains | Sort-Object -Unique

# Construct the JSON body for the PATCH request
$body = @{
    organization = @{
        whitelist_domains = $updatedDomains
    }
} | ConvertTo-Json

# Update the allow list
Invoke-RestMethod -Uri $patchURL -Method Patch -Body $body -ContentType "application/json" -WebSession $session

Write-Host "Allow list updated successfully."