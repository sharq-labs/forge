"""E1 preregistered configuration — decision-visible half.

Frozen BEFORE the first scored run. The grader-only true parameter lives in
:mod:`e1_truth`; the preregistration hash over BOTH halves is computed by the
harness so this module never has to import the truth.

THE CIRCUIT (declared topology)
-------------------------------
A two-resistor voltage divider:

    vin ──[R1 = 1000 Ω known]── mid ──[R2 unknown]── gnd(reference)
     │                                                  │
     └──────────────[Vs, action-controlled]─────────────┘

Observed QoI: the node voltage at ``mid``. Analytically
``V_mid = Vs · R2 / (R1 + R2)`` — but the decision path never uses that
formula; its forward model is the actual :func:`solve_circuit` MNA path, and
the closed form belongs to the grader.

THE DECISION
------------
Classify the unknown resistance against a predeclared threshold:

    A  =  "R2 > 1200 Ω"        B  =  "R2 <= 1200 Ω"

    loss(A | actually below) = 4.0      loss(B | actually above) = 1.0
    correct decisions cost 0

Asymmetric on purpose: the indifference point is P(above) = 0.8, not 0.5, so
the utility genuinely governs the decision.

ONE unknown parameter, deliberately: E1 is an integration and verification
experiment, and structural identifiability questions must not be allowed to
dominate it. With a single theta, EVPPI(R2) = EVPI trivially — the parameter is
the complete latent decision-relevant state — and that is stated rather than
dressed up.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

EXPERIMENT_ID = "E1"
EXPERIMENT_NAME = "electrical_quantitative_verification"
EXPERIMENT_VERSION = "1.0.0"
BASE_COMMIT = "bcbd2faa37d2fae6106c5a0c185c83ed443e5217"

# --- circuit (known part) ----------------------------------------------------
R1_OHM = 1000.0
NODE_IN = "vin"
NODE_MID = "mid"
NODE_REF = "gnd"
VMID_METRIC = f"node_voltage:{NODE_MID}"

# --- unknown parameter grid + prior -----------------------------------------
THETA_MIN_OHM = 500.0
THETA_MAX_OHM = 2500.0
THETA_POINTS = 101                      # 20 ohm spacing
PRIOR = "uniform"

# --- terminal decision -------------------------------------------------------
DECISION_ID = "r2_class"
THRESHOLD_OHM = 1200.0
LOSS_A_BELOW = 4.0                       # decide "above" when it is below
LOSS_B_ABOVE = 1.0                       # decide "below" when it is above
LOSS_A_ABOVE = 0.0
LOSS_B_BELOW = 0.0

# --- candidate actions -------------------------------------------------------
#: Benchmark observation noise is INJECTED BY THE BENCHMARK, not produced by
#: the solver — the solver is deterministic and this is stated honestly. The
#: sigma is part of the declared observation model p(y | theta, action).


@dataclass(frozen=True)
class E1Action:
    action_id: str
    source_voltage_volt: float
    noise_sigma_volt: float
    cost: float                          # declared benchmark cost units ("hour")
    description: str


ACTIONS: tuple[E1Action, ...] = (
    E1Action(
        action_id="measure_vmid_10V",
        source_voltage_volt=10.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        description="measure V_mid at Vs = 10 V with the standard instrument",
    ),
    E1Action(
        action_id="measure_vmid_0V01",
        source_voltage_volt=0.01,
        noise_sigma_volt=0.05,
        cost=0.01,
        description=(
            "measure V_mid at Vs = 0.01 V — the signal spread across the whole "
            "prior (~4 mV) is far below the 50 mV noise floor"
        ),
    ),
    E1Action(
        action_id="measure_vmid_10V_premium",
        source_voltage_volt=10.0,
        noise_sigma_volt=0.005,
        cost=5.0,
        description=(
            "measure V_mid at Vs = 10 V with a premium low-noise instrument; "
            "informative, and priced far above the total information value"
        ),
    ),
)

TOTAL_BUDGET = 10.0
COST_UNIT = "hour"                       # declared benchmark cost unit

# --- solver verification gate ------------------------------------------------
#: Preregistered (Vs, R2) points at which the real solver must agree with the
#: analytic oracle before any inference is trusted. Deliberately truth-free:
#: the grader's true parameter appears nowhere in this module.
VERIFICATION_POINTS: tuple[tuple[float, float], ...] = (
    (10.0, 500.0),
    (10.0, 1000.0),
    (10.0, 1200.0),
    (10.0, 2000.0),
    (10.0, 2500.0),
    (0.01, 1000.0),
    (2.0, 900.0),
    (5.0, 1600.0),
)
VERIFICATION_REL_TOL = 1e-9
VERIFICATION_ABS_TOL_VOLT = 1e-12

# --- quadrature for EVSI -----------------------------------------------------
Y_NODES = 241
Y_SPAN_SIGMAS = 7.0

# --- benchmark noise seed ----------------------------------------------------
NOISE_SEED = 20260814

# --- campaign ----------------------------------------------------------------
MAX_ITERATIONS = 2
CAMPAIGN_ID = "e1-electrical"
CHARTER_VERSION = "1"


def theta_grid() -> np.ndarray:
    return np.linspace(THETA_MIN_OHM, THETA_MAX_OHM, THETA_POINTS)


def indifference_probability() -> float:
    """P(above) at which decisions A and B carry equal expected loss."""
    return LOSS_A_BELOW / (LOSS_A_BELOW + LOSS_B_ABOVE)


def config_payload() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": EXPERIMENT_VERSION,
        "base_commit": BASE_COMMIT,
        "circuit": {
            "topology": "two_resistor_voltage_divider",
            "r1_ohm": R1_OHM,
            "nodes": [NODE_IN, NODE_MID, NODE_REF],
            "reference": NODE_REF,
            "observed_metric": VMID_METRIC,
        },
        "theta": {
            "parameter": "R2_ohm",
            "grid_min": THETA_MIN_OHM,
            "grid_max": THETA_MAX_OHM,
            "grid_points": THETA_POINTS,
            "prior": PRIOR,
        },
        "terminal_decision": {
            "decision_id": DECISION_ID,
            "rule": "A iff R2 > threshold",
            "threshold_ohm": THRESHOLD_OHM,
            "loss": {
                "A_below": LOSS_A_BELOW,
                "B_above": LOSS_B_ABOVE,
                "A_above": LOSS_A_ABOVE,
                "B_below": LOSS_B_BELOW,
            },
            "indifference_probability": indifference_probability(),
        },
        "actions": [
            {
                "action_id": action.action_id,
                "source_voltage_volt": action.source_voltage_volt,
                "noise_sigma_volt": action.noise_sigma_volt,
                "cost": action.cost,
            }
            for action in ACTIONS
        ],
        "budget": {"total": TOTAL_BUDGET, "cost_unit": COST_UNIT},
        "verification": {
            "points": [list(p) for p in VERIFICATION_POINTS],
            "rel_tol": VERIFICATION_REL_TOL,
            "abs_tol_volt": VERIFICATION_ABS_TOL_VOLT,
        },
        "quadrature": {"y_nodes": Y_NODES, "y_span_sigmas": Y_SPAN_SIGMAS},
        "noise_seed": NOISE_SEED,
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "charter_version": CHARTER_VERSION,
            "max_iterations": MAX_ITERATIONS,
        },
        "evppi_statement": (
            "EVPPI(R2) = EVPI because R2 is the complete latent "
            "decision-relevant state of this single-parameter problem"
        ),
        "stopping_interpretation": (
            "a STOP_PROPOSAL from the campaign loop is an economic statement; "
            "E1 registers no stopping criterion, so the Arbiter stopping "
            "review is expected to return STOP_NOT_ASSESSED and the loop to "
            "pause. The terminal decision is then graded from the final "
            "posterior."
        ),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
