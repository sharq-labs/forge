"""Forgery and read-back: a serialized assessment is believed only when it re-derives.

Every mutation below edits one fact a reader relies on -- the claim, the plan,
the selected model, the reported value, a validation level, the uncertainty, the
decision context, the verdict -- and the reader must refuse the record rather
than return the edited answer.
"""

from __future__ import annotations

import copy
import json

import pytest

from claims_support import et_claim, t3_claim
from engcore.claims import AssessmentForgeryError, ClaimTarget, assess_claim, verify_assessment
from engcore.mcp.capabilities import production_registry
from engcore.scientific.units.quantity import Quantity


@pytest.fixture(scope="module")
def registry():
    return production_registry()


@pytest.fixture(scope="module")
def t3_record(registry):
    return assess_claim(t3_claim(), registry).to_dict()


@pytest.fixture(scope="module")
def refused_record(registry):
    point = t3_claim().operating_context
    point = {**point, "conductivity": Quantity(36.0, "watt / meter / kelvin")}
    return assess_claim(t3_claim(operating_context=point), registry).to_dict()


def test_an_untouched_record_reads_back_to_the_same_answer(registry, t3_record, refused_record) -> None:
    for record in (t3_record, refused_record, assess_claim(et_claim(), registry).to_dict()):
        back = verify_assessment(json.loads(json.dumps(record)), registry)
        assert back.to_dict() == record


def _report_values(w):
    return w["credibility"]["report"]["values"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda w: w.__setitem__("verdict", "contradicted"),
        lambda w: w["basis"].__setitem__("admissible", False),
        lambda w: w["claim"]["target"]["value"].__setitem__("magnitude", 305.0),
        lambda w: w["claim"]["evidence"].__setitem__("required_levels", ["dimensionally_valid"]),
        lambda w: w["claim"]["decision"].__setitem__("statement", "another use entirely"),
        lambda w: w["claim"]["discrepancy"].__setitem__("kind", "zero_declared"),
        lambda w: w["plan"]["content"]["models"][0].__setitem__("version", "9.9.9"),
        lambda w: w["plan"]["content"]["capability"].__setitem__("digest", "0" * 64),
        lambda w: w["result"]["value"].__setitem__("magnitude", 300.0),
        lambda w: next(iter(_report_values(w).values())).__setitem__("magnitude", 300.0),
        lambda w: w["validation"].__setitem__("attained", ["experimentally_validated"]),
        lambda w: w["credibility"]["report"]["verdict_qualifiers"].__setitem__("attained_levels", ["experimentally_validated"]),
        lambda w: w["uncertainty"].__setitem__("reported", {"kind": "standard"}),
        lambda w: w["evidence"].__setitem__("context_ref", "charter:" + "0" * 64 + "#decision:d-1"),
        lambda w: w["assurance"].__setitem__("unmet_obligations", ["confidence:claim_evidence_level:benchmark_validated"]),
        lambda w: w["explanation"].pop(),
        lambda w: w["repair_actions"].append({"kind": "supply_input", "target": "x"}),
        lambda w: w["execution"].__setitem__("binding_problems", ["invented"]),
    ],
    ids=[
        "verdict", "basis", "claim_target", "claim_levels", "decision", "discrepancy", "model_version",
        "capability_digest", "result_value", "report_value", "validation_levels", "report_levels",
        "uncertainty", "context_ref", "assurance_obligations", "explanation", "repairs", "binding",
    ],
)
def test_an_edited_record_is_refused(registry, t3_record, mutate) -> None:
    wire = copy.deepcopy(t3_record)
    mutate(wire)
    assert wire != t3_record
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(wire, registry)


def test_an_insufficient_record_cannot_be_promoted_by_editing_its_assurance(registry) -> None:
    from engcore.claims import EvidenceRequirement
    from engcore.scientific.results.validation import ValidationLevel

    record = assess_claim(et_claim(evidence=EvidenceRequirement((ValidationLevel.EXPERIMENTALLY_VALIDATED,))), registry).to_dict()
    assert record["verdict"] == "insufficient_evidence" and record["assurance"]["verdict"] == "inconclusive"
    forged = copy.deepcopy(record)
    forged["assurance"]["verdict"] = "valid"
    forged["assurance"]["unmet_obligations"] = []
    forged["basis"]["assurance"] = "valid"
    forged["basis"]["admissible"] = True
    forged["verdict"] = "supported"
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(forged, registry)


def test_an_unbound_report_cannot_be_declared_bound(registry) -> None:
    from dataclasses import replace

    from engcore.claims import CapabilityRegistry
    from engcore.mcp.capabilities import NAFEMS_T3_CAPABILITY_ID

    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor
    swapped = CapabilityRegistry(
        replace(d, executor=lambda case, *, run_id: genuine(case, run_id="another-run"))
        if d.capability_id == NAFEMS_T3_CAPABILITY_ID
        else d
        for d in registry
    )
    record = assess_claim(t3_claim(), swapped).to_dict()
    assert record["execution"]["binding_problems"]
    verify_assessment(copy.deepcopy(record), registry)  # honest record: re-derives
    forged = copy.deepcopy(record)
    forged["execution"]["binding_problems"] = []
    with pytest.raises(AssessmentForgeryError, match="binding"):
        verify_assessment(forged, registry)


def test_a_refused_claim_cannot_acquire_a_verdict_or_a_plan(registry, refused_record) -> None:
    forged = copy.deepcopy(refused_record)
    forged["verdict"] = "supported"
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(forged, registry)
    forged = copy.deepcopy(refused_record)
    forged["plan"] = assess_claim(t3_claim(), registry).to_dict()["plan"]
    with pytest.raises(AssessmentForgeryError, match="cannot carry a plan"):
        verify_assessment(forged, registry)


def test_evidence_for_one_claim_cannot_stand_in_for_another_with_the_same_number(registry, t3_record) -> None:
    """The same run and value, re-labelled for a different decision, is refused."""
    other = assess_claim(t3_claim(target=ClaimTarget(value=Quantity(309.8, "kelvin"))), registry).to_dict()
    forged = copy.deepcopy(other)
    forged["credibility"] = copy.deepcopy(t3_record["credibility"])
    forged["evidence"] = copy.deepcopy(t3_record["evidence"])
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(forged, registry)


def test_a_record_of_another_schema_is_refused(registry, t3_record) -> None:
    forged = copy.deepcopy(t3_record)
    forged["schema"] = "claim_assessment_record/2"
    with pytest.raises(AssessmentForgeryError, match="expected schema"):
        verify_assessment(forged, registry)
