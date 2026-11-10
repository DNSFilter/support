# Deploy DNSFilter Clientless to Windows with your RMM

DNSFilter Clientless filters a computer's DNS without installing any DNSFilter software. It uses the encrypted DNS (DNS over
HTTPS) built into Windows. `Install-DNSFilterClientless.ps1` sets it up. Run it once on each computer from your RMM, and run it
again whenever you like. It never creates duplicates.

## Before you start

You need three things:

| What | Where to get it |
|---|---|
| **The script** | `Install-DNSFilterClientless.ps1` |
| **An API key** | Dashboard → **Account Settings → Security → API Keys**. Create one for this script. The key acts as the user who creates it, so create it from an admin account that will stay in place. Keys expire (12 months at most); note the date. |
| **The Site ID** | Dashboard → **Deployments → Sites** → edit the Site. The Site ID is the number at the end of the page address, for example `…/deployments/sites/edit/123456`. |

Requirements:

- Windows 11, or Windows Server 2022 or later.
- The script must run as **SYSTEM** (or a local administrator).
- If the Site has **local domains** (for example your Active Directory domain), add your **local DNS servers** to the
  Site too. The script refuses to run without them, so your internal names keep working.

## The two values the script needs

| Name | Value |
|---|---|
| `DNSFILTER_API_KEY` | your API key |
| `DNSFILTER_SITE_ID` | the Site ID |

Give them to the script in whichever way your RMM supports:

- **A. Script or environment variables** with exactly those names. This is the best option: the key stays out of the command line and job logs.
- **B. Parameters:** `-ApiKey <key> -SiteId <id>`
- **C. Typed into the script:** fill in the two lines under `FILL IN` near the top of the script. Use this when your tool
  can't pass values at all, as with Intune. The key is then stored in the script, so protect that copy.

Policy, scheduled policy and block page come from the Site. You can change them per computer later in the dashboard.

## Step by step for common RMMs

### NinjaOne
1. **Automation Library** → add a new PowerShell script and paste in `Install-DNSFilterClientless.ps1`.
2. Under **Script variables**, add two **String** variables named `DNSFILTER_API_KEY` and `DNSFILTER_SITE_ID`. NinjaOne
   passes script variables to the script as environment variables (option A).
3. Run it as **System** on the target devices.

### Datto RMM
1. Create a **Component** (PowerShell) and paste in the script.
2. **Variables → Add Variable** for `DNSFILTER_API_KEY` and `DNSFILTER_SITE_ID` (type String). Datto passes component
   variables as environment variables (option A).
3. Run the component as a job on the target devices.

### N-able N-sight RMM
1. Add the script as a **Script Check** or **Automated Task**.
2. In **Script Parameters → Command Line**, enter: `-SiteId 123456 -ApiKey <your key>` (option B).
   N-sight treats any non-zero exit code as a failure. See the exit codes below.

### Microsoft Intune
Intune scripts can't take values, so use option C.
1. Fill in `$FillInApiKey` and `$FillInSiteId` at the top of the script and save it.
2. **Devices → Scripts and remediations → Platform scripts → Add → Windows 10 and later**, then upload the script.
3. Set **Run this script using the logged on credentials = No**, so it runs as SYSTEM.
4. Optionally set **Run script in 64-bit PowerShell host = Yes**. The script also works in the default 32-bit host.
5. Assign it to a device group.

### Other tools (ConnectWise, Kaseya, Atera, Syncro, Action1, N-central)
Use option A if your tool can set environment variables or script variables. Use option B if it passes command-line
parameters. Otherwise use option C. Always run as SYSTEM.

## What success looks like

| Exit code | Meaning | What to do |
|---|---|---|
| **0** | DNS is encrypted and identified as this computer. | Nothing. The computer appears under Clientless in the dashboard. |
| **1** | Not set up. The reason is in the output. If anything had been changed, it was removed, and DNS uses the network's normal servers. | Fix the reason and run it again. |
| **2** | DNS is encrypted, but DNSFilter doesn't recognize this computer yet. The setup stays in place. | Wait a few minutes and run it again. If it still returns 2, check the deployment in the dashboard. |

Each run also writes a log to `C:\ProgramData\DNSFilter\Clientless\install.log`.

Common exit-1 reasons, and how to fix each:

- *"No valid Site ID"*: set `DNSFILTER_SITE_ID`, or pass `-SiteId`.
- *"has local domains but no local DNS servers"*: add your internal DNS servers to the Site in the dashboard.
- *"Group Policy manages DNS rules (NRPT)"*: Windows ignores this script's rules on that computer. Contact DNSFilter
  support.
- *"Another DNS product or VPN already sends all DNS through its own rule"*: Clientless can't run alongside that product.
- *"No answer from DNSFilter"*: allow outbound TCP 443 to `103.247.36.150` and `103.247.37.150`.

## When the API key expires

Computers that are already set up keep working: their configuration doesn't need the key. Only new runs fail, with
*"The API key was rejected"*, and they change nothing on the computer. Create a new key, update it in your RMM, and
carry on.

## Removing it

Run the script with `-Uninstall`. It needs no API key, and DNS goes back to the network's normal servers. The deployment
stays in the dashboard, where you can archive it. The block page certificates are removed only if the script added them.

## Good to know

- **Every network:** the setup applies to every network the computer uses, including Wi-Fi and adapters added later. It
  doesn't change any network adapter settings.
- **Block page certificates:** the script adds the DNSFilter Root CA and the newer DNSFilter Root CA G1 to the
  computer's trusted root certificates, so a blocked HTTPS site shows the block page instead of a certificate warning.
  If they are already trusted (for example, deployed by Group Policy), the script leaves them as they are. Firefox uses
  the Windows trusted roots unless that is turned off; the `Certificates` → `ImportEnterpriseRoots` policy turns it on.
- **Local domains:** each local domain on the Site keeps resolving through your local DNS servers. If you change the
  Site's local domains, run the script again to pick up the change.
- **Browsers with their own "secure DNS":** Chrome, Edge and Firefox can send DNS themselves when that setting is on,
  and the script doesn't cover that. Turn it off with your browser management policy:
  - Chrome and Edge: `DnsOverHttpsMode` = `off`
  - Firefox: the `DNSOverHTTPS` policy
- **Computer names must be unique within a Site.** Computers cloned from one image keep the same name, and would share
  one deployment. Give each a unique name, or pass `-Name`.
