"""Phase 2A -- numerical uncertainty from a declared refinement study, or UNKNOWN.

A discretized solution differs from the exact solution of its own declared
model. Where the solver is in its asymptotic range, a sequence of solutions at
systematically refined resolution measures that difference: Richardson's
extrapolation with the observed order of convergence, reported conservatively
as Roache's Grid Convergence Index (GCI). Where the sequence does not show that
behaviour, the numbers measure nothing and the answer is ``UNKNOWN`` -- never
zero, and never a percentage chosen here.

What the estimate is, and is not
--------------------------------
* ``source_kind = NUMERICAL``: the record is about the *solution's* error with
  respect to the declared model. It says nothing about parameters, the
  measurement, or whether the model is the right one; the channel table files it
  under NUMERICAL only, so it can never satisfy a MODEL_FORM demand.
* It is an INTERVAL ``[f1 - U, f1 + U]`` around the finest value ``f1`` with
  ``U = Fs * |f2 - f1| / (r**p - 1)``. No confidence level is claimed: the
  GCI's safety factor is an engineering convention for coverage, not a
  probability computed here, and the record's ``method`` says so.

The rules (every one a reason for UNKNOWN when it fails)
--------------------------------------------------------
1. At least three levels, finest first, at one constant refinement ratio
   ``r > 1`` declared by the capability (never inferred from the values).
2. Every value finite.
3. The finest difference is above round-off (``64 * eps * max|f|``); below it
   the order is undetermined, and a zero-width answer would be invented.
4. **Monotone convergence**: successive differences have one sign and shrink,
   so ``e_{k+1} / e_k > 1``. Oscillatory or diverging sequences are refused.
5. **Asymptotic range**: the observed order ``p`` is within the declared
   ``order_tolerance`` of the scheme's declared formal order, and -- with four
   or more levels -- successive observed orders agree within the same
   tolerance.
6. The order used is ``min(p_observed, p_formal)``: a smaller order gives the
   larger (conservative) estimate. ``Fs = 1.25``, Roache's value for studies of
   three or more levels.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from ..scientific.units.quantity import Quantity
from ._records import tagged_digest
from .errors import ClaimLayerError

#: Roache's GCI safety factor for a study of three or more levels.
GCI_SAFETY_FACTOR = 1.25
_ROUNDOFF_ULPS = 64.0
METHOD = "richardson_gci"
_TAG = "crafty.claims.numerical_uq/1"


class NumericalUQError(ClaimLayerError):
    """A refinement study was declared or supplied in a form no estimate can be read from."""


class EstimateStatus(str, Enum):
    QUANTIFIED = "quantified"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RefinementLevel:
    """One solution of the sequence. ``level`` 0 is the finest (the reported run)."""

    level: int
    value: float | None  # None: the level produced no usable value
    resolution: dict[str, int]
    run_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "value": self.value, "resolution": dict(sorted(self.resolution.items())), "run_id": self.run_id}


@dataclass(frozen=True)
class NumericalUncertaintyEstimate:
    """The study's answer: a quantified NUMERICAL interval, or UNKNOWN and why."""

    status: EstimateStatus
    quantity: str
    units: str
    levels: tuple[RefinementLevel, ...]
    refinement_ratio: float
    formal_order: float
    order_tolerance: float
    observed_orders: tuple[float, ...]
    order_used: float | None
    richardson_extrapolate: float | None
    error_estimate: float | None
    half_width: float | None
    failure_reason: str | None
    assumptions: tuple[str, ...]

    @property
    def quantified(self) -> bool:
        return self.status is EstimateStatus.QUANTIFIED

    def to_uncertainty(self) -> Uncertainty:
        """The Core record. UNKNOWN stays UNKNOWN, with the reason, and is never zero."""
        if not self.quantified:
            return Uncertainty.unknown(f"numerical uncertainty not quantified: {self.failure_reason}")
        f1 = self.levels[0].value
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(f1 - self.half_width, self.units),
            upper=Quantity(f1 + self.half_width, self.units),
            source=f"refinement_study:{self.digest[:16]}",
            method=(
                f"{METHOD}: {len(self.levels)}-level refinement, r={self.refinement_ratio:g}, "
                f"p_observed={self.observed_orders[0]:.4g}, p_used={self.order_used:.4g}, Fs={GCI_SAFETY_FACTOR}; "
                f"no coverage probability is claimed"
            ),
            notes="discretization error of the declared model's solution; not parameter, measurement or model-form uncertainty",
            source_kind=UncertaintySource.NUMERICAL,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": METHOD,
            "status": self.status.value,
            "quantity": self.quantity,
            "units": self.units,
            "levels": [level.to_dict() for level in self.levels],
            "refinement_ratio": self.refinement_ratio,
            "formal_order": self.formal_order,
            "order_tolerance": self.order_tolerance,
            "observed_orders": list(self.observed_orders),
            "order_used": self.order_used,
            "safety_factor": GCI_SAFETY_FACTOR,
            "richardson_extrapolate": self.richardson_extrapolate,
            "error_estimate": self.error_estimate,
            "half_width": self.half_width,
            "failure_reason": self.failure_reason,
            "assumptions": list(self.assumptions),
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


_ASSUMPTIONS = (
    "every level solves the same declared model at the same operating point; only resolution changes",
    "all refined resolutions scale together by one constant ratio",
    "the error behaves as C*h**p over the finest levels (asymptotic range), checked by the observed order",
    "iteration and round-off errors are small beside discretization error (round-off floor checked)",
)


def estimate_numerical_uncertainty(
    levels: Sequence[RefinementLevel],
    *,
    quantity: str,
    units: str,
    refinement_ratio: float,
    formal_order: float,
    order_tolerance: float,
) -> NumericalUncertaintyEstimate:
    """Apply the module's rules to a finest-first sequence. Pure; UNKNOWN is a result, not an exception."""
    for label, number in (("refinement_ratio", refinement_ratio), ("formal_order", formal_order), ("order_tolerance", order_tolerance)):
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number <= 0:
            raise NumericalUQError(f"{label} must be a finite positive number, got {number!r}")
    if refinement_ratio <= 1.0:
        raise NumericalUQError("refinement_ratio must exceed 1: a refinement that does not refine measures nothing")
    ordered = tuple(sorted(levels, key=lambda lv: lv.level))
    if [lv.level for lv in ordered] != list(range(len(ordered))):
        raise NumericalUQError("levels must be numbered 0 (finest) .. n-1 with none missing")

    base = dict(
        quantity=quantity, units=units, levels=ordered, refinement_ratio=float(refinement_ratio),
        formal_order=float(formal_order), order_tolerance=float(order_tolerance), assumptions=_ASSUMPTIONS,
    )

    def unknown(reason: str, orders: tuple[float, ...] = ()) -> NumericalUncertaintyEstimate:
        return NumericalUncertaintyEstimate(
            status=EstimateStatus.UNKNOWN, observed_orders=orders, order_used=None, richardson_extrapolate=None,
            error_estimate=None, half_width=None, failure_reason=reason, **base,
        )

    if len(ordered) < 3:
        return unknown(f"{len(ordered)} level(s); an observed order needs at least three")
    values = [lv.value for lv in ordered]
    if any(v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return unknown("a level produced no finite value")
    diffs = [values[k + 1] - values[k] for k in range(len(values) - 1)]
    floor = _ROUNDOFF_ULPS * sys.float_info.epsilon * max(abs(v) for v in values)
    if abs(diffs[0]) <= floor:
        return unknown(
            f"the finest difference |f2 - f1| = {abs(diffs[0]):.3g} is at round-off ({floor:.3g}); "
            f"the order is undetermined and a zero-width interval would be invented"
        )
    orders: list[float] = []
    for k in range(len(diffs) - 1):
        if diffs[k] == 0.0:
            return unknown(f"levels {k} and {k + 1} agree exactly while coarser ones do not; not a convergent sequence", tuple(orders))
        ratio = diffs[k + 1] / diffs[k]
        if ratio <= 0.0:
            return unknown(f"oscillatory convergence between levels {k}..{k + 2} (successive differences change sign)", tuple(orders))
        if ratio <= 1.0:
            return unknown(f"differences do not shrink with refinement between levels {k}..{k + 2} (ratio {ratio:.4g})", tuple(orders))
        orders.append(math.log(ratio) / math.log(refinement_ratio))
    observed = tuple(orders)
    p = observed[0]
    if abs(p - formal_order) > order_tolerance:
        return unknown(
            f"observed order {p:.4g} is outside the declared formal order {formal_order:g} +/- {order_tolerance:g}; "
            f"the finest levels are not shown to be in the asymptotic range",
            observed,
        )
    for k in range(1, len(observed)):
        if abs(observed[k] - observed[k - 1]) > order_tolerance:
            return unknown(
                f"observed orders {observed[k - 1]:.4g} and {observed[k]:.4g} disagree by more than {order_tolerance:g}",
                observed,
            )
    used = min(p, formal_order)
    error = diffs[0] / (refinement_ratio ** used - 1.0)
    half = GCI_SAFETY_FACTOR * abs(error)
    return NumericalUncertaintyEstimate(
        status=EstimateStatus.QUANTIFIED,
        observed_orders=observed,
        order_used=used,
        richardson_extrapolate=values[0] - error,
        error_estimate=error,
        half_width=half,
        failure_reason=None,
        **base,
    )


def estimate_from_dict(payload: dict[str, Any]) -> NumericalUncertaintyEstimate:
    """Re-derive an estimate from its recorded inputs. The recorded outputs must match or it is refused."""
    try:
        levels = tuple(
            RefinementLevel(int(lv["level"]), None if lv["value"] is None else float(lv["value"]), {str(k): int(v) for k, v in lv["resolution"].items()}, str(lv["run_id"]))
            for lv in payload["levels"]
        )
        rebuilt = estimate_numerical_uncertainty(
            levels,
            quantity=payload["quantity"],
            units=payload["units"],
            refinement_ratio=payload["refinement_ratio"],
            formal_order=payload["formal_order"],
            order_tolerance=payload["order_tolerance"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NumericalUQError(f"a numerical-uncertainty record is not readable: {exc}") from exc
    if rebuilt.to_dict() != dict(payload):
        raise NumericalUQError("a numerical-uncertainty record does not re-derive from the levels it carries")
    return rebuilt


__all__ = [
    "GCI_SAFETY_FACTOR",
    "EstimateStatus",
    "NumericalUQError",
    "NumericalUncertaintyEstimate",
    "RefinementLevel",
    "estimate_from_dict",
    "estimate_numerical_uncertainty",
]
