param (
    [string[]]$AppNames = @("DNSFilter Agent", "DNS Agent"),
    [string[]]$RegistryKeys = @(
        "HKLM:\Software\DNSFilter",
        "HKLM:\Software\DNSAgent",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{005C7475-188C-42C4-A8BB-BA5D85258289}", #DNS Agent#
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{4E66DFE1-8225-4ED8-9C7F-6A56E4125018}", #DNSFilter Agent#
        "HKLM:\SYSTEM\CurrentControlSet\Services\DNS Agent",
        "HKLM:\SYSTEM\CurrentControlSet\Services\DNSFilter Agent",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunNotification\StartupTNotiDNS Agent TrayIcon",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunNotification\StartupTNotiDNSFilter Agent TrayIcon",
        "HKCU:\Control Panel\NotifyIconSettings\13101556903037567574", #DNS Agent#
        "HKCU:\Control Panel\NotifyIconSettings\3725302543443254742" #DNSFilter Agent#
		"HKCR:\Installer\Assemblies\C:\Program Files\DNS Agent\DNS Agent.exe",
		"HKCR:\Installer\Assemblies\C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe",
		"HKCR:\Installer\Products\E199BDD22BB7C1E4DA3389D71AA98EEA", #DNS Agent#
		"HKCR:\Installer\Products\1EFD66E452288DE4C9F7A6654E210581", #DNSFilter Agent#
		"HKCR:\Installer\Assemblies\C:\Program Files\DNS Agent\DNS Agent TrayIcon.exe",
		"HKCR:\Installer\Assemblies\C:\Program Files\DNSFilter Agent\DNSFilter Agent TrayIcon.exe"),
	[string[]]$DirectoryPaths = @("C:\Program Files\DNS Agent", "C:\Program Files\DNSFilter Agent"),
	[string[]]$ServicesCheck = @("DNS Agent", "DNSFilter Agent")
)

# Get current date and time for use in the log file name
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

# Log file path
$LogFilePath = "C:\Temp\UninstallScriptLog_$timestamp.txt"

function Log-Message {
    param (
        [string]$Message,
        [switch]$IsHeading
    )
    if ($IsHeading) {
        $formattedMessage = "`n========== $Message ==========`n"
    } else {
        $formattedMessage = $Message
    }
    Write-Host $formattedMessage
    $formattedMessage | Out-File -FilePath $LogFilePath -Append
}

# Function to elevate permissions if needed
function Ensure-AdminMode {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Log-Message -Message "Script is not running in Administrator mode. Attempting to restart with elevated permissions..." -IsHeading
        Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
        exit
    }
}

# Function to uninstall both DNSFilter Agent and DNS Agent
function Uninstall-App {
    param ([string]$AppName)
    try {
        Log-Message -Message "Attempting to uninstall $AppName..." -IsHeading
        $uninstallPaths = Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        foreach ($obj in $uninstallPaths) {
            $displayName = $obj.GetValue("DisplayName")
            if ($displayName -eq $AppName) {
                $uninstallString = $obj.GetValue("UninstallString")
                if ($uninstallString -match '(\{.+\}).*') {
                    $appId = $matches[1]
                    Log-Message "Found application ID: $appId. Uninstalling..."
                    Start-Process "msiexec.exe" -ArgumentList "/X$appId /qb" -Wait

                    # Attempt to remove the registry key after uninstallation
                    $registryPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$appId"
                    if (Test-Path $registryPath) {
                        Remove-Item $registryPath -Force -Recurse
                        Log-Message "Successfully removed registry key: $registryPath"
                    } else {
                        Log-Message "Registry key not found post-uninstallation: $registryPath"
                    }
                } else {
                    Start-Process -FilePath "cmd.exe" -ArgumentList "/c $uninstallString" -Wait
                }
                break
            }
        }
    } catch {
        Log-Message ("Error uninstalling $AppName or removing registry key: " + $_.Exception.Message)
    }
}

# Function to check all registry entries and remove if they still exist
function Remove-RegistryKeys {
    param ([string[]]$Keys)
    Log-Message -Message "Registry Key Cleanup Process" -IsHeading
    foreach ($key in $Keys) {
        try {
            if (Test-Path $key) {
                Remove-Item -Path $key -Recurse -ErrorAction Stop
                Log-Message "Successfully removed registry key: $key"
            } else {
                Log-Message "Registry key not found: $key"
            }
        } catch {
            Log-Message ("Error removing registry key ${key}: " + ": " + $_.Exception.Message)
        }
    }
}

# Function to check installation directories and remove if necessary
function Remove-DirectoryIfExist {
	param ([string[]]$Paths)
	Log-Message -Message "Directory Cleanup Process" -IsHeading
    foreach ($path in $Paths) {
		try {
			if (Test-Path $path) {
				Log-Message -Message "Directory found: $path. Attempting to remove..." -IsHeading
				Remove-Item -Path $path -Recurse -Force
				Log-Message "Successfully removed directory: $path"
			} else {
				Log-Message "Directory not found: $path"
			}
		} catch {
            Log-Message ("Error removing directory ${path}: " + ": " + $_.Exception.Message)
		}
	}
	
}
# Check if the service exists
function Remove-ServiceIfExist {
    param ([string[]]$Services)
    Log-Message -Message "Services Check Process" -IsHeading
    foreach ($ServiceName in $Services) {
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            Log-Message -Message "Service found: $ServiceName. Checking status..."
            if ($service.Status -eq 'Running') {
                try {
                    Stop-Service -Name $ServiceName -Force
                    Log-Message "Service $ServiceName stopped successfully."
                } catch {
                    Log-Message ("Failed to stop service ${ServiceName}: " + ": " + $_)
                }
            }
            try {
                Remove-Service -Name $ServiceName
                Log-Message "Service $ServiceName removed successfully."
            } catch {
                Log-Message ("Failed to remove service ${ServiceName}: " + ": " + $_)
            }
        } else {
            Log-Message "Service $ServiceName not found. No removal necessary."
        }
    }
}




# Network connectivity test if DHCP change is made
function Test-NetworkConnectivity {
    Log-Message -Message "Network Connectivity Check" -IsHeading
    $testUrl = "8.8.8.8"
    try {
        $pingResult = Test-Connection -ComputerName $testUrl -Count 1 -ErrorAction Stop
        if ($pingResult.StatusCode -eq 0) {
            Log-Message "Network connectivity check successful."
        } else {
            Log-Message "Network connectivity check failed. Please check your network settings."
        }
    } catch {
        Log-Message "Error during network connectivity check: $($_). Please check your network settings."
    }
}

# Check if loopback address is still on the adapter and if so switches adapter to DHCP to acquire a new address
function CheckAndFixDNS {
    Log-Message -Message "DNS Configuration Check and Fix" -IsHeading
    try {
        $loopbackAddresses = @("127.0.0.1", "127.0.0.2", "127.0.0.3", "127.0.0.4")
        $interfaces = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
        foreach ($interface in $interfaces) {
            $DNS = Get-DnsClientServerAddress -AddressFamily IPv4 -InterfaceIndex $interface.InterfaceIndex
            Log-Message "Checking DNS configuration for interface: $($interface.Name)"
            Log-Message "DNS Servers: $($DNS.ServerAddresses -join ', ')"

            $containsLoopback = $false
            foreach ($address in $DNS.ServerAddresses) {
                if ($address -in $loopbackAddresses) {
                    $containsLoopback = $true
                    break
                }
            }

            if ($containsLoopback) {
                Log-Message "Loopback address detected. Switching to DHCP..."
                Set-DnsClientServerAddress -InterfaceIndex $interface.InterfaceIndex -ResetServerAddresses
                
                # Recheck after setting to DHCP
                $DNSFinal = Get-DnsClientServerAddress -AddressFamily IPv4 -InterfaceIndex $interface.InterfaceIndex
                $containsLoopbackAfterFix = $false
                foreach ($address in $DNSFinal.ServerAddresses) {
                    if ($address -in $loopbackAddresses) {
                        $containsLoopbackAfterFix = $true
                        break
                    }
                }

                if ($containsLoopbackAfterFix) {
                    Log-Message "Failed to remove loopback DNS address."
                } else {
                    Log-Message "DNS successfully reset. New DNS Servers: $($DNSFinal.ServerAddresses -join ', ')"
                    # Perform network connectivity check
                    Test-NetworkConnectivity
                }
            } else {
                Log-Message "DNS configuration does not require correction."
            }
        }
    } catch {
        Log-Message "Error checking or fixing DNS settings: $($_)"
    }
}

# Ensure the log file directory exists
$LogDir = Split-Path -Path $LogFilePath -Parent
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Start script execution with a log heading
Log-Message -Message "Script Execution Start" -IsHeading

# Ensure admin mode is enabled for script execution
Ensure-AdminMode

# Uninstall applications and handle related tasks
foreach ($appName in $AppNames) {
    Uninstall-App -AppName $appName
}

# Remove registry keys as specified
Remove-RegistryKeys -Keys $RegistryKeys

# Remove installation directories if they still exist
Remove-DirectoryIfExist -Paths $DirectoryPaths

# Remove services if they exists
Remove-ServiceIfExist -Services $ServicesCheck

# Perform DNS checks and network connectivity tests
CheckAndFixDNS

# Script execution complete
Log-Message -Message "Script Execution Complete" -IsHeading
