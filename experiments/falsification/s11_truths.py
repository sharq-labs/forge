"""S1.1 hidden truth families — GRADER ONLY.

**No decision-path module may import this**, and the S1.1 test enforces it by
parsing import graphs, exactly as S1 does for :mod:`truth`.

Every family has the form

    g(x) = 1.0 + 0.5*x - correction(x)

with ``correction(x) == 0`` for all ``x <= 8``. Since every observation lies in
``0..8``, all six families produce **identical observations for a given seed**.
That is the whole point: the decision path cannot distinguish them from the
data it is allowed to see, so any difference in outcome is attributable to what
happens outside support and nowhere else.

Two classes:

BENIGN
    the response continues in a way the assumed linear model handles well
    enough that the terminal decision stays correct. These cases measure what
    the guard *costs*.

REGIME_CHANGE
    the response departs sharply beyond the data, flipping the terminal
    decision. These cases measure what the guard *buys*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .s11_config import (
    NOMINAL_INTERCEPT,
    NOMINAL_SLOPE,
    TRUTH_BREAK_POINT,
)


@dataclass(frozen=True)
class TruthFamily:
    """One grader-only hidden response."""

    family_id: str
    truth_class: str
    description: str
    correction: Callable[[np.ndarray], np.ndarray]

    def qoi(self, x: float | np.ndarray) -> float | np.ndarray:
        x = np.asarray(x, dtype=float)
        value = NOMINAL_INTERCEPT + NOMINAL_SLOPE * x - self.correction(x)
        return float(value) if value.ndim == 0 else value

    def is_above(self, x: float, threshold: float) -> bool:
        return bool(self.qoi(x) > threshold)


def _excess(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x - TRUTH_BREAK_POINT)


def _zero(x: np.ndarray) -> np.ndarray:
    return np.zeros_like(x)


def _quadratic(coefficient: float) -> Callable[[np.ndarray], np.ndarray]:
    def correction(x: np.ndarray) -> np.ndarray:
        return coefficient * _excess(x) ** 2

    return correction


def _linear_kink(slope: float) -> Callable[[np.ndarray], np.ndarray]:
    def correction(x: np.ndarray) -> np.ndarray:
        return slope * _excess(x)

    return correction


def _step(height: float) -> Callable[[np.ndarray], np.ndarray]:
    def correction(x: np.ndarray) -> np.ndarray:
        return np.where(x > TRUTH_BREAK_POINT, height, 0.0)

    return correction


#: The six declared families, in the order fixed by the configuration.
TRUTH_FAMILIES: tuple[TruthFamily, ...] = (
    TruthFamily(
        family_id="linear_exact",
        truth_class="BENIGN",
        description="the assumed model is exactly right everywhere",
        correction=_zero,
    ),
    TruthFamily(
        family_id="mild_quadratic",
        truth_class="BENIGN",
        description="slight curvature beyond the data, never enough to flip",
        correction=_quadratic(0.01),
    ),
    TruthFamily(
        family_id="mild_kink",
        truth_class="BENIGN",
        description="small slope change beyond the data",
        correction=_linear_kink(0.03),
    ),
    TruthFamily(
        family_id="regime_moderate",
        truth_class="REGIME_CHANGE",
        description="quadratic saturation that flips the decision from ~9.5",
        correction=_quadratic(0.2),
    ),
    TruthFamily(
        family_id="regime_strong",
        truth_class="REGIME_CHANGE",
        description="strong saturation that flips the decision from ~9",
        correction=_quadratic(0.8),
    ),
    TruthFamily(
        family_id="regime_step",
        truth_class="REGIME_CHANGE",
        description="discontinuous drop immediately beyond the data",
        correction=_step(1.0),
    ),
)

FAMILY_BY_ID = {family.family_id: family for family in TRUTH_FAMILIES}


def observations_for_seed(
    xs: np.ndarray, sigma: float, seed: int
) -> np.ndarray:
    """Measured values at the observation locations.

    Deliberately does **not** take a truth family: on ``x <= 8`` every family
    is the same function, so the observations depend on the seed alone. Writing
    it this way makes the no-leakage property structural — there is no argument
    a caller could pass that would let the hidden family influence the data.
    """
    rng = np.random.default_rng(seed)
    nominal = NOMINAL_INTERCEPT + NOMINAL_SLOPE * np.asarray(xs, dtype=float)
    return nominal + rng.normal(0.0, sigma, size=len(xs))
