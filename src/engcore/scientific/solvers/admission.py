"""Admitting a provider's numbers before anything interprets them.

The defect
----------
An adapter that reaches an external provider has to reconcile what came back
against something it declared, before those numbers become metrics. Every such
reconciliation is a tolerance comparison, and every tolerance comparison looks
like this::

    if abs(actual - expected) > atol + rtol * abs(expected):
        raise ...

**That comparison is False for NaN.** ``nan - x`` is ``nan``, ``abs(nan)`` is
``nan``, and ``nan > anything`` is False — so a provider returning NaN does not
disagree with anything, and walks through a gate written to catch exactly the
provider that disagrees. Infinity does the same whenever both operands are
infinite: ``abs(inf - inf)`` is ``nan``, and the comparison is False again.

That is not a quirk of one adapter's arithmetic. It is a property of the shape,
which means every gate of this shape that anyone writes has the hole, and the
hole is invisible in the code — the line reads like a check and is one, for
every value except the ones that are not numbers.

The rule
--------
**Finiteness first, then agreement.** A non-finite provider number is refused
before any comparison is attempted, because a comparison is the one thing that
cannot detect it.

``RawSolverOutput`` remains the sanctioned home for non-finite values, and this
does not change that: a diverged solve genuinely produces NaN and an adapter
that hid it would be lying about what happened. What this refuses is a
non-finite number *being admitted* — passing a gate and becoming a metric, a
transported coupling input, a number a downstream loop converges around.
``Quantity`` refuses non-finite magnitudes for the same reason, one layer
further on; this closes the gap between the two, which is exactly where a
tolerance comparison sits.

Why in the core
---------------
Because the hole is in the shape of the comparison, not in any domain's
physics. One adapter has this gate today and its numbers are transported into a
thermal coupling. The next provider adapter will write the same four lines, and
a rule that lives in this one's private method will not be there when it does.
"""

from __future__ import annotations

import math
from typing import Callable, Mapping

__all__ = ["require_finite", "require_agreement"]


def require_finite(
    values: Mapping[str, float],
    *,
    error: Callable[[str], Exception],
    source: str,
) -> None:
    """Refuse any non-finite number among ``values``.

    ``values`` maps a name a reader will recognise to the number itself.
    ``error`` is the caller's own exception type, so a refusal arrives as the
    failure category that caller already documents — for a provider adapter
    that is "the provider ran and did not deliver what was asked", which is
    what a NaN is. ``source`` names where the numbers came from.

    Called **before** any tolerance comparison, never after: a comparison
    cannot detect what it is being asked to detect here.
    """
    offenders = sorted(
        f"{name}={value!r}"
        for name, value in values.items()
        if not math.isfinite(float(value))
    )
    if offenders:
        raise error(
            f"{source} returned non-finite value(s) {offenders}. A NaN or an "
            f"infinity satisfies every tolerance comparison written against it "
            f"-- abs(nan - x) > tol is False -- so it cannot be admitted and "
            f"then checked; it is refused here, before anything compares it"
        )


def require_agreement(
    *,
    actual: float,
    expected: float,
    atol: float,
    rtol: float,
    error: Callable[[str], Exception],
    detail: str,
    operands: Mapping[str, float] | None = None,
) -> None:
    """Refuse a disagreement, and refuse a non-finite operand first.

    ``detail`` is the caller's own message about what the two numbers are and
    why their agreement matters; it is used verbatim, because only the caller
    knows which physical relation is being reconciled.

    ``operands`` are the further numbers the comparison was derived from — a
    voltage drop and a resistance behind an expected current, say. They are
    checked for finiteness too, because an expected value computed from an
    infinity can come out finite and a gate that only looked at its own two
    operands would admit it.

    The finiteness check is not an early-out for tidiness. It is the check the
    comparison below **cannot** perform, and putting it after the comparison
    would put it after the thing it exists to catch.
    """
    # THE BOUND IS CHECKED BEFORE THE OPERANDS, because a malformed bound
    # defeats the comparison more completely than a malformed operand does.
    #
    # `atol + rtol * abs(expected)` is NaN if either tolerance is NaN, and
    # `anything > nan` is False -- so a NaN tolerance admits every disagreement
    # in existence while the two operands are perfectly finite and the
    # finiteness check below passes. An infinite tolerance does the same thing
    # arithmetically honestly: every difference is inside it.
    #
    # Negative tolerances are refused in the other direction. They do not
    # create false agreement, they create false disagreement -- but a bound
    # below zero is not a bound anybody meant, and admitting it would leave the
    # gate's behaviour depending on a number nobody can defend.
    for label, bound in (("atol", atol), ("rtol", rtol)):
        value = float(bound)
        if not math.isfinite(value) or value < 0.0:
            raise error(
                f"{detail}: {label}={bound!r} is not a usable tolerance. A "
                f"tolerance must be finite and non-negative -- a NaN bound "
                f"makes `abs(actual - expected) > atol + rtol * abs(expected)` "
                f"False for EVERY pair of operands, so the gate admits every "
                f"disagreement while looking exactly like a working check, and "
                f"an infinite one admits them arithmetically. The bound is "
                f"checked before the operands because a comparison cannot "
                f"detect the bound that disabled it"
            )

    checked: dict[str, float] = {"actual": float(actual), "expected": float(expected)}
    checked.update({str(k): float(v) for k, v in (operands or {}).items()})
    require_finite(checked, error=error, source=detail)

    if abs(actual - expected) > (atol + rtol * abs(expected)):
        raise error(detail)
