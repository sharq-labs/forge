"""E1 decision-path model: the REAL Electrical solver as forward map.

DECISION-PATH MODULE. It must never import :mod:`e1_truth`; a test parses the
import graph.

The forward model here is not an equation — it is the repository's actual
``solve_circuit`` MNA lifecycle, run once per grid point per operating
condition and cached (the solver is deterministic, so caching is exact). If
the solver fails or its validation report does not pass at ANY grid point, the
model refuses rather than interpolating around the hole: inference over an
unverified forward map would be exactly the mistake E1 exists to catch.

Everything downstream mirrors the S1 mathematics on a 1-D grid: explicit
prior, declared Gaussian observation likelihood, exact normalized reweighting,
predictive by mixture, EVPI/EVSI by deterministic quadrature. No sampler, no
framework, no hand-authored utility gain.
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

from .e1_config import (
    ACTIONS,
    E1Action,
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


def build_divider_circuit(
    source_voltage_volt: float, r2_ohm: float, *, circuit_id: str
) -> DCCircuit:
    """The declared topology, with R2 as the candidate parameter."""
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
        description="E1 voltage divider, R2 under inference",
    )


def solver_vmid(source_voltage_volt: float, r2_ohm: float, *, run_id: str) -> float:
    """One forward evaluation through the full solver lifecycle.

    Refuses anything short of a converged solve with a passing validation
    report — a number extracted past a failed check is not a prediction.
    """
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
                solver_vmid(
                    key, float(r2), run_id=f"e1-fmap-vs{key:g}-i{i:03d}"
                )
                for i, r2 in enumerate(grid)
            ]
        )
        values.flags.writeable = False
        _FORWARD_CACHE[key] = values
        cached = values
    return cached


# =====================================================================
# Observations and the posterior
# =====================================================================

@dataclass(frozen=True)
class E1Observation:
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
    observations: Sequence[E1Observation],
    prior: np.ndarray | None = None,
) -> np.ndarray:
    """Exact normalized reweighting. Deterministic and order-independent."""
    weights = prior_weights() if prior is None else np.asarray(prior, float)
    if not math.isclose(float(weights.sum()), 1.0, rel_tol=1e-9):
        raise ValueError("prior must be normalized")
    log_weights = np.log(
        np.where(weights > 0.0, weights, np.finfo(float).tiny)
    )
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


def observations_digest(observations: Sequence[E1Observation]) -> str:
    """Order-independent digest of the assimilated evidence + configuration."""
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
# Terminal decision, EVPI, predictive, EVSI
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
    vectors = _utility_vectors()
    per_theta_best = np.maximum(vectors["A"], vectors["B"])
    _, without = best_decision(weights)
    return float(np.dot(weights, per_theta_best)) - without


def predictive_summary(
    weights: np.ndarray, action: E1Action
) -> dict[str, float]:
    """Predictive mean/sd for the would-be measurement, BEFORE observing it."""
    predicted = forward_predictions(action.source_voltage_volt)
    mean = float(np.dot(weights, predicted))
    spread = float(np.dot(weights, (predicted - mean) ** 2))
    return {
        "mean_volt": mean,
        "sd_volt": math.sqrt(max(spread, 0.0) + action.noise_sigma_volt**2),
        "latent_sd_volt": math.sqrt(max(spread, 0.0)),
    }


def evsi(weights: np.ndarray, action: E1Action) -> float:
    """One-step EVSI by deterministic quadrature over the predictive.

        EVSI(a) = E_y[ max_d E[u(d,theta) | D, y, a] ] - max_d E[u(d,theta) | D]

    The inner expectation is an exact grid sum; the outer is a trapezoid rule
    over the predictive mixture density, renormalized by captured mass so a
    truncation artifact cannot masquerade as value.
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
    joint = kernel * weights[None, :]
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
    weights: np.ndarray, actions: Sequence[E1Action] = ACTIONS
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
