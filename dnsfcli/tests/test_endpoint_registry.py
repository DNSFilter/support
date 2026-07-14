"""Unit tests for the endpoint registry -- no network required."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.endpoints import (
    REGISTRY,
    Operation,
    get_operation,
    list_endpoints,
    list_functions,
)

# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

EXPECTED_ENDPOINTS = [
    "agent-local-users",
    "api-keys",
    "application-categories",
    "applications",
    "billing",
    "block-pages",
    "categories",
    "collections",
    "current-user",
    "dictionary",
    "domains",
    "enterprise-connections",
    "invoices",
    "ip-addresses",
    "mac-addresses",
    "metrics",
    "networks",
    "organizations",
    "policies",
    "policy-ips",
    "psa-integrations",
    "scheduled-policies",
    "scheduled-reports",
    "traffic-reports",
    "user-agent-bulk-deletes",
    "user-agent-bulk-updates",
    "user-agent-cleanups",
    "user-agent-csv-exports",
    "user-agent-releases",
    "user-agents",
    "users",
    "v2-agent-local-users",
    "v2-current-user",
    "v2-dictionary",
    "v2-networks",
    "v2-user-agents",
]


class TestRegistryCoverage:
    def test_all_expected_endpoints_present(self):
        registered = set(REGISTRY.keys())
        missing = set(EXPECTED_ENDPOINTS) - registered
        assert not missing, f"Missing endpoints: {sorted(missing)}"

    def test_minimum_operation_count(self):
        total = sum(len(ep.operations) for ep in REGISTRY.values())
        assert total >= 240, f"Only {total} operations registered"

    def test_no_empty_endpoint(self):
        for name, ep in REGISTRY.items():
            assert ep.operations, f"Endpoint '{name}' has no operations"

    @pytest.mark.parametrize("name", EXPECTED_ENDPOINTS)
    def test_endpoint_exists(self, name):
        assert name in REGISTRY, f"'{name}' not in registry"


class TestCrudEndpoints:
    """Endpoints with standard CRUD should have the right operations and methods."""

    @pytest.mark.parametrize("endpoint,expected_ops", [
        ("networks",       {"list", "show", "create", "update", "delete"}),
        ("organizations",  {"list", "show", "create", "update", "delete"}),
        ("policies",       {"list", "show", "create", "update", "delete"}),
        ("block-pages",    {"list", "show", "create", "update", "delete"}),
        ("ip-addresses",   {"list", "show", "create", "update", "delete"}),
        ("mac-addresses",  {"list", "show", "create", "update", "delete"}),
    ])
    def test_crud_operations_present(self, endpoint, expected_ops):
        ops = set(REGISTRY[endpoint].operations.keys())
        missing = expected_ops - ops
        assert not missing, f"'{endpoint}' missing CRUD ops: {missing}"

    @pytest.mark.parametrize("endpoint,op,expected_method", [
        ("networks",       "list",   "GET"),
        ("networks",       "create", "POST"),
        ("networks",       "update", "PATCH"),
        ("networks",       "delete", "DELETE"),
        ("organizations",  "list",   "GET"),
        ("policies",       "create", "POST"),
        ("policies",       "delete", "DELETE"),
    ])
    def test_http_method_correct(self, endpoint, op, expected_method):
        operation = REGISTRY[endpoint].operations[op]
        assert operation.method == expected_method


class TestPathTemplates:
    def test_networks_show_has_id_placeholder(self):
        op = REGISTRY["networks"].operations["show"]
        assert "{id}" in op.path_template

    def test_collections_users_list_has_collection_id(self):
        op = REGISTRY["collections"].operations["users-list"]
        assert "{collection_id}" in op.path_template

    def test_all_path_templates_start_with_slash(self):
        for name, ep in REGISTRY.items():
            for fn, op in ep.operations.items():
                assert op.path_template.startswith("/"), (
                    f"{name}/{fn}: path must start with '/'"
                )

    def test_all_paths_have_version_prefix(self):
        for name, ep in REGISTRY.items():
            for fn, op in ep.operations.items():
                assert op.path_template.startswith(("/v1/", "/v2/")), (
                    f"{name}/{fn}: unexpected path prefix in '{op.path_template}'"
                )

    def test_v2_endpoints_use_v2_prefix(self):
        for name in [k for k in REGISTRY if k.startswith("v2")]:
            for fn, op in REGISTRY[name].operations.items():
                assert op.path_template.startswith("/v2/"), (
                    f"{name}/{fn}: expected /v2/ prefix"
                )


class TestTrafficReports:
    def test_traffic_reports_has_51_plus_operations(self):
        ops = REGISTRY["traffic-reports"].operations
        assert len(ops) >= 51

    def test_all_traffic_report_ops_are_get(self):
        for fn, op in REGISTRY["traffic-reports"].operations.items():
            assert op.method == "GET", f"traffic-reports/{fn} should be GET"

    def test_key_traffic_reports_present(self):
        ops = REGISTRY["traffic-reports"].operations
        for key in ("qps", "query-logs", "total-requests", "total-threats", "top-domains"):
            assert key in ops, f"traffic-reports/{key} missing"


class TestPolicyActions:
    def test_add_and_remove_domain_ops_present(self):
        ops = REGISTRY["policies"].operations
        assert "add-blacklist-domain" in ops
        assert "remove-blacklist-domain" in ops
        assert "add-whitelist-domain" in ops
        assert "remove-whitelist-domain" in ops

    def test_add_and_remove_ops_are_post(self):
        ops = REGISTRY["policies"].operations
        for fn in ("add-blacklist-domain", "remove-blacklist-domain"):
            assert ops[fn].method == "POST"

    def test_bulk_policy_ops_present(self):
        ops = REGISTRY["policies"].operations
        for fn in ("bulk-add-allowlist", "bulk-add-blocklist",
                   "bulk-remove-allowlist", "bulk-remove-blocklist"):
            assert fn in ops


class TestLookupHelpers:
    def test_get_operation_returns_registered(self):
        op = get_operation("networks", "list")
        assert "/v1/networks" in op.path_template

    def test_get_operation_raises_for_unknown_endpoint(self):
        with pytest.raises(ValueError, match="Unknown endpoint"):
            get_operation("nonexistent", "list")

    def test_get_operation_raises_for_unknown_function(self):
        with pytest.raises(ValueError, match="Unknown function"):
            get_operation("networks", "nonexistent_fn")

    def test_list_endpoints_sorted(self):
        eps = list_endpoints()
        assert eps == sorted(eps)

    def test_list_functions_for_known_endpoint(self):
        fns = list_functions("networks")
        assert "list" in fns
        assert "show" in fns
        assert "create" in fns

    def test_list_functions_for_unknown_endpoint_is_empty(self):
        assert list_functions("unknown_endpoint") == []
