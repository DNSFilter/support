# Set API Key and Headers
$apikey = 'xxx'
$headers = New-Object "System.Collections.Generic.Dictionary[[String],[String]]"
$headers.Add("Accept", "application/json")
$headers.Add("Authorization", "$apikey")

Write-Host "Fetching category data..."

# Fetch categories
$categoryResponse = Invoke-RestMethod 'https://api.dnsfilter.com/v1/categories/all?' -Method 'GET' -Headers $headers

# Define CSV file for categories
$categoriesCsv = "C:\Windows\Temp\categories.csv"

# Write category headers
"CategoryID,CategoryName" | Out-File -FilePath $categoriesCsv -Encoding utf8

# Write categories to CSV
foreach ($item in $categoryResponse.data) {
    if ($item.type -eq "categories") {
        "$($item.id),$($item.attributes.name)" | Out-File -FilePath $categoriesCsv -Encoding utf8 -Append
    }
}
Write-Host "Category data saved to $categoriesCsv"

# Fetch organizations separately
Write-Host "Fetching organizations..."
$orgResponse = Invoke-RestMethod 'https://api.dnsfilter.com/v1/organizations/all?basic_info=True' -Method 'GET' -Headers $headers 

if (-not $orgResponse.data) {
    Write-Host "No organizations found or API access issue."
    exit
}

Write-Host "Organizations retrieved, processing policies..."

# Define CSV file for final report
$orgPoliciesCsv = "C:\Windows\Temp\policy_audit.csv"

# Write headers for final CSV
"OrganizationName,OrganizationID,PolicyName,PolicyDescription,WhitelistDomains,BlacklistDomains,BlacklistCategories,GoogleSafeSearch,BingSafeSearch,DuckDuckGoSafeSearch,EcosiaSafeSearch,YandexSafeSearch,YouTubeRestricted,YouTubeRestrictedLevel,Interstitial,IsGlobalPolicy" | Out-File -FilePath $orgPoliciesCsv -Encoding utf8

# Process each organization
foreach ($org in $orgResponse.data) {
    $orgName = $org.attributes.name
    $orgId = $org.id
    Write-Host "Processing organization: $orgName (ID: $orgId)"
    
    # Fetch policies for the organization
    Write-Host "Fetching policies for organization ID: $orgId"
    $policyResponse = Invoke-RestMethod "https://api.dnsfilter.com/v1/policies/all?include_global_policies=true&organization_id=$orgId&number=1&size=10" -Method 'GET' -Headers $headers

    foreach ($policy in $policyResponse.data) {
        $policyName = $policy.attributes.name
        $policyDescription = $policy.attributes.description

        # Extract additional attributes
        $whitelistDomains = $policy.attributes.whitelist_domains -join '; '
        $blacklistDomains = $policy.attributes.blacklist_domains -join '; '

        # Convert blacklist category IDs to names
        $blacklistCategories = @()
        if ($policy.attributes.blacklist_categories) {
            foreach ($categoryId in $policy.attributes.blacklist_categories) {
                $categoryId = "$categoryId"  # Convert to string
                $categoryName = (Import-Csv -Path $categoriesCsv | Where-Object { $_.CategoryID -eq $categoryId }).CategoryName
                if ($categoryName) {
                    $blacklistCategories += $categoryName
                } else {
                    $blacklistCategories += "Unknown Category ($categoryId)"
                }
            }
        }
        $blacklistCategories = $blacklistCategories -join '; '

        # Other settings
        $googleSafeSearch = $policy.attributes.google_safesearch
        $bingSafeSearch = $policy.attributes.bing_safe_search
        $duckDuckGoSafeSearch = $policy.attributes.duck_duck_go_safe_search
        $ecosiaSafeSearch = $policy.attributes.ecosia_safesearch
        $yandexSafeSearch = $policy.attributes.yandex_safe_search
        $youtubeRestricted = $policy.attributes.youtube_restricted
        $youtubeRestrictedLevel = $policy.attributes.youtube_restricted_level
        $interstitial = $policy.attributes.interstitial
        $isGlobalPolicy = $policy.attributes.is_global_policy

        # Append data to CSV
        "$orgName,$orgId,$policyName,$policyDescription,$whitelistDomains,$blacklistDomains,$blacklistCategories,$googleSafeSearch,$bingSafeSearch,$duckDuckGoSafeSearch,$ecosiaSafeSearch,$yandexSafeSearch,$youtubeRestricted,$youtubeRestrictedLevel,$interstitial,$isGlobalPolicy" | Out-File -FilePath $orgPoliciesCsv -Encoding utf8 -Append
    }
}

Write-Host "Final policy report saved to $orgPoliciesCsv"
