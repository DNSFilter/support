# Deploy DNSFilter Clientless to Macs with your MDM

DNSFilter Clientless filters a Mac's DNS without installing any DNSFilter software. Each Mac gets a configuration
profile that turns on the encrypted DNS (DNS over HTTPS) built into macOS. `dnsfilter-clientless-profiles.sh` makes one
signed profile per Mac from a list of names. You then upload the profiles to your MDM.

Apple only lets an MDM install a configuration profile without someone clicking through it on the Mac. The script runs
on your own computer, and your MDM does the installing.

## Before you start

| What | Where to get it |
|---|---|
| **The script** | `dnsfilter-clientless-profiles.sh`. It runs on any Mac with macOS 12 or later and needs nothing installed. |
| **An API key** | Dashboard → **Account Settings → Security → API Keys**, created from an admin account. |
| **The Site ID** | Dashboard → **Deployments → Sites** → edit the Site. The Site ID is the number at the end of the page address. |
| **A CSV of your Macs** | One name per line, under a first line that says `name`. Use the names your MDM shows, so you can match profiles to Macs. |

If the Site has **local domains** (for example your Active Directory domain), each profile keeps those names on your
network's own DNS servers.

## Make the profiles

```bash
DNSFILTER_SITE_ID=123456 ./dnsfilter-clientless-profiles.sh macs.csv
```

The script asks for your API key, or reads it from `DNSFILTER_API_KEY`. For each Mac it:
- finds or creates the Mac's deployment, so it shows in the dashboard
- downloads that Mac's signed profile into `./dnsfilter-profiles/`

`summary.csv` in the same folder lists each Mac's deployment and result. Run the script again at any time. It never
creates duplicates, and the profiles it downloads replace the earlier ones on the Mac instead of adding a second.

Advanced: add `policy_id`, `scheduled_policy_id` or `block_page_id` columns to give a Mac its own settings instead of
the Site's.

## Upload to your MDM

Upload each `.mobileconfig` file as a custom configuration profile, and **assign it to that one Mac only**. A profile
carries one Mac's unique ID. If you assign it to several Macs, they all report as the same deployment.

Each profile:
- sends all DNS to DNSFilter over encrypted DNS
- trusts the DNSFilter block page certificate, so blocked HTTPS sites show the block page instead of a warning
- keeps the Site's local domains on your network's DNS servers

## Roll out safely

Start with one Mac. Check that it browses normally and that a blocked site shows the block page, then roll out the rest.

If something goes wrong, you can always get back:
- **Remove the profile in your MDM.** The Mac goes back to its network's normal DNS straight away. A profile installed
  by an MDM can always be removed by that MDM.
- **A profile installed by hand** (double-clicked on the Mac) can be removed in System Settings → Privacy & Security →
  Profiles, with an administrator password.

These profiles don't stop people removing them, and they never make a Mac unmanageable.

## Good to know

- **No fallback when DNSFilter is unreachable.** If the Mac can't reach DNSFilter's encrypted DNS, it doesn't quietly
  switch to unfiltered DNS. Names stop resolving until DNSFilter is reachable again or the profile is removed.
- **Browsers with their own "secure DNS":** Chrome, Edge and Firefox can send DNS themselves when that setting is on.
  Turn it off with your browser management policy (Chrome/Edge `DnsOverHttpsMode` = `off`; Firefox `DNSOverHTTPS`).
- **Removing a Mac:** remove its profile in your MDM, then archive its deployment in the dashboard.
