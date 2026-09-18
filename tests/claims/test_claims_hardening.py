"""Adversarial cases across the layer: what a declaration, a caller or a run cannot grant itself."""

from __future__ import annotations

from dataclasses import replace

import pytest

from claims_support import et_claim, et_inputs, t3_claim
from engcore.claims import (
    AttainableLevel,
    CapabilityRegistry,
    CapabilityRun,
    CompilationStatus,
    EvidenceRequirement,
    GapKind,
    InstanceReport,
    RejectionReason,
    assess_claim,
    compile_claim,
)
from engcore.mcp.capabilities import NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _swap(registry, capability_id, **changes):
    return CapabilityRegistry(replace(d, **changes) if d.capability_id == capability_id else d for d in registry)


def test_evidence_that_loses_its_validation_level_never_improves_the_verdict(registry) -> None:
    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor

    def without_the_benchmark(case, *, run_id):
        (item,) = genuine(case, run_id=run_id).reports
        report = item.report
        kept = tuple(c for c in report.validation if c.name != "nafems_t3_external_benchmark")
        return CapabilityRun(reports=(InstanceReport(None, replace(report, validation=kept)),))

    full = assess_claim(t3_claim(), registry).to_dict()
    weaker = assess_claim(t3_claim(), _swap(registry, NAFEMS_T3_CAPABILITY_ID, executor=without_the_benchmark)).to_dict()
    assert full["verdict"] == "supported"
    assert "benchmark_validated" not in weaker["validation"]["attained"]
    assert weaker["verdict"] == "insufficient_evidence"


def test_a_declaration_that_overstates_what_it_attains_grants_nothing(registry) -> None:
    """The declared upper bound silences a predicted gap; only the run's report can attain a level."""
    t3 = registry.get(NAFEMS_T3_CAPABILITY_ID)
    boastful = t3.attainable_levels + (
        AttainableLevel(ValidationLevel.EXPERIMENTALLY_VALIDATED, "nafems_t3_external_benchmark", None, "claimed, not earned"),
    )
    swapped = _swap(registry, NAFEMS_T3_CAPABILITY_ID, attainable_levels=boastful)
    demand = EvidenceRequirement((ValidationLevel.EXPERIMENTALLY_VALIDATED,))
    compiled = compile_claim(t3_claim(evidence=demand), swapped)
    assert compiled.status is CompilationStatus.READY
    assert GapKind.LEVEL_UNATTAINABLE not in {g.kind for g in compiled.predicted_gaps}
    record = assess_claim(t3_claim(evidence=demand), swapped).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["validation"]["missing_required"] == ["experimentally_validated"]


def test_a_caller_cannot_pose_as_a_derived_quantity(registry) -> None:
    inputs = et_inputs()
    inputs["stages[0].body.applicability.biot_number"] = Quantity(0.01, "dimensionless")
    compiled = compile_claim(et_claim(known_inputs=inputs), registry)
    assert compiled.status is CompilationStatus.UNSUPPORTED_CAPABILITY
    (candidate,) = [c for c in compiled.selection.candidates if c.capability_id == "system.electrothermal"]
    assert RejectionReason.UNACCEPTED_INPUT in {r for r, _ in candidate.rejections}


def test_a_caller_cannot_supply_the_answer_as_an_input(registry) -> None:
    inputs = et_inputs()
    inputs["stages[0].body.final_temperature"] = Quantity(300.0, "kelvin")
    record = assess_claim(et_claim(known_inputs=inputs), registry).to_dict()
    assert record["verdict"] == "insufficient_evidence" and record["status"] == "not_executed"


def test_a_report_whose_checks_were_stripped_of_every_level_cannot_support_anything(registry) -> None:
    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor

    def unchecked(case, *, run_id):
        (item,) = genuine(case, run_id=run_id).reports
        return CapabilityRun(reports=(InstanceReport(None, replace(item.report, validation=())),))

    record = assess_claim(t3_claim(), _swap(registry, NAFEMS_T3_CAPABILITY_ID, executor=unchecked)).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["credibility"]["verdict"] == "insufficient_evidence"
