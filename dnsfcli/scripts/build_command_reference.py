"""
build_command_reference.py

Generates comprehensive one-command-per-page documentation for dnsfcli.

Each page contains:
  - HTTP method + path
  - One-sentence description
  - Complete flag reference table (all path / query / body params)
  - Example command with realistic values
  - Real API response (for GET operations) or realistic example (for writes)
"""

import html as htmllib
import io
import json
import pathlib
import re
import sys
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

# ── paths ────────────────────────────────────────────────────────────────────

# Brand assets (fonts, logos) ship with DNSFilter's internal build-guide
# skill and are NOT part of this repository. Point DNSFCLI_BRAND_ASSETS at
# that skill's assets/ directory to rebuild the branded documents.
import os as _os
if "DNSFCLI_BRAND_ASSETS" not in _os.environ:
    sys.exit("Set DNSFCLI_BRAND_ASSETS to the build-guide skill assets directory.")
ASSETS = pathlib.Path(_os.environ["DNSFCLI_BRAND_ASSETS"])
OUT_DIR      = pathlib.Path(__file__).parent.parent / "docs"
OUT_BASENAME = "dnsfcli-command-reference"
FORMATS      = ["md", "docx", "confluence"]
COVER        = "feature"
OUT_DIR.mkdir(exist_ok=True)

from dnsfcli.endpoints import REGISTRY

# ── real output collected from the live API ───────────────────────────────────

REAL_OUTPUT: dict[str, str] = json.loads(
    (pathlib.Path(__file__).parent / "real_output_v2.json").read_text()
)

# ── example values ────────────────────────────────────────────────────────────

EX = {
    "org_id":       "802315",
    "net_id":       "736401",
    "policy_id":    "285109",
    "user_id":      "42618",
    "agent_id":     "9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5",
    "block_page_id":"5147",
    "cat_id":       "2",
    "sched_pol":    "71203",
    "apikey_id":    "20981",
    "domain":       "malware.example.com",
    "date_from":    "2025-01-01",
    "date_to":      "2025-01-31",
    "email":        "admin@company.com",
    "ip":           "203.0.113.5",
    "mac":          "AA:BB:CC:DD:EE:FF",
    "app":          "TikTok",
}

# ── example responses for write operations ────────────────────────────────────

def _w(status: int, body: dict | str | None) -> str:
    """Format a write-operation example response with HTTP status prefix."""
    reasons = {200:"OK", 201:"Created", 202:"Accepted", 204:"No Content"}
    hdr = f"HTTP {status} {reasons.get(status,'')}"
    if status == 204 or (body is None and status == 204):
        return (
            f"{hdr}\n\n"
            "# No response body — this is the expected success response.\n"
            "# HTTP 204 confirms the operation completed successfully."
        )
    if body is None:
        return hdr
    pretty = json.dumps(body, indent=2) if isinstance(body, dict) else str(body)
    return f"{hdr}\n\n{pretty}"


WRITE_RESPONSES: dict[str, str] = {
    # ── policies ────────────────────────────────────────────────────────────
    "policies/create": _w(201, {"id": 1501234, "type": "policies", "attributes": {"name": "Guest WiFi", "organization_id": 802315, "google_safesearch": True, "youtube_restricted": True, "allow_unknown_domains": True, "created_at": "2025-06-01T10:00:00.000-04:00"}}),
    "policies/update": _w(200, {"id": 285109, "type": "policies", "attributes": {"name": "Guest WiFi Updated", "organization_id": 802315, "interstitial": True, "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "policies/delete":                    _w(204, None),
    "policies/add-blacklist-domain":      _w(200, {"id": 285109, "type": "policies", "attributes": {"blacklist_domains": ["malware.example.com"]}}),
    "policies/remove-blacklist-domain":   _w(200, {"id": 285109, "type": "policies", "attributes": {"blacklist_domains": []}}),
    "policies/add-whitelist-domain":      _w(200, {"id": 285109, "type": "policies", "attributes": {"whitelist_domains": ["internal.corp.com"]}}),
    "policies/remove-whitelist-domain":   _w(200, {"id": 285109, "type": "policies", "attributes": {"whitelist_domains": []}}),
    "policies/add-blacklist-category":    _w(200, {"id": 285109, "type": "policies", "attributes": {"blacklist_categories": [2]}}),
    "policies/remove-blacklist-category": _w(200, {"id": 285109, "type": "policies", "attributes": {"blacklist_categories": []}}),
    "policies/add-allowed-application":   _w(200, {"id": 285109, "type": "policies", "attributes": {"allow_applications": ["TikTok"]}}),
    "policies/remove-allowed-application":_w(200, {"id": 285109, "type": "policies", "attributes": {"allow_applications": []}}),
    "policies/add-blocked-application":   _w(200, {"id": 285109, "type": "policies", "attributes": {"block_applications": ["TikTok"]}}),
    "policies/remove-blocked-application":_w(200, {"id": 285109, "type": "policies", "attributes": {"block_applications": []}}),
    "policies/application-update":        _w(200, {"status": "ok"}),
    "policies/bulk-add-allowlist":         _w(200, {"status": "ok", "updated_policies": [285109, 331207]}),
    "policies/bulk-add-blocklist":         _w(200, {"status": "ok", "updated_policies": [285109, 331207]}),
    "policies/bulk-remove-allowlist":      _w(200, {"status": "ok", "updated_policies": [285109]}),
    "policies/bulk-remove-blocklist":      _w(200, {"status": "ok", "updated_policies": [285109]}),
    "policies/set-permissive-mode":        _w(200, {"id": 285109, "permissive_mode": True}),
    # ── networks ────────────────────────────────────────────────────────────
    "networks/create":          _w(201, {"id": 9999901, "type": "networks", "attributes": {"name": "HQ Network", "organization_id": 802315, "created_at": "2025-06-01T10:00:00.000-04:00"}}),
    "networks/update":          _w(200, {"id": 736401, "type": "networks", "attributes": {"name": "HQ Network Updated", "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "networks/delete":          _w(204, None),
    "networks/bulk-create":      _w(202, {"id": "job-bc-123", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "networks/bulk-create-show": _w(200, {"id": "job-bc-123", "status": "completed", "created_count": 3, "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:08.000-04:00"}),
    "networks/bulk-update":      _w(202, {"id": "job-bu-456", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "networks/bulk-update-show": _w(200, {"id": "job-bu-456", "status": "completed", "updated_count": 5, "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:06.000-04:00"}),
    "networks/bulk-destroy":     _w(202, {"id": "job-bd-789", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "networks/bulk-destroy-show":_w(200, {"id": "job-bd-789", "status": "completed", "deleted_count": 5, "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:07.000-04:00"}),
    "networks/subnets-create":  _w(201, {"id": 7701, "type": "network_subnets", "attributes": {"name": "Sales Floor", "from": "10.0.1.0", "to": "10.0.1.255", "policy_id": 285109}}),
    "networks/subnets-update":  _w(200, {"id": 7701, "type": "network_subnets", "attributes": {"name": "Sales Floor Renamed", "from": "10.0.1.0", "to": "10.0.1.255"}}),
    "networks/subnets-delete":  _w(204, None),
    "networks/lan-ip-update":   _w(200, {"id": 9901, "type": "lan_ips", "attributes": {"name": "Reception Desk", "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "networks/secret-key-create": _w(201, {"secret_key": "sk-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"}),
    "networks/secret-key-update": _w(200, {"secret_key": "sk-newkey1234567890abcdef1234567890"}),
    "networks/secret-key-delete": _w(204, None),
    # ── organizations ────────────────────────────────────────────────────────
    "organizations/create":           _w(201, {"id": 9999902, "type": "organizations", "attributes": {"name": "New Client Corp", "sku": "professional", "created_at": "2025-06-01T10:00:00.000-04:00"}}),
    "organizations/update":           _w(200, {"id": 802315, "type": "organizations", "attributes": {"name": "New Client Corp Updated", "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "organizations/delete":           _w(204, None),
    "organizations/cancel":           _w(200, {"id": 802315, "type": "organizations", "attributes": {"status": "cancelled"}}),
    "organizations/promote-to-msp":   _w(200, {"id": 802315, "type": "organizations", "attributes": {"is_msp": True}}),
    "organizations/bulk-update":      _w(200, {"status": "ok", "updated_count": 2}),
    "organizations/users-create":     _w(201, {"id": 9999903, "type": "users", "attributes": {"email": "admin@company.com", "first_name": "Jane", "last_name": "Smith", "role": "administrator"}}),
    "organizations/users-update":     _w(200, {"id": 42618, "type": "users", "attributes": {"role": "read_only", "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "organizations/users-delete":     _w(204, None),
    "organizations/users-resend-invite": _w(200, {"status": "ok", "message": "Invitation resent successfully"}),
    # ── ip-addresses ─────────────────────────────────────────────────────────
    "ip-addresses/create": _w(201, {"id": 88801, "type": "ip_addresses", "attributes": {"address": "203.0.113.5", "network_id": 736401, "organization_id": 802315}}),
    "ip-addresses/update": _w(200, {"id": 88801, "type": "ip_addresses", "attributes": {"address": "203.0.113.5", "dynamic_hostname": "updated.example.com"}}),
    "ip-addresses/delete": _w(204, None),
    # ── mac-addresses ─────────────────────────────────────────────────────────
    "mac-addresses/create": _w(201, {"id": 77701, "type": "mac_addresses", "attributes": {"address": "AA:BB:CC:DD:EE:FF", "filter_value": "Reception Printer", "policy_id": 285109, "organization_id": 802315}}),
    "mac-addresses/update": _w(200, {"id": 77701, "type": "mac_addresses", "attributes": {"address": "AA:BB:CC:DD:EE:FF", "filter_value": "Updated Label"}}),
    "mac-addresses/delete": _w(204, None),
    # ── block-pages ───────────────────────────────────────────────────────────
    "block-pages/create": _w(201, {"id": 9901, "type": "block_pages", "attributes": {"name": "Corporate Block Page", "block_org_name": "Acme Corp", "block_email_addr": "admin@company.com"}}),
    "block-pages/update": _w(200, {"id": 9901, "type": "block_pages", "attributes": {"name": "Corporate Block Page Updated"}}),
    "block-pages/delete": _w(204, None),
    # ── api-keys ──────────────────────────────────────────────────────────────
    "api-keys/create": _w(201, {"id": 20982, "type": "api_keys", "attributes": {"name": "CI Pipeline Key", "expiry": "2027-05-31", "token": "eyJhbGciOiJIUzI1NiJ9.new_key_token_here", "created_at": "2025-06-01T10:00:00.000-04:00"}}),
    "api-keys/delete": _w(204, None),
    "api-keys/revoke": _w(200, {"id": 20981, "type": "api_keys", "attributes": {"name": "Old Key", "revoked_at": "2025-06-01T10:00:00.000-04:00", "status": "revoked"}}),
    # ── billing ───────────────────────────────────────────────────────────────
    "billing/create":         _w(201, {"id": 802315, "type": "billing", "attributes": {"organization_id": 802315, "status": "active"}}),
    "billing/update-address": _w(200, {"id": 802315, "type": "billing_address", "attributes": {"first_name": "Jane", "last_name": "Smith", "line1": "123 Main St", "city": "Denver", "state": "Colorado", "zip": "80202", "country": "US"}}),
    # ── enterprise-connections ────────────────────────────────────────────────
    "enterprise-connections/create": _w(201, {"id": 4401, "type": "enterprise_connections", "attributes": {"display_name": "Company SSO", "strategy": "oidc", "status": "active"}}),
    "enterprise-connections/update": _w(200, {"id": 4401, "type": "enterprise_connections", "attributes": {"display_name": "Company SSO Updated"}}),
    "enterprise-connections/delete": _w(204, None),
    # ── user-agents ───────────────────────────────────────────────────────────
    "user-agents/update":      _w(200, {"id": "9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5", "type": "user_agents", "attributes": {"friendly_name": "Finance-Laptop", "policy_id": 285109, "tags": ["managed", "finance"], "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "user-agents/delete":      _w(204, None),
    "user-agents/dequeue-uninstall": _w(200, {"status": "ok"}),
    "user-agent-bulk-deletes/create":   _w(202, {"id": "job-bd-001", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "user-agent-bulk-deletes/show":     _w(200, {"id": "job-bd-001", "status": "completed", "deleted_count": 12, "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:10.000-04:00"}),
    "user-agent-bulk-updates/create":   _w(202, {"id": "job-bu-001", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "user-agent-bulk-updates/show":     _w(200, {"id": "job-bu-001", "status": "completed", "updated_count": 12, "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:09.000-04:00"}),
    "user-agent-bulk-updates/has-mixed": _w(200, {"has_mixed": False, "fields": {"policy_id": False, "network_id": True}}),
    "user-agent-cleanups/create":   _w(202, {"id": "job-cleanup-001", "status": "pending", "organization_ids": [802315], "inactive_for": 30}),
    "user-agent-cleanups/show":     _w(200, {"id": "job-cleanup-001", "status": "completed", "deleted_count": 4, "organization_ids": [802315], "inactive_for": 30, "completed_at": "2025-06-01T10:00:30.000-04:00"}),
    "user-agent-cleanups/update":   _w(200, {"id": "job-cleanup-001", "status": "running", "start": True}),
    "user-agent-csv-exports/create": _w(202, {"id": "export-001", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "user-agent-csv-exports/show":   _w(200, {"id": "export-001", "status": "completed", "download_url": "https://api.dnsfilter.com/exports/export-001.csv", "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:15.000-04:00"}),
    # ── scheduled reports / policies ─────────────────────────────────────────
    "scheduled-reports/create":         _w(201, {"id": 9901, "type": "scheduled_reports", "attributes": {"organization_id": 802315, "frequency": "weekly", "day_of_week": "1", "include_threat_summary": True}}),
    "scheduled-reports/update":         _w(200, {"id": 9901, "type": "scheduled_reports", "attributes": {"frequency": "monthly", "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "scheduled-reports/delete":         _w(204, None),
    "scheduled-reports/preview-create": _w(202, {"id": "preview-001", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "scheduled-reports/preview-show":   _w(200, {"id": "preview-001", "status": "completed", "download_url": "https://api.dnsfilter.com/reports/preview-001.pdf", "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:20.000-04:00"}),
    "scheduled-policies/create": _w(201, {"id": 99102, "type": "scheduled_policies", "attributes": {"name": "School Hours", "organization_id": 802315, "policy_ids": [285109], "timezone": "America/Denver"}}),
    "scheduled-policies/update": _w(200, {"id": 71203, "type": "scheduled_policies", "attributes": {"name": "School Hours Updated", "timezone": "America/Chicago"}}),
    "scheduled-policies/delete": _w(204, None),
    # ── agent-local-users ─────────────────────────────────────────────────────
    "agent-local-users/update":      _w(200, {"id": 1001, "type": "agent_local_users", "attributes": {"friendly_name": "Jane Smith Laptop", "policy_id": 285109, "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    "agent-local-users/delete":      _w(204, None),
    "agent-local-users/bulk-delete":        _w(202, {"id": "job-alu-bd-001", "status": "pending", "ids": [1001, 1002, 1003]}),
    # NOTE: bulk-delete-show takes the job ID returned by bulk-delete
    "agent-local-users/bulk-delete-show":   _w(200, {"id": "job-alu-bd-001", "status": "completed", "ids": [1001, 1002, 1003], "deleted_count": 3, "created_at": "2025-06-01T10:00:00.000-04:00", "completed_at": "2025-06-01T10:00:05.000-04:00"}),
    # NOTE: bulk-delete-counts returns 404 when no bulk-delete operations have been run;
    # a populated account returns a count of users matching the bulk-delete criteria.
    "agent-local-users/bulk-delete-counts": _w(200, {"count": 47, "ids": [1001, 1002, 1003, {"...": "44 more"}]}),
    # ── collections ───────────────────────────────────────────────────────────
    "collections/users-add":    _w(201, {"id": 42618, "type": "users", "attributes": {"email": "admin@company.com", "added_at": "2025-06-01T10:00:00.000-04:00"}}),
    "collections/users-remove": _w(204, None),
    # ── current-user ─────────────────────────────────────────────────────────
    "current-user/update": _w(200, {"id": 42618, "type": "users", "attributes": {"first_name": "Jane", "last_name": "Smith", "updated_at": "2025-06-01T10:00:00.000-04:00"}}),
    # ── domains ───────────────────────────────────────────────────────────────
    "domains/suggest-threat": _w(200, {"status": "ok", "message": "Domain submitted for review"}),
    # ── notes ─────────────────────────────────────────────────────────────────
    "notes/update":        _w(200, {"domain": "malware.example.com", "type": "block", "note": "Known malware distribution point", "updated_at": "2025-06-01T10:00:00.000-04:00"}),
    "notes/batch-update":  _w(200, {"status": "ok", "updated": 3}),
    "notes/batch-destroy": _w(204, None),
    "notes/delete":        _w(204, None),
    # ── trials ────────────────────────────────────────────────────────────────
    "trials/create": _w(201, {"id": 9999906, "type": "organizations", "attributes": {"name": "Trial Org", "sku": "professional", "trial_expires_at": "2025-07-01T00:00:00.000Z"}}),
    # ── users ─────────────────────────────────────────────────────────────────
    "users/change-password": _w(200, {"status": "ok", "message": "Password changed successfully"}),
    # ── v2 ────────────────────────────────────────────────────────────────────
    "v2-current-user/suppress-license-warning": _w(200, {"status": "ok"}),
    "v2-current-user/ui-settings-update":        _w(200, {"theme_mode": "dark", "disable_license_warnings": False, "updated_at": "2025-06-01T10:00:00.000-04:00"}),
    "v2-cyber-sight/csv-export":        _w(202, {"id": "cs-export-001",  "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "v2-cyber-sight/csv-export-show":   _w(200, {"id": "cs-export-001",  "status": "completed", "download_url": "https://api.dnsfilter.com/exports/cs-export-001.csv", "completed_at": "2025-06-01T10:00:25.000-04:00"}),
    "v2-agent-local-users/csv-export":  _w(202, {"id": "alu-export-001", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "v2-agent-local-users/csv-export-show": _w(200, {"id": "alu-export-001", "status": "completed", "download_url": "https://api.dnsfilter.com/exports/alu-export-001.csv", "completed_at": "2025-06-01T10:00:12.000-04:00"}),
    "v2-networks/csv-export":           _w(202, {"id": "net-export-001", "status": "pending", "created_at": "2025-06-01T10:00:00.000-04:00"}),
    "v2-networks/csv-export-show":      _w(200, {"id": "net-export-001", "status": "completed", "download_url": "https://api.dnsfilter.com/exports/net-export-001.csv", "completed_at": "2025-06-01T10:00:10.000-04:00"}),
    "v2-user-agents/update-settings":  _w(200, {"id": "9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5", "status": "ok", "updated_at": "2025-06-01T10:00:00.000-04:00"}),
}


# ── example command values per operation ─────────────────────────────────────

EXAMPLE_ARGS: dict[str, dict[str, str]] = {
    ("agent-local-users","update"):          {"id": "1001", "friendly_name": '"Jane Smith Laptop"', "policy_id": EX["policy_id"]},
    ("agent-local-users","bulk-delete"):     {"ids": '\'["1001","1002","1003"]\''},
    ("api-keys","create"):                   {"name": '"CI Pipeline Key"', "expiry": "2027-05-31"},
    ("billing","create"):                    {"organization_id": EX["org_id"], "payment_token": "tok_visa_4242"},
    ("billing","update-address"):            {"organization_id": EX["org_id"], "first_name": '"Jane"', "last_name": '"Smith"', "line1": '"123 Main St"', "city": '"Denver"', "state": '"Colorado"', "zip": "80202", "country": '"US"'},
    ("block-pages","create"):                {"name": '"Corporate Block Page"', "block_org_name": '"Acme Corp"', "block_email_addr": EX["email"]},
    ("block-pages","update"):                {"id": "5147", "name": '"Corporate Block Page Updated"'},
    ("block-pages","delete"):                {"id": "57840"},
    ("collections","users-add"):             {"collection_id": "7788", "id": EX["user_id"]},
    ("collections","users-show"):            {"collection_id": "7788", "id": EX["user_id"]},
    ("collections","users-list"):            {"collection_id": "7788"},
    ("collections","users-remove"):          {"collection_id": "7788", "id": EX["user_id"]},
    ("current-user","update"):               {"first_name": '"Jane"', "last_name": '"Smith"'},
    ("domains","bulk-lookup"):               {"domains": "google.com,facebook.com,malware.example"},
    ("domains","suggest-threat"):            {"domain": EX["domain"], "reason": '"Flagged in phishing campaign"'},
    ("domains","user-lookup"):               {"fqdn": "dnsfilter.com"},
    ("enterprise-connections","create"):     {"client_id": "my-client-id", "client_secret": "my-secret", "discovery_url": '"https://idp.company.com/.well-known/openid-configuration"', "strategy": "oidc", "display_name": '"Company SSO"'},
    ("enterprise-connections","show"):       {"id": "4401"},
    ("enterprise-connections","list"):    {"organization_id": "802315"},
    ("enterprise-connections","update"):     {"id": "4401", "display_name": '"Company SSO Updated"'},
    ("enterprise-connections","delete"):     {"id": "4401"},
    ("ip-addresses","create"):               {"address": EX["ip"], "organization_id": EX["org_id"], "network_id": EX["net_id"]},
    ("ip-addresses","update"):               {"id": "2100638", "address": EX["ip"]},
    ("ip-addresses","delete"):               {"id": "2100638"},
    ("ip-addresses","verify"):               {"ip_address": "8.8.8.8"},
    ("mac-addresses","create"):              {"organization_id": EX["org_id"], "address": EX["mac"], "filter_value": '"Reception Printer"', "policy_id": EX["policy_id"]},
    ("mac-addresses","update"):              {"id": "77701", "address": EX["mac"], "filter_value": '"Updated Label"'},
    ("mac-addresses","delete"):              {"id": "77701"},
    ("metrics","org-usage"):                 {"id": EX["org_id"]},
    ("metrics","org-usage-detailed"):        {"id": EX["org_id"]},
    ("networks","create"):                   {"name": '"HQ Network"', "organization_id": EX["org_id"], "policy_ids": '\'["285109"]\'', "physical_address": '"123 Main St, Denver CO"'},
    ("networks","update"):                   {"id": "736401", "name": '"HQ Network Updated"', "organization_id": EX["org_id"]},
    ("networks","delete"):                   {"id": "736401"},
    ("networks","show"):                     {"id": "736401"},
    ("networks","lookup"):                   {"ip": EX["ip"]},
    ("networks","msp-all"):                  {"organization_id": "802315"},
    ("networks","msp"):                  {"organization_id": "802315"},
    ("networks","lan-ips"):                  {"id": "736401"},
    ("networks","lan-ip-show"):              {"id": "736401", "lan_ip_id": "9901"},
    ("networks","lan-ip-update"):            {"id": "736401", "lan_ip_id": "9901", "name": '"Reception Desk"'},
    ("networks","secret-key-create"):        {"id": "736401"},
    ("networks","secret-key-update"):        {"id": "736401"},
    ("networks","secret-key-delete"):        {"id": "736401"},
    ("networks","subnets-list"):             {"id": EX["net_id"]},
    ("networks","subnets-create"):           {"id": EX["net_id"], "name": '"Sales Floor"', "from": "10.0.1.0", "to": "10.0.1.255"},
    ("networks","subnets-show"):             {"id": "736401", "subnet_id": "2165762"},
    ("networks","subnets-update"):           {"id": "736401", "subnet_id": "2165762", "name": '"Sales Floor Renamed"', "from": "10.0.1.0", "to": "10.0.1.255"},
    ("networks","subnets-delete"):           {"id": "736401", "subnet_id": "2165762"},
    ("networks","bulk-create"):              {},
    ("networks","bulk-create-show"):         {"id": "job-bc-123"},
    ("networks","bulk-update"):              {"ids": f'{EX["net_id"]},736402', "policy_id": EX["policy_id"]},
    ("networks","bulk-update-show"):         {"id": "job-bu-456"},
    ("networks","bulk-destroy"):             {},
    ("networks","bulk-destroy-show"):        {"id": "job-bd-789"},
    ("notes","show"):                        {"resource": "networks", "id": EX["net_id"], "domain": EX["domain"]},
    ("notes","update"):                      {"resource": "networks", "id": EX["net_id"], "domain": EX["domain"], "type": "block", "note": '"Known malware distribution point"'},
    ("notes","batch-update"):                {"resource": "networks", "id": EX["net_id"]},
    ("notes","batch-destroy"):               {"resource": "networks", "id": EX["net_id"]},
    ("notes","delete"):                      {"resource": "networks", "id": EX["net_id"], "domain": EX["domain"]},
    ("organizations","create"):              {"name": '"New Client Corp"', "billing_contact_email": EX["email"], "sku": "professional"},
    ("organizations","update"):              {"id": EX["org_id"], "name": '"New Client Corp Updated"'},
    ("organizations","delete"):              {"id": EX["org_id"]},
    ("organizations","cancel"):              {"id": EX["org_id"]},
    ("organizations","bulk-update"):         {"organization_ids": f'\'["{EX["org_id"]}"]\'', "gdpr": "true"},
    ("organizations","users-create"):        {"organization_id": EX["org_id"], "email": EX["email"], "first_name": '"Jane"', "last_name": '"Smith"', "role": "administrator"},
    ("organizations","users-list"):          {"organization_id": EX["org_id"]},
    ("organizations","users-show"):          {"organization_id": EX["org_id"], "id": EX["user_id"]},
    ("organizations","users-update"):        {"organization_id": EX["org_id"], "id": EX["user_id"], "role": "read_only"},
    ("organizations","users-delete"):        {"organization_id": EX["org_id"], "id": EX["user_id"]},
    ("organizations","users-resend-invite"): {"organization_id": EX["org_id"], "id": EX["user_id"]},
    ("policies","create"):                   {"name": '"Guest WiFi"', "organization_id": EX["org_id"], "allow_unknown_domains": "true", "google_safesearch": "true", "youtube_restricted": "true", "youtube_restricted_level": "strict"},
    ("policies","update"):                   {"id": EX["policy_id"], "name": '"Guest WiFi Updated"', "interstitial": "true"},
    ("policies","delete"):                   {"id": EX["policy_id"]},
    ("policies","show"):                     {"id": EX["policy_id"]},
    ("policies","add-blacklist-domain"):     {"id": EX["policy_id"], "domain": EX["domain"], "note": '"Flagged by threat intel"'},
    ("policies","add-whitelist-domain"):     {"id": EX["policy_id"], "domain": "internal.corp.com"},
    ("policies","remove-blacklist-domain"):  {"id": EX["policy_id"], "domain": EX["domain"]},
    ("policies","remove-whitelist-domain"):  {"id": EX["policy_id"], "domain": "internal.corp.com"},
    ("policies","add-blacklist-category"):   {"id": EX["policy_id"], "category_id": EX["cat_id"]},
    ("policies","remove-blacklist-category"):{"id": EX["policy_id"], "category_id": EX["cat_id"]},
    ("policies","add-allowed-application"):  {"id": EX["policy_id"], "name": EX["app"]},
    ("policies","add-blocked-application"):  {"id": EX["policy_id"], "name": EX["app"]},
    ("policies","remove-allowed-application"):{"id": EX["policy_id"], "name": EX["app"]},
    ("policies","remove-blocked-application"):{"id": EX["policy_id"], "name": EX["app"]},
    ("policies","bulk-add-allowlist"):       {"policy_ids": '\'["285109","331207"]\'', "domains": '\'["safe.com","trusted.org"]\''},
    ("policies","bulk-add-blocklist"):       {"policy_ids": '\'["285109","331207"]\'', "domains": '\'["evil.com","malware.net"]\''},
    ("policies","bulk-remove-allowlist"):    {"policy_ids": '\'["285109"]\'', "domains": '\'["safe.com"]\''},
    ("policies","bulk-remove-blocklist"):    {"policy_ids": '\'["285109"]\'', "domains": '\'["evil.com"]\''},
    ("policies","set-permissive-mode"):      {"id": EX["policy_id"], "enabled": "true"},
    ("scheduled-policies","create"):         {"name": '"School Hours"', "organization_id": EX["org_id"], "policy_ids": f'\'["{EX["policy_id"]}\"]\'', "timezone": "America/Denver"},
    ("scheduled-policies","update"):         {"id": EX["sched_pol"], "name": '"School Hours Updated"', "timezone": "America/Chicago"},
    ("scheduled-policies","delete"):         {"id": EX["sched_pol"]},
    ("scheduled-policies","show"):           {"id": EX["sched_pol"]},
    ("scheduled-reports","create"):          {"organization_id": EX["org_id"], "frequency": "weekly", "day_of_week": "1", "include_threat_summary": "true", "send_to_dashboard_users": "true"},
    ("scheduled-reports","update"):          {"id": "9901", "frequency": "monthly"},
    ("scheduled-reports","delete"):          {"id": "9901"},
    ("scheduled-reports","list"):         {"organization_id": "802315"},
    ("scheduled-reports","show"):            {"id": "9901"},
    ("scheduled-reports","preview-create"):  {"organization_id": EX["org_id"], "include_threat_summary": "true"},
    ("scheduled-reports","preview-show"):    {"id": "preview-001"},
    ("trials","create"):                     {"organization_id": EX["org_id"], "sku": "professional"},
    ("user-agent-bulk-deletes","create"):    {"ids": f'\'["{EX["agent_id"]}\"]\''},
    ("user-agent-bulk-deletes","show"):      {"id": "job-bd-001"},
    ("user-agent-bulk-updates","create"):    {"ids": f'\'["{EX["agent_id"]}\"]\'', "policy_id": EX["policy_id"]},
    ("user-agent-bulk-updates","has-mixed"): {"ids": f'\'["{EX["agent_id"]}\"]\''},
    ("user-agent-bulk-updates","show"):      {"id": "job-bu-001"},
    ("user-agent-cleanups","create"):        {"organization_ids": f'\'["{EX["org_id"]}\"]\'', "inactive_for": "30"},
    ("user-agent-cleanups","show"):          {"id": "job-cleanup-001"},
    ("user-agent-cleanups","update"):        {"id": "job-cleanup-001", "start": "true", "inactive_for": "30"},
    ("user-agent-csv-exports","create"):     {"organization_ids": f'\'["{EX["org_id"]}\"]\''},
    ("user-agent-csv-exports","show"):       {"id": "export-001"},
    ("user-agents","update"):                {"id": EX["agent_id"], "friendly_name": '"Finance-Laptop"', "policy_id": EX["policy_id"], "tags": '\'["managed","finance"]\''},
    ("user-agents","delete"):                {"id": EX["agent_id"]},
    ("user-agents","show"):                  {"id": EX["agent_id"]},
    ("users","show"):                        {"id": EX["user_id"]},
    ("users","change-password"):             {"new_password": '"NewSecurePass123!"'},
    ("v2-agent-local-users","csv-export"):   {"organization_ids": f'\'["{EX["org_id"]}\"]\''},
    ("v2-agent-local-users","csv-export-show"):{"id": "alu-export-001"},
    ("v2-current-user","ui-settings-update"):{"theme_mode": "dark"},
    ("v2-current-user","suppress-license-warning"): {},
    ("v2-cyber-sight","csv-export"):         {"organization_ids": f'\'["{EX["org_id"]}\"]\'', "threats_only": "true", "start_at": "2025-01-01T00:00:00Z", "end_at": "2025-01-31T23:59:59Z"},
    ("v2-cyber-sight","csv-export-show"):    {"id": "cs-export-001"},
    ("v2-networks","csv-export"):            {"organization_ids": f'\'["{EX["org_id"]}\"]\''},
    ("v2-networks","csv-export-show"):       {"id": "net-export-001"},
    ("v2-user-agents","update-settings"):    {"id": EX["agent_id"], "policy_id": EX["policy_id"]},
    ("billing","get-address"):               {"organization_id": EX["org_id"]},
    ("collections","users-list"):            {"collection_id": "7788"},
    ("api-keys","show"):                     {"id": "1618"},
    ("api-keys","delete"):                   {"id": "1618"},
    ("api-keys","revoke"):                   {"id": "1618"},
    ("agent-local-users","show"):            {"id": "1001"},
    ("agent-local-users","delete"):          {"id": "1001"},
    ("agent-local-users","bulk-delete-show"):{"id": "job-alu-bd-001"},
    ("block-pages","show"):                  {"id": "57840"},
    ("categories","show"):                   {"id": "2"},
    ("application-categories","show"):       {"id": "1"},
    ("applications","show"):                  {"id": "496"},
    ("invoices","show"):                     {"id": "inv-001"},
    ("invoices","current"):                  {"organization_id": "802315"},
    ("invoices","list"):                  {"organization_id": "802315"},
    ("ip-addresses","show"):                 {"id": "2100638"},
    ("ip-addresses","list-all"):             {},
    ("mac-addresses","show"):                {"id": "77701"},
    ("policy-ips","show"):                   {"id": "pp-001"},
    ("enterprise-connections","list-all"):   {},
}

# Default args for list operations
LIST_DEFAULTS = {"list": {"page": "1", "per_page": "25"}}
TRAFFIC_DATES = {"start_date": EX["date_from"], "end_date": EX["date_to"]}


# ── HTML helpers ─────────────────────────────────────────────────────────────

def e(t: str) -> str:
    return htmllib.escape(str(t))


KIND_LABELS = {"path": "Path", "query": "Query", "body": "Body"}

TYPE_DESCRIPTIONS: dict[str, str] = {
    "string":  "text string",
    "integer": "whole number",
    "boolean": "true or false",
    "array":   "JSON array  e.g. [\"a\",\"b\"]",
    "object":  "JSON object e.g. {\"key\":\"value\"}",
}

PARAM_HINTS: dict[str, str] = {
    "id":             "The numeric ID of the resource to operate on.",
    "organization_id":"The numeric ID of the organization that owns this resource.",
    "network_id":     "The numeric ID of the network to associate with.",
    "policy_id":      "The numeric ID of the filtering policy to assign.",
    "policy_ids":     "An array of policy IDs to assign. Example: [\"285109\",\"331207\"]",
    "block_page_id":  "The numeric ID of the block page to display when a domain is blocked.",
    "scheduled_policy_id": "The numeric ID of a time-based scheduled policy.",
    "collection_id":  "The numeric ID of the user collection.",
    "organization_ids":"An array of organization IDs. Example: [\"802315\",\"802316\"]",
    "lan_ip_id":      "The numeric ID of the LAN IP address entry.",
    "subnet_id":      "The numeric ID of the network subnet.",
    "resource":       "The resource type the note is attached to. Example: networks",
    "domain":         "A fully-qualified domain name. Example: malware.example.com",
    "name":           "A human-readable display name for this resource.",
    "friendly_name":  "The display name shown for this agent in the dashboard.",
    "address":        "The IP address (for ip-addresses) or MAC address (for mac-addresses).",
    "ip_address":     "The IP address to look up or verify.",
    "email":          "An email address. Example: admin@company.com",
    "first_name":     "The user's given (first) name.",
    "last_name":      "The user's family (last) name.",
    "phone":          "A phone number. Example: +12025551234",
    "role":           "The user's role. One of: administrator, read_only, network_administrator, network_support, support.",
    "expiry":         "The expiry date in YYYY-MM-DD format. Maximum 1 year from today.",
    "from":           "The start IP address of the subnet range. Example: 10.0.1.0",
    "to":             "The end IP address of the subnet range. Example: 10.0.1.255",
    "start_date":     "Report start date in YYYY-MM-DD format. Example: 2025-01-01",
    "end_date":       "Report end date in YYYY-MM-DD format. Example: 2025-01-31",
    "page":           "Page number for paginated results. Default: 1.",
    "per_page":       "Number of results per page. Default: 25.",
    "ids":            "An array of resource IDs. Example: [\"id1\",\"id2\"]",
    "exclude_ids":    "An array of resource IDs to exclude from the operation.",
    "domains":        "An array of domain names. Example: [\"evil.com\",\"malware.net\"]",
    "category_id":    "The numeric ID of a DNS filtering category. Use 'categories list' to see all IDs.",
    "sku":            "A product SKU code. Example: professional",
    "inactive_for":   "Number of days of inactivity after which agents are considered inactive.",
    "frequency":      "Report frequency. One of: daily, weekly, monthly.",
    "day_of_week":    "Day of week for weekly reports. 0=Sunday, 1=Monday … 6=Saturday.",
    "timezone":       "IANA timezone string. Example: America/Denver",
    "include_threat_summary":          "Include the threat summary section in the report. true or false.",
    "include_content_category_summary":"Include the content category summary section. true or false.",
    "send_to_dashboard_users":         "Send the report to all dashboard users. true or false.",
    "google_safesearch":               "Force Google SafeSearch on for all users on this policy.",
    "bing_safe_search":                "Force Bing SafeSearch on for all users on this policy.",
    "duck_duck_go_safe_search":        "Force DuckDuckGo SafeSearch on for all users on this policy.",
    "ecosia_safesearch":               "Force Ecosia SafeSearch on for all users on this policy.",
    "yandex_safe_search":              "Force Yandex SafeSearch on for all users on this policy.",
    "youtube_restricted":              "Enable YouTube restricted mode for all users on this policy.",
    "youtube_restricted_level":        "YouTube restriction level. One of: strict, none.",
    "interstitial":                    "Show an interstitial warning page before blocked domains.",
    "allow_unknown_domains":           "Allow domains not yet classified by DNSFilter. Default: false.",
    "allow_list_only":                 "Block all domains except those explicitly allowlisted. Default: false.",
    "is_global_policy":                "Mark this policy as a global (default) policy for the organization.",
    "whitelist_domains":               "Domains to pre-populate on the allowlist. JSON array of strings.",
    "blacklist_domains":               "Domains to pre-populate on the blocklist. JSON array of strings.",
    "blacklist_categories":            "Category IDs to pre-populate on the blocklist. JSON array of integers.",
    "allow_applications":              "Application names to pre-populate on the allowed-applications list.",
    "block_applications":              "Application names to pre-populate on the blocked-applications list.",
    "append_domains":                  "If true, append to existing allow/block lists instead of replacing them.",
    "include_relationships":           "Include related objects (org, networks) in the response. Default: true.",
    "tags":                            "Agent tags as a JSON array. Example: [\"managed\",\"finance\"]",
    "filter_value":                    "A display label for this MAC address, shown in the dashboard.",
    "dynamic_hostname":                "A dynamic DNS hostname associated with this IP address.",
    "physical_address":                "The physical street address of the network location.",
    "external_id":                     "An external identifier from a third-party system.",
    "is_legacy_vpn_active":            "Enable legacy VPN mode for this network.",
    "local_domains":                   "Local domain names that should resolve internally, not via DNSFilter.",
    "local_resolvers":                 "IP addresses of local DNS resolvers to use for local_domains.",
    "enabled":                         "Enable or disable this feature. true or false.",
    "search":                          "Filter results by a text search string.",
    "status":                          "Filter by resource status.",
    "type":                            "Note type. Example: block",
    "note":                            "The note text to attach to this domain on the resource.",
    "start":                           "Set to true to start the cleanup job immediately.",
    "new_password":                    "The new password to set for the current user.",
    "theme_mode":                      "UI theme. One of: light, dark, system.",
    "organization_id_path":            "Organization ID in the URL path.",
    "cidr":                            "CIDR notation subnet. Example: 10.0.1.0/24",
    "ip":                              "An IP address to look up in the network registry.",
    "reasons":                         "Reason for the threat submission.",
    "reason":                          "Reason for the threat submission.",
}


def param_description(p) -> str:
    hint = PARAM_HINTS.get(p.name)
    if hint:
        return hint
    if p.description:
        return p.description
    return f"The {p.name.replace('_', ' ')} value."


def build_command(endpoint: str, function: str, op) -> str:
    """Build a formatted multi-line example command."""
    parts = [f"python dnsfcli.py {endpoint} {function}"]
    overrides = EXAMPLE_ARGS.get((endpoint, function), {})

    for p in op.params:
        if p.kind == "path":
            val = overrides.get(p.name)
            if val is None:
                if p.name == "id":
                    val = {"networks": EX["net_id"], "policies": EX["policy_id"],
                           "organizations": EX["org_id"], "users": EX["user_id"],
                           "user-agents": EX["agent_id"]}.get(endpoint, "12345")
                elif p.name == "organization_id": val = EX["org_id"]
                elif p.name == "collection_id":   val = "7788"
                elif p.name == "lan_ip_id":        val = "9901"
                elif p.name == "subnet_id":        val = "4455"
                elif p.name == "resource":         val = "networks"
                elif p.name == "domain":           val = EX["domain"]
                else:                              val = "12345"
            parts.append(f"--{p.name} {val}")

    if endpoint == "traffic-reports":
        parts.append(f"--start_date {EX['date_from']}")
        parts.append(f"--end_date {EX['date_to']}")

    if function == "list" and endpoint != "traffic-reports":
        parts.append("--page 1 --per_page 25")

    if op.method in ("POST", "PATCH", "PUT"):
        for p in op.params:
            if p.kind != "body":
                continue
            val = overrides.get(p.name)
            if val is None and p.required:
                val = {"integer": "1", "boolean": "true", "array": '\'["item1","item2"]\'', "string": '"example"'}.get(p.type_hint, '"value"')
            if val is not None:
                parts.append(f"--{p.name} {val}")
    elif op.method == "GET":
        for p in op.params:
            if p.kind == "query" and p.name not in ("page","per_page","start_date","end_date"):
                val = overrides.get(p.name)
                if val is not None:
                    parts.append(f"--{p.name} {val}")

    if len(parts) == 1:
        return parts[0]
    # Wrap each flag on its own line for readability
    base = parts[0]
    flags = parts[1:]
    if len(" ".join(parts)) <= 90:
        return " ".join(parts)
    return base + " \\\n  " + " \\\n  ".join(flags)


def _endpoint_404_note(endpoint, function):
    notes = {
        "psa-integrations": "# HTTP 404 is expected when no PSA integration is configured on this account.",
        "policies/application": "# HTTP 404 is expected when the application policy feature is not enabled on this account.",
        "billing": "# HTTP 404 is expected when no billing record is configured. Use billing/create to set one up.",
        "invoices": "# HTTP 404 is expected when the account has no invoices or billing is not configured.",
        "enterprise-connections": "# HTTP 404 is expected when no enterprise SSO connections are configured.",
        "notes": "# HTTP 404 is returned when no note exists for the specified domain on this resource.",
        "collections": "# HTTP 404 is returned when the specified collection does not exist.",
        "networks/lan-ip": "# HTTP 404 is returned when no LAN IPs are registered for this network.",
        "scheduled-reports": "# HTTP 404 is returned when the specified report does not exist.",
        "agent-local-users/bulk-delete": "# HTTP 404 is returned when no bulk-delete job exists with this ID. Create one first with agent-local-users bulk-delete.",
    }
    for prefix, note in notes.items():
        if endpoint.startswith(prefix.split("/")[0]) or key_contains(endpoint, function, prefix):
            return note
    return "# HTTP 404 — resource not found. Verify the ID exists on your account."

def _endpoint_400_note(endpoint, function):
    notes = {
        "traffic-reports/total-client-stats": "# HTTP 400 is expected when the time range exceeds 20 minutes. This endpoint only accepts windows of 20 minutes or less.",
        "traffic-reports/qps": "# HTTP 400 is expected when the time range is too large. QPS endpoints require a narrow real-time window.",
        "networks/lookup": "# HTTP 400 is returned when the IP address is not registered to any network on this account.",
        "domains/user-lookup": "# HTTP 400 is returned when there is no active DNS-over-HTTPS user session to look up.",
        "ip-addresses/verify": "# HTTP 400 or 500 is returned when the IP address is not registered to this account.",
    }
    for prefix, note in notes.items():
        if f"{endpoint}/{function}".startswith(prefix) or endpoint.startswith(prefix):
            return note
    return "# HTTP 400 — the request parameters were invalid or missing required values."

def key_contains(endpoint, function, prefix):
    return prefix in f"{endpoint}/{function}"


def get_response(endpoint: str, function: str, op) -> str:
    key = f"{endpoint}/{function}"
    real = REAL_OUTPUT.get(key)
    write = WRITE_RESPONSES.get(key)

    # Priority: real 200 response > write response > annotated empty/error > fallback

    if real and real.startswith("HTTP 200") and "{}" not in real.split("\n\n",1)[-1].strip():
        return real  # real non-empty 200

    if write:
        return write  # constructed write example with status

    if real:
        status_line = real.split("\n")[0]  # "HTTP 200 OK" or "HTTP 404 Not Found" etc
        body_part = real.split("\n\n",1)[-1].strip() if "\n\n" in real else ""

        if "HTTP 200" in status_line and (not body_part or body_part in ("{}", "null", "[]")):
            return f"{status_line}\n\n# Empty response — this is the expected behaviour for this endpoint.\n# It indicates the operation succeeded but there is no data to return.\n{body_part or '{}'}"

        if "HTTP 204" in status_line:
            return f"HTTP 204 No Content\n\n# No response body — this is the expected success response.\n# HTTP 204 confirms the operation completed successfully."

        if "HTTP 404" in status_line:
            note = _endpoint_404_note(endpoint, function)
            return f"{status_line}\n\n{note}\n\n{body_part}"

        if "HTTP 401" in status_line or "HTTP 403" in status_line:
            return f"{status_line}\n\n# This endpoint requires distributor-level access.\n# This account does not have distributor privileges.\n\n{body_part}"

        if "HTTP 400" in status_line:
            note = _endpoint_400_note(endpoint, function)
            return f"{status_line}\n\n{note}\n\n{body_part}"

        return real

    if op.method == "DELETE":
        return (
            "HTTP 204 No Content\n\n"
            "# No response body — this is the expected success response.\n"
            "# HTTP 204 confirms the resource was deleted successfully."
        )

    if op.method in ("POST","PATCH","PUT"):
        return _w(200, {"status": "ok", "message": "Operation completed successfully"})

    # GET with no real response collected — add context based on endpoint
    if endpoint == "collections":
        return (
            "HTTP 200 OK\n\n"
            "# Empty response — this is the expected behaviour when no users exist in the collection.\n"
            "{}"
        )
    if endpoint == "invoices":
        return (
            "HTTP 404 Not Found\n\n"
            "# HTTP 404 is expected when the account has no invoices or billing is not configured.\n\n"
            '{\n  "error": "Unable to find the object that you requested."\n}'
        )
    if endpoint == "enterprise-connections":
        return (
            "HTTP 200 OK\n\n"
            "# Empty response — this is the expected behaviour when no SSO connections are configured.\n"
            '{\n  "data": []\n}'
        )
    # Generic fallback: annotate so readers know an empty body is not an error
    return (
        "HTTP 200 OK\n\n"
        "# Empty response — this is the expected behaviour for this endpoint.\n"
        "# It indicates the operation succeeded but no data was returned.\n"
        "{}"
    )


FUNC_DESCRIPTIONS: dict[str, str] = {
    "list":       "Retrieve a paginated list of {endpoint} resources.",
    "list-all":   "Retrieve all {endpoint} resources without pagination limits.",
    "show":       "Retrieve a single {endpoint} resource by its ID.",
    "create":     "Create a new {endpoint} resource.",
    "update":     "Update an existing {endpoint} resource by its ID.",
    "delete":     "Permanently delete a {endpoint} resource by its ID.",
}


def get_description(endpoint: str, function: str, op) -> str:
    tmpl = FUNC_DESCRIPTIONS.get(function)
    if tmpl:
        return tmpl.format(endpoint=endpoint)
    return op.description + "."


# Per-param example values used in the flag usage column
_PARAM_EXAMPLES: dict[str, str] = {
    "id":                    "285109",
    "organization_id":       "802315",
    "network_id":            "736401",
    "policy_id":             "285109",
    "policy_ids":            '["285109","331207"]',
    "collection_id":         "7788",
    "lan_ip_id":             "9901",
    "subnet_id":             "4455",
    "block_page_id":         "5147",
    "scheduled_policy_id":   "71203",
    "resource":              "networks",
    "domain":                "malware.example.com",
    "name":                  '"Guest WiFi"',
    "friendly_name":         '"Finance-Laptop"',
    "address":               "203.0.113.5",
    "ip_address":            "8.8.8.8",
    "email":                 "admin@company.com",
    "first_name":            '"Jane"',
    "last_name":             '"Smith"',
    "phone":                 "+12025551234",
    "role":                  "administrator",
    "expiry":                "2027-05-31",
    "from":                  "10.0.1.0",
    "to":                    "10.0.1.255",
    "start_date":            "2025-01-01",
    "end_date":              "2025-01-31",
    "page":                  "1",
    "per_page":              "25",
    "ids":                   '["9b2f6c04-5a1e-4d37-8c2a-f0e1d2c3b4a5"]',
    "exclude_ids":           '["other-agent-uuid"]',
    "domains":               '["evil.com","malware.net"]',
    "category_id":           "2",
    "sku":                   "professional",
    "inactive_for":          "30",
    "frequency":             "weekly",
    "day_of_week":           "1",
    "timezone":              "America/Denver",
    "include_threat_summary":          "true",
    "include_content_category_summary":"true",
    "send_to_dashboard_users":         "true",
    "google_safesearch":               "true",
    "bing_safe_search":                "true",
    "duck_duck_go_safe_search":        "true",
    "ecosia_safesearch":               "true",
    "yandex_safe_search":              "true",
    "youtube_restricted":              "true",
    "youtube_restricted_level":        "strict",
    "interstitial":                    "true",
    "allow_unknown_domains":           "true",
    "allow_list_only":                 "false",
    "is_global_policy":                "false",
    "whitelist_domains":               '["safe.com","trusted.org"]',
    "blacklist_domains":               '["evil.com","malware.net"]',
    "blacklist_categories":            '["2","14","66"]',
    "allow_applications":              '["Slack","Zoom"]',
    "block_applications":              '["TikTok","Instagram"]',
    "append_domains":                  "true",
    "include_relationships":           "true",
    "tags":                            '["managed","finance"]',
    "filter_value":                    '"Reception Printer"',
    "dynamic_hostname":                "myhost.dyndns.org",
    "physical_address":                '"123 Main St, Denver CO"',
    "external_id":                     "ext-12345",
    "is_legacy_vpn_active":            "false",
    "local_domains":                   '["corp.local","internal.local"]',
    "local_resolvers":                 '["192.168.1.1","192.168.1.2"]',
    "enabled":                         "true",
    "search":                          '"laptop"',
    "status":                          "active",
    "type":                            "block",
    "note":                            '"Known C2 infrastructure"',
    "start":                           "true",
    "new_password":                    '"NewSecurePass123!"',
    "theme_mode":                      "dark",
    "ip":                              "203.0.113.5",
    "reason":                          '"Flagged in phishing campaign"',
    "organization_ids":                '["802315"]',
    "billing_contact_email":           "billing@company.com",
    "billing_contact_name":            '"Jane Smith"',
    "billing_contact_phone":           "+12025551234",
    "gdpr":                            "true",
    "privacy_mode":                    "standard",
    "enable_cybersight":               "true",
    "show_pii_rc_hostnames":           "false",
    "unique_id":                       "ext-client-001",
    "quantity":                        "25",
    "payment_token":                   "tok_visa_4242",
    "first_name_billing":              '"Jane"',
    "line1":                           '"123 Main St"',
    "line2":                           '"Suite 400"',
    "city":                            '"Denver"',
    "state":                           '"Colorado"',
    "state_code":                      '"CO"',
    "zip":                             "80202",
    "country":                         '"US"',
    "company":                         '"Acme Corp"',
    "content_categories_show_count":   "10",
    "lock_version":                    "23",
    "policy_ip_id":                    "7701",
    "organization_permission_ids":     '["perm-1","perm-2"]',
    "is_include_only_list":            "false",
    "client_id":                       "my-client-id",
    "client_secret":                   "my-client-secret",
    "discovery_url":                   '"https://idp.company.com/.well-known/openid-configuration"',
    "strategy":                        "oidc",
    "display_name":                    '"Company SSO"',
    "role_default":                    "read_only",
    "role_map":                        '["admin-group:administrator"]',
    "idp":                             "okta",
    "authorized_domains":              '["company.com"]',
    "network_ids":                     '["736401","736402"]',
    "msp_id":                          "8801",
    "release_channels":                '["stable"]',
    "device_setting_attributes":       '{"auto_update":true}',
    "filtering_client_setting_attributes": '{"block_malware":true}',
    "vpn_settings_user_agent":         '{"enabled":true}',
    "vpn_settings_organization_attributes": '{"enabled":false}',
    "start_at":                        "2025-01-01T00:00:00Z",
    "end_at":                          "2025-01-31T23:59:59Z",
    "threats_only":                    "true",
    "included_columns":                '["domain","category","action"]',
    "sort_by":                         "domain",
    "sort_direction":                  "asc",
    "disable_license_warnings":        "false",
    "user_uuid":                       "0175f7b1-704d-72f8-9855-538ed456663c",
    "managed_by_msp_id":               "8801",
    "selected_sub_orgs":               '["802316","491461"]',
    "scheduled_report_recipients":     '[{"email":"admin@company.com"}]',
    "user_policy_override":            "false",
    "block_org_name":                  '"Acme Corp"',
    "block_email_addr":                "admin@company.com",
    "block_logo_uuid":                 "uuid-logo-1234",
    "filter_value_mac":                '"Reception Printer"',
    "inactive_for_days":               "30",
}


def flag_example_value(endpoint: str, function: str, p) -> str:
    """Return a realistic example value for a flag, for use in the FLAGS block."""
    # Check command-specific EXAMPLE_ARGS overrides first
    val = EXAMPLE_ARGS.get((endpoint, function), {}).get(p.name)
    if val is not None:
        return str(val)
    # Named-param lookup
    val = _PARAM_EXAMPLES.get(p.name)
    if val is not None:
        return str(val)
    # Id param: pick a sensible default by endpoint
    if p.name == "id":
        return {"networks": EX["net_id"], "policies": EX["policy_id"],
                "organizations": EX["org_id"], "users": EX["user_id"],
                "user-agents": EX["agent_id"]}.get(endpoint, "12345")
    # Type-based fallback
    return {"string": '"example"', "integer": "1", "boolean": "true",
            "array": '["item1","item2"]', "object": '{"key":"value"}'}.get(p.type_hint, "value")


# ── page builder ─────────────────────────────────────────────────────────────

def build_page(endpoint: str, function: str, op, page_num: int) -> str:
    buf = io.StringIO()
    h = buf.write

    page_break = 'style="page-break-before:always; margin-top:0;"' if page_num > 0 else ""

    h(f'<h2 {page_break}>{e(endpoint)} {e(function)}</h2>\n')
    h(f'<p style="font-family:monospace; color:#666; font-size:0.85em;">'
      f'{e(op.method)}&nbsp;&nbsp;{e(op.path_template)}</p>\n')
    h(f'<p>{e(get_description(endpoint, function, op))}</p>\n\n')

    # ── flags block (formatted text — renders in all four output formats) ──
    params_to_show = [p for p in op.params
                      if not (p.kind == "query" and function not in ("list",)
                              and p.name in ("page", "per_page"))]
    if endpoint == "traffic-reports":
        params_to_show = list(op.params)

    if params_to_show:
        # One flag per line: --flag  Description of what it does, e.g. --flag example_value
        lines = []
        for p in params_to_show:
            flag     = f"--{p.name}"
            desc     = param_description(p).rstrip(".")
            req_tag  = " [required]" if p.required else ""
            example  = f"--{p.name} {flag_example_value(endpoint, function, p)}"
            lines.append(f"{flag}{req_tag}  {desc}, e.g. {example}")

        lines += [
            "",
            "Common global flags (every command; see the Global Flags page for all of them):",
            "--raw             Return raw JSON instead of the formatted table, e.g. --raw",
            "--json            Output JSON to stdout (automatic when piped), e.g. --json",
            "--to-csv FILE     Write the response to a CSV file, e.g. --to-csv output.csv",
            "--from-csv FILE   Read input rows from a CSV file (one API call per row), e.g. --from-csv policies.csv",
            "--template        Print a blank CSV import template for this command and exit, e.g. --template",
            "--filter EXPR     Keep matching rows only, e.g. --filter status=active",
            "--columns a,b,c   Limit table output to named columns, e.g. --columns id,name",
            "--org-id ID       Override the stored organization ID for this call only, e.g. --org-id 802315",
        ]
        # Join with <br> (not \n). Each line is individually HTML-escaped so the
        # <br> tag is a real tag, not an escaped entity.  The CSS patch below
        # adds white-space:pre-wrap so PDF renders each <br> as a line break,
        # and the html_to_plain patch below converts <br> to \n for Markdown.
        flag_html = "<br>".join(e(line) for line in lines)
        h('<div class="prompt">\n')
        h('  <div class="prompt-label">FLAGS</div>\n')
        h(f'  <div class="prompt-body">{flag_html}</div>\n')
        h('</div>\n\n')

    # ── example command ─────────────────────────────────────────────────────
    cmd = build_command(endpoint, function, op)
    h('<div class="prompt">\n')
    h(f'  <div class="prompt-label">EXAMPLE COMMAND</div>\n')
    h(f'  <div class="prompt-body">{e(cmd)}</div>\n')
    h('</div>\n\n')

    # ── response ────────────────────────────────────────────────────────────
    resp = get_response(endpoint, function, op)
    h('<div class="prompt">\n')
    h(f'  <div class="prompt-label">RESPONSE</div>\n')
    h(f'  <div class="prompt-body">{e(resp)}</div>\n')
    h('</div>\n\n')

    return buf.getvalue()


# ── assemble body ─────────────────────────────────────────────────────────────

def build_body() -> str:
    buf = io.StringIO()
    h = buf.write

    h('<section class="content">\n\n')

    # Intro page
    h('<h2>Getting Started</h2>\n')
    _total_ops = sum(len(ep.operations) for ep in REGISTRY.values())
    h(f'<p>dnsfcli is a command-line tool for the complete DNSFilter REST API. '
      f'Every endpoint and operation is available from the terminal. '
      f'This reference documents all {_total_ops} operations — one per page — with the exact flags, '
      f'a complete example command, and the response you can expect.</p>\n\n')

    h('<h3>Install</h3>\n')
    h('<div class="prompt"><div class="prompt-label">INSTALL</div>'
      '<div class="prompt-body">pip install -e .</div></div>\n\n')

    h('<h3>Authenticate</h3>\n')
    h('<p>Store your API token and default organization ID in the OS keychain once. '
      'Every command picks them up automatically.</p>\n')
    h('<div class="prompt"><div class="prompt-label">AUTH SETUP</div>'
      '<div class="prompt-body">'
      'python dnsfcli.py auth setup\n'
      'python dnsfcli.py auth setup --org-id 802315\n'
      'python dnsfcli.py auth verify\n'
      'python dnsfcli.py auth show</div></div>\n\n')

    h('<h3>Global flags</h3>\n')
    from flags_reference import render_flag_table_html
    h(render_flag_table_html())
    h('\n')

    # One page per command
    page_num = 1
    for ep_name, ep_data in sorted(REGISTRY.items()):
        for fn_name, op in sorted(ep_data.operations.items()):
            h(build_page(ep_name, fn_name, op, page_num))
            page_num += 1

    h('<div class="signoff">'
      '<div class="signoff-text">From the team at</div>'
      '<div class="signoff-name">DNSFilter</div>'
      '</div>\n\n')
    h('</section>\n')

    return buf.getvalue()


# ── build the guide ────────────────────────────────────────────────────────

GUIDE_SCRIPT = pathlib.Path(__file__).parent / "build_guide.py"
src = GUIDE_SCRIPT.read_text()

body = build_body()
print(f"Body: {len(body):,} chars, {body.count('<h2')} pages")

COVER_FIELDS_NEW = '''COVER_FIELDS = {
    "doc_type": "Command Reference · 2026",
    "eyebrow": "One command, one page — every flag, every response",
    "title": "dnsfcli<br>Command Reference",
    "subtitle": (
        "Complete reference for all 242 dnsfcli operations. "
        "Each page covers one command: what it does, every flag explained, "
        "an example call, and the response you will receive."
    ),
    "byline": [
        ("Updated",     "2026-07-13"),
        ("Commands",    "242 operations across 36 endpoints"),
        ("Audience",    "Developers & Administrators"),
    ],
}'''

src = src.replace("ASSETS = Path(__file__).resolve().parent", f'ASSETS = Path(r"{ASSETS}")')
src = src.replace('OUT_DIR = Path(".")', f'OUT_DIR = Path(r"{OUT_DIR}")')
src = re.sub(r'OUT_BASENAME\s*=\s*"[^"]+"', f'OUT_BASENAME = "{OUT_BASENAME}"', src, count=1)
src = re.sub(r'FORMATS\s*=\s*\[[^\]]+\]', f'FORMATS = {FORMATS!r}', src, count=1)
src = src.replace('COVER = "minimal"', f'COVER = "{COVER}"')
src = re.sub(r'COVER_FIELDS\s*=\s*\{[^}]+?\}',
             COVER_FIELDS_NEW.replace('\\', '\\\\'), src, count=1, flags=re.DOTALL)

body_start = src.index('BODY = """')
body_end   = src.index('"""', body_start + 10) + 3
# Escape backslashes so sequences like a Windows login "DOMAIN\jsmith" in
# captured API responses aren't interpreted as string escapes (\a → bell)
# when the generated module is compiled.
body_lit = body.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
src = src[:body_start] + f'BODY = """\n{body_lit}\n"""' + src[body_end:]
src = src.replace('if __name__ == "__main__":', 'if True:')

# ── Patch 1: white-space:pre-wrap on prompt-body so PDF preserves <br> as
#             actual line breaks (WeasyPrint renders HTML directly).
src = src.replace(
    ".prompt-body {{ font-family: 'Inter','Arial',sans-serif;",
    ".prompt-body {{ white-space: pre-wrap; font-family: 'Inter','Arial',sans-serif;",
)

# ── Patch 2: make html_to_plain convert <br> → \n (not space) and preserve
#             those newlines so Markdown code blocks show one flag per line.
OLD_H2P = (
    'def html_to_plain(html):\n'
    '    text = re.sub(r"<br\\s*/?>", " ", html or "", flags=re.IGNORECASE)\n'
    '    text = re.sub(r"<[^>]+>", "", text)\n'
    '    return re.sub(r"\\s+", " ", text).strip()'
)
NEW_H2P = (
    'def html_to_plain(html):\n'
    '    text = re.sub(r"<br\\s*/?>", "\\n", html or "", flags=re.IGNORECASE)\n'
    '    text = re.sub(r"<[^>]+>", "", text)\n'
    '    # Collapse inline whitespace but keep newlines\n'
    '    text = re.sub(r"[ \\t]+", " ", text)\n'
    '    text = re.sub(r"\\n ", "\\n", text)   # trim leading space per line\n'
    '    return text.strip()'
)
if OLD_H2P in src:
    src = src.replace(OLD_H2P, NEW_H2P)
    print("html_to_plain patched")
else:
    print("WARNING: html_to_plain patch target not found — check indentation")

exec(compile(src, str(GUIDE_SCRIPT), "exec"), {
    "__file__": str(GUIDE_SCRIPT),
    "__name__": "__main__",
})
