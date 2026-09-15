"""Audit stream sria — SRIA-TRUST-02: the assurance policy is bound to the charter.

``CampaignRunner`` accepted a charter and an obligation set independently.
Probe E3: under a strict charter a caller supplied ``ObligationSet(campaign_id=
"camp-WEAK", (critic:numerical,))`` — a hand-built policy from another campaign —
and the Arbiter's decisions carried ``campaign_id="camp-WEAK"`` with nothing
recording which policy had been applied.
"""

from __future__ import annotations

import pytest

from engcore.sria import CampaignCharter, TerminalDecision
from engcore.sria.assurance import (
    CriticClass,
    CriticVerdict,
    ObligationKind,
    ObligationSet,
    ValidationObligation,
    obligations_from_charter,
)
from engcore.sria.campaign import (
    ArbiterStoppingReview,
    CampaignRunner,
    StopProposal,
    StopReviewOutcome,
)
from engcore.sria.charter import CharterAmendment

from engcore.sria.assurance import NumericalCritic
from engcore.sria.campaign.events import CampaignEventType

import tests.test_sria_m3_assurance as T
from tests.test_audit_sria_assurance_binding import (
    _budget,
    _domain_critic,
    _honest_assessments,
    _stack,
    _voltage_evidence,
)
from tests.sria_m5_benchmark import (
    build_assurance,
    critic_obligation,
    toy_budget,
    toy_charter,
)
from tests.test_sria_m5_campaign import S1, S1_SEED, build_campaign
from tests.test_sria_m51_durability import CRITERION, ToyStoppingEvaluator


def _numerical_only(campaign_id="camp-WEAK", source="me") -> ObligationSet:
    return ObligationSet(
        campaign_id=campaign_id,
        obligations=(
            ValidationObligation(
                obligation_id="critic:numerical",
                kind=ObligationKind.REQUIRED_CRITIC,
                target="numerical",
                source=source,
            ),
        ),
    )


def _runner_with(*, charter, obligations, charter_version=None):
    template, harness, gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5}, max_iterations=1,
    )
    kwargs = dict(
        run_id="policy",
        charter=charter,
        harness=harness,
        gateway=gateway,
        arbiter=template._arbiter,
        obligations=obligations,
        budget=toy_budget(),
        max_iterations=1,
    )
    if charter_version is not None:
        kwargs["charter_version"] = charter_version
    return CampaignRunner(**kwargs)


def test_trust02_e3_obligations_from_another_campaign_are_refused():
    strict = CampaignCharter(
        campaign_id="camp-STRICT",
        terminal_decisions=(TerminalDecision(decision_id="d1", statement="x"),),
    )
    with pytest.raises(ValueError):
        _runner_with(charter=strict, obligations=_numerical_only("camp-WEAK"))


def test_trust02_a_policy_naming_the_charter_digest_for_another_campaign_is_refused():
    """Copying the charter digest onto another campaign's set is not derivation."""
    charter = toy_charter()
    borrowed = ObligationSet(
        campaign_id="camp-WEAK",
        obligations=_numerical_only().obligations,
        charter_digest=charter.digest,
    )
    with pytest.raises(ValueError):
        _runner_with(charter=charter, obligations=borrowed)


def test_trust02_a_hand_built_policy_with_the_right_campaign_id_is_refused():
    """Matching the campaign id is not derivation: the set names no charter."""
    with pytest.raises(ValueError):
        _runner_with(charter=toy_charter(), obligations=_numerical_only("m5-campaign"))


def test_trust02_a_policy_derived_from_a_different_charter_version_is_refused():
    original = toy_charter()
    amended = original.amend(
        CharterAmendment(amendment_id="a1", reason="tighter acceptance"),
        utility_reference="m5/two-unknown-confidence/2",
    )
    stale = obligations_from_charter(original, required_critics=(CriticClass.NUMERICAL,))
    assert stale.charter_digest == original.digest != amended.digest
    with pytest.raises(ValueError):
        _runner_with(charter=amended, obligations=stale)


def test_trust02_charter_version_is_checked_against_the_charter():
    charter = toy_charter()
    obligations = obligations_from_charter(charter, required_critics=(CriticClass.NUMERICAL,))
    assert charter.version == "1"
    with pytest.raises(ValueError):
        _runner_with(charter=charter, obligations=obligations, charter_version="7")
    runner = _runner_with(charter=charter, obligations=obligations)
    assert runner.run.charter_version == charter.version


def test_trust02_decisions_record_the_policy_and_admission_carries_it():
    runner, _harness, _gateway = build_campaign(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5}, max_iterations=1,
    )
    runner.run_campaign()
    obligations = critic_obligation()
    assert obligations.charter_digest == toy_charter().digest
    decided = runner.events.last(CampaignEventType.ARBITER_DECIDED, iteration=1)
    assert decided.payload["policy_digest"] == obligations.digest

    # At the Arbiter: the signed authorization names the policy version.
    _authority, arbiter, _gw = _stack("pol", NumericalCritic(), _domain_critic())
    evidence = _voltage_evidence("ev-pol")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), evidence)
    policy = T.standard_obligations()
    decision = arbiter.decide(
        decision_id="d-pol", evidence=evidence, assessments=[numerical, domain],
        obligations=policy, budget=_budget(),
    )
    assert decision.policy_digest == policy.digest
    declaration = arbiter.authorize_admission(
        decision, evidence.with_assessment(numerical.to_evidence_assessment())
    )
    assert policy.digest in declaration.authorization.policy_version


def test_trust02_policy_digest_is_part_of_the_decision_hash():
    weak = _numerical_only("camp-A", source="one")
    other = _numerical_only("camp-A", source="two")
    assert weak.digest != other.digest
    _g, arbiter, _a = build_assurance()
    first = arbiter.decide(decision_id="same", subject_ref="p", assessments=(),
                           obligations=weak)
    second = arbiter.decide(decision_id="same", subject_ref="p", assessments=(),
                            obligations=other)
    assert first.policy_digest == weak.digest
    assert second.policy_digest == other.digest
    assert first.decision_hash != second.decision_hash


def test_trust02_stopping_review_refuses_a_proposal_from_another_campaign():
    evaluator = ToyStoppingEvaluator(CRITERION.criterion_id, CriticVerdict.PASS)
    _g, arbiter, _a = build_assurance(critics=(evaluator,))
    proposal = StopProposal(
        proposal_id="p-other", campaign_id="some-other-campaign", run_id="r", iteration=1
    )
    review = ArbiterStoppingReview(arbiter).review(
        proposal,
        review_id="rev-other",
        obligations=critic_obligation(),
        obligation_state={"critic:numerical": True},
        terminal_objective_available=True,
        criteria=(CRITERION,),
        evaluators={CRITERION.criterion_id: evaluator},
    )
    assert review.outcome is not StopReviewOutcome.STOP_APPROVED
