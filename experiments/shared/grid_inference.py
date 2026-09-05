"""Exact Bayesian inference for one parameter on a finite grid.

The same mathematics E2 froze — uniform prior, Gaussian observation
likelihood, exact normalized reweighting — with one difference: the forward map
is supplied by the caller instead of being wired to a particular solver.

WHY THIS IS A COPY AND NOT AN IMPORT
-------------------------------------
``e2_model.posterior_weights`` is frozen and internally bound to E2's theta
grid and to ``forward_predictions``, which calls the Electrical solver. It
cannot be reused for a different domain without editing it, and editing it
would break the E2 freeze. So the arithmetic is restated here over a general
grid. A test asserts the two agree on a shared case, so "the same mathematics"
is checked rather than asserted.

WHAT IT DELIBERATELY DOES NOT DO
---------------------------------
No EVPI, no EVSI, no predictive mixture, no campaign, no model adequacy. Those
exist frozen in E2 for the Electrical path; nothing here reimplements them
speculatively. This module answers exactly one question — given observations
and a forward map, what is the posterior over the parameter, and does its
credible interval contain a stated value — because that is what the
experiment that prompted it needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True)
class ParameterGrid:
    """A finite support for one scalar parameter, with a uniform prior."""

    name: str
    unit: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        values = tuple(float(v) for v in self.values)
        if len(values) < 2:
            raise ValueError(
                f"grid {self.name!r} needs at least two points; a single point "
                f"is a fixed value, not a parameter under inference"
            )
        if any(not math.isfinite(v) for v in values):
            raise ValueError(f"grid {self.name!r} contains a non-finite value")
        if any(b <= a for a, b in zip(values, values[1:])):
            raise ValueError(f"grid {self.name!r} must be strictly increasing")
        if not str(self.name).strip() or not str(self.unit).strip():
            raise ValueError("a parameter grid requires a name and a unit")
        object.__setattr__(self, "values", values)

    @property
    def array(self) -> np.ndarray:
        return np.asarray(self.values, dtype=np.float64)

    @property
    def size(self) -> int:
        return len(self.values)

    @property
    def spacing(self) -> float:
        return float(self.values[1] - self.values[0])

    def uniform_prior(self) -> np.ndarray:
        return np.full(self.size, 1.0 / self.size)

    def contains(self, value: float) -> bool:
        return self.values[0] <= float(value) <= self.values[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "size": self.size,
            "minimum": self.values[0],
            "maximum": self.values[-1],
            "spacing": self.spacing,
            "prior": "uniform",
        }


def posterior_weights(
    grid: ParameterGrid,
    forward: Sequence[float],
    observations: Sequence[float],
    sigma: float,
    prior: np.ndarray | None = None,
) -> np.ndarray:
    """p(theta | observations) by exact normalized reweighting.

    ``forward[i]`` is the predicted observable at ``grid.values[i]``. Whether
    that prediction is accurate is not this function's business — and that is
    exactly the point of the experiment this was written for: a biased forward
    map produces a perfectly well-formed, possibly very narrow, wrong posterior,
    and nothing in the arithmetic can notice.
    """
    predictions = np.asarray(forward, dtype=np.float64)
    if predictions.shape != (grid.size,):
        raise ValueError(
            f"forward map has {predictions.shape} entries, grid has {grid.size}"
        )
    if not np.all(np.isfinite(predictions)):
        raise ValueError("forward map contains non-finite predictions")
    sigma = float(sigma)
    if not math.isfinite(sigma) or sigma <= 0.0:
        raise ValueError(f"observation sigma must be positive, got {sigma!r}")
    if not len(observations):
        raise ValueError("at least one observation is required")

    weights = grid.uniform_prior() if prior is None else np.asarray(prior, float)
    if not math.isclose(float(weights.sum()), 1.0, rel_tol=1e-9):
        raise ValueError("prior must be normalized")

    log_weights = np.log(np.where(weights > 0.0, weights, np.finfo(float).tiny))
    for value in observations:
        residual = float(value) - predictions
        log_weights = log_weights - 0.5 * (residual / sigma) ** 2

    finite = log_weights[np.isfinite(log_weights)]
    if finite.size == 0:
        raise ValueError("every grid point has zero likelihood")
    shifted = np.exp(log_weights - finite.max())
    total = shifted.sum()
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("posterior failed to normalize")
    return shifted / total


@dataclass(frozen=True)
class PosteriorSummary:
    """What the posterior says, and how confidently it says it."""

    mean: float
    map_value: float
    sd: float
    credible_mass: float
    lower: float
    upper: float
    effective_support: int

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def covers(self, value: float) -> bool:
        """Whether the credible interval contains a stated value.

        Note what this is not: coverage of ONE interval is a single Bernoulli
        outcome, not a calibration statement. It says whether this posterior
        happened to contain the value, and nothing about long-run frequency.
        """
        return self.lower <= float(value) <= self.upper

    def error_against(self, truth: float) -> dict[str, float]:
        truth = float(truth)
        return {
            "mean_error": self.mean - truth,
            "map_error": self.map_value - truth,
            "mean_relative_error": (self.mean - truth) / truth if truth else float("nan"),
            "mean_error_in_sd": (self.mean - truth) / self.sd if self.sd else float("inf"),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "map": self.map_value,
            "sd": self.sd,
            "credible_mass": self.credible_mass,
            "lower": self.lower,
            "upper": self.upper,
            "width": self.width,
            "effective_support": self.effective_support,
        }


def summarize(
    grid: ParameterGrid, weights: np.ndarray, credible_mass: float = 0.95
) -> PosteriorSummary:
    """Summarize a discrete posterior, including an equal-tailed interval."""
    if not 0.0 < credible_mass < 1.0:
        raise ValueError("credible_mass must lie strictly between 0 and 1")
    w = np.asarray(weights, dtype=np.float64)
    if w.shape != (grid.size,):
        raise ValueError("weights and grid disagree in length")

    values = grid.array
    mean = float(np.dot(w, values))
    variance = float(np.dot(w, (values - mean) ** 2))
    tail = (1.0 - credible_mass) / 2.0
    cumulative = np.cumsum(w)
    # Equal-tailed on the discrete support: the smallest grid point whose
    # cumulative mass reaches each tail. Conservative by construction, since a
    # discrete interval can only widen to the next grid point, never narrow.
    lower_index = int(np.searchsorted(cumulative, tail, side="left"))
    upper_index = int(np.searchsorted(cumulative, 1.0 - tail, side="left"))
    lower_index = min(lower_index, grid.size - 1)
    upper_index = min(upper_index, grid.size - 1)
    return PosteriorSummary(
        mean=mean,
        map_value=float(values[int(np.argmax(w))]),
        sd=float(math.sqrt(max(variance, 0.0))),
        credible_mass=float(credible_mass),
        lower=float(values[lower_index]),
        upper=float(values[upper_index]),
        effective_support=int(np.count_nonzero(w > 1e-12)),
    )


def predictive_mean(weights: np.ndarray, forward: Sequence[float]) -> float:
    """Posterior-weighted mean of the observable.

    The noise-free predictive centre: what the model expects to see next,
    given the parameter posterior it currently holds.
    """
    w = np.asarray(weights, dtype=np.float64)
    predictions = np.asarray(forward, dtype=np.float64)
    if w.shape != predictions.shape:
        raise ValueError("weights and forward map disagree in length")
    return float(np.dot(w, predictions))
