"""Opt-in estimate of explicit-coupling splitting error by coupling-window refinement.

An explicit (staggered) coupled run feeds each participant lagged coupling
values, which introduces a splitting error that the run itself never sees.
:func:`estimate_splitting_error` re-executes the SAME coupled problem at the
base coupling window ``dt`` and at ``dt/2`` (and ``dt/4``) and applies
Richardson extrapolation to named scalar outputs at the horizon end:

* three levels -- the order of accuracy is OBSERVED, ``p = log2(d1 / d2)``
  with ``d1 = q(dt/2) - q(dt)`` and ``d2 = q(dt/4) - q(dt/2)``;
* two levels -- the order is DECLARED by the caller, with a stated basis
  (an order is never assumed by the runtime).

The base run's error is estimated as ``|d1| * 2^p / (2^p - 1)``.  A quantity
whose refinement is not in the asymptotic range (differences change sign or do
not shrink, or the observed order is not positive and finite) stays
UNQUANTIFIED with the reason.  The result is an ESTIMATE, never a bound: it
assumes the observed (or declared) order holds at the base window.

Every refined run must differ from the base only in its coupling window (same
graph, same plan otherwise, same end time); anything else is refused.  The
estimate is bound to the digest of the base run it was produced with, so
:func:`~engcore.execution.multiphysics.numerical_error.assess_coupling_numerical_error`
uses it for that exact run only.  Cost: 1 + 2 (+ 4) times the base run.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Mapping, Sequence

import sys

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import CouplingScheme, MultiphysicsRunRecord
from ...scientific.units.quantity import Quantity, base_unit
from .numerical_error import run_digest  # noqa: F401  (one digest rule, re-exported)
from .runtime import MultiphysicsRuntime

ESTIMATE_KIND = "coupling_splitting_error_estimate"
#: the round-off floor of the claims-layer refinement rule (claims.numerical_uq): below
#: 64 ulp of the largest value a difference is not resolved, and a zero would be invented
_ROUNDOFF_ULPS = 64.0


@dataclass(frozen=True)
class SplittingQuantityEstimate:
    quantity: str
    unit: str
    values: tuple[float, ...]
    observed_order: float | None
    relative: float | None
    detail: str

    @property
    def estimated(self) -> bool:
        return self.relative is not None

    def to_dict(self) -> dict[str, Any]:
        return {"quantity": self.quantity, "unit": self.unit, "values": list(self.values),
                "observed_order": self.observed_order, "relative": self.relative,
                "status": "estimated" if self.estimated else "unquantified", "detail": self.detail}


@dataclass(frozen=True)
class SplittingErrorEstimate:
    base_run_id: str
    base_run_digest: str
    windows_s: tuple[float, ...]
    order_basis: str
    quantities: tuple[SplittingQuantityEstimate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": ESTIMATE_KIND, "base_run_id": self.base_run_id, "base_run_digest": self.base_run_digest,
                "windows_s": list(self.windows_s), "order_basis": self.order_basis,
                "quantities": [q.to_dict() for q in self.quantities],
                "notice": ("Richardson estimate of explicit-coupling splitting error at the base window; an "
                           "estimate, not a bound, and not physical or model-form uncertainty.")}


def _plan_without_window(runtime: MultiphysicsRuntime) -> dict[str, Any]:
    payload = runtime.plan.to_dict()
    time = dict(payload["time"])
    time.pop("coupling_window")
    payload["time"] = time
    return payload


def _value(run: MultiphysicsRunRecord, quantity: str, unit: str | None) -> tuple[float, str]:
    raw = run.final_outputs.get(quantity)
    if not isinstance(raw, Mapping) or "magnitude" not in raw or "units" not in raw:
        raise InvalidScientificProblem(
            f"splitting estimate compares scalar outputs; {quantity!r} is not a scalar output of run {run.run_id!r}"
        )
    value = Quantity.from_dict(raw)
    target = unit or base_unit(str(value.units))
    return value.magnitude_in(target), target


def _estimate(quantity: str, unit: str, values: list[float], order: float | None, basis_observed: bool) -> SplittingQuantityEstimate:
    v0, v1 = values[0], values[1]
    d1 = v1 - v0
    floor = _ROUNDOFF_ULPS * sys.float_info.epsilon * max(abs(v) for v in values)
    if abs(d1) <= floor:
        # identical (or round-off-equal) levels resolve no order: a zero-width estimate would be invented
        return SplittingQuantityEstimate(
            quantity, unit, tuple(values), None, None,
            f"the first refinement difference {d1!r} is at round-off ({floor:.3g}); no estimate is made",
        )
    if basis_observed:
        d2 = values[2] - v1
        if abs(d2) <= floor or d2 / d1 <= 0.0 or abs(d2) >= abs(d1):
            return SplittingQuantityEstimate(
                quantity, unit, tuple(values), None, None,
                f"not in the asymptotic range: successive refinements differ by {d1!r} then {d2!r}",
            )
        else:
            order = math.log2(d1 / d2)
            if not math.isfinite(order) or order <= 0.0:
                return SplittingQuantityEstimate(quantity, unit, tuple(values), None, None,
                                                 f"observed order {order!r} is not positive and finite")
            error = abs(d1) * 2.0 ** order / (2.0 ** order - 1.0)
    else:
        assert order is not None
        error = abs(d1) * 2.0 ** order / (2.0 ** order - 1.0)
    if v0 == 0.0:
        return SplittingQuantityEstimate(quantity, unit, tuple(values), order, None,
                                         "base value is zero in the ratio-scale unit: no relative error is defined")
    relative = error / abs(v0)
    if not math.isfinite(relative):
        return SplittingQuantityEstimate(quantity, unit, tuple(values), order, None, "estimate is not finite")
    return SplittingQuantityEstimate(
        quantity, unit, tuple(values), order, relative,
        f"Richardson estimate of the base-window error with p = {order:.6g} (an estimate; no safety factor, "
        f"not the claims-layer GCI)",
    )


def estimate_splitting_error(
    build: Callable[[Quantity], MultiphysicsRuntime],
    *,
    coupling_window: Quantity,
    run_id: str,
    run_kwargs: Mapping[str, Any],
    quantities: Sequence[str],
    levels: int = 3,
    declared_order: float | None = None,
    declared_order_basis: str = "",
) -> tuple[MultiphysicsRunRecord, SplittingErrorEstimate]:
    """Run the base problem and its refinements; return the base run and its splitting estimate.

    ``build(window)`` must construct a fresh runtime for the same problem with
    the given coupling window (fresh participants: runs must not share state).
    ``run_kwargs`` are passed to every ``run`` call.  ``quantities`` name
    scalar outputs ``"participant.port"`` compared at the horizon end.
    """
    if levels not in (2, 3):
        raise InvalidScientificProblem("splitting estimate uses 2 or 3 refinement levels")
    if levels == 2:
        if declared_order is None or not str(declared_order_basis).strip():
            raise InvalidScientificProblem(
                "two refinement levels cannot observe an order: declare it, with its basis"
            )
        if not math.isfinite(float(declared_order)) or float(declared_order) <= 0.0:
            raise InvalidScientificProblem("declared order must be finite and positive")
    elif declared_order is not None:
        raise InvalidScientificProblem("three refinement levels observe the order; do not also declare one")
    names = tuple(str(q).strip() for q in quantities)
    if not names or any(not q for q in names) or len(set(names)) != len(names):
        raise InvalidScientificProblem("splitting estimate needs unique, non-empty quantity names")
    if not isinstance(coupling_window, Quantity):
        raise InvalidScientificProblem("coupling_window must be a time Quantity")
    window_s = coupling_window.magnitude_in("second")

    runs: list[MultiphysicsRunRecord] = []
    reference_graph: dict[str, Any] | None = None
    reference_plan: dict[str, Any] | None = None
    windows: list[float] = []
    for level in range(levels):
        expected = window_s / (2 ** level)
        runtime = build(Quantity(expected, "second"))
        if not isinstance(runtime, MultiphysicsRuntime):
            raise InvalidScientificProblem("build must return a MultiphysicsRuntime")
        if runtime.plan.scheme is not CouplingScheme.EXPLICIT:
            raise InvalidScientificProblem("splitting estimate applies to explicit coupling only")
        actual = runtime.plan.time.coupling_window.magnitude_in("second")
        if abs(actual - expected) > 1e-12 * max(1.0, expected):
            raise InvalidScientificProblem(
                f"refinement level {level} built a {actual!r} s window, expected {expected!r} s"
            )
        graph, plan = runtime.graph.to_dict(), _plan_without_window(runtime)
        if reference_graph is None:
            reference_graph, reference_plan = graph, plan
        elif graph != reference_graph or plan != reference_plan:
            raise InvalidScientificProblem(
                f"refinement level {level} changed the problem, not only its coupling window"
            )
        level_id = run_id if level == 0 else f"{run_id}:splitting-refinement-{level}"
        runs.append(runtime.run(level_id, **dict(run_kwargs)))
        windows.append(expected)

    end = runs[0].ended_at.magnitude_in("second")
    for run in runs[1:]:
        if abs(run.ended_at.magnitude_in("second") - end) > 1e-12 * max(1.0, abs(end)):
            raise InvalidScientificProblem("refined runs ended at another instant than the base run")

    estimates = []
    for name in names:
        base_value, unit = _value(runs[0], name, None)
        values = [base_value] + [_value(run, name, unit)[0] for run in runs[1:]]
        estimates.append(_estimate(name, unit, values, declared_order, levels == 3))

    basis = ("observed from three refinement levels" if levels == 3
             else f"declared order {float(declared_order):g}: {declared_order_basis}")
    return runs[0], SplittingErrorEstimate(runs[0].run_id, run_digest(runs[0]), tuple(windows), basis, tuple(estimates))
