Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Secure API Key Input
function Get-ApiKey {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "DNSFilter API Key"
    $form.Width = 400
    $form.Height = 150
    $form.StartPosition = "CenterScreen"
    $form.TopMost = $true
    $form.Add_Shown({ $form.Activate() })

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "Enter your DNSFilter API key:"
    $label.Left = 10
    $label.Top = 10
    $label.Width = 360
    $form.Controls.Add($label)

    $textbox = New-Object System.Windows.Forms.TextBox
    $textbox.Left = 10
    $textbox.Top = 35
    $textbox.Width = 360
    $textbox.UseSystemPasswordChar = $true
    $form.Controls.Add($textbox)

    $okButton = New-Object System.Windows.Forms.Button
    $okButton.Text = "OK"
    $okButton.Left = 210
    $okButton.Top = 70
    $okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $okButton
    $form.Controls.Add($okButton)

    $cancelButton = New-Object System.Windows.Forms.Button
    $cancelButton.Text = "Cancel"
    $cancelButton.Left = 290
    $cancelButton.Top = 70
    $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $cancelButton
    $form.Controls.Add($cancelButton)

    if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK -or [string]::IsNullOrWhiteSpace($textbox.Text)) {
        Write-Host "No API key entered. Exiting script."
        exit 1
    }

    return $textbox.Text
}


# Prompt user to select HAR file
function Get-FileDialog {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Select HAR file"
    $dialog.Filter = "HAR files (*.har)|*.har"
    $dialog.InitialDirectory = [Environment]::GetFolderPath("Desktop")
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host " No file selected. Exiting script."
        exit 1
    }
    return $dialog.FileName
}

# Prompt user to choose where to save the CSV
function Get-SaveFileDialog {
    $dialog = New-Object System.Windows.Forms.SaveFileDialog
    $dialog.Title = "Save CSV Report"
    $dialog.Filter = "CSV files (*.csv)|*.csv"
    $dialog.DefaultExt = "csv"
    $dialog.FileName = "HARAudit" + (Get-Date -Format "yyyyMMdd_HHmm") + ".csv"
    $dialog.InitialDirectory = [Environment]::GetFolderPath("Desktop")
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "No save path selected. Exiting script."
        exit 1
    }
    return $dialog.FileName
}

# Prompt user and set paths
$harPath = Get-FileDialog
$outputCsv = Get-SaveFileDialog
$apiKey = Get-ApiKey
$headers = @{ "Accept" = "application/json"; "Authorization" = "Bearer $apiKey" }

# Category cache setup
$lookupCachePath = "$env:TEMP\dnsfilter_category_cache.json"
$fqdnToCategories = @{}
if (Test-Path $lookupCachePath) {
    try {
        $fqdnRaw = Get-Content $lookupCachePath -Raw | ConvertFrom-Json
        $fqdnRaw.PSObject.Properties | ForEach-Object {
            $fqdnToCategories[$_.Name] = $_.Value
        }
    } catch {
        Write-Warning "Failed to load cached category data."
    }
}

# Known subnets to flag in loopback results
$targetSubnets = @(
    @{ Subnet = [IPAddress]"45.253.131.0"; Mask = [IPAddress]"255.255.255.0" },  # /16
    @{ Subnet = [IPAddress]"45.54.0.0";     Mask = [IPAddress]"255.255.0.0" }    # /16
)

# Explicit category IPs
$debugIPs   = @("45.253.131.16")
$errorIPs   = @("45.253.131.216", "45.54.28.16")
$unknownIPs = @("45.253.131.226", "45.253.131.236")

# Checks if an IP falls within a given subnet and mask
function InSubnet($ip, $subnet, $mask) {
    try {
        $b1 = ([IPAddress]$ip).GetAddressBytes()
        $b2 = $subnet.GetAddressBytes()
        $m  = $mask.GetAddressBytes()
        for ($i = 0; $i -lt 4; $i++) {
            if (($b1[$i] -band $m[$i]) -ne ($b2[$i] -band $m[$i])) { return $false }
        }
        return $true
    } catch { return $false }
}

# Checks if an IP matches any known subnet
function InAnyTargetSubnet($ip) {
    foreach ($target in $targetSubnets) {
        if (InSubnet $ip $target.Subnet $target.Mask) {
            return $true
        }
    }
    return $false
}

# Parse HAR
$har = Get-Content $harPath -Raw | ConvertFrom-Json
$entries = $har.log.entries
$fqdnToUrls = @{}
$ipToMeta = @{}

foreach ($entry in $entries) {
    try {
        $uri = [Uri]$entry.request.url
        $fqdn = $uri.Host
        $url = $uri.AbsoluteUri
        $ip = $entry.serverIPAddress
        $status = $entry.response.status
        $time = $entry.time
        $timestamp = $entry.startedDateTime

        if (!$fqdnToUrls.ContainsKey($fqdn)) { $fqdnToUrls[$fqdn] = @() }
        $fqdnToUrls[$fqdn] += $url

        if ($ip -and $ip -match '\d+\.\d+\.\d+\.\d+') {
            if (!$ipToMeta.ContainsKey($ip)) {
                $ipToMeta[$ip] = @{
                    FQDNs = New-Object System.Collections.Generic.HashSet[string]
                    URLs = @()
                    Statuses = @()
                    HasError = $false
                    Times = @()
                    StartTimes = @()
                }
            }
            $null = $ipToMeta[$ip].FQDNs.Add($fqdn)
            $ipToMeta[$ip].URLs += $url
            $ipToMeta[$ip].Statuses += $status
            $ipToMeta[$ip].Times += [double]$time
            $ipToMeta[$ip].StartTimes += [datetime]$timestamp
            if ($status -ge 400 -or $time -gt 3000) { $ipToMeta[$ip].HasError = $true }
        }
    } catch {}
}


# Lookup FQDN Categories with Caching
$fqdnToCategories = @{}
$lookupCachePath = "$env:TEMP\dnsfilter_category_cache.json"

if (Test-Path $lookupCachePath) {
    try {
        $fqdnRaw = Get-Content $lookupCachePath -Raw | ConvertFrom-Json
        $fqdnRaw.PSObject.Properties | ForEach-Object {
            $fqdnToCategories[$_.Name] = $_.Value
        } | Out-Null
    } catch {
        Write-Warning "Failed to load cached category data."
    }
}

# Collect all unique FQDNs
$allFqdns = ($ipToMeta.Values | ForEach-Object { $_.FQDNs }) -join ',' -split ',' | ForEach-Object { $_.Trim() } | Sort-Object -Unique
$uncachedFqdns = $allFqdns | Where-Object { -not $fqdnToCategories.ContainsKey($_) }

$null = "Fetching category list..."
$null = "Cached: $($fqdnToCategories.Count), Uncached: $($uncachedFqdns.Count)"

# Bulk lookup uncached FQDNs
$chunkSize = 100
if ($uncachedFqdns.Count -gt 0) {
    for ($i = 0; $i -lt $uncachedFqdns.Count; $i += $chunkSize) {
        $chunk = $uncachedFqdns[$i..([Math]::Min($i + $chunkSize - 1, $uncachedFqdns.Count - 1))]
        $uri = 'https://api.dnsfilter.com/v1/domains/bulk_lookup?fqdns=' + ($chunk -join ',')
        try {
            $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method GET
            foreach ($fqdn in $response.data.PSObject.Properties.Name) {
                $domain = $response.data.$fqdn
                $categoryIds = $domain.relationships.categories.data.id
                $categoryNames = $categoryIds | ForEach-Object { $categoryHashTable["$_"] }
                $fqdnToCategories[$fqdn] = $categoryNames -join '; '
            }
        } catch {
            Write-Warning " Category lookup failed for chunk: $_"
        }
        Start-Sleep -Milliseconds 500
    }
    $fqdnToCategories | ConvertTo-Json -Compress | Set-Content -Path $lookupCachePath -Encoding UTF8
}


# Build final results
$results = @()
foreach ($ip in $ipToMeta.Keys) {
    $meta = $ipToMeta[$ip]
    $fqdnList = ($meta.FQDNs | Sort-Object) -join ", "
    $urlList = ($meta.URLs | Sort-Object -Unique) -join "; "
    $statuses = ($meta.Statuses | Sort-Object -Unique) -join ", "
    $avgTimeMs = "{0:N0}" -f (($meta.Times | Measure-Object -Average).Average)
    $maxTimeMs = "{0:N0}" -f (($meta.Times | Measure-Object -Maximum).Maximum)
    $firstSeen = ($meta.StartTimes | Sort-Object)[0]
     # --- GEOLOCATION ---
    $country = $region = $city = $isp = $lat = $lon = $geoError = ""
    $geoStatus = "Failed"
     try {
        $geo = Invoke-RestMethod -Uri "http://ip-api.com/json/$ip"
        if ($geo.status -eq "success") {
            $geoStatus = "Success"
            $country = $geo.country
            $region = $geo.regionName
            $city = $geo.city
            $isp = $geo.isp
            $lat = $geo.lat
            $lon = $geo.lon
        } else {
            $geoError = $geo.message
        }
    } catch {
        $geoError = $_.Exception.Message
    }

    $loopbackResult = @()
    $loopbackErrorFlags = @()
    foreach ($fqdn in $meta.FQDNs) {
    try {
        $res = Resolve-DnsName -Name $fqdn -Server "127.0.0.2" -ErrorAction Stop
        $aRecords = ($res | Where-Object { $_.Type -eq "A" }).IPAddress

        if ($aRecords) {
            $loopbackResult += "$fqdn → $($aRecords -join ', ')"

            foreach ($resolvedIp in $aRecords) {
                if ($debugIPs -contains $resolvedIp) {
                    $loopbackErrorFlags += "Match (debug)"
                } elseif ($errorIPs -contains $resolvedIp) {
                    $loopbackErrorFlags += "Match (error)"
                } elseif ($unknownIPs -contains $resolvedIp) {
                    $loopbackErrorFlags += "Match (unknown)"
                } elseif (InTargetSubnet $resolvedIp) {
                    $loopbackErrorFlags += "Subnet match"
                }
            }
        } else {
            $loopbackResult += "$fqdn → NO A record"
        }

    } catch {
        if ($_.Exception.Message -match "timed out" -or $_.Exception.Message -match "Timeout") {
            $loopbackErrorFlags += "Timeout"
        } else {
            $loopbackErrorFlags += "DNS failure"
        }
        $loopbackResult += "$fqdn → FAILED: $_"
    }
}


    $loopbackError = if ($loopbackErrorFlags.Count -gt 0) {
        ($loopbackErrorFlags | Sort-Object -Unique) -join "; "
    } else {
        "None"
    }

    # Match categories
    $categorySummary = ($meta.FQDNs | ForEach-Object {
        if ($fqdnToCategories.ContainsKey($_)) {
            "${_}: $($fqdnToCategories[$_])"
        } else {
            "${_}: Unclassified"
        }
    }) -join " | "

    # Add to results
    $results += [PSCustomObject]@{
        RequestStartUtc = $firstSeen
        IP              = $ip
        FQDNs           = $fqdnList
        Statuses        = $statuses
        HasError        = $meta.HasError
        URLs            = $urlList
        AverageTimeMs   = $avgTimeMs
        MaxTimeMs       = $maxTimeMs
        Country         = $country
        Region          = $region
        City            = $city
        ISP             = $isp
        Latitude        = $lat
        Longitude       = $lon
        GeoStatus       = $geoStatus
        GeoError        = $geoError
        LoopbackResult  = ($loopbackResult -join "; ")
        LoopbackError   = $loopbackError
        Categories      = $categorySummary
    }
}

# Export to CSV and open
$results = $results | Sort-Object RequestStartUtc
$results | Export-Csv -Path $outputCsv -NoTypeInformation -Encoding UTF8
Start-Process -FilePath $outputCsv
