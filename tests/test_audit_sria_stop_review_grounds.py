"""Audit stream sria follow-up — the grounds a stop review may stand on.

``ArbiterStoppingReview.review`` took ``obligation_state`` from its caller and
treated it as the campaign's discharged obligations. The runner passed its own
derived state, but any direct caller could pass ``{"critic:numerical": True}``
and have the review proceed as though every obligation had been assessed and
met. The review now takes Arbiter decisions and keeps only those its own
Arbiter issued, about evidence, for this campaign, under these obligations; a
caller may still report an obligation unmet, which can only lower standing.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.sria.assurance import (
    AssuranceVerdict,
    CriticClass,
    CriticVerdict,
    obligations_from_charter,
)
from engcore.sria.campaign import ArbiterStoppingReview, StopProposal, StopReviewOutcome

from tests.sria_m5_benchmark import (
    TOY_CRITIC_ID,
    build_assurance,
    critic_obligation,
    toy_charter,
    toy_evidence,
)
from tests.test_sria_m51_durability import CRITERION, ToyStoppingEvaluator

PROPOSAL = StopProposal(
    proposal_id="p-grounds", campaign_id="m5-campaign", run_id="r", iteration=1
)


def _stack():
    evaluator = ToyStoppingEvaluator(CRITERION.criterion_id, CriticVerdict.PASS)
    _g, arbiter, _a = build_assurance(critics=(evaluator,))
    return arbiter, evaluator


def _decision(arbiter, tag, *, verdict=CriticVerdict.PASS, obligations=None):
    evidence = toy_evidence(f"ev-{tag}")
    assessment = arbiter.run_critic(
        TOY_CRITIC_ID, evidence, subject=evidence, assessment_id=f"{tag}-a",
        declared_convergence=verdict,
    )
    return arbiter.decide(
        decision_id=f"{tag}-d", evidence=evidence, assessments=(assessment,),
        obligations=obligations or critic_obligation(),
    )


def _review(arbiter, evaluator, review_id, **kwargs):
    return ArbiterStoppingReview(arbiter).review(
        PROPOSAL,
        review_id=review_id,
        obligations=critic_obligation(),
        terminal_objective_available=True,
        criteria=(CRITERION,),
        evaluators={CRITERION.criterion_id: evaluator},
        **kwargs,
    )


def test_grounds_a_caller_supplied_obligation_state_is_not_accepted():
    arbiter, evaluator = _stack()
    with pytest.raises(TypeError):
        _review(arbiter, evaluator, "state", obligation_state={"critic:numerical": True})


def test_grounds_genuine_decisions_from_the_reviewing_arbiter_support_approval():
    arbiter, evaluator = _stack()
    decision = _decision(arbiter, "genuine")
    assert decision.verdict is AssuranceVerdict.VALID
    review = _review(arbiter, evaluator, "genuine", assurance_decisions=(decision,))
    assert review.outcome is StopReviewOutcome.STOP_APPROVED, review.reasons


def test_grounds_a_hand_built_decision_is_ignored():
    arbiter, evaluator = _stack()
    genuine = _decision(arbiter, "template")
    forged = dataclasses.replace(genuine, decision_id="forged-d")
    review = _review(arbiter, evaluator, "forged", assurance_decisions=(forged,))
    assert review.outcome is not StopReviewOutcome.STOP_APPROVED
    assert review.unassessed_aspects == ("critic:numerical",)
    assert review.arbiter_decision_id == ""


def test_grounds_a_decision_from_another_arbiter_is_ignored():
    arbiter, evaluator = _stack()
    _g, other, _a = build_assurance()
    foreign = _decision(other, "foreign")
    assert foreign.verdict is AssuranceVerdict.VALID
    review = _review(arbiter, evaluator, "foreign", assurance_decisions=(foreign,))
    assert review.outcome is not StopReviewOutcome.STOP_APPROVED
    assert review.unassessed_aspects == ("critic:numerical",)


def test_grounds_a_decision_under_another_policy_is_ignored():
    arbiter, evaluator = _stack()
    other_policy = obligations_from_charter(
        toy_charter(), required_critics=(CriticClass.NUMERICAL,),
        required_checks=("convergence_state",),
    )
    decision = _decision(arbiter, "policy", obligations=other_policy)
    assert decision.verdict is AssuranceVerdict.VALID
    review = _review(arbiter, evaluator, "policy", assurance_decisions=(decision,))
    assert review.outcome is not StopReviewOutcome.STOP_APPROVED
    assert review.unassessed_aspects == ("critic:numerical",)


def test_grounds_the_latest_decision_about_an_obligation_governs():
    arbiter, evaluator = _stack()
    passed = _decision(arbiter, "first")
    doubted = _decision(arbiter, "second", verdict=CriticVerdict.INCONCLUSIVE)
    review = _review(arbiter, evaluator, "latest", assurance_decisions=(passed, doubted))
    assert review.outcome is StopReviewOutcome.STOP_REJECTED
    assert review.unmet_obligations == ("critic:numerical",)


def test_grounds_a_caller_may_only_lower_standing():
    arbiter, evaluator = _stack()
    decision = _decision(arbiter, "lower")
    review = _review(
        arbiter, evaluator, "lower",
        assurance_decisions=(decision,), reported_unmet=("critic:numerical",),
    )
    assert review.outcome is StopReviewOutcome.STOP_REJECTED
