"""BR-15 F-9: a restored campaign's stop-review state must be what its own event log says.

``CampaignRunner.restore`` checked the obligation state and each iteration's decisions against the event log, but not
``run.stop_review_outcome`` or a stop-proposing iteration's ``detail``. A checkpoint edited to say ``stop_approved``
over a log whose STOP_REVIEWED entry says ``stop_rejected`` was adopted as it was.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.sria.assurance.assessment import CriticVerdict
from engcore.sria.campaign import CampaignCheckpoint, StopReviewOutcome
from engcore.sria.campaign.checkpoint import ResumeViolation

from tests.test_sria_m51_closeout import _stopping_campaign
from tests.test_sria_m51_durability import CRITERION, ToyStoppingEvaluator


def _rejected():
    runner = _stopping_campaign(
        CriticVerdict.FAIL, criteria=(CRITERION,),
        evaluators={CRITERION.criterion_id: ToyStoppingEvaluator(CRITERION.criterion_id, CriticVerdict.FAIL)},
        run_id="br15-f9")
    assert runner.stop_reviews[0].outcome is StopReviewOutcome.STOP_REJECTED
    assert runner.run.stop_review_outcome == "stop_rejected"
    return runner


def _checkpoint(runner, run):
    return CampaignCheckpoint(run=run, events=runner.events, budget=runner.budget, effects=runner.effects,
                              plan=None, obligation_state=dict(runner._obligation_state))


def test_positive_control_an_honest_checkpoint_restores():
    runner = _rejected()
    assert runner.restore(_checkpoint(runner, runner.run)).stop_review_outcome == "stop_rejected"


def test_a_checkpoint_claiming_an_approval_the_log_does_not_record_is_refused():
    runner = _rejected()
    forged = dataclasses.replace(runner.run, stop_review_outcome=StopReviewOutcome.STOP_APPROVED.value)
    with pytest.raises(ResumeViolation, match="stop review"):
        runner.restore(_checkpoint(runner, forged))
    assert runner.run.stop_review_outcome == "stop_rejected"


def test_an_iteration_record_rewritten_to_an_approval_is_refused():
    runner = _rejected()
    iterations = tuple(dataclasses.replace(it, detail=StopReviewOutcome.STOP_APPROVED.value) if it.stop_proposed else it
                       for it in runner.run.iterations)
    assert any(it.stop_proposed for it in iterations)
    with pytest.raises(ResumeViolation, match="stop review"):
        runner.restore(_checkpoint(runner, dataclasses.replace(runner.run, iterations=iterations)))
