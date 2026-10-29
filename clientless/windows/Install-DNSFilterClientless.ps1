<#
.SYNOPSIS
    Sets up DNSFilter Clientless (DNS over HTTPS) on a Windows computer.

.DESCRIPTION
    QUICK START
      Give the script two values, then run it as SYSTEM on each computer:
        DNSFILTER_API_KEY   your DNSFilter API key
        DNSFILTER_SITE_ID   the ID of the Site these computers belong to. In the dashboard, go to
                            Deployments > Sites and edit the Site. The Site ID is the number at the end
                            of the page address, for example .../deployments/sites/edit/123456
      You can supply them in any of three ways. Use whichever your RMM supports:
        A. As environment variables or script variables with those names (most RMM tools)
        B. As parameters: -ApiKey and -SiteId
        C. By typing them into the two lines under "FILL IN" near the top of the script (for example, Intune)
      That's all most deployments need. Policy, schedule and block page come from the Site.

    Run this script on each computer from your RMM or management tool. No DNSFilter software is installed.
    It uses the encrypted DNS (DNS over HTTPS) built into Windows.

    Each run does the following:

      1. Finds this computer's Clientless deployment in your DNSFilter account, or creates one.
         The computer name identifies the deployment, so running the script again never creates a duplicate.
      2. Applies any per-computer policy, schedule or block page (Advanced, optional).
      3. Reads the Site's local domains and local DNS servers from your DNSFilter dashboard.
      4. Configures Windows:
           - DNSFilter's block page certificates (the DNSFilter Root CA and the newer DNSFilter Root CA G1)
             are added to the computer's trusted root certificates, so a blocked HTTPS site shows the
             DNSFilter block page instead of a certificate warning.
           - All DNS goes to DNSFilter, encrypted, with this computer's unique ID.
           - Each local domain on the Site (for example corp.example.com) keeps resolving through your
             local DNS servers, so Active Directory and internal names keep working.
         Network adapter settings are not changed. The configuration applies to every network the computer
         uses, including Wi-Fi networks and adapters added later.
      5. Confirms with DNSFilter that this computer's DNS is encrypted and identified.
         If the check fails, the script removes the DNS configuration, so the computer is never left
         without working DNS. The block page certificates stay; -Uninstall removes them.

    Run it again at any time. It updates the configuration to match the Site, adding or removing local
    domains, and changes nothing that is already correct.

    What is sent to DNSFilter: the computer name (as the deployment name) and the Site ID. Nothing else
    about the computer is sent.

    Requirements
      - Windows 11, or Windows Server 2022 or later
      - Run as Administrator or SYSTEM (RMM tools normally run scripts as SYSTEM)
      - A DNSFilter API key (Account Settings > Security > API Keys) from an admin account. Use a
        dedicated key for this script. Keys expire; computers already set up keep working after that, only
        new runs fail until you supply a new key. The key is sent only to api.dnsfilter.com over HTTPS.
        The script never writes it to the log or to disk, but with option C the key is stored in the script
        file itself, so protect that copy.
      - If the Site has local domains, the Site must also list your local DNS servers

    Exit codes
      0  Done. DNS is encrypted and identified as this computer.
      1  Failed. The reason is in the output and the log. If Windows settings had already been changed,
         they were removed, and DNS now uses the network's normal servers.
      2  DNS is encrypted, but DNSFilter does not recognize this computer's ID yet. The configuration stays
         in place. Wait a few minutes and run the script again. If it still returns 2, check the
         deployment in the dashboard.

    Log file: C:\ProgramData\DNSFilter\Clientless\install.log

    Good to know
      - Software that does its own DNS lookups is not covered. That includes browsers with their own
        "secure DNS" setting turned on. Turn that setting off with your browser management policy.
      - If your Group Policy already deploys Name Resolution Policy Table (NRPT) rules, Windows ignores
        the rules this script creates. The script detects this and stops.

.PARAMETER ApiKey
    Your DNSFilter API key. Or set DNSFILTER_API_KEY (recommended: RMM job logs often record the command
    line, so this keeps the key out of them).

.PARAMETER SiteId
    The ID of the Site this computer belongs to. Or set DNSFILTER_SITE_ID. See QUICK START for where to
    find it.

.PARAMETER PolicyId
    Advanced, optional. Most deployments leave this out and use the Site's policy. A policy ID for this
    computer instead of the Site's. You can also change it later per computer in the dashboard.

.PARAMETER ScheduledPolicyId
    Advanced, optional. A scheduled policy ID for this computer instead of the Site's. Use either PolicyId
    or ScheduledPolicyId, not both.

.PARAMETER BlockPageId
    Advanced, optional. A block page ID for this computer instead of the Site's.

.PARAMETER Name
    Advanced, optional. The name shown in the dashboard. Defaults to the computer name, and must be unique within the
    Site. If two computers have the same name (for example, from a cloned image), pass a unique -Name for
    each one, or they share one deployment.

.PARAMETER Uninstall
    Removes the configuration this script added. DNS goes back to the network's normal servers.
    Block page certificates are removed only if this script added them; a certificate that was already
    trusted (for example, installed by the DNSFilter agent or Group Policy) is left in place.
    The deployment stays in your dashboard, where you can archive it. Does not need an API key and does
    not contact DNSFilter.

.EXAMPLE
    .\Install-DNSFilterClientless.ps1

    Takes the API key and Site ID from DNSFILTER_API_KEY and DNSFILTER_SITE_ID (recommended).

.EXAMPLE
    .\Install-DNSFilterClientless.ps1 -SiteId 123456 -ApiKey "<your API key>"

.EXAMPLE
    .\Install-DNSFilterClientless.ps1 -SiteId 123456 -PolicyId 7890 -BlockPageId 1201

    Advanced: a per-computer policy and block page instead of the Site's.

.EXAMPLE
    .\Install-DNSFilterClientless.ps1 -Uninstall
#>
[CmdletBinding(DefaultParameterSetName = 'Install')]
param(
    [Parameter(ParameterSetName = 'Install')][string]$ApiKey = $env:DNSFILTER_API_KEY,
    [Parameter(ParameterSetName = 'Install')][string]$SiteId = $env:DNSFILTER_SITE_ID,
    [Parameter(ParameterSetName = 'Install')][int]$PolicyId,
    [Parameter(ParameterSetName = 'Install')][int]$ScheduledPolicyId,
    [Parameter(ParameterSetName = 'Install')][int]$BlockPageId,
    [Parameter(ParameterSetName = 'Install')][string]$Name = $env:COMPUTERNAME,
    [Parameter(ParameterSetName = 'Uninstall', Mandatory)][switch]$Uninstall
)

# ------------------------------------------------------------------------------------------------
# FILL IN (option C) - only if your tool cannot pass DNSFILTER_API_KEY and DNSFILTER_SITE_ID.
# Values passed as parameters or environment variables take priority over these.
# ------------------------------------------------------------------------------------------------
$FillInApiKey = ''
$FillInSiteId = ''

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

# ------------------------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------------------------
$ApiUrl         = 'https://api.dnsfilter.com'
$DohHost        = 'doh.dnsfilter.com'
$DohServerIps   = @('103.247.36.150', '103.247.37.150')   # DNSFilter's DNS-over-HTTPS servers
$RuleTag        = 'DNSFilter-Clientless'                   # marks every rule this script creates
$StateDir       = Join-Path $env:ProgramData 'DNSFilter\Clientless'
$StateFile      = Join-Path $StateDir 'deployment.json'
$LogFile        = Join-Path $StateDir 'install.log'
$GpoNrptKey     = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient\DnsPolicyConfig'

# DNSFilter's block page certificates. HTTPS block pages are signed by these roots, so without them a
# blocked HTTPS site shows a certificate warning. Both are needed: block pages use the 2017 root today and
# move to G1. Each one is checked against its SHA-1 thumbprint before it is trusted.
$BlockPageRoots = @(
    @{
        Name       = 'DNSFilter Root CA'
        Thumbprint = '94F049E8CF62BB16ACC75AA82B6B0700F75FB77B'
        Pem        = @'
-----BEGIN CERTIFICATE-----
MIIB+zCCAYCgAwIBAgIJAOmnrpSmpkDHMAoGCCqGSM49BAMDMDAxEjAQBgNVBAoM
CUROU0ZpbHRlcjEaMBgGA1UEAwwRRE5TRmlsdGVyIFJvb3QgQ0EwHhcNMTcxMTA5
MjMyMDI5WhcNMzcxMTA0MjMyMDI5WjAwMRIwEAYDVQQKDAlETlNGaWx0ZXIxGjAY
BgNVBAMMEUROU0ZpbHRlciBSb290IENBMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAE
OXmRoYaUunupYevaDz3amvJJncDKx9q9xpWPSpUd9HmDMbTTJCXyjIwBcfZvMkST
uoJ85PzI/OxbKTBL4Ju3xeyedZJoQDQC2kGdw2/7AAuEJ5qX/H8eTYgd/U0HZptL
o2YwZDAdBgNVHQ4EFgQUOOmtJ8Qr1M4Q4NlnTRQdhOJm7vUwHwYDVR0jBBgwFoAU
OOmtJ8Qr1M4Q4NlnTRQdhOJm7vUwEgYDVR0TAQH/BAgwBgEB/wIBADAOBgNVHQ8B
Af8EBAMCAYYwCgYIKoZIzj0EAwMDaQAwZgIxAP21roVYzTcLue2zEXkt6UGftv0O
jitFCWV4/jWVIZg9jJd2y/RS58QTMPaWUSyInQIxAO8WYt/eZeLgEE82jBHtTCN1
exKSEHwaLmwXlOXBY0b+7youkJRXvXtyitUJ2HjvVw==
-----END CERTIFICATE-----
'@
    }
    @{
        Name       = 'DNSFilter Root CA G1'
        Thumbprint = '80E7ED9F86F27ABF9FDC0B999B77E9C774F3485F'
        Pem        = @'
-----BEGIN CERTIFICATE-----
MIICIjCCAaigAwIBAgIUccjA3xyzbr8KGAEkHocpwZTvAkYwCgYIKoZIzj0EAwMw
QDELMAkGA1UEBhMCVVMxEjAQBgNVBAoTCUROU0ZpbHRlcjEdMBsGA1UEAxMURE5T
RmlsdGVyIFJvb3QgQ0EgRzEwHhcNMjYwNTIxMTYzOTU0WhcNMzYwNTE4MTY0MDI0
WjBAMQswCQYDVQQGEwJVUzESMBAGA1UEChMJRE5TRmlsdGVyMR0wGwYDVQQDExRE
TlNGaWx0ZXIgUm9vdCBDQSBHMTB2MBAGByqGSM49AgEGBSuBBAAiA2IABPVL/ueD
61gJomLPROtQJYbod4RxWJyIxxUl7QpGs7F4skdvJv/gbSuZevR4brn552fTfDfa
FG7Ltic1uL70ffNurNs4nO/HhtIwXMKj4onH1pwO4bKZh2CsWvMIG1fMp6NjMGEw
DgYDVR0PAQH/BAQDAgEGMA8GA1UdEwEB/wQFMAMBAf8wHQYDVR0OBBYEFBX7m2/k
WFRpAN5PuinQSVM4DolPMB8GA1UdIwQYMBaAFBX7m2/kWFRpAN5PuinQSVM4DolP
MAoGCCqGSM49BAMDA2gAMGUCMQCVg2gSSO/MQQYeLj0aVs1hBBDbkc4ToNuTZWuP
QuVZG0a+lPglSCFJpQBJsmIeccICMGMvLK1EVSWWmPV9Ib1aqJ3MXxT/2Ic5lPgT
ZKH6SnVud7MeJrwffn19C7k/XswBGA==
-----END CERTIFICATE-----
'@
    }
)

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

function Write-Log([string]$Message) {
    $line = '{0:yyyy-MM-dd HH:mm:ss}  {1}' -f (Get-Date), $Message
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

function Stop-WithError([string]$Message) {
    Write-Log "ERROR: $Message"
    exit 1
}

# ------------------------------------------------------------------------------------------------
# Windows configuration
# ------------------------------------------------------------------------------------------------
function Get-OurRules {
    @(Get-DnsClientNrptRule | Where-Object Comment -eq $RuleTag)
}

function Remove-DnsFilterConfig {
    # Remove the catch-all rule first, so local domains keep their rules until the very end.
    $rules    = Get-OurRules
    $catchAll = @($rules | Where-Object { @($_.Namespace) -contains '.' })
    $local    = @($rules | Where-Object { @($_.Namespace) -notcontains '.' })
    foreach ($rule in $catchAll + $local) {
        Remove-DnsClientNrptRule -Name $rule.Name -Force
    }

    foreach ($ip in $DohServerIps) {
        $entry = Get-DnsClientDohServerAddress -ServerAddress $ip -ErrorAction SilentlyContinue
        if ($entry -and $entry.DohTemplate -match 'dnsfilter\.com/') { Remove-DnsClientDohServerAddress -ServerAddress $ip }
    }
    Clear-DnsClientCache
    Write-Log "Removed $($rules.Count) DNS rule(s) and the encrypted DNS settings. Network adapter settings were not changed."
}

function Open-RootStore {
    $store = [Security.Cryptography.X509Certificates.X509Store]::new(
        [Security.Cryptography.X509Certificates.StoreName]::Root,
        [Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine)
    $store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $store
}

function Install-BlockPageCertificates {
    $store = Open-RootStore
    try {
        foreach ($root in $BlockPageRoots) {
            if ($store.Certificates.Find('FindByThumbprint', $root.Thumbprint, $false).Count) {
                Write-Log "Block page certificate already trusted: $($root.Name)."
                continue
            }
            $der  = [Convert]::FromBase64String(($root.Pem -replace '-----[A-Z ]+-----|\s', ''))
            $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new($der)
            if ($cert.Thumbprint -ne $root.Thumbprint) { throw "The built-in copy of $($root.Name) does not match its thumbprint." }
            # The friendly name marks the certificate as added by this script, so -Uninstall removes only these.
            $cert.FriendlyName = "$RuleTag $($root.Name)"
            $store.Add($cert)
            Write-Log "Block page certificate added to trusted roots: $($root.Name)."
        }
    } finally { $store.Close() }
}

function Remove-BlockPageCertificates {
    $store = Open-RootStore
    try {
        foreach ($root in $BlockPageRoots) {
            foreach ($cert in @($store.Certificates.Find('FindByThumbprint', $root.Thumbprint, $false))) {
                if ($cert.FriendlyName -like "$RuleTag *") {
                    $store.Remove($cert)
                    Write-Log "Block page certificate removed: $($root.Name)."
                } else {
                    Write-Log "Block page certificate left in place (not added by this script): $($root.Name)."
                }
            }
        }
    } finally { $store.Close() }
}

function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')
}

# ------------------------------------------------------------------------------------------------
# Uninstall
# ------------------------------------------------------------------------------------------------
if ($Uninstall) {
    if (-not (Test-IsAdmin)) { Stop-WithError 'Run this script as Administrator or SYSTEM.' }
    Remove-DnsFilterConfig
    Remove-BlockPageCertificates
    Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
    Write-Log 'Uninstalled. The deployment is still in your DNSFilter dashboard.'
    exit 0
}

# ------------------------------------------------------------------------------------------------
# Checks before changing anything
# ------------------------------------------------------------------------------------------------
if (-not (Test-IsAdmin)) { Stop-WithError 'Run this script as Administrator or SYSTEM.' }
if (-not (Get-Command Add-DnsClientDohServerAddress -ErrorAction SilentlyContinue)) {
    Stop-WithError 'This version of Windows does not support DNS over HTTPS. Windows 11 or Windows Server 2022 or later is required.'
}
if (-not $ApiKey) { $ApiKey = $FillInApiKey }
if (-not $SiteId) { $SiteId = $FillInSiteId }
if (-not $ApiKey) { Stop-WithError 'No API key. Set DNSFILTER_API_KEY, pass -ApiKey, or fill in $FillInApiKey at the top of the script.' }
# The value itself is never printed: if an API key was pasted into the Site ID by mistake, it must not reach the log.
if ("$SiteId".Trim() -notmatch '^\d+$') { Stop-WithError "No valid Site ID. Set DNSFILTER_SITE_ID, pass -SiteId, or fill in `$FillInSiteId at the top of the script. The Site ID is a number." }
$SiteId = [int]"$SiteId".Trim()
if ($PSBoundParameters.ContainsKey('PolicyId') -and $PSBoundParameters.ContainsKey('ScheduledPolicyId')) {
    Stop-WithError 'Use either -PolicyId or -ScheduledPolicyId, not both.'
}
if (-not $Name) { Stop-WithError 'No deployment name. Pass -Name.' }
if (@(Get-ChildItem $GpoNrptKey -ErrorAction SilentlyContinue).Count) {
    Stop-WithError 'Group Policy manages DNS rules (NRPT) on this computer, so Windows would ignore the rules this script creates. Contact DNSFilter support for Group Policy deployment.'
}
$otherCatchAll = @(Get-DnsClientNrptRule | Where-Object { $_.Comment -ne $RuleTag -and @($_.Namespace) -contains '.' })
if ($otherCatchAll.Count) {
    $otherNames = @($otherCatchAll | ForEach-Object { if ($_.DisplayName) { $_.DisplayName } else { $_.Name } })
    Stop-WithError "Another DNS product or VPN already sends all DNS through its own rule ($($otherNames -join ', ')). DNSFilter Clientless cannot run alongside it."
}

$Headers = @{ Authorization = "Bearer $ApiKey"; Accept = 'application/json' }

function Invoke-DnsFilterApi([string]$Method, [string]$Path, $Body) {
    $request = @{ Method = $Method; Uri = "$ApiUrl$Path"; Headers = $Headers; UseBasicParsing = $true; ContentType = 'application/json' }
    if ($null -ne $Body) { $request.Body = ($Body | ConvertTo-Json -Depth 5 -Compress) }
    try { Invoke-RestMethod @request }
    catch {
        $status = $_.Exception.Response.StatusCode.value__
        if (-not $status) { Stop-WithError "Could not reach $ApiUrl. Check this computer's internet access and firewall. ($($_.Exception.Message))" }
        $detail = $_.ErrorDetails.Message
        if ($status -eq 401) { $detail = 'The API key was rejected.' }
        elseif ($status -eq 404 -and -not $detail) { $detail = 'Not found. Check the Site ID, and that Clientless is enabled for your account.' }
        Stop-WithError "DNSFilter API request failed ($Method $Path, HTTP $status). $detail"
    }
}

# ------------------------------------------------------------------------------------------------
# 1. Read the Site
# ------------------------------------------------------------------------------------------------
$site           = Invoke-DnsFilterApi GET "/v1/networks/$SiteId"
$siteName       = $site.data.attributes.name
$orgId          = $site.data.relationships.organization.data.id
$localDomains   = @($site.data.attributes.local_domains   | Where-Object { $_ })
$localResolvers = @($site.data.attributes.local_resolvers | Where-Object { $_ })
Write-Log "Site $SiteId ($siteName): local domains [$($localDomains -join ', ')], local DNS servers [$($localResolvers -join ', ')]"

# Local domains need somewhere to resolve. Without local DNS servers they would stop working, so stop here.
if ($localDomains.Count -and -not $localResolvers.Count) {
    Stop-WithError "Site $SiteId has local domains but no local DNS servers. Add your local DNS servers to the Site in the DNSFilter dashboard, then run this script again."
}
$localNamespaces = @($localDomains | ForEach-Object { '.' + $_.Trim().Trim('.').ToLowerInvariant() } | Where-Object { $_ -ne '.' } | Select-Object -Unique)

# ------------------------------------------------------------------------------------------------
# 2. Find or create this computer's deployment
# ------------------------------------------------------------------------------------------------
function Find-Deployment {
    $query = "/v2/clientless?network_id=$SiteId&name=$([uri]::EscapeDataString($Name))&page[size]=100"
    if ($orgId) { $query += "&organization_id=$orgId" }
    # The name search also matches partial names, so keep exact matches only.
    @((Invoke-DnsFilterApi GET $query).data | Where-Object { $_.name -eq $Name -and "$($_.network_id)" -eq "$SiteId" -and -not $_.deleted_at })
}

$deployment = $null
$saved      = if (Test-Path $StateFile) { Get-Content $StateFile -Raw | ConvertFrom-Json }
$existingDeployments   = @(Find-Deployment)
if ($saved) {
    $deployment = $existingDeployments | Where-Object id -eq $saved.id | Select-Object -First 1
    if ($deployment) { Write-Log "Using this computer's existing deployment $($deployment.id)." }
}
if (-not $deployment -and $existingDeployments.Count -eq 1) {
    $deployment = $existingDeployments[0]
    Write-Log "Found the existing deployment named '$Name' ($($deployment.id)). No duplicate was created."
}
if (-not $deployment -and $existingDeployments.Count -gt 1) {
    Stop-WithError "$($existingDeployments.Count) deployments are named '$Name' on Site $SiteId. Archive the extra ones in the dashboard, or pass a unique -Name."
}

$overrides = @{}
if ($PSBoundParameters.ContainsKey('PolicyId'))          { $overrides.policy_id = $PolicyId }
if ($PSBoundParameters.ContainsKey('ScheduledPolicyId')) { $overrides.scheduled_policy_id = $ScheduledPolicyId }
if ($PSBoundParameters.ContainsKey('BlockPageId'))       { $overrides.block_page_id = $BlockPageId }

if (-not $deployment) {
    $deployment = (Invoke-DnsFilterApi POST '/v2/clientless' (@{ network_id = $SiteId; name = $Name } + $overrides)).data
    if (-not $deployment.id) { Stop-WithError 'DNSFilter did not return a deployment ID.' }
    Write-Log "Created deployment $($deployment.id) for '$Name'."
} else {
    # Only change the settings that were passed in and differ from the deployment.
    $changes = @{}
    foreach ($key in $overrides.Keys) {
        if ("$($deployment.$key)" -ne "$($overrides[$key])") {
            $changes[$key] = $overrides[$key]
        }
    }
    if ($changes.ContainsKey('policy_id') -and $deployment.scheduled_policy_id) { $changes.scheduled_policy_id = $null }
    if ($changes.ContainsKey('scheduled_policy_id') -and $deployment.policy_id) { $changes.policy_id = $null }
    if ($changes.Count) {
        $deployment = (Invoke-DnsFilterApi PATCH "/v2/clientless/$($deployment.id)" $changes).data
        Write-Log "Updated deployment $($deployment.id): $(($changes.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', ')"
    }
}

@{ id = $deployment.id; name = $Name; site_id = $SiteId; updated = (Get-Date).ToString('s') } |
    ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8

$dohUrl = "https://$DohHost/$($deployment.id)"
Write-Log "Encrypted DNS address for this computer: $dohUrl"

# ------------------------------------------------------------------------------------------------
# 3. Configure Windows
# ------------------------------------------------------------------------------------------------
# Certificates first: if this fails, DNS has not been touched yet.
try { Install-BlockPageCertificates }
catch { Stop-WithError "Could not add the block page certificates to the trusted roots: $($_.Exception.Message) DNS was not changed." }

try {
    # Tell Windows that DNSFilter's servers use DNS over HTTPS at this computer's address.
    # Fallback to unencrypted DNS is off, so DNS is never sent unencrypted to DNSFilter.
    foreach ($ip in $DohServerIps) {
        $entry = Get-DnsClientDohServerAddress -ServerAddress $ip -ErrorAction SilentlyContinue
        if ($entry -and $entry.DohTemplate -eq $dohUrl -and $entry.AutoUpgrade -and -not $entry.AllowFallbackToUdp) { continue }
        Remove-DnsClientDohServerAddress -ServerAddress $ip -ErrorAction SilentlyContinue
        Add-DnsClientDohServerAddress -ServerAddress $ip -DohTemplate $dohUrl -AutoUpgrade $true -AllowFallbackToUdp $false | Out-Null
        Write-Log "Encrypted DNS set for $ip."
    }

    # Name Resolution Policy Table (NRPT) rules:
    #   - one rule per local domain, sending it to your local DNS servers
    #   - one catch-all rule ('.') sending everything else to DNSFilter
    # Windows uses the most specific rule that matches, so local domains always win.
    $wanted = [ordered]@{}
    foreach ($ns in $localNamespaces) { $wanted[$ns] = @($localResolvers) }
    $wanted['.'] = @($DohServerIps)

    $current = @{}
    foreach ($rule in Get-OurRules) { foreach ($ns in @($rule.Namespace)) { $current[$ns] = $rule } }

    # Add local domains before the catch-all, so internal names keep working throughout.
    foreach ($ns in $wanted.Keys) {
        $rule = $current[$ns]
        if ($rule -and (@($rule.NameServers) -join ',') -eq ($wanted[$ns] -join ',')) { continue }
        if ($rule) { Remove-DnsClientNrptRule -Name $rule.Name -Force }
        Add-DnsClientNrptRule -Namespace $ns -NameServers $wanted[$ns] -Comment $RuleTag -DisplayName "$RuleTag $ns" | Out-Null
        Write-Log "DNS rule set: $ns -> $($wanted[$ns] -join ', ')"
    }
    foreach ($ns in @($current.Keys)) {
        if (-not $wanted.Contains($ns)) {
            Remove-DnsClientNrptRule -Name $current[$ns].Name -Force
            Write-Log "DNS rule removed: $ns (no longer a local domain on the Site)"
        }
    }
    Clear-DnsClientCache
} catch {
    Write-Log "Configuration failed: $($_.Exception.Message)"
    Remove-DnsFilterConfig
    Stop-WithError "Configuration failed and was rolled back. DNS now uses the network's normal servers."
}

# ------------------------------------------------------------------------------------------------
# 4. Confirm with DNSFilter
# ------------------------------------------------------------------------------------------------
# DNSFilter answers this lookup with how the query arrived: the protocol and this computer's ID.
$answer = @{}
foreach ($attempt in 1..5) {
    Start-Sleep -Seconds 2
    try {
        $records = @((Resolve-DnsName debug.dnsfilter.com -Type TXT -DnsOnly -QuickTimeout -ErrorAction Stop |
                      Where-Object Type -eq 'TXT').Strings)
    } catch {
        $records = @()
    }
    # Each record is "key=value", for example "protocol=doh".
    foreach ($record in $records) {
        $key, $value = $record -split '=', 2
        if ($value) { $answer[$key] = $value }
    }
    if ($answer.Count) { break }
    Clear-DnsClientCache
}

$problem = if (-not $answer.Count)                      { "No answer from DNSFilter. Check that this computer can reach $($DohServerIps -join ' and ') on TCP port 443." }
           elseif ($answer.protocol -ne 'doh')          { "DNS is not encrypted (protocol: $($answer.protocol))." }
           elseif ($answer.client_id -ne $deployment.id) { 'DNSFilter sees a different ID for this computer.' }
if ($problem) {
    Remove-DnsFilterConfig
    Stop-WithError "Check failed: $problem The configuration was rolled back. DNS now uses the network's normal servers."
}

if ($answer.policy_source -eq 'ip_address') {
    Write-Log "DNS is encrypted, but DNSFilter does not recognize deployment $($deployment.id) yet. The configuration stays in place. Wait a few minutes and run the script again. If this repeats, check the deployment in the dashboard."
    exit 2
}
Write-Log "Done. DNS is encrypted and identified as '$Name' (deployment $($deployment.id)), with $($localNamespaces.Count) local domain(s) going to your local DNS servers."
exit 0
