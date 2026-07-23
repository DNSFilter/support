"""Endpoint registry: maps (endpoint, function) -> HTTP method + path template.

All schemas are sourced from the DNSFilter OpenAPI spec (2026-05-27).
Every field returned by the spec's requestBody schemas is modelled here,
including arrays, booleans, and enum-constrained strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

HttpMethod = Literal["GET", "POST", "PATCH", "PUT", "DELETE"]


@dataclass(frozen=True)
class Param:
    name: str
    description: str
    required: bool = False
    kind: Literal["path", "query", "body"] = "body"
    type_hint: str = "string"
    top_level: bool = False  # when True and Operation.body_key is set, stays at root of body
    # Params carrying credentials (client_secret, payment_token, new_password)
    # set secret=True so their CLI values are scrubbed from the history log.
    secret: bool = False


@dataclass
class Operation:
    method: HttpMethod
    path_template: str
    description: str
    params: list[Param] = field(default_factory=list)
    uses_id: bool = False
    body_key: str | None = None  # wrap body params under this key before sending
    destructive: bool = False    # True for POST operations that permanently delete resources
    poll_on: str | None = None   # function name to poll when --wait is used (async jobs)


@dataclass
class Endpoint:
    name: str
    description: str
    operations: dict[str, Operation] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shared param helpers
# ---------------------------------------------------------------------------

def _pagination() -> list[Param]:
    return [
        Param("page",     "Page number",    kind="query", type_hint="integer"),
        Param("per_page", "Items per page", kind="query", type_hint="integer"),
    ]

def _id(label: str = "Resource ID") -> Param:
    return Param("id", label, required=True, kind="path", type_hint="integer")

def _uuid_id(label: str = "Resource UUID") -> Param:
    """Path ID param for resources that use UUID strings rather than integers."""
    return Param("id", label, required=True, kind="path", type_hint="string")

def _p(name: str, desc: str, *, req: bool = False,
       kind: str = "body", hint: str = "string", tl: bool = False,
       secret: bool = False) -> Param:
    return Param(name, desc, required=req, kind=kind, type_hint=hint, top_level=tl, secret=secret)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Full endpoint registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, Endpoint] = {}


# ------ agent-local-users ---------------------------------------------------

REGISTRY["agent-local-users"] = Endpoint(
    name="agent-local-users",
    description="Agent local user management",
    operations={
        "list":               Operation("GET",    "/v1/agent_local_users",          "List agent local users",        _pagination()),
        "list-all":           Operation("GET",    "/v1/agent_local_users/all",       "List all agent local users"),
        "show":               Operation("GET",    "/v1/agent_local_users/{id}",      "Show an agent local user",      [_id()], uses_id=True),
        "update":             Operation("PATCH",  "/v1/agent_local_users/{id}",      "Update an agent local user",
                                        [_id(),
                                         _p("friendly_name",       "Display name"),
                                         _p("policy_id",           "Policy ID",           hint="integer"),
                                         _p("scheduled_policy_id", "Scheduled policy ID", hint="integer"),
                                         _p("block_page_id",       "Block page ID",       hint="integer")],
                                        uses_id=True, body_key="agent_local_user"),
        "delete":             Operation("DELETE", "/v1/agent_local_users/{id}",      "Delete an agent local user",    [_id()], uses_id=True),
        "bulk-delete":        Operation("POST",   "/v1/agent_local_users_bulk_delete",       "Bulk delete agent local users",
                                        [_p("ids",         "Array of IDs to delete",   req=True, hint="array"),
                                         _p("exclude_ids", "Array of IDs to exclude",           hint="array")],
                                        destructive=True, poll_on="bulk-delete-show"),
        "bulk-delete-show":   Operation("GET",    "/v1/agent_local_users_bulk_delete/{id}",  "Show a bulk-delete job",        [_id()], uses_id=True),
        "bulk-delete-counts": Operation("GET",    "/v1/agent_local_users_bulk_delete/counts", "Count agent local users matching bulk-delete criteria"),
    },
)

# ------ api-keys ------------------------------------------------------------

REGISTRY["api-keys"] = Endpoint(
    name="api-keys",
    description="API key management",
    operations={
        "list":   Operation("GET",    "/v1/api_keys",             "List API keys",    _pagination()),
        "create": Operation("POST",   "/v1/api_keys",             "Create an API key",
                            [_p("name",   "Key name",        req=True),
                             _p("expiry", "Expiry date (YYYY-MM-DD)")]),
        "show":   Operation("GET",    "/v1/api_keys/{id}",        "Show an API key",  [_id()], uses_id=True),
        "delete": Operation("DELETE", "/v1/api_keys/{id}",        "Delete an API key",[_id()], uses_id=True),
        "revoke": Operation("POST",   "/v1/api_keys/{id}/revoke", "Revoke an API key",[_id()], uses_id=True),
    },
)

# ------ application-categories ----------------------------------------------

REGISTRY["application-categories"] = Endpoint(
    name="application-categories",
    description="Application category reference",
    operations={
        "list": Operation("GET", "/v1/application_categories",      "List application categories", _pagination()),
        "show": Operation("GET", "/v1/application_categories/{id}", "Show an application category", [_id()], uses_id=True),
    },
)

# ------ applications --------------------------------------------------------

REGISTRY["applications"] = Endpoint(
    name="applications",
    description="Application catalog",
    operations={
        "list":     Operation("GET", "/v1/applications",      "List applications"),
        "list-all": Operation("GET", "/v1/applications/all",  "List all applications"),
        "show":     Operation("GET", "/v1/applications/{id}", "Show an application", [_id()], uses_id=True),
    },
)

# ------ billing -------------------------------------------------------------

REGISTRY["billing"] = Endpoint(
    name="billing",
    description="Billing and subscription",
    operations={
        "show":    Operation("GET",   "/v1/billing", "Show billing details. Returns {} if no billing record is configured.",
                     [Param("organization_id", "Organization ID — injected automatically from stored org-id if omitted", required=True, kind="query", type_hint="integer")]),
        "create":  Operation("POST",  "/v1/billing", "Create billing record",
                             [_p("organization_id", "Organization ID", req=True, hint="integer"),
                              _p("payment_token",   "Payment token",   req=True, secret=True)]),
        "get-address":    Operation("GET",   "/v1/billing/address/{organization_id}",
                                    "Get billing address",
                                    [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer")],
                                    uses_id=True),
        "update-address": Operation("PATCH", "/v1/billing/address/{organization_id}",
                                    "Update billing address",
                                    [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer"),
                                     _p("first_name",  "First name"),
                                     _p("last_name",   "Last name"),
                                     _p("email",       "Email address"),
                                     _p("company",     "Company name"),
                                     _p("phone",       "Phone number"),
                                     _p("line1",       "Address line 1"),
                                     _p("line2",       "Address line 2"),
                                     _p("line3",       "Address line 3"),
                                     _p("city",        "City"),
                                     _p("state",       "State name"),
                                     _p("state_code",  "State code (e.g. CO)"),
                                     _p("zip",         "ZIP / postal code"),
                                     _p("country",     "Country")],
                                    uses_id=True),
    },
)

# ------ block-pages ---------------------------------------------------------

_block_page_body = [
    _p("name",            "Page name",                req=True),
    _p("organization_id", "Organization ID",          hint="integer"),
    _p("block_org_name",  "Organization name to display on block page"),
    _p("block_email_addr","Contact email shown on block page"),
    _p("block_logo_uuid", "UUID of logo to display"),
]

REGISTRY["block-pages"] = Endpoint(
    name="block-pages",
    description="Custom block page configuration",
    operations={
        "list":     Operation("GET",    "/v1/block_pages",        "List block pages",   _pagination()),
        "list-all": Operation("GET",    "/v1/block_pages/all",    "List all block pages"),
        "show":     Operation("GET",    "/v1/block_pages/{id}",   "Show a block page",  [_id()], uses_id=True),
        "create":   Operation("POST",   "/v1/block_pages",        "Create a block page",_block_page_body),
        "update":   Operation("PATCH",  "/v1/block_pages/{id}",   "Update a block page",[_id(), *_block_page_body], uses_id=True),
        "delete":   Operation("DELETE", "/v1/block_pages/{id}",   "Delete a block page",[_id()], uses_id=True),
    },
)

# ------ categories ----------------------------------------------------------

REGISTRY["categories"] = Endpoint(
    name="categories",
    description="DNS filtering category reference",
    operations={
        "list":     Operation("GET", "/v1/categories",      "List categories"),
        "list-all": Operation("GET", "/v1/categories/all",  "List all categories"),
        "show":     Operation("GET", "/v1/categories/{id}", "Show a category", [_id()], uses_id=True),
    },
)

# ------ collections ---------------------------------------------------------

REGISTRY["collections"] = Endpoint(
    name="collections",
    description="Collection user membership",
    operations={
        "users-list":   Operation("GET",    "/v1/collections/{collection_id}/users",
                                  "List users in a collection",
                                  [Param("collection_id", "Collection ID", required=True, kind="path", type_hint="integer"),
                                   *_pagination()], uses_id=True),
        "users-add":    Operation("POST",   "/v1/collections/{collection_id}/users",
                                  "Add a user to a collection",
                                  [Param("collection_id", "Collection ID", required=True, kind="path", type_hint="integer"),
                                   _p("id", "User ID", req=True, hint="integer")], uses_id=True),
        "users-show":   Operation("GET",    "/v1/collections/{collection_id}/users/{id}",
                                  "Show a collection user",
                                  [Param("collection_id", "Collection ID", required=True, kind="path", type_hint="integer"),
                                   _id("User ID")], uses_id=True),
        "users-remove": Operation("DELETE", "/v1/collections/{collection_id}/users/{id}",
                                  "Remove a user from a collection",
                                  [Param("collection_id", "Collection ID", required=True, kind="path", type_hint="integer"),
                                   _id("User ID")], uses_id=True),
    },
)

# ------ current-user --------------------------------------------------------

REGISTRY["current-user"] = Endpoint(
    name="current-user",
    description="Authenticated user profile",
    operations={
        "show":   Operation("GET",   "/v1/current_user", "Show current user"),
        "update": Operation("PATCH", "/v1/current_user", "Update current user",
                            [_p("first_name", "First name"),
                             _p("last_name",  "Last name"),
                             _p("phone",      "Phone number")],
                            body_key="user"),
    },
)

# ------ dictionary ----------------------------------------------------------

REGISTRY["dictionary"] = Endpoint(
    name="dictionary",
    description="API dictionary / reference data",
    operations={
        "qp-methods": Operation("GET", "/v1/dictionary/qp_methods", "List QP method types"),
    },
)


# ------ domains -------------------------------------------------------------

REGISTRY["domains"] = Endpoint(
    name="domains",
    description="Domain lookup and classification",
    operations={
        "bulk-lookup":    Operation("GET",  "/v1/domains/bulk_lookup",    "Classify multiple FQDNs in a single request.",
                                    [_p("fqdns", "Comma-separated list of FQDNs to classify", req=True, kind="query")]),
        "suggest-threat": Operation("POST", "/v1/domains/suggest_threat", "Suggest a domain for threat-intel review.",
                                    [_p("fqdn",       "Fully-qualified domain name to flag",          req=True, kind="query"),
                                     _p("notes",      "Reason or notes for the threat suggestion",    req=True, kind="query"),
                                     _p("categories", "Comma-separated category IDs (optional)",      kind="query")]),
        "user-lookup":    Operation("GET",  "/v1/domains/user_lookup",    "Gets all domains associated with a particular FQDN.",
                                    [_p("fqdn", "Fully-qualified domain name to look up", req=False, kind="query")]),
    },
)

# ------ enterprise-connections ----------------------------------------------

_ec_body = [
    _p("client_id",             "OAuth client ID"),
    _p("client_secret",         "OAuth client secret", secret=True),
    _p("discovery_url",         "OIDC discovery URL"),
    _p("organization_id",       "Organization ID",          hint="integer"),
    _p("default_organization_id","Default organization ID", hint="integer"),
    _p("strategy",              "Connection strategy (e.g. oidc, saml)"),
    _p("display_name",          "Display name"),
    _p("role_default",          "Default role for new users"),
    _p("role_map",              "JSON array of role mapping rules", hint="array"),
    _p("idp",                   "Identity provider identifier"),
    _p("authorized_domains",    "Authorized email domains",  hint="array"),
]

REGISTRY["enterprise-connections"] = Endpoint(
    name="enterprise-connections",
    description="Enterprise SSO connection management",
    operations={
        "list":   Operation("GET",    "/v1/enterprise_connections",      "List enterprise connections",
                                      [*_pagination(), Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "list-all": Operation("GET",  "/v1/enterprise_connections/all",  "List all enterprise connections -- NOTE: endpoint may not exist; use list"),
        "show":   Operation("GET",    "/v1/enterprise_connections/{id}", "Show an enterprise connection", [_id()], uses_id=True),
        "create": Operation("POST",   "/v1/enterprise_connections",      "Create an enterprise connection", _ec_body),
        "update": Operation("PATCH",  "/v1/enterprise_connections/{id}", "Update an enterprise connection.",
                           [_id(),
                            _p("organization_id",         "Organization ID",              hint="integer"),
                            _p("default_organization_id", "Default organization ID",      hint="integer"),
                            _p("display_name",            "Connection display name"),
                            _p("role_default",            "Default role for new users"),
                            _p("role_map",                "JSON array of role mapping rules", hint="array"),
                            _p("idp",                     "Identity provider identifier"),
                            _p("authorized_domains",      "Authorized email domains",     hint="array")], uses_id=True),
        "delete": Operation("DELETE", "/v1/enterprise_connections/{id}", "Delete an enterprise connection", [_id()], uses_id=True),
    },
)

# ------ invoices ------------------------------------------------------------

REGISTRY["invoices"] = Endpoint(
    name="invoices",
    description="Invoice history",
    operations={
        "list":    Operation("GET", "/v1/invoices",         "List invoices",
                    [*_pagination(), Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "current": Operation("GET", "/v1/invoices/current", "Show current invoice",
                    [Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "show":    Operation("GET", "/v1/invoices/{id}",    "Show an invoice",  [_id()], uses_id=True),
    },
)

# ------ ip-addresses --------------------------------------------------------
# NOTE: the API field is 'address', not 'ip_address'

REGISTRY["ip-addresses"] = Endpoint(
    name="ip-addresses",
    description="IP address management",
    operations={
        "list":     Operation("GET",    "/v1/ip_addresses",        "List IP addresses",    _pagination()),
        "list-all": Operation("GET",    "/v1/ip_addresses/all",    "List all IP addresses"),
        "myip":     Operation("GET",    "/v1/ip_addresses/myip",   "Show caller's IP address"),
        "verify":   Operation("GET",    "/v1/ip_addresses/verify", "Verify whether an IP address is registered.",
                              [_p("address", "IP address to verify", req=True, kind="query")]),
        "show":     Operation("GET",    "/v1/ip_addresses/{id}",   "Show an IP address",   [_id()], uses_id=True),
        "create":   Operation("POST",   "/v1/ip_addresses",        "Add an IP address",
                              [_p("address",          "IP address or CIDR",    req=True),
                               _p("organization_id",  "Organization ID",       req=True, hint="integer"),
                               _p("network_id",       "Network ID",            req=True, hint="integer"),
                               _p("dynamic_hostname", "Dynamic DNS hostname")]),
        "update":   Operation("PATCH",  "/v1/ip_addresses/{id}",   "Update an IP address",
                              [_id(),
                               _p("address",          "IP address or CIDR",  req=True),
                               _p("organization_id",  "Organization ID",  hint="integer"),
                               _p("network_id",       "Network ID",       hint="integer"),
                               _p("dynamic_hostname", "Dynamic DNS hostname")], uses_id=True),
        "delete":   Operation("DELETE", "/v1/ip_addresses/{id}",   "Delete an IP address", [_id()], uses_id=True),
    },
)

# ------ mac-addresses -------------------------------------------------------
# NOTE: the API field is 'address', not 'mac_address'

REGISTRY["mac-addresses"] = Endpoint(
    name="mac-addresses",
    description="MAC address management",
    operations={
        "list":     Operation("GET",    "/v1/mac_addresses",        "List MAC addresses",    _pagination()),
        "list-all": Operation("GET",    "/v1/mac_addresses/all",    "List all MAC addresses"),
        "show":     Operation("GET",    "/v1/mac_addresses/{id}",   "Show a MAC address",    [_id()], uses_id=True),
        "create":   Operation("POST",   "/v1/mac_addresses",        "Add a MAC address",
                              [_p("organization_id",  "Organization ID",       req=True, hint="integer"),
                               _p("address",          "MAC address"),
                               _p("filter_value",     "Filter / display label"),
                               _p("policy_id",        "Policy ID",             hint="integer"),
                               _p("scheduled_policy_id","Scheduled policy ID", hint="integer"),
                               _p("block_page_id",    "Block page ID",         hint="integer")]),
        "update":   Operation("PATCH",  "/v1/mac_addresses/{id}",   "Update a MAC address",
                              [_id(),
                               _p("organization_id",  "Organization ID",       hint="integer"),
                               _p("address",          "MAC address"),
                               _p("filter_value",     "Filter / display label"),
                               _p("policy_id",        "Policy ID",             hint="integer"),
                               _p("scheduled_policy_id","Scheduled policy ID", hint="integer"),
                               _p("block_page_id",    "Block page ID",         hint="integer")], uses_id=True),
        "delete":   Operation("DELETE", "/v1/mac_addresses/{id}",   "Delete a MAC address",  [_id()], uses_id=True),
    },
)

# ------ metrics -------------------------------------------------------------

REGISTRY["metrics"] = Endpoint(
    name="metrics",
    description="Organization usage metrics",
    operations={
        "org-usage":          Operation("GET", "/v1/metrics/organization_usage/{id}",
                                        "Organization usage metrics",
                                        [_id("Organization ID"),
                                         Param("from", "Start date (YYYY-MM-DD)", required=True, kind="query"),
                                         Param("to",   "End date (YYYY-MM-DD)",   required=True, kind="query")], uses_id=True),
        "org-usage-detailed": Operation("GET", "/v1/metrics/organization_usage_detailed/{id}",
                                        "Detailed organization usage metrics",
                                        [_id("Organization ID"),
                                         Param("from", "Start date (YYYY-MM-DD)", required=True, kind="query"),
                                         Param("to",   "End date (YYYY-MM-DD)",   required=True, kind="query")], uses_id=True),
    },
)

# ------ networks ------------------------------------------------------------
# NOTE: networks use 'policy_ids' (array) not a single 'policy_id'
#       Subnets use 'from' and 'to' IP range, not 'cidr'

_network_body = [
    _p("name",                    "Network name",                  req=True),
    _p("organization_id",         "Organization ID",               req=True, hint="integer"),
    _p("block_page_id",           "Block page ID",                 hint="integer"),
    _p("policy_ids",              "Array of policy IDs",           hint="array"),
    _p("external_id",             "External / third-party ID"),
    _p("is_legacy_vpn_active",    "Enable legacy VPN mode",        hint="boolean"),
    _p("physical_address",        "Physical location address"),
    _p("ip_addresses_attributes", "JSON array of IP address objects", hint="array"),
    _p("local_domains",           "Array of local domain names",   hint="array"),
    _p("local_resolvers",         "Array of local DNS resolver IPs", hint="array"),
]

_subnet_body_create = [
    _p("name",               "Subnet name",         req=True),
    _p("from",               "Start IP address",    req=True),
    _p("to",                 "End IP address",      req=True),
    _p("policy_id",          "Policy ID",           hint="integer"),
    _p("scheduled_policy_id","Scheduled policy ID", hint="integer"),
    _p("block_page_id",      "Block page ID",       hint="integer"),
]

_subnet_body_update = [
    _p("name",               "Subnet name",         req=True),
    _p("from",               "Start IP address",    req=True),
    _p("to",                 "End IP address",      req=True),
    _p("policy_id",          "Policy ID",           hint="integer"),
    _p("scheduled_policy_id","Scheduled policy ID", hint="integer"),
    _p("block_page_id",      "Block page ID",       hint="integer"),
]

REGISTRY["networks"] = Endpoint(
    name="networks",
    description="Network management",
    operations={
        "list":              Operation("GET",    "/v1/networks",                      "List networks",
                                       [*_pagination(), _p("organization_id", "Filter by org", kind="query", hint="integer")]),
        "list-all":          Operation("GET",    "/v1/networks/all",                  "List all networks"),
        "counts":            Operation("GET",    "/v1/networks/counts",               "Network counts",
                                       [Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "geo":               Operation("GET",    "/v1/networks/geo",                  "Network geo information"),
        "lookup":            Operation("GET",    "/v1/networks/lookup",               "Lookup a network",
                                       [_p("requesting_ip_address", "IP address to look up", req=True, kind="query")]),
        "msp":               Operation("GET",    "/v1/networks/msp",                  "List MSP networks",
                                       [*_pagination(), Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "msp-all":           Operation("GET",    "/v1/networks/msp/all",              "List all MSP networks",
                                       [Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "subnets":           Operation("GET",    "/v1/networks/subnets",              "List all subnets"),
        "show":              Operation("GET",    "/v1/networks/{id}",                 "Show a network",          [_id()], uses_id=True),
        "create":            Operation("POST",   "/v1/networks",                      "Create a network",        _network_body),
        "update":            Operation("PATCH",  "/v1/networks/{id}",                 "Update a network",        [_id(), *_network_body], uses_id=True),
        "delete":            Operation("DELETE", "/v1/networks/{id}",                 "Delete a network",        [_id()], uses_id=True),
        "bulk-create":       Operation("POST",   "/v1/networks/bulk_create",          "Bulk create networks",
                                       poll_on="bulk-create-show"),
        "bulk-create-show":  Operation("GET",    "/v1/networks/bulk_create/{id}",     "Show a bulk-create job",  [_id()], uses_id=True),
        "bulk-update":       Operation("POST",   "/v1/networks/bulk_update",          "Bulk update networks",
                                       [_p("ids",                  "Comma-separated network IDs", req=True),
                                        _p("organization_id",      "Organization ID",             hint="integer"),
                                        _p("policy_id",            "Policy ID",                   hint="integer"),
                                        _p("scheduled_policy_id",  "Scheduled policy ID",         hint="integer"),
                                        _p("block_page_id",        "Block page ID",               hint="integer"),
                                        _p("is_legacy_vpn_active", "Enable legacy VPN",           hint="boolean")],
                                       poll_on="bulk-update-show"),
        "bulk-update-show":  Operation("GET",    "/v1/networks/bulk_update/{id}",     "Show a bulk-update job",  [_id()], uses_id=True),
        "bulk-destroy":      Operation("DELETE", "/v1/networks/bulk_destroy",         "Bulk delete networks.",
                                       [_p("ids",           "Comma-separated network IDs, or the keyword 'all'", req=True),
                                        _p("organization_id","Organization ID (required when ids='all')", hint="integer")],
                                       poll_on="bulk-destroy-show"),
        "bulk-destroy-show": Operation("GET",    "/v1/networks/bulk_destroy/{id}",    "Show a bulk-destroy job", [_id()], uses_id=True),
        "lan-ips":           Operation("GET",    "/v1/networks/{id}/lan_ips",         "List LAN IPs for a network", [_id("Network ID")], uses_id=True),
        "lan-ip-show":       Operation("GET",    "/v1/networks/{id}/lan_ips/{lan_ip_id}", "Show a LAN IP",
                                       [_id("Network ID"), Param("lan_ip_id", "LAN IP ID", required=True, kind="path", type_hint="integer")], uses_id=True),
        "lan-ip-update":     Operation("PATCH",  "/v1/networks/{id}/lan_ips/{lan_ip_id}", "Update a LAN IP",
                                       [_id("Network ID"), Param("lan_ip_id", "LAN IP ID", required=True, kind="path", type_hint="integer"),
                                        _p("name", "LAN IP name")], uses_id=True),
        "secret-key-create": Operation("POST",   "/v1/networks/{id}/secret_key",     "Create network secret key", [_id("Network ID")], uses_id=True),
        "secret-key-update": Operation("PATCH",  "/v1/networks/{id}/secret_key",     "Update network secret key", [_id("Network ID")], uses_id=True),
        "secret-key-delete": Operation("DELETE", "/v1/networks/{id}/secret_key",     "Delete network secret key", [_id("Network ID")], uses_id=True),
        "subnets-list":      Operation("GET",    "/v1/networks/{id}/subnets",         "List subnets for a network", [_id("Network ID"), *_pagination()], uses_id=True),
        "subnets-create":    Operation("POST",   "/v1/networks/{id}/subnets",         "Add a subnet to a network", [_id("Network ID"), *_subnet_body_create], uses_id=True),
        "subnets-show":      Operation("GET",    "/v1/networks/{id}/subnets/{subnet_id}", "Show a subnet",
                                       [_id("Network ID"), Param("subnet_id", "Subnet ID", required=True, kind="path", type_hint="integer")], uses_id=True),
        "subnets-update":    Operation("PATCH",  "/v1/networks/{id}/subnets/{subnet_id}", "Update a subnet",
                                       [_id("Network ID"), Param("subnet_id", "Subnet ID", required=True, kind="path", type_hint="integer"),
                                        *_subnet_body_update], uses_id=True),
        "subnets-delete":    Operation("DELETE", "/v1/networks/{id}/subnets/{subnet_id}", "Delete a subnet",
                                       [_id("Network ID"), Param("subnet_id", "Subnet ID", required=True, kind="path", type_hint="integer")], uses_id=True),
    },
)

# ------ organizations -------------------------------------------------------

_org_body_fields = [
    _p("billing_contact_name",      "Billing contact name"),
    _p("billing_contact_phone",     "Billing contact phone"),
    _p("billing_contact_email",     "Billing contact email"),
    _p("address",                   "Physical address"),
    _p("managed_by_msp_id",         "Managing MSP ID",                  hint="integer"),
    _p("show_pii_rc_hostnames",     "Show PII roaming client hostnames", hint="boolean"),
    _p("unique_id",                 "External unique identifier"),
    _p("sku",                       "SKU / plan code"),
    _p("quantity",                  "Seat quantity",                    hint="integer"),
    _p("gdpr",                      "Enable GDPR mode",                 hint="boolean"),
    _p("privacy_mode",              "Privacy mode (standard / strict)"),
    _p("enable_cybersight",         "Enable CyberSight",                hint="boolean"),
    _p("vpn_settings_organization_attributes", "VPN settings JSON object", hint="object"),
]

_org_body_create = [_p("name", "Organization name", req=True), *_org_body_fields]
_org_body_update = [_p("name", "Organization name"),           *_org_body_fields]

REGISTRY["organizations"] = Endpoint(
    name="organizations",
    description="Organization management",
    operations={
        "list":               Operation("GET",   "/v1/organizations",                   "List organizations",    _pagination()),
        "list-all":           Operation("GET",   "/v1/organizations/all",               "List all organizations"),
        "settings":           Operation("GET",   "/v1/organizations/settings",          "Show organization settings"),
        "bulk-update":        Operation("PATCH", "/v1/organizations/bulk_update",       "Bulk update organizations",
                                        [_p("organization_ids",     "Array of org IDs to update", req=True, hint="array"),
                                         _p("msp_id",               "MSP ID",                          hint="integer"),
                                         _p("exclude_organization_ids", "Array of org IDs to exclude", hint="array"),
                                         _p("vpn_settings_state_type_id", "VPN state type ID",         hint="integer"),
                                         _p("gdpr",                 "Enable GDPR",                     hint="boolean"),
                                         _p("send_uninstall_notifications_to_admin_users", "Send uninstall notifications", hint="boolean"),
                                         _p("show_pii_rc_hostnames","Show PII hostnames",              hint="boolean"),
                                         _p("user_agent_uninstall_notification", "Uninstall notification", hint="boolean"),
                                         _p("user_agent_uninstall_notification_recipient_emails", "Notification emails", hint="array"),
                                         _p("user_agents_auto_update", "Auto-update agents",           hint="boolean")]),
        "show":               Operation("GET",   "/v1/organizations/{id}",              "Show an organization",  [_id()], uses_id=True),
        "create":             Operation("POST",  "/v1/organizations",                   "Create an organization", _org_body_create),
        "update":             Operation("PATCH", "/v1/organizations/{id}",              "Update an organization", [_id(), *_org_body_update], uses_id=True),
        "delete":             Operation("DELETE","/v1/organizations/{id}",              "Delete an organization", [_id()], uses_id=True),
        "cancel":             Operation("POST",  "/v1/organizations/{id}/cancel",       "Cancel an organization", [_id()], uses_id=True),
        "users-list":         Operation("GET",   "/v1/organizations/{organization_id}/users",
                                        "List users in an organization",
                                        [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer"),
                                         *_pagination()], uses_id=True),
        "users-create":       Operation("POST",  "/v1/organizations/{organization_id}/users",
                                        "Add a user to an organization",
                                        [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer"),
                                         _p("email",       "User email address"),
                                         _p("first_name",  "First name"),
                                         _p("last_name",   "Last name"),
                                         _p("phone",       "Phone number"),
                                         _p("role",        "User role (administrator, read_only, network_administrator, network_support, support)"),
                                         _p("organization_permission_ids", "Array of permission IDs", hint="array"),
                                         _p("is_include_only_list", "Include-only permission list", hint="boolean")], uses_id=True, body_key="user"),
        "users-show":         Operation("GET",   "/v1/organizations/{organization_id}/users/{id}",
                                        "Show an org user",
                                        [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer"),
                                         _id("User ID")], uses_id=True),
        "users-update":       Operation("PATCH", "/v1/organizations/{organization_id}/users/{id}",
                                        "Update an org user",
                                        [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer"),
                                         _id("User ID"),
                                         _p("email",       "Email address"),
                                         _p("first_name",  "First name"),
                                         _p("last_name",   "Last name"),
                                         _p("phone",       "Phone number"),
                                         _p("role",        "User role"),
                                         _p("organization_permission_ids", "Array of permission IDs", hint="array"),
                                         _p("is_include_only_list", "Include-only permission list", hint="boolean")], uses_id=True, body_key="user"),
        "users-delete":       Operation("DELETE","/v1/organizations/{organization_id}/users/{id}",
                                        "Remove a user from an organization",
                                        [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer"),
                                         _id("User ID")], uses_id=True),
        "users-resend-invite": Operation("POST", "/v1/organizations/{organization_id}/users/{id}/resend_invite",
                                          "Resend invite to an org user",
                                          [Param("organization_id", "Organization ID", required=True, kind="path", type_hint="integer"),
                                           _id("User ID")], uses_id=True),
    },
)

# ------ policies ------------------------------------------------------------
# NOTE: organization_id is REQUIRED per the spec.
#       Application actions use 'name' (app name string), NOT application_id.
#       Domain actions take both 'domain' and 'note'; note is optional in practice.

_policy_body = [
    _p("name",                    "Policy name",                    req=True),
    _p("organization_id",         "Organization ID",                req=True, hint="integer"),
    _p("allow_unknown_domains",   "Allow uncategorised domains",    hint="boolean"),
    _p("google_safesearch",       "Force Google SafeSearch",        hint="boolean"),
    _p("bing_safe_search",        "Force Bing SafeSearch",          hint="boolean"),
    _p("duck_duck_go_safe_search","Force DuckDuckGo SafeSearch",    hint="boolean"),
    _p("ecosia_safesearch",       "Force Ecosia SafeSearch",        hint="boolean"),
    _p("yandex_safe_search",      "Force Yandex SafeSearch",        hint="boolean"),
    _p("youtube_restricted",      "Restrict YouTube",               hint="boolean"),
    _p("youtube_restricted_level","YouTube restriction level (strict | none)"),
    _p("interstitial",            "Show interstitial warning page", hint="boolean"),
    _p("allow_list_only",         "Block all except allowlisted domains", hint="boolean"),
    _p("is_global_policy",        "Mark as global policy",          hint="boolean"),
    _p("policy_ip_id",            "Associated policy IP ID",        hint="integer"),
    _p("whitelist_domains",       "Domains to allowlist",           hint="array"),
    _p("blacklist_domains",       "Domains to blocklist",           hint="array"),
    _p("blacklist_categories",    "Category IDs to block",          hint="array"),
    _p("allow_applications",      "Application names to allow",     hint="array"),
    _p("block_applications",      "Application names to block",     hint="array"),
    _p("lock_version",            "Optimistic lock version",        hint="integer"),
    _p("include_relationships",   "Include related objects in response", hint="boolean"),
    _p("append_domains",          "Append to existing domain lists (default: replace)", hint="boolean"),
]

REGISTRY["policies"] = Endpoint(
    name="policies",
    description="DNS filtering policy management",
    operations={
        "list":                      Operation("GET",   "/v1/policies",                     "List policies",    _pagination()),
        "list-all":                  Operation("GET",   "/v1/policies/all",                 "List all policies"),
        "application":               Operation("GET",   "/v1/policies/application",         "List policies with application filtering for a specific application.",
                                               [_p("application_id",  "Application ID",            req=True,  kind="query", hint="integer"),
                                                _p("organization_id", "Organization ID",           req=True,  kind="query", hint="integer"),
                                                _p("name",            "Application name filter",   kind="query"),
                                                _p("policy_ids",      "Filter by policy IDs",      kind="query", hint="array")]),
        "application-update":        Operation("POST",  "/v1/policies/application_update",  "Update application allow/block policy assignments.",
                                               [_p("application_id",  "Application ID",                             req=True, kind="query", hint="integer"),
                                                _p("organization_id", "Organization ID",                            req=True, kind="query", hint="integer"),
                                                _p("allow_policies",  "Array of policy IDs to allow this app on",   req=True, kind="query", hint="array"),
                                                _p("block_policies",  "Array of policy IDs to block this app on",   req=True, kind="query", hint="array")]),
        "show":                      Operation("GET",   "/v1/policies/{id}",                "Show a policy",    [_id()], uses_id=True),
        "create":                    Operation("POST",  "/v1/policies",                     "Create a policy",  _policy_body),
        "update":                    Operation("PATCH", "/v1/policies/{id}",                "Update a policy",  [_id(), *_policy_body], uses_id=True),
        "delete":                    Operation("DELETE","/v1/policies/{id}",                "Delete a policy",  [_id()], uses_id=True),
        "bulk-add-allowlist":        Operation("POST",  "/v1/policies/bulk/add_allowlist_domains",    "Bulk add allowlist domains",
                                               [_p("policy_ids", "Array of policy IDs", req=True, hint="array"),
                                                _p("domains",    "Array of domains",    req=True, hint="array")]),
        "bulk-add-blocklist":        Operation("POST",  "/v1/policies/bulk/add_blocklist_domains",    "Bulk add blocklist domains",
                                               [_p("policy_ids", "Array of policy IDs", req=True, hint="array"),
                                                _p("domains",    "Array of domains",    req=True, hint="array")]),
        "bulk-remove-allowlist":     Operation("POST",  "/v1/policies/bulk/remove_allowlist_domains", "Bulk remove allowlist domains",
                                               [_p("policy_ids", "Array of policy IDs", req=True, hint="array"),
                                                _p("domains",    "Array of domains",    req=True, hint="array")]),
        "bulk-remove-blocklist":     Operation("POST",  "/v1/policies/bulk/remove_blocklist_domains", "Bulk remove blocklist domains",
                                               [_p("policy_ids", "Array of policy IDs", req=True, hint="array"),
                                                _p("domains",    "Array of domains",    req=True, hint="array")]),
        "add-allowed-application":   Operation("POST",  "/v1/policies/{id}/add_allowed_application",
                                               "Allow an application on a policy",
                                               [_id(), _p("name", "Application name", req=True),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "add-blacklist-category":    Operation("POST",  "/v1/policies/{id}/add_blacklist_category",
                                               "Block a category on a policy",
                                               [_id(), _p("category_id", "Category ID", req=True, hint="integer"),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "add-blacklist-domain":      Operation("POST",  "/v1/policies/{id}/add_blacklist_domain",
                                               "Block a domain on a policy",
                                               [_id(), _p("domain", "Domain name", req=True),
                                                _p("note", "Note (reason for blocking)"),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "add-blocked-application":   Operation("POST",  "/v1/policies/{id}/add_blocked_application",
                                               "Block an application on a policy",
                                               [_id(), _p("name", "Application name", req=True),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "add-whitelist-domain":      Operation("POST",  "/v1/policies/{id}/add_whitelist_domain",
                                               "Allowlist a domain on a policy",
                                               [_id(), _p("domain", "Domain name", req=True),
                                                _p("note", "Note (reason for allowing)"),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "permissive-mode":           Operation("GET",   "/v1/policies/{id}/permissive_mode", "Show permissive mode status", [_id()], uses_id=True),
        "set-permissive-mode":       Operation("POST",  "/v1/policies/{id}/permissive_mode", "Enable/disable permissive mode",
                                               [_id(), _p("permissive_mode", "true to enable permissive mode, false to disable", req=True, kind="query", hint="boolean")], uses_id=True),
        "remove-allowed-application":Operation("POST",  "/v1/policies/{id}/remove_allowed_application",
                                               "Remove an allowed application",
                                               [_id(), _p("name", "Application name", req=True),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "remove-blacklist-category": Operation("POST",  "/v1/policies/{id}/remove_blacklist_category",
                                               "Unblock a category",
                                               [_id(), _p("category_id", "Category ID", req=True, hint="integer"),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "remove-blacklist-domain":   Operation("POST",  "/v1/policies/{id}/remove_blacklist_domain",
                                               "Unblock a domain",
                                               [_id(), _p("domain", "Domain name", req=True),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "remove-blocked-application":Operation("POST",  "/v1/policies/{id}/remove_blocked_application",
                                               "Unblock an application",
                                               [_id(), _p("name", "Application name", req=True),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
        "remove-whitelist-domain":   Operation("POST",  "/v1/policies/{id}/remove_whitelist_domain",
                                               "Remove a domain from allowlist",
                                               [_id(), _p("domain", "Domain name", req=True),
                                                _p("include_relationships", "Include relationships", hint="boolean")], uses_id=True),
    },
)

# ------ policy-ips ----------------------------------------------------------

REGISTRY["policy-ips"] = Endpoint(
    name="policy-ips",
    description="Policy IP associations",
    operations={
        "list": Operation("GET", "/v1/policy_ips",      "List policy IPs",  _pagination()),
        "show": Operation("GET", "/v1/policy_ips/{id}", "Show a policy IP", [_id()], uses_id=True),
    },
)

# ------ psa-integrations ----------------------------------------------------

REGISTRY["psa-integrations"] = Endpoint(
    name="psa-integrations",
    description="PSA integration links",
    operations={
        "redirect-link": Operation("GET", "/v1/psa_integrations/redirect_link", "Get PSA integration redirect link"),
    },
)

# ------ scheduled-policies --------------------------------------------------
# NOTE: uses 'policy_ids' (array) and 'timezone', not single 'policy_id'

REGISTRY["scheduled-policies"] = Endpoint(
    name="scheduled-policies",
    description="Scheduled policy management",
    operations={
        "list":     Operation("GET",    "/v1/scheduled_policies",      "List scheduled policies",    _pagination()),
        "list-all": Operation("GET",    "/v1/scheduled_policies/all",  "List all scheduled policies"),
        "show":     Operation("GET",    "/v1/scheduled_policies/{id}", "Show a scheduled policy",    [_id()], uses_id=True),
        "create":   Operation("POST",   "/v1/scheduled_policies",      "Create a scheduled policy",
                              [_p("name",            "Policy name",         req=True),
                               _p("organization_id", "Organization ID",     hint="integer"),
                               _p("policy_ids",      "Array of policy IDs", hint="array"),
                               _p("timezone",        "IANA timezone string (e.g. America/Denver)")]),
        "update":   Operation("PATCH",  "/v1/scheduled_policies/{id}", "Update a scheduled policy",
                              [_id(),
                               _p("name",            "Policy name"),
                               _p("organization_id", "Organization ID",     hint="integer"),
                               _p("policy_ids",      "Array of policy IDs", hint="array"),
                               _p("timezone",        "IANA timezone string")], uses_id=True),
        "delete":   Operation("DELETE", "/v1/scheduled_policies/{id}", "Delete a scheduled policy",  [_id()], uses_id=True),
    },
)

# ------ scheduled-reports ---------------------------------------------------

_sched_report_body = [
    _p("organization_id",              "Organization ID",                        hint="integer"),
    _p("frequency",                    "Frequency (daily | weekly | monthly)"),
    _p("day_of_week",                  "Day of week for weekly reports (0=Sunday … 6=Saturday)"),
    _p("include_threat_summary",       "Include threat summary section",         hint="boolean"),
    _p("include_content_category_summary", "Include category summary section",   hint="boolean"),
    _p("content_categories_show_count","Number of categories to show"),
    _p("send_to_dashboard_users",      "Send to all dashboard users",            hint="boolean"),
    _p("scheduled_report_recipients",  "Array of recipient objects (JSON)",      hint="array"),
    _p("selected_sub_orgs",            "Array of sub-org IDs to include",        hint="array"),
]

REGISTRY["scheduled-reports"] = Endpoint(
    name="scheduled-reports",
    description="Scheduled report management",
    operations={
        "list":           Operation("GET",   "/v1/scheduled_reports",          "List scheduled reports",
                    [*_pagination(), Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "show":           Operation("GET",   "/v1/scheduled_reports/{id}",     "Show a scheduled report",   [_id()], uses_id=True),
        "create":         Operation("POST",  "/v1/scheduled_reports",          "Create a scheduled report", _sched_report_body),
        "update":         Operation("PATCH", "/v1/scheduled_reports/{id}",     "Update a scheduled report", [_id(), *_sched_report_body], uses_id=True),
        "delete":         Operation("DELETE","/v1/scheduled_reports/{id}",     "Delete a scheduled report", [_id()], uses_id=True),
        "preview-create": Operation("POST",  "/v1/scheduled_report_previews",  "Create a report preview",
                                    [_p("organization_id",                 "Organization ID",     hint="integer"),
                                     _p("include_threat_summary",          "Include threat summary", hint="boolean"),
                                     _p("include_content_category_summary","Include category summary", hint="boolean"),
                                     _p("content_categories_show_count",   "Categories to show")],
                                    poll_on="preview-show"),
        "preview-show":   Operation("GET",   "/v1/scheduled_report_previews/{id}", "Show a report preview", [_id()], uses_id=True),
    },
)

# ------ traffic-reports (51 GET-only endpoints) -----------------------------

_tr_common = [
    _p("start_date",       "Start date (YYYY-MM-DD or ISO 8601)", req=True,  kind="query"),
    _p("end_date",         "End date (YYYY-MM-DD or ISO 8601)",   req=True,  kind="query"),
    _p("organization_id",  "Filter by organization ID",           kind="query", hint="integer"),
    _p("network_id",       "Filter by network ID",                kind="query", hint="integer"),
    _p("limit",            "Maximum number of results",           kind="query", hint="integer"),
    _p("page",             "Page number",                         kind="query", hint="integer"),
    _p("per_page",         "Items per page",                      kind="query", hint="integer"),
]

# Real-time QPS and client-stats endpoints use from/to (ISO 8601 datetime) instead
# of start_date/end_date, and enforce a max 20-minute window.
_tr_realtime = [
    _p("from",             "Start datetime ISO 8601 (window max 20 min)", req=True, kind="query"),
    _p("to",               "End datetime ISO 8601 (window max 20 min)",   req=True, kind="query"),
    _p("organization_id",  "Filter by organization ID",                   kind="query", hint="integer"),
]

_TR_REALTIME_NAMES = {
    "qps-active-agents", "qps-active-collections",
    "qps-active-organizations", "qps-active-users",
    "total-client-stats",
}

_TRAFFIC_REPORT_PATHS: list[tuple[str, str, str]] = [
    ("qps",                               "/v1/traffic_reports/qps",                               "Queries per second"),
    ("qps-active-agents",                 "/v1/traffic_reports/qps_active_agents",                 "QPS for active agents"),
    ("qps-active-collections",            "/v1/traffic_reports/qps_active_collections",            "QPS for active collections"),
    ("qps-active-organizations",          "/v1/traffic_reports/qps_active_organizations",          "QPS for active organizations"),
    ("qps-active-users",                  "/v1/traffic_reports/qps_active_users",                  "QPS for active users"),
    ("query-logs",                        "/v1/traffic_reports/query_logs",                        "Query log export"),
    ("top-agents",                        "/v1/traffic_reports/top_agents",                        "Top agents by query volume"),
    ("top-application-categories",        "/v1/traffic_reports/top_application_categories",        "Top application categories"),
    ("top-categories",                    "/v1/traffic_reports/top_categories",                    "Top DNS categories"),
    ("top-collections",                   "/v1/traffic_reports/top_collections",                   "Top collections by query volume"),
    ("top-domains",                       "/v1/traffic_reports/top_domains",                       "Top queried domains"),
    ("top-networks",                      "/v1/traffic_reports/top_networks",                      "Top networks by query volume"),
    ("top-organizations",                 "/v1/traffic_reports/top_organizations",                 "Top organizations by query volume"),
    ("top-organizations-requests",        "/v1/traffic_reports/top_organizations_requests",        "Top organizations by request count"),
    ("top-users",                         "/v1/traffic_reports/top_users",                         "Top users by query volume"),
    ("total-applications-agents-stats",   "/v1/traffic_reports/total_applications_agents_stats",   "Total application stats by agent"),
    ("total-applications-collections-stats", "/v1/traffic_reports/total_applications_collections_stats", "Total application stats by collection"),
    ("total-applications-networks-stats", "/v1/traffic_reports/total_applications_networks_stats", "Total application stats by network"),
    ("total-applications-organizations-stats", "/v1/traffic_reports/total_applications_organizations_stats", "Total application stats by organization"),
    ("total-applications-stats",          "/v1/traffic_reports/total_applications_stats",          "Total application stats"),
    ("total-applications-users-stats",    "/v1/traffic_reports/total_applications_users_stats",    "Total application stats by user"),
    ("total-categories",                  "/v1/traffic_reports/total_categories",                  "Total queries by category"),
    ("total-categories-agents",           "/v1/traffic_reports/total_categories_agents",           "Total category stats by agent"),
    ("total-categories-collections",      "/v1/traffic_reports/total_categories_collections",      "Total category stats by collection"),
    ("total-categories-organizations",    "/v1/traffic_reports/total_categories_organizations",    "Total category stats by organization"),
    ("total-categories-users",            "/v1/traffic_reports/total_categories_users",            "Total category stats by user"),
    ("total-category-stats",              "/v1/traffic_reports/total_category_stats",              "Total category stats"),
    ("total-client-stats",                "/v1/traffic_reports/total_client_stats",                "Total client (agent) stats"),
    ("total-collections",                 "/v1/traffic_reports/total_collections",                 "Total queries by collection"),
    ("total-collections-agents",          "/v1/traffic_reports/total_collections_agents",          "Total collection stats by agent"),
    ("total-collections-organizations",   "/v1/traffic_reports/total_collections_organizations",   "Total collection stats by organization"),
    ("total-collections-users",           "/v1/traffic_reports/total_collections_users",           "Total collection stats by user"),
    ("total-deployments",                 "/v1/traffic_reports/total_deployments",                 "Total deployments"),
    ("total-domain-requests",             "/v1/traffic_reports/total_domain_requests",             "Total requests per domain"),
    ("total-domain-stats",                "/v1/traffic_reports/total_domain_stats",                "Total domain stats"),
    ("total-domains",                     "/v1/traffic_reports/total_domains",                     "Total unique domains queried"),
    ("total-domains-collections",         "/v1/traffic_reports/total_domains_collections",         "Total domains by collection"),
    ("total-domains-organizations",       "/v1/traffic_reports/total_domains_organizations",       "Total domains by organization"),
    ("total-domains-users",               "/v1/traffic_reports/total_domains_users",               "Total domains by user"),
    ("total-organizations-requests",      "/v1/traffic_reports/total_organizations_requests",      "Total requests by organization"),
    ("total-organizations-stats",         "/v1/traffic_reports/total_organizations_stats",         "Total stats by organization"),
    ("total-requests",                    "/v1/traffic_reports/total_requests",                    "Total DNS requests"),
    ("total-requests-agents",             "/v1/traffic_reports/total_requests_agents",             "Total requests by agent"),
    ("total-requests-collections",        "/v1/traffic_reports/total_requests_collections",        "Total requests by collection"),
    ("total-requests-geo",                "/v1/traffic_reports/total_requests_geo",                "Total requests by geography"),
    ("total-requests-organizations",      "/v1/traffic_reports/total_requests_organizations",      "Total requests by organization"),
    ("total-requests-users",              "/v1/traffic_reports/total_requests_users",              "Total requests by user"),
    ("total-roaming-clients",             "/v1/traffic_reports/total_roaming_clients",             "Total roaming client stats"),
    ("total-threats",                     "/v1/traffic_reports/total_threats",                     "Total threats blocked"),
    ("total-threats-agents",              "/v1/traffic_reports/total_threats_agents",              "Total threats by agent"),
    ("total-threats-collections",         "/v1/traffic_reports/total_threats_collections",         "Total threats by collection"),
    ("total-threats-organizations",       "/v1/traffic_reports/total_threats_organizations",       "Total threats by organization"),
    ("total-threats-users",               "/v1/traffic_reports/total_threats_users",               "Total threats by user"),
]

REGISTRY["traffic-reports"] = Endpoint(
    name="traffic-reports",
    description="DNS traffic analytics and reporting (all GET)",
    operations={
        name: Operation("GET", path, desc, _tr_realtime if name in _TR_REALTIME_NAMES else _tr_common)
        for name, path, desc in _TRAFFIC_REPORT_PATHS
    },
)


# ------ user-agent-bulk-deletes ---------------------------------------------

REGISTRY["user-agent-bulk-deletes"] = Endpoint(
    name="user-agent-bulk-deletes",
    description="Bulk agent deletion jobs",
    operations={
        "create": Operation("POST", "/v1/user_agent_bulk_deletes",        "Create a bulk agent delete job",
                            [_p("organization_id", "Organization ID",             hint="integer"),
                             _p("ids",             "Array of agent IDs to delete",hint="array"),
                             _p("exclude_ids",     "Array of agent IDs to exclude", hint="array")],
                            destructive=True, poll_on="show"),
        "counts": Operation("GET",  "/v1/user_agent_bulk_deletes/counts", "Count agents matching bulk delete criteria"),
        "show":   Operation("GET",  "/v1/user_agent_bulk_deletes/{id}",   "Show a bulk delete job", [_id()], uses_id=True),
    },
)

# ------ user-agent-bulk-updates ---------------------------------------------

REGISTRY["user-agent-bulk-updates"] = Endpoint(
    name="user-agent-bulk-updates",
    description="Bulk agent update jobs",
    operations={
        "create":    Operation("POST", "/v1/user_agent_bulk_updates",           "Create a bulk agent update job",
                               [_p("organization_id",      "Organization ID",                    hint="integer", tl=True),
                                _p("ids",                  "Array of agent IDs to update",       hint="array",   tl=True),
                                _p("exclude_ids",          "Array of agent IDs to exclude",      hint="array",   tl=True),
                                _p("network_id",           "Array of network IDs (filter)",      hint="array",   tl=True),
                                _p("policy_id",            "Policy ID",                hint="integer"),
                                _p("scheduled_policy_id",  "Scheduled policy ID",      hint="integer"),
                                _p("block_page_id",        "Block page ID",            hint="integer"),
                                _p("friendly_name",        "Display name"),
                                _p("tags",                 "Array of tags",            hint="array"),
                                _p("release_channels",     "Array of release channels",hint="array"),
                                _p("device_setting_attributes",            "Device settings JSON",   hint="object"),
                                _p("filtering_client_setting_attributes",  "Filter settings JSON",   hint="object"),
                                _p("vpn_settings_user_agent",              "VPN settings JSON",      hint="object")],
                               body_key="changeset", poll_on="show"),
        "counts":    Operation("GET",  "/v1/user_agent_bulk_updates/counts",    "Count agents matching bulk update criteria"),
        "has-mixed": Operation("POST", "/v1/user_agent_bulk_updates/has_mixed", "Check for mixed values in bulk update selection",
                               [_p("ids", "Array of agent IDs", hint="array")]),
        "show":      Operation("GET",  "/v1/user_agent_bulk_updates/{id}",      "Show a bulk update job", [_id()], uses_id=True),
    },
)

# ------ user-agent-cleanups -------------------------------------------------

REGISTRY["user-agent-cleanups"] = Endpoint(
    name="user-agent-cleanups",
    description="Agent cleanup jobs",
    operations={
        "create": Operation("POST", "/v1/user_agent_cleanups",      "Create an agent cleanup job",
                            [_p("organization_id",  "Single organization ID",          hint="integer"),
                             _p("organization_ids", "Array of organization IDs",       req=True, hint="array"),
                             _p("inactive_for",     "Days of inactivity threshold",    req=True, hint="integer")],
                            poll_on="show"),
        "show":   Operation("GET",  "/v1/user_agent_cleanups/{id}", "Show a cleanup job",  [_id()], uses_id=True),
        "update": Operation("PUT",  "/v1/user_agent_cleanups/{id}", "Update a cleanup job",
                            [_id(),
                             _p("start",         "Start the cleanup job", hint="boolean"),
                             _p("inactive_for",  "Days of inactivity",    hint="integer")], uses_id=True),
    },
)

# ------ user-agent-csv-exports ----------------------------------------------

REGISTRY["user-agent-csv-exports"] = Endpoint(
    name="user-agent-csv-exports",
    description="Agent CSV export jobs",
    operations={
        "create": Operation("POST", "/v1/user_agent_csv_exports",      "Create an agent CSV export job",
                            [_p("organization_ids", "Array of org IDs",    hint="array"),
                             _p("msp_id",           "MSP ID",              hint="integer"),
                             _p("ids",              "Array of agent IDs",  hint="array"),
                             _p("network_ids",      "Array of network IDs",hint="array"),
                             _p("type",             "Export type"),
                             _p("search",           "Search term"),
                             _p("name_search",      "Name search term"),
                             _p("tags",             "Array of tags to filter",  hint="array"),
                             _p("status",           "Agent status filter"),
                             _p("state",            "Agent state filter"),
                             _p("agent_state",      "Agent state"),
                             _p("traffic_received_last_15_mins", "Only include agents active in last 15 min", hint="boolean")],
                            body_key="user_agent_csv_export", poll_on="show"),
        "show":   Operation("GET",  "/v1/user_agent_csv_exports/{id}", "Show an export job", [_id()], uses_id=True),
    },
)

# ------ user-agent-releases -------------------------------------------------

REGISTRY["user-agent-releases"] = Endpoint(
    name="user-agent-releases",
    description="Agent release information",
    operations={
        "list":  Operation("GET", "/v1/user_agent_releases",       "List agent releases"),
        "relay": Operation("GET", "/v1/user_agent_releases/relay", "Show relay agent release info"),
    },
)

# ------ user-agents ---------------------------------------------------------
# NOTE: the display name field is 'friendly_name', not 'name'

REGISTRY["user-agents"] = Endpoint(
    name="user-agents",
    description="Roaming agent (client) management",
    operations={
        "list":              Operation("GET",    "/v1/user_agents",                  "List agents",
                                       [*_pagination(),
                                        _p("organization_ids","Filter by org IDs (array)",    kind="query", hint="array"),
                                        _p("network_ids",     "Filter by network IDs (array)", kind="query", hint="array"),
                                        _p("policy_id",       "Filter by policy ID",          kind="query", hint="integer"),
                                        _p("search",          "Search by hostname",           kind="query"),
                                        _p("status",          "Filter by status",             kind="query"),
                                        _p("state",           "Filter by agent state",        kind="query"),
                                        _p("tags",            "Filter by tags",               kind="query"),
                                        _p("sort",            "Sort field",                   kind="query")]),
        "list-all":          Operation("GET",    "/v1/user_agents/all",              "List all agents"),
        "counts":            Operation("GET",    "/v1/user_agents/counts",           "Agent counts"),
        "csv":               Operation("GET",    "/v1/user_agents/csv",              "Export agents to CSV",
                             [Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "tags":              Operation("GET",    "/v1/user_agents/tags",             "List agent tags"),
        "uninstall-pin":     Operation("GET",    "/v1/user_agents/uninstall_pin",    "Get uninstall PIN",
                             [Param("organization_id", "Organization ID", required=True, kind="query", type_hint="integer")]),
        "dequeue-uninstall": Operation("POST",   "/v1/user_agents/dequeue_uninstall","Dequeue a pending uninstall request for a specific agent.",
                             [_p("id", "Agent ID to remove from the uninstall queue", req=True, kind="query")]),
        "show":              Operation("GET",    "/v1/user_agents/{id}",             "Show an agent",  [_uuid_id()], uses_id=True),
        "update":            Operation("PATCH",  "/v1/user_agents/{id}",             "Update an agent",
                                       [_uuid_id(),
                                        _p("friendly_name",       "Display name"),
                                        _p("status",              "Agent status"),
                                        _p("network_id",          "Network ID",           hint="integer"),
                                        _p("policy_id",           "Policy ID",            hint="integer"),
                                        _p("scheduled_policy_id", "Scheduled policy ID",  hint="integer"),
                                        _p("block_page_id",       "Block page ID",        hint="integer"),
                                        _p("tags",                "Array of tags",        hint="array"),
                                        _p("vpn_settings_user_agent_attributes", "VPN settings JSON", hint="object")],
                                       uses_id=True),
        "delete":            Operation("DELETE", "/v1/user_agents/{id}",             "Delete an agent", [_uuid_id()], uses_id=True),
    },
)

# ------ users ---------------------------------------------------------------
# NOTE: change-password only requires 'new_password' per the spec

REGISTRY["users"] = Endpoint(
    name="users",
    description="User management",
    operations={
        "list":            Operation("GET",   "/v1/users",                "List users",       _pagination()),
        "list-all":        Operation("GET",   "/v1/users/all",            "List all users"),
        "show":            Operation("GET",   "/v1/users/{id}",           "Show a user",      [_id()], uses_id=True),
        "change-password": Operation("PATCH", "/v1/users/change_password","Change current user password",
                                     [_p("new_password", "New password", req=True, secret=True)]),
    },
)

# ===========================================================================
# v2 endpoints
# ===========================================================================

REGISTRY["v2-agent-local-users"] = Endpoint(
    name="v2-agent-local-users",
    description="v2 Agent local user endpoints",
    operations={
        "counts":          Operation("GET",  "/v2/agent_local_users/counts",          "Count agent local users"),
        "csv-export":      Operation("POST", "/v2/agent_local_users_csv_export",       "Create agent local users CSV export",
                                    [_p("organization_ids", "Array of org IDs",   hint="array"),
                                     _p("name",             "Name filter"),
                                     _p("search",           "Search term"),
                                     _p("user_policy_override", "Filter by policy override", hint="boolean")],
                                    body_key="agent_local_users_csv_export", poll_on="csv-export-show"),
        "csv-export-show": Operation("GET",  "/v2/agent_local_users_csv_export/{id}", "Show a CSV export job", [_id()], uses_id=True),
    },
)

REGISTRY["v2-current-user"] = Endpoint(
    name="v2-current-user",
    description="v2 Current user endpoints",
    operations={
        "suppress-license-warning": Operation("POST",  "/v2/current_user/suppress_license_warning", "Suppress the license warning for the current user.",
                                              [_p("organization_uuid", "UUID of the organization to suppress the warning for", kind="query")]),
        "ui-settings":              Operation("GET",   "/v2/current_user/ui_settings",              "Show UI settings"),
        "ui-settings-update":       Operation("PATCH", "/v2/current_user/ui_settings",              "Update UI settings",
                                              [_p("disable_license_warnings", "Disable license warnings", hint="boolean"),
                                               _p("user_uuid",  "User UUID"),
                                               _p("theme_mode", "Theme mode (light | dark | system)")]),
    },
)


REGISTRY["v2-dictionary"] = Endpoint(
    name="v2-dictionary",
    description="v2 Dictionary / reference data",
    operations={
        "cyber-sight-activity-types": Operation("GET", "/v2/dictionary/cyber_sight_activity_types", "List Cyber Sight activity types"),
        "vpn-settings-state-types":   Operation("GET", "/v2/dictionary/vpn_settings_state_types",   "List VPN settings state types"),
    },
)

REGISTRY["v2-networks"] = Endpoint(
    name="v2-networks",
    description="v2 Network export endpoints",
    operations={
        "csv-export":      Operation("POST", "/v2/networks_csv_export",      "Create networks CSV export",
                                    [_p("organization_ids", "Array of org IDs",    hint="array"),
                                     _p("msp_id",           "MSP ID",              hint="integer"),
                                     _p("ids",              "Array of network IDs",hint="array")],
                                    body_key="networks_csv_export", poll_on="csv-export-show"),
        "csv-export-show": Operation("GET",  "/v2/networks_csv_export/{id}", "Show a network export job", [_id()], uses_id=True),
    },
)

REGISTRY["v2-user-agents"] = Endpoint(
    name="v2-user-agents",
    description="v2 Agent management",
    operations={
        "update-settings": Operation("PATCH", "/v2/user_agents/{id}/update_settings", "Update agent settings",
                                     [_uuid_id(),
                                      _p("device_setting_attributes",           "Device settings JSON",  hint="object"),
                                      _p("filtering_client_setting_attributes", "Filter settings JSON",  hint="object")],
                                     uses_id=True, body_key="user_agent"),
    },
)


# ---------------------------------------------------------------------------
def get_operation(endpoint: str, function: str) -> Operation:
    ep = REGISTRY.get(endpoint)
    if ep is not None:
        op = ep.operations.get(function)
        if op is not None:
            return op
        known = sorted(ep.operations.keys())
        raise ValueError(
            f"Unknown function '{function}' for endpoint '{endpoint}'.\n"
            f"Available functions: {', '.join(known)}"
        )
    raise ValueError(
        f"Unknown endpoint '{endpoint}'.\n"
        f"Run 'dnsfcli --help' to see available endpoints."
    )


def list_endpoints() -> list[str]:
    return sorted(REGISTRY.keys())


def list_functions(endpoint: str) -> list[str]:
    ep = REGISTRY.get(endpoint)
    return sorted(ep.operations.keys()) if ep else []
