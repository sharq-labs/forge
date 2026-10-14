"""An independent interpreter of the Blindfold law language (JSON trees), standard library only.

Written from the grammar specification, not from ``engcore.blindfold.expression``:

    {"const": k} {"var": name} {"add": [e, ...]} {"mul": [e, ...]} {"pow": [e, {"const": k}]}
    {"exp": e} {"log": e} {"neg": e} {"piecewise": {"if_below": [e, {"const": t}], "then": e, "else": e}}

Any non-finite or undefined value (log of a non-positive number, a negative base to a non-integer power, zero to a
negative power, overflow, a variable missing at the point) evaluates to NaN: never a guess.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

LIMIT_NODES = 96
LIMIT_DEPTH = 12


class ExpressionInvalid(ValueError):
    pass


def check(expr: Any, depth: int = 0, seen: list[int] | None = None) -> set[str]:
    """The variables an admissible expression uses; raises ExpressionInvalid outside the grammar or its limits."""
    seen = [0] if seen is None else seen
    seen[0] += 1
    if seen[0] > LIMIT_NODES or depth > LIMIT_DEPTH:
        raise ExpressionInvalid("expression exceeds the size limits")
    if not isinstance(expr, Mapping) or len(expr) != 1:
        raise ExpressionInvalid("a node is a one-key object")
    ((op, arg),) = expr.items()
    if op == "const":
        if isinstance(arg, bool) or not isinstance(arg, (int, float)) or not math.isfinite(float(arg)):
            raise ExpressionInvalid("a constant is a finite number")
        return set()
    if op == "var":
        if not isinstance(arg, str) or not arg:
            raise ExpressionInvalid("a variable is a non-empty name")
        return {arg}
    if op in ("add", "mul"):
        if not isinstance(arg, list) or len(arg) < 2:
            raise ExpressionInvalid(f"{op} takes two or more operands")
        out: set[str] = set()
        for a in arg:
            out |= check(a, depth + 1, seen)
        return out
    if op == "pow":
        if not isinstance(arg, list) or len(arg) != 2 or not isinstance(arg[1], Mapping) or set(arg[1]) != {"const"}:
            raise ExpressionInvalid("pow is [base, {const: exponent}]")
        return check(arg[0], depth + 1, seen) | check(arg[1], depth + 1, seen)
    if op in ("exp", "log", "neg"):
        return check(arg, depth + 1, seen)
    if op == "piecewise":
        if not isinstance(arg, Mapping) or set(arg) != {"if_below", "then", "else"}:
            raise ExpressionInvalid("piecewise is {if_below, then, else}")
        sw = arg["if_below"]
        if not isinstance(sw, list) or len(sw) != 2 or not isinstance(sw[1], Mapping) or set(sw[1]) != {"const"}:
            raise ExpressionInvalid("piecewise switches below a constant")
        return check(sw[0], depth + 1, seen) | check(sw[1], depth + 1, seen) | check(arg["then"], depth + 1, seen) \
            | check(arg["else"], depth + 1, seen)
    raise ExpressionInvalid(f"operator {op!r} is not in the grammar")


def value(expr: Mapping[str, Any], point: Mapping[str, float]) -> float:
    try:
        out = _value(expr, point)
    except (ArithmeticError, ValueError, KeyError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def _value(node: Mapping[str, Any], p: Mapping[str, float]) -> float:
    ((op, arg),) = node.items()
    if op == "const":
        return float(arg)
    if op == "var":
        return float(p[arg])
    if op == "add":
        return math.fsum(_value(a, p) for a in arg)
    if op == "mul":
        acc = 1.0
        for a in arg:
            acc *= _value(a, p)
        return acc
    if op == "pow":
        base, k = _value(arg[0], p), float(arg[1]["const"])
        if base < 0 and not k.is_integer():
            raise ValueError("negative base, non-integer power")
        if base == 0 and k < 0:
            raise ValueError("zero to a negative power")
        return math.pow(base, k)
    if op == "exp":
        return math.exp(_value(arg, p))
    if op == "log":
        x = _value(arg, p)
        if x <= 0:
            raise ValueError("log of a non-positive number")
        return math.log(x)
    if op == "neg":
        return -_value(arg, p)
    sw = arg["if_below"]
    return _value(arg["then"], p) if _value(sw[0], p) < float(sw[1]["const"]) else _value(arg["else"], p)
