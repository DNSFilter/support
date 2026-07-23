"""The response cache key must be scoped to the credential + host.

Regression for the cross-account disclosure: without cred_scope, a GET cached
under API key A is served to a later invocation using API key B on the same
path (for endpoints scoped only by the bearer token, not an org param).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli import cache


def _scope(api_key: str, base_url: str) -> str:
    return hashlib.sha256(f"{api_key}\x00{base_url}".encode()).hexdigest()[:16]


def test_different_credentials_do_not_collide():
    args = ("networks", "list", "/v1/networks", {"page[number]": 1})
    k_a = cache.make_key(*args, cred_scope=_scope("KEY_A", "https://api.dnsfilter.com"))
    k_b = cache.make_key(*args, cred_scope=_scope("KEY_B", "https://api.dnsfilter.com"))
    assert k_a != k_b, "two different API keys produced the SAME cache key (cross-account leak)"


def test_different_base_urls_do_not_collide():
    args = ("networks", "list", "/v1/networks", None)
    k_prod = cache.make_key(*args, cred_scope=_scope("KEY", "https://api.dnsfilter.com"))
    k_stag = cache.make_key(*args, cred_scope=_scope("KEY", "https://staging.example.com"))
    assert k_prod != k_stag


def test_same_credential_same_request_is_stable():
    s = _scope("KEY", "https://api.dnsfilter.com")
    a = cache.make_key("networks", "list", "/v1/networks", {"page[number]": 1}, cred_scope=s)
    b = cache.make_key("networks", "list", "/v1/networks", {"page[number]": 1}, cred_scope=s)
    assert a == b


def test_roundtrip_scoped_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    k = cache.make_key("x", "list", "/v1/x", None, cred_scope=_scope("K", "https://h"))
    cache.put(k, {"data": [1, 2, 3]})
    assert cache.get(k, ttl=3600) == {"data": [1, 2, 3]}
    # a different credential's key must miss
    k2 = cache.make_key("x", "list", "/v1/x", None, cred_scope=_scope("OTHER", "https://h"))
    assert cache.get(k2, ttl=3600) is None
