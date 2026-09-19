"""Scientific Diagnostic Engine: blockers, assumptions, discrepancy and repair hypotheses."""

from __future__ import annotations

import copy

import pytest

from claims_support import assumption, t3_claim, t3_point
from engcore.claims import UncertaintyDemand, assess_claim
from engcore.claims.analysis.diagnostics import (
    AssumptionStatus,
    DiagnosticClass,
    DiscrepancyStatus,
    HypothesisKind,
    diagnose_assessment,
)
from engcore.claims.external_evidence import MeasurementRecord, TrustedExternalRegistry, TrustedPin
from engcore.mcp.capabilities import production_registry
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.evidence import SourceClass
from engcore.sria.uncertainty import UncertaintyChannel as C


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _mismatch_measurement() -> MeasurementRecord:
    return MeasurementRecord(
        "temperature_at_probe",
        Quantity(320.0, "kelvin"),
        Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(319.9, "kelvin"),
            upper=Quantity(320.1, "kelvin"),
            method="calibrated sensor interval",
            source_kind=UncertaintySource.MEASUREMENT,
        ),
        "calibration:2026-09",
        "lab:run-17",
        dict(t3_point()),
        "dataset-v1",
        independence_roots=("lab:run-17",),
    )


def test_model_form_gap_becomes_a_root_cause_and_a_non_guaranteed_corrective_action(registry) -> None:
    claim = t3_claim(
        assumptions=(assumption(),),
        uncertainty=UncertaintyDemand(frozenset({C.MODEL_FORM}), None, False),
    )
    assessment = assess_claim(claim, registry)
    before = copy.deepcopy(assessment.to_dict())

    report = diagnose_assessment(before, registry)

    assert report.verdict == "insufficient_evidence"
    assert report.primary_cause is not None
    assert report.primary_cause.cause_class is DiagnosticClass.MODEL_FORM
    assert any(action.action == "quantify_model_form" for action in report.corrective_actions)
    assert all(action.to_dict()["guarantees_fix"] is False for action in report.corrective_actions)
    assert report.assumptions.assumptions[0].status is AssumptionStatus.DECLARED_NOT_EVIDENCE
    assert assessment.to_dict() == before


def _numerical_t3_claim():
    return t3_claim(uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL}), None, False))


def test_admissible_model_data_mismatch_is_diagnosed_without_becoming_model_form_uq(registry) -> None:
    measurement = _mismatch_measurement()
    trust = TrustedExternalRegistry(
        (TrustedPin(measurement.digest, SourceClass.MEASUREMENT, "curator", "independent calibrated run"),)
    )
    assessment = assess_claim(_numerical_t3_claim(), registry, external=(measurement,), trust=trust)

    report = diagnose_assessment(assessment.to_dict(), registry)

    assert report.discrepancy.status is DiscrepancyStatus.OBSERVED_MISMATCH
    assert report.discrepancy.to_dict()["quantifies_model_form_uncertainty"] is False
    measurement_comparisons = [
        item for item in report.discrepancy.comparisons if item.source_class == "measurement"
    ]
    assert len(measurement_comparisons) == 1
    comparison = measurement_comparisons[0]
    assert comparison.outcome == "inconsistent"
    assert comparison.excess is not None and comparison.excess > 0
    assert any(item.cause_class is DiagnosticClass.MODEL_DATA_MISMATCH for item in report.root_causes)
    assert report.verdict == assessment.verdict.value


def test_sensitivity_can_rank_repair_hypotheses_but_never_establish_causality(registry) -> None:
    measurement = _mismatch_measurement()
    trust = TrustedExternalRegistry(
        (TrustedPin(measurement.digest, SourceClass.MEASUREMENT, "curator", "independent calibrated run"),)
    )
    assessment = assess_claim(_numerical_t3_claim(), registry, external=(measurement,), trust=trust)
    sensitivity = {
        "quantity": "temperature_at_probe",
        "parameters": [
            {
                "path": "material.conductivity",
                "derivative": 1.0,
                "normalized": 0.1,
                "problem": None,
            },
            {
                "path": "boundary.heat_transfer",
                "derivative": 5.0,
                "normalized": 0.8,
                "problem": None,
            },
        ],
    }

    report = diagnose_assessment(assessment.to_dict(), registry, sensitivity=sensitivity)

    assert [item.target for item in report.repair_hypotheses] == [
        "boundary.heat_transfer",
        "material.conductivity",
    ]
    assert all(item.kind is HypothesisKind.PARAMETER_CONTRIBUTOR for item in report.repair_hypotheses)
    assert all(item.to_dict()["causal_relationship_established"] is False for item in report.repair_hypotheses)
    assert all(item.to_dict()["guarantees_fix"] is False for item in report.repair_hypotheses)


def test_without_sensitivity_a_mismatch_stays_a_broad_testable_hypothesis(registry) -> None:
    measurement = _mismatch_measurement()
    trust = TrustedExternalRegistry(
        (TrustedPin(measurement.digest, SourceClass.MEASUREMENT, "curator", "independent calibrated run"),)
    )
    assessment = assess_claim(_numerical_t3_claim(), registry, external=(measurement,), trust=trust)

    report = diagnose_assessment(assessment.to_dict(), registry)

    assert len(report.repair_hypotheses) == 1
    assert report.repair_hypotheses[0].kind is HypothesisKind.MODEL_FORM_OR_PARAMETER
    assert "held-out validation data" in report.repair_hypotheses[0].proposed_test


def test_robustness_method_assumptions_are_visible_and_not_evidence(registry) -> None:
    assessment = assess_claim(t3_claim(), registry)
    robustness = {
        "assumptions": [
            "one input varied at a time",
            "uncertainty band is not re-quantified away from nominal",
        ]
    }
    report = diagnose_assessment(assessment.to_dict(), registry, robustness=robustness)
    entries = report.assumptions.assumptions
    assert [entry.assumption_id for entry in entries] == ["robustness:0", "robustness:1"]
    assert all(entry.to_dict()["can_grant_evidence"] is False for entry in entries)
