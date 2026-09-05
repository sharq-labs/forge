"""Terminal decision, EVPI, and a genuine one-step EVSI.

DECISION-PATH MODULE. It must never import the hidden truth.

The EVSI here is computed from the predictive distribution by deterministic
numerical integration:

    EVSI(a) = E_y[ max_d E[u(d, theta) | D, y, a] ] - max_d E[u(d, theta) | D]

There is no hand-authored ``expected_delta_utility`` anywhere. The inner
expectation is an exact grid sum; the outer expectation over ``y`` is a
trapezoid rule over the predictive mixture density. If the code that computes
the posterior is wrong, this number is wrong with it — which is the point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

from .inference import Observation, ParameterGrid, posterior

#: Nodes and half-width (in predictive sigmas) for the outer y-integration.
#: Fixed rather than adaptive so the number is reproducible to the digit.
#: 301 nodes over +/-7 sigma is ~0.047 sigma spacing, far finer than the
#: integrand's smallest feature; :func:`evsi_quadrature_residual` measures the
#: remaining discretization error rather than asserting it is small.
Y_NODES = 301
Y_SPAN_SIGMAS = 7.0


@dataclass(frozen=True)
class TerminalDecisionSpec:
    """What is being decided, where, and what being wrong costs.

    Frozen before any observation is assimilated (invariants 1 and 4). The
    loss matrix is asymmetric on purpose: a symmetric loss makes the decision
    threshold 0.5 and hides whether the machinery respects the utility at all.
    """

    decision_id: str
    #: The condition at which the terminal decision is evaluated.
    x_star: float
    #: QoI threshold separating the two states of the world.
    threshold: float
    #: loss[decision][state], state True = QoI above threshold.
    loss_a_above: float = 0.0
    loss_a_below: float = 10.0
    loss_b_above: float = 1.0
    loss_b_below: float = 0.0
    tolerance: float = 1e-9

    def loss(self, decision: str, above: bool) -> float:
        if decision == "A":
            return self.loss_a_above if above else self.loss_a_below
        if decision == "B":
            return self.loss_b_above if above else self.loss_b_below
        raise ValueError(f"unknown decision {decision!r}")

    @property
    def decisions(self) -> tuple[str, ...]:
        return ("A", "B")

    def utility_vector(self, grid: ParameterGrid, decision: str) -> np.ndarray:
        """u(d, theta) for every theta on the grid. Utility = -loss."""
        above = grid.predict(self.x_star) > self.threshold
        return -np.where(
            above, self.loss(decision, True), self.loss(decision, False)
        )

    def indifference_probability(self) -> float:
        """P(above) at which A and B have equal expected utility."""
        # -(1-p)*L_a_below - p*L_a_above  ==  -(1-p)*L_b_below - p*L_b_above
        numerator = self.loss_a_below - self.loss_b_below
        denominator = (
            self.loss_a_below - self.loss_b_below
            + self.loss_b_above - self.loss_a_above
        )
        return numerator / denominator


class ObservationAction(Protocol):
    """A candidate experiment: what it would measure, and what it costs."""

    action_id: str
    cost: float
    sigma: float

    def predict(self, grid: ParameterGrid) -> np.ndarray:
        """Predicted measurement value for every theta on the grid."""
        ...


@dataclass(frozen=True)
class PointObservationAction:
    """Measure the QoI at a condition ``x``."""

    action_id: str
    x: float
    sigma: float
    cost: float

    def predict(self, grid: ParameterGrid) -> np.ndarray:
        return grid.predict(self.x)


@dataclass(frozen=True)
class DecisionIrrelevantAction:
    """Measure something the model space does not depend on.

    Its prediction is constant across theta, so the likelihood is constant, so
    the posterior cannot move and EVSI must be exactly zero. This is the
    concrete identifiability probe of invariant 11: "this observation type
    cannot identify the question" is a different statement from "we need more
    data", and the arithmetic has to be able to tell them apart.
    """

    action_id: str
    sigma: float
    cost: float
    constant: float = 1.0

    def predict(self, grid: ParameterGrid) -> np.ndarray:
        return np.full(grid.size, float(self.constant))


def expected_utility(
    grid: ParameterGrid, weights: np.ndarray, spec: TerminalDecisionSpec, decision: str
) -> float:
    return float(np.dot(weights, spec.utility_vector(grid, decision)))


def best_decision(
    grid: ParameterGrid, weights: np.ndarray, spec: TerminalDecisionSpec
) -> tuple[str, float]:
    """Bayes decision and its expected utility. Ties break on decision id."""
    scored = [
        (expected_utility(grid, weights, spec, d), d) for d in spec.decisions
    ]
    value, decision = max(scored, key=lambda item: (item[0], -ord(item[1][0])))
    return decision, value


def evpi(
    grid: ParameterGrid, weights: np.ndarray, spec: TerminalDecisionSpec
) -> float:
    """E_theta[max_d u(d, theta)] - max_d E_theta[u(d, theta)]."""
    per_theta_best = np.max(
        np.vstack([spec.utility_vector(grid, d) for d in spec.decisions]), axis=0
    )
    with_perfect_information = float(np.dot(weights, per_theta_best))
    _, without = best_decision(grid, weights, spec)
    return with_perfect_information - without


def _predictive_nodes(
    grid: ParameterGrid,
    weights: np.ndarray,
    action: ObservationAction,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Quadrature nodes, trapezoid weights, and predictive density over y."""
    predicted = action.predict(grid)
    mean = float(np.dot(weights, predicted))
    spread = float(np.dot(weights, (predicted - mean) ** 2))
    sigma_total = math.sqrt(max(spread, 0.0) + action.sigma**2)
    half_width = Y_SPAN_SIGMAS * sigma_total
    nodes = np.linspace(mean - half_width, mean + half_width, Y_NODES)

    # Mixture density: sum_theta w_theta * N(y; f_theta, sigma_a)
    residual = nodes[:, None] - predicted[None, :]
    kernel = np.exp(-0.5 * (residual / action.sigma) ** 2) / (
        action.sigma * math.sqrt(2.0 * math.pi)
    )
    density = kernel @ weights

    step = nodes[1] - nodes[0]
    quad = np.full(Y_NODES, step)
    quad[0] *= 0.5
    quad[-1] *= 0.5
    return nodes, quad, density


def evsi(
    grid: ParameterGrid,
    weights: np.ndarray,
    spec: TerminalDecisionSpec,
    action: ObservationAction,
) -> float:
    """One-step expected value of sample information, from the predictive.

    For each hypothetical outcome ``y`` the posterior is reweighted by the
    declared likelihood, the Bayes decision is recomputed, and the resulting
    expected utility is averaged under the predictive density of ``y``.
    """
    predicted = action.predict(grid)
    utilities = np.vstack([spec.utility_vector(grid, d) for d in spec.decisions])

    # One Gaussian kernel serves both the predictive density and the per-y
    # posterior update; computing it twice was pure waste.
    mean = float(np.dot(weights, predicted))
    spread = float(np.dot(weights, (predicted - mean) ** 2))
    sigma_total = math.sqrt(max(spread, 0.0) + action.sigma**2)
    nodes = np.linspace(
        mean - Y_SPAN_SIGMAS * sigma_total,
        mean + Y_SPAN_SIGMAS * sigma_total,
        Y_NODES,
    )
    step = nodes[1] - nodes[0]
    quad = np.full(Y_NODES, step)
    quad[0] *= 0.5
    quad[-1] *= 0.5

    residual = nodes[:, None] - predicted[None, :]
    residual /= action.sigma
    residual *= residual
    residual *= -0.5                                   # now log N kernel + const
    unnormalized = np.exp(residual - residual.max(axis=1, keepdims=True))

    joint = unnormalized * weights[None, :]
    totals = joint.sum(axis=1, keepdims=True)
    # Predictive density, recovered from the same kernel: the shift removed
    # above is put back so the density is on its true scale.
    density = (
        totals[:, 0]
        * np.exp(residual.max(axis=1))
        / (action.sigma * math.sqrt(2.0 * math.pi))
    )
    safe = totals > 0.0
    updated = np.where(safe, joint / np.where(safe, totals, 1.0), 0.0)

    # max_d E[u | y] for each y, then integrate against the predictive.
    per_y_best = (updated @ utilities.T).max(axis=1)
    expected_after = float(np.sum(quad * density * per_y_best))

    # The quadrature does not capture the whole real line; renormalize by the
    # mass it does capture so a truncation artifact cannot masquerade as value.
    captured = float(np.sum(quad * density))
    if captured <= 0.0:
        raise ValueError("predictive density integrated to zero")
    expected_after /= captured

    _, before = best_decision(grid, weights, spec)
    return expected_after - before


def evsi_report(
    grid: ParameterGrid,
    weights: np.ndarray,
    spec: TerminalDecisionSpec,
    actions: Sequence[ObservationAction],
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for action in actions:
        value = evsi(grid, weights, spec, action)
        out[action.action_id] = {
            "evsi": value,
            "cost": float(action.cost),
            "net": value - float(action.cost),
        }
    return out


def assimilate(
    grid: ParameterGrid,
    observations: Sequence[Observation],
    prior: np.ndarray | None = None,
) -> np.ndarray:
    """Convenience wrapper so callers need not import :mod:`inference`."""
    return posterior(grid, observations, prior)
