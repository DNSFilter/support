Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

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

    # Loopback check (Example: Resolve DNS)
    $loopbackResult = @()
    $loopbackErrorFlags = @()
    foreach ($fqdn in $meta.FQDNs) {
        try {
            $res = Resolve-DnsName -Name $fqdn -Server "127.0.0.2" -ErrorAction Stop
            $aRecords = ($res | Where-Object { $_.Type -eq "A" }).IPAddress

            if ($aRecords) {
                $loopbackResult += "$fqdn → $($aRecords -join ', ')"
            } else {
                $loopbackResult += "$fqdn → NO A record"
            }
        } catch {
            $loopbackResult += "$fqdn → FAILED: $_"
        }
    }

    $loopbackError = if ($loopbackErrorFlags.Count -gt 0) {
        ($loopbackErrorFlags | Sort-Object -Unique) -join "; "
    } else {
        "None"
    }

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
    }
}

# Export to CSV and open
$results = $results | Sort-Object RequestStartUtc
$results | Export-Csv -Path $outputCsv -NoTypeInformation -Encoding UTF8
Start-Process -FilePath $outputCsv
