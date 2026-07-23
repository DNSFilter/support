"""Pure result post-processing helpers for dnsfcli.

Everything here transforms an already-fetched API result (a list/dict of
records) into another value or a printed view: filtering, sorting keys,
aggregation, field mapping, flattening, jq-style extraction, format
templates, and the --transform expression sandbox. These functions take
data in and return data out (a few print via the shared console), with no
knowledge of HTTP, argument parsing, or command wiring — which is why they
live apart from the command layer.
"""

from __future__ import annotations

import ast
import copy
import re
import shlex
import sys
from typing import Any

from .output import (
    console,
    print_error,
    print_warning,
    tee_write,
)

def _apply_exclude(items: list[Any], fields: list[str]) -> list[Any]:
    """Remove *fields* from every dict item (other items are passed through unchanged)."""
    field_set = set(fields)
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({k: v for k, v in item.items() if k not in field_set})
        else:
            result.append(item)
    return result


def _apply_renames(items: list[Any], renames: list[str]) -> list[Any]:
    """Rename fields in each item.  Each rename expr is 'FROM=TO'."""
    parsed: list[tuple[str, str]] = []
    for expr in renames:
        if "=" in expr:
            src, _, dst = expr.partition("=")
            src = src.strip()
            dst = dst.strip()
            if src and dst:
                parsed.append((src, dst))
    if not parsed:
        return items
    result = []
    for item in items:
        if isinstance(item, dict):
            new_item = dict(item)
            for src, dst in parsed:
                if src in new_item:
                    new_item[dst] = new_item.pop(src)
            result.append(new_item)
        else:
            result.append(item)
    return result


def _apply_pick(items: list[Any], field: str) -> list[str]:
    """Extract *field* (supports dot-notation) from each item; return one string per item."""
    parts = field.split(".")
    out: list[str] = []
    for item in items:
        obj: Any = item
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        if obj is not None:
            out.append(str(obj))
    return out


def _as_number(v: Any) -> float | None:
    """Coerce a value to a number, including numeric STRINGS ("150").

    Matches the coercion --filter uses, so `--sum count` and `--filter count>90`
    agree on what counts as numeric when the API returns a number as a string.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _numeric_field_values(items: list[Any], field: str) -> list[float]:
    out: list[float] = []
    for item in items:
        if isinstance(item, dict):
            n = _as_number(item.get(field))
            if n is not None:
                out.append(n)
    return out


def _apply_sum(items: list[Any], field: str) -> float:
    """Sum numeric values of *field* across all dict items."""
    return sum(_numeric_field_values(items, field))


def _apply_avg(items: list[Any], field: str) -> float | None:
    """Average numeric values of *field* across all dict items; None if no values."""
    nums = _numeric_field_values(items, field)
    return sum(nums) / len(nums) if nums else None


def _apply_min(items: list[Any], field: str) -> float | None:
    """Minimum numeric value of *field* across all dict items; None if no values."""
    nums = _numeric_field_values(items, field)
    return min(nums) if nums else None


def _apply_max(items: list[Any], field: str) -> float | None:
    """Maximum numeric value of *field* across all dict items; None if no values."""
    nums = _numeric_field_values(items, field)
    return max(nums) if nums else None


def _apply_group_by(items: list[Any], field: str) -> list[dict[str, Any]]:
    """Return a count table: one row per distinct *field* value, sorted descending."""
    parts = field.split(".")
    counts: dict[str, int] = {}
    for item in items:
        obj: Any = item
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        key = str(obj) if obj is not None else "(none)"
        counts[key] = counts.get(key, 0) + 1
    return [
        {field: k, "count": v}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]


def _apply_select(items: list[Any], fields: list[str]) -> list[Any]:
    """Keep only *fields* in each dict item (other items are passed through unchanged)."""
    field_set = set(fields)
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append({k: v for k, v in item.items() if k in field_set})
        else:
            result.append(item)
    return result


def _apply_null_as(obj: Any, replacement: str) -> Any:
    """Recursively replace None values with *replacement* string."""
    if obj is None:
        return replacement
    if isinstance(obj, list):
        return [_apply_null_as(item, replacement) for item in obj]
    if isinstance(obj, dict):
        return {k: _apply_null_as(v, replacement) for k, v in obj.items()}
    return obj


def _apply_count_by(items: list[Any], field: str) -> list[dict[str, Any]]:
    """Return a frequency table with a pct column, sorted descending by count."""
    parts = field.split(".")
    counts: dict[str, int] = {}
    for item in items:
        obj: Any = item
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = None
                break
        key = str(obj) if obj is not None else "(none)"
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values()) or 1
    return [
        {field: k, "count": v, "pct": f"{v / total * 100:.1f}%"}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]


def _apply_map_fields(items: list[Any], map_specs: list[str]) -> list[Any]:
    """Apply named transformations to field values.

    Each spec has the form ``FIELD=TRANSFORM`` where TRANSFORM is one of:
    ``upper``, ``lower``, ``strip``, ``title``, ``truncate:N``.
    Specs for unknown fields are silently ignored.
    """
    transforms: list[tuple[str, str]] = []
    for spec in map_specs:
        if "=" not in spec:
            continue
        field, transform = spec.split("=", 1)
        transforms.append((field.strip(), transform.strip()))

    def _apply_one(value: Any, transform: str) -> Any:
        if not isinstance(value, str):
            value = str(value) if value is not None else value
        if value is None:
            return value
        t = transform.lower()
        if t == "upper":
            return value.upper()
        if t == "lower":
            return value.lower()
        if t == "strip":
            return value.strip()
        if t == "title":
            return value.title()
        if t.startswith("truncate:"):
            try:
                n = int(t[9:])
                return value[:n]
            except ValueError:
                return value
        return value

    result = []
    for item in items:
        if isinstance(item, dict):
            new_item = dict(item)
            for field, transform in transforms:
                if field in new_item:
                    new_item[field] = _apply_one(new_item[field], transform)
            result.append(new_item)
        else:
            result.append(item)
    return result


def _apply_flatten(items: list[Any], separator: str = ".") -> list[Any]:
    """Flatten nested dict objects to dot-notation keys."""
    def _flat(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in obj.items():
            key = f"{prefix}{separator}{k}" if prefix else k
            if isinstance(v, dict) and v:
                result.update(_flat(v, key))
            else:
                result[key] = v
        return result
    return [_flat(item) if isinstance(item, dict) else item for item in items]


class _WatchUntilSatisfied(Exception):
    """Raised inside _run_api_call to signal that --watch-until condition is met."""


def _apply_jq(result: Any, expr: str) -> Any:
    """Extract a value via a dot-separated path (e.g. 'data.0.attributes.name')."""
    parts = expr.split(".")
    current = result
    for part in parts:
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                print_warning(f"--jq: index '{part}' out of range or not an integer")
                return result
        elif isinstance(current, dict):
            if part not in current:
                print_warning(f"--jq: key '{part}' not found in result")
                return result
            current = current[part]
        else:
            print_warning(f"--jq: cannot traverse '{part}' on a {type(current).__name__}")
            return result
    return current


def _show_watch_diff(old_data: Any, new_data: Any) -> None:
    """Print a compact diff summary between two watch-loop iterations."""
    import json as _json

    def _to_set(d: Any) -> set[str]:
        items = d if isinstance(d, list) else ([d] if d is not None else [])
        return {_json.dumps(item, sort_keys=True, default=str) for item in items}

    old_set = _to_set(old_data)
    new_set = _to_set(new_data)
    added = len(new_set - old_set)
    removed = len(old_set - new_set)
    if not added and not removed:
        console.print("[dim]  Δ (no changes)[/dim]")
    else:
        parts = []
        if added:
            parts.append(f"[green]+{added} added[/green]")
        if removed:
            parts.append(f"[red]-{removed} removed[/red]")
        console.print("  Δ " + "  ".join(parts))


def _compute_stats(items: list[Any], field: str) -> None:
    """Print min/max/mean/count for a numeric field across *items*."""
    values: list[float] = []
    for item in items:
        if isinstance(item, dict):
            v = item.get(field)
            try:
                values.append(float(v))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
    if not values:
        console.print(f"[dim]--stats {field!r}: no numeric values found[/dim]")
        return
    n = len(values)
    console.print(
        f"[dim]  stats({field}): n={n}  min={min(values):g}  max={max(values):g}"
        f"  mean={sum(values)/n:g}[/dim]"
    )


def _parse_filter(expr: str) -> tuple[str, str, str]:
    """Parse a filter expression into (field, operator, value).

    Supported operators (checked in order of length so '>=' is not mis-parsed as '>'):
      field=value    exact match (string comparison after coercion)
      field!=value   not equal
      field~value    case-insensitive substring contains
      field>=value   >=
      field<=value   <=
      field>value    >
      field<value    <

    Raises ``ValueError`` for unrecognised expressions.
    """
    for op in ("!=", ">=", "<=", "~", "=", ">", "<"):
        if op in expr:
            field, _, value = expr.partition(op)
            field = field.strip()
            value = value.strip()
            if not field:
                raise ValueError(f"No field name in filter expression: {expr!r}")
            return field, op, value
    raise ValueError(
        f"Unrecognised filter expression: {expr!r}. "
        "Expected form: field=value, field!=value, field~value, field>=value, etc."
    )


_TRANSFORM_BUILTINS: dict[str, Any] = {
    "int": int, "float": float, "str": str, "len": len,
    "abs": abs, "round": round, "min": min, "max": max, "bool": bool,
}


# AST nodes permitted in --transform expressions. Attribute access is
# deliberately excluded — it is the escape hatch from any eval sandbox
# (e.g. ().__class__.__bases__). Dotted field access is not needed here
# because transforms operate on top-level response fields.
_TRANSFORM_ALLOWED_NODES: tuple = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.Name, ast.Constant, ast.Subscript, ast.List, ast.Tuple,
    ast.Dict, ast.Load,
    # operators
    # ast.Pow (**) is intentionally excluded: 9**9**9 is a cheap way to hang
    # the process on a giant-integer computation. Field transforms don't need it.
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
)


def _compile_transform_expr(expr: str):
    """Parse and validate a --transform expression; return a code object.

    Raises ``ValueError`` when the expression uses anything beyond arithmetic,
    comparisons, literals, field names, and the whitelisted builtin calls.
    """
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _TRANSFORM_ALLOWED_NODES):
            raise ValueError(
                f"Unsupported syntax in transform expression {expr!r}: "
                f"{type(node).__name__}"
            )
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError(f"Illegal name {node.id!r} in transform expression")
        if isinstance(node, ast.Call) and not (
            isinstance(node.func, ast.Name) and node.func.id in _TRANSFORM_BUILTINS
        ):
            raise ValueError(
                f"Only these functions may be called in a transform: "
                f"{', '.join(sorted(_TRANSFORM_BUILTINS))}"
            )
        # Sequence repetition ("a"*N, [0]*N, (0,)*N) is a cheap way to allocate
        # gigabytes and hang the process — the same class of DoS the excluded
        # ast.Pow guards against. Field transforms never need it.
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            for operand in (node.left, node.right):
                if isinstance(operand, (ast.List, ast.Tuple)) or (
                    isinstance(operand, ast.Constant) and isinstance(operand.value, str)
                ):
                    raise ValueError(
                        "Sequence repetition (str/list * n) is not allowed in a "
                        "transform expression"
                    )
    return compile(tree, "<transform>", "eval")


def _apply_transforms(items: list[Any], transform_specs: list[str]) -> list[Any]:
    """Compute new or derived fields from restricted expressions.

    Each spec is FIELD=EXPR where EXPR may reference any existing field by name.
    Expressions are validated against an AST allowlist before evaluation:
    arithmetic, comparisons, literals, and calls to int, float, str, len, abs,
    round, min, max, bool. Attribute access and other syntax are rejected.
    """
    for spec in transform_specs:
        if "=" not in spec:
            continue
        _tf_field, _tf_expr = spec.split("=", 1)
        _tf_field = _tf_field.strip()
        _tf_expr = _tf_expr.strip()
        try:
            _code = _compile_transform_expr(_tf_expr)
        except (ValueError, SyntaxError) as exc:
            print_error(f"Invalid --transform expression: {exc}")
            sys.exit(1)
        _new: list[Any] = []
        _tf_failures = 0
        for item in items:
            if isinstance(item, dict):
                _ns = {
                    **_TRANSFORM_BUILTINS,
                    **{k: v for k, v in item.items() if isinstance(k, str)},
                }
                try:
                    _val = eval(_code, {"__builtins__": {}}, _ns)  # noqa: S307 — AST-validated above
                    item = {**item, _tf_field: _val}
                except Exception:
                    # A per-row failure (missing field, division by zero, type
                    # error) leaves that row unchanged; count them so we can
                    # tell the user rather than silently under-transforming.
                    _tf_failures += 1
            _new.append(item)
        if _tf_failures:
            print_warning(
                f"--transform {_tf_field!r}: could not compute on {_tf_failures} "
                f"row(s) (missing field or bad value); those rows are unchanged."
            )
        items = _new
    return items


# --exec rendering ---------------------------------------------------------

_EXEC_PLACEHOLDER = re.compile(r"\{(\w+)\}|\$(\w+)\b")

# --exec substitutes result fields into a command run with shell=True. shlex.quote
# makes a *bare* placeholder safe, but an operator who quotes the placeholder the
# idiomatic way (echo "{name}" or echo '{name}') reopens injection: $(...) and
# backticks stay active inside double quotes, and single-quote wrapping can be
# broken out of. We cannot reliably know a placeholder's quoting context, so we
# refuse any substituted value containing a shell-active character and let only
# inert values (ids, names, domains, URLs) through. The command TEMPLATE itself
# is operator-supplied and trusted, so it keeps full shell power.
_EXEC_UNSAFE_CHARS = re.compile(r"[^\w.\-:/@ ]")


def render_exec_command(template: str, item: dict[str, Any]) -> tuple[str, list[str]]:
    """Render a ``--exec`` command template for one result *item*.

    Returns ``(rendered_command, unsafe_fields)``. Each ``{field}`` / ``$field``
    placeholder present in *item* is replaced by ``shlex.quote``'d field value.
    If ``unsafe_fields`` is non-empty the caller MUST NOT execute the command —
    a substituted value contained a character that a shell could interpret, so
    running it would risk command injection from (possibly attacker-controlled)
    API data.
    """
    unsafe: list[str] = []

    def _sub(m: "re.Match[str]") -> str:
        name = m.group(1) or m.group(2)
        if name in item:
            val = str(item[name])
            # Flag shell-active characters AND leading-dash values: a value like
            # "-rf" or "--all" is all "safe" chars but injects an OPTION into the
            # operator's own command (e.g. `rm {name}` → `rm -rf`).
            if _EXEC_UNSAFE_CHARS.search(val) or val.startswith("-"):
                unsafe.append(name)
            return shlex.quote(val)
        return m.group(0)  # unknown placeholder: leave verbatim

    return _EXEC_PLACEHOLDER.sub(_sub, template), unsafe


def _apply_filters(items: list[Any], filters: list[str], mode: str = "and") -> list[Any]:
    """Return the subset of *items* that match *filters*.

    With mode='and' (default) ALL filters must match.  With mode='or' ANY filter
    is sufficient.  Each filter string is parsed by ``_parse_filter``.  Items that
    are not dicts are kept as-is when the field is absent.
    """
    import re as _re

    compiled: list[tuple[str, str, str]] = []
    for expr in filters:
        compiled.append(_parse_filter(expr))

    def _get(item: Any, field: str) -> Any:
        """Fetch a dotted or flat field from *item*."""
        if not isinstance(item, dict):
            return None
        if "." in field:
            parts = field.split(".", 1)
            return _get(item.get(parts[0]), parts[1])
        return item.get(field)

    def _matches(item: Any, field: str, op: str, raw_value: str) -> bool:
        cell = _get(item, field)
        # Coerce raw_value to the same type as cell when possible
        try:
            if isinstance(cell, bool):
                typed: Any = raw_value.lower() in ("1", "true", "yes")
            elif isinstance(cell, int):
                typed = int(raw_value)
            elif isinstance(cell, float):
                typed = float(raw_value)
            else:
                typed = raw_value
        except (ValueError, TypeError):
            typed = raw_value

        if op in ("=", "!="):
            # Equality is numeric-aware, matching the ordering operators below:
            # 90 == "90" == 90.0 == "90.0" (fixes fields the API returns as
            # numeric strings). Booleans keep their 1/true/yes coercion, and
            # non-numeric values fall back to case-insensitive string compare.
            if cell is None:
                eq = (str(raw_value) == "")
            elif isinstance(cell, bool):
                eq = (cell == (raw_value.strip().lower() in ("1", "true", "yes")))
            else:
                try:
                    eq = float(str(cell)) == float(str(raw_value))
                except (ValueError, TypeError):
                    eq = str(cell).lower() == str(raw_value).lower()
            return eq if op == "=" else (not eq)
        if op == "~":
            return raw_value.lower() in str(cell).lower() if cell is not None else False
        if op == ">":
            try:
                return float(str(cell)) > float(str(typed))
            except (ValueError, TypeError):
                return str(cell) > str(typed)
        if op == "<":
            try:
                return float(str(cell)) < float(str(typed))
            except (ValueError, TypeError):
                return str(cell) < str(typed)
        if op == ">=":
            try:
                return float(str(cell)) >= float(str(typed))
            except (ValueError, TypeError):
                return str(cell) >= str(typed)
        if op == "<=":
            try:
                return float(str(cell)) <= float(str(typed))
            except (ValueError, TypeError):
                return str(cell) <= str(typed)
        return False

    _check = all if mode != "or" else any
    result = []
    for item in items:
        if _check(_matches(item, field, op, value) for field, op, value in compiled):
            result.append(item)
    return result


def _apply_grep(items: list[Any], pattern: str) -> list[Any]:
    """Return items where any leaf string value matches *pattern* (regex, case-insensitive)."""
    import re as _re
    try:
        rx = _re.compile(pattern, _re.IGNORECASE)
    except _re.error:
        rx = _re.compile(_re.escape(pattern), _re.IGNORECASE)

    def _leaf_strings(obj: Any):
        if isinstance(obj, dict):
            for v in obj.values():
                yield from _leaf_strings(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from _leaf_strings(v)
        elif obj is not None:
            yield str(obj)

    return [item for item in items if any(rx.search(s) for s in _leaf_strings(item))]


def _apply_unique(items: list[Any], field: str) -> list[Any]:
    """Deduplicate *items* by *field* value, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        key = str(item.get(field, "")) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _render_format_template(items: list[Any], template: str) -> None:
    """Print each item rendered through a template.

    Both placeholder styles are accepted:
      Go-style   {{.field}}  (dotted paths supported: {{.meta.total}})
      Simple     {field}     (used when no Go-style placeholder is present)
    """
    import re as _re
    _PLACEHOLDER = _re.compile(r"\{\{\.([^}]+)\}\}")
    _SIMPLE = _re.compile(r"\{([A-Za-z0-9_][A-Za-z0-9_.]*)\}")
    pattern = _PLACEHOLDER if _PLACEHOLDER.search(template) else _SIMPLE

    def _get_nested(obj: Any, dotted_key: str) -> Any:
        for part in dotted_key.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return None
        return obj

    single = not isinstance(items, list)
    rows = [items] if single else items
    for item in rows:
        def _sub(m: Any) -> str:
            val = _get_nested(item, m.group(1)) if isinstance(item, dict) else None
            return str(val) if val is not None else ""
        line = pattern.sub(_sub, template) + "\n"
        sys.stdout.write(line)
        tee_write(line)


def _enrich_domain_result(result: Any, client: Any) -> Any:
    """Resolve category and application IDs in a domain lookup response to names.

    Works for both user-lookup (single domain) and bulk-lookup (dict of domains).
    Replaces the relationships structure with plain name strings so the output
    renderer shows "Information Technology" instead of "(1 item)".
    """
    # Build lookup maps once, reused across all domains in the response
    id_to_cat: dict[str, str] = {}
    id_to_app: dict[str, str] = {}
    try:
        cats = client.get("/v1/categories/all")
        cats_list = cats if isinstance(cats, list) else (cats or {}).get("data", [])
        for c in cats_list or []:
            if isinstance(c, dict):
                cid = str(c.get("id", ""))
                name = (c.get("attributes") or {}).get("name") or c.get("name") or ""
                if cid and name:
                    id_to_cat[cid] = name
    except Exception:
        pass

    try:
        apps = client.get("/v1/applications/all")
        apps_list = apps if isinstance(apps, list) else (apps or {}).get("data", [])
        for a in apps_list or []:
            if isinstance(a, dict):
                aid = str(a.get("id", ""))
                name = (a.get("attributes") or {}).get("name") or a.get("name") or ""
                if aid and name:
                    id_to_app[aid] = name
    except Exception:
        pass

    def _resolve_domain_obj(obj: dict) -> dict:
        """Replace relationship id-lists with resolved name strings."""
        import copy
        obj = copy.deepcopy(obj)
        rels = obj.get("relationships", {})

        cat_ids = [str(c["id"]) for c in rels.get("categories",    {}).get("data", []) if c.get("id")]
        app_ids = [str(a["id"]) for a in rels.get("applications", {}).get("data", []) if a.get("id")]

        cat_names = [id_to_cat.get(cid, f"Category {cid}") for cid in cat_ids]
        app_names = [id_to_app.get(aid, f"Application {aid}") for aid in app_ids]

        # Replace the relationship block with plain resolved strings
        obj["categories"]    = ", ".join(cat_names) if cat_names else None
        obj["applications"]  = ", ".join(app_names) if app_names else None

        # Remove the raw relationships block so it doesn't clutter the output
        obj.pop("relationships", None)
        obj.pop("type", None)
        obj.pop("id",   None)

        return obj

    if not isinstance(result, dict):
        return result

    data = result.get("data")
    if data is None:
        return result

    # bulk-lookup: data is {"google.com": {...}, ...}
    if isinstance(data, dict) and not data.get("type"):
        enriched = {}
        for domain_name, domain_obj in data.items():
            if isinstance(domain_obj, dict):
                enriched[domain_name] = _resolve_domain_obj(domain_obj)
            else:
                enriched[domain_name] = domain_obj
        return {"data": enriched}

    # user-lookup: data is a single domain object
    if isinstance(data, dict):
        return {"data": _resolve_domain_obj(data)}

    return result
