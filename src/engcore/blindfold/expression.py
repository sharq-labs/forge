"""A restricted expression language for laws: the only form in which a proposal reaches the escrow.

A proposer's law is DATA (a JSON tree), never code: the escrow interprets it
with this module and nothing a proposer sends can execute.  Limits on depth
and node count bound the work one proposal can demand.

Grammar (JSON)::

    {"const": 1.5}
    {"var": "x1"}
    {"add": [e, e, ...]}       {"mul": [e, e, ...]}
    {"pow": [e, {"const": k}]}  (exponent is a constant)
    {"exp": e}  {"log": e}  {"neg": e}
    {"piecewise": {"if_below": [e_switch, {"const": t}], "then": e, "else": e}}

:func:`structure_digest` is the canonical STRUCTURE identity used for
de-duplication and the novelty check: constants are abstracted and every
product of powers is merged into one monomial with combined exponents, so two
laws differing only in constants -- or only in how a power law is written --
share a structure.  It is a canonicalization, not a proof of equivalence:
rewrites outside the monomial algebra (e.g. ``exp(log x)``) are not merged;
:class:`engcore.claims.novelty.EquivalenceSpec` covers those numerically.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

MAX_DEPTH = 12
MAX_NODES = 96
_UNARY = ("exp", "log", "neg")
_NARY = ("add", "mul")


class ExpressionRefused(ValueError):
    """An expression outside the grammar or its limits."""


def _check(node: Any, depth: int, count: list[int], variables: set[str]) -> None:
    count[0] += 1
    if count[0] > MAX_NODES:
        raise ExpressionRefused(f"expression exceeds {MAX_NODES} nodes")
    if depth > MAX_DEPTH:
        raise ExpressionRefused(f"expression exceeds depth {MAX_DEPTH}")
    if not isinstance(node, Mapping) or len(node) != 1:
        raise ExpressionRefused("every expression node is a one-key object")
    (op, arg), = node.items()
    if op == "const":
        if isinstance(arg, bool) or not isinstance(arg, (int, float)) or not math.isfinite(float(arg)):
            raise ExpressionRefused("a constant is a finite number")
    elif op == "var":
        if not isinstance(arg, str) or not arg:
            raise ExpressionRefused("a variable is a non-empty name")
        variables.add(arg)
    elif op in _NARY:
        if not isinstance(arg, list) or len(arg) < 2:
            raise ExpressionRefused(f"{op} takes at least two operands")
        for a in arg:
            _check(a, depth + 1, count, variables)
    elif op == "pow":
        if not isinstance(arg, list) or len(arg) != 2 or not isinstance(arg[1], Mapping) or set(arg[1]) != {"const"}:
            raise ExpressionRefused("pow is [base, {'const': exponent}]")
        _check(arg[0], depth + 1, count, variables)
        _check(arg[1], depth + 1, count, variables)
    elif op in _UNARY:
        _check(arg, depth + 1, count, variables)
    elif op == "piecewise":
        if not isinstance(arg, Mapping) or set(arg) != {"if_below", "then", "else"}:
            raise ExpressionRefused("piecewise is {if_below: [switch, {const: t}], then, else}")
        sw = arg["if_below"]
        if not isinstance(sw, list) or len(sw) != 2 or not isinstance(sw[1], Mapping) or set(sw[1]) != {"const"}:
            raise ExpressionRefused("piecewise switches below a constant")
        for a in (sw[0], sw[1], arg["then"], arg["else"]):
            _check(a, depth + 1, count, variables)
    else:
        raise ExpressionRefused(f"operator {op!r} is not in the grammar")


def validate(expr: Mapping[str, Any]) -> frozenset[str]:
    """Check the grammar and limits; return the variables used."""
    variables: set[str] = set()
    _check(expr, 0, [0], variables)
    return frozenset(variables)


def evaluate(expr: Mapping[str, Any], point: Mapping[str, float]) -> float:
    """Evaluate at one point.  Non-finite results (log of a non-positive number, overflow) return NaN, never a guess."""
    try:
        return float(_eval(expr, point))
    except (ValueError, OverflowError, ZeroDivisionError):
        return float("nan")


def _eval(node: Mapping[str, Any], p: Mapping[str, float]) -> float:
    (op, arg), = node.items()
    if op == "const":
        return float(arg)
    if op == "var":
        if arg not in p:
            raise ValueError(f"variable {arg!r} is not available at this point")
        return float(p[arg])
    if op == "add":
        return math.fsum(_eval(a, p) for a in arg)
    if op == "mul":
        out = 1.0
        for a in arg:
            out *= _eval(a, p)
        return out
    if op == "pow":
        base, k = _eval(arg[0], p), float(arg[1]["const"])
        if base < 0 and not float(k).is_integer():
            raise ValueError("negative base to a non-integer power")
        if base == 0 and k < 0:
            raise ValueError("zero to a negative power")
        return base ** k
    if op == "exp":
        return math.exp(_eval(arg, p))
    if op == "log":
        v = _eval(arg, p)
        if v <= 0:
            raise ValueError("log of a non-positive number")
        return math.log(v)
    if op == "neg":
        return -_eval(arg, p)
    sw = arg["if_below"]
    return _eval(arg["then"], p) if _eval(sw[0], p) < float(sw[1]["const"]) else _eval(arg["else"], p)


def _key(x: Any) -> str:
    return json.dumps(x, sort_keys=True)


def _monomial_of(node: Mapping[str, Any]) -> dict[str, float]:
    """A node as a product of powers: canonical base -> combined exponent.  Constant factors (and negation) are dropped:
    structure is identity UP TO CONSTANTS.  ``pow`` distributes over a product (laws here live on positive domains)."""
    (op, arg), = node.items()
    if op == "const":
        return {}
    if op == "neg":
        return _monomial_of(arg)
    if op == "mul":
        out: dict[str, float] = {}
        for a in arg:
            for base, k in _monomial_of(a).items():
                out[base] = out.get(base, 0.0) + k
        return out
    if op == "pow":
        k = float(arg[1]["const"])
        return {base: e * k for base, e in _monomial_of(arg[0]).items()}
    return {_key(_atom(node)): 1.0}


def _atom(node: Mapping[str, Any]) -> Any:
    (op, arg), = node.items()
    if op == "var":
        return ["v", arg]
    if op == "add":
        terms = {_key(_structure(a)) for a in arg}             # a repeated term differs only by a constant
        return ["add", *sorted(terms)]
    if op in ("exp", "log"):
        return [op, _structure(arg)]
    if op == "piecewise":
        return ["piecewise", _structure(arg["if_below"][0]), _structure(arg["then"]), _structure(arg["else"])]
    raise ExpressionRefused(f"no atom form for {op!r}")  # pragma: no cover - const/neg/mul/pow are monomial forms


def _structure(node: Mapping[str, Any]) -> Any:
    """Canonical form: every product of powers becomes ONE monomial {base: combined exponent (3 d.p.)} with constants
    abstracted, so ``(x^a y^b)^e`` and ``x^(a e) y^(b e)`` -- or ``x^0.37 * x * 5`` and ``2 x^1.37`` -- are one structure."""
    mono = {b: round(k, 3) for b, k in _monomial_of(node).items()}
    mono = {b: k for b, k in mono.items() if k != 0.0}
    if not mono:
        return "c"
    if len(mono) == 1:
        (base, k), = mono.items()
        if k == 1.0:
            return json.loads(base)
    return ["mono", [[b, mono[b]] for b in sorted(mono)]]


def structure_digest(expr: Mapping[str, Any]) -> str:
    """Canonical structure identity: constants abstracted, products of powers merged into one monomial with combined
    exponents (3 d.p.), commutative operands sorted.  Algebraically identical power-law rewrites share a digest."""
    validate(expr)
    return hashlib.sha256(json.dumps(_structure(expr), sort_keys=True).encode()).hexdigest()


def content_digest(expr: Mapping[str, Any]) -> str:
    validate(expr)
    return hashlib.sha256(json.dumps(expr, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# -- builders (readability in generators/tests) -------------------------------------------------------------------
def c(v: float) -> dict:
    return {"const": float(v)}


def v(name: str) -> dict:
    return {"var": name}


def mul(*a: dict) -> dict:
    return {"mul": list(a)}


def add(*a: dict) -> dict:
    return {"add": list(a)}


def pw(base: dict, k: float) -> dict:
    return {"pow": [base, c(k)]}


__all__ = ["ExpressionRefused", "MAX_DEPTH", "MAX_NODES", "add", "c", "content_digest", "evaluate", "mul", "pw", "structure_digest",
           "v", "validate"]
