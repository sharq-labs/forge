"""Electrical V0.1 demo scenario — declared once, hashed, and not tuned after.

THE SCIENTIFIC QUESTION
-----------------------
A two-resistor divider with a known 1000 ohm upper resistor and an unknown
lower one. The campaign must classify that unknown resistance against a
declared threshold, and it must not certify its answer until it has tested the
model it used to get there.

WHY THE PARAMETER INSTRUMENT IS PRECISE AND CHEAP
-------------------------------------------------
This is the one scenario choice worth explaining, because it is what makes the
demo show a whole lifecycle rather than a fragment.

The terminal decision — is R2 above 1200 ohm, when it is in fact near 1378 — is
easy. A single good measurement settles it, after which EVPI collapses and no
further parameter-learning action can be worth its price. That is the honest
behaviour of the frozen decision theory and the demo does not fight it.

So the parameter instrument is declared precise (sigma = 0.01 V) and cheap
(0.10). Precise, because the posterior it leaves behind is what the later
predictive checks are made against: a campaign that stopped learning while
still uncertain to +/- 60 ohm could not test its own model at all, and the demo
would have nothing to show. Cheap, because it must genuinely win on net value
against every validation probe at the prior — which it does, by 0.05 — so the
first action is bought for information and not by fiat.

The consequence is the state the whole V0.1 story is about: after ONE
economically justified purchase the parameter question is closed, every
remaining action is net-negative, and the only thing with anything left to say
is the certification requirement.

WHAT IS INHERITED AND NOT REDECLARED
------------------------------------
The circuit, the theta grid, the uniform prior, the 1200 ohm threshold, the
asymmetric 4:1 loss, the observation model, the noise derivation, the EVPI/EVSI
quadrature, the adequacy rule and both grader worlds all come from E2 v1.1.0
unchanged. This module declares only what a campaign has to declare for itself:
which instruments exist, what they cost, and what must be tested before the
answer counts.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from experiments.electrical_e2.e2_config import (
    E2Action,
    THETA_MAX_OHM,
    THETA_MIN_OHM,
    THETA_POINTS,
    THRESHOLD_OHM,
)
from experiments.electrical_e2.e2_config import config_hash as e2_config_hash
from experiments.electrical_e2.e2_truth import (
    MISSPEC_KAPPA,
    MISSPEC_LAW,
    MISSPEC_VREF_VOLT,
    TRUE_R0_OHM,
)

from . import BASE_COMMIT, DEMO_VERSION

DEMO_ID = "electrical_v01_demo"
CAMPAIGN_ID = "electrical-v01"
CHARTER_VERSION = "1"
DECISION_ID = "r2_class"
COST_UNIT = "hour"
MAX_ITERATIONS = 8

# --- inherited, pinned so a drift in E2 breaks the demo loudly ---------------
E2_CONFIG_HASH = (
    "d6add0d816563ea65f70473cf5cdc926dd7fa17ebff6769790879f8de057ab13"
)

# --- the instruments this campaign owns -------------------------------------
#: Parameter learning. Precise and cheap, for the reasons in the module
#: docstring. CHARACTERIZE, so it may draw only on the general pool.
PARAMETER_ACTION = E2Action(
    action_id="measure_vmid_10V_precise",
    source_voltage_volt=10.0,
    noise_sigma_volt=0.01,
    cost=0.10,
    phase="parameter",
    repeats=1,
    description=(
        "precise bench measurement of V_mid at the standard 10 V operating "
        "point; the economically best first action at the prior"
    ),
)

#: Validation probes at conditions the parameter measurement never visits.
#: VALIDATE, so the frozen BudgetLedger reservation applies to them.
PROBE_ACTIONS: tuple[E2Action, ...] = tuple(
    E2Action(
        action_id=f"validate_vmid_{volt:02d}V",
        source_voltage_volt=float(volt),
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="validation",
        repeats=1,
        description=description,
    )
    for volt, description in (
        (16, "low end of the declared operating range"),
        (20, "available, not required by the coverage rule"),
        (22, "middle of the declared operating range"),
        (24, "available, not required by the coverage rule"),
        (28, "high end of the declared operating range"),
    )
)

CANDIDATE_ACTIONS: tuple[E2Action, ...] = (PARAMETER_ACTION,) + PROBE_ACTIONS
ACTION_FAMILY_BY_PHASE = {"parameter": "characterize", "validation": "validate"}

# --- the certification requirement ------------------------------------------
REQUIREMENT_ID = "certification:constant_r:operating_range"
REQUIRED_ACTION_IDS: tuple[str, ...] = (
    "validate_vmid_16V",
    "validate_vmid_22V",
    "validate_vmid_28V",
)
REQUIREMENT_SOURCE = "electrical v0.1 demo charter"
COVERAGE_RULE = (
    "one required probe at the low, middle and high of the declared operating "
    "range, spanning the claim rather than hunting for a failure the decision "
    "path could not know about. Two further probes exist and are never bought, "
    "which is what makes the requirement finite"
)
DECLARED_SCOPE = "constant-R model for Vs in [10, 28] V on this divider"

# --- budget ------------------------------------------------------------------
TOTAL_BUDGET = 1.20
RESERVED_VALIDATION_BUDGET = 0.45      # exactly three probes at 0.15

# --- adequacy ----------------------------------------------------------------
STOPPING_CRITERION_ID = REQUIREMENT_ID
ADEQUACY_RULE = "e2.joint_posterior_predictive_log_score/1.1.0"

# --- determinism -------------------------------------------------------------
#: Every observation is a solver evaluation plus E2's frozen benchmark noise,
#: which is derived from (action_id, repeat) and nothing else. There is no RNG
#: state in the demo, so two runs produce identical scientific output.
NOISE_DERIVATION = "e2.benchmark_noise(action_id, repeat) — seed 20260821"
ADEQUACY_NULL_SEED = 20260822          # E2's frozen simulation seed

WORLDS = {
    "A": "well specified — the truth is a constant inside the assumed family",
    "B": "misspecified — E2's frozen synthetic condition-dependent law",
}


def config_payload() -> dict[str, Any]:
    return {
        "demo_id": DEMO_ID,
        "demo_version": DEMO_VERSION,
        "base_commit": BASE_COMMIT,
        "inherited_from_e2": {
            "config_hash": E2_CONFIG_HASH,
            "grid": {
                "min_ohm": THETA_MIN_OHM,
                "max_ohm": THETA_MAX_OHM,
                "points": THETA_POINTS,
            },
            "prior": "uniform over the frozen grid",
            "threshold_ohm": THRESHOLD_OHM,
            "loss": {"A_when_below": 4.0, "B_when_above": 1.0},
            "adequacy_rule": ADEQUACY_RULE,
            "adequacy_null_seed": ADEQUACY_NULL_SEED,
            "grader_law": MISSPEC_LAW,
            "grader_r0_ohm": TRUE_R0_OHM,
            "grader_kappa": MISSPEC_KAPPA,
            "grader_vref_volt": MISSPEC_VREF_VOLT,
        },
        "actions": [
            {
                "action_id": a.action_id,
                "source_voltage_volt": a.source_voltage_volt,
                "noise_sigma_volt": a.noise_sigma_volt,
                "cost": a.cost,
                "phase": a.phase,
                "action_family": ACTION_FAMILY_BY_PHASE[a.phase],
                "required_for_certification": (
                    a.action_id in REQUIRED_ACTION_IDS
                ),
            }
            for a in CANDIDATE_ACTIONS
        ],
        "certification_requirement": {
            "requirement_id": REQUIREMENT_ID,
            "required_action_ids": list(REQUIRED_ACTION_IDS),
            "source": REQUIREMENT_SOURCE,
            "coverage_rule": COVERAGE_RULE,
            "declared_scope": DECLARED_SCOPE,
        },
        "budget": {
            "total": TOTAL_BUDGET,
            "reserved_validation": RESERVED_VALIDATION_BUDGET,
            "cost_unit": COST_UNIT,
            "ledger": "frozen BudgetLedger; no demo-only budget logic",
        },
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "charter_version": CHARTER_VERSION,
            "decision_id": DECISION_ID,
            "max_iterations": MAX_ITERATIONS,
        },
        "noise_derivation": NOISE_DERIVATION,
        "worlds": WORLDS,
        "scope_statement": (
            "a computational Electrical DC benchmark. No physical claim, no "
            "hardware, and no validation against any real electrical system"
        ),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def scenario_hash() -> str:
    """The demo config bound to the E2 configuration it inherits."""
    blob = f"{config_hash()}|{e2_config_hash()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
