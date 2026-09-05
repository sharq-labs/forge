"""SRIA V0.1 M5.1 close-out — durability and authority regressions.

Runs under pytest, and standalone via
``python -m tests.test_sria_m51_closeout``.

Three defects were reproduced against the M5.1 code and are locked here. Each
test fails against the pre-close-out implementation:

1. ``CampaignRunner._obligation_state`` was not checkpointed, so a restart
   rewound the campaign's assurance record to "nothing has ever been assessed"
   and iteration 2's decision basis diverged from the uninterrupted run.
2. ``BeliefUpdateGateway.update_standing`` accepted a raised standing, so
   suspended evidence could be returned to active belief with a sentence of
   prose and no fresh assessment, decision or authorization.
3. ``CampaignRunner`` had no end-to-end stopping test — every stopping proof
   exercised the reviewer in isolation, so nothing checked that the runner
   actually routes a stop proposal through the Arbiter.
"""

from __future__ import annotations

import json
import sys

from src.engcore.sria import AdmissionError, EvidenceStatus
from src.engcore.sria.assurance.arbiter import AssuranceVerdict
from src.engcore.sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
)
from src.engcore.sria.campaign import (
    CampaignCheckpoint,
    CampaignEventType,
    ExecutionState,
    PauseReason,
    StopReviewOutcome,
    StoppingCriterion,
)
from src.engcore.sria.provenance import AssessmentProvenance

from tests.sria_m5_benchmark import build_assurance, critic_obligation
from tests.test_sria_m5_campaign import S1, S1_SEED, S5, S5_SEED, build_campaign
from tests.test_sria_m51_durability import CRITERION, ToyStoppingEvaluator


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


COSTS = {"a_theta": 1.0, "b_phi": 0.5}


# =====================================================================
# 1. Checkpoint durability across a MULTI-iteration restart
# =====================================================================

def _control_run():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs=COSTS, max_iterations=2, run_id="dur",
    )
    runner.run_campaign()
    return runner


def _restart_run():
    """Iteration 1, serialize, build a NEW runner, restore, iteration 2."""
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs=COSTS, max_iterations=2, run_id="dur",
    )
    arbiter = runner._arbiter
    runner.step()
    blob = json.dumps(runner.checkpoints.latest().to_dict())
    del runner

    fresh, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs=COSTS, max_iterations=2, run_id="dur",
        reuse=(gateway, arbiter, harness),
    )
    fresh.restore(CampaignCheckpoint.from_dict(json.loads(blob)))
    fresh.step()
    return fresh


def test_restart_reproduces_the_control_decision_basis():
    """A one-iteration restart hides this; the second iteration exposes it.

    Before the fix, ``_obligation_state`` was dropped on restore, so the
    iteration-2 snapshot carried an empty ``obligation_state`` and hashed
    differently from the uninterrupted run.
    """
    control = _control_run()
    restart = _restart_run()

    c2 = control.run.record(2)
    r2 = restart.run.record(2)
    assert c2 is not None and r2 is not None

    assert r2.snapshot_digest == c2.snapshot_digest
    assert r2.decision_basis_digest == c2.decision_basis_digest
    assert r2.selected_action_id == c2.selected_action_id

    # ...and the assurance record itself survived, which is why they match.
    assert control.snapshot(2).obligation_state == {"critic:numerical": True}
    assert restart.snapshot(2).obligation_state == {"critic:numerical": True}
    assert restart._obligation_state == control._obligation_state


def test_obligation_state_is_carried_on_the_checkpoint():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs=COSTS, max_iterations=2, run_id="dur2",
    )
    runner.step()
    checkpoint = runner.checkpoints.latest()
    assert checkpoint.obligation_state == {"critic:numerical": True}

    reloaded = CampaignCheckpoint.from_dict(
        json.loads(json.dumps(checkpoint.to_dict()))
    )
    assert reloaded.obligation_state == checkpoint.obligation_state
    assert reloaded.digest == checkpoint.digest


def test_a_restart_does_not_reopen_a_satisfied_obligation():
    """Checked immediately after restore, before the next iteration runs.

    Later iterations re-assess and would repopulate the state, hiding the loss.
    The moment that matters is the one where the liveness policy and the
    stopping review would consult it.
    """
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs=COSTS, max_iterations=2, run_id="dur3",
    )
    arbiter = runner._arbiter
    runner.step()
    assert runner._obligation_state == {"critic:numerical": True}
    blob = json.dumps(runner.checkpoints.latest().to_dict())
    del runner

    fresh, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs=COSTS, max_iterations=2, run_id="dur3",
        reuse=(gateway, arbiter, harness),
    )
    fresh.restore(CampaignCheckpoint.from_dict(json.loads(blob)))

    assert fresh._obligation_state == {"critic:numerical": True}
    unsatisfied = [
        o.obligation_id
        for o in fresh._obligations.obligations
        if not fresh._obligation_state.get(o.obligation_id, False)
    ]
    assert unsatisfied == []


# =====================================================================
# 2. Standing may fall, never rise
# =====================================================================

def _numerical_assessment(subject: str, aid: str) -> CriticAssessment:
    return CriticAssessment(
        assessment_id=aid,
        critic_id="closeout.numerical",
        critic_version="1",
        critic_class=CriticClass.NUMERICAL,
        subject_ref=subject,
        verdict=CriticVerdict.PASS,
        provenance=AssessmentProvenance(
            assessment_id=aid,
            critic_id="closeout.numerical",
            critic_version="1",
        ),
        checks=(
            CheckRecord(
                name="convergence_state",
                outcome=CriticVerdict.PASS,
                mandatory=True,
                detail="closeout fixture",
            ),
        ),
        summary="closeout fixture assessment",
    )


def _admitted(gateway, arbiter, evidence_id="ev-standing"):
    """Drive the full authorized path and return the admitted record."""
    from tests.test_sria_m31_semantics import evidence_for, good_result

    evidence = evidence_for(good_result(), evidence_id)   # already ASSESSED
    assessment = _numerical_assessment(evidence.evidence_id, f"{evidence_id}-a")
    decision = arbiter.decide(
        decision_id=f"{evidence_id}-d",
        subject_ref=evidence.evidence_id,
        assessments=(assessment,),
        obligations=critic_obligation(),
    )
    declaration = arbiter.authorize_admission(decision, evidence)
    admitted = evidence.admit(declaration)
    gateway.submit(admitted)
    return admitted


def test_suspended_evidence_cannot_be_reactivated_by_update_standing():
    """The reproduced bypass: prose + a lifecycle move restored active belief."""
    gateway, arbiter, _authority = build_assurance()
    admitted = _admitted(gateway, arbiter)
    assert len(gateway.belief) == 1

    suspended = admitted.suspend("withdrawn pending review", actor="reviewer")
    gateway.update_standing(suspended)
    assert len(gateway.belief) == 0

    reinstated = suspended.reinstate("looks fine to me", actor="anyone")
    assert reinstated.status is EvidenceStatus.ACCEPTED
    _raises(AdmissionError, gateway.update_standing, reinstated)
    assert len(gateway.belief) == 0
    assert gateway.belief.supports(admitted.belief_key) is False


def test_lowering_standing_still_needs_no_authorization():
    """The asymmetry must not become a lock on withdrawal."""
    gateway, arbiter, _authority = build_assurance()
    admitted = _admitted(gateway, arbiter, evidence_id="ev-lower")
    gateway.update_standing(admitted.suspend("reviewer pulled it"))
    assert len(gateway.belief) == 0
    # Invalidation is also a lowering, and also free.
    gateway.update_standing(
        admitted.suspend("x").invalidate("found a unit error")
    )
    assert len(gateway.belief) == 0


def test_reactivation_through_the_authorized_path_still_works():
    """Closing the bypass must not close the legitimate route."""
    gateway, arbiter, authority = build_assurance()
    admitted = _admitted(gateway, arbiter, evidence_id="ev-back")
    suspended = admitted.suspend("withdrawn")
    gateway.update_standing(suspended)
    assert len(gateway.belief) == 0

    assessment = _numerical_assessment(suspended.evidence_id, "ev-back-a2")
    fresh_decision = arbiter.decide(
        decision_id="ev-back-d2",
        subject_ref=suspended.evidence_id,
        assessments=(assessment,),
        obligations=critic_obligation(),
    )
    fresh = arbiter.authorize_admission(fresh_decision, suspended)
    gateway.submit(suspended.admit(fresh, actor="arbiter"))
    assert len(gateway.belief) == 1

    # And that fresh authorization is spent, like any other.
    assert (
        authority.verifies_authorization(
            fresh.authorization, subject_record_hash=suspended.record_hash
        )
        is False
    )


# =====================================================================
# 3. STOP_APPROVED through the CampaignRunner itself
# =====================================================================

def _stopping_campaign(verdict, *, criteria, evaluators, run_id):
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S5, seed_rows=S5_SEED,
        realized_costs={"a_theta": 5.0, "b_phi": 5.0},
        max_iterations=2, run_id=run_id,
    )
    runner._stopping_criteria = tuple(criteria)
    runner._stopping_evaluators = dict(evaluators)
    # A discharged obligation set is necessary context; the criterion is what
    # actually decides.
    runner._obligation_state = {"critic:numerical": True}
    runner.run_campaign()
    return runner


def test_runner_reaches_STOP_APPROVED_through_the_arbiter():
    """End to end: campaign state -> proposal -> criterion -> Arbiter -> approved."""
    runner = _stopping_campaign(
        CriticVerdict.PASS,
        criteria=(CRITERION,),
        evaluators={
            CRITERION.criterion_id: ToyStoppingEvaluator(
                CRITERION.criterion_id, CriticVerdict.PASS
            )
        },
        run_id="stop-ok",
    )
    assert runner.run.state is ExecutionState.PAUSED
    assert runner.run.pause_reason is PauseReason.NO_ACTION_WORTH_BUYING

    review = runner.stop_reviews[0]
    assert review.outcome is StopReviewOutcome.STOP_APPROVED
    assert runner.run.stop_review_outcome == "stop_approved"
    # It rests on a real Arbiter decision and names the criterion.
    assert review.arbiter_decision_id
    assert review.arbiter_verdict == "valid"
    assert review.criterion_id == CRITERION.criterion_id
    # ...and still is not a certification of scientific completeness.
    assert review.is_certification is False
    assert runner.run.is_certification is False

    reviewed = runner.events.last(CampaignEventType.STOP_REVIEWED)
    assert reviewed.payload["outcome"] == "stop_approved"
    assert reviewed.payload["arbiter_decision_id"] == review.arbiter_decision_id


def test_runner_cannot_self_certify_without_an_evaluable_criterion():
    """The negative case, driven by the same runner path."""
    runner = _stopping_campaign(
        CriticVerdict.PASS, criteria=(), evaluators={}, run_id="stop-none"
    )
    review = runner.stop_reviews[0]
    assert review.outcome is StopReviewOutcome.STOP_NOT_ASSESSED
    assert review.arbiter_decision_id == ""
    assert any(
        "no independently declared stopping criterion" in r for r in review.reasons
    )

    # A registered criterion with no evaluator is equally not-assessed.
    unevaluable = _stopping_campaign(
        CriticVerdict.PASS,
        criteria=(CRITERION,), evaluators={}, run_id="stop-noeval",
    )
    assert (
        unevaluable.stop_reviews[0].outcome is StopReviewOutcome.STOP_NOT_ASSESSED
    )


def test_runner_stop_is_rejected_when_the_criterion_fails():
    runner = _stopping_campaign(
        CriticVerdict.FAIL,
        criteria=(CRITERION,),
        evaluators={
            CRITERION.criterion_id: ToyStoppingEvaluator(
                CRITERION.criterion_id, CriticVerdict.FAIL
            )
        },
        run_id="stop-reject",
    )
    review = runner.stop_reviews[0]
    assert review.outcome is StopReviewOutcome.STOP_REJECTED
    assert review.arbiter_verdict == "invalid"


# =====================================================================
# 4. Documented limitation: ValidationLevel obligations are unevaluable
# =====================================================================

def test_validation_level_obligations_are_unevaluable_and_fail_closed():
    """An accepted M5.1 limitation, locked so it cannot silently become a pass.

    A charter's ``confidence_requirements`` become ``validation_level:*``
    obligations, and M3 has no machinery to evaluate a ValidationLevel. The
    Arbiter therefore records them as unsatisfied *whatever* the critics say —
    it cannot certify what it cannot assess. That is the conservative
    direction: such a campaign can never reach VALID or STOP_APPROVED.

    Evaluating ValidationLevel belongs to the next scientific phase. Until then
    this test exists so the limitation is a decision, not a surprise.
    """
    from src.engcore.scientific.results.validation import ValidationLevel
    from src.engcore.sria import (
        CampaignCharter,
        ConfidenceRequirement,
        TerminalDecision,
    )
    from src.engcore.sria.assurance.obligations import obligations_from_charter

    charter = CampaignCharter(
        campaign_id="limitation",
        terminal_decisions=(
            TerminalDecision(decision_id="d", statement="pick", options=("a", "b")),
        ),
        utility_reference="u/1",
        confidence_requirements=(
            ConfidenceRequirement(
                requirement_id="qoi_confidence",
                description="the QoI must reach benchmark validation",
                required_levels=(ValidationLevel.BENCHMARK_VALIDATED,),
            ),
        ),
    )
    obligations = obligations_from_charter(charter)
    target = obligations.obligations[0].target
    assert target == "validation_level:benchmark_validated"

    _g, arbiter, _a = build_assurance()
    # Even a critic that explicitly passes a check of exactly that name cannot
    # satisfy it — the Arbiter refuses to certify a level it cannot evaluate.
    satisfying_attempt = _numerical_assessment("ev-1", "a-lim")
    satisfying_attempt = CriticAssessment(
        assessment_id="a-lim",
        critic_id="closeout.numerical",
        critic_version="1",
        critic_class=CriticClass.NUMERICAL,
        subject_ref="ev-1",
        verdict=CriticVerdict.PASS,
        provenance=AssessmentProvenance(
            assessment_id="a-lim",
            critic_id="closeout.numerical",
            critic_version="1",
        ),
        checks=(
            CheckRecord(
                name=target,
                outcome=CriticVerdict.PASS,
                mandatory=True,
                detail="a critic claiming it evaluated the level",
            ),
        ),
        summary="attempt to satisfy a validation-level obligation",
    )
    decision = arbiter.decide(
        decision_id="d-lim",
        subject_ref="ev-1",
        assessments=(satisfying_attempt,),
        obligations=obligations,
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert decision.unmet_obligations
    assert any("validation_level" in o for o in decision.unmet_obligations)

    # The M5 campaign path is unaffected: its charter declares none of these.
    from tests.sria_m5_benchmark import toy_charter

    assert toy_charter().confidence_requirements == ()


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M5.1 — close-out regressions")
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
        print(f"M5.1 close-out: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M5.1 close-out: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
