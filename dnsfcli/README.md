# dnsfcli

Command-line interface for the [DNSFilter](https://www.dnsfilter.com) API. Manage networks, policies, users, agents, and every other API resource directly from your terminal — with rich table output, CSV bulk import/export, filtering, sorting, watch mode, and scripting-friendly JSON output.

## Requirements

Python 3.11 or later.

## Installation

Install directly from the repository:

```sh
pip install "git+https://github.com/DNSFilter/support.git#subdirectory=dnsfcli"
```

Re-run the same command to upgrade. Or work from a local clone:

```sh
git clone https://github.com/DNSFilter/support
cd support/dnsfcli
pip install -e .
```

## Authentication

Credentials are stored in the OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service) and reused automatically on every call.

```sh
dnsfcli auth setup          # interactive prompt for API key + org ID
dnsfcli auth verify         # confirm credentials work
dnsfcli auth show           # display stored credentials (key masked)
```

Multiple credential profiles are supported:

```sh
dnsfcli auth setup --profile prod
dnsfcli auth setup --profile staging
dnsfcli auth use prod        # set the active profile
dnsfcli --profile staging networks list
```

## Basic Usage

```sh
# List all networks
dnsfcli networks list

# Get a specific resource
dnsfcli networks show --id 736401

# Create from flags
dnsfcli networks create --name "HQ" --organization-id 802315 --policy-ids '["285109"]'

# Update
dnsfcli networks update --id 736401 --name "HQ Updated"

# Delete
dnsfcli networks delete --id 736401
```

## Output & Filtering

```sh
# Choose columns
dnsfcli networks list --columns id,name,status

# Filter rows
dnsfcli networks list --filter "status=active"
dnsfcli networks list --filter "status=active" --filter "name~HQ"   # AND
dnsfcli networks list --filter "status=active" --filter-mode or      # OR

# Sort, limit, paginate
dnsfcli networks list --sort -created_at --limit 20
dnsfcli networks list --all                     # fetch every page

# JSON / JSONL output
dnsfcli networks list --json
dnsfcli networks list --jsonl

# Custom format template
dnsfcli networks list --format "{name} ({id}) — {status}"

# Extract one field per line
dnsfcli networks list --pick id

# Aggregates
dnsfcli networks list --count
dnsfcli metrics list --sum blocked_requests --all
```

## CSV Bulk Operations

```sh
# Generate a blank template
dnsfcli networks create --template > networks.csv

# Create from CSV (one API call per row)
dnsfcli networks create --from-csv networks.csv

# Save responses to CSV
dnsfcli networks list --to-csv out.csv

# Export as Markdown table
dnsfcli networks list --to-markdown networks.md

# Resume an interrupted batch
dnsfcli networks create --from-csv networks.csv --skip-rows 50

# Limit rows processed
dnsfcli networks create --from-csv networks.csv --max-rows 10

# Write a JSON report of the run
dnsfcli networks create --from-csv networks.csv --batch-report run.json
```

## Data Transformation

```sh
# Map field values
dnsfcli users list --map "email=lower"
dnsfcli users list --map "name=upper"

# Compute derived fields
dnsfcli metrics list --transform "ratio=blocked/total" --all

# Inject static fields
dnsfcli networks list --add-field source=export

# Join related resources
dnsfcli networks list --join "policies:policy_id=id" --columns name,_policy.name
```

## Watch & Monitor

```sh
# Poll every 30 seconds
dnsfcli networks list --watch 30

# Stop when a condition is met
dnsfcli networks list --watch 10 --watch-until "status=active"

# Ring the terminal bell and print a banner when matching
dnsfcli networks list --watch 60 --alert "status=error"
```

## Scripting & CI

```sh
# Exit 1 when result list is empty
dnsfcli networks list --filter "status=error" --fail-on-empty

# Exit 1 when any row matches a condition
dnsfcli networks list --fail-on-pattern "status=error"

# Run a shell command for each result row
dnsfcli networks list --exec "curl -X POST https://hook.example.com/{id}"

# Pipe JSON to another tool
dnsfcli networks list --json | jq '.[] | .id'
```

## Multi-Org

```sh
# Run the same command across every organization
dnsfcli networks list --each-org

# Supply org list from a CSV file instead of the API
dnsfcli networks list --each-org --org-csv orgs.csv

# Filter and cap the org list
dnsfcli networks list --each-org --org-filter "Acme" --max-orgs 5
```

## Configuration

All settings are optional. The config file is at `~/.config/dnsfcli/config.toml`.

```sh
dnsfcli config init          # scaffold a starter config with documentation
dnsfcli config show          # print the current resolved config
dnsfcli config set timeout 60
dnsfcli config set batch.concurrency 5
```

Named presets stored in config save you from repeating long flag chains:

```sh
# Column preset
dnsfcli config set preset.compact "id,name,status"
dnsfcli networks list --preset compact

# Format preset
dnsfcli config set format.oneline "{id}  {name}  {status}"
dnsfcli networks list --format-preset oneline

# Full command bundle (columns + filter + sort + format)
dnsfcli config set bundle.active.filter "status=active"
dnsfcli config set bundle.active.sort "-created_at"
dnsfcli config set bundle.active.columns "id,name,status,created_at"
dnsfcli networks list --bundle active
```

## Discovery

```sh
# List all endpoint groups
dnsfcli endpoints

# List all functions for an endpoint
dnsfcli endpoints policies

# Show the CSV template for any write operation
dnsfcli policies create --template

# Inspect available fields in a response
dnsfcli networks list --fields
dnsfcli networks list --output-schema
```

## Aliases

Save frequently-used commands as short names:

```sh
dnsfcli networks list --filter "status=active" --sort name --save-as active-nets
dnsfcli active-nets
```

## Environment Variables

| Variable | Description |
|---|---|
| `DNSF_API_KEY` | API key (overrides keychain) |
| `DNSF_ORG_ID` | Organization ID (overrides keychain) |
| `DNSF_BASE_URL` | API base URL (default: `https://api.dnsfilter.com`) |
| `DNSF_PROFILE` | Active credential profile |
| `NO_COLOR` | Disable ANSI color output |

## Example Scripts

The [`examples/`](examples/) directory contains 14 ready-to-adapt shell scripts for common workflows: bulk CSV onboarding, MSP fleet audits, scheduled threat reports, agent coverage-gap analysis, blocklist synchronization from a feed, break-glass troubleshooting, API-key rotation, and more.

## Full Reference

See [`docs/dnsfcli-full-reference.md`](docs/dnsfcli-full-reference.md) for the complete command reference covering all 36 endpoint groups with examples, parameter descriptions, and CSV templates.
