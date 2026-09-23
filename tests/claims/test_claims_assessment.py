"""CORE-10 / CORE-13: generic claim assessment, end to end on real systems.

The one distinction this file exists to hold: a claim that admissible evidence
shows FALSE is CONTRADICTED; a claim this execution cannot establish either way
is INSUFFICIENT_EVIDENCE -- however its reported number compares.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from claims_support import battery_inputs, claim, et_claim, et_inputs, payload, t3_claim, t3_point
from engcore.claims import (
    CapabilityExecutionRefused,
    CapabilityRegistry,
    ClaimTarget,
    ClaimVerdict,
    EvidenceRequirement,
    QuantityOfInterest,
    UncertaintyDemand,
    assess_claim,
    resolve,
)
from engcore.mcp.capabilities import NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import DiscrepancyKind, ModelDiscrepancy, UncertaintyChannel

T3_VALUE_K = 309.75  # the NAFEMS target, 36.6 degC; the run lands within 0.001 K of it


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _kinds(record) -> set[str]:
    return {item["kind"] for item in record["explanation"]}


def _codes(record) -> set[str]:
    return {item["code"] for item in record["explanation"]}


# ---------------------------------------------------------------------------
# SUPPORTED and CONTRADICTED need admissible evidence -- the same bar
# ---------------------------------------------------------------------------


def test_a_t3_claim_at_the_benchmark_point_is_supported_with_benchmark_validation(registry) -> None:
    record = assess_claim(t3_claim(), registry).to_dict()
    assert record["verdict"] == "supported" and record["status"] == "assessed"
    assert record["validation"]["attained"] == ["benchmark_validated"]
    assert record["validation"]["evidence_basis"] == "VALIDATED"
    assert record["assurance"]["verdict"] == "valid" and record["assurance"]["unmet_obligations"] == []
    assert record["comparison"]["rule"] == "point" and record["comparison"]["outcome"] == "satisfied"
    assert record["basis"]["admissible"] is True


def test_the_value_compared_is_the_reports_never_the_callers(registry) -> None:
    assessed = assess_claim(t3_claim(), registry)
    record = assessed.to_dict()
    reported = assessed.report.values["temperature_at_probe"]
    assert record["result"]["value"] == reported.to_dict()
    assert record["comparison"]["value"] == reported.to_dict()
    assert record["evidence"]["context_ref"] == assessed.plan.context_ref


def test_a_t3_claim_the_benchmark_run_violates_is_contradicted(registry) -> None:
    record = assess_claim(t3_claim(target=ClaimTarget(value=Quantity(305.0, "kelvin"))), registry).to_dict()
    assert record["verdict"] == "contradicted"
    assert "contradiction" in _kinds(record)
    assert record["basis"]["admissible"] is True


def test_an_electrothermal_threshold_claim_is_supported_or_contradicted_by_its_bound(registry) -> None:
    supported = assess_claim(et_claim(), registry).to_dict()
    assert supported["verdict"] == "supported"
    assert supported["validation"]["evidence_basis"] == "VERIFICATION_ONLY"
    assert "validation.verification_only" in _codes(supported)  # support on verification is said to be only that
    contradicted = assess_claim(et_claim(target=ClaimTarget(value=Quantity(310.0, "kelvin"))), registry).to_dict()
    assert contradicted["verdict"] == "contradicted"


# ---------------------------------------------------------------------------
# "false" is not "cannot establish"
# ---------------------------------------------------------------------------


def test_a_violated_comparison_without_the_required_evidence_is_not_a_contradiction(registry) -> None:
    record = assess_claim(
        et_claim(
            target=ClaimTarget(value=Quantity(310.0, "kelvin")),
            evidence=EvidenceRequirement((ValidationLevel.EXPERIMENTALLY_VALIDATED,)),
        ),
        registry,
    ).to_dict()
    assert record["comparison"]["outcome"] == "violated"
    assert record["verdict"] == "insufficient_evidence"
    assert "contradiction" not in _kinds(record)
    assert "comparison.violated_inadmissible" in _codes(record)
    assert "experimentally_validated" in record["validation"]["missing_required"]


def test_verification_cannot_satisfy_a_validation_requirement(registry) -> None:
    record = assess_claim(et_claim(evidence=EvidenceRequirement((ValidationLevel.BENCHMARK_VALIDATED,))), registry).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["validation"]["missing_required"] == ["benchmark_validated"]
    assert any(r["kind"] == "provide_evidence" and r["target"] == "benchmark_validated" for r in record["repair_actions"])


def test_a_model_outside_its_domain_never_contradicts_the_claim(registry) -> None:
    point = t3_point()
    point["conductivity"] = Quantity(36.0, "watt / meter / kelvin")
    # A target the benchmark value would violate: still not a contradiction.
    record = assess_claim(t3_claim(operating_context=point, target=ClaimTarget(value=Quantity(305.0, "kelvin"))), registry).to_dict()
    assert record["verdict"] == "insufficient_evidence" and record["status"] == "not_executed"
    assert "contradiction" not in _kinds(record)
    assert "selection.outside_validity" in _codes(record)
    assert any(r["kind"] == "move_inside_validity" for r in record["repair_actions"])


def test_a_complete_battery_claim_is_supported_when_thermal_applicability_is_declared(registry) -> None:
    record = assess_claim(
        claim(
            qoi=QuantityOfInterest("terminal_voltage", "volt"),
            target=ClaimTarget(value=Quantity(3.0, "volt")),
            operator=ConstraintOperator.GREATER_EQUAL,
            operating_context={},
            known_inputs=battery_inputs(),
        ),
        registry,
    ).to_dict()
    assert record["verdict"] == "supported"
    assert record["status"] == "executed"
    assert "selection.validity_unassessable" not in _codes(record)


def test_a_demanded_uncertainty_channel_that_is_unknown_leaves_the_claim_undecided(registry) -> None:
    # The electrothermal capability declares no refinement study, so NUMERICAL stays UNKNOWN there.
    record = assess_claim(et_claim(uncertainty=UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), 2.0, False)), registry).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["comparison"]["outcome"] == "not_evaluated"
    assert record["uncertainty"]["channels"] == {"numerical": False}
    assert "assurance.unmet" in _codes(record) and "uncertainty:numerical" in record["assurance"]["unmet_obligations"]


def test_a_demanded_discrepancy_needs_support_that_unknown_and_bare_zero_do_not_give(registry) -> None:
    demand = UncertaintyDemand(frozenset(), None, True)
    for kind in (DiscrepancyKind.UNKNOWN, DiscrepancyKind.ZERO_DECLARED):
        record = assess_claim(t3_claim(uncertainty=demand, discrepancy=ModelDiscrepancy(kind, rationale="stated")), registry).to_dict()
        assert record["verdict"] == "insufficient_evidence", kind
        assert record["assurance"]["discrepancy_check"]["outcome"] != "pass"
    prior = ModelDiscrepancy(DiscrepancyKind.CONSTRAINED_PRIOR, reference="doi:10.0/t3-prior", rationale="bounded")
    record = assess_claim(t3_claim(uncertainty=demand, discrepancy=prior), registry).to_dict()
    assert record["verdict"] == "supported"


def test_a_claim_that_cannot_run_is_insufficient_with_its_repairs(registry) -> None:
    inputs = et_inputs()
    del inputs["stages[0].body.heat_capacity"]
    record = assess_claim(et_claim(known_inputs=inputs), registry).to_dict()
    assert record["verdict"] == "insufficient_evidence" and record["status"] == "not_executed"
    assert record["plan"] is None and record["execution"] is None
    assert [r["target"] for r in record["repair_actions"] if r["kind"] == "supply_input"] == ["stages[0].body.heat_capacity"]


def test_a_malformed_claim_is_answered_not_raised(registry) -> None:
    wire = payload()
    wire["probability"] = 0.99
    record = assess_claim(wire, registry).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["compilation"]["status"] == "refused"
    assert record["claim"] is None


# ---------------------------------------------------------------------------
# Execution that misbehaves
# ---------------------------------------------------------------------------


def _with_executor(registry, capability_id, executor):
    return CapabilityRegistry(replace(d, executor=executor) if d.capability_id == capability_id else d for d in registry)


def test_a_system_refusal_is_recorded_and_insufficient(registry) -> None:
    def refuse(case, *, run_id):
        raise CapabilityExecutionRefused("the system would not run this case")

    record = assess_claim(t3_claim(), _with_executor(registry, NAFEMS_T3_CAPABILITY_ID, refuse)).to_dict()
    assert record["execution"]["outcome"] == "refused_by_system"
    assert record["verdict"] == "insufficient_evidence"
    assert "execution.refused" in _codes(record)


def test_a_report_from_another_run_is_never_evidence(registry) -> None:
    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor

    def elsewhere(case, *, run_id):
        return genuine(case, run_id="some-other-run")

    record = assess_claim(t3_claim(), _with_executor(registry, NAFEMS_T3_CAPABILITY_ID, elsewhere)).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["execution"]["binding_problems"]
    assert record["evidence"] is None and record["assurance"] is None
    assert "execution.unbound" in _codes(record)


def test_an_unexpected_defect_is_not_disguised_as_insufficiency(registry) -> None:
    def broken(case, *, run_id):
        raise ZeroDivisionError("a defect")

    with pytest.raises(ZeroDivisionError):
        assess_claim(t3_claim(), _with_executor(registry, NAFEMS_T3_CAPABILITY_ID, broken))


# ---------------------------------------------------------------------------
# Monotonicity: less evidence, more requirements, never a firmer answer
# ---------------------------------------------------------------------------

_RANK = {"insufficient_evidence": 0, "supported": 1, "contradicted": 1}


@pytest.mark.parametrize(
    "stricter",
    [
        {"evidence": EvidenceRequirement((ValidationLevel.BENCHMARK_VALIDATED, ValidationLevel.CROSS_SOLVER_VALIDATED))},
        {"evidence": EvidenceRequirement((ValidationLevel.BENCHMARK_VALIDATED, ValidationLevel.EXPERIMENTALLY_VALIDATED))},
        {"uncertainty": UncertaintyDemand(frozenset({UncertaintyChannel.MODEL_FORM}), 2.0, False)},
        {"uncertainty": UncertaintyDemand(frozenset(), None, True)},
    ],
    ids=["cross_solver", "experimental", "model_form_channel", "supported_discrepancy"],
)
def test_asking_for_more_evidence_never_firms_up_the_answer(registry, stricter) -> None:
    for target in (309.75, 305.0):
        base = assess_claim(t3_claim(target=ClaimTarget(value=Quantity(target, "kelvin"))), registry).to_dict()
        strict = assess_claim(t3_claim(target=ClaimTarget(value=Quantity(target, "kelvin")), **stricter), registry).to_dict()
        assert _RANK[strict["verdict"]] <= _RANK[base["verdict"]]
        assert strict["verdict"] in (base["verdict"], "insufficient_evidence")


def test_removing_a_discrepancy_declaration_never_firms_up_the_answer(registry) -> None:
    demand = UncertaintyDemand(frozenset(), None, True)
    prior = ModelDiscrepancy(DiscrepancyKind.CONSTRAINED_PRIOR, reference="doi:10.0/t3-prior", rationale="bounded")
    unknown = ModelDiscrepancy(DiscrepancyKind.UNKNOWN, rationale="not quantified")
    declared = assess_claim(t3_claim(uncertainty=demand, discrepancy=prior), registry).to_dict()
    removed = assess_claim(t3_claim(uncertainty=demand, discrepancy=unknown), registry).to_dict()
    assert _RANK[removed["verdict"]] <= _RANK[declared["verdict"]]


# ---------------------------------------------------------------------------
# The record: complete, traceable, and explained only by what it holds
# ---------------------------------------------------------------------------


def test_an_assessed_record_answers_every_question_a_reader_asks(registry) -> None:
    record = assess_claim(t3_claim(), registry).to_dict()
    for section in (
        "claim", "compilation", "plan", "execution", "result", "validity", "verification", "validation",
        "uncertainty", "evidence", "assurance", "credibility", "comparison", "basis", "verdict",
        "reasons", "limitations", "missing_evidence", "repair_actions", "explanation",
    ):
        assert section in record, section
    assert record["plan"]["content"]["capability"]["capability_id"] == NAFEMS_T3_CAPABILITY_ID
    assert record["execution"]["run_id"] == record["plan"]["content"]["run_id"]
    assert record["validity"][0]["model_id"] == "thermal.nafems_t3.transient_heat_1d"
    assert record["uncertainty"]["reported"]["kind"] == "unknown"
    assert "uncertainty.reported_unknown" in _codes(record)  # unknown is shown, never zero
    json.dumps(record)


@pytest.mark.parametrize(
    "builder",
    [
        lambda: t3_claim(),
        lambda: t3_claim(target=ClaimTarget(value=Quantity(305.0, "kelvin"))),
        lambda: et_claim(evidence=EvidenceRequirement((ValidationLevel.EXPERIMENTALLY_VALIDATED,))),
        lambda: t3_claim(operating_context={**t3_point(), "conductivity": Quantity(36.0, "watt / meter / kelvin")}),
        lambda: et_claim(known_inputs={k: v for k, v in et_inputs().items() if ".applicability." not in k}),
    ],
    ids=["supported", "contradicted", "missing_level", "outside", "unknown_applicability"],
)
def test_every_explanation_item_points_at_a_value_the_record_holds(registry, builder) -> None:
    record = assess_claim(builder(), registry).to_dict()
    assert record["explanation"]
    for item in record["explanation"]:
        resolve(record, item["source"])  # raises when an item restates nothing
    for reason in record["reasons"]:
        resolve(record, reason["source"])


def test_unknown_applicability_after_the_run_is_repaired_from_the_declarations(registry) -> None:
    inputs = {k: v for k, v in et_inputs().items() if ".applicability." not in k}
    record = assess_claim(et_claim(known_inputs=inputs), registry).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["credibility"]["verdict"] == "insufficient_evidence"
    supply = [r for r in record["repair_actions"] if r["kind"] == "supply_validity_evidence"]
    assert supply and all(r["detail"].get("observed_unknown") for r in supply)
    assert any(r["target"] == "stages[0].body.applicability.surface_area" for r in supply)


def test_the_mcp_tool_returns_the_same_record(registry) -> None:
    from engcore.mcp.server import assess_scientific_claim

    record = assess_scientific_claim(t3_claim().to_dict())
    assert record == assess_claim(t3_claim(), registry).to_dict()
