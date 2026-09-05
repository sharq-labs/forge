"""SRIA V0.1 M5.1 — campaign safety and durability.

Runs under pytest, and standalone via
``python -m tests.test_sria_m51_durability``.

Four corrections, each reproduced as a defect first:

* stopping approval was minted by a generic campaign component from discharged
  obligations alone; it is now Arbiter-owned and criterion-driven;
* a realized overrun was *refused* by the ledger rather than recorded;
* resume rebuilt the decision artifacts instead of loading them;
* durability was only ever exercised inside one live Python object.

The restart tests here construct a genuinely new runner from JSON alone — no
shared objects except the world the effects act on, so a duplicate would show
up on the same counters.
"""

from __future__ import annotations

import dataclasses
import json
import sys

from src.engcore.sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    FindingImpact,
    Severity,
)
from src.engcore.sria.provenance import AssessmentProvenance
from src.engcore.sria.campaign import (
    ArbiterStoppingReview,
    BudgetLedger,
    CampaignCheckpoint,
    CampaignEventType,
    CampaignRunner,
    ExecutionState,
    IterationPlan,
    PauseReason,
    StopProposal,
    StopReview,
    StopReviewOutcome,
    StoppingCriterion,
)
from src.engcore.sria.decision import ActionFamily

from tests.sria_m5_benchmark import (
    InterruptedCampaign,
    build_assurance,
    critic_obligation,
    generators_for,
    toy_budget,
    toy_charter,
)
from tests.test_sria_m5_campaign import S1, S1_ACTIONS, S1_SEED, build_campaign


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


PROPOSAL = StopProposal(
    proposal_id="p1", campaign_id="m5-campaign", run_id="r1", iteration=1,
    economic_reason="no evaluated candidate scored above zero",
)


def review_with(arbiter, **kwargs):
    base = dict(
        review_id="rev1",
        obligations=critic_obligation(),
        obligation_state={"critic:numerical": True},
        terminal_objective_available=True,
    )
    base.update(kwargs)
    return ArbiterStoppingReview(arbiter).review(PROPOSAL, **base)


class ToyStoppingEvaluator:
    """Evaluates one registered criterion. Supplied by the campaign."""

    def __init__(self, criterion_id: str, verdict: CriticVerdict):
        self.criterion_id = criterion_id
        self.critic_id = "m5.stopping_evaluator"
        self.critic_version = "1"
        self._verdict = verdict

    def evaluate(self, context, *, assessment_id: str) -> CriticAssessment:
        # A criterion the campaign can show is *not* met is an invalidating
        # finding, which is what lets the Arbiter reject rather than abstain.
        findings = ()
        if self._verdict is CriticVerdict.FAIL:
            findings = (
                Finding(
                    code="stopping.criterion_unmet",
                    severity=Severity.BLOCKING,
                    category="process",
                    message="the declared stopping criterion is not satisfied",
                    check_name=self.criterion_id,
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                ),
            )
        return CriticAssessment(
            findings=findings,
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=CriticClass.PROCESS,
            subject_ref=PROPOSAL.proposal_id,
            verdict=self._verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id, critic_id=self.critic_id,
                critic_version=self.critic_version,
            ),
            checks=(
                CheckRecord(
                    name=self.criterion_id,
                    outcome=self._verdict,
                    mandatory=True,
                    detail="declared charter stopping criterion",
                ),
            ),
            summary=f"stopping criterion evaluated to {self._verdict.value}",
        )


CRITERION = StoppingCriterion(
    criterion_id="theta_confidence_at_least_0_9",
    statement="stop once confidence in theta reaches 0.9",
    source="m5 toy charter, clause 4",
    evaluator_id="m5.stopping_evaluator",
    evaluator_version="1",
)


# =====================================================================
# 1. Stopping authority — A through E
# =====================================================================

def test_A_stop_proposal_alone_cannot_yield_approval():
    """Non-positive VoI is a statement about prices, not about science."""
    _g, arbiter, _a = build_assurance()
    review = review_with(arbiter, obligation_state={}, obligations=critic_obligation())
    assert review.outcome is not StopReviewOutcome.STOP_APPROVED
    assert review.arbiter_decision_id == ""


def test_B_discharged_obligations_alone_cannot_yield_approval():
    """The M5 defect, reproduced: this used to return STOP_APPROVED."""
    _g, arbiter, _a = build_assurance()
    review = review_with(arbiter)          # every obligation satisfied
    assert review.unmet_obligations == ()
    assert review.terminal_objective_available is True
    assert review.outcome is StopReviewOutcome.STOP_NOT_ASSESSED
    assert any("no independently declared stopping criterion" in r
               for r in review.reasons)
    assert any("neither is evidence" in r for r in review.reasons)
    assert any("expected-regret certification is not implemented" in r
               for r in review.reasons)


def test_C_missing_stopping_criterion_gives_not_assessed():
    _g, arbiter, _a = build_assurance()
    # No criteria at all.
    assert review_with(arbiter).outcome is StopReviewOutcome.STOP_NOT_ASSESSED
    # A criterion with no evaluator.
    review = review_with(arbiter, criteria=(CRITERION,))
    assert review.outcome is StopReviewOutcome.STOP_NOT_ASSESSED
    assert any("no evaluator" in r for r in review.reasons)
    # An evaluator that cannot reach a verdict.
    review = review_with(
        arbiter,
        criteria=(CRITERION,),
        evaluators={
            CRITERION.criterion_id: ToyStoppingEvaluator(
                CRITERION.criterion_id, CriticVerdict.NOT_ASSESSED
            )
        },
    )
    assert review.outcome is StopReviewOutcome.STOP_NOT_ASSESSED
    assert any("UNKNOWN is the honest answer" in r for r in review.reasons)


def test_D_an_evaluable_charter_criterion_may_be_arbiter_approved():
    _g, arbiter, _a = build_assurance()
    review = review_with(
        arbiter,
        criteria=(CRITERION,),
        evaluators={
            CRITERION.criterion_id: ToyStoppingEvaluator(
                CRITERION.criterion_id, CriticVerdict.PASS
            )
        },
    )
    assert review.outcome is StopReviewOutcome.STOP_APPROVED
    assert review.arbiter_decision_id                  # rests on a real decision
    assert review.arbiter_verdict == "valid"
    assert review.criterion_id == CRITERION.criterion_id
    assert review.is_certification is False
    assert any("not a general certification" in r for r in review.reasons)

    # A criterion the Arbiter finds unsatisfied is rejected, not ignored.
    rejected = review_with(
        arbiter,
        review_id="rev2",
        criteria=(CRITERION,),
        evaluators={
            CRITERION.criterion_id: ToyStoppingEvaluator(
                CRITERION.criterion_id, CriticVerdict.FAIL
            )
        },
    )
    assert rejected.outcome is StopReviewOutcome.STOP_REJECTED


def test_E_no_campaign_component_can_issue_final_stopping_approval():
    """Structural: approval without an Arbiter decision cannot be constructed."""
    _raises(
        ValueError,
        StopReview,
        review_id="r", proposal_id="p",
        outcome=StopReviewOutcome.STOP_APPROVED,
        terminal_objective_available=True,
        criterion_id="c",
        reasons=("looks finished to me",),
    )
    # ...nor without a named criterion.
    _raises(
        ValueError,
        StopReview,
        review_id="r", proposal_id="p",
        outcome=StopReviewOutcome.STOP_APPROVED,
        terminal_objective_available=True,
        arbiter_decision_id="d1",
        reasons=("obligations are discharged",),
    )
    # The reviewer cannot exist without an Arbiter.
    _raises(TypeError, ArbiterStoppingReview, object())

    # And the loop's own run object never certifies.
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    runner.run_campaign()
    assert runner.run.is_certification is False
    assert not hasattr(runner, "approve_stop")
    assert not hasattr(CampaignRunner, "approve_stop")


def test_E2_the_runner_routes_stopping_through_its_arbiter():
    from src.engcore.sria.campaign import runner as runner_module

    runner, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    assert isinstance(runner._stopping, ArbiterStoppingReview)
    assert runner._stopping._arbiter is runner._arbiter
    # No fallback path constructs a reviewer without one.
    source = __import__("pathlib").Path(
        runner_module.__file__
    ).read_text(encoding="utf-8")
    assert "ArbiterStoppingReview(arbiter)" in source


# =====================================================================
# 2. Budget overrun accounting
# =====================================================================

def test_predicted_fits_but_realized_overruns_is_recorded_and_halts():
    """remaining 2, predicted 1, realized 5 -> charged 5, overrun 3, halt."""
    runner, harness, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows={"theta": (1.0, 1.0, 1.0), "phi": (0.5, 0.5, 0.5)},
        realized_costs={"a_theta": 5.0, "b_phi": 0.5},
        budget=BudgetLedger(total_budget=2.0, cost_unit="hour"),
        max_iterations=2,
    )
    runner.run_campaign()

    record = runner.run.iterations[0]
    assert record.predicted_cost == 1.0            # it fitted when selected
    assert record.realized_cost == 5.0             # what actually happened
    assert record.cost_overrun == 4.0

    ledger = runner.budget
    assert ledger.spent_total == 5.0               # fully recorded
    assert ledger.overrun == 3.0                   # past the declared 2.0
    assert ledger.is_overrun is True
    assert len(ledger.charges) == 1

    assert runner.run.state is ExecutionState.PAUSED
    assert runner.run.pause_reason is PauseReason.BUDGET_OVERRUN
    assert harness.executor_impl.calls == ["a_theta"]   # nothing further ran

    event = runner.events.last(CampaignEventType.BUDGET_UPDATED, iteration=1)
    assert event.payload["predicted"] == 1.0
    assert event.payload["realized"] == 5.0
    assert event.payload["overrun"] == 4.0
    assert event.payload["budget_overrun"] == 3.0

    # The decision itself was not retroactively altered.
    recommendation = runner.recommendation(record.recommendation_id)
    scored = {s.action_id: s.total for s in recommendation.scores}
    assert abs(scored["a_theta"] - 3.0) < 1e-9


def test_validation_reservation_stays_truthful_through_an_overrun():
    ledger = BudgetLedger(total_budget=6.0, reserved_validation_budget=2.0)
    ledger.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=9.0, predicted=1.0,
    )
    assert ledger.spent_general == 9.0
    assert ledger.spent_validation == 0.0
    assert ledger.validation_pool == 2.0           # untouched by the overrun
    assert ledger.overrun == 3.0
    assert ledger.charges[0].from_validation_reservation == 0.0


def test_budget_guarantee_language_is_honest_in_the_loop():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 5.0},
        budget=BudgetLedger(total_budget=2.0, cost_unit="hour"),
        max_iterations=1,
    )
    runner.run_campaign()
    paused = runner.events.last(CampaignEventType.CAMPAIGN_PAUSED, iteration=1)
    assert "no executor-enforced resource cap" in paused.payload["detail"]
    assert "cannot be prevented mid-run" in paused.payload["detail"]


# =====================================================================
# 3. Exact iteration artifacts are persisted before execution
# =====================================================================

def test_the_plan_is_persisted_before_anything_executes():
    runner, harness, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    harness.crash_at = "calibrate"
    _raises(InterruptedCampaign, runner.step)

    # A checkpoint carrying the plan exists, and it predates execution.
    with_plan = [c for c in runner.checkpoints.history if c.plan is not None]
    assert with_plan
    first_plan = with_plan[0]
    assert first_plan.plan.action_id == "a_theta"
    assert first_plan.plan.iteration == 1
    assert first_plan.plan.predicted_cost == 1.0
    assert first_plan.plan.snapshot.digest == runner.snapshot(1).digest
    assert first_plan.plan.manifest.manifest_digest == (
        runner.recommendation(first_plan.plan.recommendation.recommendation_id)
        .dependency_manifest.manifest_digest
    )
    # It was written before the execution event.
    assert not first_plan.events.has(
        CampaignEventType.EXECUTION_COMPLETED, iteration=1
    )


def test_the_plan_round_trips_and_preserves_m44_coherence():
    from src.engcore.sria.decision import CoherenceStatus, check_state_coherence

    runner, harness, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    harness.crash_at = "calibrate"
    _raises(InterruptedCampaign, runner.step)

    stored = next(c for c in runner.checkpoints.history if c.plan is not None)
    reloaded = CampaignCheckpoint.from_dict(
        json.loads(json.dumps(stored.to_dict()))
    )
    plan = reloaded.plan
    assert plan.digest == stored.plan.digest
    assert plan.action_id == "a_theta"
    assert plan.snapshot.digest == stored.plan.snapshot.digest
    assert plan.snapshot.pins_decision_basis is True
    # The stored snapshot and stored manifest still agree — coherence survives
    # a restart because neither was rebuilt.
    report = check_state_coherence(plan.snapshot, plan.manifest)
    assert report.status is CoherenceStatus.COHERENT
    assert plan.recommendation.is_state_coherent is True


def test_a_plan_missing_an_artifact_is_refused():
    for missing in ("snapshot", "manifest", "recommendation", "action"):
        kwargs = dict(
            iteration=1, snapshot=object(), manifest=object(),
            recommendation=object(), action=object(),
        )
        kwargs[missing] = None
        _raises(ValueError, IterationPlan, **kwargs)


# =====================================================================
# 4. Genuine process-restart durability
# =====================================================================

def restart_from(checkpoint_json, *, gateway, arbiter, harness, max_iterations=1):
    """Build a brand-new runner from JSON alone, as a new process would."""
    checkpoint = CampaignCheckpoint.from_dict(json.loads(checkpoint_json))
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        max_iterations=max_iterations,
        reuse=(gateway, arbiter, harness),
    )
    runner.restore(checkpoint)
    return runner


#: Where the process dies, covering the windows the brief names:
#:   "run"       — action selected, solver finished, campaign died before
#:                 recording it (execution completed before downstream work)
#:   "assess"    — execution recorded and budget charged, before evidence
#:   "calibrate" — evidence admitted, before the iteration checkpoint
#:   None        — no interruption, as a control
INTERRUPTION_WINDOWS = ("run", "assess", "calibrate", None)


def test_restart_at_every_interruption_window_duplicates_nothing():
    """Crash at four points; each time a *new* object resumes from JSON only."""
    for window in INTERRUPTION_WINDOWS:
        runner, harness, gateway = build_campaign(
            actions_by_iteration=S1, seed_rows=S1_SEED,
            realized_costs={"a_theta": 1.0}, max_iterations=1,
        )
        arbiter = runner._arbiter
        if window == "run":
            harness.executor_impl.crash_after_run = True
        else:
            harness.crash_at = window or ""
        if window is None:
            runner.step()
        else:
            _raises(InterruptedCampaign, runner.step)

        # Everything the restarted process may see: one JSON blob.
        blob = json.dumps(runner.checkpoints.latest().to_dict())
        harness.crash_at = ""
        harness.executor_impl.crash_after_run = False
        del runner                              # the old object is gone

        resumed = restart_from(
            blob, gateway=gateway, arbiter=arbiter, harness=harness
        )
        resumed.step()

        assert harness.executor_impl.calls == ["a_theta"], window
        assert len(gateway.belief) == 1, window
        assert len(harness.memory) == 1, window
        assert resumed.budget.spent_total == 1.0, window
        assert len(resumed.budget.charges) == 1, window
        assert resumed.events.verify_chain() is True, window
        assert len(
            resumed.events.of_type(CampaignEventType.EVIDENCE_ADMITTED)
        ) == 1, window
        assert len(
            resumed.events.of_type(CampaignEventType.CALIBRATION_UPDATED)
        ) == 1, window


def test_restart_continues_the_stored_decision_rather_than_re_deciding():
    """The M5 defect: a resumed iteration used to re-rank and pick differently.

    Belief moves the moment this iteration's own evidence is admitted, so a
    fresh ranking at that point genuinely prefers a different action — and the
    campaign would execute two actions for one decision.
    """
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5}, max_iterations=1,
    )
    arbiter = runner._arbiter
    harness.crash_at = "calibrate"              # after admission
    _raises(InterruptedCampaign, runner.step)

    # Belief has already moved, so a fresh ranking would prefer b_phi.
    assert harness.confidences["theta"] == 0.9
    blob = json.dumps(runner.checkpoints.latest().to_dict())
    harness.crash_at = ""

    resumed = restart_from(blob, gateway=gateway, arbiter=arbiter, harness=harness)
    assert resumed.plan is not None
    assert resumed.plan.action_id == "a_theta"
    resumed.step()

    assert harness.executor_impl.calls == ["a_theta"]
    assert "b_phi" not in harness.executor_impl.calls
    assert resumed.run.iterations[0].selected_action_id == "a_theta"


def test_restart_without_a_stored_plan_refuses_rather_than_re_deciding():
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    arbiter = runner._arbiter
    harness.crash_at = "calibrate"
    _raises(InterruptedCampaign, runner.step)

    stripped = dataclasses.replace(runner.checkpoints.latest(), plan=None)
    harness.crash_at = ""
    resumed = restart_from(
        json.dumps(stripped.to_dict()),
        gateway=gateway, arbiter=arbiter, harness=harness,
    )
    assert resumed.plan is None
    resumed.step()
    assert resumed.run.state is ExecutionState.PAUSED
    assert resumed.run.pause_reason is PauseReason.OPERATOR_REQUESTED
    paused = resumed.events.last(CampaignEventType.CAMPAIGN_PAUSED, iteration=1)
    assert "not a resume" in paused.payload["detail"]
    assert harness.executor_impl.calls == ["a_theta"]


def test_a_completed_run_is_recovered_not_repeated():
    """Solver finished, campaign died before recording it -> fetch, don't rerun."""
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    arbiter = runner._arbiter
    harness.executor_impl.crash_after_run = True
    _raises(InterruptedCampaign, runner.step)
    assert harness.executor_impl.calls == ["a_theta"]
    assert runner.budget.spent_total == 0.0        # never got to settle

    blob = json.dumps(runner.checkpoints.latest().to_dict())
    harness.executor_impl.crash_after_run = False
    resumed = restart_from(blob, gateway=gateway, arbiter=arbiter, harness=harness)
    resumed.step()

    assert harness.executor_impl.calls == ["a_theta"], "the solver must not re-run"
    recovered = [
        e for e in resumed.events.of_type(CampaignEventType.EXECUTION_COMPLETED)
        if e.payload.get("recovered")
    ]
    assert recovered, "the completed run should have been retrieved"
    assert resumed.budget.spent_total == 1.0
    assert len(gateway.belief) == 1


def test_unrecoverable_execution_pauses_for_an_operator():
    """If completion cannot be determined, never re-run. Ask a human."""
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    arbiter = runner._arbiter
    harness.executor_impl.crash_after_run = True
    _raises(InterruptedCampaign, runner.step)

    blob = json.dumps(runner.checkpoints.latest().to_dict())
    harness.executor_impl.crash_after_run = False
    # The executor cannot say whether the operation finished — a restarted
    # worker with no shared result store.
    harness.executor_impl.completed.clear()

    resumed = restart_from(blob, gateway=gateway, arbiter=arbiter, harness=harness)
    resumed.step()

    assert resumed.run.state is ExecutionState.PAUSED
    assert resumed.run.pause_reason is PauseReason.OPERATOR_REQUESTED
    paused = resumed.events.last(CampaignEventType.CAMPAIGN_PAUSED, iteration=1)
    assert "cannot be determined" in paused.payload["detail"]
    assert "spend the budget twice" in paused.payload["detail"]
    assert harness.executor_impl.calls == ["a_theta"]   # no automatic rerun
    assert resumed.budget.spent_total == 0.0
    assert len(gateway.belief) == 0


# =====================================================================
# 5. Effect identity binds enough context
# =====================================================================

def test_effect_keys_bind_run_iteration_kind_and_action_content():
    runner, harness, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
    )
    runner.run_campaign()
    keys = list(runner.effects.applied)
    assert keys
    for key in keys:
        run_id, iteration, kind, subject = key.split(":", 3)
        assert run_id == runner.run.run_id
        assert iteration in {"1", "2"}
        assert kind in {"execute", "charge", "evidence", "admit", "calibrate"}
        assert subject


def test_a_reused_action_id_with_different_content_is_a_different_effect():
    """Iteration scoping plus a content digest: no accidental collision."""
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0}, max_iterations=1,
    )
    original = next(a for a in S1_ACTIONS if a.action_id == "a_theta")
    same_id_different_content = dataclasses.replace(
        original,
        action=dataclasses.replace(
            original.action, metadata={**original.action.metadata,
                                       "reliability": 0.55},
        ),
    )
    assert same_id_different_content.action_id == original.action_id
    assert runner._effect_subject(original) != runner._effect_subject(
        same_id_different_content
    )
    # ...and the same content in two iterations still yields distinct keys.
    key1 = runner.effects.key(
        "run", 1, "execute", runner._effect_subject(original)
    )
    key2 = runner.effects.key(
        "run", 2, "execute", runner._effect_subject(original)
    )
    assert key1 != key2


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M5.1 — campaign safety / durability")
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
        print(f"M5.1: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M5.1: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
