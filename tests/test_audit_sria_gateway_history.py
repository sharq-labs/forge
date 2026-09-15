"""Audit stream sria — SRIA-05: one evidence id names one record; history is kept.

Probe E8 admitted ``ev-W``, invalidated it, then admitted a *different* record
under the same ``evidence_id`` with a fresh decision. ``ScientificBelief`` keyed
its store by evidence id and overwrote the entry, so the audit log showed only
the new accepted claim and the invalidation vanished.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.scientific import Quantity

from engcore.sria import AdmissionError, BeliefWriteViolation, EvidenceStatus
from engcore.sria.assurance import AssuranceVerdict

import tests.test_sria_m3_assurance as T
from tests.test_audit_sria_assurance_binding import (
    _budget,
    _domain_critic,
    _honest_assessments,
    _stack,
    _voltage_evidence,
)
from engcore.sria.assurance import NumericalCritic


def _accept(arbiter, gateway, evidence, tag):
    # The critics assess a result holding exactly the claimed value, so the
    # assessments back the claim (audit sria follow-up, claim binding).
    result = dataclasses.replace(
        T.good_result("res-W"),
        values={"V:mid": Quantity(float(evidence.claim_payload["value"]), "volt")},
    )
    numerical, domain = _honest_assessments(arbiter, result, evidence, tag=tag)
    decision = arbiter.decide(
        decision_id=f"dec-{tag}", evidence=evidence, assessments=[numerical, domain],
        obligations=T.standard_obligations(), budget=_budget(),
    )
    assert decision.verdict is AssuranceVerdict.VALID, decision.reasons
    assessed = evidence
    if assessed.status is not EvidenceStatus.ASSESSED:
        assessed = assessed.with_assessment(numerical.to_evidence_assessment())
    return assessed.admit(arbiter.authorize_admission(decision, assessed))


def test_sria05_e8_same_id_different_record_is_refused_and_history_survives():
    _authority, arbiter, gateway = _stack("e8", NumericalCritic(), _domain_critic())
    first = _accept(arbiter, gateway, _voltage_evidence("ev-W", 1.0), "w1")
    gateway.submit(first)
    gateway.update_standing(first.invalidate("refuted by measurement"))

    second = _accept(arbiter, gateway, _voltage_evidence("ev-W", 2.0), "w2")
    assert second.record_hash != first.record_hash
    with pytest.raises((BeliefWriteViolation, AdmissionError)):
        gateway.submit(second)

    audit = gateway.belief.audit_log()
    assert [(e.evidence_id, e.status, dict(e.claim_payload)["value"]) for e in audit] == [
        ("ev-W", EvidenceStatus.INVALID, 1.0)
    ]
    assert len(gateway.belief) == 0


def test_sria05_history_keeps_every_recorded_standing():
    _authority, arbiter, gateway = _stack("hist", NumericalCritic(), _domain_critic())
    first = _accept(arbiter, gateway, _voltage_evidence("ev-H", 1.0), "h1")
    gateway.submit(first)
    gateway.update_standing(first.suspend("pending review"))
    statuses = [e.status for e in gateway.belief.history()]
    assert statuses == [EvidenceStatus.ACCEPTED, EvidenceStatus.SUSPENDED]


def test_sria05_an_invalidated_record_cannot_be_readmitted_by_a_fresh_decision():
    _authority, arbiter, gateway = _stack("inv", NumericalCritic(), _domain_critic())
    evidence = _voltage_evidence("ev-I", 1.0)
    first = _accept(arbiter, gateway, evidence, "i1")
    gateway.submit(first)
    gateway.update_standing(first.invalidate("unit error found"))

    # The same record, re-assessed and re-decided, is still the record a
    # scientific authority invalidated. INVALID is terminal.
    again = _accept(arbiter, gateway, evidence, "i2")
    assert again.record_hash == first.record_hash
    with pytest.raises((BeliefWriteViolation, AdmissionError)):
        gateway.submit(again)
    assert gateway.belief.audit_log()[0].status is EvidenceStatus.INVALID


def test_sria05_an_active_record_cannot_be_replaced_under_its_id():
    """No invalidation involved: a live record's id cannot be reused either."""
    _authority, arbiter, gateway = _stack("live", NumericalCritic(), _domain_critic())
    first = _accept(arbiter, gateway, _voltage_evidence("ev-L", 1.0), "l1")
    gateway.submit(first)
    replacement = _accept(arbiter, gateway, _voltage_evidence("ev-L", 2.0), "l2")
    with pytest.raises(BeliefWriteViolation):
        gateway.submit(replacement)
    [entry] = gateway.belief.audit_log()
    assert entry.record_hash == first.record_hash
    assert dict(entry.claim_payload)["value"] == 1.0
    assert [e.record_hash for e in gateway.belief.history()] == [first.record_hash]

