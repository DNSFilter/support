"""Adversarial tests for the --transform AST sandbox (postprocess).

The sandbox's whole job is to block attribute/dunder/comprehension/lambda
escapes and DoS operators while allowing arithmetic on result fields. Previously
only the ** operator was tested, so adding ast.Attribute to the allowlist (or
deleting the __-name guard) would have escaped to arbitrary code with the suite
still green. These drive the REAL compiler _compile_transform_expr.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dnsfcli.postprocess import _apply_transforms, _compile_transform_expr


@pytest.mark.parametrize("expr", [
    "().__class__",
    "x.__class__.__bases__",
    "().__class__.__bases__[0].__subclasses__()",
    "__import__('os')",
    "getattr(x, 'y')",
    "[a for a in b]",
    "{k: v for k, v in x}",
    "(lambda: 1)()",
    "x.foo",
    "9 ** 9",
    "2 ** 2 ** 30",
    '"a" * 1000000000',      # sequence-repetition DoS (L1)
    "[0] * 1000000000",
    "(0,) * 1000000000",
    "open('/etc/passwd')",
    "eval('1')",
    "globals()",
])
def test_sandbox_rejects_escape_and_dos(expr):
    with pytest.raises((ValueError, SyntaxError)):
        _compile_transform_expr(expr)


@pytest.mark.parametrize("expr", [
    "blocked / total",
    "(a + b) * 2",
    "min(a, b)",
    "max(a, b)",
    "abs(x)",
    "round(x, 2)",
    "int(x) + 1",
    "str(x)",
    "len(name)",
    "x if x else y",
])
def test_sandbox_allows_benign_arithmetic(expr):
    # Must compile without raising.
    _compile_transform_expr(expr)


def test_transform_cannot_read_process_state_via_field_named_like_builtin():
    """A field value is data, never callable — even if named like a builtin."""
    items = [{"int": "not-callable", "n": 5}]
    # int(n) would call the field 'int' (shadowing the builtin) if resolution
    # were unsafe; the field is a str, so it fails gracefully (row unchanged).
    out = _apply_transforms(items, ["y=int(n)"])
    # No crash, no escape; the row is either transformed (if builtin used) or
    # left unchanged (if shadowed) — never executes arbitrary code.
    assert isinstance(out, list) and len(out) == 1


def test_transform_computes_real_value():
    out = _apply_transforms([{"blocked": 30, "total": 100}], ["ratio=blocked/total"])
    assert out[0]["ratio"] == 0.3
