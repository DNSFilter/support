# Define a function to process each interface
function Remove-DnsSettings {
    param(
        [string]$RegistryPath
    )

    # Get the interface GUIDs from the registry
    $guids = Get-ChildItem -Path $RegistryPath | Select-Object -ExpandProperty PSChildName

    foreach ($guid in $guids) {
        $path = Join-Path $RegistryPath $guid

        # Check for DNS settings at the interface level
        $nameserver = (Get-ItemProperty -Path $path -Name "NameServer" -ErrorAction SilentlyContinue).NameServer
        $profilename = (Get-ItemProperty -Path $path -Name "ProfileNameServer" -ErrorAction SilentlyContinue).ProfileNameServer

        if ($nameserver -or $profilename) {
            Write-Output "$path : DNS settings found"
            if ($nameserver) {
                Write-Output "NameServerValue: $nameserver"
                Write-Output "Removing NameServerValue"
                Set-ItemProperty -Path $path -Name "NameServer" -Value ""
            }
            if ($profilename) {
                Write-Output "ProfileNameServerValue: $profilename"
                Write-Output "Removing ProfileNameServerValue"
                Set-ItemProperty -Path $path -Name "ProfileNameServer" -Value ""
            }
        } else {
            Write-Output "$path : No DNS settings found"
        }

        # Check for DNS settings at the sub-interface level
        $networks = Get-ChildItem -Path $path
        if ($networks) {
            foreach ($network in $networks) {
                $networkPath = $network.PSPath -replace "HKEY_LOCAL_MACHINE", "HKLM:"
                $nameserver = (Get-ItemProperty -Path $networkPath -Name "NameServer" -ErrorAction SilentlyContinue).NameServer
                $profilename = (Get-ItemProperty -Path $networkPath -Name "ProfileNameServer" -ErrorAction SilentlyContinue).ProfileNameServer

                if ($nameserver -or $profilename) {
                    Write-Output "$networkPath : DNS settings found"
                    if ($nameserver) {
                        Write-Output "NameServerValue: $nameserver"
                        Write-Output "Removing NameServerValue"
                        Set-ItemProperty -Path $networkPath -Name "NameServer" -Value ""
                    }
                    if ($profilename) {
                        Write-Output "ProfileNameServerValue: $profilename"
                        Write-Output "Removing ProfileNameServerValue"
                        Set-ItemProperty -Path $networkPath -Name "ProfileNameServer" -Value ""
                    }
                } else {
                    Write-Output "$networkPath : No DNS settings found"
                }
            }
        }
    }
}

# Process IPv4 interfaces
Remove-DnsSettings -RegistryPath "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"

# Process IPv6 interfaces
Remove-DnsSettings -RegistryPath "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters\Interfaces"