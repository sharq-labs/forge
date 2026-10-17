"""Adaptive resolution: refine until the canonical numerical-uncertainty estimate meets a declared target.

Adaptive mesh control, slice 1 (active-epic exception EXC-1).  A refinement
study (:mod:`.uq_studies`) measures the numerical uncertainty of a run whose
resolution was fixed in advance.  This module decides the resolution instead.
It solves at ``baseline * ratio**k`` for k = 0, 1, 2, ... and, after every new
level, applies the CANONICAL estimator
(:func:`.numerical_uq.estimate_numerical_uncertainty`, Richardson / GCI with
its rules) to the three finest levels.  It stops as soon as that estimate is
QUANTIFIED with a half-width within the declared target, or when the declared
level budget is spent.

What the result is, and is not
------------------------------
* The reported value is the FINEST level actually run.  Its uncertainty is the
  canonical NUMERICAL interval of that level, or UNKNOWN.
* ``TARGET_MET`` is stated only when the quantified half-width is within the
  target.  ``BUDGET_EXHAUSTED`` keeps the quantified interval and says it
  exceeds the target.  ``UNKNOWN`` means no level sequence gave a quantified
  estimate (pre-asymptotic, oscillating, at round-off) or a level was unusable.
  An unusable level ends the search: it is never skipped over.
* A met target is a numerical-accuracy statement about the declared model's
  solution.  It is not validation, and it never promotes a capability stage.
* Uniform refinement only: every refined count is multiplied by the same ratio.
  Local (non-uniform) refinement is a later slice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity, require_spread_unit
from .errors import ClaimLayerError
from .numerical_uq import NumericalUncertaintyEstimate, RefinementLevel, estimate_numerical_uncertainty


class AdaptiveResolutionError(ClaimLayerError):
    """An adaptive-resolution policy or level run is malformed."""


class AdaptiveResolutionStatus(str, Enum):
    TARGET_MET = "target_met"
    BUDGET_EXHAUSTED = "budget_exhausted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AdaptiveResolutionPolicy:
    """The declared search: baseline counts, ratio, level budget, scheme order and the accuracy target."""

    refined_inputs: Mapping[str, int]
    ratio: int
    max_levels: int
    formal_order: float
    order_tolerance: float
    target_half_width: Quantity
    basis: str

    def __post_init__(self) -> None:
        refined = {}
        for path, value in dict(self.refined_inputs).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AdaptiveResolutionError(f"baseline count {path!r} must be a positive integer")
            refined[str(path).strip()] = value
        if not refined or any(not path for path in refined):
            raise AdaptiveResolutionError("an adaptive resolution search refines at least one named count")
        object.__setattr__(self, "refined_inputs", dict(sorted(refined.items())))
        if isinstance(self.ratio, bool) or not isinstance(self.ratio, int) or self.ratio < 2:
            raise AdaptiveResolutionError("ratio must be an integer >= 2")
        if isinstance(self.max_levels, bool) or not isinstance(self.max_levels, int) or not 3 <= self.max_levels <= 12:
            raise AdaptiveResolutionError("max_levels must be an int in [3, 12]: an observed order needs three solutions")
        for label in ("formal_order", "order_tolerance"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise AdaptiveResolutionError(f"{label} must be a finite positive number")
            object.__setattr__(self, label, float(value))
        if not isinstance(self.target_half_width, Quantity):
            raise AdaptiveResolutionError("target_half_width must be a Quantity in the quantity's unit family")
        # a half-width is a spread: stated on a ratio scale or a difference unit (degC is refused, delta_degC is not)
        require_spread_unit(str(self.target_half_width.units), context="target_half_width")
        if not self.target_half_width.magnitude > 0:
            raise AdaptiveResolutionError("target_half_width must be positive")
        if not str(self.basis).strip():
            raise AdaptiveResolutionError("the search states the basis of its target and scheme order")

    def counts(self, level: int) -> dict[str, int]:
        return {path: value * self.ratio ** level for path, value in self.refined_inputs.items()}

    def to_dict(self) -> dict[str, Any]:
        return {"refined_inputs": dict(self.refined_inputs), "ratio": self.ratio, "max_levels": self.max_levels,
                "formal_order": self.formal_order, "order_tolerance": self.order_tolerance,
                "target_half_width": self.target_half_width.to_dict(), "basis": self.basis}


@dataclass(frozen=True)
class ResolutionLevelRun:
    """One solve the caller performed at the requested counts."""

    counts: Mapping[str, int]
    value: float | None
    run_id: str
    usable: bool
    problem: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"counts": dict(sorted(self.counts.items())), "value": self.value, "run_id": self.run_id,
                "usable": self.usable, "problem": self.problem}


@dataclass(frozen=True)
class AdaptiveResolutionRecord:
    quantity: str
    units: str
    policy: AdaptiveResolutionPolicy
    runs: tuple[ResolutionLevelRun, ...]  # in execution order, coarsest first
    estimate: NumericalUncertaintyEstimate | None  # over the three finest levels run, if any
    status: AdaptiveResolutionStatus
    reason: str

    @property
    def reported_value(self) -> float | None:
        """The finest level actually run (None when the search ended on an unusable level)."""
        last = self.runs[-1] if self.runs else None
        return None if last is None or not last.usable else last.value

    def uncertainty(self) -> Uncertainty:
        """The canonical NUMERICAL record of the reported value, or UNKNOWN (never zero)."""
        if self.status is AdaptiveResolutionStatus.UNKNOWN or self.estimate is None or not self.estimate.quantified:
            return Uncertainty.unknown(f"numerical uncertainty not quantified: {self.reason}")
        return self.estimate.to_uncertainty()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "adaptive_resolution",
            "quantity": self.quantity, "units": self.units, "policy": self.policy.to_dict(),
            "runs": [r.to_dict() for r in self.runs],
            "estimate": None if self.estimate is None else self.estimate.to_dict(),
            "status": self.status.value, "reason": self.reason, "reported_value": self.reported_value,
            "notice": ("numerical accuracy of the declared model's solution; not validation, never a stage promotion; "
                       "uniform refinement only"),
        }


def adapt_resolution(
    solve: Callable[[Mapping[str, int], int], ResolutionLevelRun],
    policy: AdaptiveResolutionPolicy,
    *,
    quantity: str,
    units: str,
) -> AdaptiveResolutionRecord:
    """Refine until the canonical estimate meets ``policy.target_half_width`` or the budget is spent."""
    if not isinstance(policy, AdaptiveResolutionPolicy):
        raise AdaptiveResolutionError("adapt_resolution takes an AdaptiveResolutionPolicy")
    target = policy.target_half_width.magnitude_as_spread_in(units)
    runs: list[ResolutionLevelRun] = []
    estimate: NumericalUncertaintyEstimate | None = None

    def done(status: AdaptiveResolutionStatus, reason: str) -> AdaptiveResolutionRecord:
        return AdaptiveResolutionRecord(quantity, units, policy, tuple(runs), estimate, status, reason)

    for level in range(policy.max_levels):
        counts = policy.counts(level)
        run = solve(dict(counts), level)
        if not isinstance(run, ResolutionLevelRun) or dict(run.counts) != counts:
            raise AdaptiveResolutionError(f"level {level} must return a ResolutionLevelRun at exactly {counts}")
        runs.append(run)
        usable = run.usable and run.value is not None and math.isfinite(run.value)
        if not usable:
            estimate = None
            return done(AdaptiveResolutionStatus.UNKNOWN,
                        f"level {level} at {counts} is not usable ({run.problem or 'no finite value'}); "
                        f"the search stops rather than skip it")
        if len(runs) >= 3:
            finest_first = runs[-1:-4:-1]
            levels = tuple(RefinementLevel(k, r.value, dict(r.counts), r.run_id) for k, r in enumerate(finest_first))
            estimate = estimate_numerical_uncertainty(levels, quantity=quantity, units=units,
                                                      refinement_ratio=float(policy.ratio),
                                                      formal_order=policy.formal_order,
                                                      order_tolerance=policy.order_tolerance)
            if estimate.quantified and estimate.half_width is not None and estimate.half_width <= target:
                return done(AdaptiveResolutionStatus.TARGET_MET,
                            f"half-width {estimate.half_width:.6g} {units} <= target {target:.6g} {units} at {counts}")
    if estimate is not None and estimate.quantified:
        return done(AdaptiveResolutionStatus.BUDGET_EXHAUSTED,
                    f"after {len(runs)} levels the quantified half-width {estimate.half_width:.6g} {units} still "
                    f"exceeds the target {target:.6g} {units}")
    return done(AdaptiveResolutionStatus.UNKNOWN,
                "no three finest levels gave a quantified estimate within the level budget"
                + ("" if estimate is None else f": {estimate.failure_reason}"))


__all__ = [
    "AdaptiveResolutionError",
    "AdaptiveResolutionPolicy",
    "AdaptiveResolutionRecord",
    "AdaptiveResolutionStatus",
    "ResolutionLevelRun",
    "adapt_resolution",
]
