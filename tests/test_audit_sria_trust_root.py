"""Audit stream sria follow-up — the admission trust root.

After SRIA-TRUST-01 an Arbiter counted only assessments from critics it was
constructed to trust. But nothing tied an AdmissionAuthority to one Arbiter or
to one critic registry, so anyone holding the trusted authority could build a
second ``Arbiter(authority, critics=(fabricating_critic,))`` and have the
Gateway accept an admission — the fabricated-assessment attack at one remove.

Now an authority declares, at construction, the critic-registry digest and the
policy digests it serves; the authorization carries the deciding Arbiter's
registry and policy digests and is refused unless they are the declared ones;
and an authority serves at most one Arbiter.
"""

from __future__ import annotations

import pytest

from engcore.sria import (
    AdmissionAuthority,
    AdmissionAuthorityError,
    AdmissionAuthorityRegistry,
    BeliefUpdateGateway,
)
from engcore.sria.admission import AdmissionDeclaration, DecisionBinding
from engcore.sria.assurance import (
    Arbiter,
    AssuranceVerdict,
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    NumericalCritic,
    critic_registry_digest,
    trusting_authority,
)
from engcore.sria.provenance import AssessmentProvenance

import tests.test_sria_m3_assurance as T
from tests.test_audit_sria_assurance_binding import _unrelated_evidence, _voltage_evidence


class Fabricator:
    """Says PASS about whatever record it is handed. Checks nothing."""

    critic_id = "audit.fabricator"
    critic_version = "1"
    critic_class = CriticClass.NUMERICAL

    def assess(self, evidence, *, assessment_id):
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=self.critic_class,
            subject_ref=evidence.record_hash,
            verdict=CriticVerdict.PASS,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id, critic_id=self.critic_id,
                critic_version=self.critic_version,
            ),
            checks=(CheckRecord(name="residual_evidence", outcome=CriticVerdict.PASS),),
        )


class Impostor(Fabricator):
    """Registers exactly like the honest numerical critic, but fabricates."""

    critic_id = NumericalCritic.critic_id
    critic_version = NumericalCritic.critic_version


def _policy():
    return T.obligations_from_charter(
        T.CampaignCharter(
            campaign_id="camp-root",
            terminal_decisions=(T.TerminalDecision(decision_id="d", statement="s"),),
        ),
        required_critics=(CriticClass.NUMERICAL,),
        required_checks=("residual_evidence",),
    )


def _honest_critics():
    return (NumericalCritic(),)


def _gateway(authority):
    return BeliefUpdateGateway(authorities=AdmissionAuthorityRegistry([authority]))


def _fabricated_decision(arbiter, evidence, policy):
    assessment = arbiter.run_critic(
        Fabricator.critic_id, evidence, subject=evidence, assessment_id="fab"
    )
    decision = arbiter.decide(
        decision_id="d-fab", evidence=evidence, assessments=[assessment],
        obligations=policy,
    )
    return assessment, decision


def test_root_the_honest_registry_still_admits():
    policy = _policy()
    authority = trusting_authority("root.honest", _honest_critics(), policies=(policy,))
    arbiter = Arbiter(authority, critics=_honest_critics())
    gateway = _gateway(authority)
    evidence = _voltage_evidence("ev-honest")
    assessment = arbiter.run_critic(
        NumericalCritic.critic_id, T.good_result("res-A"), subject=evidence,
        assessment_id="num", budget=T.full_budget(numerical=T.quantified()),
        mandatory_checks=("residual_evidence",), run_outcome=T.clean_run(),
    )
    decision = arbiter.decide(
        decision_id="d-honest", evidence=evidence, assessments=[assessment],
        obligations=policy,
    )
    assert decision.verdict is AssuranceVerdict.VALID, decision.reasons
    assessed = evidence.with_assessment(assessment.to_evidence_assessment())
    declaration = arbiter.authorize_admission(decision, assessed)
    assert declaration.authorization.critic_registry_digest == authority.critic_registry_digest
    assert declaration.authorization.policy_digest == policy.digest
    gateway.submit(assessed.admit(declaration))
    assert len(gateway.belief) == 1


def test_root_a_second_arbiter_around_the_authority_is_refused():
    policy = _policy()
    authority = trusting_authority("root.second", _honest_critics(), policies=(policy,))
    Arbiter(authority, critics=_honest_critics())
    with pytest.raises(AdmissionAuthorityError):
        Arbiter(authority, critics=(Fabricator(),))
    # Even an impostor whose registration is indistinguishable by id, version
    # and class cannot take the authority over.
    with pytest.raises(AdmissionAuthorityError):
        Arbiter(authority, critics=(Impostor(),))


def test_root_an_arbiter_with_other_critics_decides_but_cannot_admit():
    """The attack: the fabricating Arbiter is the only one around the authority."""
    policy = _policy()
    authority = trusting_authority("root.attack", _honest_critics(), policies=(policy,))
    gateway = _gateway(authority)
    attacker = Arbiter(authority, critics=(Fabricator(),))
    evidence = _unrelated_evidence("ev-attack", -5.0)
    assessment, decision = _fabricated_decision(attacker, evidence, policy)
    assert decision.verdict is AssuranceVerdict.VALID
    assessed = evidence.with_assessment(assessment.to_evidence_assessment())
    with pytest.raises(AdmissionAuthorityError):
        attacker.authorize_admission(decision, assessed)
    assert len(gateway.belief) == 0


def test_root_registry_digest_names_the_implementation():
    assert critic_registry_digest((Impostor(),)) != critic_registry_digest(_honest_critics())


def test_root_gateway_refuses_a_declaration_embedding_another_registry():
    """Bypass issue(): the attacker's genuine commitment, signed directly."""
    policy = _policy()
    authority = trusting_authority("root.gw", _honest_critics(), policies=(policy,))
    gateway = _gateway(authority)
    attacker = Arbiter(authority, critics=(Fabricator(),))
    evidence = _unrelated_evidence("ev-gw", 1.0e9)
    assessment, decision = _fabricated_decision(attacker, evidence, policy)
    assessed = evidence.with_assessment(assessment.to_evidence_assessment())
    code = attacker._mint_authorization(  # noqa: SLF001 — the attack surface
        decision=decision, subject_record_hash=assessed.record_hash
    )
    binding = DecisionBinding(
        decision_id=decision.decision_id,
        decision_hash=decision.decision_hash,
        verdict=decision.verdict.value,
        policy_id="sria.arbiter",
        policy_version=attacker._policy_version(decision),  # noqa: SLF001
        arbiter_id=attacker._arbiter_id,  # noqa: SLF001
        authorization_code=code,
        critic_registry_digest=attacker.critic_registry_digest,
        policy_digest=decision.policy_digest,
    )
    assert binding.critic_registry_digest != authority.critic_registry_digest
    unsigned = AdmissionDeclaration(
        admitted=True, arbiter_id=authority.authority_id,
        subject_record_hash=assessed.record_hash, authorization=binding,
        issuer_id=authority.authority_id,
    )
    signed = AdmissionDeclaration(
        admitted=True, arbiter_id=authority.authority_id,
        subject_record_hash=assessed.record_hash, authorization=binding,
        issuer_id=authority.authority_id,
        issued_signature=authority._sign(unsigned.signing_payload()),  # noqa: SLF001
    )
    assert authority.verifies(signed)
    with pytest.raises(AdmissionAuthorityError):
        gateway.submit(assessed.admit(signed))
    assert len(gateway.belief) == 0
    assert "registry" in gateway.rejection_log[-1].reason


def test_root_a_policy_the_authority_does_not_serve_cannot_admit():
    """The honest Arbiter itself cannot admit under a policy nobody declared."""
    served = _policy()
    authority = trusting_authority("root.policy", _honest_critics(), policies=(served,))
    arbiter = Arbiter(authority, critics=_honest_critics())
    weak = T.ObligationSet(
        campaign_id="camp-root",
        obligations=(
            T.ValidationObligation(
                obligation_id="critic:numerical", kind=T.ObligationKind.REQUIRED_CRITIC,
                target="numerical", source="me",
            ),
        ),
    )
    evidence = _voltage_evidence("ev-weak")
    assessment = arbiter.run_critic(
        NumericalCritic.critic_id, T.good_result("res-A"), subject=evidence,
        assessment_id="num", budget=T.full_budget(numerical=T.quantified()),
        run_outcome=T.clean_run(),
    )
    decision = arbiter.decide(
        decision_id="d-weak", evidence=evidence, assessments=[assessment], obligations=weak,
    )
    assert decision.verdict is AssuranceVerdict.VALID
    with pytest.raises(AdmissionAuthorityError):
        arbiter.authorize_admission(
            decision, evidence.with_assessment(assessment.to_evidence_assessment())
        )


def test_root_an_authority_that_declares_nothing_admits_nothing():
    authority = AdmissionAuthority("root.silent")
    arbiter = Arbiter(authority, critics=_honest_critics())
    evidence = _voltage_evidence("ev-silent")
    assessment = arbiter.run_critic(
        NumericalCritic.critic_id, T.good_result("res-A"), subject=evidence,
        assessment_id="num", budget=T.full_budget(numerical=T.quantified()),
        mandatory_checks=("residual_evidence",), run_outcome=T.clean_run(),
    )
    decision = arbiter.decide(
        decision_id="d-silent", evidence=evidence, assessments=[assessment],
        obligations=_policy(),
    )
    assert decision.verdict is AssuranceVerdict.VALID
    with pytest.raises(AdmissionAuthorityError):
        arbiter.authorize_admission(
            decision, evidence.with_assessment(assessment.to_evidence_assessment())
        )
