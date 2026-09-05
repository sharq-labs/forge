"""HIDDEN GROUND TRUTH — GRADER ONLY.

**No decision-path module may import this.** ``inference``, ``decision`` and
``support`` must remain ignorant of everything here, and a test enforces that by
parsing their import graphs. The benchmark harness uses this module in exactly
two places: to generate the observations a real instrument would have produced,
and to grade the decision afterwards.

The truth agrees with SRIA's linear model space *exactly* on the observed
region and departs from it only beyond a break point. That is what makes the
trap fair: no amount of correct inference inside the model space can detect the
misspecification from the data SRIA is allowed to see, because within that data
there is no misspecification to detect.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HiddenTruth:
    """g(x) = a + b*x - curvature * max(0, x - break_point)^2.

    The correction term is identically zero for x <= break_point, so on the
    observed region the truth *is* a straight line. Beyond it, a regime change
    bends the response down — a saturation, a phase change, a limiting
    mechanism; the benchmark does not care which.
    """

    intercept: float = 1.0
    slope: float = 0.5
    break_point: float = 8.5
    curvature: float = 0.8

    def qoi(self, x: float | np.ndarray) -> float | np.ndarray:
        x = np.asarray(x, dtype=float)
        excess = np.maximum(0.0, x - self.break_point)
        value = self.intercept + self.slope * x - self.curvature * excess**2
        return float(value) if value.ndim == 0 else value

    def is_above(self, x: float, threshold: float) -> bool:
        return bool(self.qoi(x) > threshold)


#: The truth used by the headline scenarios.
DEFAULT_TRUTH = HiddenTruth()

#: An alternative truth that differs ONLY beyond the observed region. Used by
#: the oracle-leakage test: swapping this in must not move the posterior or any
#: EVSI, because nothing SRIA has seen distinguishes them.
ALTERNATIVE_OUT_OF_SUPPORT_TRUTH = HiddenTruth(curvature=2.5)


def generate_observations(
    truth: HiddenTruth,
    xs: np.ndarray,
    sigma: float,
    seed: int,
) -> np.ndarray:
    """Measured values. Deterministic given ``seed``."""
    rng = np.random.default_rng(seed)
    return truth.qoi(xs) + rng.normal(0.0, sigma, size=len(xs))
