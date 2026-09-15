"""Audit stream sria — SRIA-06: obligation state comes from the Arbiter, not a caller.

``CampaignRunner`` merged whatever booleans the harness put in
``AssessmentBundle.obligation_state``, and ``adopt_prior_assurance`` accepted any
mapping. Stop review, validation liveness and the checkpoint all read that
state, so a harness — or a caller holding the runner — could mark an obligation
satisfied that no Arbiter decision ever found satisfied.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.sria.assurance import AssuranceVerdict, CriticVerdict
from engcore.sria.campaign import CampaignCheckpoint, CampaignEventType
from engcore.sria.campaign.checkpoint import ResumeViolation

from tests.sria_m5_benchmark import TOY_CRITIC_ID, build_assurance, toy_evidence
from tests.test_sria_m5_campaign import S1, S1_SEED, build_campaign


def _campaign(**kwargs):
    base = dict(
        actions_by_iteration=S1, seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5}, max_iterations=1,
    )
    base.update(kwargs)
    return build_campaign(**base)


def test_sria06_a_harness_cannot_mark_an_obligation_satisfied():
    runner, harness, _gateway = _campaign(critic_verdict=CriticVerdict.INCONCLUSIVE)
    honest = harness.assess

    def boastful(execution, evidence, *, assessment_prefix):
        bundle = honest(execution, evidence, assessment_prefix=assessment_prefix)
        claims = {o.obligation_id: True for o in harness.obligations.obligations}
        return dataclasses.replace(bundle, obligation_state=claims)

    harness.assess = boastful
    runner.run_campaign()

    assert runner.run.iterations[0].arbiter_verdict == AssuranceVerdict.INCONCLUSIVE.value
    latest = runner.checkpoints.latest()
    assert latest.obligation_state.get("critic:numerical") is not True
    assert runner._obligation_state.get("critic:numerical") is not True


def test_sria06_a_harness_may_still_report_an_obligation_unmet():
    runner, harness, _gateway = _campaign()
    honest = harness.assess

    def cautious(execution, evidence, *, assessment_prefix):
        bundle = honest(execution, evidence, assessment_prefix=assessment_prefix)
        return dataclasses.replace(bundle, obligation_state={"critic:numerical": False})

    harness.assess = cautious
    runner.run_campaign()
    assert runner.run.iterations[0].arbiter_verdict == AssuranceVerdict.VALID.value
    assert runner._obligation_state.get("critic:numerical") is False


def test_sria06_the_arbiter_decision_is_what_satisfies_an_obligation():
    runner, _harness, _gateway = _campaign()
    runner.run_campaign()
    assert runner.run.iterations[0].arbiter_verdict == AssuranceVerdict.VALID.value
    assert runner._obligation_state == {"critic:numerical": True}
    assert runner.checkpoints.latest().obligation_state == {"critic:numerical": True}


def test_sria06_adopting_a_bare_mapping_is_refused():
    runner, _harness, _gateway = _campaign()
    with pytest.raises((TypeError, ValueError)):
        runner.adopt_prior_assurance({"critic:numerical": True})
    assert runner._obligation_state.get("critic:numerical") is not True


def test_sria06_adopting_a_decision_from_another_arbiter_is_refused():
    runner, _harness, _gateway = _campaign()
    _g, foreign, _a = build_assurance()
    evidence = toy_evidence("ev-foreign")
    assessment = foreign.run_critic(
        TOY_CRITIC_ID, evidence, subject=evidence, assessment_id="foreign-a"
    )
    decision = foreign.decide(
        decision_id="foreign-d", evidence=evidence, assessments=(assessment,),
        obligations=runner._obligations,
    )
    assert decision.verdict is AssuranceVerdict.VALID
    with pytest.raises(ValueError):
        runner.adopt_prior_assurance((decision,))
    assert runner._obligation_state.get("critic:numerical") is not True


def test_sria06_adopting_decisions_issued_by_this_arbiter_is_derived_and_logged():
    runner, _harness, _gateway = _campaign()
    arbiter = runner._arbiter
    evidence = toy_evidence("ev-prior")
    assessment = arbiter.run_critic(
        TOY_CRITIC_ID, evidence, subject=evidence, assessment_id="prior-a"
    )
    decision = arbiter.decide(
        decision_id="prior-d", evidence=evidence, assessments=(assessment,),
        obligations=runner._obligations,
    )
    runner.adopt_prior_assurance((decision,))
    assert runner._obligation_state == {"critic:numerical": True}
    adopted = runner.events.of_type(CampaignEventType.PRIOR_ASSURANCE_ADOPTED)
    assert len(adopted) == 1
    assert adopted[0].payload["decision_ids"] == ["prior-d"]


def test_sria06_restoring_an_unbacked_obligation_state_is_refused():
    runner, _harness, _gateway = _campaign()
    forged = CampaignCheckpoint(
        run=runner.run,
        events=runner.events,
        budget=runner.budget,
        effects=runner.effects,
        plan=None,
        obligation_state={"critic:numerical": True},
    )
    with pytest.raises(ResumeViolation):
        runner.restore(forged)
    assert runner._obligation_state.get("critic:numerical") is not True


def test_sria06_adopting_a_decision_made_under_another_policy_is_refused():
    """Same Arbiter, same campaign, different obligation set: not this policy."""
    from engcore.sria.assurance import CriticClass, obligations_from_charter
    from tests.sria_m5_benchmark import toy_charter

    runner, _harness, _gateway = _campaign()
    arbiter = runner._arbiter
    evidence = toy_evidence("ev-policy")
    assessment = arbiter.run_critic(
        TOY_CRITIC_ID, evidence, subject=evidence, assessment_id="policy-a"
    )
    other_policy = obligations_from_charter(
        toy_charter(),
        required_critics=(CriticClass.NUMERICAL,),
        required_checks=("convergence_state",),
    )
    decision = arbiter.decide(
        decision_id="policy-d", evidence=evidence, assessments=(assessment,),
        obligations=other_policy,
    )
    assert decision.verdict is AssuranceVerdict.VALID
    with pytest.raises(ValueError):
        runner.adopt_prior_assurance((decision,))
    assert runner._obligation_state.get("critic:numerical") is not True


def test_sria06_the_latest_adopted_decision_about_an_obligation_governs():
    """One rule everywhere — event-log derivation, adoption and stop review:
    in order, the most recent Arbiter decision about an obligation decides it."""
    def adopted_state(order):
        runner, _harness, _gateway = _campaign()
        arbiter = runner._arbiter
        decisions = {}
        for tag, verdict in (("ok", CriticVerdict.PASS), ("doubt", CriticVerdict.INCONCLUSIVE)):
            evidence = toy_evidence(f"ev-{tag}")
            assessment = arbiter.run_critic(
                TOY_CRITIC_ID, evidence, subject=evidence, assessment_id=f"{tag}-a",
                declared_convergence=verdict,
            )
            decisions[tag] = arbiter.decide(
                decision_id=f"{tag}-d", evidence=evidence, assessments=(assessment,),
                obligations=runner._obligations,
            )
        runner.adopt_prior_assurance(tuple(decisions[t] for t in order))
        return runner._obligation_state

    assert adopted_state(("ok", "doubt")) == {"critic:numerical": False}
    assert adopted_state(("doubt", "ok")) == {"critic:numerical": True}
