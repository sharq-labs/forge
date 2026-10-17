"""Numerical-health classification of iterative solves (Phase 3 BR13).

One vocabulary for WHY an iterative numerical solve did not produce an
acceptable result, and one set of history detectors shared by the numerical
providers.  It classifies; it never accepts, relaxes or repairs anything.

The detectors use the same rules as the coupling runtime's window detectors
(``MultiphysicsRuntime._diverging_edge`` / ``_stagnating``), restated on a plain
sequence of non-negative residual measures:

* DIVERGING: the latest measure exceeds ``divergence_factor`` times the first;
* STAGNATING: none of the last ``stagnation_window`` measures improves on the
  best measure seen before them.

A residual measure is a property of the iterate, not of the solution error.
:data:`RESIDUAL_IS_NOT_AN_ERROR_BOUND` is the statement every record built on
these measures carries: a small residual bounds neither the distance to a
true root (that needs conditioning or a Kantorovich-type argument), nor its
uniqueness, nor the physical correctness, conservation or applicability of the
model whose equations were solved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Sequence

import numpy as np

from .core import NumericalRefusal

RESIDUAL_IS_NOT_AN_ERROR_BOUND = (
    "residual_not_solution_error_bound: a residual below tolerance bounds neither the solution error, nor "
    "uniqueness, nor physical correctness, conservation or applicability"
)


class NumericalFailureClass(str, Enum):
    """Why an iterative numerical solve ended without an acceptable result."""

    #: a residual, Jacobian or iterate stopped being finite
    NON_FINITE = "non_finite"
    #: the residual measure grew past the declared divergence factor
    DIVERGING = "diverging"
    #: the residual measure stopped improving for the declared window
    STAGNATING = "stagnating"
    #: the step became negligible while the residual is still above tolerance
    STEP_STAGNATION = "step_stagnation"
    #: no step length satisfied the declared sufficient-decrease condition
    LINE_SEARCH_FAILED = "line_search_failed"
    #: the linearized system could not be solved (singular / numerically singular Jacobian)
    SINGULAR_JACOBIAN = "singular_jacobian"
    #: the declared iteration (or evaluation) budget was spent
    ITERATION_LIMIT = "iteration_limit"
    #: the backend reported termination but the declared acceptance test failed
    TOLERANCE_NOT_MET = "tolerance_not_met"
    #: a backend reported failure for a reason it did not classify further
    BACKEND_FAILURE = "backend_failure"


@dataclass(frozen=True)
class HistoryPolicy:
    """Optional early-stop rules over a residual history.  Unset rules never fire."""

    divergence_factor: float | None = None
    stagnation_window: int | None = None

    def __post_init__(self) -> None:
        if self.divergence_factor is not None:
            value = self.divergence_factor
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 1.0:
                raise NumericalRefusal("divergence_factor must be finite and > 1")
            object.__setattr__(self, "divergence_factor", float(value))
        if self.stagnation_window is not None:
            value = self.stagnation_window
            if isinstance(value, bool) or not isinstance(value, int) or not 2 <= value <= 1000:
                raise NumericalRefusal("stagnation_window must be an int in [2, 1000]")

    def to_dict(self) -> dict[str, Any]:
        return {"divergence_factor": self.divergence_factor, "stagnation_window": self.stagnation_window}


def diverging(history: Sequence[float], factor: float | None) -> str:
    """Why the history diverges (latest > factor * first), or ''."""
    if factor is None or len(history) < 2:
        return ""
    first, last = float(history[0]), float(history[-1])
    if first <= 0.0 or not math.isfinite(first):
        return ""
    ratio = last / first
    if ratio > factor:
        return f"residual grew {ratio:.3g}x over {len(history)} iterations (declared limit {factor:g}x)"
    return ""


def stagnating(history: Sequence[float], window: int | None) -> str:
    """Why the history stagnates (none of the last ``window`` values beats the best before them), or ''."""
    if window is None or len(history) <= window:
        return ""
    values = [float(v) for v in history]
    best_before = min(values[:-window])
    if min(values[-window:]) >= best_before:
        return f"residual has not improved on {best_before:.3g} for {window} consecutive iterations"
    return ""


def classify_history(history: Sequence[float], policy: HistoryPolicy) -> tuple[NumericalFailureClass | None, str]:
    """The first failure the history shows under ``policy`` (non-finite, diverging, stagnating), or (None, '')."""
    values = [float(v) for v in history]
    if any(not math.isfinite(v) for v in values):
        return NumericalFailureClass.NON_FINITE, "a residual measure is not finite"
    reason = diverging(values, policy.divergence_factor)
    if reason:
        return NumericalFailureClass.DIVERGING, reason
    reason = stagnating(values, policy.stagnation_window)
    if reason:
        return NumericalFailureClass.STAGNATING, reason
    return None, ""


@dataclass(frozen=True)
class ResidualScaling:
    """Declared positive scales of the residual components: the measure is ``max_i |F_i| / s_i``.

    Without declared scales the measure is the UNSCALED max-norm in the
    residual's own (normalized-space) numbers, and the record says so.  Scales
    are part of the method's execution identity; they are never inferred from
    the iterate, so a solve cannot make its own residual look small.
    """

    scales: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if self.scales is None:
            return
        values = tuple(self.scales)
        if not values or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
            raise NumericalRefusal("residual scales must be a non-empty tuple of numbers")
        if any(not math.isfinite(float(v)) or float(v) <= 0.0 for v in values):
            raise NumericalRefusal("residual scales must be finite and positive")
        object.__setattr__(self, "scales", tuple(float(v) for v in values))

    @property
    def label(self) -> str:
        return "linf_scaled_by_declared_residual_scales" if self.scales is not None else "linf_unscaled"

    def measure(self, residual: np.ndarray) -> float:
        r = np.asarray(residual, dtype=float).reshape(-1)
        if self.scales is not None:
            if r.size != len(self.scales):
                raise NumericalRefusal(f"residual has {r.size} components; {len(self.scales)} scales are declared")
            r = r / np.asarray(self.scales)
        if not np.all(np.isfinite(r)):
            return math.inf
        return float(np.max(np.abs(r))) if r.size else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"measure": self.label, "scales": None if self.scales is None else list(self.scales)}


__all__ = [
    "HistoryPolicy",
    "NumericalFailureClass",
    "RESIDUAL_IS_NOT_AN_ERROR_BOUND",
    "ResidualScaling",
    "classify_history",
    "diverging",
    "stagnating",
]
