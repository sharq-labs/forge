"""Audit stream sria follow-up — the assessed result must back the claim.

After SRIA-TRUST-01 an assessment counted for evidence when it named the run the
evidence came from. Nothing checked that what the critics looked at says what
the evidence claims: a record from run ``run-1`` claiming ``V:mid = 9000 V``
was admitted on the strength of critics that assessed ``V:mid = 9 V``.

Now, for a QOI/parameter claim whose payload states a value and units, an
assessment made over a ScientificResult counts only if that result holds the
claimed quantity at the claimed value (unit-converted; exact up to rounding, or
within a tolerance the claim declares). And an uncertainty budget counts only
if it carries the evidence's own uncertainty declaration.
"""

from __future__ import annotations

import dataclasses

from engcore.sria import ClaimBinding, ClaimType, Evidence, SourceClass
from engcore.sria.assurance import AssuranceVerdict, NumericalCritic

import tests.test_sria_m3_assurance as T
from tests.test_audit_sria_assurance_binding import (
    _budget,
    _domain_critic,
    _honest_assessments,
    _result_for,
    _stack,
)


def _claim(eid, *, quantity="V:mid", payload=None):
    return Evidence(
        evidence_id=eid,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref=quantity),
        claim_payload=payload if payload is not None else {"value": 9.0, "units": "volt"},
        uncertainty=T.declaration(numerical=T.quantified()),
        provenance_ref="run-1",
        domain_pack_ref="electrical.dc",
    )


def _decide(evidence, *, budget=None, tag="c"):
    _authority, arbiter, _gateway = _stack(tag, NumericalCritic(), _domain_critic())
    numerical, domain = _honest_assessments(arbiter, T.good_result("res-A"), evidence, tag=tag)
    decision = arbiter.decide(
        decision_id=f"d-{tag}", evidence=evidence, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=budget or _budget(),
    )
    return decision, numerical, domain


def test_claim_matching_value_counts():
    decision, _n, _d = _decide(_claim("ev-match"), tag="match")
    assert decision.verdict is AssuranceVerdict.VALID, decision.reasons


def test_claim_a_different_value_for_the_assessed_quantity_does_not_count():
    evidence = _claim("ev-inflated", payload={"value": 9000.0, "units": "volt"})
    decision, numerical, domain = _decide(evidence, tag="inflated")
    assert decision.verdict is not AssuranceVerdict.VALID
    assert set(decision.refused_assessments) == {numerical.assessment_id, domain.assessment_id}
    assert any("9000" in r for r in decision.reasons)


def test_claim_is_compared_after_unit_conversion():
    evidence = _claim("ev-mv", payload={"value": 9000.0, "units": "millivolt"})
    decision, _n, _d = _decide(evidence, tag="mv")
    assert decision.refused_assessments == ()
    assert decision.verdict is AssuranceVerdict.VALID, decision.reasons


def test_claim_in_incompatible_units_does_not_count():
    evidence = _claim("ev-kelvin", payload={"value": 9.0, "units": "kelvin"})
    decision, _n, _d = _decide(evidence, tag="kelvin")
    assert len(decision.refused_assessments) == 2


def test_claim_about_a_quantity_the_result_does_not_hold_does_not_count():
    evidence = _claim("ev-absent", quantity="I:branch",
                      payload={"value": 0.003, "units": "ampere"})
    decision, _n, _d = _decide(evidence, tag="absent")
    assert len(decision.refused_assessments) == 2
    assert decision.verdict is not AssuranceVerdict.VALID


def test_claim_within_its_declared_tolerance_counts_and_outside_it_does_not():
    near = {"value": 9.0005, "units": "volt"}
    decision, _n, _d = _decide(_claim("ev-near", payload=near), tag="near")
    assert len(decision.refused_assessments) == 2
    tolerant = {"value": 9.0005, "units": "volt", "tolerance": 0.001}
    decision, _n, _d = _decide(_claim("ev-tol", payload=tolerant), tag="tol")
    assert decision.refused_assessments == ()


def test_claim_the_assessment_records_the_result_it_read():
    _decision, numerical, domain = _decide(_claim("ev-digest"), tag="digest")
    for assessment in (numerical, domain):
        assert len(assessment.provenance.metadata["assessed_result_digest"]) == 64


def test_claim_budget_must_carry_the_evidences_uncertainty_declaration():
    evidence = _claim("ev-decl")
    other = dataclasses.replace(
        _budget(), declaration=T.declaration(numerical=T.quantified(2e-12))
    )
    decision, _n, _d = _decide(evidence, budget=other, tag="decl")
    channel = _result_for("uncertainty:numerical", decision)
    assert channel.satisfied is False
    assert "declaration" in channel.detail
    assert decision.verdict is not AssuranceVerdict.VALID
