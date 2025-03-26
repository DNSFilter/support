 # DNSFilter Bulk Import Tool for Organizations and Sites
# Created by Jesse Eddy & Rick Cohen
# Last edited on 12/07/2023 - generate SSK after creating network
#                11/14/2023 - added external_id
#                07/03/2023 - Added physical_address


# Example of CSV for import:
#   orgName,networkName,ipAddresses,physicalAddress,externalId
#   Organization 1,Network 1,123.456.789.123,"123 1st St, Wichita KS, 67213", "External_id 1"
#   Organization 1,Network 2,123.456.789.124,"456 1st St, Wichita KS, 67213", "External_id 2"
#   Organization 2,Network 1,123.456.789.125,"789 1st St, Wichita KS, 67213", "External_id 3"
#   Organization 2,Network 2,123.456.789.126,"134 1st St, Wichita KS, 67213", "External_id 4"

# This script does not support CIDR

# Initialize WebRequest session
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$apiUrl = "https://api.dnsfilter.com/v1"
$apiKey = "API_Token"

# Authenticate with DNSFilter API
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


# Set variables
$mspid = "YOUR MSPID"
$orgs_csv = 'path\to\csv'

# Read organizations data from CSV
$orgs = Import-Csv -Path $orgs_csv

# Get a list of existing organizations from DNSFilter API
$existingOrgs = (Invoke-WebRequest -UseBasicParsing -Uri "$apiUrl/organizations" -WebSession $session).content | ConvertFrom-Json

# Extract organization names from the existing data
$orgNames = $existingOrgs.data.attributes | Select-Object -ExpandProperty name

# Iterate through each row in the CSV
foreach ($row in $orgs) {

    # Check if the organization already exists
    if ($orgNames -notcontains $row.orgname) {

        # Create a new organization
        $orgBody = @{"name" = $row.orgName; "managed_by_msp_id" = $mspid}
        $orgResponse = Invoke-RestMethod -Uri "$apiUrl/organizations" -Method POST -Headers @{"Authorization" = "Bearer $apiKey"} -Body ($orgBody | ConvertTo-Json) -ContentType "application/json"

        # Add the created organization name to $orgNames
        $orgNames += $row.orgName
    } 
    
    # Refresh the list of existing organizations
    $existingOrgs = (Invoke-WebRequest -UseBasicParsing -Uri "$apiUrl/organizations" -WebSession $session).content | ConvertFrom-Json  

    # Get the organization ID by its name
    $orgId = ($existingOrgs.data | Where-Object {$_.attributes.name -eq $row.orgname}).id
    
    # Check if the network already exists within the same organization
    $existingNetworks = (Invoke-WebRequest -UseBasicParsing -Uri "$apiUrl/networks" -WebSession $session).content | ConvertFrom-Json 
    $orgNetworks = $existingNetworks.data | Where-Object {$_.relationships.organization.data.id -eq $orgId}
    $networkName = $orgNetworks.attributes | Select-Object -ExpandProperty name

    if ($networkName -notcontains $row.networkName) {
        # Create a new network with the name from the CSV
        $networkBody = @{ "network" = @{"name" = $row.networkName; "organization_id" = $orgId; "physical_address" = $row.physicalAddress; "external_id" = $row.externalId}}
        $networkResponse = Invoke-RestMethod -Uri "$apiUrl/networks" -Method POST -Headers @{"Authorization" = "Bearer $apiKey"} -Body ($networkBody | ConvertTo-Json) -ContentType "application/json"
       
    }

    # Refresh the list of networks within the organization
    $existingNetworks = (Invoke-WebRequest -UseBasicParsing -Uri "$apiUrl/networks" -WebSession $session).content | ConvertFrom-Json 
    $orgNetworks = $existingNetworks.data | Where-Object {$_.relationships.organization.data.id -eq $orgId}

    # Get the network ID by its name
    $networkId = ($orgNetworks | Where-Object {$_.attributes.name -eq $row.networkName}).id
    

    # Generate a site secret key for the newly created network
    Invoke-RestMethod -Method Post -Uri https://api.dnsfilter.com/v1/networks/$networkid/secret_key -Headers @{"Authorization" = "Bearer $apiKey"} -Body ""


    # Create IP address for the network
    $ipBody = @{ "ip_address" = @{ "address" = $row.ipAddresses; "network_id" = $networkId; "organization_id" = $orgId}}
    $ipResponse = Invoke-RestMethod -Uri "$apiUrl/ip_addresses" -Method POST -Headers @{"Authorization" = "Bearer $apiKey"} -Body ($ipBody | ConvertTo-Json) -ContentType "application/json"
}      

# Update the list of organization names after all organizations have been checked and created
$orgNames += $orgs.orgName

 
 
