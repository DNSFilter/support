"""OS keychain credential storage for DNSFilter API credentials.

Profiles let you store credentials for multiple tenants or environments.
The "default" profile maps to the original bare keychain keys (api_key,
org_id, base_url) so existing setups require no migration.  Additional
profiles store their credentials under namespaced keys (e.g. prod:api_key).

Profile resolution order:
  1. Explicit --profile flag on the command line
  2. DNSF_PROFILE environment variable
  3. Active profile set via `dnsfcli auth use <name>`
  4. "default"
"""

from __future__ import annotations

import keyring
import keyring.errors

SERVICE = "dnsfcli"
DEFAULT_PROFILE = "default"
DEFAULT_BASE_URL = "https://api.dnsfilter.com"

# Internal keychain keys (not profile credentials)
_META_PROFILES = "_profiles"
_META_ACTIVE   = "_active_profile"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_or_none(username: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, username)
    except keyring.errors.KeyringError:
        return None


def _cred_key(profile: str, field: str) -> str:
    """Return the keychain username for *field* within *profile*.

    The default profile uses bare field names for backward compatibility with
    credentials stored before profiles were introduced.
    """
    if profile == DEFAULT_PROFILE:
        return field
    return f"{profile}:{field}"


# ---------------------------------------------------------------------------
# Profile registry
# ---------------------------------------------------------------------------

def list_profiles() -> list[str]:
    """Return all configured profile names.  "default" is always first."""
    raw = _get_or_none(_META_PROFILES) or ""
    others = [n.strip() for n in raw.split(",") if n.strip() and n.strip() != DEFAULT_PROFILE]
    return [DEFAULT_PROFILE] + others


def _register_profile(profile: str) -> None:
    """Add *profile* to the stored list if not already present."""
    if profile == DEFAULT_PROFILE:
        return
    existing = list_profiles()
    if profile not in existing:
        others = [p for p in existing if p != DEFAULT_PROFILE]
        others.append(profile)
        keyring.set_password(SERVICE, _META_PROFILES, ",".join(others))


def _unregister_profile(profile: str) -> None:
    """Remove *profile* from the stored list."""
    if profile == DEFAULT_PROFILE:
        return
    existing = list_profiles()
    others = [p for p in existing if p != DEFAULT_PROFILE and p != profile]
    keyring.set_password(SERVICE, _META_PROFILES, ",".join(others))


# ---------------------------------------------------------------------------
# Active profile
# ---------------------------------------------------------------------------

def get_active_profile() -> str:
    """Return the persistently-set active profile, or "default"."""
    return _get_or_none(_META_ACTIVE) or DEFAULT_PROFILE


def set_active_profile(profile: str) -> None:
    """Persist *profile* as the active profile."""
    keyring.set_password(SERVICE, _META_ACTIVE, profile)


# ---------------------------------------------------------------------------
# Credential getters / setters
# ---------------------------------------------------------------------------

def store_api_key(api_key: str, profile: str = DEFAULT_PROFILE) -> None:
    _register_profile(profile)
    keyring.set_password(SERVICE, _cred_key(profile, "api_key"), api_key)


def get_api_key(profile: str = DEFAULT_PROFILE) -> str | None:
    return _get_or_none(_cred_key(profile, "api_key"))


def delete_api_key(profile: str = DEFAULT_PROFILE) -> None:
    try:
        keyring.delete_password(SERVICE, _cred_key(profile, "api_key"))
    except keyring.errors.PasswordDeleteError:
        pass


def store_org_id(org_id: str, profile: str = DEFAULT_PROFILE) -> None:
    keyring.set_password(SERVICE, _cred_key(profile, "org_id"), org_id)


def get_org_id(profile: str = DEFAULT_PROFILE) -> str | None:
    return _get_or_none(_cred_key(profile, "org_id"))


def delete_org_id(profile: str = DEFAULT_PROFILE) -> None:
    try:
        keyring.delete_password(SERVICE, _cred_key(profile, "org_id"))
    except keyring.errors.PasswordDeleteError:
        pass


def store_base_url(url: str, profile: str = DEFAULT_PROFILE) -> None:
    if not url.startswith("https://"):
        raise ValueError(f"Base URL must use HTTPS. Got: {url!r}")
    keyring.set_password(SERVICE, _cred_key(profile, "base_url"), url)


def get_base_url(profile: str = DEFAULT_PROFILE) -> str:
    stored = _get_or_none(_cred_key(profile, "base_url"))
    return stored or DEFAULT_BASE_URL


def delete_base_url(profile: str = DEFAULT_PROFILE) -> None:
    try:
        keyring.delete_password(SERVICE, _cred_key(profile, "base_url"))
    except keyring.errors.PasswordDeleteError:
        pass


# ---------------------------------------------------------------------------
# Profile-level operations
# ---------------------------------------------------------------------------

def clear_profile(profile: str = DEFAULT_PROFILE) -> None:
    """Delete all credentials for *profile* and remove it from the registry."""
    delete_api_key(profile)
    delete_org_id(profile)
    delete_base_url(profile)
    if profile != DEFAULT_PROFILE:
        _unregister_profile(profile)
        # If this was the active profile, reset to default
        if get_active_profile() == profile:
            try:
                keyring.delete_password(SERVICE, _META_ACTIVE)
            except keyring.errors.PasswordDeleteError:
                pass


def clear_all() -> None:
    """Delete credentials for every profile and reset all metadata."""
    for profile in list_profiles():
        delete_api_key(profile)
        delete_org_id(profile)
        delete_base_url(profile)
    for meta_key in (_META_PROFILES, _META_ACTIVE):
        try:
            keyring.delete_password(SERVICE, meta_key)
        except keyring.errors.PasswordDeleteError:
            pass


def store_last_verified(profile: str = DEFAULT_PROFILE) -> None:
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keyring.set_password(SERVICE, _cred_key(profile, "last_verified_at"), ts)


def get_last_verified(profile: str = DEFAULT_PROFILE) -> str | None:
    return _get_or_none(_cred_key(profile, "last_verified_at"))


def credentials_summary(profile: str = DEFAULT_PROFILE) -> dict[str, str]:
    api_key = get_api_key(profile)
    org_id  = get_org_id(profile)
    base_url = get_base_url(profile)
    return {
        "profile":  profile,
        "api_key":  (f"{api_key[:6]}...{api_key[-4:]}" if api_key and len(api_key) > 10
                     else ("[not set]" if not api_key else "***")),
        "org_id":   org_id or "[not set]",
        "base_url": base_url,
    }
