"""Batch execution engine: one API call per CSV/JSON row, plus CIDR expansion.

_execute_csv_rows runs a batch (serial or bounded-concurrency) with per-row
result reporting, streamed error checkpointing, and real stop semantics;
_create_ips_from_cidr expands a CIDR block into individual ip-address creates.
"""

from __future__ import annotations

import os
import sys
import threading
import time as _time
from typing import Any

import typer
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)

from .audit import log_event
from .client import APIError, DNSFilterClient
from .cliparams import _build_path
from .output import _unwrap, console, err_console, print_error, print_info, print_success, print_warning, write_csv
from .preview import _confirm_destructive, _dry_run_batch_preview, _preview_confirm_batch


_ROW_CONTEXT_FIELDS = ("name", "id", "email", "address", "fqdn", "domain")


def _scrub_report_input(row: dict[str, Any]) -> dict[str, Any]:
    """Mask secret-looking columns before echoing a row into --batch-report.

    The report is a diagnostic artifact (unlike --errors-to-csv, which must
    retain real values to be re-runnable), so secret-named fields are masked."""
    from .audit import mask_secret_keys
    return mask_secret_keys(row)


def _is_auth_error(err: str | None) -> bool:
    return bool(err and ("authentication failed" in err or "authorization denied" in err))


def _row_context(row: dict[str, Any]) -> str:
    """Return a short '[field=value, ...]' string for the most identifying fields of a row."""
    parts = [f"{k}={row[k]!r}" for k in _ROW_CONTEXT_FIELDS if k in row]
    return f" [{', '.join(parts[:2])}]" if parts else ""


def _execute_csv_rows(
    rows: list[dict[str, Any]],
    operation: Any,
    endpoint: str,
    function: str,
    client: Any,
    *,
    verbose: bool,
    csv_output: str | None,
    org_id: str | None = None,
    columns: list[str] | None = None,
    on_error: str = "continue",
    concurrency: int = 1,
    csv_delimiter: str = ",",
    retry: int = 0,
    errors_csv: str | None = None,
    upsert: bool = False,
    max_errors: int | None = None,
    confirm_each: bool = False,
    validate_only: bool = False,
    no_progress: bool = False,
    batch_delay: int | None = None,
    diff_mode: bool = False,
    batch_report_path: str | None = None,
) -> None:
    """Execute one API call per CSV row and report per-row results."""
    import threading
    import time as _time
    from . import output as _out_mod
    from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

    n = len(rows)
    _use_bar = not verbose and not _out_mod._quiet and not no_progress

    # --confirm-each cannot prompt safely from parallel workers; a silently
    # skipped confirmation on a destructive batch is dangerous, so force
    # sequential execution when both are requested.
    if confirm_each and concurrency > 1:
        print_warning("--confirm-each requires sequential execution; ignoring --concurrency for this run.")
        concurrency = 1

    # 5xx retries are only safe for idempotent methods. POST/PATCH are not
    # retried on 5xx (a failed write may have applied server-side, so a retry
    # could duplicate it); the operator is warned once and can re-run the
    # streamed --errors-to-csv after checking.
    _IDEMPOTENT = {"GET", "PUT", "DELETE"}
    _dup_warn_shown = {"v": False}

    # --validate-only: check required params without making API calls
    if validate_only:
        required = {p.name for p in operation.params if p.required}
        errors_found = 0
        for i, row_params in enumerate(rows, start=1):
            missing = required - set(row_params.keys())
            if missing:
                err_console.print(f"  Row {i}{_row_context(row_params)}: missing required field(s): {', '.join(sorted(missing))}")
                errors_found += 1
        if errors_found:
            console.print(f"[bold red]Validation failed:[/bold red] {errors_found} row(s) have errors.")
            sys.exit(1)
        console.print(f"[bold green]Validation passed:[/bold green] {n} row(s) look OK.")
        return

    if verbose:
        console.print(f"\nProcessing {n} row{'s' if n != 1 else ''} from CSV...\n")

    known_kinds: dict[str, str] = {p.name: p.kind for p in operation.params}

    def _execute_row(i: int, row_params: dict[str, Any]) -> tuple[bool, Any, str | None]:
        """Execute one row. Returns (ok, result_or_None, error_str_or_None)."""
        # CIDR expansion
        if (endpoint == "ip-addresses" and function == "create"
                and "/" in str(row_params.get("address", ""))):
            cidr = str(row_params["address"])
            body_base = {k: v for k, v in row_params.items() if k != "address"}
            if not _use_bar:
                console.print(f"\n  Row {i}: expanding CIDR [bold]{cidr}[/bold]")
            try:
                _create_ips_from_cidr(cidr, body_base, client, verbose=verbose, csv_output=csv_output, org_id=org_id)
                return True, None, None
            except SystemExit:
                return False, None, "CIDR expansion failed"

        try:
            path, remaining = _build_path(operation.path_template, dict(row_params), raise_on_missing=True)
        except ValueError as exc:
            return False, None, str(exc)

        method = operation.method
        query_params: dict[str, Any] = {}
        body_params: dict[str, Any] = {}
        for key, val in remaining.items():
            kind = known_kinds.get(key)
            if kind == "query" or (kind is None and method in ("GET", "DELETE")):
                query_params[key] = val
            else:
                body_params[key] = val

        json_body: dict[str, Any] | None = None
        if body_params or operation.body_key:
            if operation.body_key:
                top_names = {p.name for p in operation.params if p.top_level}
                top = {k: v for k, v in body_params.items() if k in top_names}
                nested = {k: v for k, v in body_params.items() if k not in top_names}
                json_body = {**top, operation.body_key: nested}
            else:
                json_body = body_params

        if verbose:
            print_info(f"Row {i}: {method} {path}")
            if json_body:
                print_info(f"  Body: {json_body}")

        # --diff-mode: fetch current state and show field changes before PATCH/PUT
        if diff_mode and method in ("PATCH", "PUT") and json_body:
            try:
                _current = client.get(path)
                if isinstance(_current, dict):
                    _current_data = _current
                    for _dk in ("data", "results", "items", "records"):
                        if _dk in _current and isinstance(_current[_dk], dict):
                            _current_data = _current[_dk]
                            break
                    _flat_body = json_body
                    if operation.body_key and operation.body_key in json_body:
                        _flat_body = {**{k: v for k, v in json_body.items() if k != operation.body_key}, **json_body[operation.body_key]}
                    _changed = {k: (_current_data.get(k), v) for k, v in _flat_body.items() if _current_data.get(k) != v}
                    if _changed:
                        from rich.table import Table as _DiffTable
                        _dt = _DiffTable(title=f"Row {i} changes", show_header=True, header_style="bold cyan")
                        _dt.add_column("Field")
                        _dt.add_column("Before")
                        _dt.add_column("After")
                        for _field, (_old, _new) in _changed.items():
                            _dt.add_row(_field, str(_old), f"[bold]{_new}[/bold]")
                        console.print(_dt)
                    else:
                        console.print(f"  [dim]Row {i}: no changes detected (diff-mode)[/dim]")
            except Exception:
                pass

        _attempts = retry + 1
        _last_exc: APIError | None = None
        for _attempt in range(_attempts):
            try:
                _row_method = method
                _row_path = path
                result = client.request(method, path, params=query_params or None, json=json_body)
                log_event(endpoint, function, _row_method, _row_path, 200, org_id)
                rid: Any = None
                if isinstance(result, dict):
                    rid = result.get("id")
                    if rid is None:
                        for v in result.values():
                            if isinstance(v, dict) and "id" in v:
                                rid = v["id"]
                                break
                id_str = f" (id: {rid})" if rid is not None else ""
                if not _use_bar:
                    console.print(f"  Row {i}: [green]✓[/green]{id_str}")
                return True, result, None
            except APIError as exc:
                # --upsert: 409 on POST → retry as PATCH on the conflicting resource
                if upsert and method == "POST" and exc.status_code == 409:
                    _upsert_id: Any = None
                    if isinstance(exc.body, dict):
                        _ub = exc.body
                        _upsert_id = (
                            _ub.get("id")
                            or (_ub.get("data") or {}).get("id")
                            or (_unwrap(_ub) or {}).get("id") if isinstance(_unwrap(_ub), dict) else None
                        )
                    if _upsert_id is None:
                        _last_exc = exc
                        break
                    _row_path = f"{path}/{_upsert_id}"
                    try:
                        result = client.request("PATCH", _row_path, json=json_body)
                        log_event(endpoint, function, "PATCH", _row_path, 200, org_id)
                        rid = result.get("id") if isinstance(result, dict) else None
                        id_str = f" (id: {rid})" if rid is not None else ""
                        if not _use_bar:
                            console.print(f"  Row {i}: [green]✓[/green] (upserted){id_str}")
                        return True, result, None
                    except APIError as _patch_exc:
                        _last_exc = _patch_exc
                        break
                _last_exc = exc
                if exc.status_code >= 500 and _attempt < _attempts - 1 and method in _IDEMPOTENT:
                    # Exponential backoff with jitter so concurrent rows that all
                    # hit a 5xx don't retry in lockstep.
                    import random as _rnd_retry
                    _wait = 2 ** _attempt + _rnd_retry.uniform(0, 0.5)
                    if verbose:
                        print_info(f"  Row {i}: 5xx ({exc.status_code}), retry {_attempt + 1}/{retry} in {_wait:.1f}s")
                    _time.sleep(_wait)
                else:
                    # Non-idempotent method with --retry: explain (once) why we
                    # did NOT retry, so a duplicate-write risk is never silent.
                    if (retry and exc.status_code >= 500 and method not in _IDEMPOTENT
                            and not _dup_warn_shown["v"]):
                        _dup_warn_shown["v"] = True
                        print_warning(
                            f"--retry: {method} rows that fail with 5xx are NOT retried — a failed "
                            f"write may have already applied server-side and retrying could create "
                            f"duplicates. Re-run the --errors-to-csv file after verifying."
                        )
                    break
        assert _last_exc is not None
        log_event(endpoint, function, method, path, _last_exc.status_code, org_id, error=str(_last_exc))
        _err_str = str(_last_exc)
        if _last_exc.status_code == 401:
            _err_str += " — authentication failed (API key invalid or expired; run: dnsfcli auth setup)"
        elif _last_exc.status_code == 403:
            _err_str += " — authorization denied (insufficient permissions for this org/operation)"
        return False, None, _err_str

    succeeded = 0
    failed = 0
    results: list[Any] = []
    failed_row_inputs: list[dict[str, Any]] = []
    failed_reasons: list[str] = []
    _report_rows: list[dict[str, Any]] = [] if batch_report_path else []
    stop_flag = threading.Event()

    # --errors-to-csv is streamed row-by-row (flushed each time) rather than
    # written once at the end, so a Ctrl-C or crash mid-batch still leaves a
    # resume checkpoint. Without this, an interrupted run left no record of
    # which rows had succeeded and rerunning the whole CSV re-created them.
    # Both the serial and concurrent paths record results in this (single)
    # thread, so no lock is needed.
    import csv as _csv_mod
    _err_fh: Any = None
    _err_writer: Any = None

    def _stream_failed_row(row_p: dict[str, Any]) -> None:
        nonlocal _err_fh, _err_writer
        if not errors_csv:
            return
        try:
            if _err_writer is None:
                # 0600: failed rows are echoed verbatim (they must be, so
                # --retry-errors-csv can re-run them) and can carry secret input
                # columns (passwords, tokens). Owner-only, like the audit log.
                _err_fd = os.open(errors_csv, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                os.fchmod(_err_fd, 0o600)  # tighten even if the file pre-existed at looser perms
                _err_fh = os.fdopen(_err_fd, "w", newline="", encoding="utf-8")
                _err_writer = _csv_mod.DictWriter(
                    _err_fh, fieldnames=list(row_p.keys()),
                    delimiter=csv_delimiter, extrasaction="ignore",
                )
                _err_writer.writeheader()
            _err_writer.writerow({k: row_p.get(k, "") for k in _err_writer.fieldnames})
            _err_fh.flush()
        except OSError:
            pass  # a failed checkpoint write must not abort the batch

    _prog_ctx: Any = None
    _task_id: Any = None
    if _use_bar:
        _prog_ctx = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.fields[ok]}✓  {task.fields[err]}✗[/dim]"),
            transient=True,
            console=err_console,
        )
        _task_id = _prog_ctx.add_task("Batch", total=n, ok=0, err=0)
        _prog_ctx.__enter__()

    try:
        if concurrency > 1:
            from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
            row_iter = enumerate(rows, start=1)
            futures_map: dict[Any, tuple[int, dict[str, Any]]] = {}
            # Clamp defensively: the CLI flag is IntRange-bounded, but a config
            # bundle could still supply an absurd value. Cap thread/connection use.
            _workers = max(1, min(concurrency, 64))
            with ThreadPoolExecutor(max_workers=_workers) as pool:
                # Keep only ~concurrency rows in flight instead of submitting
                # every row up front. This is what makes --on-error stop and
                # --max-errors real under concurrency: once the stop flag trips
                # we submit no more rows and cancel the ones not yet started.
                def _submit_next() -> bool:
                    try:
                        i, row_params = next(row_iter)
                    except StopIteration:
                        return False
                    fut = pool.submit(_execute_row, i, row_params)
                    futures_map[fut] = (i, row_params)
                    return True

                for _ in range(concurrency):
                    if stop_flag.is_set() or not _submit_next():
                        break

                while futures_map:
                    done, _ = wait(futures_map, return_when=FIRST_COMPLETED)
                    for f in done:
                        ok, result, err = f.result()
                        row_i, row_p = futures_map.pop(f)
                        if batch_report_path:
                            _report_rows.append({"row": row_i, "ok": ok, "error": err, "input": _scrub_report_input(row_p)})
                        if ok:
                            succeeded += 1
                            if result is not None and csv_output:
                                results.append(result)  # only retained to write --to-csv
                        else:
                            failed += 1
                            failed_row_inputs.append(row_p)
                            failed_reasons.append(err or "unknown error")
                            _stream_failed_row(row_p)
                            err_console.print(f"  Row {row_i}{_row_context(row_p)}: [red]✗[/red] {err}")
                            if _is_auth_error(err):
                                err_console.print(f"[bold red]Auth error — stopping batch (further rows will fail too).[/bold red]")
                                stop_flag.set()
                            elif on_error == "stop" or (max_errors is not None and failed >= max_errors):
                                stop_flag.set()
                        if _prog_ctx and _task_id is not None:
                            _prog_ctx.update(_task_id, advance=1, ok=succeeded, err=failed)
                    # Backfill the freed slots — unless we're stopping, in which
                    # case cancel whatever hasn't begun and drain the rest.
                    if stop_flag.is_set():
                        for pending in list(futures_map):
                            if pending.cancel():
                                del futures_map[pending]
                    else:
                        for _ in range(len(done)):
                            if not _submit_next():
                                break
        else:
            for i, row_params in enumerate(rows, start=1):
                if confirm_each:
                    ctx_str = _row_context(row_params)
                    console.print(f"[dim]Row {i}/{n}{ctx_str}[/dim]")
                    if not typer.confirm(f"  Process row {i}?", default=True):
                        console.print(f"  [dim]Row {i}: skipped.[/dim]")
                        continue
                ok, result, err = _execute_row(i, row_params)
                if batch_report_path:
                    _report_rows.append({"row": i, "ok": ok, "error": err, "input": _scrub_report_input(row_params)})
                if ok:
                    succeeded += 1
                    if result is not None and csv_output:
                        results.append(result)  # only retained to write --to-csv
                else:
                    failed += 1
                    failed_row_inputs.append(row_params)
                    failed_reasons.append(err or "unknown error")
                    _stream_failed_row(row_params)
                    _err_target = err_console if _use_bar else console
                    _err_target.print(f"  Row {i}{_row_context(row_params)}: [red]✗[/red] {err}")
                    if _is_auth_error(err):
                        _err_target.print("[bold red]Auth error — stopping batch (further rows will fail too).[/bold red]")
                        break
                    _stop_now = on_error == "stop" or (max_errors is not None and failed >= max_errors)
                    if _stop_now:
                        if not _use_bar:
                            if max_errors is not None and failed >= max_errors:
                                console.print(f"[dim]Stopping after {failed} error(s) (--max-errors {max_errors}).[/dim]")
                            else:
                                console.print("[dim]Stopping on first error (--on-error stop).[/dim]")
                        break
                if _prog_ctx and _task_id is not None:
                    _prog_ctx.update(_task_id, advance=1, ok=succeeded, err=failed)
                if batch_delay and i < n:
                    _time.sleep(batch_delay / 1000.0)
    finally:
        if _prog_ctx:
            _prog_ctx.__exit__(None, None, None)
        if _err_fh is not None:
            try:
                _err_fh.close()
            except OSError:
                pass

    console.print()
    if failed == 0:
        console.print(f"[bold green]Done:[/bold green] {succeeded}/{n} row(s) succeeded")
    else:
        console.print(
            f"[bold yellow]Done:[/bold yellow] "
            f"{succeeded} succeeded, {failed} failed (out of {n})"
        )
        if failed_reasons:
            _reason_counts: dict[str, int] = {}
            for _r in failed_reasons:
                # Key by the HTTP status prefix if present (e.g. "HTTP 422: ...")
                import re as _re_reason
                _m = _re_reason.match(r"HTTP (\d+)", _r)
                _key = f"HTTP {_m.group(1)}" if _m else _r[:60]
                _reason_counts[_key] = _reason_counts.get(_key, 0) + 1
            _breakdown = ", ".join(f"{cnt}× {k}" for k, cnt in sorted(_reason_counts.items(), key=lambda x: -x[1]))
            console.print(f"[dim]Error breakdown: {_breakdown}[/dim]")

    if csv_output and results:
        written = write_csv(results, csv_output, columns=columns, delimiter=csv_delimiter)
        print_success(f"Wrote {written} result row(s) to {csv_output}")

    if errors_csv and failed_row_inputs:
        # The file was already streamed row-by-row during the run (crash-safe);
        # just report it. No end-of-run rewrite — the streamed file IS the file.
        print_success(f"Wrote {len(failed_row_inputs)} failed input row(s) to {errors_csv}")
        console.print(f"[dim]Retry failed rows with: --retry-errors-csv {errors_csv}[/dim]")

    if batch_report_path and _report_rows:
        import json as _json_br
        import datetime as _dt_br
        _br_doc = {
            "timestamp": _dt_br.datetime.now(_dt_br.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": n, "succeeded": succeeded, "failed": failed,
            "rows": _report_rows,
        }
        try:
            # 0600: even with secret columns masked, the report holds tenant data.
            _br_fd = os.open(batch_report_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(_br_fd, 0o600)  # tighten even if the file pre-existed at looser perms
            with os.fdopen(_br_fd, "w", encoding="utf-8") as _br_fh:
                _br_fh.write(_json_br.dumps(_br_doc, indent=2, default=str))
            print_success(f"Wrote batch report to {batch_report_path}")
        except OSError as _br_exc:
            print_warning(f"--batch-report: could not write {batch_report_path}: {_br_exc}")

    if failed > 0 and on_error != "report":
        sys.exit(1)


def _create_ips_from_cidr(
    cidr: str,
    body_base: dict[str, Any],
    client: Any,
    verbose: bool,
    csv_output: str | None,
    columns: list[str] | None = None,
    org_id: str | None = None,
) -> None:
    """Expand a CIDR block and register all host addresses against a network.

    Strategy (fewest possible API calls):
      1. Attempt a single PATCH to /v1/networks/{network_id} passing all host
         addresses in ``ip_addresses_attributes``.  This handles an entire /24
         in one round-trip.
      2. If the batch fails because some IPs already exist elsewhere in
         DNSFilter, parse the error response to identify which indices failed,
         strip those addresses, and retry the remainder in a second batch call.
         Retries continue until either the batch succeeds or no retries remain.
      3. If the network_id is missing, or the batch keeps failing for a
         non-duplicate reason, fall back to individual POST calls so partial
         progress is captured.

    Network address (x.x.x.0) and broadcast (x.x.x.255) are excluded for
    prefix <= /30 via ``ip_network.hosts()``.  /31 and /32 include every
    address per RFC 3021.

    Hard limit: /16 (65,536 addresses).
    """
    import ipaddress

    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        print_error(f"Invalid CIDR notation '{cidr}': {exc}")
        sys.exit(1)

    hosts: list[Any] = list(network) if network.prefixlen >= 31 else list(network.hosts())
    total = len(hosts)

    if total > 65_536:
        print_error(
            f"{cidr} contains {total:,} addresses. "
            "Maximum supported is 65,536 (/16). Please split into smaller blocks."
        )
        sys.exit(1)

    console.print(
        f"Expanding [bold]{cidr}[/bold] → "
        f"[bold]{total:,}[/bold] host address{'es' if total != 1 else ''}."
    )

    network_id = body_base.get("network_id")

    # ── Batch path via networks update ────────────────────────────────────────
    if network_id:
        ip_attrs = [{"address": str(h)} for h in hosts]
        n_pending = len(ip_attrs)

        if verbose:
            print_info(f"Batch: PATCH /v1/networks/{network_id} with {n_pending} IP(s)")

        for _once in [1]:  # single-iteration loop; break exits to individual-call fallback

            try:
                result = client.patch(
                    f"/v1/networks/{network_id}",
                    json={"network": {"ip_addresses_attributes": ip_attrs}},
                )
                log_event("ip-addresses", "create", "PATCH",
                          f"/v1/networks/{network_id}", 200, org_id)
                # Success — all IPs registered in one call
                console.print(
                    f"\n[bold green]Done:[/bold green] "
                    f"{n_pending} IP address{'es' if n_pending != 1 else ''} "
                    f"registered in [bold]1 API call[/bold]."
                )
                if csv_output and isinstance(result, dict):
                    write_csv(result, csv_output, columns=columns)
                    print_success(f"Wrote result to {csv_output}")
                return

            except APIError as exc:
                log_event("ip-addresses", "create", "PATCH",
                          f"/v1/networks/{network_id}", exc.status_code, org_id,
                          error=str(exc))
                # The networks update endpoint returns 422 with an unindexed error
                # format when duplicates exist — it reports how many IPs failed but
                # not which ones.  We can't selectively retry, so fall through to
                # individual calls which give clear per-IP success/failure feedback.
                is_duplicate = (
                    isinstance(exc.body, dict)
                    and any(
                        "already" in " ".join(str(v) for v in (val if isinstance(val, list) else [val]))
                        for val in exc.body.values()
                    )
                )
                if is_duplicate:
                    dup_count = sum(
                        1 for val in exc.body.values()
                        if isinstance(val, list) and val and "already" in str(val[0])
                    )
                    console.print(
                        f"\n[yellow]{dup_count} IP address{'es' if dup_count != 1 else ''} in "
                        f"this block already exist in DNSFilter.[/yellow] "
                        "Falling back to individual calls to identify which ones...\n"
                    )
                else:
                    console.print(
                        f"[yellow]Batch call failed: {exc}.[/yellow] "
                        "Falling back to individual calls.\n"
                    )
                break  # exit retry loop → fall through to individual calls

        # fall through to individual calls if the batch did not return

    # ── Individual-call fallback ───────────────────────────────────────────────
    console.print(
        f"[dim]Using individual calls "
        f"({'network_id not provided' if not network_id else 'batch retries exhausted'}).[/dim]\n"
    )

    succeeded = 0
    failed    = 0
    ind_results: list[Any] = []

    for i, host_ip in enumerate(hosts, start=1):
        ip_str = str(host_ip)
        body   = {**body_base, "address": ip_str}

        if verbose:
            print_info(f"[{i}/{total}] POST /v1/ip_addresses  {ip_str}")

        try:
            result = client.request("POST", "/v1/ip_addresses", json=body)
            log_event("ip-addresses", "create", "POST", "/v1/ip_addresses", 200, org_id)
            succeeded += 1
            rid: Any = None
            if isinstance(result, dict):
                rid = result.get("id") or (result.get("data") or {}).get("id")
            id_str = f" [dim](id: {rid})[/dim]" if rid else ""
            console.print(f"  [{i}/{total}] [green]✓[/green] {ip_str}{id_str}")
            if result is not None:
                ind_results.append(result)
        except APIError as exc:
            log_event("ip-addresses", "create", "POST", "/v1/ip_addresses",
                      exc.status_code, org_id, error=str(exc))
            failed += 1
            console.print(f"  [{i}/{total}] [red]✗[/red] {ip_str}: {exc}")

    console.print()
    if failed == 0:
        console.print(
            f"[bold green]Done:[/bold green] "
            f"{succeeded}/{total} IP address{'es' if total != 1 else ''} created."
        )
    else:
        console.print(
            f"[bold yellow]Done:[/bold yellow] "
            f"{succeeded} created, {failed} failed (out of {total})."
        )

    if csv_output and ind_results:
        n = write_csv(ind_results, csv_output, columns=columns)
        print_success(f"Wrote {n} result row(s) to {csv_output}")

    if failed > 0:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Batch dispatch: --from-csv / --from-json entry points for _run_api_call.
# Row acquisition differs (CSV validate/read vs JSON parse/merge); everything
# after — dry-run preview, confirmation, chunking, execution — is shared.
# ---------------------------------------------------------------------------

def run_batch(
    rows: list[dict[str, Any]],
    *,
    opts: Any,
    operation: Any,
    endpoint: str,
    function: str,
    source_label: str,
    client_kwargs: dict[str, Any],
    resolved_org: str | None,
    columns: list[str] | None,
) -> None:
    """Shared batch tail: preview on --dry-run, confirm, chunk, execute.

    `rows` has already been sliced by --skip-rows / --max-rows by the caller.
    Stable per-run flags are read from *opts* (RunOptions); values that the
    caller may have derived (columns from config defaults, resolved_org, the
    fully-built client_kwargs) are passed explicitly.
    """
    n = len(rows)
    if opts.dry_run:
        # --dry-run must send NOTHING, including for batch input.
        _dry_run_batch_preview(rows, operation, endpoint, function, source_label)
        return
    if operation.method == "DELETE" or operation.destructive:
        _confirm_destructive(
            f"About to execute {n} destructive {'operation' if n == 1 else 'operations'} "
            f"({endpoint} {function}) from {source_label}.",
            opts.skip_confirm,
        )
    elif operation.method in ("POST", "PATCH", "PUT"):
        _preview_confirm_batch(rows, operation, endpoint, function, opts.skip_confirm)
    _batches = [rows]
    if opts.batch_size and opts.batch_size > 0:
        _batches = [rows[i:i + opts.batch_size] for i in range(0, len(rows), opts.batch_size)]
    with DNSFilterClient(**client_kwargs) as client:
        for _batch_idx, _batch in enumerate(_batches):
            if len(_batches) > 1:
                console.print(f"[dim]Batch {_batch_idx + 1}/{len(_batches)} ({len(_batch)} rows)[/dim]")
            _execute_csv_rows(
                _batch, operation, endpoint, function, client,
                verbose=opts.verbose, csv_output=opts.csv_file, org_id=resolved_org, columns=columns,
                on_error=opts.on_error, concurrency=opts.concurrency, csv_delimiter=opts.csv_delimiter,
                retry=opts.retry, errors_csv=opts.errors_csv, upsert=opts.upsert, max_errors=opts.max_errors,
                confirm_each=opts.confirm_each, validate_only=opts.validate_only, no_progress=opts.no_progress,
                batch_delay=opts.batch_delay, diff_mode=opts.diff_mode, batch_report_path=opts.batch_report,
            )


def dispatch_from_csv(
    csv_input: str,
    *,
    opts: Any,
    operation: Any,
    endpoint: str,
    function: str,
    params: dict[str, Any],
    client_kwargs: dict[str, Any],
    resolved_org: str | None,
    columns: list[str] | None,
) -> None:
    """--from-csv: validate + read the file, slice, then run the batch."""
    from .csv_io import CsvValidationError, read_csv_input
    try:
        rows = read_csv_input(csv_input, operation, params, opts.csv_delimiter)
    except CsvValidationError as exc:
        print_error(f"CSV validation failed for {exc.filepath}:")
        for err in exc.errors:
            err_console.print(f"  {err}")
        sys.exit(1)
    # --skip-rows / --max-rows: slice input before processing
    if opts.skip_rows:
        console.print(f"[dim]--skip-rows: skipping first {opts.skip_rows} row(s) ({len(rows)} total)[/dim]")
        rows = rows[opts.skip_rows:]
    if opts.max_rows is not None:
        rows = rows[:opts.max_rows]
    run_batch(
        rows, opts=opts, operation=operation, endpoint=endpoint, function=function,
        source_label=csv_input, client_kwargs=client_kwargs,
        resolved_org=resolved_org, columns=columns,
    )


def dispatch_from_json(
    json_input: str,
    *,
    opts: Any,
    operation: Any,
    endpoint: str,
    function: str,
    params: dict[str, Any],
    client_kwargs: dict[str, Any],
    resolved_org: str | None,
    columns: list[str] | None,
) -> None:
    """--from-json: parse a JSON array, merge CLI params, slice, run the batch."""
    import json as _json
    src = json_input.strip()
    if src == "-":
        content = sys.stdin.read()
        src_label = "stdin"
    else:
        try:
            with open(src, encoding="utf-8") as _fh:
                content = _fh.read()
            src_label = src
        except OSError as exc:
            print_error(f"--from-json: cannot read file: {exc}")
            sys.exit(1)
    try:
        json_data: Any = _json.loads(content)
    except _json.JSONDecodeError as exc:
        print_error(f"--from-json: invalid JSON: {exc}")
        sys.exit(1)
    if isinstance(json_data, dict):
        json_data = _unwrap(json_data)
    if not isinstance(json_data, list):
        print_error("--from-json: expected a JSON array ([...]).")
        sys.exit(1)
    if not json_data:
        print_error("--from-json: JSON array is empty.")
        sys.exit(1)
    if not all(isinstance(item, dict) for item in json_data):
        print_error("--from-json: every element of the JSON array must be an object ({...}).")
        sys.exit(1)
    # Merge: CLI params take priority over JSON fields
    json_rows = [{**item, **params} for item in json_data]
    if opts.skip_rows:
        json_rows = json_rows[opts.skip_rows:]
    if opts.max_rows is not None:
        json_rows = json_rows[:opts.max_rows]
    run_batch(
        json_rows, opts=opts, operation=operation, endpoint=endpoint, function=function,
        source_label=src_label, client_kwargs=client_kwargs,
        resolved_org=resolved_org, columns=columns,
    )
