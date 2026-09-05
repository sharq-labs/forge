"""E2 decision path: the assumed constant-R model over the REAL solver.

DECISION-PATH MODULE. It must never import :mod:`e2_truth`; a test parses the
import graph transitively.

Everything here is conditional on the assumed family

    M_const  =  { R2 = c, condition-independent }

and says so in its own vocabulary. ``posterior_weights`` returns
p(R2 | data, M_const). ``predictive_components`` returns the mixture that
family implies for a not-yet-taken measurement. ``evpi``/``evsi`` are computed
inside that family. None of them can detect that the family is wrong, and none
of them is asked to — that is the adequacy layer's job, and keeping the two
apart is the point.

The forward map is the repository's actual ``solve_circuit`` MNA lifecycle, run
once per grid point per operating condition and cached (the solver is
deterministic, so caching is exact). If the solver fails or its validation
report does not pass at ANY grid point the model refuses rather than
interpolating around the hole.

THE PREDICTIVE IS EXACT, NOT SAMPLED
------------------------------------
Under M_const with a discrete grid, p(y | data, a) is a finite Gaussian mixture
with one component per grid point: means from the solver, common sd from the
declared observation noise, weights from the posterior. That makes both the
predictive density and its tail probabilities closed-form. ``erfc`` is used
directly for each side rather than differencing a CDF, so a tail of 1e-12 is
computed to full relative accuracy instead of being lost to cancellation —
which matters, because the adequacy rule reads exactly those small tails.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from src.engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    solve_circuit,
)
from src.engcore.scientific import Quantity
from src.engcore.scientific.results.validation import ValidationOutcome
from src.engcore.scientific.solvers.protocol import ConvergenceState

from .e2_config import (
    ACTIONS,
    E2Action,
    LOSS_A_ABOVE,
    LOSS_A_BELOW,
    LOSS_B_ABOVE,
    LOSS_B_BELOW,
    NODE_IN,
    NODE_MID,
    NODE_REF,
    R1_OHM,
    THRESHOLD_OHM,
    VMID_METRIC,
    Y_NODES,
    Y_SPAN_SIGMAS,
    config_hash,
    theta_grid,
)

_SQRT2 = math.sqrt(2.0)
_LOG_SQRT_2PI = 0.5 * math.log(2.0 * math.pi)


# =====================================================================
# Forward map — the real solver
# =====================================================================

def build_divider_circuit(
    source_voltage_volt: float, r2_ohm: float, *, circuit_id: str
) -> DCCircuit:
    """The declared topology, with R2 as the candidate constant parameter."""
    return DCCircuit(
        circuit_id=circuit_id,
        nodes=(
            ElectricalNode(node_id=NODE_IN),
            ElectricalNode(node_id=NODE_MID),
            ElectricalNode(node_id=NODE_REF, is_reference=True),
        ),
        resistors=(
            Resistor(
                component_id="R1",
                node_a=NODE_IN,
                node_b=NODE_MID,
                resistance=Quantity(R1_OHM, "ohm"),
            ),
            Resistor(
                component_id="R2",
                node_a=NODE_MID,
                node_b=NODE_REF,
                resistance=Quantity(float(r2_ohm), "ohm"),
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="VS",
                positive_node=NODE_IN,
                negative_node=NODE_REF,
                voltage=Quantity(float(source_voltage_volt), "volt"),
            ),
        ),
        description="E2 voltage divider, constant R2 under inference",
    )


def solver_vmid(source_voltage_volt: float, r2_ohm: float, *, run_id: str) -> float:
    """One forward evaluation through the full solver lifecycle."""
    result = solve_circuit(
        build_divider_circuit(source_voltage_volt, r2_ohm, circuit_id=run_id),
        run_id=run_id,
    )
    if result.convergence is not ConvergenceState.CONVERGED:
        raise RuntimeError(
            f"solver did not converge at Vs={source_voltage_volt}, R2={r2_ohm}"
        )
    if result.validation.status is not ValidationOutcome.PASS:
        raise RuntimeError(
            f"solver validation {result.validation.status.value} at "
            f"Vs={source_voltage_volt}, R2={r2_ohm}"
        )
    return result.values[VMID_METRIC].magnitude_in("volt")


#: Forward map cache: source voltage -> predicted V_mid over the theta grid.
_FORWARD_CACHE: dict[float, np.ndarray] = {}


def forward_predictions(source_voltage_volt: float) -> np.ndarray:
    """Solver-predicted V_mid for every theta on the frozen grid. Cached."""
    key = float(source_voltage_volt)
    cached = _FORWARD_CACHE.get(key)
    if cached is None:
        grid = theta_grid()
        values = np.array(
            [
                solver_vmid(key, float(r2), run_id=f"e2-fmap-vs{key:g}-i{i:04d}")
                for i, r2 in enumerate(grid)
            ]
        )
        values.flags.writeable = False
        _FORWARD_CACHE[key] = values
        cached = values
    return cached


# =====================================================================
# Observations and the conditional posterior
# =====================================================================

@dataclass(frozen=True)
class E2Observation:
    """One assimilated measurement, with its declared likelihood."""

    action_id: str
    source_voltage_volt: float
    y_volt: float
    sigma_volt: float

    def __post_init__(self) -> None:
        if self.sigma_volt <= 0.0:
            raise ValueError("observation noise must be positive")


def prior_weights() -> np.ndarray:
    grid = theta_grid()
    return np.full(len(grid), 1.0 / len(grid))


def posterior_weights(
    observations: Sequence[E2Observation],
    prior: np.ndarray | None = None,
) -> np.ndarray:
    """p(R2 | observations, M_const) by exact normalized reweighting.

    Deterministic and order-independent. Note what this function CANNOT do: it
    has no way to express "no constant fits these observations". Handed
    mutually contradictory measurements it returns the least-bad constant, with
    a perfectly well-formed and possibly very narrow distribution around it.
    That is not a defect to be patched here — it is the behaviour E2 exists to
    expose, and patching it inside the posterior would hide the finding.
    """
    weights = prior_weights() if prior is None else np.asarray(prior, float)
    if not math.isclose(float(weights.sum()), 1.0, rel_tol=1e-9):
        raise ValueError("prior must be normalized")
    log_weights = np.log(np.where(weights > 0.0, weights, np.finfo(float).tiny))
    for observation in observations:
        predicted = forward_predictions(observation.source_voltage_volt)
        residual = observation.y_volt - predicted
        log_weights = log_weights - 0.5 * (residual / observation.sigma_volt) ** 2
    finite = log_weights[np.isfinite(log_weights)]
    if finite.size == 0:
        raise ValueError("every theta has zero likelihood")
    shifted = np.exp(log_weights - finite.max())
    total = shifted.sum()
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("posterior failed to normalize")
    return shifted / total


def observations_digest(observations: Sequence[E2Observation]) -> str:
    """Order-independent digest of the assimilated evidence + configuration.

    This is what binds a predictive commitment to the exact evidence state it
    was computed from. Two commitments carrying the same digest were computed
    from the same admitted set; one carrying a different digest was not, and
    the ledger refuses to score it as though it had been.
    """
    payload = {
        "config": config_hash(),
        "observations": sorted(
            [
                [o.action_id, o.source_voltage_volt, o.y_volt, o.sigma_volt]
                for o in observations
            ]
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# =====================================================================
# Terminal decision and EVPI — inside the assumed family
# =====================================================================

def _utility_vectors() -> dict[str, np.ndarray]:
    above = theta_grid() > THRESHOLD_OHM
    return {
        "A": -np.where(above, LOSS_A_ABOVE, LOSS_A_BELOW),
        "B": -np.where(above, LOSS_B_ABOVE, LOSS_B_BELOW),
    }


def decision_expected_utilities(weights: np.ndarray) -> dict[str, float]:
    return {
        decision: float(np.dot(weights, vector))
        for decision, vector in _utility_vectors().items()
    }


def best_decision(weights: np.ndarray) -> tuple[str, float]:
    scored = decision_expected_utilities(weights)
    decision = max(sorted(scored), key=lambda d: scored[d])
    return decision, scored[decision]


def p_above(weights: np.ndarray) -> float:
    return float(np.asarray(weights)[theta_grid() > THRESHOLD_OHM].sum())


def evpi(weights: np.ndarray) -> float:
    """EVPI *within* M_const. It prices out uncertainty about which constant,
    and is structurally blind to the possibility that no constant is right."""
    vectors = _utility_vectors()
    per_theta_best = np.maximum(vectors["A"], vectors["B"])
    _, without = best_decision(weights)
    return float(np.dot(weights, per_theta_best)) - without


def posterior_entropy(weights: np.ndarray) -> float:
    """Shannon entropy of the discrete conditional posterior, in nats."""
    w = np.asarray(weights, float)
    positive = w[w > 0.0]
    return float(-np.sum(positive * np.log(positive)))


def posterior_summary(weights: np.ndarray) -> dict[str, float | int | str]:
    grid = theta_grid()
    mean = float(np.dot(weights, grid))
    sd = float(np.sqrt(max(np.dot(weights, (grid - mean) ** 2), 0.0)))
    decision, value = best_decision(weights)
    return {
        "conditional_on": "M_const (R2 constant)",
        "mean_r2_ohm": mean,
        "sd_r2_ohm": sd,
        "entropy_nats": posterior_entropy(weights),
        "p_above_threshold": p_above(weights),
        "bayes_decision": decision,
        "expected_utility": value,
        "evpi": evpi(weights),
        "effective_support_points": int(np.count_nonzero(weights > 1e-12)),
    }


# =====================================================================
# The predictive distribution — exact finite Gaussian mixture
# =====================================================================

@dataclass(frozen=True)
class PredictiveMixture:
    """p(y | data, action, M_const) as an exact finite Gaussian mixture.

    ``means`` are solver predictions, one per grid point; ``weights`` are the
    conditional posterior; ``sigma`` is the declared observation noise. This is
    the whole predictive — nothing is approximated and nothing is sampled, so
    the object can be serialized, hashed and later re-scored bit-exactly.
    """

    means: tuple[float, ...]
    weights: tuple[float, ...]
    sigma: float

    def __post_init__(self) -> None:
        if len(self.means) != len(self.weights):
            raise ValueError("mixture means and weights must align")
        if self.sigma <= 0.0:
            raise ValueError("predictive sigma must be positive")

    @property
    def mean(self) -> float:
        return float(np.dot(np.asarray(self.weights), np.asarray(self.means)))

    @property
    def latent_sd(self) -> float:
        m = np.asarray(self.means)
        w = np.asarray(self.weights)
        mu = float(np.dot(w, m))
        return float(math.sqrt(max(float(np.dot(w, (m - mu) ** 2)), 0.0)))

    @property
    def sd(self) -> float:
        return float(math.sqrt(self.latent_sd**2 + self.sigma**2))

    # -- exact tail probabilities -------------------------------------------
    def lower_tail(self, y: float) -> float:
        """P(Y <= y). Computed with erfc per component, no cancellation."""
        scale = self.sigma * _SQRT2
        return float(
            sum(
                w * 0.5 * math.erfc((m - y) / scale)
                for m, w in zip(self.means, self.weights)
                if w > 0.0
            )
        )

    def upper_tail(self, y: float) -> float:
        """P(Y >= y). Computed with erfc per component, no cancellation."""
        scale = self.sigma * _SQRT2
        return float(
            sum(
                w * 0.5 * math.erfc((y - m) / scale)
                for m, w in zip(self.means, self.weights)
                if w > 0.0
            )
        )

    def two_sided_tail(self, y: float) -> float:
        """The preregistered surprise statistic.

        2 * min(P(Y <= y), P(Y >= y)), capped at 1. Exact for this mixture, and
        a probability rather than a score — which is what makes a preregistered
        threshold on it meaningful rather than decorative.
        """
        return float(min(1.0, 2.0 * min(self.lower_tail(y), self.upper_tail(y))))

    def log_density(self, y: float) -> float:
        """log p(y). Log-sum-exp, so a 20-sigma point is still finite."""
        terms = []
        for m, w in zip(self.means, self.weights):
            if w <= 0.0:
                continue
            terms.append(math.log(w) - 0.5 * ((y - m) / self.sigma) ** 2)
        if not terms:
            raise ValueError("predictive mixture has no support")
        peak = max(terms)
        total = sum(math.exp(t - peak) for t in terms)
        return peak + math.log(total) - math.log(self.sigma) - _LOG_SQRT_2PI

    def negative_log_density(self, y: float) -> float:
        """Prequential NLPD — the secondary, scale-free surprise statistic."""
        return -self.log_density(y)


def predictive_mixture(weights: np.ndarray, action: E2Action) -> PredictiveMixture:
    """The predictive for a measurement that has NOT been taken yet."""
    predicted = forward_predictions(action.source_voltage_volt)
    w = np.asarray(weights, float)
    keep = w > 1e-15
    return PredictiveMixture(
        means=tuple(float(v) for v in predicted[keep]),
        weights=tuple(float(v / w[keep].sum()) for v in w[keep]),
        sigma=float(action.noise_sigma_volt),
    )


def predictive_summary(weights: np.ndarray, action: E2Action) -> dict[str, float]:
    mixture = predictive_mixture(weights, action)
    return {
        "mean_volt": mixture.mean,
        "sd_volt": mixture.sd,
        "latent_sd_volt": mixture.latent_sd,
    }


# =====================================================================
# The JOINT predictive over several conditions at once
# =====================================================================

@dataclass(frozen=True)
class JointPredictive:
    """p(y_1..y_k | D, action_1..k, M_const) — the exact joint, not a product.

    WHY THIS EXISTS
    ---------------
    The marginal predictive at each condition is exactly right, and each
    marginal tail probability is exactly Uniform(0,1) under the null. But the
    conditions are **not independent**: they are conditionally independent
    GIVEN theta and share one latent theta, so marginalizing the calibration
    posterior induces positive dependence between them. A shift in theta moves
    every prediction in the same direction, by an amount proportional to that
    condition's sensitivity dV_mid/dR.

    Combining the marginal tails as if they were independent therefore
    understates the null variability of any aggregate built from them. The
    honest object is this one:

        p(y_1..y_k | D) = SUM_theta p(theta | D) PROD_j p(y_j | theta, a_j)

    which is a finite mixture of independent-Gaussian blocks — exact on the
    frozen grid, no sampling, no asymptotics.
    """

    #: Row j is the solver's predictions for condition j over the shared grid.
    component_means: tuple[tuple[float, ...], ...]
    sigmas: tuple[float, ...]
    #: The ONE calibration posterior every condition is conditional on.
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        n = len(self.weights)
        if not self.component_means:
            raise ValueError("joint predictive needs at least one condition")
        if len(self.sigmas) != len(self.component_means):
            raise ValueError("one sigma per condition is required")
        for row in self.component_means:
            if len(row) != n:
                raise ValueError(
                    "every condition must share the same posterior support; "
                    "conditions built from different evidence states cannot be "
                    "combined into one joint predictive"
                )

    @property
    def n_conditions(self) -> int:
        return len(self.component_means)

    def _matrices(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (
            np.asarray(self.component_means, float),   # k x n
            np.asarray(self.sigmas, float),            # k
            np.asarray(self.weights, float),           # n
        )

    def log_density(self, y: Sequence[float]) -> float:
        """log p(y_1..y_k | D). Exact, by log-sum-exp over the grid."""
        return float(self.log_density_batch(np.asarray(y, float)[None, :])[0])

    def log_density_batch(self, ys: np.ndarray) -> np.ndarray:
        """Vectorized over rows of ``ys`` (each row is one full k-vector)."""
        means, sigmas, weights = self._matrices()
        ys = np.atleast_2d(np.asarray(ys, float))
        if ys.shape[1] != self.n_conditions:
            raise ValueError("each row must supply one value per condition")
        # (draws, k, n) standardized residuals -> summed over k inside the log
        residual = (ys[:, :, None] - means[None, :, :]) / sigmas[None, :, None]
        exponent = -0.5 * np.sum(residual * residual, axis=1)     # draws x n
        exponent = exponent + np.log(
            np.where(weights > 0.0, weights, np.finfo(float).tiny)
        )[None, :]
        peak = exponent.max(axis=1, keepdims=True)
        total = np.log(np.sum(np.exp(exponent - peak), axis=1)) + peak[:, 0]
        normalizer = float(
            np.sum(np.log(sigmas)) + self.n_conditions * _LOG_SQRT_2PI
        )
        return total - normalizer

    def log_score(self, y: Sequence[float]) -> float:
        """The preregistered joint discrepancy: -log p(y | D, M_const).

        Large means the complete observed vector sits where the assumed family
        — having already been given every chance to move theta within its own
        calibration posterior — says it should not be.
        """
        return -self.log_density(y)

    def simulate(self, n_draws: int, seed: int) -> np.ndarray:
        """Draw complete k-vectors from the joint predictive under M_const.

        One theta per draw, shared across all k conditions. That shared draw is
        precisely the dependence a per-condition simulation would destroy.
        """
        means, sigmas, weights = self._matrices()
        rng = np.random.default_rng(seed)
        w = weights / weights.sum()
        index = rng.choice(len(w), size=int(n_draws), p=w)
        return means[:, index].T + rng.normal(
            0.0, 1.0, size=(int(n_draws), self.n_conditions)
        ) * sigmas[None, :]

    def marginal(self, condition: int) -> PredictiveMixture:
        return PredictiveMixture(
            means=self.component_means[condition],
            weights=self.weights,
            sigma=self.sigmas[condition],
        )

    def covariance(self) -> np.ndarray:
        """Exact Cov(y) = Cov_theta(mu(theta)) + diag(sigma^2)."""
        means, sigmas, weights = self._matrices()
        centered = means - (means @ weights)[:, None]
        return (centered * weights[None, :]) @ centered.T + np.diag(sigmas**2)

    def correlation(self) -> np.ndarray:
        """Exact correlation matrix. Off-diagonals are the dependence that
        makes an independence-based aggregate reference invalid."""
        cov = self.covariance()
        sd = np.sqrt(np.diag(cov))
        return cov / np.outer(sd, sd)


# =====================================================================
# EVSI — one-step, by deterministic quadrature, inside the assumed family
# =====================================================================

def evsi(weights: np.ndarray, action: E2Action) -> float:
    """EVSI(a) = E_y[ max_d E[u | D, y, a] ] - max_d E[u | D], within M_const.

    Inherited unchanged from E1's mathematics. E2 keeps reporting it in order
    to demonstrate its limit: it prices the information a measurement carries
    ABOUT WHICH CONSTANT, and once the posterior is sharp it goes to zero — no
    matter how wrong the constant-R premise is. A near-zero EVSI is therefore
    not evidence that there is nothing left to learn.
    """
    predicted = forward_predictions(action.source_voltage_volt)
    sigma = action.noise_sigma_volt
    vectors = _utility_vectors()
    utilities = np.vstack([vectors["A"], vectors["B"]])

    mean = float(np.dot(weights, predicted))
    spread = float(np.dot(weights, (predicted - mean) ** 2))
    sigma_total = math.sqrt(max(spread, 0.0) + sigma**2)
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
    residual /= sigma
    residual *= residual
    residual *= -0.5
    kernel = np.exp(residual - residual.max(axis=1, keepdims=True))
    joint = kernel * np.asarray(weights)[None, :]
    totals = joint.sum(axis=1, keepdims=True)
    density = (
        totals[:, 0]
        * np.exp(residual.max(axis=1))
        / (sigma * math.sqrt(2.0 * math.pi))
    )
    safe = totals > 0.0
    updated = np.where(safe, joint / np.where(safe, totals, 1.0), 0.0)

    per_y_best = (updated @ utilities.T).max(axis=1)
    captured = float(np.sum(quad * density))
    if captured <= 0.0:
        raise ValueError("predictive density integrated to zero")
    expected_after = float(np.sum(quad * density * per_y_best)) / captured

    _, before = best_decision(weights)
    return expected_after - before


def evsi_table(
    weights: np.ndarray, actions: Sequence[E2Action] = ACTIONS
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for action in actions:
        value = evsi(weights, action)
        summary = predictive_summary(weights, action)
        out[action.action_id] = {
            "evsi": value,
            "cost": action.cost,
            "net": value - action.cost,
            "predictive_mean_volt": summary["mean_volt"],
            "predictive_sd_volt": summary["sd_volt"],
        }
    return out
