"""E3 preregistered configuration — decision-visible half.

Frozen BEFORE the first scored run. E3 inherits its entire scientific setup
from E2 v1.1.0 and adds one thing: a finite, preregistered obligation to test
the model before certifying it.

WHAT IS INHERITED, UNCHANGED
----------------------------
Circuit, real ``ElectricalDCSolver``, the constant-R assumed family, the theta
grid and prior, the posterior/predictive/EVPI/EVSI machinery, the synthetic
observation noise, the predictive-commitment ledger, and the corrected joint
posterior-predictive adequacy rule. E2's files are pinned by digest below and a
test recomputes them, so "E3 did not quietly edit E2" is checked, not asserted.

THE CALIBRATION STATE E3 STARTS FROM
------------------------------------
E3 reuses E2's calibration action id verbatim, so its four calibration draws
are bit-identical to E2's and the campaign begins from exactly the state E2
ended its Phase 1 in: posterior sd ~14.4 ohm, P(decision) = 1.0, EVPI ~1e-50.
That is the state in which parameter-learning EVSI has already collapsed, and
it is the state whose governance E3 is about.

THE ADEQUACY OBLIGATION
-----------------------
Declared in full below. The properties that matter:

**It is finite.** Three required conditions, chosen by a coverage rule, out of
a catalogue of five feasible ones. Once those three are acquired the obligation
is discharged and stops asking for anything. An obligation that could always
demand one more measurement would not be a scientific requirement; it would be
a refusal to ever finish.

**It is not evidence.** Declaring the obligation says nothing about whether the
model is adequate. Before the probes the adequacy status is NOT_ESTABLISHED —
not "provisionally fine", not "presumed adequate".

**Satisfying it is not passing it.** The obligation is discharged by obtaining
the required valid, predictively-committed evidence. What that evidence then
says about the model is a separate question with a separate answer.

WHY THE COVERAGE RULE IS WHAT IT IS
-----------------------------------
The required set spans the declared operating range — low, middle and high of
the extrapolation region above the calibration condition. That is chosen for
*coverage of the claim being made*, not for detection power: the campaign
claims the constant-R model over Vs in [4, 28] V, so the required evidence is
distributed across the range it claims. Choosing the conditions where a
particular misspecification would show up most is not available to the decision
path, which does not know what the misspecification is, and would not be a
defensible general rule if it were.

WHAT THE SELECTION RULE IS NOT
------------------------------
Probe order is decided by a transparent constraint rule — cheapest outstanding
required probe, ties broken by the frozen declared order — and NOT by ranking
candidates on expected information value. Parameter EVSI is reported for every
probe and is at the floor for all of them; that number is what makes the
separation visible, so it is neither hidden nor adjusted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from experiments.electrical_e2.e2_config import (
    E2Action,
    THRESHOLD_OHM,
    THETA_MAX_OHM,
    THETA_MIN_OHM,
    THETA_POINTS,
)
from experiments.electrical_e2.e2_config import config_hash as e2_config_hash

EXPERIMENT_ID = "E3"
EXPERIMENT_NAME = "adequacy_evidence_vs_parameter_evsi"
EXPERIMENT_VERSION = "1.0.0"

#: The E2 final freeze E3 is built on (E2 v1.1.0 plus its metadata hotfix).
BASE_COMMIT = "619d3cc04d5cbed501670718f7ea814ddadf7cc0"
E2_EXPERIMENT_VERSION = "1.1.0"
E2_CONFIG_HASH = (
    "d6add0d816563ea65f70473cf5cdc926dd7fa17ebff6769790879f8de057ab13"
)
E2_PREREGISTRATION_HASH = (
    "6b93e70dac164f286170b3218943062602d47013bbdb83092a102e46a496b216"
)
#: Newline-normalized SHA-256 of every E2 file, recomputed by test.
E2_FROZEN_FILE_DIGESTS: dict[str, str] = {
    "experiments/electrical_e2/__init__.py":
        "d35f2e7cf4ab4dd9251f57ba5038f5237b239b9892fe6c9f9f8aacf66d8ae80c",
    "experiments/electrical_e2/e2_config.py":
        "7e3ad55b7c77584aade036e1d3786d99136d139558e29f2c00ff55163409f033",
    "experiments/electrical_e2/e2_model.py":
        "5984ca1dd9b290eb016c6d1dd88315713125cfd78504b493af7aba44df92697c",
    "experiments/electrical_e2/e2_adequacy.py":
        "94f14191ea669d627068b3ec2bbeba524b8cf1d854627b4182d811ee9d7f5627",
    "experiments/electrical_e2/e2_truth.py":
        "6d39b99db4c23321743e49384b7d677a2f43781e0740a7870169ce18cece8410",
    "experiments/electrical_e2/e2_harness.py":
        "eeb7ef9e4de506373babdf2d19277e0e2d19616743ee34bd972adbca0121dfff",
    "experiments/electrical_e2/e2_run.py":
        "c5f888d1e313ccffa09bf1ae8d703312c01727f24a1a0d127f0fa902b198dcde",
    "experiments/electrical_e2/e2_config_frozen.json":
        "bafe9cd708235b0a59e02fe84c49383c9b2e803a825caa0b34be1098a8997017",
    "experiments/electrical_e2/e2_results.json":
        "b9e4c4186897bf159a68f0c064c57176f6d3911dc22edf635369487574de3394",
    "experiments/electrical_e2/e2_report.md":
        "a17bd633a78efcc6922f44a5787b534b68a2fc6603520e4324517de3ef63eeea",
    "tests/test_sria_e2_model_adequacy.py":
        "06d3b56515500aa246dbb4f252b2e18ca3f0ec7a09ed803911c93dfcac410496",
}

# --- campaign identity -------------------------------------------------------
CAMPAIGN_ID = "e3-electrical"
CHARTER_VERSION = "1"
DECISION_ID = "r2_class"
COST_UNIT = "hour"
MAX_ITERATIONS = 3

# --- the calibration state the campaign starts from --------------------------
#: E2's calibration action, reused verbatim so the draws are bit-identical.
CALIBRATION_ACTION_ID = "calibrate_vmid_10V"
CALIBRATION_VOLTAGE = 10.0
CALIBRATION_SIGMA = 0.05
CALIBRATION_COST = 0.15
CALIBRATION_REPEATS = 4

CALIBRATION_ACTION = E2Action(
    action_id=CALIBRATION_ACTION_ID,
    source_voltage_volt=CALIBRATION_VOLTAGE,
    noise_sigma_volt=CALIBRATION_SIGMA,
    cost=CALIBRATION_COST,
    phase="calibration",
    repeats=CALIBRATION_REPEATS,
    description="E2's calibration action, reused verbatim",
)

# --- candidate actions the campaign scores -----------------------------------
#: A parameter-learning action: one more measurement at the already-calibrated
#: condition. Its EVSI after calibration is at the floor, which is correct and
#: is left alone.
PARAMETER_ACTIONS: tuple[E2Action, ...] = (
    E2Action(
        action_id="parameter_repeat_10V",
        source_voltage_volt=10.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="parameter",
        repeats=1,
        description=(
            "one more measurement at the calibration condition; a genuine "
            "parameter-learning action whose information value has collapsed"
        ),
    ),
)

#: The feasible adequacy-probe catalogue. Every one of these is ALSO scored by
#: the utility engine alongside the parameter action, at the same price, so the
#: EVSI-only policy sees them and declines them on the merits. Two of the five
#: are deliberately NOT required, so the obligation demonstrably stops asking.
PROBE_CATALOGUE: tuple[E2Action, ...] = (
    E2Action(
        action_id="adequacy_probe_16V",
        source_voltage_volt=16.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="adequacy_probe",
        repeats=1,
        description="low end of the declared extrapolation range",
    ),
    E2Action(
        action_id="adequacy_probe_20V",
        source_voltage_volt=20.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="adequacy_probe",
        repeats=1,
        description="feasible but NOT required by the coverage rule",
    ),
    E2Action(
        action_id="adequacy_probe_22V",
        source_voltage_volt=22.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="adequacy_probe",
        repeats=1,
        description="middle of the declared extrapolation range",
    ),
    E2Action(
        action_id="adequacy_probe_24V",
        source_voltage_volt=24.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="adequacy_probe",
        repeats=1,
        description="feasible but NOT required by the coverage rule",
    ),
    E2Action(
        action_id="adequacy_probe_28V",
        source_voltage_volt=28.0,
        noise_sigma_volt=0.05,
        cost=0.15,
        phase="adequacy_probe",
        repeats=1,
        description="high end of the declared extrapolation range",
    ),
)

CANDIDATE_ACTIONS: tuple[E2Action, ...] = PARAMETER_ACTIONS + PROBE_CATALOGUE

# =====================================================================
# THE ADEQUACY OBLIGATION
# =====================================================================

@dataclass(frozen=True)
class AdequacyObligation:
    """One finite, preregistered scientific requirement.

    Every field below is part of the config hash. In particular the required
    conditions and the maximum budget are frozen, so the obligation cannot
    grow after the run starts.
    """

    obligation_id: str
    model_family_id: str
    model_family_version: str
    declared_scope: str
    scope_min_volt: float
    scope_max_volt: float
    required_action_ids: tuple[str, ...]
    coverage_rule: str
    selection_rule: str
    predictive_commitment_required: bool
    adequacy_rule_id: str
    adequacy_rule_version: str
    satisfaction_condition: str
    failure_condition: str
    max_adequacy_cost: float
    disposition_satisfied: str
    disposition_inadequate: str
    disposition_budget_infeasible: str
    disposition_execution_invalid: str
    source: str

    @property
    def n_required(self) -> int:
        return len(self.required_action_ids)

    def payload(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "model_family": {
                "id": self.model_family_id,
                "version": self.model_family_version,
            },
            "declared_scope": self.declared_scope,
            "scope_volt": [self.scope_min_volt, self.scope_max_volt],
            "required_action_ids": list(self.required_action_ids),
            "n_required": self.n_required,
            "coverage_rule": self.coverage_rule,
            "selection_rule": self.selection_rule,
            "predictive_commitment_required": self.predictive_commitment_required,
            "adequacy_rule": {
                "id": self.adequacy_rule_id,
                "version": self.adequacy_rule_version,
            },
            "satisfaction_condition": self.satisfaction_condition,
            "failure_condition": self.failure_condition,
            "max_adequacy_cost": self.max_adequacy_cost,
            "dispositions": {
                "satisfied": self.disposition_satisfied,
                "model_inadequate": self.disposition_inadequate,
                "budget_infeasible": self.disposition_budget_infeasible,
                "execution_invalid": self.disposition_execution_invalid,
            },
            "source": self.source,
        }


ADEQUACY_OBLIGATION = AdequacyObligation(
    obligation_id="adequacy:constant_r:declared_range",
    model_family_id="constant_r",
    model_family_version=E2_EXPERIMENT_VERSION,
    declared_scope="constant-R model for Vs in [4, 28] V on the E2 divider",
    scope_min_volt=4.0,
    scope_max_volt=28.0,
    #: Three conditions spanning the extrapolation region, in declared order.
    required_action_ids=(
        "adequacy_probe_16V",
        "adequacy_probe_22V",
        "adequacy_probe_28V",
    ),
    coverage_rule=(
        "one required probe at the low, middle and high of the declared "
        "extrapolation range above the calibration condition; chosen to cover "
        "the range the campaign claims, NOT to maximise detection power, which "
        "the decision path could not do without knowing the misspecification"
    ),
    selection_rule=(
        "execute the cheapest OUTSTANDING REQUIRED probe first, ties broken by "
        "the frozen declared order. This is a constraint-satisfaction rule over "
        "a fixed required set and is deliberately NOT a ranking by expected "
        "information value"
    ),
    predictive_commitment_required=True,
    adequacy_rule_id="e2.joint_posterior_predictive_log_score",
    adequacy_rule_version=E2_EXPERIMENT_VERSION,
    satisfaction_condition=(
        "every required probe has been executed with a VALID computational "
        "result, admitted through the M1 evidence chain, and scored against a "
        "predictive commitment that existed before its observation. Satisfying "
        "this says the required TEST WAS PERFORMED; it says nothing whatever "
        "about whether the model passed it"
    ),
    failure_condition=(
        "a required probe cannot be executed validly, or cannot be afforded "
        "within max_adequacy_cost. Neither is a model-adequacy finding"
    ),
    max_adequacy_cost=0.45,          # exactly three probes at 0.15
    disposition_satisfied="CERTIFICATION_ELIGIBLE_IF_ADEQUACY_ACCEPTABLE",
    disposition_inadequate="MODEL_REVISION_REQUIRED",
    disposition_budget_infeasible="CERTIFICATION_NOT_POSSIBLE",
    disposition_execution_invalid="EXECUTION_REPAIR_REQUIRED",
    source="e3 preregistered charter",
)

# --- the stopping criterion that carries the obligation ----------------------
STOPPING_CRITERION_ID = ADEQUACY_OBLIGATION.obligation_id
STOPPING_CRITERION_STATEMENT = (
    "the campaign may stop only when the declared model-adequacy obligation "
    "has been discharged by acquiring its required evidence AND that evidence "
    "left the model family adequate for the declared scope"
)
STOPPING_EVALUATOR_ID = "e3.adequacy_obligation"
STOPPING_EVALUATOR_VERSION = "1"

# =====================================================================
# BUDGET POLICIES
# =====================================================================

BUDGET_POLICY_SHARED = "shared_pool"
BUDGET_POLICY_RESERVED = "reserved_adequacy_allocation"

#: Total campaign budget in declared cost units. Sized so the comparison
#: between the two policies is observable rather than hypothetical.
TOTAL_BUDGET = 1.20
#: Under the reserved policy, this much is carved out up front. E3 does NOT
#: implement the fencing: the frozen ``BudgetLedger`` already does it, via
#: ``reserved_validation_budget`` and ``affordable(cost, family=...)``, which
#: lets only ActionFamily.VALIDATE draw on the reservation. The adequacy probes
#: are declared VALIDATE — which is what they are — so the protection E3 is
#: asking about is the repository's existing mechanism, exercised, not a new one.
ADEQUACY_RESERVE = 0.45
#: Preregistered parameter-learning spend used ONLY in the budget comparison
#: control, to represent a campaign that spent its pool before the obligation
#: came due. Not part of the two scored worlds.
CONTROL_PARAMETER_SPEND = 0.90

BUDGET_POLICY_STATEMENT = (
    "E3 does not claim a reserved validation budget is universally correct. It "
    "tests one narrow question: whether mandatory certification evidence can be "
    "protected from being consumed by parameter-learning actions. Both policies "
    "are run on the same scientific state and reported descriptively"
)

# --- how each candidate is declared to the frozen budget/liveness machinery --
#: Parameter-learning actions are CHARACTERIZE and may draw only on the general
#: pool. Adequacy probes are VALIDATE, which is both semantically correct and
#: what makes the frozen reservation apply to them.
ACTION_FAMILY_BY_PHASE = {
    "calibration": "characterize",
    "parameter": "characterize",
    "adequacy_probe": "validate",
}

# --- where the adequacy obligation lives, and where it deliberately does not -
OBLIGATION_PLACEMENT_STATEMENT = (
    "The adequacy obligation is carried by a registered StoppingCriterion with "
    "a real evaluator, NOT by the campaign ObligationSet. ObligationSet is "
    "evaluated by the Arbiter against the critic assessments of ONE evidence "
    "record, so a campaign-scoped scientific requirement placed there is looked "
    "for among that record's checks, never found, and makes every piece of "
    "evidence INCONCLUSIVE — blocking all admission. E3 demonstrates that "
    "failure mode in a test rather than asserting it. It is also the reason the "
    "frozen validation-liveness router cannot see this obligation: the router "
    "reads unsatisfied obligations from ObligationSet, which is welded to "
    "per-evidence admission"
)

#: M5.1 recorded that charter confidence requirements become REQUIRED_CHECK
#: obligations targeting ``validation_level:*``, which M3 records for
#: provenance and explicitly cannot evaluate — they fail closed forever. E3
#: does not use that vocabulary, and a test asserts it appears nowhere in the
#: E3 decision path: a governance result built on an obligation that can never
#: be satisfied would be an artifact of the bug, not a demonstration.
FORBIDDEN_OBLIGATION_VOCABULARY = "validation_level:"

# =====================================================================
# CERTIFICATION RULE
# =====================================================================

CERTIFICATION_RULE = (
    "SCIENTIFIC_CERTIFICATION = ELIGIBLE only if execution validity is VALID "
    "AND the adequacy obligation status is COMPLETED AND the adequacy state is "
    "ACCEPTABLE_FOR_DECLARED_SCOPE. Posterior sd, posterior entropy, "
    "P(decision), EVPI and EVSI are NOT inputs to this rule and are not "
    "parameters of the function that evaluates it. Neither is the fact that a "
    "stop was proposed economically"
)

STOPPING_SEMANTICS = (
    "ECONOMIC STOP PROPOSAL means no evaluated candidate scored above its "
    "price. SCIENTIFIC STOP APPROVAL means a registered stopping criterion was "
    "evaluated and the Arbiter found it satisfied. NO_ACTION_WORTH_BUYING does "
    "NOT imply STOP_APPROVED while a mandatory adequacy obligation is "
    "outstanding, and the frozen M5.1 StopReview refuses to represent that "
    "combination at all"
)

# --- worlds and controls -----------------------------------------------------
WORLDS = {
    "A": "well-specified truth, inside the assumed constant-R family",
    "B": "E2's frozen synthetic misspecification, outside the family",
}
CONTROLS = {
    "1": "no adequacy obligation registered — ordinary EVSI policy",
    "2": "obligation outstanding and affordable — probe must be routed",
    "3": "obligation already satisfied — must not force duplicate probes",
    "4": "obligation required but budget infeasible — no fake PASS",
    "5": "required probe fails computational validity — no adequacy judgment",
    "6": "valid evidence acquired, test completed, model fails",
}


def config_payload() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": EXPERIMENT_VERSION,
        "base_commit": BASE_COMMIT,
        "e2_dependency": {
            "experiment_version": E2_EXPERIMENT_VERSION,
            "config_hash": E2_CONFIG_HASH,
            "preregistration_hash": E2_PREREGISTRATION_HASH,
            "inherited": [
                "circuit and real ElectricalDCSolver forward map",
                "constant-R assumed model family, theta grid and prior",
                "posterior / predictive / EVPI / EVSI machinery",
                "synthetic observation noise and its derivation",
                "predictive commitment ledger",
                "corrected joint posterior-predictive adequacy rule (v1.1.0)",
                "well-specified and misspecified grader worlds",
            ],
        },
        "assumed_model_family": {
            "family_id": "constant_r",
            "parameter": "R2_ohm",
            "grid_min": THETA_MIN_OHM,
            "grid_max": THETA_MAX_OHM,
            "grid_points": THETA_POINTS,
            "posterior_reading": "p(R2 | data, constant-R model)",
        },
        "terminal_decision": {
            "decision_id": DECISION_ID,
            "threshold_ohm": THRESHOLD_OHM,
        },
        "calibration_state": {
            "action_id": CALIBRATION_ACTION_ID,
            "source_voltage_volt": CALIBRATION_VOLTAGE,
            "noise_sigma_volt": CALIBRATION_SIGMA,
            "repeats": CALIBRATION_REPEATS,
            "note": "identical to E2 Phase 1; draws are bit-identical",
        },
        "parameter_actions": [
            {
                "action_id": a.action_id,
                "source_voltage_volt": a.source_voltage_volt,
                "cost": a.cost,
            }
            for a in PARAMETER_ACTIONS
        ],
        "probe_catalogue": [
            {
                "action_id": a.action_id,
                "source_voltage_volt": a.source_voltage_volt,
                "cost": a.cost,
                "required": a.action_id in ADEQUACY_OBLIGATION.required_action_ids,
                "action_family": ACTION_FAMILY_BY_PHASE[a.phase],
            }
            for a in PROBE_CATALOGUE
        ],
        "action_families": ACTION_FAMILY_BY_PHASE,
        "obligation_placement": OBLIGATION_PLACEMENT_STATEMENT,
        "forbidden_obligation_vocabulary": FORBIDDEN_OBLIGATION_VOCABULARY,
        "adequacy_obligation": ADEQUACY_OBLIGATION.payload(),
        "stopping_criterion": {
            "criterion_id": STOPPING_CRITERION_ID,
            "statement": STOPPING_CRITERION_STATEMENT,
            "evaluator_id": STOPPING_EVALUATOR_ID,
            "evaluator_version": STOPPING_EVALUATOR_VERSION,
        },
        "stopping_semantics": STOPPING_SEMANTICS,
        "budget": {
            "total": TOTAL_BUDGET,
            "cost_unit": COST_UNIT,
            "policies": [BUDGET_POLICY_SHARED, BUDGET_POLICY_RESERVED],
            "adequacy_reserve": ADEQUACY_RESERVE,
            "control_parameter_spend": CONTROL_PARAMETER_SPEND,
            "statement": BUDGET_POLICY_STATEMENT,
        },
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "charter_version": CHARTER_VERSION,
            "max_iterations": MAX_ITERATIONS,
        },
        "certification_rule": CERTIFICATION_RULE,
        "worlds": WORLDS,
        "controls": CONTROLS,
        "no_fake_utility_statement": (
            "parameter EVSI for every action, including the adequacy probes, is "
            "computed by E2's unmodified quadrature and reported as it comes "
            "out. No adequacy utility, validation reward, critic-confidence "
            "term or obligation priority enters the decision basis"
        ),
        "scope_statement": (
            "E3 is a computational Electrical DC campaign-governance benchmark. "
            "It says nothing about optimal validation budgeting, universal "
            "value of validation, or real-domain regulatory readiness"
        ),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def preregistration_hash() -> str:
    """SHA-256 over the E3 config AND the E2 preregistration it inherits."""
    blob = f"{config_hash()}|{E2_PREREGISTRATION_HASH}|{e2_config_hash()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
