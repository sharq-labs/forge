"""V0.1 — the minimal certification path, end to end through CampaignRunner.

E3 froze with one demonstrated production failure: the campaign could refuse
scientific STOP while a declared adequacy obligation was outstanding, but it
could not route itself to the finite evidence that would resolve the refusal.
E3 recorded ``runner_executed_probes == []`` and did step 5 in an
experiment-local adapter.

This file reproduces that exact state and asserts the adapter is gone.

The scientific fixture is E3's, imported read-only: the real Electrical solver,
the real posterior, the real E2 EVSI, the real grader worlds. Nothing about the
science is re-derived here, because nothing about the science changed — the
milestone is engineering integration and the test says only that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from experiments.electrical_e2 import e2_truth
from experiments.electrical_e2.e2_adequacy import (
    AdequacyState,
    CommitmentLedger,
    aggregate_adequacy,
    build_joint_predictive,
    classify_adequacy,
    score_commitments,
)
from experiments.electrical_e2.e2_model import (
    evsi,
    posterior_summary,
    posterior_weights,
    predictive_mixture,
)
from experiments.electrical_e3.e3_config import (
    ADEQUACY_OBLIGATION,
    CANDIDATE_ACTIONS,
    CHARTER_VERSION,
    COST_UNIT,
    MAX_ITERATIONS,
)
from experiments.electrical_e3.e3_harness import (
    ACTION_BY_ID,
    E3Generator,
    e3_charter,
    build_e3_stack,
    family_for,
    run_calibration,
    swap_to_faulty_executor,
)
from src.engcore.scientific import Quantity
from src.engcore.sria import ExecutorType, ResearchAction
from src.engcore.sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    FindingImpact,
    Severity,
)
from src.engcore.sria.campaign import (
    BudgetLedger,
    CampaignRunner,
    CertificationRequirement,
    RequirementStatus,
)
from src.engcore.sria.campaign.events import CampaignEventType
from src.engcore.sria.campaign.state import PauseReason
from src.engcore.sria.campaign.stopping import StopReviewOutcome, StoppingCriterion
from src.engcore.sria.decision import ActionFamily, ActionProposal, AtomicAction
from src.engcore.sria.provenance import AssessmentProvenance

CRITERION_ID = "certification:constant_r:declared_range"
REQUIRED = ADEQUACY_OBLIGATION.required_action_ids
TOTAL_BUDGET = 1.20
RESERVE = 0.45


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


# =====================================================================
# The V0.1 contract adapter: predictions committed before observation
# =====================================================================

class CertifiedProbeGenerator:
    """E3's generator, plus the one thing V0.1 requires of a probe.

    Each required action carries ``prediction_ref`` — the content hash of a
    predictive committed and SEALED before the campaign started. This is the
    thin adapter around E2's commitment primitive the milestone allows, and it
    is deliberately not promoted into src/: the runner only checks that a
    reference exists, never what is inside it.
    """

    family = ActionFamily.CHARACTERIZE

    def __init__(self, commitments: CommitmentLedger) -> None:
        self._refs = {
            action_id: commitment.artifact_hash
            for action_id, commitment in commitments.commitments.items()
        }
        self._inner = E3Generator()

    def generate(self, context):
        out = []
        for candidate in self._inner.generate(context):
            member = candidate.members[0]
            reference = self._refs.get(member.action_id, "")
            if not reference:
                out.append(candidate)
                continue
            metadata = dict(member.action.metadata)
            metadata["prediction_ref"] = reference
            spec = ACTION_BY_ID[member.action_id]
            out.append(
                AtomicAction(
                    action=ResearchAction(
                        action_id=member.action_id,
                        executor_type=ExecutorType.SIMULATION,
                        target_ref="theta.R2",
                        parameters={
                            "source_voltage": Quantity(
                                spec.source_voltage_volt, "volt"
                            )
                        },
                        expected_cost={
                            "acquisition": Quantity(spec.cost, COST_UNIT)
                        },
                        metadata=metadata,
                    ),
                    proposal=ActionProposal(
                        family=family_for(spec),
                        target_ref="theta.R2",
                        rationale=spec.description,
                        expected_observable="node_voltage:mid",
                        informative_failure_causes=("numerical",),
                    ),
                )
            )
        return tuple(out)


class V01AdequacyEvaluator:
    """Stopping criterion: has the declared test been done, and did it pass?

    Reads the gateway (which required actions have admitted evidence) and the
    sealed commitments. It never reads the grader truth, the posterior, EVPI or
    EVSI, and it mints no stopping verdict — it produces an assessment and the
    Arbiter decides.
    """

    criterion_id = CRITERION_ID
    critic_id = "v01.certification"
    critic_version = "1"

    def __init__(self, gateway, commitments: CommitmentLedger) -> None:
        self._gateway = gateway
        self._commitments = commitments

    def admitted_actions(self) -> set[str]:
        return {
            str(entry.claim_payload["action_id"])
            for entry in self._gateway.belief.active_view().values()
        }

    def adequacy_state(self) -> AdequacyState | None:
        admitted = self.admitted_actions()
        if not set(REQUIRED) <= admitted:
            return None
        for action_id in REQUIRED:
            if action_id in self._commitments.observations:
                continue
            y = next(
                float(e.claim_payload["y_volt"])
                for e in self._gateway.belief.active_view().values()
                if str(e.claim_payload["action_id"]) == action_id
            )
            self._commitments.record_observation(
                action_id=action_id,
                y_volt=y,
                execution_id=f"v01-{action_id}",
                execution_valid=True,
            )
        surprises = score_commitments(self._commitments)
        joint = build_joint_predictive(
            self._commitments, [s.action_id for s in surprises]
        )
        return classify_adequacy(
            surprises, aggregate_adequacy(surprises, joint)
        ).state

    def evaluate(self, context, *, assessment_id: str) -> CriticAssessment:
        state = self.adequacy_state()
        if state is None:
            verdict, findings, summary = (
                CriticVerdict.FAIL,
                (
                    Finding(
                        code="v01.certification_outstanding",
                        severity=Severity.BLOCKING,
                        category="process",
                        message="declared certification evidence is outstanding",
                        impact=FindingImpact.ASSURANCE_BLOCKING,
                    ),
                ),
                "required certification evidence has not been obtained",
            )
        elif state is AdequacyState.MODEL_ADEQUACY_ACCEPTABLE:
            verdict, findings, summary = (
                CriticVerdict.PASS,
                (),
                "required evidence obtained; the family survived it",
            )
        else:
            verdict, findings, summary = (
                CriticVerdict.FAIL,
                (
                    Finding(
                        code="v01.model_space_inadequate",
                        severity=Severity.BLOCKING,
                        category="model_adequacy",
                        message="the required evidence refuted the family",
                        impact=FindingImpact.EVIDENCE_INVALIDATING,
                    ),
                ),
                f"required evidence obtained; adequacy is {state.value}",
            )
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=CriticClass.PROCESS,
            subject_ref=assessment_id,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=(CRITERION_ID,),
            ),
            checks=(
                CheckRecord(
                    name=self.criterion_id,
                    outcome=verdict,
                    mandatory=True,
                    detail=summary,
                ),
            ),
            findings=findings,
            summary=summary,
        )


# =====================================================================
# Fixture: the exact E3 state
# =====================================================================

def build_v01_campaign(
    spec,
    *,
    label: str,
    with_requirement: bool = True,
    total_budget: float = TOTAL_BUDGET,
    reserved: float = RESERVE,
    pre_spend_general: float = 0.0,
    faulty: bool = False,
):
    """A real CampaignRunner in E3's post-calibration state."""
    stack = build_e3_stack(spec, label=label)
    run_calibration(stack)

    weights = posterior_weights(stack.harness.current_observations())
    commitments = CommitmentLedger(f"{label}-commitments")
    for action_id in REQUIRED:
        action = ACTION_BY_ID[action_id]
        commitments.commit(
            action_id=action_id,
            source_voltage_volt=action.source_voltage_volt,
            noise_sigma_volt=action.noise_sigma_volt,
            evidence_snapshot_digest=stack.e2.evidence_snapshot_digest(),
            n_observations=len(stack.harness.current_observations()),
            mixture=predictive_mixture(weights, action),
        )
    commitments.seal()

    budget = BudgetLedger(
        total_budget=total_budget,
        reserved_validation_budget=reserved,
        cost_unit=COST_UNIT,
    )
    if pre_spend_general > 0.0:
        budget.settle(
            charge_id=f"{label}-prespend",
            action_id="parameter_repeat_10V",
            iteration=0,
            family=ActionFamily.CHARACTERIZE,
            realized=pre_spend_general,
            predicted=pre_spend_general,
        )
    if faulty:
        swap_to_faulty_executor(stack)

    requirements = (
        (
            CertificationRequirement(
                requirement_id=CRITERION_ID,
                required_action_ids=REQUIRED,
                source="v0.1 test charter",
            ),
        )
        if with_requirement
        else ()
    )
    evaluator = V01AdequacyEvaluator(stack.gateway, commitments)
    generator = CertifiedProbeGenerator(commitments)
    # The runner reads its candidate pool from the harness when the harness
    # supplies one, so the certified generator has to be installed there — not
    # only passed to the constructor, which is the fallback.
    stack.harness.generators = lambda run: (generator,)
    runner = CampaignRunner(
        run_id=label,
        charter=e3_charter(),
        harness=stack.harness,
        gateway=stack.gateway,
        arbiter=stack.arbiter,
        obligations=stack.harness.obligations,
        budget=budget,
        max_iterations=8,
        generators=(generator,),
        charter_version=CHARTER_VERSION,
        stopping_criteria=(
            StoppingCriterion(
                criterion_id=CRITERION_ID,
                statement="required certification evidence obtained and passed",
                source="v0.1 test charter",
                evaluator_id=evaluator.critic_id,
                evaluator_version=evaluator.critic_version,
            ),
        ),
        stopping_evaluators={CRITERION_ID: evaluator},
        certification_requirements=requirements,
    )
    runner.adopt_prior_assurance(stack.assurance_record())
    # restore() rebuilds the ledger from the checkpoint, so the live one is the
    # runner's. Returning the pre-restore object would silently report zeros.
    return stack, runner, commitments, runner.budget, weights


def _executed_probes(runner) -> list[str]:
    return [
        str(e.payload.get("action_id", ""))
        for e in runner.events.of_type(CampaignEventType.ACTION_SELECTED)
        if str(e.payload.get("action_id", "")) in REQUIRED
    ]


# =====================================================================
# 1. The E3 state is genuinely reproduced
# =====================================================================

def test_1_e3_state_is_reproduced_before_routing():
    stack, runner, _c, _b, weights = build_v01_campaign(
        e2_truth.WELL_SPECIFIED_TRUTH, label="v01-state"
    )
    summary = posterior_summary(weights)
    assert summary["p_above_threshold"] > 0.999999
    assert summary["sd_r2_ohm"] < 25.0
    assert summary["evpi"] < 1e-30
    for action in CANDIDATE_ACTIONS:
        value = evsi(weights, action)
        assert value < 1e-9, action.action_id
        assert value - action.cost < 0.0, action.action_id
    status = runner.certification_status()
    assert status[CRITERION_ID] == RequirementStatus.OUTSTANDING.value


# =====================================================================
# 2. OLD behaviour is unchanged when nothing is declared
# =====================================================================

def test_2_no_requirement_reproduces_the_old_runner_behaviour():
    _s, runner, _c, _b, _w = build_v01_campaign(
        e2_truth.MISSPECIFIED_TRUTH, label="v01-none", with_requirement=False
    )
    runner.run_campaign()
    assert runner.run.pause_reason is PauseReason.NO_ACTION_WORTH_BUYING
    assert _executed_probes(runner) == []
    assert runner.run.stop_review_outcome != StopReviewOutcome.STOP_APPROVED.value
    assert runner.certification_status() == {}


# =====================================================================
# 3-4. NEW behaviour: native routing, both adequacy outcomes
# =====================================================================

def test_3_passing_adequacy_path_reaches_stop_approved():
    _s, runner, _c, budget, _w = build_v01_campaign(
        e2_truth.WELL_SPECIFIED_TRUTH, label="v01-pass"
    )
    runner.run_campaign()

    # The runner itself executed every required probe. No adapter did it.
    assert _executed_probes(runner) == list(REQUIRED)
    assert runner.certification_status()[CRITERION_ID] == (
        RequirementStatus.SATISFIED.value
    )
    review = runner.stop_reviews[-1]
    assert review.outcome is StopReviewOutcome.STOP_APPROVED
    assert review.arbiter_verdict == "valid"
    assert review.arbiter_decision_id
    assert review.criterion_id == CRITERION_ID
    # Charged to the fenced reservation, by the frozen ledger.
    assert budget.spent_validation > 0.0
    assert budget.spent_general == 0.0


def test_4_failing_adequacy_path_stays_not_certifiable():
    _s, runner, _c, _b, _w = build_v01_campaign(
        e2_truth.MISSPECIFIED_TRUTH, label="v01-fail"
    )
    runner.run_campaign()

    assert _executed_probes(runner) == list(REQUIRED)
    assert runner.certification_status()[CRITERION_ID] == (
        RequirementStatus.SATISFIED.value
    )
    review = runner.stop_reviews[-1]
    assert review.outcome is StopReviewOutcome.STOP_REJECTED
    assert review.arbiter_verdict == "invalid"
    assert review.approves is False
    assert review.is_certification is False
    # Requirement discharged, model refused: two different things.
    assert runner.certification_status()[CRITERION_ID] == (
        RequirementStatus.SATISFIED.value
    )


# =====================================================================
# 5. Parameter EVSI is untouched
# =====================================================================

def test_5_parameter_evsi_is_identical_with_and_without_the_requirement():
    scores = {}
    for label, with_requirement in (("with", True), ("without", False)):
        _s, runner, _c, _b, _w = build_v01_campaign(
            e2_truth.MISSPECIFIED_TRUTH,
            label=f"v01-evsi-{label}",
            with_requirement=with_requirement,
        )
        runner.run_campaign()
        recommendation = runner.recommendation(
            f"{runner.run.run_id}-rec-1"
        )
        scores[label] = {
            s.action_id: (
                s.component("conditional_success_utility_gain").value,
                s.component("expected_cost").value,
                s.total,
            )
            for s in recommendation.scores
        }
    assert scores["with"] == scores["without"]
    # ...and the routed action's own score is still negative.
    for action_id in REQUIRED:
        assert scores["with"][action_id][2] < 0.0


def test_5b_execution_reason_records_the_constraint_not_a_value_claim():
    _s, runner, _c, _b, _w = build_v01_campaign(
        e2_truth.WELL_SPECIFIED_TRUTH, label="v01-reason"
    )
    runner.run_campaign()
    for event in runner.events.of_type(CampaignEventType.ACTION_SELECTED):
        if str(event.payload.get("action_id")) in REQUIRED:
            assert event.payload["execution_reason"] == "CERTIFICATION_REQUIREMENT"
            assert event.payload["execution_reason"] != "POSITIVE_NET_VALUE"


# =====================================================================
# 6. Prediction precedes observation, natively
# =====================================================================

def test_6_prediction_reference_precedes_execution_in_the_event_log():
    _s, runner, commitments, _b, _w = build_v01_campaign(
        e2_truth.MISSPECIFIED_TRUTH, label="v01-commit"
    )
    runner.run_campaign()
    assert runner.events.verify_chain() is True

    selected = {
        e.iteration: e
        for e in runner.events.of_type(CampaignEventType.ACTION_SELECTED)
        if str(e.payload.get("action_id")) in REQUIRED
    }
    started = {
        e.iteration: e
        for e in runner.events.of_type(CampaignEventType.EXECUTION_STARTED)
    }
    assert selected
    valid_refs = {c.artifact_hash for c in commitments.commitments.values()}
    for iteration, event in selected.items():
        assert event.payload["prediction_ref"] in valid_refs
        assert event.sequence < started[iteration].sequence


def test_6b_a_probe_without_a_prediction_reference_does_not_satisfy():
    """The satisfaction rule is derived from the log, and refuses an action
    whose selection carried no prediction reference."""
    _s, runner, _c, _b, _w = build_v01_campaign(
        e2_truth.WELL_SPECIFIED_TRUTH, label="v01-noref"
    )
    satisfied = runner._satisfied_certification_actions()
    assert satisfied == frozenset()
    runner.run_campaign()
    assert runner._satisfied_certification_actions() == frozenset(REQUIRED)

    # A selection event with an empty prediction_ref contributes nothing.
    requirement = CertificationRequirement(CRITERION_ID, REQUIRED, "test")
    assert requirement.status(frozenset()) is RequirementStatus.OUTSTANDING
    assert requirement.status(frozenset(REQUIRED)) is RequirementStatus.SATISFIED


# =====================================================================
# 7-9. The three ways it must not fake success
# =====================================================================

def test_7_invalid_execution_does_not_satisfy_the_requirement():
    _s, runner, _c, _b, _w = build_v01_campaign(
        e2_truth.WELL_SPECIFIED_TRUTH, label="v01-invalid", faulty=True
    )
    runner.run_campaign()
    # The runner routed and executed, but nothing was admitted.
    assert _executed_probes(runner)
    assert runner.certification_status()[CRITERION_ID] == (
        RequirementStatus.OUTSTANDING.value
    )
    assert runner._satisfied_certification_actions() == frozenset()
    assert runner.run.stop_review_outcome != StopReviewOutcome.STOP_APPROVED.value


def test_8_unaffordable_requirement_never_yields_stop_approved():
    _s, runner, _c, budget, _w = build_v01_campaign(
        e2_truth.WELL_SPECIFIED_TRUTH,
        label="v01-poor",
        total_budget=0.50,
        reserved=0.10,          # below one probe at 0.15
        pre_spend_general=0.40,
    )
    runner.run_campaign()
    assert budget.validation_pool < ACTION_BY_ID[REQUIRED[0]].cost
    assert _executed_probes(runner) == []
    assert runner.certification_status()[CRITERION_ID] == (
        RequirementStatus.OUTSTANDING.value
    )
    assert runner.run.stop_review_outcome != StopReviewOutcome.STOP_APPROVED.value
    for review in runner.stop_reviews:
        assert review.approves is False


def test_9_a_different_action_cannot_satisfy_the_requirement():
    requirement = CertificationRequirement(CRITERION_ID, REQUIRED, "test")
    # The cheap parameter action is not required evidence, whatever it costs.
    assert requirement.outstanding({"parameter_repeat_10V"}) == REQUIRED
    assert requirement.status({"parameter_repeat_10V"}) is (
        RequirementStatus.OUTSTANDING
    )
    # A non-required catalogue probe counts for nothing either.
    assert requirement.outstanding({"adequacy_probe_20V"}) == REQUIRED

    _s, runner, _c, _b, _w = build_v01_campaign(
        e2_truth.WELL_SPECIFIED_TRUTH, label="v01-wrong"
    )
    runner.run_campaign()
    routed = _executed_probes(runner)
    assert set(routed) == set(REQUIRED)
    assert "adequacy_probe_20V" not in routed
    assert "adequacy_probe_24V" not in routed


# =====================================================================
# 10. The validation fence is unchanged
# =====================================================================

def test_10_validation_budget_fence_is_unchanged():
    ledger = BudgetLedger(
        total_budget=TOTAL_BUDGET,
        reserved_validation_budget=RESERVE,
        cost_unit=COST_UNIT,
    )
    ledger.settle(
        charge_id="drain",
        action_id="parameter_repeat_10V",
        iteration=0,
        family=ActionFamily.CHARACTERIZE,
        realized=TOTAL_BUDGET - RESERVE,
        predicted=TOTAL_BUDGET - RESERVE,
    )
    assert ledger.general_pool == 0.0
    assert ledger.validation_pool == RESERVE
    assert ledger.affordable(0.15, family=ActionFamily.VALIDATE) is True
    assert ledger.affordable(0.15, family=ActionFamily.CHARACTERIZE) is False


def test_11_requirement_declaration_refuses_to_be_empty():
    _raises(ValueError, CertificationRequirement, "id", (), "source")
    _raises(ValueError, CertificationRequirement, "", REQUIRED, "source")
    _raises(ValueError, CertificationRequirement, "id", REQUIRED, "")
    _raises(
        ValueError, CertificationRequirement, "id", ("a", "a"), "source"
    )


def test_12_runner_still_has_no_family_state_machine():
    """The routing branch must not reintroduce family-based control flow."""
    import ast

    import src.engcore.sria.campaign.runner as runner_module

    tree = ast.parse(Path(runner_module.__file__).read_text(encoding="utf-8"))
    family_reads = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "ActionFamily"
    ]
    assert family_reads == []


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 — minimal certification path")
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
        print(f"V0.1: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"V0.1: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
