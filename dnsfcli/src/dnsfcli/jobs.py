"""Async-job polling for --wait and human-readable duration estimates."""

from __future__ import annotations

from typing import Any

from .cliparams import _build_path
from .client import APIError, DNSFilterClient
from .endpoints import get_operation
from .output import console, print_error, print_warning, print_response

_TERMINAL_OK: frozenset[str] = frozenset({
    "completed", "complete", "done", "success", "finished",
})
_TERMINAL_ERR: frozenset[str] = frozenset({
    "failed", "error", "errored",
})

def _estimate_duration(n_calls: int) -> str:
    """Return a human-readable time estimate for *n_calls* API calls."""
    if n_calls == 0:
        return "< 1 second"
    if n_calls == 1:
        return "~1 second"
    if n_calls <= 5:
        return f"~{n_calls * 2} seconds"
    if n_calls <= 30:
        return f"~{n_calls * 1.5:.0f} seconds"
    # DNSFilter allows 2,000 req / 300 s ≈ 6.67 req/s sustained
    RATE = 6.67
    secs = n_calls / RATE
    if secs < 60:
        return f"~{secs:.0f} seconds"
    if secs < 3600:
        return f"~{secs / 60:.1f} minutes"
    return f"~{secs / 3600:.1f} hours"


def _find_job_status(data: Any) -> str | None:
    """Return the job status string from an API response, or None if not found."""
    if not isinstance(data, dict):
        return None
    for key in ("status", "state"):
        val = data.get(key)
        if isinstance(val, str):
            return val
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("status", "state"):
            val = inner.get(key)
            if isinstance(val, str):
                return val
    return None


def _find_job_id(data: Any) -> Any:
    """Return the job ID from an API response (root or inside 'data' envelope)."""
    if not isinstance(data, dict):
        return None
    job_id = data.get("id")
    if job_id is not None:
        return job_id
    inner = data.get("data")
    if isinstance(inner, dict):
        return inner.get("id")
    return None


def _wait_for_job(
    initial_result: Any,
    endpoint: str,
    poll_function: str,
    resolved_key: str,
    base_url: str,
    resolved_org: str | None,
    raw: bool,
    title: str,
    columns: list[str] | None,
    max_wait: float | None = None,
) -> bool:
    """Poll *endpoint*/*poll_function* until the job reaches a terminal state.

    Returns True when the job completed successfully OR when waiting was not
    applicable (no job id / no poll op — the primary request still succeeded).
    Returns False when a tracked job ended in error, timed out, or its outcome
    could not be determined — so the caller can exit non-zero for CI.
    """
    import time

    job_id = _find_job_id(initial_result)
    if job_id is None:
        print_warning("--wait: could not extract a job ID from the response; polling skipped.")
        return True

    try:
        poll_op = get_operation(endpoint, poll_function)
    except Exception:
        print_warning(f"--wait: poll operation '{endpoint} {poll_function}' not found; polling skipped.")
        return True

    poll_path, _ = _build_path(poll_op.path_template, {"id": job_id})

    interval = 3.0   # seconds between polls
    max_interval = 30.0
    attempt = 0

    console.print(f"[dim]Waiting for job {job_id} ({endpoint} {poll_function})…[/dim]")

    _wfj_deadline = time.monotonic() + max_wait if max_wait is not None else None
    with DNSFilterClient(api_key=resolved_key, base_url=base_url, org_id=resolved_org) as client:
        while True:
            attempt += 1
            time.sleep(interval)
            if _wfj_deadline is not None and time.monotonic() > _wfj_deadline:
                print_warning(f"--max-wait: {max_wait:.0f}s exceeded waiting for job {job_id}.")
                return False
            interval = min(interval * 1.5, max_interval)

            try:
                result = client.request("GET", poll_path)
            except APIError as exc:
                print_error(f"Poll request failed: {exc}")
                return False

            status = _find_job_status(result)

            if status is None:
                # Can't detect status; give up after a few tries to avoid an infinite loop
                if attempt >= 5:
                    print_warning("--wait: no recognizable status field found after 5 polls; showing last result.")
                    print_response(result, raw=raw, title=title, columns=columns)
                    return False
                console.print(f"  [dim]Attempt {attempt}: status unknown, retrying in {interval:.0f}s…[/dim]")
                continue

            status_lower = status.lower()
            if status_lower in _TERMINAL_OK:
                console.print(f"[bold green]✓[/bold green] Job {job_id} {status_lower}.")
                print_response(result, raw=raw, title=title, columns=columns)
                return True
            if status_lower in _TERMINAL_ERR:
                console.print(f"[bold red]✗[/bold red] Job {job_id} {status_lower}.")
                print_response(result, raw=raw, title=title, columns=columns)
                return False

            console.print(f"  [dim]{status} — checking again in {interval:.0f}s (attempt {attempt})[/dim]")
