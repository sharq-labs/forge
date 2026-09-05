"""E3 — Adequacy evidence vs parameter EVSI.

Runs under pytest, and standalone via
``python -m tests.test_sria_e3_adequacy_obligation``.

The claim under test: a preregistered, finite model-adequacy obligation can
make a campaign acquire challenge evidence after parameter-learning EVSI has
collapsed, without assigning that evidence any fake information value — and the
same obligation clears a well-specified family and withholds certification from
a misspecified one.

The invariant every test here protects:

    A measurement may have almost zero value for estimating theta and still be
    mandatory evidence for deciding whether the model containing theta deserves
    certification. Do not fake the former in order to justify the latter.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import sys
from pathlib import Path

import numpy as np

from experiments.electrical_e2 import e2_truth
from experiments.electrical_e2.e2_adequacy import (
    AdequacyState,
    ExecutionValidity,
    PredictiveCommitmentViolation,
)
from experiments.electrical_e2.e2_model import evsi, posterior_summary
from experiments.electrical_e3 import (
    DECISION_PATH_MODULES,
    E2_DECISION_PATH_MODULES,
    E3_VERSION,
)
from experiments.electrical_e3.e3_config import (
    ADEQUACY_OBLIGATION,
    ADEQUACY_RESERVE,
    BUDGET_POLICY_RESERVED,
    BUDGET_POLICY_SHARED,
    CANDIDATE_ACTIONS,
    E2_CONFIG_HASH,
    E2_FROZEN_FILE_DIGESTS,
    EXPERIMENT_VERSION,
    FORBIDDEN_OBLIGATION_VOCABULARY,
    TOTAL_BUDGET,
    config_hash,
    preregistration_hash,
)
from experiments.electrical_e3.e3_harness import (
    ACTION_BY_ID,
    build_e3_stack,
    family_for,
    run_calibration,
)
from experiments.electrical_e3.e3_obligation import (
    CERTIFY_CAMPAIGN_ALLOWED_PARAMETERS,
    AdequacyScope,
    Certification,
    Disposition,
    ObligationBindingError,
    ObligationLedger,
    ObligationStatus,
    certify_campaign,
    scope_from_e2_state,
)
from experiments.electrical_e3.e3_run import (
    EXECUTION_REASON_OBLIGATION,
    run_e3,
)
from src.engcore.sria.campaign.stopping import StopReview, StopReviewOutcome
from src.engcore.sria.decision.actions import ActionFamily

#: The scored E3 run, executed once and shared (fully deterministic).
_RESULT = None


def e3_result():
    global _RESULT
    if _RESULT is None:
        _RESULT = run_e3()
    return _RESULT


def world_a():
    return e3_result()["world_a_well_specified"]


def world_b():
    return e3_result()["world_b_misspecified"]


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# =====================================================================
# 1-2. Preregistration and the frozen base
# =====================================================================

def test_1_frozen_e3_config_hash_is_stable():
    first = config_hash()
    assert config_hash() == first
    assert len(first) == 64
    pre = preregistration_hash()
    assert preregistration_hash() == pre
    assert pre != first
    result = e3_result()
    assert result["config_hash"] == first
    assert result["preregistration_hash"] == pre
    # The obligation is INSIDE the hash, so it cannot grow after the run.
    obligation = result["config"]["adequacy_obligation"]
    assert obligation["n_required"] == 3
    assert obligation["required_action_ids"] == list(
        ADEQUACY_OBLIGATION.required_action_ids
    )
    assert obligation["max_adequacy_cost"] == ADEQUACY_OBLIGATION.max_adequacy_cost
    assert E3_VERSION == EXPERIMENT_VERSION


def test_2_e2_final_freeze_files_are_unchanged():
    from experiments.electrical_e2.e2_config import config_hash as e2_hash

    root = _repo_root()
    for name, expected in E2_FROZEN_FILE_DIGESTS.items():
        raw = (root / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == expected, f"E2 changed: {name}"
    assert e2_hash() == E2_CONFIG_HASH


# =====================================================================
# 3-5. Parameter EVSI stays honest
# =====================================================================

def test_3_parameter_state_is_identical_across_policies_before_adequacy():
    """The two policies differ only in whether a criterion is registered."""
    for world in (world_a(), world_b()):
        evsi_only = {
            s["action_id"]: s for s in world["evsi_only_phase"]["scores"]
        }
        obligation = {
            s["action_id"]: s for s in world["obligation_aware_pre"]["scores"]
        }
        assert set(evsi_only) == set(obligation)
        assert evsi_only, "no candidates were scored"
        for action_id, left in evsi_only.items():
            right = obligation[action_id]
            assert left["parameter_evsi"] == right["parameter_evsi"], action_id
            assert left["cost"] == right["cost"], action_id
            assert (
                left["net_parameter_value"] == right["net_parameter_value"]
            ), action_id
    assert e3_result()["success_checks"][
        "parameter_evsi_identical_across_policies"
    ] is True


def test_4_no_adequacy_utility_enters_the_decision_basis():
    """Structural, not just numerical.

    The outcome model that supplies the information term has no reference to
    the obligation ledger, and the scores carry an explicit assumption saying
    the term is parameter information only.
    """
    import experiments.electrical_e3.e3_harness as harness_module

    source = Path(harness_module.__file__).read_text(encoding="utf-8")
    outcome_model_src = source.split("class E3EvsiOutcomeModel")[1].split(
        "class E3CostSupplier"
    )[0]
    for forbidden in (
        "ObligationLedger",
        "obligation_state",
        "adequacy_scope",
        "ObligationStatus",
    ):
        assert forbidden not in outcome_model_src, forbidden
    # The information term is E2's evsi(), called on the plain action spec.
    assert "evsi(weights, spec)" in outcome_model_src

    # And the probes score exactly what E2's unmodified quadrature says.
    stack = build_e3_stack(e2_truth.WELL_SPECIFIED_TRUTH, label="t4")
    run_calibration(stack)
    weights = stack.harness.posterior_for(stack.harness.current_observations())
    scored = {
        s["action_id"]: s["parameter_evsi"]
        for s in world_a()["obligation_aware_pre"]["scores"]
    }
    for action_id, value in scored.items():
        assert value == evsi(weights, ACTION_BY_ID[action_id]), action_id


def test_5_parameter_evsi_is_at_the_floor_while_the_obligation_is_outstanding():
    world = world_b()
    before = world["before_adequacy"]
    assert before["obligation_status"] == ObligationStatus.OUTSTANDING.value
    assert before["adequacy_scope"] == AdequacyScope.NOT_ESTABLISHED.value
    assert before["posterior"]["evpi"] < 1e-30
    for action_id, row in before["evsi_table"].items():
        assert row["parameter_evsi"] < 1e-9, action_id
        assert row["net"] < 0.0, action_id
    # Declaring the obligation did not make the model adequate.
    assert before["adequacy_scope"] != (
        AdequacyScope.ACCEPTABLE_FOR_DECLARED_SCOPE.value
    )


# =====================================================================
# 6-8. Economic stop vs scientific stop
# =====================================================================

def test_6_economic_no_action_cannot_self_certify_a_stop():
    world = world_b()
    assert all(
        s["net_parameter_value"] < 0.0
        for s in world["obligation_aware_pre"]["scores"]
    )
    review = world["obligation_aware_pre"]["stop_review"]
    assert review["outcome"] != StopReviewOutcome.STOP_APPROVED.value
    assert review["approves"] is False
    assert review["is_certification"] is False
    assert review["criterion_id"] == ADEQUACY_OBLIGATION.obligation_id
    assert review["arbiter_verdict"] == "inconclusive"

    # Structurally impossible to hold the forbidden combination at all.
    _raises(
        ValueError,
        StopReview,
        review_id="x",
        proposal_id="y",
        outcome=StopReviewOutcome.STOP_APPROVED,
        terminal_objective_available=True,
        arbiter_decision_id="d",
        criterion_id=ADEQUACY_OBLIGATION.obligation_id,
        unmet_obligations=(ADEQUACY_OBLIGATION.obligation_id,),
        reasons=("forged",),
    )


def test_7_affordable_outstanding_obligation_routes_a_preregistered_probe():
    world = world_b()
    executed = world["acquisition"]["executed"]
    assert executed, "no probe was routed"
    assert [r["action_id"] for r in executed] == list(
        ADEQUACY_OBLIGATION.required_action_ids
    )
    for row in executed:
        assert row["action_id"] in ADEQUACY_OBLIGATION.required_action_ids
        assert row["admitted"] is True
    # The frozen selection rule: cheapest outstanding required, declared order.
    assert executed[0]["action_id"] == ADEQUACY_OBLIGATION.required_action_ids[0]


def test_8_probe_selection_reason_is_the_obligation_not_parameter_evsi():
    for world in (world_a(), world_b()):
        for row in world["acquisition"]["executed"]:
            assert row["execution_reason"] == EXECUTION_REASON_OBLIGATION
            assert row["parameter_evsi_at_selection"] < 1e-9
            assert "parameter EVSI is at the floor" in row["why_action_executed"]
    # And the probes the obligation does NOT require were never bought, even
    # though their EVSI is indistinguishable from the ones that were.
    control = e3_result()["control_3_already_satisfied"]
    assert set(control["never_required"]) == {
        "adequacy_probe_20V",
        "adequacy_probe_24V",
    }
    bought = {r["action_id"] for r in world_b()["acquisition"]["executed"]}
    assert bought.isdisjoint(control["never_required"])


# =====================================================================
# 9-10. Prediction before observation
# =====================================================================

def test_9_predictive_commitment_exists_before_probe_execution():
    for world in (world_a(), world_b()):
        ledger = world["acquisition"]["commitment_ledger"]
        assert ledger["chain_verified"] is True
        assert ledger["sealed_at"] is not None
        for commitment in ledger["commitments"]:
            # Committed before the seal; the seal precedes every observation.
            assert commitment["sequence"] < ledger["sealed_at"]
            assert commitment["n_observations"] == 4
            assert commitment["artifact_hash"]
        surprises = world["acquisition"]["adequacy"]["surprises"]
        for surprise in surprises:
            assert surprise["commitment_sequence"] < ledger["sealed_at"]
            assert ledger["sealed_at"] < surprise["observation_sequence"]


def test_10_probe_without_a_valid_commitment_cannot_satisfy_the_obligation():
    ledger = ObligationLedger()
    action_id = ledger.required[0]
    ledger.record_probe(
        action_id=action_id,
        source_voltage_volt=ACTION_BY_ID[action_id].source_voltage_volt,
        execution_id="no-commitment",
        execution_valid=True,
        admitted=True,
        commitment_artifact_hash="",          # nothing was predicted
        realized_cost=0.15,
        execution_reason=EXECUTION_REASON_OBLIGATION,
    )
    assert action_id in ledger.outstanding_required()
    assert ledger.records[0].is_obligation_evidence is False
    assert ledger.status is ObligationStatus.UNRESOLVED_EXECUTION_FAILURE


# =====================================================================
# 11-13. The obligation passes one family and fails the other
# =====================================================================

def test_11_well_specified_probe_completes_the_obligation_and_passes():
    world = world_a()
    assert world["obligation_status"] == ObligationStatus.COMPLETED.value
    assert world["adequacy_scope"] == (
        AdequacyScope.ACCEPTABLE_FOR_DECLARED_SCOPE.value
    )
    adequacy = world["acquisition"]["adequacy"]
    assert adequacy["scored"] is True
    assert adequacy["e2_state"] == AdequacyState.MODEL_ADEQUACY_ACCEPTABLE.value
    assert adequacy["aggregate"]["n_extreme"] == 0
    assert adequacy["aggregate"]["p_joint"] > 0.01
    review = world["obligation_aware_post"]["stop_review"]
    assert review["outcome"] == StopReviewOutcome.STOP_APPROVED.value
    assert review["arbiter_verdict"] == "valid"
    assert review["arbiter_decision_id"]        # minted by a real Arbiter
    assert world["certification"]["scientific_certification"] == (
        Certification.ELIGIBLE.value
    )


def test_12_misspecified_probe_completes_the_test_but_adequacy_fails():
    world = world_b()
    assert world["obligation_status"] == ObligationStatus.COMPLETED.value
    adequacy = world["acquisition"]["adequacy"]
    assert adequacy["scored"] is True
    assert adequacy["e2_state"] == AdequacyState.MODEL_SPACE_INADEQUATE.value
    assert adequacy["aggregate"]["n_extreme"] >= 2
    review = world["obligation_aware_post"]["stop_review"]
    assert review["outcome"] == StopReviewOutcome.STOP_REJECTED.value
    assert review["arbiter_verdict"] == "invalid"
    certification = world["certification"]
    assert certification["scientific_certification"] == (
        Certification.NOT_CERTIFIABLE.value
    )
    assert certification["reason"] == "MODEL_SPACE_INADEQUATE"
    assert certification["disposition"] == (
        Disposition.MODEL_REVISION_REQUIRED.value
    )


def test_13_test_completed_and_model_passed_are_separate_states():
    """The same obligation status, two opposite model verdicts."""
    assert (
        world_a()["obligation_status"]
        == world_b()["obligation_status"]
        == ObligationStatus.COMPLETED.value
    )
    assert world_a()["adequacy_scope"] != world_b()["adequacy_scope"]
    assert (
        world_a()["certification"]["scientific_certification"]
        != world_b()["certification"]["scientific_certification"]
    )
    # And the gate reports the obligation as fully discharged while refusing.
    refused = certify_campaign(
        "A",
        ObligationStatus.COMPLETED,
        AdequacyScope.MODEL_SPACE_INADEQUATE,
        ExecutionValidity.VALID,
    )
    assert refused.obligation_status is ObligationStatus.COMPLETED
    assert refused.scientific_certification is Certification.NOT_CERTIFIABLE
    assert "discharged COMPLETELY" in refused.statement


# =====================================================================
# 14-16. Finiteness, budget, execution failure
# =====================================================================

def test_14_a_satisfied_obligation_does_not_force_duplicate_probes():
    control = e3_result()["control_3_already_satisfied"]
    assert control["obligation_status"] == ObligationStatus.COMPLETED.value
    assert control["next_probe"] is None
    assert control["outstanding"] == []
    assert len(control["satisfied"]) == ADEQUACY_OBLIGATION.n_required
    # Finite by construction: 3 required of 5 feasible, and it stops.
    assert control["probes_executed"] == ADEQUACY_OBLIGATION.n_required
    assert control["n_catalogue"] > ADEQUACY_OBLIGATION.n_required


def test_15_budget_infeasible_obligation_is_not_a_passing_model():
    control = e3_result()["control_4_budget_infeasible"]
    shared = control[BUDGET_POLICY_SHARED]
    assert shared["obligation_status"] == (
        ObligationStatus.UNRESOLVED_BUDGET_INFEASIBLE.value
    )
    assert shared["certification"]["scientific_certification"] == (
        Certification.NOT_CERTIFIABLE.value
    )
    assert shared["certification"]["reason"] == (
        "REQUIRED_ADEQUACY_EVIDENCE_BUDGET_INFEASIBLE"
    )
    assert shared["certification"]["disposition"] == (
        Disposition.CERTIFICATION_NOT_POSSIBLE.value
    )
    # Not a model finding, and not an execution finding.
    assert shared["certification"]["reason"] != "MODEL_SPACE_INADEQUATE"
    assert shared["certification"]["disposition"] != (
        Disposition.EXECUTION_REPAIR_REQUIRED.value
    )
    # The frozen reservation protected the same evidence under the same spend.
    reserved = control[BUDGET_POLICY_RESERVED]
    assert reserved["obligation_status"] == ObligationStatus.COMPLETED.value
    assert control["comparison"]["protection_observed"] is True


def test_16_computationally_invalid_probe_is_not_adequacy_evidence():
    control = e3_result()["control_5_execution_invalid"]
    assert control["obligation_status"] == (
        ObligationStatus.UNRESOLVED_EXECUTION_FAILURE.value
    )
    assert control["adequacy_scored"] is False
    assert control["adequacy_scope"] == AdequacyScope.NOT_ASSESSED.value
    assert control["certification"]["disposition"] == (
        Disposition.EXECUTION_REPAIR_REQUIRED.value
    )
    assert control["certification"]["reason"] != "MODEL_SPACE_INADEQUATE"
    for row in control["executed"]:
        assert row["admitted"] is False
        assert row["execution_validity"] == ExecutionValidity.INVALID.value


def test_17_surprising_but_valid_probe_is_admitted():
    world = world_b()
    surprises = world["acquisition"]["adequacy"]["surprises"]
    worst = min(surprises, key=lambda s: s["tail_probability"])
    assert worst["tail_probability"] < 1e-4
    row = next(
        r
        for r in world["acquisition"]["executed"]
        if r["action_id"] == worst["action_id"]
    )
    assert row["critic_verdict"] == "pass"
    assert row["arbiter_verdict"] == "valid"
    assert row["admitted"] is True
    assert row["execution_validity"] == ExecutionValidity.VALID.value
    assert all(r["admitted"] for r in world["acquisition"]["executed"])


# =====================================================================
# 18-19. The central counterfactual
# =====================================================================

def test_18_evsi_only_policy_stops_before_any_adequacy_measurement():
    for world in (world_a(), world_b()):
        phase = world["evsi_only_phase"]
        assert phase["executed_actions"] == []
        review = phase["stop_review"]
        assert review["outcome"] == StopReviewOutcome.STOP_NOT_ASSESSED.value
        assert review["criterion_id"] == ""       # none was registered
        assert any(
            "no independently declared stopping criterion" in r
            for r in review["reasons"]
        )
        assert phase["pause_reason"] == "no_action_worth_buying"
    assert e3_result()["success_checks"]["evsi_only_acquired_nothing"] is True


def test_19_obligation_aware_policy_acquires_evidence_from_the_same_state():
    """Same pre-probe parameter state, same prices, different outcome."""
    for world in (world_a(), world_b()):
        evsi_only = {
            s["action_id"]: s["net_parameter_value"]
            for s in world["evsi_only_phase"]["scores"]
        }
        obligation = {
            s["action_id"]: s["net_parameter_value"]
            for s in world["obligation_aware_pre"]["scores"]
        }
        assert evsi_only == obligation
        assert world["evsi_only_phase"]["executed_actions"] == []
        assert len(world["acquisition"]["executed"]) == (
            ADEQUACY_OBLIGATION.n_required
        )
        assert world["acquisition"]["adequacy"]["scored"] is True


# =====================================================================
# 20-22. Nothing computed inside the model may override the obligation
# =====================================================================

def test_20_posterior_confidence_cannot_override_the_obligation():
    world = world_b()
    after = world["posterior_after_adequacy"]
    assert after["sd_r2_ohm"] < 10.0
    assert after["p_above_threshold"] > 0.999999
    assert world["certification"]["scientific_certification"] == (
        Certification.NOT_CERTIFIABLE.value
    )
    # Structural: no confidence quantity is a parameter of the gate.
    params = tuple(inspect.signature(certify_campaign).parameters)
    assert params == CERTIFY_CAMPAIGN_ALLOWED_PARAMETERS
    for name in params:
        assert not any(
            token in name
            for token in ("sd", "entropy", "confidence", "evpi", "evsi", "stop")
        )


def test_21_zero_evpi_cannot_override_the_obligation():
    world = world_b()
    assert world["before_adequacy"]["posterior"]["evpi"] < 1e-30
    assert world["posterior_after_adequacy"]["evpi"] <= 1e-30
    # Outstanding, with EVPI already at the floor -> still not certifiable.
    outstanding = certify_campaign(
        "A",
        ObligationStatus.OUTSTANDING,
        AdequacyScope.NOT_ESTABLISHED,
        ExecutionValidity.VALID,
    )
    assert outstanding.scientific_certification is Certification.NOT_CERTIFIABLE
    assert outstanding.disposition is Disposition.ADEQUACY_EVIDENCE_REQUIRED


def test_22_zero_parameter_evsi_cannot_override_the_obligation():
    world = world_b()
    assert max(world["evsi_after_adequacy"].values()) < 1e-9
    assert max(
        row["parameter_evsi"] for row in world["before_adequacy"]["evsi_table"].values()
    ) < 1e-9
    assert world["certification"]["scientific_certification"] == (
        Certification.NOT_CERTIFIABLE.value
    )
    injections = {i["injection"]: i for i in e3_result()["adversarial_injections"]}
    assert injections["H"]["caught"] is True


# =====================================================================
# 23. No oracle leakage
# =====================================================================

def _module_imports(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute: set[str] = set()
    siblings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                if node.module:
                    siblings.add(node.module.split(".")[0])
                else:
                    siblings.update(alias.name for alias in node.names)
            elif node.module:
                absolute.add(node.module)
                # ``from package import module`` names the module in the alias,
                # not in node.module, so both have to be collected or a truth
                # import through a package would be invisible to this check.
                absolute.update(
                    f"{node.module}.{alias.name}" for alias in node.names
                )
    return absolute, siblings


def test_23_no_grader_truth_reaches_the_e3_decision_path():
    import experiments.electrical_e3 as package

    root = Path(package.__file__).resolve().parent
    e2_root = root.parent / "electrical_e2"
    for name in DECISION_PATH_MODULES:
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert "e3_truth" not in siblings
        assert not any("truth" in c for c in absolute | siblings), name
        assert siblings <= set(DECISION_PATH_MODULES), (name, siblings)
        # Any E2 module reached must be on E2's own decision-path list.
        for module in absolute:
            if module.startswith("experiments.electrical_e2."):
                reached = module.split(".")[2]
                assert reached in E2_DECISION_PATH_MODULES, (name, module)

    # Transitively: E2's decision-path modules import no truth either.
    for name in E2_DECISION_PATH_MODULES:
        absolute, siblings = _module_imports(e2_root / f"{name}.py")
        assert not any("truth" in c for c in absolute | siblings), name

    # The harness and runner ARE expected to reach the truth.
    absolute, _ = _module_imports(root / "e3_harness.py")
    assert any("e2_truth" in c for c in absolute)


def test_23b_the_unevaluable_obligation_vocabulary_is_not_used():
    """M5.1 recorded that ``validation_level:*`` obligations fail closed.

    A governance result built on an obligation that can never be satisfied
    would be an artifact of that bug. E3 uses a real, evaluable target instead,
    and this asserts the broken vocabulary appears nowhere in E3.
    """
    from experiments.electrical_e3.e3_obligation import (
        adequacy_stopping_criterion,
    )

    criterion = adequacy_stopping_criterion()
    assert ADEQUACY_OBLIGATION.obligation_id.startswith("adequacy:")
    for identifier in (
        ADEQUACY_OBLIGATION.obligation_id,
        criterion.criterion_id,
        criterion.obligation.target,
    ):
        assert not identifier.startswith(FORBIDDEN_OBLIGATION_VOCABULARY)

    # The decisive evidence that a REAL, evaluable target was used: a
    # ``validation_level:*`` obligation is hard-coded unsatisfied in the
    # Arbiter and can never produce VALID, so a genuine STOP_APPROVED over
    # this criterion is only reachable because the target is evaluable.
    review = world_a()["obligation_aware_post"]["stop_review"]
    assert review["outcome"] == StopReviewOutcome.STOP_APPROVED.value
    assert review["arbiter_verdict"] == "valid"
    assert review["criterion_id"] == criterion.criterion_id
    assert review["arbiter_decision_id"]


# =====================================================================
# 24-25. E1 / E2 regression surface
# =====================================================================

def test_24_e2_regression_surface_is_intact():
    from experiments.electrical_e2.e2_config import config_hash as e2_hash
    from experiments.electrical_e2.e2_run import run_solver_verification

    assert e2_hash() == E2_CONFIG_HASH
    gate = run_solver_verification()
    assert gate["passed"] is True
    # E3 added no import into E2's decision path.
    root = _repo_root() / "experiments" / "electrical_e2"
    for name in E2_DECISION_PATH_MODULES:
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert not any("e3_" in c for c in absolute | siblings), name


def test_25_e1_regression_surface_is_intact():
    from experiments.electrical_e1.e1_run import run_solver_verification

    gate = run_solver_verification()
    assert gate["passed"] is True
    root = _repo_root() / "experiments" / "electrical_e1"
    for name in ("e1_config", "e1_model"):
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert not any("e3_" in c or "e2_" in c for c in absolute | siblings)


# =====================================================================
# Architecture findings, demonstrated rather than asserted
# =====================================================================

def test_obligation_set_is_the_wrong_home_for_a_campaign_scoped_obligation():
    """Why the adequacy obligation is carried by a StoppingCriterion.

    Placed in the campaign ObligationSet it is looked for among ONE evidence
    record's checks, never found, and blocks all admission. This is also why
    the frozen validation-liveness router cannot see it: that router reads
    unsatisfied obligations from ObligationSet.
    """
    probe = e3_result()["obligation_set_placement_probe"]
    assert probe["critic_verdict"] == "pass"       # the science was fine
    assert probe["arbiter_verdict"] == "inconclusive"
    assert probe["admitted"] is False
    assert probe["belief_size"] == 0
    assert probe["blocks_all_admission"] is True


def test_adequacy_probes_are_declared_validate_so_the_frozen_fence_applies():
    for spec in CANDIDATE_ACTIONS:
        family = family_for(spec)
        if spec.phase == "adequacy_probe":
            assert family is ActionFamily.VALIDATE, spec.action_id
        else:
            assert family is ActionFamily.CHARACTERIZE, spec.action_id

    # The fence is the frozen ledger's, not E3's.
    stack = build_e3_stack(e2_truth.WELL_SPECIFIED_TRUTH, label="fence")
    ledger = stack.budget_ledger(total=TOTAL_BUDGET, reserved=ADEQUACY_RESERVE)
    ledger.settle(
        charge_id="drain-general",
        action_id="parameter_repeat_10V",
        iteration=0,
        family=ActionFamily.CHARACTERIZE,
        realized=TOTAL_BUDGET - ADEQUACY_RESERVE,
        predicted=TOTAL_BUDGET - ADEQUACY_RESERVE,
    )
    assert ledger.general_pool == 0.0
    assert ledger.validation_pool == ADEQUACY_RESERVE
    assert ledger.affordable(0.15, family=ActionFamily.VALIDATE) is True
    assert ledger.affordable(0.15, family=ActionFamily.CHARACTERIZE) is False


def test_scope_mapping_from_e2_is_total_and_refuses_to_guess():
    for state in AdequacyState:
        assert isinstance(scope_from_e2_state(state), AdequacyScope)
    _raises(KeyError, scope_from_e2_state, "not_a_state")


def test_obligation_binding_rejects_a_different_condition():
    ledger = ObligationLedger()
    _raises(
        ObligationBindingError,
        ledger.record_probe,
        action_id="adequacy_probe_16V",
        source_voltage_volt=10.0,
        execution_id="wrong",
        execution_valid=True,
        admitted=True,
        commitment_artifact_hash="abc",
        realized_cost=0.02,
        execution_reason="pretending",
    )
    _raises(
        ObligationBindingError,
        ledger.record_probe,
        action_id="not_a_declared_action",
        source_voltage_volt=16.0,
        execution_id="wrong",
        execution_valid=True,
        admitted=True,
        commitment_artifact_hash="abc",
        realized_cost=0.02,
        execution_reason="pretending",
    )
    assert len(ledger.outstanding_required()) == ADEQUACY_OBLIGATION.n_required


def test_all_adversarial_injections_are_caught():
    injections = e3_result()["adversarial_injections"]
    assert [i["injection"] for i in injections] == list("ABCDEFGH")
    for injection in injections:
        assert injection["caught"] is True, injection
        assert injection["catcher"], injection


def test_e3_overall_verdict_and_success_checks():
    """Every obligation-policy check passes, and the verdict is still bounded.

    The two groups answer different questions. ``success_checks`` asks whether
    the obligation policy worked; ``campaign_native_checks`` asks whether the
    frozen stack did it unaided. E3 is entitled to the first claim and not the
    second, so the verdict is the weaker of the two.
    """
    result = e3_result()
    for name, value in result["success_checks"].items():
        assert value is True, name
    assert result["verdict"] == "E3 PARTIALLY VERIFIED"


def test_campaign_native_acquisition_is_measured_not_asserted():
    """The claim bound comes from what a runner actually executed."""
    result = e3_result()
    native = result["campaign_native_checks"]

    # What the frozen stack DID do on its own.
    assert native["stop_refusal_is_campaign_native"] is True
    assert native["validation_budget_fence_is_campaign_native"] is True
    # What it did NOT: no CampaignRunner pass executed any adequacy probe.
    assert native["adequacy_acquisition_is_campaign_native"] is False
    assert result["runner_executed_probes"] == []
    for world in (world_a(), world_b()):
        for phase in (
            "evsi_only_phase",
            "obligation_aware_pre",
            "obligation_aware_post",
        ):
            assert world[phase]["executed_actions"] == []
        # ...while the adapter executed the full required set.
        assert len(world["acquisition"]["executed"]) == (
            ADEQUACY_OBLIGATION.n_required
        )

    # The verdict follows from the conjunction, not from wording.
    assert all(result["success_checks"].values())
    assert not all(native.values())
    assert result["verdict"] == "E3 PARTIALLY VERIFIED"


def test_reported_claim_does_not_overstate_campaign_support():
    result = e3_result()
    claim = result["allowed_claim"]
    assert "did not natively acquire" in claim
    assert "experiment-local adapter" in claim
    assert "remain scientifically binding" in claim
    assert "without assigning fake parameter information value" in claim
    # The forbidden overstatement, in any casing.
    lowered = claim.lower()
    assert "the campaign acquired" not in lowered
    assert "campaign-native acquisition" not in lowered
    assert "PARTIALLY VERIFIED" in result["claim_scope"]


def test_next_step_is_one_integration_milestone_and_not_started():
    step = e3_result()["next_step"]
    assert step["milestone"] == "CAMPAIGN OBLIGATION ROUTING INTEGRATION"
    assert step["started"] is False
    assert "generic validation subsystem" in step["not"]
    # Four gaps were found, and the next step does not claim vocabulary alone
    # closes them.
    gaps = e3_result()["architecture_gaps"]
    assert len(gaps) == 4
    for gap in gaps:
        assert gap["gap"] and gap["evidence"]
    assert "three of the four" in step["not"]


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA E3 — adequacy evidence vs parameter EVSI")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"E3: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"E3: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
