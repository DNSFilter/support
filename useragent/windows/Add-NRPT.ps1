# this script is meant to have the Windows OS bypass the RC completely for specific domains, the OS will use DNS servers set in the $DnsServers value

# Add DNS Servers - Set this to the IP of DNS servers to be used 
$DnsServers = (
    "Enter resolver ip(s) here"
)

# parameters that will be passed into Add-DnsClientNrptRule cmdlet - documenation here https://learn.microsoft.com/en-us/powershell/module/dnsclient/add-dnsclientnrptrule?view=windowsserver2019-ps
$params = @{
    Namespace = "Enter domain suffix Here"
    NameServers = $DnsServers
    DisplayName = "Enter name of rule here"
}

try {
    Add-DnsClientNrptRule @params
}
catch {
    "Adding NRPT rule failed with the following message: $_"
}