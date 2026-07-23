"""CLI argument parsing and request-shaping helpers.

Turns raw CLI tokens into typed request pieces: parsing --key value pairs,
coercing string values to JSON types, substituting (URL-encoded) path
params, normalizing dashed param names, loading --env-file, and detecting a
literal --api-key flag. No HTTP, no output — just input massaging.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from .auth import get_api_key, get_base_url, get_org_id
from .output import print_error, print_warning

_loaded_env_files: set[str] = set()

# Every generic CLI flag the dynamic command defines (see cliopts._OPTION_SPECS),
# in dashed form. _run_api_call strips these from the caller-supplied --key=value
# args so they are never mistaken for API parameters. Kept as one source of truth
# because the list was previously duplicated verbatim in two places and drifted.
RESERVED_CLI_FLAGS: tuple[str, ...] = (
    "raw", "verbose", "api-key", "org-id", "to-csv", "from-csv", "template", "plan",
    "yes", "columns", "wait", "profile", "all", "json", "no-color", "quiet", "sort",
    "limit", "to-json", "timeout", "filter", "count", "body-json", "page", "page-size",
    "jsonl", "on-error", "concurrency", "grep", "unique", "format", "append", "dry-run",
    "from-json", "cache-ttl", "each-org", "org-name", "set", "exclude", "merge-key",
    "rate", "truncate", "csv-delimiter", "no-header", "retry", "errors-to-csv",
    "retry-errors-csv", "csv-header-case", "rename", "pick", "batch-size", "timing",
    "group-by", "select", "sum", "avg", "min", "max", "map", "watch-changes", "upsert",
    "last", "sample", "fields", "strip-nulls", "max-pages", "max-errors", "save-as",
    "null-as", "no-wrap", "color-if", "count-by", "not-null", "is-null", "since",
    "header", "insecure", "no-progress", "tee", "output", "validate-only", "confirm-each",
    "diff-mode", "parallel-orgs", "org-concurrency", "max-orgs", "preset", "flatten",
    "strip-empties", "csv-null", "watch-until", "fail-on-empty", "quiet-ok", "delay",
    "org-filter", "connect-timeout", "proxy", "jq", "max-wait", "watch", "watch-diff", "alert",
    "table-style", "stats", "env-file", "log-file", "stdin-json", "skip-rows", "max-rows",
    "add-field", "paginate-until", "org-csv", "batch-report", "color-scale",
    "format-preset", "fail-on-pattern", "filter-mode", "to-markdown", "output-schema",
    "exec", "transform", "join", "bundle",
)


_PATH_COMPONENT_UNSAFE = re.compile(r"[^\w.\- ]")


def sanitize_path_component(component: Any) -> str:
    """Reduce an arbitrary string to a safe single path component (basename).

    Used for API-supplied values (e.g. an organization name in an MSP account)
    substituted into an output FILE path via {org_name}/{org_id}: a value
    containing '/' or '..' could otherwise write outside the intended
    directory. Maps everything outside [word chars, dot, dash, space] to '_'
    and strips leading/trailing dots and spaces so '.'/'..' cannot survive.
    """
    s = _PATH_COMPONENT_UNSAFE.sub("_", str(component))
    s = s.strip(". ")
    return s or "org"


def resolve_http_context(opts: Any) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve credentials + base URL and build the shared DNSFilterClient kwargs.

    Reads api_key / org_id / profile / insecure / proxy / connect_timeout /
    extra_headers off *opts* (a RunOptions). Emits the same warnings as before
    (--api-key on CLI, non-default base URL, --insecure / --insecure+--proxy)
    and exits on a missing key or non-HTTPS base URL. Returns
    ``(resolved_key, resolved_org, base_url, client_kwargs)``; the parsed
    --header dict is folded into client_kwargs and is not returned separately.
    """
    import re

    resolved_key = opts.api_key or get_api_key(profile=opts.profile)
    if not resolved_key:
        print_error(
            "No API key found. Set one with [bold]dnsfcli auth setup[/bold] "
            "or pass [bold]--api-key[/bold] / env var [bold]DNSF_API_KEY[/bold]."
        )
        sys.exit(1)
    if opts.api_key and _api_key_flag_on_cli():
        print_warning(
            "API key passed via [bold]--api-key[/bold]. "
            "It may be exposed in: shell history (~/.zsh_history, ~/.bash_history), "
            "process listings (ps aux), and CI/CD logs. "
            "Prefer [bold]dnsfcli auth setup[/bold] or the "
            "[bold]DNSF_API_KEY[/bold] environment variable."
        )

    resolved_org = opts.org_id or get_org_id(profile=opts.profile)
    # Normalise: strip any trailing /v1 or /v2 from the stored base URL so the
    # version-prefixed paths in the registry are never doubled.
    base_url = re.sub(r"/v\d+/*$", "", get_base_url(profile=opts.profile).rstrip("/"))
    if not base_url.startswith("https://"):
        print_error(f"Base URL must use HTTPS. Got: {base_url!r}. Update it with [bold]dnsfcli auth setup --base-url[/bold].")
        sys.exit(1)
    if base_url != "https://api.dnsfilter.com":
        print_warning(f"Non-default base URL in use: {base_url}")

    # Parse --header KEY=VALUE list into a dict; --insecure skips TLS verification
    parsed_headers: dict[str, str] | None = None
    if opts.extra_headers:
        parsed_headers = {}
        for _hdr in opts.extra_headers:
            if "=" in _hdr:
                _hk, _hv = _hdr.split("=", 1)
                parsed_headers[_hk.strip()] = _hv.strip()
            else:
                print_warning(f"--header: ignored malformed entry {_hdr!r} (expected KEY=VALUE)")
    if opts.insecure:
        print_warning("TLS verification disabled (--insecure). Do not use in production.")
        if opts.proxy:
            print_warning("--insecure + --proxy: TLS is disabled and a proxy is set. "
                          "Your API key and all request data will be visible to the proxy operator in plaintext.")

    # Shared kwargs for every DNSFilterClient instantiation in this call
    client_kwargs: dict[str, Any] = {
        "api_key": resolved_key,
        "base_url": base_url,
        "verify": not opts.insecure,
        "extra_headers": parsed_headers,
        **({"connect_timeout": opts.connect_timeout} if opts.connect_timeout is not None else {}),
        **({"proxy": opts.proxy} if opts.proxy else {}),
    }
    return resolved_key, resolved_org, base_url, client_kwargs


def _load_env_file(path: str) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (skips already-set vars).

    Idempotent per path — app_entry loads it early for envvar= resolution and
    _cmd loads it again; the second call (and its failure warning) is skipped.
    """
    if path in _loaded_env_files:
        return
    _loaded_env_files.add(path)
    import os as _os_ef
    try:
        with open(path, encoding="utf-8") as _ef_fh:
            for _ef_line in _ef_fh:
                _ef_line = _ef_line.strip()
                if not _ef_line or _ef_line.startswith("#"):
                    continue
                if "=" in _ef_line:
                    _ef_key, _, _ef_val = _ef_line.partition("=")
                    _ef_key = _ef_key.strip()
                    _ef_val = _ef_val.strip().strip('"').strip("'")
                    if _ef_key:
                        _os_ef.environ.setdefault(_ef_key, _ef_val)
    except OSError as _ef_exc:
        import sys as _sys_ef
        _sys_ef.stderr.write(f"Warning: --env-file: cannot read {path!r}: {_ef_exc}\n")


def _parse_extra_args(args: list[str]) -> dict[str, str]:
    """Parse --key value or --key=value pairs from the extra args list."""
    result: dict[str, str] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                result[k] = v
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                result[key] = args[i + 1]
                i += 1
            else:
                result[key] = "true"
        elif token.startswith("-") and len(token) == 2:
            # short flags like -v
            key = token[1:]
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                result[key] = args[i + 1]
                i += 1
            else:
                result[key] = "true"
        i += 1
    return result


def _api_key_flag_on_cli() -> bool:
    """True when --api-key/-k was literally typed on the command line.

    The Click options also accept DNSF_API_KEY via envvar=; the exposure
    warning must fire only for the flag form, not for the (recommended)
    environment variable.
    """
    return any(
        tok in ("--api-key", "-k") or tok.startswith(("--api-key=", "-k="))
        for tok in sys.argv[1:]
    )


def _normalize_param_keys(params: dict[str, Any]) -> dict[str, Any]:
    """Map dashed CLI param names to underscore API field names.

    Help text renders API params in dashed form (--organization-id), so both
    spellings must reach the API as the canonical underscore name. Called
    AFTER internal-flag cleanup, which matches on dashed names.
    """
    return {k.replace("-", "_"): v for k, v in params.items()}


def _coerce_value(value: str) -> Any:
    """Coerce a CLI string value to the most appropriate Python type.

    Order of attempts:
      1. boolean literals   "true" / "false"
      2. JSON array/object  "[…]" / "{…}"
      3. integer
      4. float
      5. plain string (returned as-is)
    """
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    stripped = value.strip()
    if stripped.startswith(("[", "{")):
        try:
            import json as _json
            return _json.loads(stripped)
        except ValueError:
            pass
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _build_path(
    template: str,
    params: dict[str, Any],
    *,
    raise_on_missing: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Substitute path placeholders in *template* from *params*.

    If a required placeholder is missing:
      - ``raise_on_missing=True``  → raises ``ValueError`` (used by CSV row loop)
      - ``raise_on_missing=False`` → prints an error and calls ``sys.exit(1)``
    """
    remaining = dict(params)
    path = template
    import re
    from urllib.parse import quote as _urlquote
    for match in re.finditer(r"\{(\w+)\}", template):
        key = match.group(1)
        if key in remaining:
            # URL-encode so a value containing / ? # .. cannot alter the
            # request path shape (e.g. --id "../other").
            path = path.replace(
                f"{{{key}}}", _urlquote(str(remaining.pop(key)), safe="")
            )
        else:
            if raise_on_missing:
                raise ValueError(
                    f"Required path parameter '{key}' not provided"
                )
            print_error(
                f"Required path parameter [bold]--{key}[/bold] was not provided.",
                f"Path template: {template}",
            )
            sys.exit(1)
    return path, remaining
