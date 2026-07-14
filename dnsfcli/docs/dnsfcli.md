# dnsfcli Documentation

Command-line interface for the [DNSFilter](https://www.dnsfilter.com) REST API.

**Table of Contents**
- [Getting Started](#getting-started)
- [Authentication](#authentication)
- [Global Options](#global-options)
- [CSV Bulk Operations](#csv-bulk-operations)
- [Audit Trail](#audit-trail)
- [Command Discovery](#command-discovery)
- [Endpoints](#endpoints)
  - [Agent Local Users](#agent-local-users)
  - [API Keys](#api-keys)
  - [Application Categories](#application-categories)
  - [Applications](#applications)
  - [Billing](#billing)
  - [Block Pages](#block-pages)
  - [Categories](#categories)
  - [Collections](#collections)
  - [Current User](#current-user)
  - [Dictionary](#dictionary)
  - [Domains](#domains)
  - [Enterprise Connections](#enterprise-connections)
  - [Invoices](#invoices)
  - [IP Addresses](#ip-addresses)
  - [MAC Addresses](#mac-addresses)
  - [Metrics](#metrics)
  - [Networks](#networks)
  - [Organizations](#organizations)
  - [Policy IPs](#policy-ips)
  - [PSA Integrations](#psa-integrations)
  - [Policies](#policies)
  - [Scheduled Policies](#scheduled-policies)
  - [Scheduled Reports](#scheduled-reports)
  - [Traffic Reports](#traffic-reports)
  - [Users](#users)
  - [User Agents](#user-agents)
  - [User Agent Bulk Deletes](#user-agent-bulk-deletes)
  - [User Agent Bulk Updates](#user-agent-bulk-updates)
  - [User Agent Cleanups](#user-agent-cleanups)
  - [User Agent CSV Exports](#user-agent-csv-exports)
  - [User Agent Releases](#user-agent-releases)
  - [V2 Agent Local Users](#v2-agent-local-users)
  - [V2 Current User](#v2-current-user)
  - [V2 Dictionary](#v2-dictionary)
  - [V2 Networks](#v2-networks)
  - [V2 User Agents](#v2-user-agents)

---

## Getting Started

`dnsfcli` is a command-line interface for the DNSFilter API. It supports every API endpoint dynamically, CSV-driven bulk operations, and a local audit trail of all write activity.

**Quick start:**

```bash
# 1. Store your credentials
dnsfcli auth setup

# 2. Verify the connection
dnsfcli auth verify

# 3. Run your first command
dnsfcli users list
```

---

## Authentication

### auth setup

Stores API credentials in the OS keychain. If `--api-key` is omitted, the key is prompted interactively with hidden input.

```bash
dnsfcli auth setup
dnsfcli auth setup --api-key YOUR_KEY --org-id 12345
dnsfcli auth setup --base-url https://api.dnsfilter.com
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--api-key` / `-k` | string | No | DNSFilter API key. Prompted securely if omitted. |
| `--org-id` / `-o` | string | No | Default organization ID injected automatically into commands that accept `organization_id`. |
| `--base-url` / `-u` | string | No | Override the API base URL (default: `https://api.dnsfilter.com`). Must be HTTPS. |

Credentials are written to the OS keychain (macOS Keychain, Linux Secret Service, or Windows Credential Store). They persist across shell sessions and are never stored in plain text on disk.

> 💡 **Tip:** You can bypass keychain storage for scripting with environment variables. `DNSF_API_KEY` and `DNSF_ORG_ID` are read automatically by every command and take precedence over the stored values.

> ⚠️ **Warning:** Passing `--api-key` directly on the command line exposes the key in your shell history (`~/.zsh_history`, `~/.bash_history`), process listings (`ps aux`), and CI/CD logs. Use `dnsfcli auth setup` or the `DNSF_API_KEY` environment variable instead.

### auth show

Displays the currently stored credentials. The API key is masked — only a short prefix and suffix are shown to confirm which key is active without exposing the full value.

```bash
dnsfcli auth show
```

### auth verify

Makes a live test call using the stored key and reports whether the credentials are accepted. Exits with a non-zero status code on failure.

```bash
dnsfcli auth verify
```

### auth clear

Removes all stored credentials (API key, org ID, and base URL) from the OS keychain.

```bash
dnsfcli auth clear        # prompts for confirmation
dnsfcli auth clear --yes  # skip prompt (for scripting)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--yes` / `-y` | flag | No | Skip the confirmation prompt. |

> ⚠️ **Warning:** This action cannot be undone. You will need to run `dnsfcli auth setup` again before making any API calls.

---

## Global Options

The following flags are accepted by every `dnsfcli` command and may appear anywhere on the command line — before or after the endpoint and function names.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--raw` / `-r` | flag | No | Print the raw JSON response instead of the formatted table view. |
| `--verbose` / `-v` | flag | No | Log the full request URL and body before execution. Useful for debugging. |
| `--api-key` | string | No | Override the stored API key for this single call. Reads `DNSF_API_KEY` env var. |
| `--org-id` | string | No | Override the stored org ID for this single call. Reads `DNSF_ORG_ID` env var. |
| `--to-csv FILE` | string | No | Write API response results to `FILE` in CSV format. |
| `--from-csv FILE` | string | No | Read input rows from `FILE` and execute one API call per row. |
| `--columns COLS` | string | No | Comma-separated list of columns to include in output (e.g. `id,name,status`). Applies to both table display and `--to-csv` output. Unknown column names are silently ignored. |
| `--template` | flag | No | Print a blank CSV template for the operation and exit. No API call is made. |
| `--plan` | flag | No | Show a dry-run summary of what would be executed without making any API calls. |
| `--yes` / `-y` | flag | No | Skip confirmation prompts on write and destructive operations. |

> 💡 **Tip:** Global flags can appear anywhere in the command line. `dnsfcli --raw users show --id 42` and `dnsfcli users show --id 42 --raw` are equivalent.

---

## CSV Bulk Operations

Any write operation can be driven by a CSV file, letting you create, update, or delete many records in a single command.

**Recommended workflow:**

**Step 1 — Generate a blank template**

```bash
dnsfcli networks create --template > networks.csv
```

The template contains one header row with every accepted parameter as a column name.

**Step 2 — Fill in the CSV**

Open `networks.csv` in a spreadsheet editor or text editor and add one row per record.

**Step 3 — Execute the bulk operation**

```bash
dnsfcli networks create --from-csv networks.csv
```

**Worked example — create multiple networks:**

```bash
# Get the template
dnsfcli networks create --template > networks.csv

# networks.csv (after editing):
# name,policy_id,organization_id
# Branch Office A,7,12345
# Branch Office B,7,12345
# Remote Workers,9,12345

# Preview what will happen
dnsfcli networks create --from-csv networks.csv --plan

# Execute
dnsfcli networks create --from-csv networks.csv

# Save the API responses (including assigned IDs) to a results file
dnsfcli networks create --from-csv networks.csv --to-csv created_networks.csv
```

**Confirmation behaviour:**

Before executing, `dnsfcli` shows a summary and asks you to confirm:

- **POST / PATCH / PUT operations** — displays the row count and prompts: `Proceed?`
- **DELETE operations** — displays a stronger destructive warning noting the action cannot be undone, then prompts: `Proceed?`

Pass `--yes` to skip the prompt in scripts and automation:

```bash
dnsfcli networks create --from-csv networks.csv --yes
```

**Column aliases:**

The following column name aliases are accepted in CSV files so common variations in exported data work without renaming columns:

| CSV column | Treated as |
|------------|------------|
| `fqdns` | `domain` |
| `fqdn` | `domain` |
| `notes` | `note` |
| `url` | `domain` |

**Combining `--from-csv` with `--to-csv`:**

Pass both flags to read input rows and write all API response bodies to an output file in one step. This is useful for capturing assigned IDs after bulk creates:

```bash
dnsfcli networks create --from-csv input.csv --to-csv output.csv
```

---

## Audit Trail

`dnsfcli` maintains a local append-only log of every write operation. Only calls that modify data (POST, PATCH, PUT, DELETE) are recorded — read operations (GET) are not logged.

Log location: `~/.local/share/dnsfcli/audit.jsonl`

Each entry records: timestamp (UTC), org ID, endpoint, function, HTTP method, path, HTTP status, and an error message if the call failed.

> 💡 **Tip:** The log rotates at 50 lines — when the file reaches 50 entries the current log is moved to `audit.jsonl.1` and a fresh `audit.jsonl` is started. The previous 50 entries are preserved in `audit.jsonl.1`. `audit show` reads both files and merges them.

### audit show

Displays recent write operations from the audit log in a table.

```bash
dnsfcli audit show
dnsfcli audit show --last 50
dnsfcli audit show --since 2024-06-01
dnsfcli audit show --endpoint networks
dnsfcli audit show --since 2024-06-01 --endpoint networks --last 100
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--last` / `-n` | integer | No | Number of most recent events to show. Default: `20`. |
| `--since` | string | No | Only show events on or after this date. Format: `YYYY-MM-DD`. |
| `--endpoint` / `-e` | string | No | Filter to events for a specific endpoint (e.g. `networks`, `users`). |

### audit clear

Deletes both the active log file and its rotation backup.

```bash
dnsfcli audit clear        # prompts for confirmation
dnsfcli audit clear --yes  # skip prompt
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--yes` / `-y` | flag | No | Skip the confirmation prompt. |

---

## Command Discovery

### endpoints

Lists all known endpoint groups and their available functions.

```bash
# List all endpoints
dnsfcli endpoints

# Show functions for a specific endpoint
dnsfcli endpoints networks
```

### --template

Generates a blank CSV input template for any write operation and prints it to stdout. No API call is made and no authentication is required.

```bash
dnsfcli networks create --template
dnsfcli networks create --template > networks_template.csv
dnsfcli policies update --template > policies_update.csv
```

### --plan

Performs a dry run: shows exactly what API calls would be made without touching the API.

```bash
dnsfcli networks create --name "HQ" --policy_id 7 --plan
dnsfcli networks create --from-csv networks.csv --plan
```

---

## Endpoints

---

## Agent Local Users

Manage local users associated with DNSFilter roaming agents.

### list

List agent local users (paginated).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli agent-local-users list --page 1 --per_page 50
```

### list-all

Return all agent local users in a single response (no pagination).

```bash
dnsfcli agent-local-users list-all
```

### show

Show details for a single agent local user.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

```bash
dnsfcli agent-local-users show --id 1234
```

### update

Update an agent local user's display name, policy, or block page assignment.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |
| friendly_name | string | No | Display name |
| policy_id | integer | No | Policy ID |
| scheduled_policy_id | integer | No | Scheduled policy ID |
| block_page_id | integer | No | Block page ID |

```bash
dnsfcli agent-local-users update --id 1234 --friendly_name "Alice Laptop" --policy_id 99
```

### delete

Delete a single agent local user.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

> ⚠️ **Warning:** This operation is permanent and cannot be undone. Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli agent-local-users delete --id 1234
```

### bulk-delete

Permanently delete multiple agent local users in a single operation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ids | array | Yes | Array of IDs to delete |
| exclude_ids | array | No | Array of IDs to exclude |

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

> 💡 **Tip:** Run `bulk-delete-counts` before `bulk-delete` to preview scope without deleting anything.

```bash
dnsfcli agent-local-users bulk-delete --ids '[101, 102, 103]'
```

### bulk-delete-show

Show the status and results of a previously submitted bulk-delete job.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

```bash
dnsfcli agent-local-users bulk-delete-show --id 7
```

### bulk-delete-counts

Count the agent local users that would be affected by a bulk-delete operation, without deleting anything.

> 💡 **Tip:** Always run this before `bulk-delete` to verify scope.

```bash
dnsfcli agent-local-users bulk-delete-counts
```

---

## API Keys

Manage API keys used to authenticate requests to the DNSFilter API.

### list

List all API keys (paginated).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli api-keys list --page 1 --per_page 25
```

### show

Show details for a single API key.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

```bash
dnsfcli api-keys show --id 42
```

### create

Create a new API key with an optional expiry date.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | Yes | Key name |
| expiry | string | No | Expiry date (YYYY-MM-DD) |

```bash
dnsfcli api-keys create --name "CI Pipeline Key" --expiry 2027-01-01
```

### revoke

Revoke an API key immediately, preventing further use without deleting the record.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

> ⚠️ **Warning:** Revocation is immediate. Any service using this key will lose access.

```bash
dnsfcli api-keys revoke --id 42
```

### delete

Permanently delete an API key.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli api-keys delete --id 42
```

---

## Application Categories

Read-only reference data for application categories used in policy filtering.

### list

```bash
dnsfcli application-categories list
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

```bash
dnsfcli application-categories show --id 5
```

---

## Applications

Read-only catalog of applications available for policy-level allow/block rules.

### list

```bash
dnsfcli applications list
```

### list-all

```bash
dnsfcli applications list-all
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

```bash
dnsfcli applications show --id 88
```

> 💡 **Tip:** Application names used in `policies add-allowed-application` are case-sensitive. Use `applications list-all` to verify exact names.

---

## Billing

Manage billing records and subscription address information for an organization.

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID (injected automatically from stored org-id if omitted) |

```bash
dnsfcli billing show --organization_id 500
```

### get-address

```bash
dnsfcli billing get-address --organization_id 500
```

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |
| payment_token | string | Yes | Payment token |

```bash
dnsfcli billing create --organization_id 500 --payment_token tok_abc123
```

### update-address

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |
| first_name | string | No | First name |
| last_name | string | No | Last name |
| email | string | No | Email address |
| company | string | No | Company name |
| phone | string | No | Phone number |
| line1 | string | No | Address line 1 |
| line2 | string | No | Address line 2 |
| line3 | string | No | Address line 3 |
| city | string | No | City |
| state | string | No | State name |
| state_code | string | No | State code (e.g. CO) |
| zip | string | No | ZIP / postal code |
| country | string | No | Country |

```bash
dnsfcli billing update-address --organization_id 500 --city Denver --state Colorado --state_code CO --zip 80203
```

---

## Block Pages

Create and manage custom block pages displayed to users when a DNS request is blocked.

### list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli block-pages list --page 1 --per_page 20
```

### list-all

```bash
dnsfcli block-pages list-all
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

```bash
dnsfcli block-pages show --id 3
```

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | Yes | Page name |
| organization_id | integer | No | Organization ID |
| block_org_name | string | No | Organization name to display on block page |
| block_email_addr | string | No | Contact email shown on block page |
| block_logo_uuid | string | No | UUID of logo to display |

```bash
dnsfcli block-pages create --name "Corporate Block Page" --block_org_name "Acme Corp" --block_email_addr "it@acme.com"
```

### update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |
| name | string | Yes | Page name |
| block_org_name | string | No | Organization name to display |
| block_email_addr | string | No | Contact email shown on block page |
| block_logo_uuid | string | No | UUID of logo to display |

```bash
dnsfcli block-pages update --id 3 --block_email_addr "security@acme.com"
```

### delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli block-pages delete --id 3
```

---

## Categories

Read-only reference data for DNS filtering categories used in policy configuration.

### list

```bash
dnsfcli categories list
```

### list-all

```bash
dnsfcli categories list-all
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Resource ID |

```bash
dnsfcli categories show --id 12
```

---

## Collections

Manage user membership within a collection. All operations require a `collection_id` path parameter.

### users-list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| collection_id | integer | Yes | Collection ID |
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli collections users-list --collection-id 42
```

### users-show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| collection_id | integer | Yes | Collection ID |
| id | integer | Yes | User ID |

```bash
dnsfcli collections users-show --collection-id 42 --id 7
```

### users-add

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| collection_id | integer | Yes | Collection ID |
| id | integer | Yes | User ID |

```bash
dnsfcli collections users-add --collection-id 42 --id 7
```

### users-remove

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| collection_id | integer | Yes | Collection ID |
| id | integer | Yes | User ID |

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli collections users-remove --collection-id 42 --id 7 --yes
```

> 💡 **Tip:** `users-add` and `users-remove` work well with `--from-csv` for bulk membership changes.

---

## Current User

View and update the profile of the authenticated user.

### show

```bash
dnsfcli current-user show
```

### update

Body parameters are automatically wrapped under the `user` key before the request is sent.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| first_name | string | No | First name |
| last_name | string | No | Last name |
| phone | string | No | Phone number |

```bash
dnsfcli current-user update --first_name Jane --last_name Doe
```

---

## Dictionary

Reference data for API method types.

### qp-methods

Return the list of QP method types recognized by the API.

```bash
dnsfcli dictionary qp-methods
```

---

## Domains

Domain lookup and classification utilities.

### user-lookup

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| fqdn | string | No | FQDN to look up |

```bash
dnsfcli domains user-lookup --fqdn example.com
```

### bulk-lookup

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| fqdns | string | Yes | Comma-separated list of FQDNs to classify |

```bash
dnsfcli domains bulk-lookup --fqdns "example.com,malware.example.net,ads.example.org"
```

> 💡 **Tip:** Output includes resolved category names for each domain.

### suggest-threat

Submit a domain to the DNSFilter threat-intelligence team for review.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| fqdn | string | Yes | FQDN to flag |
| notes | string | Yes | Reason or notes for the threat suggestion |
| categories | string | No | Comma-separated category IDs |

```bash
dnsfcli domains suggest-threat --fqdn malware.example.com --notes "Observed C2 traffic"
```

---

## Enterprise Connections

Manage enterprise SSO connections (OIDC, SAML, etc.).

### list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli enterprise-connections list --organization_id 100
```

### list-all

```bash
dnsfcli enterprise-connections list-all
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Connection ID |

```bash
dnsfcli enterprise-connections show --id 5
```

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| client_id | string | No | OAuth client ID |
| client_secret | string | No | OAuth client secret |
| discovery_url | string | No | OIDC discovery URL |
| organization_id | integer | No | Organization ID |
| default_organization_id | integer | No | Default organization ID |
| strategy | string | No | Connection strategy (`oidc`, `saml`) |
| display_name | string | No | Display name |
| role_default | string | No | Default role for new users |
| role_map | array | No | JSON array of role mapping rules |
| idp | string | No | Identity provider identifier |
| authorized_domains | array | No | Authorized email domains |

```bash
dnsfcli enterprise-connections create \
  --strategy oidc \
  --client_id "my-client-id" \
  --client_secret "my-client-secret" \
  --discovery_url "https://idp.example.com/.well-known/openid-configuration" \
  --organization_id 100
```

### update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Connection ID |
| organization_id | integer | No | Organization ID |
| display_name | string | No | Display name |
| role_default | string | No | Default role for new users |
| role_map | array | No | JSON array of role mapping rules |
| authorized_domains | array | No | Authorized email domains |

```bash
dnsfcli enterprise-connections update --id 5 --display_name "Corporate SSO"
```

### delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli enterprise-connections delete --id 5 --yes
```

---

## Invoices

### list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli invoices list --organization_id 100
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Invoice ID |

```bash
dnsfcli invoices show --id 9001
```

### current

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |

```bash
dnsfcli invoices current --organization_id 100
```

---

## IP Addresses

Manage IP addresses (including CIDR blocks) registered with DNSFilter.

### list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli ip-addresses list --page 2 --per_page 100
```

### list-all

```bash
dnsfcli ip-addresses list-all
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | IP address record ID |

```bash
dnsfcli ip-addresses show --id 301
```

### myip

Return the public IP address of the caller as seen by the API.

```bash
dnsfcli ip-addresses myip
```

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| address | string | Yes | IP address or CIDR block |
| organization_id | integer | Yes | Organization ID |
| network_id | integer | Yes | Network ID |
| dynamic_hostname | string | No | Dynamic DNS hostname |

```bash
dnsfcli ip-addresses create --address 203.0.113.10 --organization_id 100 --network_id 55
```

> 💡 **Tip:** Passing a CIDR block (e.g. `10.0.1.0/24`) automatically expands to individual host IPs — one API call per IP.

> ⚠️ **Warning:** Large CIDR ranges (`/8`, `/16`) generate tens of thousands of API calls. The client rate-limiter (~5.33 req/s) will throttle automatically but the operation may take hours.

### update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | IP address record ID |
| address | string | Yes | IP address or CIDR block |
| organization_id | integer | No | Organization ID |
| network_id | integer | No | Network ID |
| dynamic_hostname | string | No | Dynamic DNS hostname |

```bash
dnsfcli ip-addresses update --id 301 --address 203.0.113.11 --network_id 55
```

### delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli ip-addresses delete --id 301 --yes
```

### verify

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| address | string | Yes | IP address to verify |

```bash
dnsfcli ip-addresses verify --address 203.0.113.10
```

---

## MAC Addresses

Manage MAC addresses registered with DNSFilter for per-device policy enforcement.

### list / list-all / show

Standard paginated list, unpaginated list-all, and show by ID.

```bash
dnsfcli mac-addresses list
dnsfcli mac-addresses list-all
dnsfcli mac-addresses show --id 201
```

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |
| address | string | No | MAC address |
| filter_value | string | No | Filter / display label |
| policy_id | integer | No | Policy ID |
| scheduled_policy_id | integer | No | Scheduled policy ID |
| block_page_id | integer | No | Block page ID |

```bash
dnsfcli mac-addresses create --organization_id 100 --address "aa:bb:cc:dd:ee:ff" --filter_value "Conference Room A" --policy_id 10
```

### update

Same parameters as `create` plus `--id`.

```bash
dnsfcli mac-addresses update --id 201 --filter_value "Lobby TV" --policy_id 12
```

### delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli mac-addresses delete --id 201 --yes
```

---

## Metrics

Retrieve DNS query usage metrics for an organization over a date range.

### org-usage

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Organization ID |
| from | string | Yes | Start date (YYYY-MM-DD) |
| to | string | Yes | End date (YYYY-MM-DD) |

```bash
dnsfcli metrics org-usage --id 100 --from 2026-01-01 --to 2026-01-31
```

### org-usage-detailed

Same parameters as `org-usage`. Returns per-day or per-network breakdown.

```bash
dnsfcli metrics org-usage-detailed --id 100 --from 2026-01-01 --to 2026-01-31
```

---

## Networks

Manage DNS filtering networks, including IP configuration, routing, subnets, LAN visibility, MSP delegation, and secret keys.

### Network CRUD

#### list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number |
| per_page | integer | No | Items per page |
| organization_id | integer | No | Filter by organization ID |

```bash
dnsfcli networks list --organization_id 42
```

#### list-all

```bash
dnsfcli networks list-all
```

#### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Network ID |

```bash
dnsfcli networks show --id 101
```

#### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | Yes | Network name |
| organization_id | integer | Yes | Organization ID |
| block_page_id | integer | No | Block page ID |
| policy_ids | array | No | Array of policy IDs |
| external_id | string | No | External / third-party ID |
| is_legacy_vpn_active | boolean | No | Enable legacy VPN mode |
| physical_address | string | No | Physical location address |
| ip_addresses_attributes | array | No | JSON array of IP address objects |
| local_domains | array | No | Array of local domain names |
| local_resolvers | array | No | Array of local DNS resolver IPs |

```bash
dnsfcli networks create --name "HQ Network" --organization_id 42 --policy_ids '[10,11]'
```

#### update

Same parameters as `create`, plus `--id`.

```bash
dnsfcli networks update --id 101 --name "HQ Network Updated"
```

#### delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli networks delete --id 101 --yes
```

#### counts

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |

```bash
dnsfcli networks counts --organization_id 42
```

#### lookup

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| requesting_ip_address | string | Yes | IP address to look up |

```bash
dnsfcli networks lookup --requesting_ip_address 203.0.113.10
```

### Bulk Operations

> 💡 **Tip:** `bulk-create` with `--from-csv` is ideal for provisioning many networks at once.

> ⚠️ **Warning:** `bulk-destroy` is irreversible. Run `list` or `counts` first to confirm scope.

#### bulk-create

```bash
dnsfcli networks bulk-create --from-csv networks.csv
```

#### bulk-create-show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Bulk-create job ID |

```bash
dnsfcli networks bulk-create-show --id 55
```

#### bulk-update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ids | string | Yes | Comma-separated network IDs |
| organization_id | integer | No | Organization ID |
| policy_id | integer | No | Policy ID |
| scheduled_policy_id | integer | No | Scheduled policy ID |
| block_page_id | integer | No | Block page ID |
| is_legacy_vpn_active | boolean | No | Enable legacy VPN |

```bash
dnsfcli networks bulk-update --ids "101,102,103" --policy_id 20
```

#### bulk-update-show

```bash
dnsfcli networks bulk-update-show --id 56
```

#### bulk-destroy

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ids | string | Yes | Comma-separated network IDs, or the keyword `all` |
| organization_id | integer | No | Required when `ids=all` |

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip. Passing `ids=all` with an `organization_id` deletes every network in that organization.

```bash
dnsfcli networks bulk-destroy --ids "101,102" --yes
```

#### bulk-destroy-show

```bash
dnsfcli networks bulk-destroy-show --id 57
```

### Secret Keys

#### secret-key-create / secret-key-update / secret-key-delete

All require `--id` (network ID). `secret-key-delete` requires confirmation.

```bash
dnsfcli networks secret-key-create --id 101
dnsfcli networks secret-key-update --id 101
dnsfcli networks secret-key-delete --id 101 --yes
```

### Subnets

#### subnets

List all subnets across all networks.

```bash
dnsfcli networks subnets
```

#### subnets-list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Network ID |

```bash
dnsfcli networks subnets-list --id 101
```

#### subnets-show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Network ID |
| subnet_id | integer | Yes | Subnet ID |

```bash
dnsfcli networks subnets-show --id 101 --subnet_id 9
```

#### subnets-create

Subnets use `from`/`to` IP range rather than CIDR notation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Network ID |
| name | string | Yes | Subnet name |
| from | string | Yes | Start IP address |
| to | string | Yes | End IP address |
| policy_id | integer | No | Policy ID |
| scheduled_policy_id | integer | No | Scheduled policy ID |
| block_page_id | integer | No | Block page ID |

```bash
dnsfcli networks subnets-create --id 101 --name "Floor 2" --from 10.0.2.1 --to 10.0.2.254
```

#### subnets-update

Same parameters as `subnets-create`.

#### subnets-delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli networks subnets-delete --id 101 --subnet_id 9 --yes
```

### Geographic & LAN

#### geo

```bash
dnsfcli networks geo
```

#### lan-ips

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Network ID |

```bash
dnsfcli networks lan-ips --id 101
```

#### lan-ip-show / lan-ip-update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Network ID |
| lan_ip_id | integer | Yes | LAN IP ID |
| name | string | No | LAN IP name (update only) |

```bash
dnsfcli networks lan-ip-show --id 101 --lan_ip_id 7
dnsfcli networks lan-ip-update --id 101 --lan_ip_id 7 --name "Reception Desk"
```

#### msp / msp-all

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |

```bash
dnsfcli networks msp --organization_id 42
dnsfcli networks msp-all --organization_id 42
```

---

## Organizations

Manage organizations, their settings, MSP promotion, and the users who belong to them.

### Organization CRUD

#### list / list-all / show

```bash
dnsfcli organizations list --page 1 --per_page 50
dnsfcli organizations list-all
dnsfcli organizations show --id 42
```

#### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | Yes | Organization name |
| billing_contact_name | string | No | Billing contact name |
| billing_contact_email | string | No | Billing contact email |
| address | string | No | Physical address |
| managed_by_msp_id | integer | No | Managing MSP ID |
| sku | string | No | SKU / plan code |
| quantity | integer | No | Seat quantity |
| gdpr | boolean | No | Enable GDPR mode |
| privacy_mode | string | No | Privacy mode (`standard` / `strict`) |
| enable_cybersight | boolean | No | Enable CyberSight |
| vpn_settings_organization_attributes | object | No | VPN settings JSON object |

```bash
dnsfcli organizations create --name "Acme Corp" --sku "dns-pro" --quantity 50
```

#### update

Same parameters as `create`, plus `--id`.

```bash
dnsfcli organizations update --id 42 --quantity 100
```

#### delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli organizations delete --id 42 --yes
```

#### settings

Returns the flat key-value settings panel for the current organization context.

> 💡 **Tip:** `settings` returns a flat key-value panel rather than a table.

```bash
dnsfcli organizations settings
```

#### bulk-update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_ids | array | Yes | Array of organization IDs to update |
| exclude_organization_ids | array | No | Array of organization IDs to exclude |
| gdpr | boolean | No | Enable GDPR |
| user_agents_auto_update | boolean | No | Auto-update agents |
| send_uninstall_notifications_to_admin_users | boolean | No | Send uninstall notifications |
| vpn_settings_state_type_id | integer | No | VPN state type ID |

```bash
dnsfcli organizations bulk-update --organization_ids '[42,43,44]' --gdpr true
```

#### cancel

```bash
dnsfcli organizations cancel --id 42
```

### Organization Users

#### users-list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |

```bash
dnsfcli organizations users-list --organization_id 42
```

#### users-show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |
| id | integer | Yes | User ID |

```bash
dnsfcli organizations users-show --organization_id 42 --id 7
```

#### users-create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |
| email | string | No | Email address |
| first_name | string | No | First name |
| last_name | string | No | Last name |
| role | string | No | Role: `administrator`, `read_only`, `network_administrator`, `network_support`, `support` |
| organization_permission_ids | array | No | Array of permission IDs |

```bash
dnsfcli organizations users-create --organization_id 42 --email jane@example.com --role administrator
```

#### users-update

Same parameters as `users-create`, plus `--id`.

```bash
dnsfcli organizations users-update --organization_id 42 --id 7 --role read_only
```

#### users-delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli organizations users-delete --organization_id 42 --id 7 --yes
```

#### users-resend-invite

```bash
dnsfcli organizations users-resend-invite --organization_id 42 --id 7
```

---

## Policy IPs

Read-only access to policy IP associations.

### list / show

```bash
dnsfcli policy-ips list --per_page 100
dnsfcli policy-ips show --id 3
```

---

## PSA Integrations

### redirect-link

Return the redirect URL for the active PSA integration.

```bash
dnsfcli psa-integrations redirect-link
```

---

## Policies

DNS filtering policy management. Policies define what categories, domains, and applications are allowed or blocked.

### Policy CRUD

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes (update/delete) | Policy ID |
| name | string | Yes (create) | Policy name |
| organization_id | integer | Yes (create) | Organization ID |
| allow_unknown_domains | boolean | No | Allow uncategorised domains |
| google_safesearch | boolean | No | Force Google SafeSearch |
| bing_safe_search | boolean | No | Force Bing SafeSearch |
| youtube_restricted | boolean | No | Restrict YouTube |
| youtube_restricted_level | string | No | YouTube restriction level (`strict` / `none`) |
| interstitial | boolean | No | Show interstitial warning page |
| allow_list_only | boolean | No | Block all except allowlisted domains |
| is_global_policy | boolean | No | Mark as global policy |
| append_domains | boolean | No | Append to existing domain lists (default: replace) |

```bash
dnsfcli policies list --page 1 --per_page 25
dnsfcli policies list-all
dnsfcli policies show --id 42
dnsfcli policies create --name "Guest WiFi" --organization_id 100 --youtube_restricted true
dnsfcli policies update --id 42 --allow_unknown_domains false
dnsfcli policies delete --id 42
```

> ⚠️ **Warning:** `delete` permanently removes the policy. Requires confirmation. Use `--yes` to skip.

### Domain Allow / Block Lists

#### Single-domain operations

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Policy ID |
| domain | string | Yes | Domain name to add or remove |
| note | string | No | Reason for allowing or blocking |

```bash
# Block a single domain
dnsfcli policies add-blacklist-domain --id 42 --domain malware.example.com --note "Known malware host"
dnsfcli policies remove-blacklist-domain --id 42 --domain malware.example.com

# Allow a single domain
dnsfcli policies add-whitelist-domain --id 42 --domain internal.example.com
dnsfcli policies remove-whitelist-domain --id 42 --domain internal.example.com
```

#### Bulk domain operations

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| policy_ids | array | Yes | Array of policy IDs to target |
| domains | array | Yes | Array of domain names |

```bash
dnsfcli policies bulk-add-blocklist --policy_ids '[1,2,3]' --domains '["bad.example.com"]'
dnsfcli policies bulk-remove-blocklist --policy_ids '[1,2,3]' --domains '["bad.example.com"]'
dnsfcli policies bulk-add-allowlist --policy_ids '[1,2,3]' --domains '["safe.example.com"]'
dnsfcli policies bulk-remove-allowlist --policy_ids '[1,2,3]' --domains '["safe.example.com"]'

# Import a large domain list from CSV
dnsfcli policies bulk-add-blocklist --from-csv domains.csv --policy_ids '[1,2,3]'
```

> 💡 **Tip:** `bulk-add-blocklist` with `--from-csv` is the recommended way to import large domain lists. Use `--template` to generate the CSV format.

### Category Controls

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Policy ID |
| category_id | integer | Yes | Category ID to block or unblock |

```bash
dnsfcli policies add-blacklist-category --id 42 --category_id 17
dnsfcli policies remove-blacklist-category --id 42 --category_id 17
```

> 💡 **Tip:** Use `dnsfcli categories list-all` to discover category IDs and names.

### Application Controls

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Policy ID |
| name | string | Yes | Application name (case-sensitive) |

```bash
dnsfcli policies add-allowed-application --id 42 --name "Zoom"
dnsfcli policies remove-allowed-application --id 42 --name "Zoom"
dnsfcli policies add-blocked-application --id 42 --name "BitTorrent"
dnsfcli policies remove-blocked-application --id 42 --name "BitTorrent"
```

> ⚠️ **Warning:** Application names are case-sensitive. Use `dnsfcli applications list-all` to verify exact names.

### Policy Settings

#### permissive-mode / set-permissive-mode

Permissive mode allows all traffic while still logging it — useful for auditing before enforcing a new policy.

```bash
dnsfcli policies permissive-mode --id 42
dnsfcli policies set-permissive-mode --id 42 --permissive_mode true
dnsfcli policies set-permissive-mode --id 42 --permissive_mode false
```

#### application / application-update

```bash
dnsfcli policies application --application_id 5 --organization_id 100
dnsfcli policies application-update \
  --application_id 5 \
  --organization_id 100 \
  --allow_policies '[1,2]' \
  --block_policies '[3]'
```

---

## Scheduled Policies

Scheduled policies automatically switch between different filtering policies on a time-based schedule.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes (show/update/delete) | Scheduled policy ID |
| name | string | Yes (create) | Policy name |
| organization_id | integer | No | Organization ID |
| policy_ids | array | No | Array of policy IDs to include in the schedule |
| timezone | string | No | IANA timezone string (e.g. `America/Denver`) |

```bash
dnsfcli scheduled-policies list
dnsfcli scheduled-policies list-all
dnsfcli scheduled-policies show --id 7
dnsfcli scheduled-policies create --name "School Hours" --organization_id 100 --policy_ids '[10,11]' --timezone "America/New_York"
dnsfcli scheduled-policies update --id 7 --timezone "America/Chicago"
dnsfcli scheduled-policies delete --id 7
```

> ⚠️ **Warning:** `delete` is permanent. Requires confirmation. Use `--yes` to skip.

---

## Scheduled Reports

Scheduled reports deliver periodic DNS traffic summaries via email.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes (show/update/delete) | Report ID |
| organization_id | integer | No | Organization ID |
| frequency | string | No | `daily`, `weekly`, or `monthly` |
| day_of_week | string | No | Day of week for weekly reports (`0`=Sunday … `6`=Saturday) |
| include_threat_summary | boolean | No | Include threat summary section |
| include_content_category_summary | boolean | No | Include category summary section |
| send_to_dashboard_users | boolean | No | Send to all dashboard users |
| scheduled_report_recipients | array | No | Array of recipient objects (JSON) |

```bash
dnsfcli scheduled-reports list --organization_id 100
dnsfcli scheduled-reports show --id 3
dnsfcli scheduled-reports create \
  --organization_id 100 \
  --frequency weekly \
  --day_of_week 1 \
  --include_threat_summary true \
  --send_to_dashboard_users true
dnsfcli scheduled-reports update --id 3 --frequency monthly
dnsfcli scheduled-reports delete --id 3
```

> ⚠️ **Warning:** `delete` is permanent. Requires confirmation. Use `--yes` to skip.

### Report Previews

Generate an on-demand preview of what a report will contain before committing to a schedule.

```bash
# Create a preview job (async)
dnsfcli scheduled-reports preview-create --organization_id 100 --include_threat_summary true

# Poll for completion
dnsfcli scheduled-reports preview-show --id 88
```

> 💡 **Tip:** `preview-create` is asynchronous. Poll `preview-show` with the returned ID until the job completes.

---

## Traffic Reports

All traffic report endpoints are read-only (GET). Most accept common date range parameters.

**Common parameters (standard endpoints):**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| start_date | string | Yes | Start date (YYYY-MM-DD) |
| end_date | string | Yes | End date (YYYY-MM-DD) |
| organization_id | integer | No | Filter by organization |
| network_id | integer | No | Filter by network |
| limit | integer | No | Maximum number of results |

**Real-time parameters** (`qps-active-*`, `total-client-stats`):

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| from | string | Yes | Start datetime ISO 8601 (max 20-minute window) |
| to | string | Yes | End datetime ISO 8601 (max 20-minute window) |

> ⚠️ **Warning:** Real-time endpoints enforce a maximum 20-minute query window.

### Query Logs & QPS

| Function | Description |
|---|---|
| `qps` | Queries per second over the requested period |
| `qps-active-agents` | Real-time QPS by active agents |
| `qps-active-collections` | Real-time QPS by active collections |
| `qps-active-organizations` | Real-time QPS by active organizations |
| `qps-active-users` | Real-time QPS by active users |
| `query-logs` | Raw query log export |

```bash
dnsfcli traffic-reports qps --start_date 2026-06-01 --end_date 2026-06-14 --organization_id 100
dnsfcli traffic-reports query-logs --start_date 2026-06-14 --end_date 2026-06-14 --organization_id 100
```

### Top Lists

| Function | Description |
|---|---|
| `top-agents` | Top agents by query volume |
| `top-application-categories` | Top application categories |
| `top-categories` | Top DNS categories |
| `top-collections` | Top collections |
| `top-domains` | Top queried domains |
| `top-networks` | Top networks |
| `top-organizations` | Top organizations |
| `top-users` | Top users |

```bash
dnsfcli traffic-reports top-domains --start_date 2026-06-01 --end_date 2026-06-14 --organization_id 100 --limit 10
```

### Request Totals

`total-requests`, `total-requests-agents`, `total-requests-collections`, `total-requests-geo`, `total-requests-organizations`, `total-requests-users`, `total-organizations-requests`, `total-organizations-stats`, `total-domain-requests`, `total-domain-stats`, `total-domains`, `total-domains-collections`, `total-domains-organizations`, `total-domains-users`

```bash
dnsfcli traffic-reports total-requests --start_date 2026-06-01 --end_date 2026-06-14 --organization_id 100
```

### Threat Totals

`total-threats`, `total-threats-agents`, `total-threats-collections`, `total-threats-organizations`, `total-threats-users`

```bash
dnsfcli traffic-reports total-threats --start_date 2026-06-01 --end_date 2026-06-14 --organization_id 100
```

### Category Totals

`total-categories`, `total-categories-agents`, `total-categories-collections`, `total-categories-organizations`, `total-categories-users`, `total-category-stats`

```bash
dnsfcli traffic-reports total-categories --start_date 2026-06-01 --end_date 2026-06-14 --organization_id 100
```

### Deployment & Client Stats

`total-deployments`, `total-roaming-clients`, `total-client-stats` (real-time), `total-collections`, `total-collections-agents`, `total-collections-organizations`, `total-collections-users`

```bash
dnsfcli traffic-reports total-deployments --start_date 2026-06-01 --end_date 2026-06-14 --organization_id 100

# Real-time (uses from/to, not start_date/end_date)
dnsfcli traffic-reports total-client-stats --from 2026-06-15T10:00:00Z --to 2026-06-15T10:20:00Z --organization_id 100
```

### Application Statistics

`total-applications-stats`, `total-applications-agents-stats`, `total-applications-collections-stats`, `total-applications-networks-stats`, `total-applications-organizations-stats`, `total-applications-users-stats`

```bash
dnsfcli traffic-reports total-applications-stats --start_date 2026-06-01 --end_date 2026-06-14 --organization_id 100
```

---

## Users

Manage DNSFilter user accounts.

### list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number |
| per_page | integer | No | Items per page |

```bash
dnsfcli users list
```

### list-all

```bash
dnsfcli users list-all
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | User ID |

```bash
dnsfcli users show --id 42
```

### change-password

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| new_password | string | Yes | New password |

> ⚠️ **Warning:** This changes the password for the authenticated API user, not an arbitrary user by ID.

```bash
dnsfcli users change-password --new_password 'NewSecureP@ss!'
```

---

## User Agents

Manage roaming DNS filter agents (clients) installed on end-user devices.

> ⚠️ **Warning:** User agent `--id` values are **UUID strings** (e.g. `f821627e-8571-4eee-92df-f194a199a32b`), not integers.

### list

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number |
| per_page | integer | No | Items per page |
| organization_ids | array | No | Filter by org IDs |
| network_ids | array | No | Filter by network IDs |
| policy_id | integer | No | Filter by policy ID |
| search | string | No | Search by hostname |
| status | string | No | Filter by status |
| tags | string | No | Filter by tags |

```bash
dnsfcli user-agents list --organization_ids '[100]' --status active
```

### list-all / show / counts / tags

```bash
dnsfcli user-agents list-all
dnsfcli user-agents show --id f821627e-8571-4eee-92df-f194a199a32b
dnsfcli user-agents counts
dnsfcli user-agents tags
```

### csv

Exports a CSV of agents synchronously.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |

```bash
dnsfcli user-agents csv --organization_id 100
```

> 💡 **Tip:** For large exports or more filtering options, use the asynchronous `user-agent-csv-exports create` workflow instead.

### update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string (UUID) | Yes | Agent UUID |
| friendly_name | string | No | Display name |
| network_id | integer | No | Network ID |
| policy_id | integer | No | Policy ID |
| scheduled_policy_id | integer | No | Scheduled policy ID |
| block_page_id | integer | No | Block page ID |
| tags | array | No | Array of tags |

```bash
dnsfcli user-agents update --id f821627e-8571-4eee-92df-f194a199a32b --friendly_name "Alice MacBook" --policy_id 10
```

### delete

> ⚠️ **Warning:** Requires confirmation. Use `--yes` to skip.

```bash
dnsfcli user-agents delete --id f821627e-8571-4eee-92df-f194a199a32b --yes
```

### uninstall-pin

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | Yes | Organization ID |

```bash
dnsfcli user-agents uninstall-pin --organization_id 100
```

### dequeue-uninstall

Removes an agent from the pending uninstall queue.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | Yes | Agent ID |

```bash
dnsfcli user-agents dequeue-uninstall --id f821627e-8571-4eee-92df-f194a199a32b
```

---

## User Agent Bulk Deletes

Create and inspect asynchronous jobs that delete large sets of agents at once.

> 💡 **Tip:** Run `counts` before `create` to preview how many agents would be deleted.

### counts

```bash
dnsfcli user-agent-bulk-deletes counts
```

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | No | Scope the delete to a specific organization |
| ids | array | No | Array of agent UUIDs to explicitly target |
| exclude_ids | array | No | Array of agent UUIDs to exclude |

> ⚠️ **Warning:** This is a destructive POST operation. Requires confirmation. Use `--yes` to skip. Omitting both `ids` and `exclude_ids` with a broad `organization_id` may delete all agents in the org.

```bash
dnsfcli user-agent-bulk-deletes create --ids '["uuid1","uuid2"]' --organization_id 100
```

### show

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Bulk delete job ID |

```bash
dnsfcli user-agent-bulk-deletes show --id 42
```

---

## User Agent Bulk Updates

Create and inspect asynchronous jobs that update large sets of agents at once.

> 💡 **Tip:** Run `counts` first to preview scope. Use `has-mixed` to check whether selected agents have mixed values for a field before updating.

The request body has two logical sections that `dnsfcli` handles automatically:

- **Selection criteria** (`organization_id`, `ids`, `exclude_ids`, `network_id`) — sent at the root level
- **Changeset** (`policy_id`, `friendly_name`, `tags`, etc.) — automatically wrapped under `changeset`

### counts / has-mixed

```bash
dnsfcli user-agent-bulk-updates counts
dnsfcli user-agent-bulk-updates has-mixed --ids '["uuid1","uuid2"]'
```

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | integer | No | Scope to organization *(selection)* |
| ids | array | No | Agent UUIDs to target *(selection)* |
| exclude_ids | array | No | Agent UUIDs to exclude *(selection)* |
| network_id | array | No | Filter by network IDs *(selection)* |
| policy_id | integer | No | Policy to assign *(changeset)* |
| scheduled_policy_id | integer | No | Scheduled policy to assign *(changeset)* |
| block_page_id | integer | No | Block page to assign *(changeset)* |
| friendly_name | string | No | Display name to set *(changeset)* |
| tags | array | No | Tags to apply *(changeset)* |
| release_channels | array | No | Release channels to assign *(changeset)* |
| device_setting_attributes | object | No | Device settings JSON *(changeset)* |
| filtering_client_setting_attributes | object | No | Filtering client settings JSON *(changeset)* |
| vpn_settings_user_agent | object | No | VPN settings JSON *(changeset)* |

```bash
dnsfcli user-agent-bulk-updates create --organization_id 100 --network_id '[55]' --policy_id 10
```

### show

```bash
dnsfcli user-agent-bulk-updates show --id 77
```

---

## User Agent Cleanups

Create and manage jobs that remove inactive agents based on inactivity thresholds.

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_ids | array | Yes | Array of organization IDs |
| inactive_for | integer | Yes | Inactivity threshold in days |

```bash
dnsfcli user-agent-cleanups create --organization_ids '[100]' --inactive_for 90
```

### show

```bash
dnsfcli user-agent-cleanups show --id 5
```

### update

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Cleanup job ID |
| start | boolean | No | Set to `true` to start the job |
| inactive_for | integer | No | Updated inactivity threshold in days |

```bash
dnsfcli user-agent-cleanups update --id 5 --start true
```

---

## User Agent CSV Exports

Create and poll asynchronous CSV export jobs for agent data.

> 💡 **Tip:** CSV exports are asynchronous. Call `create` to start the export, capture the returned job ID, then poll `show` until the export is ready.

### create

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_ids | array | No | Array of organization IDs |
| msp_id | integer | No | MSP ID |
| ids | array | No | Specific agent IDs |
| network_ids | array | No | Filter by network IDs |
| tags | array | No | Filter by tags |
| status | string | No | Agent status filter |
| state | string | No | Agent state filter |
| traffic_received_last_15_mins | boolean | No | Only agents active in last 15 minutes |

```bash
dnsfcli user-agent-csv-exports create --organization_ids '[100]'
```

### show

Poll for completion.

```bash
dnsfcli user-agent-csv-exports show --id 33
```

---

## User Agent Releases

### list / relay

```bash
dnsfcli user-agent-releases list
dnsfcli user-agent-releases relay
```

---

## V2 Agent Local Users

V2 endpoints for counting and exporting agent local user data.

> 💡 **Tip:** `csv-export` is asynchronous — poll `csv-export-show` with the returned ID until complete.

### counts

```bash
dnsfcli v2-agent-local-users counts
```

### csv-export

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_ids | array | No | Array of organization IDs |
| name | string | No | Name filter |
| search | string | No | Search term |
| user_policy_override | boolean | No | Filter by policy override status |

```bash
dnsfcli v2-agent-local-users csv-export --organization_ids '[100]'
```

### csv-export-show

```bash
dnsfcli v2-agent-local-users csv-export-show --id 12
```

---

## V2 Current User

### suppress-license-warning

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_uuid | string | No | UUID of the organization |

```bash
dnsfcli v2-current-user suppress-license-warning --organization_uuid "abc-123"
```

### ui-settings / ui-settings-update

```bash
dnsfcli v2-current-user ui-settings

dnsfcli v2-current-user ui-settings-update --theme_mode dark --disable_license_warnings true
```

---

## V2 Dictionary

Static lookup tables used by other endpoints.

### cyber-sight-activity-types

Returns all valid Cyber Sight activity type values.

```bash
dnsfcli v2-dictionary cyber-sight-activity-types
```

### vpn-settings-state-types

Returns all valid VPN settings state type values. Use these IDs with `vpn_settings_state_type_id` in `organizations bulk-update`.

```bash
dnsfcli v2-dictionary vpn-settings-state-types
```

---

## V2 Networks

Asynchronous CSV export for network data.

> 💡 **Tip:** Call `csv-export`, then poll `csv-export-show` until the export is ready.

### csv-export

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_ids | array | No | Array of organization IDs |
| msp_id | integer | No | MSP ID |
| ids | array | No | Specific network IDs |

```bash
dnsfcli v2-networks csv-export --organization_ids '[100]'
```

### csv-export-show

```bash
dnsfcli v2-networks csv-export-show --id 8
```

---

## V2 User Agents

### update-settings

> ⚠️ **Warning:** `--id` must be a **UUID string**, not an integer.

All parameters are sent under the `user_agent` key automatically.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string (UUID) | Yes | Agent UUID |
| device_setting_attributes | object | No | Device settings JSON |
| filtering_client_setting_attributes | object | No | Filtering client settings JSON |

```bash
dnsfcli v2-user-agents update-settings --id f821627e-8571-4eee-92df-f194a199a32b \
  --device_setting_attributes '{"tamper_protection": true}'
```
