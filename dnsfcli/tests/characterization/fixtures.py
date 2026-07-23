"""Canned API responses served in place of the network during characterization.

Items are intentionally flat (id/name/status/blocked/total) so the
post-processing helpers (--filter, --sum, --sort, --group-by, ...) can be
exercised directly and deterministically.
"""

from __future__ import annotations

from typing import Any

# A small, stable "networks list" dataset spread across two pages.
_NETWORKS = [
    {"id": "101", "name": "alpha", "status": "active",   "blocked": 30, "total": 100, "note": None},
    {"id": "102", "name": "bravo", "status": "error",    "blocked": 5,  "total": 50,  "note": "x"},
    {"id": "103", "name": "charlie", "status": "active", "blocked": 0,  "total": 10,  "note": None},
]

_ORGS = [
    {"id": "802315", "attributes": {"name": "Acme Accounting Co."}},
    {"id": "802316", "attributes": {"name": "Beta Corp"}},
]

_POLICIES = [
    {"id": "285109", "name": "Block Adult Content", "google_safesearch": True},
    {"id": "331207", "name": "Guest WiFi",          "google_safesearch": False},
]


def _page(items: list[dict], page: int, per_page: int = 2, total_pages: int = 2) -> dict[str, Any]:
    start = (page - 1) * per_page
    return {"data": items[start:start + per_page], "meta": {"total_pages": total_pages}}


def respond(method: str, path: str, params: dict | None, json_body: dict | None) -> Any:
    """Return a canned response for (method, path). Deterministic; no network."""
    params = params or {}
    page = int(params.get("page[number]", 1) or 1)

    # write ops (POST/PATCH/DELETE) echo a created/updated resource
    if method in ("POST", "PATCH", "PUT"):
        return {"data": {"id": "999", "type": path.strip("/").split("/")[-1], "attributes": json_body or {}}}
    if method == "DELETE":
        return None

    if path.startswith("/v1/organizations"):
        # /v1/organizations (list) — paginate 2 orgs over 1 page
        return {"data": _ORGS, "meta": {"total_pages": 1}}
    if path.startswith("/v1/policies"):
        return {"data": _POLICIES, "meta": {"total_pages": 1}}
    if path.startswith("/v1/networks"):
        # single-resource show: /v1/networks/{id}
        tail = path.rstrip("/").split("/")[-1]
        if tail.isdigit():
            return {"data": next((n for n in _NETWORKS if n["id"] == tail), _NETWORKS[0])}
        return _page(_NETWORKS, page)
    if path.startswith("/v1/EMPTY"):
        return {"data": [], "meta": {"total_pages": 1}}
    # default: empty list
    return {"data": [], "meta": {"total_pages": 1}}
