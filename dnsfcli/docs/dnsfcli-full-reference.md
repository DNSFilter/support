# dnsfcli Reference Guide

_Command-line interface for the DNSFilter API_

Complete command reference, tested examples, CSV bulk-import workflows, and output flag usage for every endpoint in the DNSFilter API.

**Reference · 2026**

| Tool version | Updated | Audience |
|---|---|---|
| 0.1.0 | 2026-07-13 | Developers & Administrators |

---

## Getting Started

dnsfcli is a command-line tool for the full DNSFilter REST API. Install it once, store your credentials in the OS keychain, and manage every aspect of your DNSFilter account from the terminal — no browser required.

### 1. Install

Python 3.9 or later is required.

```text
# SHELL / INSTALL
pip install -e . # or run directly: python dnsfcli.py --help
```

### 2. Store credentials

Your API token and default organization ID are stored in the OS keychain (macOS Keychain / Windows Credential Manager / Linux Secret Service) and used automatically on every subsequent command.

```text
# SHELL / AUTH SETUP
python dnsfcli.py auth setup python dnsfcli.py auth setup --org-id 802315 python dnsfcli.py auth verify python dnsfcli.py auth show
```

## Command Structure

Every command follows the same three-part pattern.

```text
# REFERENCE / COMMAND STRUCTURE
python dnsfcli.py [endpoint] [function] [--param value ...] # Examples python dnsfcli.py policies list python dnsfcli.py policies show --id 285109 python dnsfcli.py policies create --name "Guest WiFi" --organization_id 802315 python dnsfcli.py policies update --id 285109 --name "Updated" python dnsfcli.py policies delete --id 285109
```

## Global Flags

These flags work on any command and can appear anywhere in the argument list (before the endpoint, between endpoint and function, or after all other flags).

## Discovery

Explore every available endpoint and function without leaving the terminal.

```text
# SHELL / DISCOVERY
# List all 36 endpoint groups python dnsfcli.py endpoints # List all functions for one endpoint python dnsfcli.py endpoints policies # Get a pre-filled CSV template for any write operation python dnsfcli.py policies create --template python dnsfcli.py policies create --template > policies-template.csv
```

## agent-local-users

Agent local user management.

Bulk delete agent local users.

```text
# SHELL / AGENT-LOCAL-USERS BULK-DELETE
python dnsfcli.py agent-local-users bulk-delete --ids ["1001","1002","1003"]
```

Count agent local users matching bulk-delete criteria.

```text
# SHELL / AGENT-LOCAL-USERS BULK-DELETE-COUNTS
python dnsfcli.py agent-local-users bulk-delete-counts
```

Show a bulk-delete job.

```text
# SHELL / AGENT-LOCAL-USERS BULK-DELETE-SHOW
python dnsfcli.py agent-local-users bulk-delete-show \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

Permanently delete a resource by ID.

```text
# SHELL / AGENT-LOCAL-USERS DELETE
python dnsfcli.py agent-local-users delete \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

Retrieve a paginated list of resources.

```text
# SHELL / AGENT-LOCAL-USERS LIST
python dnsfcli.py agent-local-users list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / AGENT-LOCAL-USERS LIST-ALL
python dnsfcli.py agent-local-users list-all
```

Retrieve a single resource by ID.

```text
# SHELL / AGENT-LOCAL-USERS SHOW
python dnsfcli.py agent-local-users show \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

Update an existing resource by ID.

```text
# SHELL / AGENT-LOCAL-USERS UPDATE
python dnsfcli.py agent-local-users update \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5 \ --friendly_name "Jane Smith Laptop" \ --policy_id 285109
```

## api-keys

API key management.

Create a new resource.

```text
# SHELL / API-KEYS CREATE
python dnsfcli.py api-keys create --name "CI Pipeline Key" --expiry 2027-05-31
```

Permanently delete a resource by ID.

```text
# SHELL / API-KEYS DELETE
python dnsfcli.py api-keys delete --id 20981
```

Retrieve a paginated list of resources.

```text
# SHELL / API-KEYS LIST
python dnsfcli.py api-keys list --page 1 --per_page 25
```

Revoke an API key immediately without deleting it.

```text
# SHELL / API-KEYS REVOKE
python dnsfcli.py api-keys revoke --id 20981
```

Retrieve a single resource by ID.

```text
# SHELL / API-KEYS SHOW
python dnsfcli.py api-keys show --id 20981
```

## application-categories

Application category reference.

Retrieve a paginated list of resources.

```text
# SHELL / APPLICATION-CATEGORIES LIST
python dnsfcli.py application-categories list --page 1 --per_page 25
```

Retrieve a single resource by ID.

```text
# SHELL / APPLICATION-CATEGORIES SHOW
python dnsfcli.py application-categories show --id 12345
```

## applications

Application catalog.

Retrieve a paginated list of resources.

```text
# SHELL / APPLICATIONS LIST
python dnsfcli.py applications list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / APPLICATIONS LIST-ALL
python dnsfcli.py applications list-all
```

Retrieve a single resource by ID.

```text
# SHELL / APPLICATIONS SHOW
python dnsfcli.py applications show --id 12345
```

## billing

Billing and subscription.

Create a new resource.

```text
# SHELL / BILLING CREATE
python dnsfcli.py billing create \ --organization_id 802315 \ --payment_token tok_visa_4242
```

Retrieve the billing address for an organization.

```text
# SHELL / BILLING GET-ADDRESS
python dnsfcli.py billing get-address --organization_id 802315
```

Retrieve a single resource by ID.

```text
# SHELL / BILLING SHOW
python dnsfcli.py billing show
```

Update the billing address for an organization.

```text
# SHELL / BILLING UPDATE-ADDRESS
python dnsfcli.py billing update-address \ --organization_id 802315 \ --first_name Jane \ --last_name Smith \ --line1 "123 Main St" \ --city Denver \ --state Colorado \ --zip 80202 \ --country US
```

## block-pages

Custom block page configuration.

Create a new resource.

```text
# SHELL / BLOCK-PAGES CREATE
python dnsfcli.py block-pages create \ --name "Corporate Block Page" \ --block_org_name "Acme Corp" \ --block_email_addr admin@company.com
```

Permanently delete a resource by ID.

```text
# SHELL / BLOCK-PAGES DELETE
python dnsfcli.py block-pages delete --id 12345
```

Retrieve a paginated list of resources.

```text
# SHELL / BLOCK-PAGES LIST
python dnsfcli.py block-pages list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / BLOCK-PAGES LIST-ALL
python dnsfcli.py block-pages list-all
```

Retrieve a single resource by ID.

```text
# SHELL / BLOCK-PAGES SHOW
python dnsfcli.py block-pages show --id 12345
```

Update an existing resource by ID.

```text
# SHELL / BLOCK-PAGES UPDATE
python dnsfcli.py block-pages update \ --id 12345 \ --name "Corporate Block Page Updated"
```

## categories

DNS filtering category reference.

Retrieve a paginated list of resources.

```text
# SHELL / CATEGORIES LIST
python dnsfcli.py categories list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / CATEGORIES LIST-ALL
python dnsfcli.py categories list-all
```

Retrieve a single resource by ID.

```text
# SHELL / CATEGORIES SHOW
python dnsfcli.py categories show --id 12345
```

## collections

Collection user membership.

Add a user to an organization or collection.

```text
# SHELL / COLLECTIONS USERS-ADD
python dnsfcli.py collections users-add --collection_id 7788 --id 42618
```

List users within a specific organization or collection.

```text
# SHELL / COLLECTIONS USERS-LIST
python dnsfcli.py collections users-list --collection_id 7788
```

Remove a user from a collection.

```text
# SHELL / COLLECTIONS USERS-REMOVE
python dnsfcli.py collections users-remove --collection_id 7788 --id 12345
```

Retrieve a specific user within an organization or collection.

```text
# SHELL / COLLECTIONS USERS-SHOW
python dnsfcli.py collections users-show --collection_id 7788 --id 12345
```

## current-user

Authenticated user profile.

Retrieve a single resource by ID.

```text
# SHELL / CURRENT-USER SHOW
python dnsfcli.py current-user show
```

Update an existing resource by ID.

```text
# SHELL / CURRENT-USER UPDATE
python dnsfcli.py current-user update --first_name Jane --last_name Smith
```

## dictionary

API dictionary / reference data.

Retrieve the list of supported QP method types.

```text
# SHELL / DICTIONARY QP-METHODS
python dnsfcli.py dictionary qp-methods
```

## domains

Domain lookup and classification.

Classify multiple domains in a single request.

```text
# SHELL / DOMAINS BULK-LOOKUP
python dnsfcli.py domains bulk-lookup
```

Submit a domain for threat-intel review.

```text
# SHELL / DOMAINS SUGGEST-THREAT
python dnsfcli.py domains suggest-threat
```

Look up a domain for an authenticated user session.

```text
# SHELL / DOMAINS USER-LOOKUP
python dnsfcli.py domains user-lookup
```

## enterprise-connections

Enterprise SSO connection management.

Create a new resource.

```text
# SHELL / ENTERPRISE-CONNECTIONS CREATE
python dnsfcli.py enterprise-connections create \ --client_id my-client-id \ --client_secret my-secret \ --discovery_url "https://idp.company.com/.well-known/openid-configuration" \ --strategy oidc \ --display_name "Company SSO"
```

Permanently delete a resource by ID.

```text
# SHELL / ENTERPRISE-CONNECTIONS DELETE
python dnsfcli.py enterprise-connections delete --id 12345
```

Retrieve a paginated list of resources.

```text
# SHELL / ENTERPRISE-CONNECTIONS LIST
python dnsfcli.py enterprise-connections list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / ENTERPRISE-CONNECTIONS LIST-ALL
python dnsfcli.py enterprise-connections list-all
```

Retrieve a single resource by ID.

```text
# SHELL / ENTERPRISE-CONNECTIONS SHOW
python dnsfcli.py enterprise-connections show --id 12345
```

Update an existing resource by ID.

```text
# SHELL / ENTERPRISE-CONNECTIONS UPDATE
python dnsfcli.py enterprise-connections update \ --id 12345 \ --display_name "Company SSO Updated"
```

## invoices

Invoice history.

Retrieve the current billing period's invoice.

```text
# SHELL / INVOICES CURRENT
python dnsfcli.py invoices current
```

Retrieve a paginated list of resources.

```text
# SHELL / INVOICES LIST
python dnsfcli.py invoices list --page 1 --per_page 25
```

Retrieve a single resource by ID.

```text
# SHELL / INVOICES SHOW
python dnsfcli.py invoices show --id 12345
```

## ip-addresses

IP address management.

Create a new resource.

```text
# SHELL / IP-ADDRESSES CREATE
python dnsfcli.py ip-addresses create \ --address 203.0.113.5 \ --organization_id 802315 \ --network_id 736401
```

Permanently delete a resource by ID.

```text
# SHELL / IP-ADDRESSES DELETE
python dnsfcli.py ip-addresses delete --id 12345
```

Retrieve a paginated list of resources.

```text
# SHELL / IP-ADDRESSES LIST
python dnsfcli.py ip-addresses list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / IP-ADDRESSES LIST-ALL
python dnsfcli.py ip-addresses list-all
```

Return the public IP address of the calling client.

```text
# SHELL / IP-ADDRESSES MYIP
python dnsfcli.py ip-addresses myip
```

Retrieve a single resource by ID.

```text
# SHELL / IP-ADDRESSES SHOW
python dnsfcli.py ip-addresses show --id 12345
```

Update an existing resource by ID.

```text
# SHELL / IP-ADDRESSES UPDATE
python dnsfcli.py ip-addresses update --id 12345 --address 203.0.113.5
```

Verify whether an IP address is registered.

```text
# SHELL / IP-ADDRESSES VERIFY
python dnsfcli.py ip-addresses verify
```

## mac-addresses

MAC address management.

Create a new resource.

```text
# SHELL / MAC-ADDRESSES CREATE
python dnsfcli.py mac-addresses create \ --organization_id 802315 \ --address "AA:BB:CC:DD:EE:FF" \ --filter_value "Reception Printer" \ --policy_id 285109
```

Permanently delete a resource by ID.

```text
# SHELL / MAC-ADDRESSES DELETE
python dnsfcli.py mac-addresses delete --id 12345
```

Retrieve a paginated list of resources.

```text
# SHELL / MAC-ADDRESSES LIST
python dnsfcli.py mac-addresses list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / MAC-ADDRESSES LIST-ALL
python dnsfcli.py mac-addresses list-all
```

Retrieve a single resource by ID.

```text
# SHELL / MAC-ADDRESSES SHOW
python dnsfcli.py mac-addresses show --id 12345
```

Update an existing resource by ID.

```text
# SHELL / MAC-ADDRESSES UPDATE
python dnsfcli.py mac-addresses update \ --id 12345 \ --address "AA:BB:CC:DD:EE:FF" \ --filter_value "Updated Label"
```

## metrics

Organization usage metrics.

Organization usage metrics.

```text
# SHELL / METRICS ORG-USAGE
python dnsfcli.py metrics org-usage --id 802315
```

Detailed organization usage metrics.

```text
# SHELL / METRICS ORG-USAGE-DETAILED
python dnsfcli.py metrics org-usage-detailed --id 802315
```

## networks

Network management.

Create multiple resources in a single async job.

```text
# SHELL / NETWORKS BULK-CREATE
python dnsfcli.py networks bulk-create
```

Check the status of a bulk-create job.

```text
# SHELL / NETWORKS BULK-CREATE-SHOW
python dnsfcli.py networks bulk-create-show --id 736401
```

Delete multiple resources in a single async job.

```text
# SHELL / NETWORKS BULK-DESTROY
python dnsfcli.py networks bulk-destroy
```

Check the status of a bulk-destroy job.

```text
# SHELL / NETWORKS BULK-DESTROY-SHOW
python dnsfcli.py networks bulk-destroy-show --id 736401
```

Update multiple resources in a single operation.

```text
# SHELL / NETWORKS BULK-UPDATE
python dnsfcli.py networks bulk-update --ids 736401,736402 --policy_id 285109
```

Check the status of a bulk-update job.

```text
# SHELL / NETWORKS BULK-UPDATE-SHOW
python dnsfcli.py networks bulk-update-show --id 736401
```

Return counts of resources matching optional filters.

```text
# SHELL / NETWORKS COUNTS
python dnsfcli.py networks counts
```

Create a new resource.

```text
# SHELL / NETWORKS CREATE
python dnsfcli.py networks create \ --name "HQ Network" \ --organization_id 802315 \ --policy_ids ["285109"] \ --physical_address "123 Main St, Denver CO"
```

Permanently delete a resource by ID.

```text
# SHELL / NETWORKS DELETE
python dnsfcli.py networks delete --id 736401
```

Return geographic information for resources.

```text
# SHELL / NETWORKS GEO
python dnsfcli.py networks geo
```

Retrieve a single LAN IP address entry.

```text
# SHELL / NETWORKS LAN-IP-SHOW
python dnsfcli.py networks lan-ip-show --id 736401 --lan_ip_id 9901
```

Update the name of a LAN IP address entry.

```text
# SHELL / NETWORKS LAN-IP-UPDATE
python dnsfcli.py networks lan-ip-update \ --id 736401 \ --lan_ip_id 9901 \ --name "Reception Desk"
```

List LAN IP addresses registered to a network.

```text
# SHELL / NETWORKS LAN-IPS
python dnsfcli.py networks lan-ips --id 736401
```

Retrieve a paginated list of resources.

```text
# SHELL / NETWORKS LIST
python dnsfcli.py networks list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / NETWORKS LIST-ALL
python dnsfcli.py networks list-all
```

Find a resource matching a specific value.

```text
# SHELL / NETWORKS LOOKUP
python dnsfcli.py networks lookup
```

List resources visible to the MSP account.

```text
# SHELL / NETWORKS MSP
python dnsfcli.py networks msp
```

List all resources visible to the MSP account.

```text
# SHELL / NETWORKS MSP-ALL
python dnsfcli.py networks msp-all
```

Generate a new network secret key.

```text
# SHELL / NETWORKS SECRET-KEY-CREATE
python dnsfcli.py networks secret-key-create --id 736401
```

Delete the network secret key.

```text
# SHELL / NETWORKS SECRET-KEY-DELETE
python dnsfcli.py networks secret-key-delete --id 736401
```

Rotate the network secret key.

```text
# SHELL / NETWORKS SECRET-KEY-UPDATE
python dnsfcli.py networks secret-key-update --id 736401
```

Retrieve a single resource by ID.

```text
# SHELL / NETWORKS SHOW
python dnsfcli.py networks show --id 736401
```

List all subnets across all networks.

```text
# SHELL / NETWORKS SUBNETS
python dnsfcli.py networks subnets
```

Add a subnet IP range to a network.

```text
# SHELL / NETWORKS SUBNETS-CREATE
python dnsfcli.py networks subnets-create \ --id 736401 \ --name "Sales Floor" \ --from 10.0.1.0 \ --to 10.0.1.255
```

Remove a subnet from a network.

```text
# SHELL / NETWORKS SUBNETS-DELETE
python dnsfcli.py networks subnets-delete --id 736401 --subnet_id 4455
```

List subnets within a specific network.

```text
# SHELL / NETWORKS SUBNETS-LIST
python dnsfcli.py networks subnets-list --id 736401
```

Retrieve a specific subnet.

```text
# SHELL / NETWORKS SUBNETS-SHOW
python dnsfcli.py networks subnets-show --id 736401 --subnet_id 4455
```

Update an existing subnet's name or IP range.

```text
# SHELL / NETWORKS SUBNETS-UPDATE
python dnsfcli.py networks subnets-update \ --id 736401 \ --subnet_id 4455 \ --name "Sales Floor Renamed" \ --from 10.0.1.0 \ --to 10.0.1.255
```

Update an existing resource by ID.

```text
# SHELL / NETWORKS UPDATE
python dnsfcli.py networks update \ --id 736401 \ --name "HQ Network Updated" \ --organization_id 802315
```

## organizations

Organization management.

Update multiple resources in a single operation.

```text
# SHELL / ORGANIZATIONS BULK-UPDATE
python dnsfcli.py organizations bulk-update \ --organization_ids ["802315","802316"] \ --gdpr true
```

Cancel an organization's subscription.

```text
# SHELL / ORGANIZATIONS CANCEL
python dnsfcli.py organizations cancel --id 802315
```

Create a new resource.

```text
# SHELL / ORGANIZATIONS CREATE
python dnsfcli.py organizations create \ --name "New Client Corp" \ --billing_contact_email admin@company.com \ --sku professional
```

Permanently delete a resource by ID.

```text
# SHELL / ORGANIZATIONS DELETE
python dnsfcli.py organizations delete --id 802315
```

Retrieve a paginated list of resources.

```text
# SHELL / ORGANIZATIONS LIST
python dnsfcli.py organizations list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / ORGANIZATIONS LIST-ALL
python dnsfcli.py organizations list-all
```

Retrieve organization-level settings.

```text
# SHELL / ORGANIZATIONS SETTINGS
python dnsfcli.py organizations settings
```

Retrieve a single resource by ID.

```text
# SHELL / ORGANIZATIONS SHOW
python dnsfcli.py organizations show --id 802315
```

Update an existing resource by ID.

```text
# SHELL / ORGANIZATIONS UPDATE
python dnsfcli.py organizations update \ --id 802315 \ --name "New Client Corp Updated"
```

Add a new user to an organization.

```text
# SHELL / ORGANIZATIONS USERS-CREATE
python dnsfcli.py organizations users-create \ --organization_id 802315 \ --email admin@company.com \ --first_name Jane \ --last_name Smith \ --role administrator
```

Remove a user from an organization or collection.

```text
# SHELL / ORGANIZATIONS USERS-DELETE
python dnsfcli.py organizations users-delete \ --organization_id 802315 \ --id 802315
```

List users within a specific organization or collection.

```text
# SHELL / ORGANIZATIONS USERS-LIST
python dnsfcli.py organizations users-list --organization_id 802315
```

Re-send the email invitation to an org user.

```text
# SHELL / ORGANIZATIONS USERS-RESEND-INVITE
python dnsfcli.py organizations users-resend-invite \ --organization_id 802315 \ --id 802315
```

Retrieve a specific user within an organization or collection.

```text
# SHELL / ORGANIZATIONS USERS-SHOW
python dnsfcli.py organizations users-show --organization_id 802315 --id 802315
```

Update a user's role or details within an organization.

```text
# SHELL / ORGANIZATIONS USERS-UPDATE
python dnsfcli.py organizations users-update \ --organization_id 802315 \ --id 802315 \ --role read_only
```

## policies

DNS filtering policy management.

Allow a specific application on a policy.

```text
# SHELL / POLICIES ADD-ALLOWED-APPLICATION
python dnsfcli.py policies add-allowed-application --id 12345 --name TikTok
```

Block all domains in a category on a policy.

```text
# SHELL / POLICIES ADD-BLACKLIST-CATEGORY
python dnsfcli.py policies add-blacklist-category --id 12345 --category_id 2
```

Block a specific domain on a policy.

```text
# SHELL / POLICIES ADD-BLACKLIST-DOMAIN
python dnsfcli.py policies add-blacklist-domain \ --id 12345 \ --domain malware.example.com \ --note "Flagged by threat intel"
```

Block a specific application on a policy.

```text
# SHELL / POLICIES ADD-BLOCKED-APPLICATION
python dnsfcli.py policies add-blocked-application --id 12345 --name TikTok
```

Allow a specific domain on a policy.

```text
# SHELL / POLICIES ADD-WHITELIST-DOMAIN
python dnsfcli.py policies add-whitelist-domain \ --id 12345 \ --domain internal.corp.com
```

List policies with application filtering enabled.

```text
# SHELL / POLICIES APPLICATION
python dnsfcli.py policies application
```

Update application filtering settings across policies.

```text
# SHELL / POLICIES APPLICATION-UPDATE
python dnsfcli.py policies application-update
```

Add domains to the allowlist on multiple policies at once.

```text
# SHELL / POLICIES BULK-ADD-ALLOWLIST
python dnsfcli.py policies bulk-add-allowlist \ --policy_ids ["285109","331207"] \ --domains ["safe.com","trusted.org"]
```

Add domains to the blocklist on multiple policies at once.

```text
# SHELL / POLICIES BULK-ADD-BLOCKLIST
python dnsfcli.py policies bulk-add-blocklist \ --policy_ids ["285109","331207"] \ --domains ["evil.com","malware.net"]
```

Remove domains from the allowlist on multiple policies.

```text
# SHELL / POLICIES BULK-REMOVE-ALLOWLIST
python dnsfcli.py policies bulk-remove-allowlist \ --policy_ids ["285109"] \ --domains ["safe.com"]
```

Remove domains from the blocklist on multiple policies.

```text
# SHELL / POLICIES BULK-REMOVE-BLOCKLIST
python dnsfcli.py policies bulk-remove-blocklist \ --policy_ids ["285109"] \ --domains ["evil.com"]
```

Create a new resource.

```text
# SHELL / POLICIES CREATE
python dnsfcli.py policies create \ --name "Guest WiFi" \ --organization_id 802315 \ --allow_unknown_domains true \ --google_safesearch true \ --youtube_restricted true \ --youtube_restricted_level strict
```

Permanently delete a resource by ID.

```text
# SHELL / POLICIES DELETE
python dnsfcli.py policies delete --id 12345
```

Retrieve a paginated list of resources.

```text
# SHELL / POLICIES LIST
python dnsfcli.py policies list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / POLICIES LIST-ALL
python dnsfcli.py policies list-all
```

Check whether permissive mode is enabled for a policy.

```text
# SHELL / POLICIES PERMISSIVE-MODE
python dnsfcli.py policies permissive-mode --id 12345
```

Remove an application from the allowlist on a policy.

```text
# SHELL / POLICIES REMOVE-ALLOWED-APPLICATION
python dnsfcli.py policies remove-allowed-application --id 12345 --name TikTok
```

Unblock a category on a policy.

```text
# SHELL / POLICIES REMOVE-BLACKLIST-CATEGORY
python dnsfcli.py policies remove-blacklist-category --id 12345 --category_id 2
```

Remove a domain from the blocklist on a policy.

```text
# SHELL / POLICIES REMOVE-BLACKLIST-DOMAIN
python dnsfcli.py policies remove-blacklist-domain \ --id 12345 \ --domain malware.example.com
```

Remove an application from the blocklist on a policy.

```text
# SHELL / POLICIES REMOVE-BLOCKED-APPLICATION
python dnsfcli.py policies remove-blocked-application --id 12345 --name TikTok
```

Remove a domain from the allowlist on a policy.

```text
# SHELL / POLICIES REMOVE-WHITELIST-DOMAIN
python dnsfcli.py policies remove-whitelist-domain \ --id 12345 \ --domain internal.corp.com
```

Enable or disable permissive mode on a policy.

```text
# SHELL / POLICIES SET-PERMISSIVE-MODE
python dnsfcli.py policies set-permissive-mode --id 12345
```

Retrieve a single resource by ID.

```text
# SHELL / POLICIES SHOW
python dnsfcli.py policies show --id 12345
```

Update an existing resource by ID.

```text
# SHELL / POLICIES UPDATE
python dnsfcli.py policies update \ --id 12345 \ --name "Guest WiFi Updated" \ --organization_id 802315 \ --interstitial true
```

## policy-ips

Policy IP associations.

Retrieve a paginated list of resources.

```text
# SHELL / POLICY-IPS LIST
python dnsfcli.py policy-ips list --page 1 --per_page 25
```

Retrieve a single resource by ID.

```text
# SHELL / POLICY-IPS SHOW
python dnsfcli.py policy-ips show --id 285109
```

## psa-integrations

PSA integration links.

Get the PSA integration redirect link.

```text
# SHELL / PSA-INTEGRATIONS REDIRECT-LINK
python dnsfcli.py psa-integrations redirect-link
```

## scheduled-policies

Scheduled policy management.

Create a new resource.

```text
# SHELL / SCHEDULED-POLICIES CREATE
python dnsfcli.py scheduled-policies create \ --name "School Hours" \ --organization_id 802315 \ --policy_ids ["285109"] \ --timezone America/Denver
```

Permanently delete a resource by ID.

```text
# SHELL / SCHEDULED-POLICIES DELETE
python dnsfcli.py scheduled-policies delete --id 12345
```

Retrieve a paginated list of resources.

```text
# SHELL / SCHEDULED-POLICIES LIST
python dnsfcli.py scheduled-policies list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / SCHEDULED-POLICIES LIST-ALL
python dnsfcli.py scheduled-policies list-all
```

Retrieve a single resource by ID.

```text
# SHELL / SCHEDULED-POLICIES SHOW
python dnsfcli.py scheduled-policies show --id 12345
```

Update an existing resource by ID.

```text
# SHELL / SCHEDULED-POLICIES UPDATE
python dnsfcli.py scheduled-policies update \ --id 12345 \ --name "School Hours Updated" \ --timezone America/Chicago
```

## scheduled-reports

Scheduled report management.

Create a new resource.

```text
# SHELL / SCHEDULED-REPORTS CREATE
python dnsfcli.py scheduled-reports create \ --organization_id 802315 \ --frequency weekly \ --day_of_week 1 \ --include_threat_summary true \ --send_to_dashboard_users true
```

Permanently delete a resource by ID.

```text
# SHELL / SCHEDULED-REPORTS DELETE
python dnsfcli.py scheduled-reports delete --id 12345
```

Retrieve a paginated list of resources.

```text
# SHELL / SCHEDULED-REPORTS LIST
python dnsfcli.py scheduled-reports list --page 1 --per_page 25
```

Generate an immediate preview of a scheduled report.

```text
# SHELL / SCHEDULED-REPORTS PREVIEW-CREATE
python dnsfcli.py scheduled-reports preview-create \ --organization_id 802315 \ --include_threat_summary true
```

Retrieve the result of a report preview job.

```text
# SHELL / SCHEDULED-REPORTS PREVIEW-SHOW
python dnsfcli.py scheduled-reports preview-show --id 12345
```

Retrieve a single resource by ID.

```text
# SHELL / SCHEDULED-REPORTS SHOW
python dnsfcli.py scheduled-reports show --id 12345
```

Update an existing resource by ID.

```text
# SHELL / SCHEDULED-REPORTS UPDATE
python dnsfcli.py scheduled-reports update --id 12345 --frequency monthly
```

## traffic-reports

DNS traffic analytics and reporting (all GET).

Queries per second.

```text
# SHELL / TRAFFIC-REPORTS QPS
python dnsfcli.py traffic-reports qps \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

QPS for active agents.

```text
# SHELL / TRAFFIC-REPORTS QPS-ACTIVE-AGENTS
python dnsfcli.py traffic-reports qps-active-agents \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

QPS for active collections.

```text
# SHELL / TRAFFIC-REPORTS QPS-ACTIVE-COLLECTIONS
python dnsfcli.py traffic-reports qps-active-collections \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

QPS for active organizations.

```text
# SHELL / TRAFFIC-REPORTS QPS-ACTIVE-ORGANIZATIONS
python dnsfcli.py traffic-reports qps-active-organizations \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

QPS for active users.

```text
# SHELL / TRAFFIC-REPORTS QPS-ACTIVE-USERS
python dnsfcli.py traffic-reports qps-active-users \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Query log export.

```text
# SHELL / TRAFFIC-REPORTS QUERY-LOGS
python dnsfcli.py traffic-reports query-logs \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top agents by query volume.

```text
# SHELL / TRAFFIC-REPORTS TOP-AGENTS
python dnsfcli.py traffic-reports top-agents \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top application categories.

```text
# SHELL / TRAFFIC-REPORTS TOP-APPLICATION-CATEGORIES
python dnsfcli.py traffic-reports top-application-categories \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top DNS categories.

```text
# SHELL / TRAFFIC-REPORTS TOP-CATEGORIES
python dnsfcli.py traffic-reports top-categories \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top collections by query volume.

```text
# SHELL / TRAFFIC-REPORTS TOP-COLLECTIONS
python dnsfcli.py traffic-reports top-collections \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top queried domains.

```text
# SHELL / TRAFFIC-REPORTS TOP-DOMAINS
python dnsfcli.py traffic-reports top-domains \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top networks by query volume.

```text
# SHELL / TRAFFIC-REPORTS TOP-NETWORKS
python dnsfcli.py traffic-reports top-networks \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top organizations by query volume.

```text
# SHELL / TRAFFIC-REPORTS TOP-ORGANIZATIONS
python dnsfcli.py traffic-reports top-organizations \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top organizations by request count.

```text
# SHELL / TRAFFIC-REPORTS TOP-ORGANIZATIONS-REQUESTS
python dnsfcli.py traffic-reports top-organizations-requests \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Top users by query volume.

```text
# SHELL / TRAFFIC-REPORTS TOP-USERS
python dnsfcli.py traffic-reports top-users \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total application stats by agent.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-APPLICATIONS-AGENTS-STATS
python dnsfcli.py traffic-reports total-applications-agents-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total application stats by collection.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-APPLICATIONS-COLLECTIONS-STATS
python dnsfcli.py traffic-reports total-applications-collections-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total application stats by network.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-APPLICATIONS-NETWORKS-STATS
python dnsfcli.py traffic-reports total-applications-networks-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total application stats by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-APPLICATIONS-ORGANIZATIONS-STATS
python dnsfcli.py traffic-reports total-applications-organizations-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total application stats.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-APPLICATIONS-STATS
python dnsfcli.py traffic-reports total-applications-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total application stats by user.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-APPLICATIONS-USERS-STATS
python dnsfcli.py traffic-reports total-applications-users-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total queries by category.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-CATEGORIES
python dnsfcli.py traffic-reports total-categories \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total category stats by agent.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-CATEGORIES-AGENTS
python dnsfcli.py traffic-reports total-categories-agents \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total category stats by collection.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-CATEGORIES-COLLECTIONS
python dnsfcli.py traffic-reports total-categories-collections \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total category stats by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-CATEGORIES-ORGANIZATIONS
python dnsfcli.py traffic-reports total-categories-organizations \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total category stats by user.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-CATEGORIES-USERS
python dnsfcli.py traffic-reports total-categories-users \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total category stats.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-CATEGORY-STATS
python dnsfcli.py traffic-reports total-category-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total client (agent) stats.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-CLIENT-STATS
python dnsfcli.py traffic-reports total-client-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total queries by collection.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-COLLECTIONS
python dnsfcli.py traffic-reports total-collections \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total collection stats by agent.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-COLLECTIONS-AGENTS
python dnsfcli.py traffic-reports total-collections-agents \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total collection stats by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-COLLECTIONS-ORGANIZATIONS
python dnsfcli.py traffic-reports total-collections-organizations \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total collection stats by user.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-COLLECTIONS-USERS
python dnsfcli.py traffic-reports total-collections-users \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total deployments.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-DEPLOYMENTS
python dnsfcli.py traffic-reports total-deployments \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total requests per domain.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-DOMAIN-REQUESTS
python dnsfcli.py traffic-reports total-domain-requests \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total domain stats.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-DOMAIN-STATS
python dnsfcli.py traffic-reports total-domain-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total unique domains queried.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-DOMAINS
python dnsfcli.py traffic-reports total-domains \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total domains by collection.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-DOMAINS-COLLECTIONS
python dnsfcli.py traffic-reports total-domains-collections \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total domains by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-DOMAINS-ORGANIZATIONS
python dnsfcli.py traffic-reports total-domains-organizations \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total domains by user.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-DOMAINS-USERS
python dnsfcli.py traffic-reports total-domains-users \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total requests by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-ORGANIZATIONS-REQUESTS
python dnsfcli.py traffic-reports total-organizations-requests \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total stats by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-ORGANIZATIONS-STATS
python dnsfcli.py traffic-reports total-organizations-stats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total DNS requests.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-REQUESTS
python dnsfcli.py traffic-reports total-requests \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total requests by agent.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-REQUESTS-AGENTS
python dnsfcli.py traffic-reports total-requests-agents \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total requests by collection.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-REQUESTS-COLLECTIONS
python dnsfcli.py traffic-reports total-requests-collections \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total requests by geography.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-REQUESTS-GEO
python dnsfcli.py traffic-reports total-requests-geo \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total requests by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-REQUESTS-ORGANIZATIONS
python dnsfcli.py traffic-reports total-requests-organizations \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total requests by user.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-REQUESTS-USERS
python dnsfcli.py traffic-reports total-requests-users \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total roaming client stats.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-ROAMING-CLIENTS
python dnsfcli.py traffic-reports total-roaming-clients \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total threats blocked.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-THREATS
python dnsfcli.py traffic-reports total-threats \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total threats by agent.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-THREATS-AGENTS
python dnsfcli.py traffic-reports total-threats-agents \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total threats by collection.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-THREATS-COLLECTIONS
python dnsfcli.py traffic-reports total-threats-collections \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total threats by organization.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-THREATS-ORGANIZATIONS
python dnsfcli.py traffic-reports total-threats-organizations \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

Total threats by user.

```text
# SHELL / TRAFFIC-REPORTS TOTAL-THREATS-USERS
python dnsfcli.py traffic-reports total-threats-users \ --start_date 2025-01-01 \ --end_date 2025-01-31
```

## user-agent-bulk-deletes

Bulk agent deletion jobs.

Return counts of resources matching optional filters.

```text
# SHELL / USER-AGENT-BULK-DELETES COUNTS
python dnsfcli.py user-agent-bulk-deletes counts
```

Create a new resource.

```text
# SHELL / USER-AGENT-BULK-DELETES CREATE
python dnsfcli.py user-agent-bulk-deletes create \ --ids ["9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5"]
```

Retrieve a single resource by ID.

```text
# SHELL / USER-AGENT-BULK-DELETES SHOW
python dnsfcli.py user-agent-bulk-deletes show \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

## user-agent-bulk-updates

Bulk agent update jobs.

Return counts of resources matching optional filters.

```text
# SHELL / USER-AGENT-BULK-UPDATES COUNTS
python dnsfcli.py user-agent-bulk-updates counts
```

Create a new resource.

```text
# SHELL / USER-AGENT-BULK-UPDATES CREATE
python dnsfcli.py user-agent-bulk-updates create \ --ids ["9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5"] \ --policy_id 285109
```

Check whether the selected agents have mixed field values.

```text
# SHELL / USER-AGENT-BULK-UPDATES HAS-MIXED
python dnsfcli.py user-agent-bulk-updates has-mixed \ --ids ["9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5"]
```

Retrieve a single resource by ID.

```text
# SHELL / USER-AGENT-BULK-UPDATES SHOW
python dnsfcli.py user-agent-bulk-updates show \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

## user-agent-cleanups

Agent cleanup jobs.

Create a new resource.

```text
# SHELL / USER-AGENT-CLEANUPS CREATE
python dnsfcli.py user-agent-cleanups create \ --organization_ids ["802315"] \ --inactive_for 30
```

Retrieve a single resource by ID.

```text
# SHELL / USER-AGENT-CLEANUPS SHOW
python dnsfcli.py user-agent-cleanups show \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

Update an existing resource by ID.

```text
# SHELL / USER-AGENT-CLEANUPS UPDATE
python dnsfcli.py user-agent-cleanups update \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5 \ --start true \ --inactive_for 30
```

## user-agent-csv-exports

Agent CSV export jobs.

Create a new resource.

```text
# SHELL / USER-AGENT-CSV-EXPORTS CREATE
python dnsfcli.py user-agent-csv-exports create --organization_ids ["802315"]
```

Retrieve a single resource by ID.

```text
# SHELL / USER-AGENT-CSV-EXPORTS SHOW
python dnsfcli.py user-agent-csv-exports show \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

## user-agent-releases

Agent release information.

Retrieve a paginated list of resources.

```text
# SHELL / USER-AGENT-RELEASES LIST
python dnsfcli.py user-agent-releases list --page 1 --per_page 25
```

Retrieve the relay channel's latest agent release.

```text
# SHELL / USER-AGENT-RELEASES RELAY
python dnsfcli.py user-agent-releases relay
```

## user-agents

Roaming agent (client) management.

Return counts of resources matching optional filters.

```text
# SHELL / USER-AGENTS COUNTS
python dnsfcli.py user-agents counts
```

Export all roaming agents to CSV format.

```text
# SHELL / USER-AGENTS CSV
python dnsfcli.py user-agents csv
```

Permanently delete a resource by ID.

```text
# SHELL / USER-AGENTS DELETE
python dnsfcli.py user-agents delete --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

Dequeue a pending uninstall request for an agent.

```text
# SHELL / USER-AGENTS DEQUEUE-UNINSTALL
python dnsfcli.py user-agents dequeue-uninstall
```

Retrieve a paginated list of resources.

```text
# SHELL / USER-AGENTS LIST
python dnsfcli.py user-agents list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / USER-AGENTS LIST-ALL
python dnsfcli.py user-agents list-all
```

Retrieve a single resource by ID.

```text
# SHELL / USER-AGENTS SHOW
python dnsfcli.py user-agents show --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

List all tags assigned to roaming agents.

```text
# SHELL / USER-AGENTS TAGS
python dnsfcli.py user-agents tags
```

Retrieve the uninstall PIN for roaming agents.

```text
# SHELL / USER-AGENTS UNINSTALL-PIN
python dnsfcli.py user-agents uninstall-pin
```

Update an existing resource by ID.

```text
# SHELL / USER-AGENTS UPDATE
python dnsfcli.py user-agents update \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5 \ --friendly_name Finance-Laptop \ --policy_id 285109 \ --tags ["managed","finance"]
```

## users

User management.

Change the current user's password.

```text
# SHELL / USERS CHANGE-PASSWORD
python dnsfcli.py users change-password --new_password NewSecurePass123!
```

Retrieve a paginated list of resources.

```text
# SHELL / USERS LIST
python dnsfcli.py users list --page 1 --per_page 25
```

Retrieve all resources without pagination limits.

```text
# SHELL / USERS LIST-ALL
python dnsfcli.py users list-all
```

Retrieve a single resource by ID.

```text
# SHELL / USERS SHOW
python dnsfcli.py users show --id 12345
```

## v2-agent-local-users

v2 Agent local user endpoints.

Return counts of resources matching optional filters.

```text
# SHELL / V2-AGENT-LOCAL-USERS COUNTS
python dnsfcli.py v2-agent-local-users counts
```

Create an async CSV export job.

```text
# SHELL / V2-AGENT-LOCAL-USERS CSV-EXPORT
python dnsfcli.py v2-agent-local-users csv-export --organization_ids ["802315"]
```

Check the status of a CSV export job.

```text
# SHELL / V2-AGENT-LOCAL-USERS CSV-EXPORT-SHOW
python dnsfcli.py v2-agent-local-users csv-export-show \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

## v2-current-user

v2 Current user endpoints.

Suppress the license warning for the current user.

```text
# SHELL / V2-CURRENT-USER SUPPRESS-LICENSE-WARNING
python dnsfcli.py v2-current-user suppress-license-warning
```

Retrieve the current user's UI settings.

```text
# SHELL / V2-CURRENT-USER UI-SETTINGS
python dnsfcli.py v2-current-user ui-settings
```

Update the current user's UI settings.

```text
# SHELL / V2-CURRENT-USER UI-SETTINGS-UPDATE
python dnsfcli.py v2-current-user ui-settings-update --theme_mode dark
```

## v2-dictionary

v2 Dictionary / reference data.

List available Cyber Sight activity types.

```text
# SHELL / V2-DICTIONARY CYBER-SIGHT-ACTIVITY-TYPES
python dnsfcli.py v2-dictionary cyber-sight-activity-types
```

List available VPN settings state types.

```text
# SHELL / V2-DICTIONARY VPN-SETTINGS-STATE-TYPES
python dnsfcli.py v2-dictionary vpn-settings-state-types
```

## v2-networks

v2 Network export endpoints.

Create an async CSV export job.

```text
# SHELL / V2-NETWORKS CSV-EXPORT
python dnsfcli.py v2-networks csv-export --organization_ids ["802315"]
```

Check the status of a CSV export job.

```text
# SHELL / V2-NETWORKS CSV-EXPORT-SHOW
python dnsfcli.py v2-networks csv-export-show --id 736401
```

## v2-user-agents

v2 Agent management.

Update settings for a specific roaming agent.

```text
# SHELL / V2-USER-AGENTS UPDATE-SETTINGS
python dnsfcli.py v2-user-agents update-settings \ --id 9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5
```

---

_From the team at_

**DNSFilter**
