"""Audit stream "results": RES-04 -- validity assessments bound to the model's declared conditions.

Written against the unfixed boundary and seen failing first.

``ModelValidityRecord`` checked an assessment's status against the assessment's OWN condition lists and nothing
else, so a hand-authored record for a real model -- ``satisfied=("condition_this_model_does_not_have",)`` -- was
IN_DOMAIN, and a report built on it was SUPPORTED. So was an assessment naming one real condition and omitting the
ones that were violated. Where the model is resolvable, the assessment must now account for exactly the conditions
its validity domain declares; where it is not, the record says so and the report cannot be SUPPORTED.
"""

from __future__ import annotations

import json

import pytest

from engcore.domains.battery.models import CONSTANT_CURRENT_RUNTIME_MODEL
from engcore.mcp.errors import CredibilityEvidenceError
from engcore.mcp.evidence import (
    EVIDENCE_PACKAGE_SCHEMA,
    MODEL_VALIDITY_SCHEMA,
    CredibilityEvidenceReport,
    CredibilityVerdict,
    ModelValidityRecord,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
)
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity

MODEL = CONSTANT_CURRENT_RUNTIME_MODEL
CONDITIONS = tuple(c.name for c in MODEL.validity.conditions)
SOLVER = SolverIdentity("anything", "1")
#: A passing check that earns a level, so the control can reach SUPPORTED. The
#: audit probe used EXPERIMENTALLY_VALIDATED; since VAL-01 that level needs a
#: verifiable issuer record a hand-built check cannot carry, and the finding
#: under test is about validity conditions, not validation levels -- so the
#: fixture earns a level that a residual against a tolerance can establish.
PASSED = ValidationCheck(
    name="analytic_reference",
    outcome=ValidationOutcome.PASS,
    establishes=ValidationLevel.ANALYTICALLY_VERIFIED,
    residual=1e-9,
    tolerance=1e-6,
)


def _provenance(model_id=MODEL.model_id, version=MODEL.version):
    return ProvenanceRecord(
        run_id="forged-run",
        bindings=(ExecutionBinding(model=ModelReference(model_id, version), solver=SOLVER),),
    )


def _record(assessment, model_id=MODEL.model_id, version=MODEL.version):
    return ModelValidityRecord(model_id=model_id, version=version, assessment=assessment)


def _report(record, provenance=None):
    return CredibilityEvidenceReport(
        run_id="forged-run",
        values={"T": Quantity(300.0, "K")},
        provenance=provenance or _provenance(record.model_id, record.version),
        validity=(record,),
        validation=(PASSED,),
    )


def test_res04_the_control_is_supported_so_the_refusals_below_mean_something():
    honest = ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=CONDITIONS)
    assert _report(_record(honest)).verdict is CredibilityVerdict.SUPPORTED


def test_res04_a_condition_the_model_does_not_declare_is_refused():
    fabricated = ValidityAssessment(
        status=ValidityStatus.IN_DOMAIN, satisfied=("condition_this_model_does_not_have",)
    )
    with pytest.raises(CredibilityEvidenceError, match="condition_this_model_does_not_have"):
        _record(fabricated)


def test_res04_the_hand_authored_payload_from_the_probe_is_refused_on_read():
    payload = {
        "schema": EVIDENCE_PACKAGE_SCHEMA,
        "run_id": "forged-run",
        "values": {"T": Quantity(300.0, "K").to_dict()},
        "provenance": _provenance().to_dict(),
        "validity": [
            {
                "schema": MODEL_VALIDITY_SCHEMA,
                "model_id": MODEL.model_id,
                "version": MODEL.version,
                "assessment": ValidityAssessment(
                    status=ValidityStatus.IN_DOMAIN,
                    satisfied=("condition_this_model_does_not_have",),
                ).to_dict(),
            }
        ],
        "validation": [PASSED.to_dict()],
        "required_levels": ["analytically_verified"],
    }
    with pytest.raises(CredibilityEvidenceError):
        CredibilityEvidenceReport.from_dict(json.loads(json.dumps(payload)))


def test_res04_an_assessment_omitting_the_conditions_it_did_not_like_is_refused():
    partial = ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=CONDITIONS[:1])
    with pytest.raises(CredibilityEvidenceError, match="does not account for"):
        _record(partial)


def test_res04_a_condition_reported_twice_is_refused():
    doubled = ValidityAssessment(
        status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
        satisfied=CONDITIONS,
        violated=CONDITIONS[:1],
    )
    with pytest.raises(CredibilityEvidenceError, match="more than once"):
        _record(doubled)


def test_res04_what_the_model_domain_itself_produces_is_accepted():
    assessment = MODEL.validity.assess({})
    record = _record(assessment)
    assert record.model_resolved is True
    assert set(record.assessment.unknown) == set(CONDITIONS)


def test_res04_an_unresolvable_model_says_so_and_cannot_be_supported():
    record = _record(
        ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=("anything",)),
        model_id="not.a.registered.model",
        version="1",
    )
    assert record.model_resolved is False
    assert record.to_dict()["model_resolved"] is False
    report = _report(record)
    assert report.unresolved_models == (("not.a.registered.model", "1"),)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["verdict_qualifiers"]["unresolved_models"] == [["not.a.registered.model", "1"]]
    assert CredibilityEvidenceReport.from_dict(payload).verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_res04_a_result_carrying_a_fabricated_assessment_cannot_become_evidence():
    provenance = _provenance()
    result = ScientificResult(
        result_id="x",
        values={"T": Quantity(300.0, "K")},
        provenance=provenance,
        models=(MODEL.key,),
        validity={
            MODEL.model_id: ValidityAssessment(
                status=ValidityStatus.IN_DOMAIN, satisfied=("condition_this_model_does_not_have",)
            )
        },
    )
    with pytest.raises(CredibilityEvidenceError, match="condition_this_model_does_not_have"):
        CredibilityEvidenceReport.from_result(result)
