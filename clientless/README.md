# DNSFilter Clientless deployment scripts

Clientless DNS filtering sends a device's DNS to DNSFilter over the encrypted DNS (DNS over HTTPS) built into the
operating system, so no DNSFilter software is installed. These scripts create each device's Clientless deployment
through the DNSFilter API and set it up in bulk.

| Folder | Platform | How it deploys |
|---|---|---|
| [`windows/`](windows/) | Windows 11, Windows Server 2022 or later | `Install-DNSFilterClientless.ps1` runs on each computer from your RMM, as SYSTEM |
| [`mac/`](mac/) | macOS | `dnsfilter-clientless-profiles.sh` runs once on your own Mac and makes one signed configuration profile per Mac for your MDM to install |

Both need a DNSFilter API key and the ID of the Site the devices belong to. Running either script again never creates
duplicate deployments. Each folder's README has the full steps.
