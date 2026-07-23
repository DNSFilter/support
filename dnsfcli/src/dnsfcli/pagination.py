"""Paginated fetch and partial-result detection.

_fetch_all_pages walks every page of a list endpoint; _result_is_partial /
_warn_if_partial let count/aggregate/guard modes warn when they would
otherwise compute on a single page.
"""

from __future__ import annotations

from typing import Any


from .output import _unwrap, err_console, print_info, print_warning
from .postprocess import _apply_filters

def _result_is_partial(result: Any) -> bool:
    """True when *result* is a single page of a larger set (more pages exist).

    Used to warn that --count/aggregates/--fail-on-* computed on partial data.
    """
    if not isinstance(result, dict):
        return False
    meta = result.get("meta") or result.get("pagination") or {}
    total = (meta.get("total") if isinstance(meta, dict) else None) or result.get("total")
    total_pages = None
    if isinstance(meta, dict):
        total_pages = meta.get("total_pages") or meta.get("last_page")
    payload = _unwrap(result)
    shown = len(payload) if isinstance(payload, list) else None
    if total and shown and int(total) > shown:
        return True
    if total_pages and int(total_pages) > 1:
        return True
    return False


def _warn_if_partial(result: Any, fetch_all: bool, mode: str) -> None:
    """Warn (to stderr) when a count/aggregate/guard runs on a single page."""
    if not fetch_all and _result_is_partial(result):
        print_warning(
            f"{mode} computed on the FIRST PAGE only — the result set spans "
            f"multiple pages. Add --all for a complete/accurate result."
        )


def _fetch_all_pages(
    client: Any,
    method: str,
    path: str,
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
    *,
    limit: int | None = None,
    max_pages: int | None = None,
    verbose: bool = False,
    show_progress: bool = True,
    paginate_until: str | None = None,
) -> tuple[Any, list[Any]]:
    """Fetch every page of a paginated list response and return the combined items.

    Returns ``(last_raw_response, all_items)`` where *all_items* is the flat
    list of every item across all pages.  If the first response is not a list
    (single resource or non-paginated) the function returns immediately with
    an empty ``all_items`` list so callers can fall back to normal handling.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    page_params = dict(params or {})
    all_items: list[Any] = []
    last_result: Any = None
    page_num = 1
    total_pages: int | None = None
    truncated = False       # set when --max-pages cut the fetch short
    pu_warned = False       # so a bad --paginate-until expr warns only once

    def _do_fetch() -> None:
        nonlocal last_result, page_num, total_pages, truncated

        use_bar = show_progress and not verbose
        progress_ctx: Any = (
            Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("[dim]{task.fields[items]} items[/dim]"),
                transient=True,
                console=err_console,
            )
            if use_bar else None
        )
        task_id: Any = None

        def _enter():
            nonlocal task_id
            if progress_ctx:
                progress_ctx.__enter__()
                task_id = progress_ctx.add_task(
                    "Fetching pages…",
                    total=None,
                    items=0,
                )

        def _update(fetched: int):
            if progress_ctx and task_id is not None:
                progress_ctx.update(
                    task_id,
                    completed=page_num - 1,
                    total=total_pages,
                    items=len(all_items),
                    description=f"Page {page_num}" + (f"/{total_pages}" if total_pages else ""),
                )

        def _exit():
            if progress_ctx:
                progress_ctx.__exit__(None, None, None)

        _enter()
        try:
            while True:
                page_params["page[number]"] = page_num
                result = client.request(method, path, params=page_params or None, json=json_body)
                last_result = result

                page_items = _unwrap(result)
                if not isinstance(page_items, list):
                    return

                all_items.extend(page_items)
                if verbose:
                    print_info(f"  Page {page_num}: +{len(page_items)} items (total: {len(all_items)})")

                # Parse total_pages from THIS page's meta before deciding to
                # stop, so a --max-pages cap can tell whether more pages remain
                # (and warn the caller that the result is partial).
                if isinstance(result, dict):
                    meta = result.get("meta") or {}
                    pagination = (
                        meta.get("pagination")
                        or meta.get("paging")
                        or (meta if ("total_pages" in meta or "last_page" in meta) else {})
                    )
                    tp = pagination.get("total_pages") or pagination.get("last_page")
                    if tp is not None:
                        total_pages = int(tp)

                _update(len(page_items))

                if limit is not None and len(all_items) >= limit:
                    break

                if max_pages is not None and page_num >= max_pages:
                    # Only flag truncation when we KNOW more pages exist.
                    if total_pages is not None and page_num < total_pages:
                        truncated = True
                    break

                if paginate_until and page_items:
                    try:
                        _pu_matched = _apply_filters(page_items, [paginate_until])
                        if _pu_matched:
                            if verbose:
                                print_info(f"  --paginate-until: condition matched on page {page_num}, stopping.")
                            break
                    except ValueError as _pu_exc:
                        nonlocal pu_warned
                        if not pu_warned:
                            print_warning(f"--paginate-until: {_pu_exc}; stop condition ignored.")
                            pu_warned = True

                if total_pages is None or page_num >= total_pages:
                    break

                page_num += 1
        finally:
            _exit()

    _do_fetch()
    # --limit caps the TOTAL items across pages. The loop stops once the count
    # reaches the limit, but the last page can overshoot it, so trim to exactly
    # `limit` here (the post-processing `payload[:limit]` guard is skipped when
    # --all is set and --limit is the only flag).
    if limit is not None and len(all_items) > limit:
        all_items = all_items[:limit]
    if truncated:
        print_warning(
            f"--max-pages: stopped at {max_pages} page(s) of {total_pages}; "
            f"results are partial — counts, sums, and --fail-on-empty reflect "
            f"only the fetched pages."
        )
    return last_result, all_items
