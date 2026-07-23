"""
Programmatic full-reference guide generator for dnsfcli.

Reads the endpoint registry directly and generates one prompt block per
operation, two endpoint groups per page. No content can be dropped because
nothing goes through an LLM — it all comes straight from the registry.
"""

import io
import pathlib
import sys
import html as htmllib

# ── paths ────────────────────────────────────────────────────────────────────

# Brand assets (fonts, logos) ship with DNSFilter's internal build-guide
# skill and are NOT part of this repository. Point DNSFCLI_BRAND_ASSETS at
# that skill's assets/ directory to rebuild the branded documents.
import os as _os
if "DNSFCLI_BRAND_ASSETS" not in _os.environ:
    sys.exit("Set DNSFCLI_BRAND_ASSETS to the build-guide skill assets directory.")
ASSETS = pathlib.Path(_os.environ["DNSFCLI_BRAND_ASSETS"])
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

OUT_DIR      = pathlib.Path(__file__).parent.parent / "docs"
OUT_BASENAME = "dnsfcli-full-reference"
FORMATS      = ["md", "docx", "confluence"]
COVER        = "feature"

OUT_DIR.mkdir(exist_ok=True)

# ── endpoint registry ────────────────────────────────────────────────────────

from dnsfcli.endpoints import REGISTRY

# ── example values ───────────────────────────────────────────────────────────

# Realistic placeholder values used when generating example commands
EXAMPLE_ORG_ID      = "802315"
EXAMPLE_NET_ID      = "736401"
EXAMPLE_POLICY_ID   = "285109"
EXAMPLE_USER_ID     = "42618"
EXAMPLE_AGENT_ID    = "9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5"
EXAMPLE_BLOCK_PAGE  = "5147"
EXAMPLE_CATEGORY_ID = "2"          # Adult Content
EXAMPLE_SCHED_POLICY= "71203"
EXAMPLE_API_KEY_ID  = "20981"
EXAMPLE_DOMAIN      = "malware.example.com"
EXAMPLE_DATE_FROM   = "2025-01-01"
EXAMPLE_DATE_TO     = "2025-01-31"
EXAMPLE_EMAIL       = "admin@company.com"
EXAMPLE_IP          = "203.0.113.5"
EXAMPLE_MAC         = "AA:BB:CC:DD:EE:FF"
EXAMPLE_APP_NAME    = "TikTok"

# Per-function value overrides  {(endpoint, function): {param: value}}
PARAM_OVERRIDES = {
    # networks
    ("networks", "create"):           {"name": "HQ Network", "organization_id": EXAMPLE_ORG_ID, "policy_ids": '["285109"]', "physical_address": "123 Main St, Denver CO"},
    ("networks", "update"):           {"name": "HQ Network Updated", "organization_id": EXAMPLE_ORG_ID},
    ("networks", "subnets-create"):   {"name": "Sales Floor", "from": "10.0.1.0", "to": "10.0.1.255"},
    ("networks", "subnets-update"):   {"name": "Sales Floor Renamed", "from": "10.0.1.0", "to": "10.0.1.255"},
    ("networks", "lan-ip-update"):    {"name": "Reception Desk"},
    ("networks", "bulk-update"):      {"ids": "736401,736402", "policy_id": EXAMPLE_POLICY_ID},
    ("networks", "lookup"):           {"ip": EXAMPLE_IP},
    # policies
    ("policies", "create"):           {"name": "Guest WiFi", "organization_id": EXAMPLE_ORG_ID, "allow_unknown_domains": "true", "google_safesearch": "true", "youtube_restricted": "true", "youtube_restricted_level": "strict"},
    ("policies", "update"):           {"name": "Guest WiFi Updated", "organization_id": EXAMPLE_ORG_ID, "interstitial": "true"},
    ("policies", "add-blacklist-domain"):   {"domain": EXAMPLE_DOMAIN, "note": "Flagged by threat intel"},
    ("policies", "add-whitelist-domain"):   {"domain": "internal.corp.com"},
    ("policies", "remove-blacklist-domain"):{"domain": EXAMPLE_DOMAIN},
    ("policies", "remove-whitelist-domain"):{"domain": "internal.corp.com"},
    ("policies", "add-blacklist-category"):  {"category_id": EXAMPLE_CATEGORY_ID},
    ("policies", "remove-blacklist-category"):{"category_id": EXAMPLE_CATEGORY_ID},
    ("policies", "add-allowed-application"):  {"name": EXAMPLE_APP_NAME},
    ("policies", "add-blocked-application"):  {"name": EXAMPLE_APP_NAME},
    ("policies", "remove-allowed-application"):{"name": EXAMPLE_APP_NAME},
    ("policies", "remove-blocked-application"):{"name": EXAMPLE_APP_NAME},
    ("policies", "bulk-add-allowlist"):  {"policy_ids": '["285109","331207"]', "domains": '["safe.com","trusted.org"]'},
    ("policies", "bulk-add-blocklist"):  {"policy_ids": '["285109","331207"]', "domains": '["evil.com","malware.net"]'},
    ("policies", "bulk-remove-allowlist"):{"policy_ids": '["285109"]', "domains": '["safe.com"]'},
    ("policies", "bulk-remove-blocklist"):{"policy_ids": '["285109"]', "domains": '["evil.com"]'},
    ("policies", "set-permissive-mode"): {"enabled": "true"},
    # ip-addresses
    ("ip-addresses", "create"):  {"address": EXAMPLE_IP,  "organization_id": EXAMPLE_ORG_ID, "network_id": EXAMPLE_NET_ID},
    ("ip-addresses", "update"):  {"address": EXAMPLE_IP},
    ("ip-addresses", "verify"):  {"ip_address": EXAMPLE_IP},
    # mac-addresses
    ("mac-addresses", "create"): {"organization_id": EXAMPLE_ORG_ID, "address": EXAMPLE_MAC, "filter_value": "Reception Printer", "policy_id": EXAMPLE_POLICY_ID},
    ("mac-addresses", "update"): {"address": EXAMPLE_MAC, "filter_value": "Updated Label"},
    # organizations
    ("organizations", "create"):        {"name": "New Client Corp", "billing_contact_email": EXAMPLE_EMAIL, "sku": "professional"},
    ("organizations", "update"):        {"name": "New Client Corp Updated"},
    ("organizations", "bulk-update"):   {"organization_ids": '["802315","802316"]', "gdpr": "true"},
    ("organizations", "users-create"):  {"email": EXAMPLE_EMAIL, "first_name": "Jane", "last_name": "Smith", "role": "administrator"},
    ("organizations", "users-update"):  {"role": "read_only"},
    # billing
    ("billing", "create"):              {"organization_id": EXAMPLE_ORG_ID, "payment_token": "tok_visa_4242"},
    ("billing", "update-address"):      {"first_name": "Jane", "last_name": "Smith", "line1": "123 Main St", "city": "Denver", "state": "Colorado", "zip": "80202", "country": "US"},
    # block-pages
    ("block-pages", "create"):  {"name": "Corporate Block Page", "block_org_name": "Acme Corp", "block_email_addr": EXAMPLE_EMAIL},
    ("block-pages", "update"):  {"name": "Corporate Block Page Updated"},
    # enterprise-connections
    ("enterprise-connections", "create"): {"client_id": "my-client-id", "client_secret": "my-secret", "discovery_url": "https://idp.company.com/.well-known/openid-configuration", "strategy": "oidc", "display_name": "Company SSO"},
    ("enterprise-connections", "update"): {"display_name": "Company SSO Updated"},
    # collections
    ("collections", "users-add"):   {"id": EXAMPLE_USER_ID},
    # current-user
    ("current-user", "update"):     {"first_name": "Jane", "last_name": "Smith"},
    # api-keys
    ("api-keys", "create"):         {"name": "CI Pipeline Key", "expiry": "2027-05-31"},
    # user-agents
    ("user-agents", "update"):      {"friendly_name": "Finance-Laptop", "policy_id": EXAMPLE_POLICY_ID, "tags": '["managed","finance"]'},
    ("user-agent-bulk-updates", "create"): {"ids": f'["{EXAMPLE_AGENT_ID}"]', "policy_id": EXAMPLE_POLICY_ID},
    ("user-agent-bulk-updates", "has-mixed"): {"ids": f'["{EXAMPLE_AGENT_ID}"]'},
    ("user-agent-bulk-deletes", "create"): {"ids": f'["{EXAMPLE_AGENT_ID}"]'},
    ("user-agent-cleanups", "create"):  {"organization_ids": f'["{EXAMPLE_ORG_ID}"]', "inactive_for": "30"},
    ("user-agent-cleanups", "update"):  {"start": "true", "inactive_for": "30"},
    ("user-agent-csv-exports", "create"): {"organization_ids": f'["{EXAMPLE_ORG_ID}"]'},
    # v2
    ("v2-agent-local-users", "csv-export"):  {"organization_ids": f'["{EXAMPLE_ORG_ID}"]'},
    ("v2-current-user", "ui-settings-update"): {"theme_mode": "dark"},
    ("v2-cyber-sight", "csv-export"): {"organization_ids": f'["{EXAMPLE_ORG_ID}"]', "threats_only": "true", "start_at": "2025-01-01T00:00:00Z", "end_at": "2025-01-31T23:59:59Z"},
    ("v2-networks", "csv-export"):  {"organization_ids": f'["{EXAMPLE_ORG_ID}"]'},
    ("v2-user-agents", "update-settings"): {"policy_id": EXAMPLE_POLICY_ID},
    # notes
    ("notes", "update"):  {"type": "block", "note": "Known malware distribution point"},
    # scheduled-reports
    ("scheduled-reports", "create"): {"organization_id": EXAMPLE_ORG_ID, "frequency": "weekly", "day_of_week": "1", "include_threat_summary": "true", "send_to_dashboard_users": "true"},
    ("scheduled-reports", "update"): {"frequency": "monthly"},
    ("scheduled-reports", "preview-create"): {"organization_id": EXAMPLE_ORG_ID, "include_threat_summary": "true"},
    # scheduled-policies
    ("scheduled-policies", "create"): {"name": "School Hours", "organization_id": EXAMPLE_ORG_ID, "policy_ids": f'["{EXAMPLE_POLICY_ID}"]', "timezone": "America/Denver"},
    ("scheduled-policies", "update"): {"name": "School Hours Updated", "timezone": "America/Chicago"},
    # distributors
    ("distributors", "msps-create"):   {"name": "ACME MSP", "email": EXAMPLE_EMAIL},
    ("distributors", "msps-update"):   {"name": "ACME MSP Updated"},
    ("distributors", "orgs-create"):   {"name": "Client Org", "sku": "professional"},
    ("distributors", "orgs-update"):   {"name": "Client Org Updated"},
    ("distributors", "orgs-add-sku"):  {"sku": "roaming-clients"},
    ("distributors", "orgs-remove-sku"): {"sku": "roaming-clients"},
    ("distributors", "update"):        {"name": "My Distributor Updated"},
    ("distributors", "users-create"):  {"email": EXAMPLE_EMAIL, "first_name": "Jane", "last_name": "Smith"},
    ("distributors", "users-add-membership"):    {"organization_id": EXAMPLE_ORG_ID, "role": "administrator"},
    ("distributors", "users-remove-membership"): {"organization_id": EXAMPLE_ORG_ID},
    ("distributors", "users-update-membership"): {"organization_id": EXAMPLE_ORG_ID, "role": "read_only"},
    # domains
    ("domains", "bulk-lookup"):    {"domains": "google.com,facebook.com,malware.example"},
    ("domains", "suggest-threat"): {"domain": EXAMPLE_DOMAIN, "reason": "Flagged in phishing campaign"},
    ("domains", "user-lookup"):    {"domain": "google.com"},
    # users
    ("users", "change-password"):  {"new_password": "NewSecurePass123!"},
    # metrics
    ("metrics", "org-usage"):          {"id": EXAMPLE_ORG_ID},
    ("metrics", "org-usage-detailed"): {"id": EXAMPLE_ORG_ID},
    # trials
    ("trials", "create"): {"organization_id": EXAMPLE_ORG_ID, "sku": "professional"},
    # agent-local-users
    ("agent-local-users", "bulk-delete"): {"ids": '["1001","1002","1003"]'},
    ("agent-local-users", "update"):      {"friendly_name": "Jane Smith Laptop", "policy_id": EXAMPLE_POLICY_ID},
}

# Default param values by type
TYPE_DEFAULTS = {
    "string":  "example-value",
    "integer": "1",
    "boolean": "true",
    "array":   '["item1","item2"]',
    "object":  '{"key":"value"}',
}

# Functions that always get a standard list of extra flags
TRAFFIC_COMMON_FLAGS = f"--start_date {EXAMPLE_DATE_FROM} --end_date {EXAMPLE_DATE_TO}"


def build_example_command(endpoint: str, function: str, op) -> str:
    """Build a realistic runnable example command for one operation."""
    parts = [f"python dnsfcli.py {endpoint} {function}"]

    overrides = PARAM_OVERRIDES.get((endpoint, function), {})

    # Path params
    for p in op.params:
        if p.kind != "path":
            continue
        val = overrides.get(p.name)
        if val is None:
            if p.name == "id":
                # Choose a sensible default by endpoint
                if "organization" in endpoint or "org" in function:
                    val = EXAMPLE_ORG_ID
                elif "network" in endpoint:
                    val = EXAMPLE_NET_ID
                elif "policy" in endpoint:
                    val = EXAMPLE_POLICY_ID
                elif "user_agent" in endpoint or "agent" in endpoint:
                    val = EXAMPLE_AGENT_ID
                elif "api" in endpoint:
                    val = EXAMPLE_API_KEY_ID
                else:
                    val = "12345"
            elif p.name == "organization_id":
                val = EXAMPLE_ORG_ID
            elif p.name == "collection_id":
                val = "7788"
            elif p.name == "lan_ip_id":
                val = "9901"
            elif p.name == "subnet_id":
                val = "4455"
            elif p.name == "resource":
                val = "networks"
            elif p.name == "domain":
                val = EXAMPLE_DOMAIN
            else:
                val = TYPE_DEFAULTS.get(p.type_hint, "value")
        parts.append(f"--{p.name} {val}")

    # Traffic reports always get date range
    if endpoint == "traffic-reports":
        parts.append(f"--start_date {EXAMPLE_DATE_FROM}")
        parts.append(f"--end_date {EXAMPLE_DATE_TO}")

    # List functions: add pagination
    if function == "list":
        parts.append("--page 1 --per_page 25")

    # Body/query params
    if op.method in ("POST", "PATCH", "PUT"):
        for p in op.params:
            if p.kind not in ("body",):
                continue
            if p.name in overrides:
                val = overrides[p.name]
            elif p.required:
                val = TYPE_DEFAULTS.get(p.type_hint, "value")
            else:
                continue  # skip optional params unless overridden
            # Quote values that contain spaces or special chars
            if " " in str(val) or ":" in str(val) or "=" in str(val):
                val = f'"{val}"'
            parts.append(f"--{p.name} {val}")
    elif op.method == "GET":
        for p in op.params:
            if p.kind != "query":
                continue
            if p.name in ("page", "per_page") and function == "list":
                continue  # already added above
            if p.name in ("start_date", "end_date") and endpoint == "traffic-reports":
                continue  # already added
            if p.name in overrides:
                val = overrides[p.name]
                parts.append(f"--{p.name} {val}")
            # skip optional query params

    # Wrap long commands across multiple lines
    cmd = " ".join(parts)
    if len(cmd) > 80:
        # Break at each --flag
        base = parts[0]
        flags = parts[1:]
        cmd = base + " \\\n  " + " \\\n  ".join(flags)
    return cmd


# ── human-readable function descriptions ─────────────────────────────────────

FUNC_DESCRIPTIONS = {
    "list":          "Retrieve a paginated list of resources.",
    "list-all":      "Retrieve all resources without pagination.",
    "show":          "Retrieve a single resource by ID.",
    "create":        "Create a new resource.",
    "update":        "Update an existing resource by ID.",
    "delete":        "Permanently delete a resource by ID.",
    "list-all":      "Retrieve all resources without pagination limits.",
    "counts":        "Return counts of resources matching optional filters.",
    "geo":           "Return geographic information for resources.",
    "lookup":        "Find a resource matching a specific value.",
    "msp":           "List resources visible to the MSP account.",
    "msp-all":       "List all resources visible to the MSP account.",
    "subnets":       "List all subnets across all networks.",
    "bulk-create":   "Create multiple resources in a single async job.",
    "bulk-create-show": "Check the status of a bulk-create job.",
    "bulk-update":   "Update multiple resources in a single async job.",
    "bulk-update-show": "Check the status of a bulk-update job.",
    "bulk-destroy":  "Delete multiple resources in a single async job.",
    "bulk-destroy-show": "Check the status of a bulk-destroy job.",
    "lan-ips":       "List LAN IP addresses registered to a network.",
    "lan-ip-show":   "Retrieve a single LAN IP address entry.",
    "lan-ip-update": "Update the name of a LAN IP address entry.",
    "secret-key-create": "Generate a new network secret key.",
    "secret-key-update": "Rotate the network secret key.",
    "secret-key-delete": "Delete the network secret key.",
    "subnets-list":  "List subnets within a specific network.",
    "subnets-create":"Add a subnet IP range to a network.",
    "subnets-show":  "Retrieve a specific subnet.",
    "subnets-update":"Update an existing subnet's name or IP range.",
    "subnets-delete":"Remove a subnet from a network.",
    "current":       "Retrieve the current billing period's invoice.",
    "myip":          "Return the public IP address of the calling client.",
    "verify":        "Verify whether an IP address is registered.",
    "get-address":   "Retrieve the billing address for an organization.",
    "update-address":"Update the billing address for an organization.",
    "qp-methods":    "Retrieve the list of supported QP method types.",
    "users-list":    "List users within a specific organization or collection.",
    "users-add":     "Add a user to an organization or collection.",
    "users-show":    "Retrieve a specific user within an organization or collection.",
    "users-update":  "Update a user's role or details within an organization.",
    "users-delete":  "Remove a user from an organization or collection.",
    "users-remove":  "Remove a user from a collection.",
    "users-resend-invite":   "Re-send the email invitation to an org user.",
    "users-create":          "Add a new user to an organization.",
    "users-add-membership":  "Assign an org membership to a distributor user.",
    "users-remove-membership":"Remove an org membership from a distributor user.",
    "users-update-membership":"Update the role of a distributor user's org membership.",
    "users-reset-password-url":"Generate a password-reset URL for a user.",
    "users-send-reset-password":"Send a password-reset email to a user.",
    "bulk-lookup":   "Classify multiple domains in a single request.",
    "suggest-threat":"Submit a domain for threat-intel review.",
    "user-lookup":   "Look up a domain for an authenticated user session.",
    "health":        "Check the distributor API health status.",
    "msps-list":     "List MSPs managed by the distributor account.",
    "msps-create":   "Create a new MSP under the distributor account.",
    "msps-show":     "Retrieve a specific distributor MSP.",
    "msps-update":   "Update a distributor MSP's details.",
    "msps-cancel":   "Cancel a distributor MSP subscription.",
    "msps-reactivate":"Reactivate a cancelled distributor MSP.",
    "orgs-list":     "List organizations managed by the distributor.",
    "orgs-create":   "Create a new organization under the distributor.",
    "orgs-show":     "Retrieve a specific distributor organization.",
    "orgs-update":   "Update a distributor organization.",
    "orgs-cancel":   "Cancel a distributor organization subscription.",
    "orgs-reactivate":"Reactivate a cancelled distributor organization.",
    "orgs-add-sku":  "Add a product SKU to a distributor organization.",
    "orgs-remove-sku":"Remove a product SKU from a distributor organization.",
    "reports-covered-users": "Get a covered-users summary report by organization.",
    "reports-usage-by-org":  "Get a usage report broken down by organization.",
    "reports-usage-by-sku":  "Get a usage report broken down by SKU.",
    "skus-available":"List available SKUs for the distributor account.",
    "redirect-link": "Get the PSA integration redirect link.",
    "settings":      "Retrieve organization-level settings.",
    "promote-to-msp":"Promote the current organization to an MSP account.",
    "bulk-update":   "Update multiple resources in a single operation.",
    "cancel":        "Cancel an organization's subscription.",
    "application":   "List policies with application filtering enabled.",
    "application-update": "Update application filtering settings across policies.",
    "bulk-add-allowlist":     "Add domains to the allowlist on multiple policies at once.",
    "bulk-add-blocklist":     "Add domains to the blocklist on multiple policies at once.",
    "bulk-remove-allowlist":  "Remove domains from the allowlist on multiple policies.",
    "bulk-remove-blocklist":  "Remove domains from the blocklist on multiple policies.",
    "add-allowed-application":  "Allow a specific application on a policy.",
    "add-blacklist-category":   "Block all domains in a category on a policy.",
    "add-blacklist-domain":     "Block a specific domain on a policy.",
    "add-blocked-application":  "Block a specific application on a policy.",
    "add-whitelist-domain":     "Allow a specific domain on a policy.",
    "permissive-mode":          "Check whether permissive mode is enabled for a policy.",
    "set-permissive-mode":      "Enable or disable permissive mode on a policy.",
    "remove-allowed-application": "Remove an application from the allowlist on a policy.",
    "remove-blacklist-category":  "Unblock a category on a policy.",
    "remove-blacklist-domain":    "Remove a domain from the blocklist on a policy.",
    "remove-blocked-application": "Remove an application from the blocklist on a policy.",
    "remove-whitelist-domain":    "Remove a domain from the allowlist on a policy.",
    "batch-update":  "Batch-update domain notes on a resource.",
    "batch-destroy": "Batch-delete domain notes on a resource.",
    "revoke":        "Revoke an API key immediately without deleting it.",
    "change-password":"Change the current user's password.",
    "preview-create":"Generate an immediate preview of a scheduled report.",
    "preview-show":  "Retrieve the result of a report preview job.",
    "relay":         "Retrieve the relay channel's latest agent release.",
    "suppress-license-warning":"Suppress the license warning for the current user.",
    "ui-settings":   "Retrieve the current user's UI settings.",
    "ui-settings-update": "Update the current user's UI settings.",
    "cyber-sight-activity-types":"List available Cyber Sight activity types.",
    "vpn-settings-state-types":"List available VPN settings state types.",
    "csv-export":    "Create an async CSV export job.",
    "csv-export-show":"Check the status of a CSV export job.",
    "update-settings":"Update settings for a specific roaming agent.",
    "has-mixed":     "Check whether the selected agents have mixed field values.",
    "dequeue-uninstall":"Dequeue a pending uninstall request for an agent.",
    "uninstall-pin": "Retrieve the uninstall PIN for roaming agents.",
    "tags":          "List all tags assigned to roaming agents.",
    "csv":           "Export all roaming agents to CSV format.",
}

def func_description(endpoint, function, op):
    desc = FUNC_DESCRIPTIONS.get(function)
    if desc:
        return desc
    return op.description + "."


# ── HTML builder ─────────────────────────────────────────────────────────────

def e(text: str) -> str:
    """HTML-escape a string."""
    return htmllib.escape(str(text))


def build_endpoint_section(endpoint: str, ep_data) -> str:
    buf = io.StringIO()
    h = buf.write

    h(f'<h2>{e(endpoint)}</h2>\n')
    h(f'<p>{e(ep_data.description)}.</p>\n\n')

    for function, op in sorted(ep_data.operations.items()):
        desc = func_description(endpoint, function, op)
        cmd  = build_example_command(endpoint, function, op)

        h(f'<h3>{e(function)}</h3>\n')
        h(f'<p>{e(desc)}</p>\n')
        h('<div class="prompt">\n')
        h(f'  <div class="prompt-label">SHELL / {e(endpoint.upper())} {e(function.upper())}</div>\n')
        h(f'  <div class="prompt-body">{e(cmd)}</div>\n')
        h('</div>\n\n')

    return buf.getvalue()


# ── page-pair ordering ────────────────────────────────────────────────────────

# Two endpoint groups per page, derived from the live registry so newly
# added or removed endpoints can never fall out of the document.
_ALL_ENDPOINTS = sorted(REGISTRY.keys())
PAGE_PAIRS = [
    (_ALL_ENDPOINTS[i], _ALL_ENDPOINTS[i + 1] if i + 1 < len(_ALL_ENDPOINTS) else None)
    for i in range(0, len(_ALL_ENDPOINTS), 2)
]

# ── assemble BODY ─────────────────────────────────────────────────────────────

def build_body() -> str:
    buf = io.StringIO()
    h = buf.write

    h('<section class="content">\n\n')

    # ── intro ──────────────────────────────────────────────────────────────
    h('<h2>Getting Started</h2>\n')
    h('<p>dnsfcli is a command-line tool for the full DNSFilter REST API. '
      'Install it once, store your credentials in the OS keychain, and manage '
      'every aspect of your DNSFilter account from the terminal — no browser required.</p>\n\n')

    h('<div class="step"><div class="step-num">1</div><div class="step-content">'
      '<div class="step-title">Install</div>'
      '<div class="step-body">Python 3.9 or later is required.</div>'
      '</div></div>\n')
    h('<div class="prompt"><div class="prompt-label">SHELL / INSTALL</div>'
      '<div class="prompt-body">pip install -e .\n'
      '# or run directly:\n'
      'python dnsfcli.py --help</div></div>\n\n')

    h('<div class="step"><div class="step-num">2</div><div class="step-content">'
      '<div class="step-title">Store credentials</div>'
      '<div class="step-body">Your API token and default organization ID are stored '
      'in the OS keychain (macOS Keychain / Windows Credential Manager / Linux Secret Service) '
      'and used automatically on every subsequent command.</div>'
      '</div></div>\n')
    h('<div class="prompt"><div class="prompt-label">SHELL / AUTH SETUP</div>'
      '<div class="prompt-body">'
      'python dnsfcli.py auth setup\n'
      'python dnsfcli.py auth setup --org-id 802315\n'
      'python dnsfcli.py auth verify\n'
      'python dnsfcli.py auth show</div></div>\n\n')

    h('<h2>Command Structure</h2>\n')
    h('<p>Every command follows the same three-part pattern.</p>\n')
    h('<div class="prompt"><div class="prompt-label">REFERENCE / COMMAND STRUCTURE</div>'
      '<div class="prompt-body">'
      'python dnsfcli.py  [endpoint]  [function]  [--param value ...]\n\n'
      '# Examples\n'
      'python dnsfcli.py policies list\n'
      'python dnsfcli.py policies show --id 285109\n'
      'python dnsfcli.py policies create --name "Guest WiFi" --organization_id 802315\n'
      'python dnsfcli.py policies update --id 285109 --name "Updated"\n'
      'python dnsfcli.py policies delete --id 285109</div></div>\n\n')

    h('<h2>Global Flags</h2>\n')
    h('<p>These flags work on any command and can appear anywhere in the argument list '
      '(before the endpoint, between endpoint and function, or after all other flags).</p>\n')
    from flags_reference import render_flag_table_html
    h(render_flag_table_html())
    h('\n')

    h('<h2>Discovery</h2>\n')
    h('<p>Explore every available endpoint and function without leaving the terminal.</p>\n')
    h('<div class="prompt"><div class="prompt-label">SHELL / DISCOVERY</div>'
      '<div class="prompt-body">'
      '# List all 36 endpoint groups\n'
      'python dnsfcli.py endpoints\n\n'
      '# List all functions for one endpoint\n'
      'python dnsfcli.py endpoints policies\n\n'
      '# Get a pre-filled CSV template for any write operation\n'
      'python dnsfcli.py policies create --template\n'
      'python dnsfcli.py policies create --template > policies-template.csv</div></div>\n\n')

    # ── endpoint reference (2 per page) ────────────────────────────────────
    # Page breaks are applied as inline styles on the opening <h2> of each pair.
    # weasyprint (PDF) honours page-break-before; Markdown/DOCX renderers
    # strip inline styles and render the heading normally — nothing is dropped.
    for pair_idx, (ep_a, ep_b) in enumerate(PAGE_PAIRS):
        page_break = ' style="page-break-before:always;"' if pair_idx > 0 else ''
        for ep_idx, ep_name in enumerate((ep_a, ep_b)):
            ep_data = REGISTRY.get(ep_name)
            if not ep_data:
                continue
            # Emit the section but inject the page-break style on the first h2
            section_html = build_endpoint_section(ep_name, ep_data)
            if ep_idx == 0 and page_break:
                section_html = section_html.replace('<h2>', f'<h2{page_break}>', 1)
            h(section_html)

    h('<div class="signoff">'
      '<div class="signoff-text">From the team at</div>'
      '<div class="signoff-name">DNSFilter</div>'
      '</div>\n\n')
    h('</section>\n')

    return buf.getvalue()


# ── build the guide ────────────────────────────────────────────────────────

# Dynamically patch and exec the brand-locked build_guide.py renderer
GUIDE_SCRIPT = pathlib.Path(__file__).parent / "build_guide.py"
src = GUIDE_SCRIPT.read_text()

# Patch asset path, output settings, cover, and body
src = src.replace(
    "ASSETS = Path(__file__).resolve().parent",
    f'ASSETS = Path(r"{ASSETS}")',
)
src = src.replace('OUT_DIR = Path(".")',       f'OUT_DIR = Path(r"{OUT_DIR}")')
# Replace whatever OUT_BASENAME is currently set to in the template
import re as _re
src = _re.sub(r'OUT_BASENAME\s*=\s*"[^"]+"', f'OUT_BASENAME = "{OUT_BASENAME}"', src, count=1)
src = src.replace('FORMATS = ["md", "docx", "confluence"]',
                  f'FORMATS = {FORMATS!r}')
src = src.replace('COVER = "minimal"', f'COVER = "{COVER}"')

# Replace COVER_FIELDS
OLD_COVER = '''COVER_FIELDS = {
    "doc_type": "Guide · No. 01",
    "eyebrow": "A short, italicized tagline",
    "title": "The Guide<br>Title",
    "subtitle": (
        "One or two sentence subtitle that tells the reader exactly what "
        "they will walk away with. Keep it concrete and specific."
    ),
    "byline": [
        ("Written by", "Author Name"),
        ("Published", "Month Year"),
        ("Audience", "Internal / Partner / Customer"),
    ],
}'''

NEW_COVER = '''COVER_FIELDS = {
    "doc_type": "API Reference · 2026",
    "eyebrow": "Complete command reference for every endpoint",
    "title": "dnsfcli<br>Full API Reference",
    "subtitle": (
        "Every endpoint, every function, and every parameter — "
        "with complete runnable examples for the DNSFilter CLI tool."
    ),
    "byline": [
        ("Updated",     "2026-07-13"),
        ("Endpoints",   "36 groups · 242 operations"),
        ("Audience",    "Developers & Administrators"),
    ],
}'''

if OLD_COVER in src:
    src = src.replace(OLD_COVER, NEW_COVER)
else:
    # Fallback: inject after FORMATS line
    src = src.replace('FORMATS = ', f'{NEW_COVER}\nFORMATS = ', 1)

# Replace BODY
body_content = build_body()
OLD_BODY_START = 'BODY = """\n<section class="content">'
if OLD_BODY_START in src:
    body_start = src.index('BODY = """')
    body_end   = src.index('"""', body_start + 10) + 3
    body_lit = body_content.replace('\\', '\\\\').replace('\"\"\"', '\\\"\\\"\\\"')
    src = src[:body_start] + f'BODY = """\n{body_lit}\n"""' + src[body_end:]
else:
    raise RuntimeError("Could not find BODY placeholder in build_guide.py")

# Replace main guard so it runs
src = src.replace("if __name__ == \"__main__\":", "if True:")

print(f"Body HTML: {len(body_content):,} chars covering {len(REGISTRY)} endpoint groups")
exec(compile(src, str(GUIDE_SCRIPT), "exec"), {
    "__file__": str(GUIDE_SCRIPT),
    "__name__": "__main__",
})
