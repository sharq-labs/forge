"""E2 preregistered configuration — decision-visible half.

Frozen BEFORE the first scored run. The grader-only misspecified truth law
lives in :mod:`e2_truth`; the preregistration hash over BOTH halves is computed
by the harness, so this module never has to import the truth.

THE CIRCUIT (E1-derived, unchanged)
-----------------------------------
    vin ──[R1 = 1000 Ω known]── mid ──[R2 unknown]── gnd(reference)
     │                                                  │
     └──────────────[Vs, action-controlled]─────────────┘

Observed QoI: ``node_voltage:mid``. The forward model on the decision path is
the repository's real ``solve_circuit`` MNA lifecycle, exactly as in E1.

THE ASSUMED MODEL FAMILY
------------------------
    M_const  =  { R2 = c  :  c in [500, 2500] Ω }

One constant parameter, condition-independent. This is the family the
posterior, the predictive, EVPI and EVSI are all conditional on, and E2's whole
point is that the grader truth is deliberately NOT in it. The decision path is
never told, and nothing in this module or in :mod:`e2_model` is adjusted to
compensate. Every posterior statement E2 makes is therefore

    p(R2 | data, M_const)

and never "the probability that R2 is really c".

WHY THE GRID IS FINER THAN E1'S
-------------------------------
E1 used 101 points (20 Ω). E2 assimilates four calibration measurements, so
the conditional posterior contracts to sd ≈ 14 Ω — under a 20 Ω grid that is
less than one cell, and a predictive built from a one-point posterior would be
an artifact of discretization rather than of inference. 401 points (5 Ω) keeps
the predictive mixture well resolved in voltage space at every challenge
condition (component spacing stays below the observation noise), so the tail
probabilities the adequacy rule consumes are properties of the model, not of
the mesh.

THE TWO PHASES
--------------
PHASE 1 (calibration) measures only at Vs = 10 V, a single operating
condition. Under ANY law that is smooth in Vs, one condition is fittable by
some constant — so the posterior is expected to contract sharply and look
healthy. That is deliberate: it is what a confident-but-wrong model looks like
from the inside.

PHASE 2 (challenge) measures at conditions the calibration never visited. The
predictive distributions for those conditions are computed and content-hashed
from the calibration-only evidence, the ledger is SEALED, and only then are the
challenge measurements executed. A prediction that cannot be revised after the
fact is what converts an execution into a test.

Vs = 10 V appears in BOTH phases on purpose, as an internal null. Its
interpretation must be stated carefully and narrowly. The synthetic grader law
was CONSTRUCTED to vanish at the calibration condition, so under this benchmark
a clean result there is expected from the misspecification and is what
distinguishes it from a condition-independent additive offset in the harness.
That is a statement about this constructed failure mode only. It does NOT
exclude alternative fault mechanisms: a real instrument or wiring fault that
happened to be condition-dependent, or one that scaled with the drive, would
also leave the calibration condition looking clean. The null discriminates
against ONE alternative explanation, not against all of them.

THE ADEQUACY RULE (preregistered, not tuned)
--------------------------------------------
Per challenge condition, the two-sided posterior-predictive tail probability of
the observed value under its own frozen pre-observation predictive. Aggregated
by Fisher's method over all challenge conditions. Classification requires BOTH
a minimum count of individually extreme conditions AND an extreme aggregate —
the conjunction is what makes a single unlucky point structurally incapable of
producing the strongest verdict.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

EXPERIMENT_ID = "E2"
EXPERIMENT_NAME = "model_adequacy_predictive_surprise"
EXPERIMENT_VERSION = "1.1.0"

#: v1.0.0 combined the six per-condition tail probabilities with Fisher's
#: method and referred the statistic to chi-square on 2N degrees of freedom.
#: That reference assumes the tails are INDEPENDENT. They are not: the six
#: predictions are conditionally independent given theta but share one
#: calibration posterior, and marginalizing it induces strictly positive
#: dependence (exact correlations 0.09 to 0.63, largest between exactly the
#: high-voltage conditions that drove the verdict). Positive dependence
#: inflates the null variance of Fisher's statistic above the 2*df the
#: chi-square reference assumes, so the reported aggregate p-value was
#: ANTI-CONSERVATIVE — too small, in the direction that overstates evidence.
#:
#: This is a statistical validity bug, corrected here rather than argued
#: around. The per-condition tails were never affected: each marginal tail is
#: exactly Uniform(0,1) under the null, so ALPHA_EXTREME and K_MIN_EXTREME are
#: carried over unchanged. Only the aggregate is replaced.
SUPERSEDED_CONFIG_HASH = (
    "dbe7c538e6f8af198be14bd6863d91249b748969c69b27c308c7df38b0275bce"
)
CORRECTION_RECORD = (
    "v1.1.0 replaces the Fisher/chi-square(2N) aggregate of v1.0.0 with the "
    "exact joint posterior-predictive log score for the complete challenge "
    "vector, calibrated by posterior-predictive simulation under M_const. The "
    "v1.0.0 aggregate assumed independence between tail probabilities that "
    "share a common latent R2 and is therefore not a valid reference "
    "distribution. Corrected as a validity fix, not a redesign: the "
    "per-condition statistic, its threshold, K_MIN_EXTREME, the challenge "
    "set, the noise seed, the grid, the prior, the calibration schedule and "
    "the hidden law are all unchanged."
)

#: The E1 freeze E2 is built on. Verified by test, not merely stated.
BASE_COMMIT = "a57a1f8062e23b51a295081d9d1c0863ee0ddb83"
E1_CONFIG_HASH = (
    "6dbf8febd6989b42fcfd58f4139ffa34330808018a1b427bb5042f43a38e847e"
)
#: Newline-normalized SHA-256 of every E1 file. A test recomputes these, so
#: "E1 is unchanged" is checked rather than asserted, and without needing git.
E1_FROZEN_FILE_DIGESTS: dict[str, str] = {
    "experiments/electrical_e1/__init__.py":
        "4336de8ccad63c8a87766a4085c5faaf507a651d8761175b8f6975ee09c1e5c5",
    "experiments/electrical_e1/e1_config.py":
        "6dcb3285ac65f9c3c4f1f07b0307bf0828df01308b31e1e02a85b88fd201dcb2",
    "experiments/electrical_e1/e1_model.py":
        "7acc376b32ba91550e7f4da3c61fa882f91d944bbb7124bcb0e2dad812b45715",
    "experiments/electrical_e1/e1_truth.py":
        "32fb8c67ffdf13f235e04a69c22796bbcc4e64f3f1ece60415bc45cfcfadf9b3",
    "experiments/electrical_e1/e1_harness.py":
        "467a68146f55d0f8e4deef467288a3c8e4b9a0100ddbb39b67fb5614e19df14a",
    "experiments/electrical_e1/e1_run.py":
        "d2538d3ac2bcb1b6ca1a1a4c04bb01ac8ee70cdaecfa54f7b35d934c2552914b",
    "tests/test_sria_e1_electrical.py":
        "2c1291081cdae8e67d0f361a33b46583d9f5a5aa7a5be488a807cc19e34a9ed1",
}

# --- circuit (known part, identical to E1) -----------------------------------
R1_OHM = 1000.0
NODE_IN = "vin"
NODE_MID = "mid"
NODE_REF = "gnd"
VMID_METRIC = f"node_voltage:{NODE_MID}"

# --- the ASSUMED model family ------------------------------------------------
ASSUMED_MODEL_FAMILY_ID = "constant_r2"
ASSUMED_MODEL_FAMILY = (
    "R2(condition) = c, a single condition-independent constant on the frozen "
    "grid; the decision path admits no other shape"
)
THETA_MIN_OHM = 500.0
THETA_MAX_OHM = 2500.0
THETA_POINTS = 401                       # 5 ohm spacing
PRIOR = "uniform"

# --- terminal decision (identical to E1) -------------------------------------
DECISION_ID = "r2_class"
THRESHOLD_OHM = 1200.0
LOSS_A_BELOW = 4.0                       # decide "above" when it is below
LOSS_B_ABOVE = 1.0                       # decide "below" when it is above
LOSS_A_ABOVE = 0.0
LOSS_B_BELOW = 0.0


@dataclass(frozen=True)
class E2Action:
    action_id: str
    source_voltage_volt: float
    noise_sigma_volt: float
    cost: float
    phase: str                           # "calibration" | "challenge"
    repeats: int
    description: str


# --- PHASE 1: calibration ----------------------------------------------------
CALIBRATION_ACTIONS: tuple[E2Action, ...] = (
    E2Action(
        action_id="calibrate_vmid_10V",
        source_voltage_volt=10.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="calibration",
        repeats=4,
        description=(
            "four repeats of V_mid at Vs = 10 V — one operating condition, "
            "which any smooth law can be fitted at by some constant R"
        ),
    ),
)

# --- PHASE 2: challenge ------------------------------------------------------
#: Conditions the calibration never visited, plus one that it did. Preregistered
#: in this order; the predictive for each is committed before any is executed.
CHALLENGE_ACTIONS: tuple[E2Action, ...] = (
    E2Action(
        action_id="challenge_vmid_04V",
        source_voltage_volt=4.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="challenge",
        repeats=1,
        description=(
            "below the calibration condition; the absolute-noise instrument "
            "has little leverage here, so a weak result is expected"
        ),
    ),
    E2Action(
        action_id="challenge_vmid_10V",
        source_voltage_volt=10.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="challenge",
        repeats=1,
        description=(
            "INTERNAL NULL — the calibration condition itself. The synthetic "
            "grader law was constructed to vanish here, so a clean result "
            "distinguishes this benchmark's failure mode from a "
            "condition-independent offset. It does not rule out other fault "
            "mechanisms, including condition-dependent instrument faults"
        ),
    ),
    E2Action(
        action_id="challenge_vmid_16V",
        source_voltage_volt=16.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="challenge",
        repeats=1,
        description="first extrapolated condition above calibration",
    ),
    E2Action(
        action_id="challenge_vmid_20V",
        source_voltage_volt=20.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="challenge",
        repeats=1,
        description="twice the calibration drive",
    ),
    E2Action(
        action_id="challenge_vmid_24V",
        source_voltage_volt=24.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="challenge",
        repeats=1,
        description="further from the calibrated condition",
    ),
    E2Action(
        action_id="challenge_vmid_28V",
        source_voltage_volt=28.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="challenge",
        repeats=1,
        description="furthest preregistered condition",
    ),
)

ACTIONS: tuple[E2Action, ...] = CALIBRATION_ACTIONS + CHALLENGE_ACTIONS

TOTAL_BUDGET = 10.0
COST_UNIT = "hour"

# --- solver verification gate ------------------------------------------------
#: Truth-free (Vs, R2) points at which the real solver must agree with the
#: closed-form divider relation before any inference is trusted. Chosen to span
#: the full challenge voltage range, because E2 predicts at conditions E1 never
#: verified. Verifying the SOLVER at these points says nothing whatever about
#: whether the constant-R FAMILY is adequate — that distinction is the whole
#: experiment, and the certificate keeps the two rows apart.
VERIFICATION_POINTS: tuple[tuple[float, float], ...] = (
    (4.0, 500.0),
    (4.0, 1378.0),
    (10.0, 1000.0),
    (10.0, 1378.0),
    (16.0, 1500.0),
    (20.0, 1378.0),
    (24.0, 2000.0),
    (28.0, 1450.0),
    (28.0, 2500.0),
)
VERIFICATION_REL_TOL = 1e-9
VERIFICATION_ABS_TOL_VOLT = 1e-12

# --- quadrature for EVSI -----------------------------------------------------
Y_NODES = 241
Y_SPAN_SIGMAS = 7.0

# --- benchmark noise seed ----------------------------------------------------
#: The draw for a measurement depends on (action_id, repeat) and NOTHING else —
#: not on which control is running. Control A and the scored misspecified run
#: therefore see bit-identical noise and differ only through the hidden law.
NOISE_SEED = 20260821

# =====================================================================
# PREDICTIVE ADEQUACY RULE — preregistered, and not tuned afterwards
# =====================================================================

#: The per-condition statistic. Chosen because it is exact for a finite Gaussian
#: mixture (no sampling, no approximation), it is a probability rather than a
#: score, and it is computable from the frozen predictive artifact and the
#: observed scalar alone — nothing else can enter it.
SURPRISE_STATISTIC = "two_sided_posterior_predictive_tail_probability"
SECONDARY_STATISTIC = "prequential_negative_log_predictive_density"

#: A condition is EXTREME if its own frozen predictive gave the observed value
#: a two-sided tail below this.
ALPHA_EXTREME = 1e-4
#: ...and MODERATE below this. Reported, but never sufficient on its own.
ALPHA_MODERATE = 0.05

#: The strongest verdict needs at least this many individually extreme
#: conditions. K >= 2 is the structural reason one unlucky point cannot produce
#: MODEL_SPACE_INADEQUATE, whatever its aggregate contribution. Unaffected by
#: the v1.1.0 correction: it counts EXACTLY calibrated marginal tails.
K_MIN_EXTREME = 2

# --- the aggregate (v1.1.0) --------------------------------------------------
#: The complete challenge vector is scored ONCE, jointly, under the frozen
#: calibration posterior:
#:
#:     S = -log p(y_1..y_k | D, M_const)
#:       = -log SUM_theta p(theta|D) PROD_j p(y_j | theta, action_j)
#:
#: Exact on the finite grid. It handles the shared-theta dependence by
#: construction rather than by assuming it away: the assumed family is given
#: every chance to move theta within its own posterior before being scored.
AGGREGATE_STATISTIC = "joint_posterior_predictive_log_score"

#: Its null distribution is obtained by simulating complete vectors from the
#: same joint predictive — ONE theta per draw, shared across all conditions,
#: which is exactly the dependence a per-condition simulation would destroy.
#: The resulting p-value uses the (1 + #{S* >= S_obs}) / (1 + N) construction,
#: which is EXACTLY valid in finite samples for any N. That is a stronger
#: guarantee than the asymptotic chi-square approximation it replaces, not a
#: weaker one.
NULL_CALIBRATION = "posterior_predictive_simulation_under_M_const"
NULL_SIMULATION_DRAWS = 20000
NULL_SIMULATION_SEED = 20260822

#: With N = 20000 the smallest attainable p is 1/20001 = 5.0e-5, so this
#: threshold demands that AT MOST ONE of twenty thousand null draws be as
#: extreme as the observation. The value is set by the Monte Carlo resolution
#: that was preregistered with it, not by inspecting any result; the run also
#: reports the range of thresholds over which all three control verdicts are
#: unchanged, so the conclusion does not rest on this particular number.
ALPHA_JOINT = 1e-4
ALPHA_JOINT_WEAK = 1e-2

#: DEPRECATED — v1.0.0's aggregate, retained and reported ONLY as a diagnostic
#: so the size of the original error stays visible. Never load-bearing again.
DEPRECATED_FISHER_STATISTIC = "fisher_combined_tail_probability"
DEPRECATED_FISHER_REFERENCE = "chi_square_2N_assuming_independence"
DEPRECATED_ALPHA_AGGREGATE = 1e-6

#: Tail probabilities below this floor when logged, so an underflow to exactly
#: zero cannot make the deprecated Fisher statistic infinite.
LOG_TAIL_FLOOR = -700.0

ESCALATION_RULE = (
    "MODEL_SPACE_INADEQUATE  iff  n_extreme >= K_MIN_EXTREME AND "
    "p_joint < ALPHA_JOINT. "
    "MODEL_ADEQUACY_NOT_ESTABLISHED  iff  not the above AND "
    "(n_extreme >= 1 OR p_joint < ALPHA_JOINT_WEAK). "
    "MODEL_ADEQUACY_ACCEPTABLE  otherwise. "
    "The conjunction in the first clause is load-bearing and independent of "
    "the aggregate: no single condition, however extreme, can satisfy "
    "n_extreme >= 2, so a p_joint of exactly zero still cannot escalate one "
    "isolated surprise."
)

CERTIFICATION_RULE = (
    "SCIENTIFIC_CERTIFICATION = CERTIFIABLE only if execution validity is VALID "
    "AND the adequacy state is MODEL_ADEQUACY_ACCEPTABLE. Posterior sd, "
    "posterior entropy, P(decision), EVPI and EVSI are NOT inputs to this rule "
    "and are not parameters of the function that evaluates it."
)


def theta_grid() -> np.ndarray:
    return np.linspace(THETA_MIN_OHM, THETA_MAX_OHM, THETA_POINTS)


def indifference_probability() -> float:
    """P(above) at which decisions A and B carry equal expected loss."""
    return LOSS_A_BELOW / (LOSS_A_BELOW + LOSS_B_ABOVE)


def _action_payload(action: E2Action) -> dict[str, Any]:
    return {
        "action_id": action.action_id,
        "source_voltage_volt": action.source_voltage_volt,
        "noise_sigma_volt": action.noise_sigma_volt,
        "cost": action.cost,
        "phase": action.phase,
        "repeats": action.repeats,
    }


def config_payload() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": EXPERIMENT_VERSION,
        "base_commit": BASE_COMMIT,
        "e1_config_hash": E1_CONFIG_HASH,
        "circuit": {
            "topology": "two_resistor_voltage_divider",
            "r1_ohm": R1_OHM,
            "nodes": [NODE_IN, NODE_MID, NODE_REF],
            "reference": NODE_REF,
            "observed_metric": VMID_METRIC,
            "derived_from": "E1 (identical topology and known resistance)",
        },
        "assumed_model_family": {
            "family_id": ASSUMED_MODEL_FAMILY_ID,
            "statement": ASSUMED_MODEL_FAMILY,
            "parameter": "R2_ohm",
            "grid_min": THETA_MIN_OHM,
            "grid_max": THETA_MAX_OHM,
            "grid_points": THETA_POINTS,
            "grid_spacing_ohm": (THETA_MAX_OHM - THETA_MIN_OHM)
            / (THETA_POINTS - 1),
            "prior": PRIOR,
            "forward_model": "real ElectricalDCSolver via solve_circuit",
            "posterior_reading": "p(R2 | data, constant-R model)",
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
        "calibration_actions": [_action_payload(a) for a in CALIBRATION_ACTIONS],
        "challenge_actions": [_action_payload(a) for a in CHALLENGE_ACTIONS],
        "budget": {"total": TOTAL_BUDGET, "cost_unit": COST_UNIT},
        "verification": {
            "points": [list(p) for p in VERIFICATION_POINTS],
            "rel_tol": VERIFICATION_REL_TOL,
            "abs_tol_volt": VERIFICATION_ABS_TOL_VOLT,
        },
        "quadrature": {"y_nodes": Y_NODES, "y_span_sigmas": Y_SPAN_SIGMAS},
        "noise_seed": NOISE_SEED,
        "noise_derivation": "sha256(action_id|repeat) — control-independent",
        "predictive_adequacy": {
            "statistic": SURPRISE_STATISTIC,
            "secondary_statistic": SECONDARY_STATISTIC,
            "aggregate_statistic": AGGREGATE_STATISTIC,
            "aggregate_null_calibration": NULL_CALIBRATION,
            "aggregate_null_draws": NULL_SIMULATION_DRAWS,
            "aggregate_null_seed": NULL_SIMULATION_SEED,
            "alpha_extreme": ALPHA_EXTREME,
            "alpha_moderate": ALPHA_MODERATE,
            "alpha_joint": ALPHA_JOINT,
            "alpha_joint_weak": ALPHA_JOINT_WEAK,
            "k_min_extreme": K_MIN_EXTREME,
            "log_tail_floor": LOG_TAIL_FLOOR,
            "escalation_rule": ESCALATION_RULE,
            "independence_assumed": False,
            "dependence_statement": (
                "the challenge conditions are conditionally independent given "
                "theta and share ONE calibration posterior, so their marginal "
                "tail probabilities are positively dependent; the aggregate is "
                "computed jointly and calibrated by simulation rather than "
                "assuming independence"
            ),
            "deprecated_v1_0_0": {
                "statistic": DEPRECATED_FISHER_STATISTIC,
                "reference": DEPRECATED_FISHER_REFERENCE,
                "alpha": DEPRECATED_ALPHA_AGGREGATE,
                "status": "INVALID — reported as a diagnostic only",
            },
        },
        "correction_record": {
            "superseded_config_hash": SUPERSEDED_CONFIG_HASH,
            "statement": CORRECTION_RECORD,
        },
        "certification_rule": CERTIFICATION_RULE,
        "controls": {
            "A": "well-specified constant-R truth, same seeds and machinery",
            "B": "well-specified truth plus ONE preregistered isolated outlier",
            "C": "systematically misspecified truth (the scored run)",
            "D": "injected computational failure, routed through validity",
            "E": "sharp posterior under the misspecified truth must still be "
                 "refused certification",
        },
        "scope_statement": (
            "E2 is a computational Electrical DC benchmark. The hidden law is "
            "a synthetic grader-only misspecification, not a claim about any "
            "physical mechanism, and no hardware is involved."
        ),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
