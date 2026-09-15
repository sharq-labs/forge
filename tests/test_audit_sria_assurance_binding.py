"""Audit stream sria — SRIA-TRUST-01, -03 and -04 regressions.

Each test here reproduces one confirmed break in the SRIA assurance trust
chain (audit of origin/main 1edddd7) and locks the repair:

* TRUST-01 — an admission-bearing decision was not bound to the evidence it
  admitted, and critic assessments were plain dataclasses anyone could build.
  Probe E1 admitted a thermal claim of 1e9 K on the strength of an electrical
  result; probe E2 admitted a negative kelvin on two hand-built PASS records.
* TRUST-03 — required checks were resolved in a flat "last writer wins" map, so
  a NUMERICAL assessment could discharge a DOMAIN obligation (E4) and a later
  PROCESS record could overwrite a failed domain check (E5).
* TRUST-04 — a decision about ``evidence_id`` authorized a different record
  with the same id (E6), and one decision could mint authorizations repeatedly.

The literal probes use only the pre-repair surface (``decide(subject_ref=...)``
with assessments the caller built), so they fail on the unrepaired code by
assertion. The rest use the repaired surface — critics registered with the
Arbiter and run through :meth:`Arbiter.run_critic` — which is the only way an
assessment can count now.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.sria import (
    AdmissionAuthority,
    AdmissionAuthorityError,
    AdmissionAuthorityRegistry,
    AdmissionError,
    BeliefUpdateGateway,
    BeliefWriteViolation,
    ClaimBinding,
    ClaimType,
    Evidence,
    SourceClass,
)
from engcore.sria.assurance import (
    Arbiter,
    AssuranceVerdict,
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    NumericalCritic,
    ObligationSet,
    ObligationKind,
    ValidationObligation,
    trusting_authority,
)
from engcore.sria.provenance import AssessmentProvenance
from engcore.scientific import ProvenanceRecord

import tests.test_sria_m3_assurance as T

NOT_ADMITTED = (
    ValueError,
    AdmissionError,
    AdmissionAuthorityError,
    BeliefWriteViolation,
)


# =====================================================================
# fixtures
# =====================================================================

def _stack(tag: str, *critics):
    """An authority trusting exactly ``critics`` and the standard obligations,
    its gateway, and the one Arbiter it serves."""
    authority = trusting_authority(
        f"audit.sria.{tag}", critics, policies=(T.standard_obligations(),)
    )
    gateway = BeliefUpdateGateway(
        authorities=AdmissionAuthorityRegistry([authority])
    )
    arbiter = Arbiter(authority, critics=critics) if critics else Arbiter(authority)
    return authority, arbiter, gateway


def _admitted(arbiter, gateway, decision, evidence, assessments=()) -> bool:
    """True only if the whole chain let this evidence into belief."""
    if decision.verdict is not AssuranceVerdict.VALID:
        return False
    assessed = evidence
    for assessment in assessments:
        assessed = assessed.with_assessment(assessment.to_evidence_assessment())
    try:
        declaration = arbiter.authorize_admission(decision, assessed)
        if not declaration.admitted:
            return False
        gateway.submit(assessed.admit(declaration))
    except NOT_ADMITTED:
        return False
    return True


def _unrelated_evidence(eid: str, value: float) -> Evidence:
    """A different quantity, from a run that never happened, in another pack."""
    return Evidence(
        evidence_id=eid,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="T:junction"),
        claim_payload={"value": value, "units": "kelvin"},
        uncertainty=T.declaration(numerical=T.quantified()),
        provenance_ref="run-that-never-happened",
        domain_pack_ref="thermal.lumped",
    )


def _voltage_evidence(eid: str, value: float = 9.0) -> Evidence:
    """Evidence genuinely derived from ``T.good_result`` (run ``run-1``)."""
    return Evidence(
        evidence_id=eid,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="V:mid"),
        claim_payload={"value": value, "units": "volt"},
        uncertainty=T.declaration(numerical=T.quantified()),
        provenance_ref="run-1",
        domain_pack_ref="electrical.dc",
    )


def _budget():
    return T.full_budget(numerical=T.quantified())


def _domain_critic():
    return T.DemoDomainCritic(discrepancy_supported_by="study X")


def _honest_assessments(arbiter, result, evidence, *, tag="a"):
    obligations = T.standard_obligations()
    numerical = arbiter.run_critic(
        NumericalCritic.critic_id,
        result,
        subject=evidence,
        assessment_id=f"{tag}-num",
        budget=_budget(),
        mandatory_checks=("residual_evidence",),
        run_outcome=T.clean_run(),
    )
    domain = arbiter.run_critic(
        "electrical.dc.critic",
        result,
        subject=evidence,
        assessment_id=f"{tag}-dom",
        budget=_budget(),
        mandatory_checks=obligations.required_domain_checks,
    )
    return numerical, domain


def _result_for(obligation_id, decision):
    return next(r for r in decision.obligation_results if r.obligation_id == obligation_id)


class _Critic:
    """A registered critic whose checks the test declares."""

    critic_version = "1"

    def __init__(self, critic_id, critic_class, checks, *, verdict=CriticVerdict.PASS,
                 domain_pack_ref=""):
        self.critic_id = critic_id
        self.critic_class = critic_class
        self._checks = tuple(checks)
        self._verdict = verdict
        if domain_pack_ref:
            self.domain_pack_ref = domain_pack_ref

    def assess(self, result, *, assessment_id):
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=self.critic_class,
            subject_ref=result.result_id,
            verdict=self._verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=(result.result_id, result.provenance.run_id),
            ),
            checks=self._checks,
        )


def _pass(name, mandatory=False):
    return CheckRecord(name=name, outcome=CriticVerdict.PASS, mandatory=mandatory)


def _fail(name):
    return CheckRecord(name=name, outcome=CriticVerdict.FAIL, mandatory=False)


def _ownership_obligations() -> ObligationSet:
    """critic:numerical, critic:domain, check:residual_evidence,
    domain_check:physical_constraints — no uncertainty channel."""
    charter = T.CampaignCharter(
        campaign_id="camp-own",
        terminal_decisions=(T.TerminalDecision(decision_id="d", statement="s"),),
    )
    return T.obligations_from_charter(
        charter,
        required_critics=(CriticClass.NUMERICAL, CriticClass.DOMAIN),
        required_checks=("residual_evidence",),
        required_domain_checks=("physical_constraints",),
    )


def _run(arbiter, critic_id, evidence, aid):
    return arbiter.run_critic(
        critic_id, T.good_result("res-A"), subject=evidence, assessment_id=aid
    )


# =====================================================================
# TRUST-01 — subject binding and attributable assessments
# =====================================================================

def test_trust01_e1_literal_probe_decision_about_another_record_admits_nothing():
    """E1 as reported: real critics assess result A, the decision names ev-B."""
    authority, arbiter, gateway = _stack("e1lit")
    result_a = T.good_result("res-A")
    budget = _budget()
    numerical = NumericalCritic().assess(
        result_a, assessment_id="as-num", budget=budget,
        mandatory_checks=("residual_evidence",), run_outcome=T.clean_run(),
    )
    domain = _domain_critic().assess_domain(
        result_a, assessment_id="as-dom", budget=budget,
        mandatory_checks=T.standard_obligations().required_domain_checks,
    )
    ev_b = _unrelated_evidence("ev-B", 1.0e9)
    decision = arbiter.decide(
        decision_id="dec-B", subject_ref=ev_b.evidence_id,
        assessments=[numerical, domain], obligations=T.standard_obligations(),
        budget=budget,
    )
    assert not _admitted(arbiter, gateway, decision, ev_b, [numerical])
    assert len(gateway.belief) == 0


def test_trust01_e1_registered_critics_on_another_run_are_refused():
    """The strongest form of E1: the critics really ran, through the Arbiter,
    but on a result whose run is not the one the evidence came from."""
    _authority, arbiter, gateway = _stack("e1reg", NumericalCritic(), _domain_critic())
    ev_b = _unrelated_evidence("ev-B", 1.0e9)
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), ev_b)
    decision = arbiter.decide(
        decision_id="dec-B", evidence=ev_b, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert decision.subject_ref == ev_b.record_hash
    assert set(decision.refused_assessments) == {numerical.assessment_id, domain.assessment_id}
    assert numerical.assessment_id not in decision.assessment_refs
    assert not _admitted(arbiter, gateway, decision, ev_b, [numerical])


def test_trust01_a_result_from_another_run_does_not_count_even_when_it_agrees():
    """The critics really ran, on a result holding exactly the claimed value —
    but from a different run than the one the evidence came from."""
    _authority, arbiter, _gateway = _stack("otherrun", NumericalCritic(), _domain_critic())
    ev = _voltage_evidence("ev-run1")
    elsewhere = dataclasses.replace(
        T.good_result("res-run2"),
        provenance=ProvenanceRecord(run_id="run-2", solvers=(("demo.linear", "1"),)),
    )
    numerical, domain = _honest_assessments(arbiter, elsewhere, ev, tag="run2")
    decision = arbiter.decide(
        decision_id="d-run2", evidence=ev, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert set(decision.refused_assessments) == {numerical.assessment_id, domain.assessment_id}


def test_trust01_bound_assessments_still_admit():
    """Control: the same critics on the evidence's own run reach VALID."""
    _authority, arbiter, gateway = _stack("ctl", NumericalCritic(), _domain_critic())
    ev_a = _voltage_evidence("ev-A")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), ev_a)
    decision = arbiter.decide(
        decision_id="dec-A", evidence=ev_a, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is AssuranceVerdict.VALID, decision.reasons
    assert decision.refused_assessments == ()
    assert decision.subject_ref == ev_a.record_hash
    assert _admitted(arbiter, gateway, decision, ev_a, [numerical, domain])
    assert len(gateway.belief) == 1


def test_trust01_e2_literal_probe_fabricated_assessments_admit_nothing():
    """E2 as reported: two hand-built PASS records, no critic ever ran."""
    _authority, arbiter, gateway = _stack("e2lit")
    prov = lambda aid: AssessmentProvenance(  # noqa: E731
        assessment_id=aid, critic_id="anyone", critic_version="x"
    )
    fake = [
        CriticAssessment(
            assessment_id="f1", critic_id="anyone", critic_version="x",
            critic_class=CriticClass.NUMERICAL, subject_ref="whatever",
            verdict=CriticVerdict.PASS, provenance=prov("f1"),
            checks=(_pass("residual_evidence"),),
        ),
        CriticAssessment(
            assessment_id="f2", critic_id="anyone", critic_version="x",
            critic_class=CriticClass.DOMAIN, subject_ref="whatever",
            verdict=CriticVerdict.PASS, provenance=prov("f2"),
            checks=(_pass("physical_constraints"),),
        ),
    ]
    ev_c = _unrelated_evidence("ev-C", -5.0)
    decision = arbiter.decide(
        decision_id="dec-C", subject_ref=ev_c.evidence_id, assessments=fake,
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert not _admitted(arbiter, gateway, decision, ev_c, fake[:1])
    assert len(gateway.belief) == 0


def test_trust01_fabricated_assessments_about_the_evidence_are_refused():
    """Hand-built records that even name the right record hash do not count."""
    _authority, arbiter, _gateway = _stack("e2ev", NumericalCritic())
    ev = _voltage_evidence("ev-F")
    forged = CriticAssessment(
        assessment_id="forged", critic_id=NumericalCritic.critic_id,
        critic_version=NumericalCritic.critic_version,
        critic_class=CriticClass.NUMERICAL, subject_ref=ev.record_hash,
        verdict=CriticVerdict.PASS,
        provenance=AssessmentProvenance(
            assessment_id="forged", critic_id=NumericalCritic.critic_id,
            inputs_ref=("run-1",),
        ),
        checks=(_pass("residual_evidence"),),
    )
    decision = arbiter.decide(
        decision_id="dec-F", evidence=ev, assessments=[forged],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is AssuranceVerdict.NOT_ASSESSED
    assert decision.refused_assessments == ("forged",)


def test_trust01_an_edited_recorded_assessment_is_refused():
    """The Arbiter records what the critic produced, not an id."""
    _authority, arbiter, _gateway = _stack("edit", NumericalCritic(), _domain_critic())
    ev = _voltage_evidence("ev-E")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), ev)
    edited = dataclasses.replace(domain, summary="edited after the run")
    decision = arbiter.decide(
        decision_id="dec-E", evidence=ev, assessments=[numerical, edited],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert decision.refused_assessments == (domain.assessment_id,)


def test_trust01_assessment_run_for_another_record_is_refused():
    """Recorded for record A; offered in a decision about record B of the same run."""
    _authority, arbiter, _gateway = _stack("swap", NumericalCritic(), _domain_critic())
    ev_a = _voltage_evidence("ev-A")
    ev_b = _voltage_evidence("ev-B")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), ev_a)
    decision = arbiter.decide(
        decision_id="dec-swap", evidence=ev_b, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert set(decision.refused_assessments) == {"a-num", "a-dom"}


def test_trust01_unregistered_critic_cannot_run_and_misattributed_output_is_refused():
    _authority, arbiter, _gateway = _stack("reg", NumericalCritic())
    ev = _voltage_evidence("ev-R")
    with pytest.raises((KeyError, ValueError)):
        arbiter.run_critic("electrical.dc.critic", T.good_result(), subject=ev,
                           assessment_id="x")

    class Impostor(_Critic):
        def assess(self, result, *, assessment_id):
            produced = super().assess(result, assessment_id=assessment_id)
            return dataclasses.replace(produced, critic_id="sria.numerical")

    _a, impostor_arbiter, _g = _stack(
        "imp", Impostor("audit.impostor", CriticClass.PROCESS, (_pass("x"),))
    )
    with pytest.raises(ValueError):
        impostor_arbiter.run_critic("audit.impostor", T.good_result(), subject=ev,
                                    assessment_id="imp")


def test_trust01_a_refused_assessment_blocks_valid_even_when_obligations_are_met():
    """Every obligation is discharged by bound assessments; a further, refused
    assessment still keeps the decision from VALID. A decision that ignored
    part of what was said about a record would certify it anyway."""
    _authority, arbiter, _gateway = _stack("extra", NumericalCritic(), _domain_critic())
    ev = _voltage_evidence("ev-X1")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), ev)
    objection = CriticAssessment(
        assessment_id="objection", critic_id="reviewer", critic_version="1",
        critic_class=CriticClass.PROCESS, subject_ref=ev.record_hash,
        verdict=CriticVerdict.FAIL,
        provenance=AssessmentProvenance(
            assessment_id="objection", critic_id="reviewer", inputs_ref=("run-1",),
        ),
    )
    control = arbiter.decide(
        decision_id="d-ctl", evidence=ev, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert control.verdict is AssuranceVerdict.VALID, control.reasons
    decision = arbiter.decide(
        decision_id="d-obj", evidence=ev, assessments=[numerical, domain, objection],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.unmet_obligations == ()
    assert decision.refused_assessments == ("objection",)
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE


def test_trust01_e7_budget_for_another_quantity_leaves_the_channel_unmet():
    """The uncertainty budget must describe the quantity the evidence claims."""
    _authority, arbiter, _gateway = _stack("e7", NumericalCritic(), _domain_critic())
    ev = _voltage_evidence("ev-U")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), ev)
    foreign = dataclasses.replace(_budget(), value_name="T:junction")
    decision = arbiter.decide(
        decision_id="dec-U", evidence=ev, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=foreign,
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    channel = _result_for("uncertainty:numerical", decision)
    assert channel.satisfied is False
    assert "T:junction" in channel.detail


# =====================================================================
# TRUST-03 — check ownership and duplicates
# =====================================================================

def test_trust03_e4_a_numerical_check_cannot_discharge_a_domain_obligation():
    ev = _voltage_evidence("ev-4")
    numerical = _Critic("audit.num", CriticClass.NUMERICAL,
                        (_pass("residual_evidence"), _pass("physical_constraints")))
    empty_domain = _Critic("audit.dom", CriticClass.DOMAIN, (),
                           domain_pack_ref="electrical.dc")
    _authority, arbiter, _gateway = _stack("e4", numerical, empty_domain)
    assessments = [
        _run(arbiter, "audit.dom", ev, "d-no"),
        _run(arbiter, "audit.num", ev, "n-yes"),
    ]
    decision = arbiter.decide(decision_id="d4", evidence=ev, assessments=assessments,
                              obligations=_ownership_obligations())
    assert _result_for("domain_check:physical_constraints", decision).satisfied is False
    assert decision.verdict is not AssuranceVerdict.VALID


def test_trust03_the_domain_critic_performing_the_check_does_discharge_it():
    """Control for E4/E5: ownership, not the check name, is what decides."""
    ev = _voltage_evidence("ev-4c")
    numerical = _Critic("audit.num", CriticClass.NUMERICAL, (_pass("residual_evidence"),))
    domain = _Critic("audit.dom", CriticClass.DOMAIN, (_pass("physical_constraints"),),
                     domain_pack_ref="electrical.dc")
    _authority, arbiter, _gateway = _stack("e4c", numerical, domain)
    assessments = [_run(arbiter, "audit.dom", ev, "d"), _run(arbiter, "audit.num", ev, "n")]
    decision = arbiter.decide(decision_id="d4c", evidence=ev, assessments=assessments,
                              obligations=_ownership_obligations())
    assert decision.verdict is AssuranceVerdict.VALID, decision.reasons


def test_trust03_e5_a_later_record_cannot_overwrite_a_failed_domain_check():
    ev = _voltage_evidence("ev-5")
    numerical = _Critic("audit.num", CriticClass.NUMERICAL, (_pass("residual_evidence"),))
    domain = _Critic("audit.dom", CriticClass.DOMAIN, (_fail("physical_constraints"),),
                     domain_pack_ref="electrical.dc")
    process = _Critic("audit.proc", CriticClass.PROCESS, (_pass("physical_constraints"),))
    _authority, arbiter, _gateway = _stack("e5", numerical, domain, process)
    assessments = [
        _run(arbiter, "audit.num", ev, "n"),
        _run(arbiter, "audit.dom", ev, "d-fail"),
        _run(arbiter, "audit.proc", ev, "p-pass"),
    ]
    decision = arbiter.decide(decision_id="d5", evidence=ev, assessments=assessments,
                              obligations=_ownership_obligations())
    assert _result_for("domain_check:physical_constraints", decision).satisfied is False
    assert decision.verdict is not AssuranceVerdict.VALID


def test_trust03_a_required_check_reported_twice_is_ambiguous():
    ev = _voltage_evidence("ev-dup")
    process = _Critic("audit.proc", CriticClass.PROCESS, (_fail("residual_evidence"),))
    numerical = _Critic("audit.num", CriticClass.NUMERICAL, (_pass("residual_evidence"),))
    domain = _Critic("audit.dom", CriticClass.DOMAIN, (_pass("physical_constraints"),),
                     domain_pack_ref="electrical.dc")
    _authority, arbiter, _gateway = _stack("dup", process, numerical, domain)
    assessments = [
        _run(arbiter, "audit.proc", ev, "p"),
        _run(arbiter, "audit.dom", ev, "d"),
        _run(arbiter, "audit.num", ev, "n"),
    ]
    decision = arbiter.decide(decision_id="ddup", evidence=ev, assessments=assessments,
                              obligations=_ownership_obligations())
    check = _result_for("check:residual_evidence", decision)
    assert check.satisfied is False
    assert "ambiguous" in check.detail
    assert decision.verdict is not AssuranceVerdict.VALID


def test_trust03_a_required_domain_check_reported_twice_is_ambiguous():
    ev = _voltage_evidence("ev-dupd")
    numerical = _Critic("audit.num", CriticClass.NUMERICAL, (_pass("residual_evidence"),))
    domain = _Critic(
        "audit.dom", CriticClass.DOMAIN,
        (_fail("physical_constraints"), _pass("physical_constraints")),
        domain_pack_ref="electrical.dc",
    )
    _authority, arbiter, _gateway = _stack("dupd", numerical, domain)
    assessments = [_run(arbiter, "audit.num", ev, "n"), _run(arbiter, "audit.dom", ev, "d")]
    decision = arbiter.decide(decision_id="ddupd", evidence=ev, assessments=assessments,
                              obligations=_ownership_obligations())
    check = _result_for("domain_check:physical_constraints", decision)
    assert check.satisfied is False
    assert "ambiguous" in check.detail


def test_trust03_every_assessment_of_a_required_critic_class_must_pass():
    ev = _voltage_evidence("ev-all")
    doubtful = _Critic("audit.num.a", CriticClass.NUMERICAL, (_pass("convergence_state"),),
                       verdict=CriticVerdict.INCONCLUSIVE)
    confident = _Critic("audit.num.b", CriticClass.NUMERICAL, (_pass("residual_evidence"),))
    _authority, arbiter, _gateway = _stack("all", doubtful, confident)
    assessments = [_run(arbiter, "audit.num.a", ev, "a"), _run(arbiter, "audit.num.b", ev, "b")]
    obligations = ObligationSet(
        campaign_id="camp-all",
        obligations=(
            ValidationObligation(obligation_id="critic:numerical",
                                 kind=ObligationKind.REQUIRED_CRITIC,
                                 target="numerical", source="audit"),
        ),
    )
    decision = arbiter.decide(decision_id="dall", evidence=ev, assessments=assessments,
                              obligations=obligations)
    assert _result_for("critic:numerical", decision).satisfied is False


def test_trust03_a_domain_critic_for_another_pack_does_not_count():
    ev = _voltage_evidence("ev-pack")
    numerical = _Critic("audit.num", CriticClass.NUMERICAL, (_pass("residual_evidence"),))
    thermal = _Critic("audit.thermal", CriticClass.DOMAIN, (_pass("physical_constraints"),),
                      domain_pack_ref="thermal.lumped")
    _authority, arbiter, _gateway = _stack("pack", numerical, thermal)
    assessments = [_run(arbiter, "audit.num", ev, "n"), _run(arbiter, "audit.thermal", ev, "t")]
    decision = arbiter.decide(decision_id="dpack", evidence=ev, assessments=assessments,
                              obligations=_ownership_obligations())
    assert decision.verdict is not AssuranceVerdict.VALID
    assert _result_for("domain_check:physical_constraints", decision).satisfied is False
    assert "t" in decision.refused_assessments


# =====================================================================
# TRUST-04 — one decision, one record, one authorization
# =====================================================================

def test_trust04_e6_literal_probe_decision_about_an_id_cannot_admit_new_content():
    """E6 as reported: decide about 'ev-X', then authorize v2 of that id."""
    authority, arbiter, gateway = _stack("e6lit")
    result_a = T.good_result("res-A")
    budget = _budget()
    numerical = NumericalCritic().assess(
        result_a, assessment_id="as-num", budget=budget,
        mandatory_checks=("residual_evidence",), run_outcome=T.clean_run(),
    )
    domain = _domain_critic().assess_domain(
        result_a, assessment_id="as-dom", budget=budget,
        mandatory_checks=T.standard_obligations().required_domain_checks,
    )
    v2 = _unrelated_evidence("ev-X", 99999.0)
    decision = arbiter.decide(
        decision_id="d6", subject_ref="ev-X", assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=budget,
    )
    assert not _admitted(arbiter, gateway, decision, v2, [numerical])


def test_trust04_a_decision_on_one_record_cannot_authorize_another_with_the_same_id():
    _authority, arbiter, gateway = _stack("e6", NumericalCritic(), _domain_critic())
    v1 = _voltage_evidence("ev-X", 9.0)
    v2 = _voltage_evidence("ev-X", 9999.0)
    assert v1.record_hash != v2.record_hash
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), v1)
    decision = arbiter.decide(
        decision_id="d6", evidence=v1, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is AssuranceVerdict.VALID, decision.reasons
    assessed_v2 = v2.with_assessment(numerical.to_evidence_assessment())
    with pytest.raises(ValueError):
        arbiter.authorize_admission(decision, assessed_v2)
    assert len(gateway.belief) == 0


def test_trust04_a_decision_authorizes_at_most_once():
    _authority, arbiter, _gateway = _stack("once", NumericalCritic(), _domain_critic())
    v1 = _voltage_evidence("ev-once")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), v1)
    decision = arbiter.decide(
        decision_id="d-once", evidence=v1, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assessed = v1.with_assessment(numerical.to_evidence_assessment())
    first = arbiter.authorize_admission(decision, assessed)
    assert first.admitted is True
    with pytest.raises(ValueError):
        arbiter.authorize_admission(decision, assessed)


def test_trust04_a_reference_decision_never_authorizes_admission():
    """A decision whose subject is a string — an id, a proposal — is not about
    an Evidence record, even when that string is the record's own id."""
    _authority, arbiter, _gateway = _stack("ref", NumericalCritic(), _domain_critic())
    v1 = _voltage_evidence("ev-ref")
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), v1)
    decision = arbiter.decide(
        decision_id="d-ref", subject_ref=v1.evidence_id, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    with pytest.raises(ValueError):
        arbiter.authorize_admission(decision, v1.with_assessment(
            numerical.to_evidence_assessment()))
