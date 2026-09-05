"""Minimal exact Bayesian inference on a frozen finite grid.

DECISION-PATH MODULE. It must never import the hidden truth; a test asserts
this by parsing the import graph.

Everything here is deliberately small enough to check by hand: a finite grid of
parameters, an explicit prior, an explicit Gaussian likelihood, and exact
normalized reweighting. There is no sampler, no optimizer and no framework —
the posterior is reconstructible from (prior, observations, likelihood) alone,
which is invariant 2 of the scientific brain spec in miniature.

The model space is the straight line

    f(x; a, b) = a + b * x

and that is the *whole* model space. The point of the benchmark is that this
space is misspecified outside the observed region, and that no amount of
correct inference inside the space can discover that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class ParameterGrid:
    """A frozen finite parameter space. No adaptivity, no refinement."""

    a_values: np.ndarray
    b_values: np.ndarray

    @classmethod
    def default(cls) -> "ParameterGrid":
        return cls(
            a_values=np.linspace(0.5, 1.5, 201),
            b_values=np.linspace(0.40, 0.60, 201),
        )

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.a_values), len(self.b_values))

    @property
    def size(self) -> int:
        return len(self.a_values) * len(self.b_values)

    def mesh(self) -> tuple[np.ndarray, np.ndarray]:
        """(a, b) meshes, each flattened to one entry per grid point.

        Memoized because the grid is frozen and the sweep asks for this
        hundreds of thousands of times. Pure caching: the arrays are identical
        to the freshly built ones, and are handed out read-only so a caller
        cannot corrupt the cache.
        """
        cached = getattr(self, "_mesh_cache", None)
        if cached is None:
            a_mesh, b_mesh = np.meshgrid(
                self.a_values, self.b_values, indexing="ij"
            )
            cached = (a_mesh.ravel(), b_mesh.ravel())
            for array in cached:
                array.flags.writeable = False
            object.__setattr__(self, "_mesh_cache", cached)
        return cached

    def predict(self, x: float) -> np.ndarray:
        """f(x; theta) for every theta on the grid."""
        a, b = self.mesh()
        return a + b * float(x)

    def uniform_prior(self) -> np.ndarray:
        return np.full(self.size, 1.0 / self.size)


@dataclass(frozen=True)
class Observation:
    """One assimilated measurement. Its likelihood is declared with it."""

    x: float
    y: float
    sigma: float

    def __post_init__(self) -> None:
        if self.sigma <= 0.0:
            raise ValueError("observation noise must be positive")


def _log_normal(residual: np.ndarray, sigma: float) -> np.ndarray:
    return -0.5 * (residual / sigma) ** 2 - math.log(sigma * math.sqrt(2.0 * math.pi))


def _normalize_log(log_weights: np.ndarray) -> np.ndarray:
    """Exact normalization in log space. No sampling anywhere."""
    finite = log_weights[np.isfinite(log_weights)]
    if finite.size == 0:
        raise ValueError("every parameter has zero likelihood; model space is empty")
    shifted = log_weights - np.max(finite)
    weights = np.exp(shifted)
    total = weights.sum()
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("posterior failed to normalize")
    return weights / total


def posterior(
    grid: ParameterGrid,
    observations: Sequence[Observation],
    prior: np.ndarray | None = None,
) -> np.ndarray:
    """Exact posterior weights over the grid.

    Deterministic and order-independent: the log-likelihood is a sum, so
    assimilating the same observations in any order gives the same answer.
    """
    weights = grid.uniform_prior() if prior is None else np.asarray(prior, float)
    if weights.shape != (grid.size,):
        raise ValueError("prior does not match the grid")
    if not math.isclose(float(weights.sum()), 1.0, rel_tol=1e-9):
        raise ValueError("prior must be normalized")

    log_weights = np.log(np.where(weights > 0.0, weights, np.finfo(float).tiny))
    for observation in observations:
        predicted = grid.predict(observation.x)
        log_weights = log_weights + _log_normal(
            observation.y - predicted, observation.sigma
        )
    return _normalize_log(log_weights)


def predictive_moments(
    grid: ParameterGrid, weights: np.ndarray, x: float, sigma: float = 0.0
) -> tuple[float, float]:
    """Mean and standard deviation of the predictive at ``x``.

    With ``sigma`` the observation noise of a hypothetical measurement, this is
    the predictive for that measurement; with ``sigma=0`` it is the predictive
    for the latent quantity itself.
    """
    predicted = grid.predict(x)
    mean = float(np.dot(weights, predicted))
    variance = float(np.dot(weights, (predicted - mean) ** 2)) + sigma**2
    return mean, math.sqrt(max(variance, 0.0))


def exceedance_probability(
    grid: ParameterGrid, weights: np.ndarray, x: float, threshold: float
) -> float:
    """P(f(x; theta) > threshold) under the posterior. Exact grid sum."""
    return float(weights[grid.predict(x) > threshold].sum())
