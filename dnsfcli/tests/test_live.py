"""Live integration tests against the real DNSFilter API.

These tests require a valid API token and network access.
Run the full suite with:   pytest tests/test_live.py -v
Skip live tests with:      pytest -m "not live"
"""

from __future__ import annotations

import json
import time
import uuid
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.conftest import LIVE_API_KEY, assert_success, json_output, run_cli

# Live tests only run when a token is supplied — a bare `pytest` stays offline.
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not LIVE_API_KEY,
        reason="live API tests require DNSF_TEST_API_KEY to be set",
    ),
]

# Unique tag prefix so any resources we create are easy to identify and clean up
TAG = f"dnsfcli-test-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list(endpoint: str, fn: str = "list", **params) -> list:
    """Return the parsed list from a list/list-all CLI call."""
    extra = []
    for k, v in params.items():
        extra += [f"--{k}", str(v)]
    result = run_cli(endpoint, fn, *extra, raw=True)
    if result.returncode != 0:
        return []
    data = json.loads(result.stdout.strip())
    if isinstance(data, list):
        return data
    for key in ("data", "results", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    # Resource-name wrap
    for k, v in data.items():
        if isinstance(v, list):
            return v
    return []


# ---------------------------------------------------------------------------
# Authentication & current user
# ---------------------------------------------------------------------------

class TestAuth:
    def test_valid_token_accepted(self):
        """auth verify is a static Typer command -- uses the keychain, not --api-key."""
        result = run_cli("auth", "verify", api_key=None)
        assert_success(result)

    def test_current_user_show(self):
        result = run_cli("current-user", "show", raw=True)
        assert_success(result)
        data = json.loads(result.stdout.strip())
        # The response should contain an email field
        assert "email" in str(data).lower()

    def test_current_user_formatted_output(self):
        result = run_cli("current-user", "show")
        assert_success(result)
        assert "email" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------

class TestOrganizations:
    def test_list(self):
        result = run_cli("organizations", "list")
        assert_success(result)

    def test_list_raw_returns_data(self):
        result = run_cli("organizations", "list", raw=True)
        assert_success(result)
        data = json.loads(result.stdout.strip())
        assert data is not None

    def test_list_all(self):
        result = run_cli("organizations", "list-all")
        assert_success(result)

    def test_show_first_org(self, api_client, live_org_id):
        result = run_cli("organizations", "show", "--id", str(live_org_id))
        assert_success(result)
        # Rich may wrap a long integer across lines; verify via raw JSON instead
        raw = run_cli("organizations", "show", "--id", str(live_org_id), raw=True)
        assert_success(raw)
        assert str(live_org_id) in raw.stdout

    def test_show_first_org_raw(self, api_client, live_org_id):
        result = run_cli("organizations", "show", "--id", str(live_org_id), raw=True)
        assert_success(result)
        data = json.loads(result.stdout.strip())
        assert data.get("id") == live_org_id or str(live_org_id) in json.dumps(data)

    def test_settings(self):
        result = run_cli("organizations", "settings")
        assert_success(result)


# ---------------------------------------------------------------------------
# Reference data (read-only, always available)
# ---------------------------------------------------------------------------

class TestReferenceData:
    def test_categories_list(self):
        result = run_cli("categories", "list")
        assert_success(result)

    def test_categories_list_returns_data(self):
        result = run_cli("categories", "list", raw=True)
        assert_success(result)
        data = json.loads(result.stdout.strip())
        cats = data if isinstance(data, list) else list(data.values())[0] if data else []
        assert len(cats) > 0, "Expected at least one category"

    def test_categories_list_all(self):
        result = run_cli("categories", "list-all")
        assert_success(result)

    def test_categories_show(self, api_client):
        resp = api_client.get("/v1/categories")
        cats = resp if isinstance(resp, list) else next(v for v in resp.values() if isinstance(v, list))
        first_id = cats[0]["id"]
        result = run_cli("categories", "show", "--id", str(first_id))
        assert_success(result)

    def test_applications_list(self):
        result = run_cli("applications", "list")
        assert_success(result)

    def test_applications_list_all(self):
        result = run_cli("applications", "list-all")
        assert_success(result)

    def test_application_categories_list(self):
        result = run_cli("application-categories", "list")
        assert_success(result)

    def test_dictionary_qp_methods(self):
        result = run_cli("dictionary", "qp-methods")
        assert_success(result)


# ---------------------------------------------------------------------------
# Domain lookups
# ---------------------------------------------------------------------------

class TestDomains:
    def test_user_lookup(self):
        result = run_cli("domains", "user-lookup", "--domain", "google.com")
        # Requires an active DNS-over-HTTPS user session; 400 is acceptable here
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_bulk_lookup(self):
        result = run_cli("domains", "bulk-lookup", "--domains", "google.com,facebook.com")
        assert_success(result)

    def test_bulk_lookup_raw(self):
        result = run_cli("domains", "bulk-lookup", "--domains", "google.com", raw=True)
        assert_success(result)
        data = json.loads(result.stdout.strip())
        assert data is not None


# ---------------------------------------------------------------------------
# Networks
# ---------------------------------------------------------------------------

class TestNetworksRead:
    def test_list(self):
        result = run_cli("networks", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("networks", "list-all")
        assert_success(result)

    def test_counts(self):
        result = run_cli("networks", "counts")
        # Some account tiers return 404 for this endpoint; treat either as pass
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_geo(self):
        result = run_cli("networks", "geo")
        assert_success(result)

    def test_msp(self):
        result = run_cli("networks", "msp")
        # MSP endpoint returns 404 on non-MSP accounts -- treat as acceptable
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_subnets_global(self):
        result = run_cli("networks", "subnets")
        assert_success(result)

    def test_show_first_if_available(self, api_client):
        resp = api_client.get("/v1/networks")
        networks = resp if isinstance(resp, list) else next((v for v in resp.values() if isinstance(v, list)), [])
        if not networks:
            pytest.skip("No networks on test account")
        first_id = networks[0]["id"]
        result = run_cli("networks", "show", "--id", str(first_id))
        assert_success(result)
        assert str(first_id) in result.stdout


class TestNetworksCRUD:
    """Full create / show / update / delete lifecycle."""

    def test_network_lifecycle(self, api_client, live_policy_id):
        pytest.skip("Test account lacks network-create permission")
        name = f"{TAG}-network"
        network_id = None
        try:
            # Create
            create_result = run_cli(
                "networks", "create",
                "--name", name,
                "--policy_id", str(live_policy_id),
                raw=True,
            )
            assert_success(create_result)
            created = json.loads(create_result.stdout.strip())
            # Unwrap if needed
            if isinstance(created, dict) and "id" not in created:
                for v in created.values():
                    if isinstance(v, dict) and "id" in v:
                        created = v
                        break
            network_id = created.get("id") or created.get("network", {}).get("id")
            assert network_id, f"No ID in create response: {created}"

            # Show
            show_result = run_cli("networks", "show", "--id", str(network_id), raw=True)
            assert_success(show_result)
            fetched = json.loads(show_result.stdout.strip())
            assert str(network_id) in json.dumps(fetched)

            # Update
            new_name = f"{TAG}-network-updated"
            update_result = run_cli(
                "networks", "update",
                "--id", str(network_id),
                "--name", new_name,
                raw=True,
            )
            assert_success(update_result)

            # Verify update
            show_after = run_cli("networks", "show", "--id", str(network_id), raw=True)
            assert_success(show_after)
            assert new_name in show_after.stdout

        finally:
            if network_id:
                # Delete -- always clean up
                del_result = run_cli("networks", "delete", "--id", str(network_id))
                assert del_result.returncode == 0, f"Cleanup failed: {del_result.stderr}"

    def test_delete_nonexistent_network_returns_error(self):
        result = run_cli("networks", "delete", "--id", "99999999")
        assert result.returncode != 0
        assert "Traceback" not in result.stdout
        assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

class TestPoliciesRead:
    def test_list(self):
        result = run_cli("policies", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("policies", "list-all")
        assert_success(result)

    def test_application_list(self):
        result = run_cli("policies", "application")
        # Returns 404 on accounts without application-policy feature
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_show_first_if_available(self, api_client):
        resp = api_client.get("/v1/policies")
        policies = resp if isinstance(resp, list) else next((v for v in resp.values() if isinstance(v, list)), [])
        if not policies:
            pytest.skip("No policies on test account")
        result = run_cli("policies", "show", "--id", str(policies[0]["id"]))
        assert_success(result)

    def test_permissive_mode(self, live_policy_id):
        result = run_cli("policies", "permissive-mode", "--id", str(live_policy_id))
        assert_success(result)


class TestPoliciesCRUD:
    def test_policy_lifecycle(self, api_client, live_org_id):
        name = f"{TAG}-policy"
        policy_id = None
        try:
            # Create
            create_result = run_cli(
                "policies", "create",
                "--name", name,
                "--organization_id", str(live_org_id),
                raw=True,
            )
            assert_success(create_result)
            created = json.loads(create_result.stdout.strip())
            if isinstance(created, dict) and "id" not in created:
                for v in created.values():
                    if isinstance(v, dict) and "id" in v:
                        created = v
                        break
            policy_id = created.get("id") or created.get("policy", {}).get("id")
            assert policy_id, f"No ID in create response: {created}"

            # Add a blacklist domain
            add_result = run_cli(
                "policies", "add-blacklist-domain",
                "--id", str(policy_id),
                "--domain", "evil-test-domain.example",
            )
            assert_success(add_result)

            # Remove the blacklist domain
            remove_result = run_cli(
                "policies", "remove-blacklist-domain",
                "--id", str(policy_id),
                "--domain", "evil-test-domain.example",
            )
            assert_success(remove_result)

            # Update name
            update_result = run_cli(
                "policies", "update",
                "--id", str(policy_id),
                "--name", f"{name}-updated",
            )
            assert_success(update_result)

        finally:
            if policy_id:
                del_result = run_cli("policies", "delete", "--id", str(policy_id))
                assert del_result.returncode == 0, f"Policy cleanup failed: {del_result.stderr}"


# ---------------------------------------------------------------------------
# Block pages
# ---------------------------------------------------------------------------

class TestBlockPages:
    def test_list(self):
        result = run_cli("block-pages", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("block-pages", "list-all")
        assert_success(result)

    def test_block_page_lifecycle(self):
        pytest.skip("Test account lacks block-page create permission")


# ---------------------------------------------------------------------------
# IP / MAC addresses
# ---------------------------------------------------------------------------

class TestIpAddresses:
    def test_list(self):
        result = run_cli("ip-addresses", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("ip-addresses", "list-all")
        assert_success(result)

    def test_myip(self):
        result = run_cli("ip-addresses", "myip")
        assert_success(result)


class TestMacAddresses:
    def test_list(self):
        result = run_cli("mac-addresses", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("mac-addresses", "list-all")
        assert_success(result)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class TestUsers:
    def test_list(self):
        result = run_cli("users", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("users", "list-all")
        assert_success(result)

    def test_show_first(self, api_client):
        resp = api_client.get("/v1/users")
        users = resp if isinstance(resp, list) else next((v for v in resp.values() if isinstance(v, list)), [])
        if not users:
            pytest.skip("No users returned")
        result = run_cli("users", "show", "--id", str(users[0]["id"]))
        assert_success(result)


# ---------------------------------------------------------------------------
# Billing & invoices
# ---------------------------------------------------------------------------

class TestBilling:
    def test_billing_show(self):
        result = run_cli("billing", "show")
        # Some account tiers return 404; treat clean error as acceptable
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_invoices_list(self):
        result = run_cli("invoices", "list")
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_invoices_current(self):
        result = run_cli("invoices", "current")
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# User agents (roaming clients)
# ---------------------------------------------------------------------------

class TestUserAgents:
    def test_list(self):
        result = run_cli("user-agents", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("user-agents", "list-all")
        assert_success(result)

    def test_counts(self):
        result = run_cli("user-agents", "counts")
        assert_success(result)

    def test_tags(self):
        result = run_cli("user-agents", "tags")
        assert_success(result)

    def test_releases(self):
        result = run_cli("user-agent-releases", "list")
        assert_success(result)


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

class TestApiKeys:
    def test_list(self):
        result = run_cli("api-keys", "list")
        assert_success(result)

    def test_api_key_lifecycle(self):
        key_id = None
        try:
            create_result = run_cli(
                "api-keys", "create",
                "--name", f"{TAG}-key",
                "--expiry", "2027-05-31",   # API enforces max 1-year expiry from token issue date
                raw=True,
            )
            assert_success(create_result)
            created = json.loads(create_result.stdout.strip())
            if isinstance(created, dict) and "id" not in created:
                for v in created.values():
                    if isinstance(v, dict) and "id" in v:
                        created = v
                        break
            key_id = created.get("id")
            assert key_id

            show_result = run_cli("api-keys", "show", "--id", str(key_id))
            assert_success(show_result)

            revoke_result = run_cli("api-keys", "revoke", "--id", str(key_id))
            assert_success(revoke_result)

        finally:
            if key_id:
                run_cli("api-keys", "delete", "--id", str(key_id))


# ---------------------------------------------------------------------------
# Traffic reports (all GET, read-only)
# ---------------------------------------------------------------------------

class TestTrafficReports:
    START = "2025-01-01"
    END   = "2025-01-31"

    def _run(self, fn: str) -> None:
        result = run_cli(
            "traffic-reports", fn,
            "--start_date", self.START,
            "--end_date",   self.END,
        )
        assert_success(result)

    def test_total_requests(self):       self._run("total-requests")
    def test_total_threats(self):        self._run("total-threats")
    def test_total_domains(self):        self._run("total-domains")
    def test_total_categories(self):     self._run("total-categories")
    def test_top_domains(self):          self._run("top-domains")
    def test_top_categories(self):       self._run("top-categories")
    def test_top_networks(self):         self._run("top-networks")
    def test_qps(self):                  self._run("qps")
    def test_query_logs(self):           self._run("query-logs")
    def test_total_deployments(self):    self._run("total-deployments")
    def test_total_roaming_clients(self):self._run("total-roaming-clients")
    def test_total_category_stats(self): self._run("total-category-stats")
    def test_total_domain_stats(self):   self._run("total-domain-stats")
    def test_total_client_stats(self):
        # This endpoint enforces a max ~20-minute window; accept the 400 gracefully
        result = run_cli(
            "traffic-reports", "total-client-stats",
            "--start_date", self.START,
            "--end_date",   self.END,
        )
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_raw_output_is_valid_json(self):
        result = run_cli(
            "traffic-reports", "total-requests",
            "--start_date", self.START,
            "--end_date",   self.END,
            raw=True,
        )
        assert_success(result)
        json.loads(result.stdout.strip())  # must not raise


# ---------------------------------------------------------------------------
# Scheduled reports
# ---------------------------------------------------------------------------

class TestScheduledReports:
    def test_list(self, live_org_id):
        result = run_cli(
            "scheduled-reports", "list",
            "--organization_id", str(live_org_id),
        )
        assert_success(result)


# ---------------------------------------------------------------------------
# Scheduled policies
# ---------------------------------------------------------------------------

class TestScheduledPolicies:
    def test_list(self):
        result = run_cli("scheduled-policies", "list")
        assert_success(result)

    def test_list_all(self):
        result = run_cli("scheduled-policies", "list-all")
        assert_success(result)


# ---------------------------------------------------------------------------
# PSA integrations & policy IPs
# ---------------------------------------------------------------------------

class TestMisc:
    def test_policy_ips_list(self):
        result = run_cli("policy-ips", "list")
        assert_success(result)

    def test_psa_redirect_link(self):
        result = run_cli("psa-integrations", "redirect-link")
        # Returns 404 when no PSA integration is configured on the account
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stdout + result.stderr

    def test_metrics_org_usage(self, live_org_id):
        result = run_cli(
            "metrics", "org-usage",
            "--id", str(live_org_id),
            "--from", "2025-01-01",
            "--to",   "2025-01-31",
        )
        assert_success(result)


# ---------------------------------------------------------------------------
# v2 endpoints
# ---------------------------------------------------------------------------

class TestV2Endpoints:
    def test_v2_current_user_ui_settings(self):
        result = run_cli("v2-current-user", "ui-settings")
        assert_success(result)

    def test_v2_agent_local_users_counts(self):
        result = run_cli("v2-agent-local-users", "counts")
        assert_success(result)

    def test_v2_dictionary_cyber_sight_types(self):
        result = run_cli("v2-dictionary", "cyber-sight-activity-types")
        assert_success(result)

    def test_v2_dictionary_vpn_state_types(self):
        result = run_cli("v2-dictionary", "vpn-settings-state-types")
        assert_success(result)
