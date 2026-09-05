"""T3 hidden truth — GRADER ONLY.

**No decision-path module may import this**, enforced by an AST test.

Holds each scenario's alpha, its terminal truth, its threshold and its
observation draw. The strategies see only the observations and tau; alpha and
the terminal truth are used to grade, never to decide.

WHY TAU IS BUILT FROM THE TRUTH
--------------------------------
tau = terminal_truth + sign * margin makes the decision margin exactly
controllable, which is the whole point: the benchmark needs scenarios that sit
at known distances from the boundary so "far from the boundary" and "close to
it" are properties of the design rather than accidents of sampling. It also
makes the correct answer exactly ``sign > 0``, so the two decisions are
balanced by construction and no strategy can profit from guessing one of them.

Knowing tau is not knowing the answer: a strategy is told the threshold, as any
real decision-maker would be, and must work out which side of it the truth
falls on using a forward model it does not know the accuracy of.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from src.engcore.domains.thermal.conduction1d import exact_midpoint

from .t3_config import (
    ALPHA_TRUE_MAX,
    ALPHA_TRUE_MIN,
    END_TIME_S,
    LENGTH_M,
    MARGIN_BANDS,
    OBSERVATION_COUNT,
    OBSERVATION_SIGMA,
    SCENARIO_COUNT,
    SEED_ENTROPY,
    TERMINAL_TIME_S,
    band_of,
)


@dataclass(frozen=True)
class Scenario:
    """One decision problem. Only ``tau`` and ``observations`` are visible."""

    index: int
    band: str
    alpha_true: float
    margin: float
    sign: int
    tau: float
    terminal_truth: float
    observations: tuple[float, ...]

    @property
    def correct_decision(self) -> bool:
        """True when the terminal truth is below tau — exactly ``sign > 0``."""
        return self.terminal_truth < self.tau

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "band": self.band,
            "alpha_true": self.alpha_true,
            "margin": self.margin,
            "sign": self.sign,
            "tau": self.tau,
            "terminal_truth": self.terminal_truth,
            "correct_decision": self.correct_decision,
        }


def _streams() -> tuple[np.random.SeedSequence, ...]:
    return tuple(np.random.SeedSequence(SEED_ENTROPY).spawn(SCENARIO_COUNT))


def scenario(index: int) -> Scenario:
    """Build one scenario. Draw order is fixed by the preregistered rule."""
    band = band_of(index)
    low, high = MARGIN_BANDS[band]
    rng = np.random.default_rng(_streams()[index])

    alpha_true = float(rng.uniform(ALPHA_TRUE_MIN, ALPHA_TRUE_MAX))
    margin = float(rng.uniform(low, high))
    sign = 1 if rng.random() < 0.5 else -1

    terminal_truth = exact_midpoint(
        length_m=LENGTH_M, alpha_m2_s=alpha_true, time_s=TERMINAL_TIME_S
    )
    observation_centre = exact_midpoint(
        length_m=LENGTH_M, alpha_m2_s=alpha_true, time_s=END_TIME_S
    )
    observations = tuple(
        float(observation_centre + rng.normal(0.0, OBSERVATION_SIGMA))
        for _ in range(OBSERVATION_COUNT)
    )
    return Scenario(
        index=index,
        band=band,
        alpha_true=alpha_true,
        margin=margin,
        sign=sign,
        tau=terminal_truth + sign * margin,
        terminal_truth=terminal_truth,
        observations=observations,
    )


_CACHE: tuple[Scenario, ...] | None = None


def all_scenarios() -> tuple[Scenario, ...]:
    """Every scenario, built once and shared by every strategy.

    Shared for the same reason T1 shared one draw across rungs and T2 shared
    500: if strategies saw different scenarios, a difference between them could
    be the draw rather than the strategy.
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = tuple(scenario(i) for i in range(SCENARIO_COUNT))
    return _CACHE


def truth_payload() -> dict[str, Any]:
    scenarios = all_scenarios()
    alphas = np.array([s.alpha_true for s in scenarios])
    positives = sum(1 for s in scenarios if s.correct_decision)
    return {
        "scenario_count": len(scenarios),
        "alpha_true_mean": float(alphas.mean()),
        "alpha_true_min": float(alphas.min()),
        "alpha_true_max": float(alphas.max()),
        "terminal_time_s": TERMINAL_TIME_S,
        "decision_balance": {
            "below_threshold_true": positives,
            "above_threshold_true": len(scenarios) - positives,
        },
        "per_band_margin_mean": {
            band: float(
                np.mean([s.margin for s in scenarios if s.band == band])
            )
            for band in MARGIN_BANDS
        },
        "truth_source": "exact analytic solution + declared Gaussian noise",
        "scope": (
            "synthetic hidden truth with known alphas; no physical validation "
            "and no real measurement is involved"
        ),
    }


def truth_hash() -> str:
    """Covers every scenario's drawn values, not just the summary."""
    blob = json.dumps(
        {
            "summary": truth_payload(),
            "scenarios": [
                {**s.to_dict(), "observations": list(s.observations)}
                for s in all_scenarios()
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
