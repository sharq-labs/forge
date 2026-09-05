"""T3 preregistered configuration — decision-visible half.

Frozen BEFORE the scored run. Everything below is fixed and is not adjusted
after seeing T3 outcomes.

THE DECISION
------------
Calibrate alpha on the observation at 60 s, exactly as in T1 and T2. Then
decide a question about the slab at 180 s -- a condition that is never
assimilated:

    is the normalized midpoint temperature at 180 s below the threshold tau?

The terminal quantity is deliberately NOT the assimilated one. See the package
docstring for why: at the assimilated condition the discretization error is
exactly an effective-alpha shift and fitting alpha cancels it, so a decision
built there is one the numerics cannot lose.

THE BENCHMARK IS NOT RIGGED TOWARD THE REFERENCE RUNG
------------------------------------------------------
Scenarios are drawn in four preregistered margin bands, sized against the
MEASURED terminal error of each rung and against the statistical floor:

    coarse    1.66e-02      medium    1.59e-03
    reference 3.59e-04      statistical (posterior-predictive sd) 3.61e-04

    FAR          margin >> coarse error          -> coarse suffices
    MODERATE     between coarse and medium       -> medium suffices
    NEAR         between medium and reference    -> reference needed
    UNDECIDABLE  below the statistical floor     -> NO fidelity can decide it,
                 and paying for refinement is pure waste

The last band exists so that "always escalate" is a losing strategy somewhere.
Without it the benchmark would answer its own question.

WHAT THE POLICY MAY AND MAY NOT KNOW
--------------------------------------
The policy sees only what a real one could: its own posterior at each rung it
has paid for, and the difference between successive rungs. It does not see
alpha_true, tau's relationship to the truth, or any rung it has not run. The
successive-difference indicator is a CONSERVATIVE estimate of the finer rung's
error -- measured at 5-10x too large on the probe -- and no order-of-accuracy
correction is applied, because the frozen thermal gate deliberately refuses to
separate spatial from temporal order. The consequence is declared here in
advance: the policy will over-escalate in the MODERATE band, and the cost of
that conservatism is measured rather than removed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from experiments.thermal_t1.t1_config import (
    ALPHA_UNIT,
    CREDIBLE_MASS,
    END_TIME_S,
    FIELD_UNIT,
    LENGTH_M,
    OBSERVATION_COUNT,
    OBSERVATION_METRIC,
    OBSERVATION_SIGMA,
    REFERENCE_RUNG_ID,
    RUNGS,
    alpha_grid,
    rung,
)
from experiments.thermal_t1.t1_config import config_hash as t1_config_hash
from experiments.thermal_t2.t2_config import config_hash as t2_config_hash

from . import BASE_COMMIT, T3_VERSION

EXPERIMENT_ID = "T3"
EXPERIMENT_NAME = "decision_aware_fidelity_escalation"

__all__ = [
    "ALPHA_UNIT", "CREDIBLE_MASS", "END_TIME_S", "FIELD_UNIT", "LENGTH_M",
    "OBSERVATION_COUNT", "OBSERVATION_METRIC", "OBSERVATION_SIGMA",
    "REFERENCE_RUNG_ID", "RUNGS", "alpha_grid", "rung",
]

# =====================================================================
# 1. Terminal QoI and decision threshold
# =====================================================================

#: The unassimilated condition. r = TERMINAL_TIME_S / END_TIME_S = 3.
TERMINAL_TIME_S = 180.0
FOURIER_RATIO = TERMINAL_TIME_S / END_TIME_S

TERMINAL_METRIC = "u:midpoint@180s"
TERMINAL_QOI_DESCRIPTION = (
    "normalized dimensionless midpoint temperature of the same slab at 180 s. "
    "Never assimilated. u is a normalized field value and is not a temperature "
    "in kelvin"
)

#: The decision. tau varies per scenario; the rule does not.
DECISION_ID = "terminal_below_threshold"
DECISION_DESCRIPTION = (
    "decide TRUE when the terminal QoI is below tau, FALSE otherwise. The "
    "decision is made from the posterior-predictive mean of the terminal QoI "
    "at whichever rung the strategy stopped on"
)

#: No asymmetric loss. Both error directions cost the same, declared rather
#: than assumed: nothing in this benchmark makes a false-below worse than a
#: false-above, and inventing an asymmetry would be a free parameter.
ASYMMETRIC_LOSS = False
LOSS_MODEL = "0/1 loss on the terminal decision, symmetric"

# =====================================================================
# 2. Scenario generation
# =====================================================================

#: Per-scenario alpha, drawn well inside the frozen grid so no posterior is
#: ever truncated at an edge.
ALPHA_TRUE_MIN = 1.18e-5
ALPHA_TRUE_MAX = 1.22e-5

#: |terminal_truth - tau|, by band. Sized against the measured error scales in
#: the module docstring. Bounds are absolute in normalized field units.
MARGIN_BANDS: dict[str, tuple[float, float]] = {
    "FAR": (4.0e-2, 8.0e-2),
    "MODERATE": (4.0e-3, 1.5e-2),
    "NEAR": (8.0e-4, 3.0e-3),
    "UNDECIDABLE": (0.0, 4.0e-4),
}

#: Which rung the band was constructed to make sufficient. Recorded so the
#: benchmark's intent is checkable rather than asserted.
BAND_INTENT = {
    "FAR": "coarse",
    "MODERATE": "medium",
    "NEAR": "reference",
    "UNDECIDABLE": None,
}

SCENARIOS_PER_BAND = 250
SCENARIO_COUNT = SCENARIOS_PER_BAND * len(MARGIN_BANDS)

#: Disjoint from T1 (20260907) and T2 (20260908).
SEED_ENTROPY = 20260909

SCENARIO_RULE = (
    "scenario i belongs to band i // SCENARIOS_PER_BAND. Its stream is "
    "numpy.random.SeedSequence(SEED_ENTROPY).spawn(SCENARIO_COUNT)[i], and it "
    "draws, in this fixed order: alpha_true ~ U(ALPHA_TRUE_MIN, "
    "ALPHA_TRUE_MAX); margin ~ U(band_low, band_high); sign ~ {-1,+1} with "
    "equal probability; then OBSERVATION_COUNT normal deviates of sd "
    "OBSERVATION_SIGMA about the exact QoI at 60 s. The threshold is "
    "tau = terminal_truth + sign * margin, so the correct decision is exactly "
    "(sign > 0) and the two decisions are balanced by construction"
)

# =====================================================================
# 3. Fidelity costs — from the frozen measured ladder
# =====================================================================

#: Cost of USING a rung on one scenario, in work-proxy units taken unchanged
#: from the frozen ladder (n_cells * n_steps). Deterministic and machine
#: independent; wall-seconds are recorded only as telemetry.
FIDELITY_COST = {spec.rung_id: spec.work_proxy for spec in RUNGS}

#: A strategy pays for every rung it runs, including the ones it escalated
#: past. Escalation is not free.
COST_MODEL = (
    "a strategy pays the sum of FIDELITY_COST over every rung it ran. The "
    "escalating policy therefore pays 80, 5,200 or 332,880; Always Reference "
    "pays 327,680 unconditionally"
)

#: Cost of a wrong terminal decision, in the same work-proxy units.
#:
#: Anchored a priori at ten times the most expensive available computation.
#: The reasoning, stated before any result: if a decision error cost less than
#: the reference rung, no one would ever run the reference rung and the whole
#: fidelity question would be vacuous; if it cost vastly more, everyone would
#: always run it and the question would be equally vacuous. An order of
#: magnitude above the top rung is where the trade-off is live.
#:
#: This choice selects the REGIME, and it is declared as such. It is not
#: fitted to any strategy's outcome, and the full sweep below reports what
#: happens everywhere else -- including the regions where a fixed baseline
#: wins, which is an expected and reportable outcome, not a failure.
WRONG_DECISION_COST = 10 * FIDELITY_COST[REFERENCE_RUNG_ID]

WRONG_DECISION_COST_SWEEP = (
    1.0e4, 3.0e4, 1.0e5, 3.0e5, 1.0e6, 3.0e6, 1.0e7, 3.0e7, 1.0e8,
)

# =====================================================================
# 4. The escalation rule and the stopping rule
# =====================================================================

#: Safety factor on the combined uncertainty. Fixed at 1.0: no free knob.
ESCALATION_SAFETY_FACTOR = 1.0
#: Two-sided normal quantile at CREDIBLE_MASS.
ESCALATION_QUANTILE = 1.959963984540054

ESCALATION_RULE = (
    "start at the cheapest rung. At rung k compute the posterior over alpha "
    "from the scenario's observations using rung k's ASSIMILATION map, "
    "propagate it through rung k's TERMINAL map to a predictive mean mu_k and "
    "sd s_k, and let d_k = |mu_k - tau|. The numerical-error indicator is "
    "e_k = |mu_k - mu_{k-1}| for k >= 1 and infinity for k = 0, because a "
    "single rung supplies no evidence at all about its own numerical error -- "
    "which is precisely what T1 and T2 established. "
    "DECIDE if d_k > SAFETY * (QUANTILE * s_k + e_k); otherwise ESCALATE"
)

STOPPING_RULE = (
    "stop escalating, and decide, when any of: (1) the margin is robust to "
    "both statistical and numerical uncertainty, d_k > SAFETY * (QUANTILE * "
    "s_k + e_k); (2) the margin is inside the statistical uncertainty alone, "
    "d_k <= SAFETY * QUANTILE * s_k, because refinement reduces e_k and never "
    "s_k, so no amount of fidelity can settle this decision and paying for it "
    "is waste; (3) the finest rung has been reached, in which case the "
    "decision is taken and recorded as uncertified"
)

#: Names for how a decision terminated, recorded per scenario.
TERMINATION_ROBUST = "robust"
TERMINATION_STATISTICALLY_UNDECIDABLE = "statistically_undecidable"
TERMINATION_EXHAUSTED = "exhausted"

# =====================================================================
# 5. Baselines
# =====================================================================

BASELINES = ("always_coarse", "always_medium", "always_reference")
POLICY_ID = "decision_aware"
STRATEGIES = BASELINES + (POLICY_ID,)

BASELINE_RULE = (
    "each fixed baseline runs exactly one rung, forms the same posterior and "
    "the same predictive mean, and decides mu < tau. It never escalates and "
    "pays that rung's cost on every scenario"
)

# =====================================================================
# 6. Metrics
# =====================================================================

PRIMARY_METRIC = "cost_to_correct_decision"
PRIMARY_METRIC_DEFINITION = (
    "(total work + WRONG_DECISION_COST * number of wrong decisions) / number "
    "of correct decisions. Lower is better. Both terms are in work-proxy "
    "units, which is what makes them addable"
)

METRICS = (
    "cost_to_correct_decision",
    "terminal_decision_accuracy",
    "incorrect_confident_decisions",
    "total_work",
    "escalations",
    "unnecessary_escalations",
    "required_escalations_missed",
    "final_fidelity_distribution",
    "decision_regret",
    "numerical_error_over_decision_margin",
)

#: A decision is CONFIDENT when its strategy claimed the margin exceeded the
#: uncertainty it could see. For the policy that is termination reason
#: "robust"; for a fixed baseline, which has no numerical-error estimate, it is
#: d > SAFETY * QUANTILE * s. An incorrect confident decision is the failure
#: T1 and T2 exposed, now carried through to an actual decision.
CONFIDENT_DECISION_DEFINITION = (
    "policy: terminated as robust. baseline: d > SAFETY * QUANTILE * s"
)

UNNECESSARY_ESCALATION_DEFINITION = (
    "an escalation after which the final decision is identical to the one the "
    "pre-escalation rung would have made, and that decision is correct. The "
    "price of not knowing, measurable only in hindsight"
)

REQUIRED_ESCALATION_MISSED_DEFINITION = (
    "the strategy's decision is wrong, and a higher rung it did not run would "
    "have decided correctly"
)

# =====================================================================
# 7. Acceptance and falsification criteria
# =====================================================================

ACCEPTANCE_CRITERIA = (
    "A1 at the nominal WRONG_DECISION_COST the decision-aware policy has a "
    "strictly lower cost-to-correct-decision than all three fixed baselines",
    "A2 policy terminal accuracy is within 2 percentage points of Always "
    "Reference, so any cost saving was not bought with reliability",
    "A3 policy total work is strictly below Always Reference total work",
    "A4 in the FAR band the policy reaches the reference rung on fewer than "
    "10% of scenarios",
    "A5 in the NEAR band the policy reaches the reference rung on more than "
    "80% of scenarios",
    "A6 the benchmark contains both regimes: the coarse rung's terminal "
    "numerical error exceeds the decision margin on more than 50% of NEAR "
    "scenarios and on fewer than 5% of FAR scenarios",
    "A7 Always Reference is NOT the accuracy-per-work winner in every band -- "
    "there is at least one band where a cheaper fixed baseline matches its "
    "accuracy, confirming the benchmark is not rigged toward refinement",
)

FALSIFICATION_CRITERIA = (
    "F1 if the policy fails A1, that is recorded as a negative result. The "
    "safety factor, the bands, the costs, the nominal wrong-decision cost and "
    "the scenario rule are NOT adjusted afterwards",
    "F2 if A6 fails, the benchmark does not contain both regimes and no "
    "comparison between strategies is informative, whoever wins",
    "F3 if Always Reference dominates every band, the benchmark is rigged "
    "toward refinement and must be reported as such rather than as a result",
    "F4 if the policy's accuracy is materially below Always Reference, a lower "
    "cost-to-correct-decision must NOT be reported as success: the saving was "
    "bought with reliability",
    "F5 if the terminal QoI turns out to cancel the bias the way the "
    "assimilated one does -- that is, if the rungs' terminal predictions agree "
    "closely -- the out-of-sample design failed and T3 answers nothing",
)

EXPECTED_NEGATIVE_REGIME = (
    "below a crossover in WRONG_DECISION_COST the cheap fixed baselines are "
    "expected to win outright, because at that point a wrong decision is worth "
    "less than the computation that would prevent it. The crossover is "
    "predicted before execution to fall in the region of 5-10x the reference "
    "rung's cost. This is reported as a measured property of the trade-off, "
    "not as a failure of the policy"
)

NO_TUNING_AFTER_RESULTS = (
    "the terminal condition, threshold rule, margin bands, scenario count, "
    "seed rule, costs, safety factor, escalation rule, stopping rule, "
    "baselines and criteria above are fixed before execution and are not "
    "adjusted afterwards"
)

SCIENTIFIC_QUESTION = (
    "Can a cost-aware decision rule determine when the current numerical "
    "fidelity is sufficient for a downstream scientific decision, and when "
    "paying for higher fidelity is necessary?"
)

NON_GOALS = (
    "no generic FidelityPolicy and no new SRIA module — the escalation logic "
    "is experiment-side",
    "no commitment promotion, no ObligationSet redesign, no certification "
    "change, no new EVSI machinery",
    "no production SRIA change of any kind",
    "no physical validation; the hidden truth is synthetic and known",
    "no modification to T1 or T2, which are pinned by digest and used only as "
    "frozen prior calibration evidence",
)

# =====================================================================
# Pins
# =====================================================================

T2_FROZEN_FILE_DIGESTS: dict[str, str] = {
    "experiments/thermal_t2/__init__.py":
        "a59932c14653f6236f7193f91b2f288d205e98cd2e90a5bfa978c4de045f1eab",
    "experiments/thermal_t2/t2_config.py":
        "4d12fbac7dba7ea37fe9d61e8e80f22b9edb1510220f22b94a29ff14dd0c1966",
    "experiments/thermal_t2/t2_run.py":
        "83b016223e61d09df201d1b6e3f9cef5df4dc62b22839af658f3f44f1d8286c7",
    "experiments/thermal_t2/t2_truth.py":
        "aca991890a0d4d961270ec6d785f8e5d9269e4baf39f5e8a88e89da24545c1dd",
}


def band_of(index: int) -> str:
    """Which margin band a scenario index belongs to. Deterministic."""
    if not 0 <= index < SCENARIO_COUNT:
        raise IndexError(f"scenario {index} outside {SCENARIO_COUNT}")
    return tuple(MARGIN_BANDS)[index // SCENARIOS_PER_BAND]


def config_payload() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": T3_VERSION,
        "base_commit": BASE_COMMIT,
        "scientific_question": SCIENTIFIC_QUESTION,
        "inherited": {
            "t1_config_hash": t1_config_hash(),
            "t2_config_hash": t2_config_hash(),
            "used_as": "frozen prior calibration evidence only",
        },
        "terminal_decision": {
            "terminal_time_s": TERMINAL_TIME_S,
            "assimilation_time_s": END_TIME_S,
            "fourier_ratio_r": FOURIER_RATIO,
            "terminal_metric": TERMINAL_METRIC,
            "terminal_qoi": TERMINAL_QOI_DESCRIPTION,
            "decision_id": DECISION_ID,
            "decision": DECISION_DESCRIPTION,
            "asymmetric_loss": ASYMMETRIC_LOSS,
            "loss_model": LOSS_MODEL,
            "why_not_the_assimilated_qoi": (
                "at r = 1 the discretization error is exactly an "
                "effective-alpha shift and fitting alpha cancels it, so every "
                "rung predicts the assimilated QoI equally well. r = 3 breaks "
                "that cancellation"
            ),
        },
        "scenarios": {
            "count": SCENARIO_COUNT,
            "per_band": SCENARIOS_PER_BAND,
            "alpha_true_range": [ALPHA_TRUE_MIN, ALPHA_TRUE_MAX],
            "margin_bands": {k: list(v) for k, v in MARGIN_BANDS.items()},
            "band_intent": BAND_INTENT,
            "seed_entropy": SEED_ENTROPY,
            "rule": SCENARIO_RULE,
        },
        "observation_model": {
            "distribution": "gaussian_additive",
            "sigma": OBSERVATION_SIGMA,
            "count": OBSERVATION_COUNT,
            "metric": OBSERVATION_METRIC,
        },
        "costs": {
            "fidelity_cost": FIDELITY_COST,
            "cost_model": COST_MODEL,
            "wrong_decision_cost": WRONG_DECISION_COST,
            "wrong_decision_cost_sweep": list(WRONG_DECISION_COST_SWEEP),
            "units": "work proxy (n_cells * n_steps) from the frozen ladder",
        },
        "rules": {
            "escalation": ESCALATION_RULE,
            "stopping": STOPPING_RULE,
            "safety_factor": ESCALATION_SAFETY_FACTOR,
            "quantile": ESCALATION_QUANTILE,
            "baselines": BASELINE_RULE,
            "indicator_is_conservative": (
                "the successive-difference indicator over-estimates the finer "
                "rung's error by roughly 5-10x on the feasibility probe, and "
                "no order-of-accuracy correction is applied because the frozen "
                "thermal gate refuses to separate spatial from temporal order. "
                "Over-escalation in the MODERATE band is therefore expected "
                "and is measured, not removed"
            ),
        },
        "strategies": list(STRATEGIES),
        "primary_metric": PRIMARY_METRIC,
        "primary_metric_definition": PRIMARY_METRIC_DEFINITION,
        "metrics": list(METRICS),
        "definitions": {
            "confident_decision": CONFIDENT_DECISION_DEFINITION,
            "unnecessary_escalation": UNNECESSARY_ESCALATION_DEFINITION,
            "required_escalation_missed": REQUIRED_ESCALATION_MISSED_DEFINITION,
        },
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "falsification_criteria": list(FALSIFICATION_CRITERIA),
        "expected_negative_regime": EXPECTED_NEGATIVE_REGIME,
        "no_tuning_after_results": NO_TUNING_AFTER_RESULTS,
        "non_goals": list(NON_GOALS),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
