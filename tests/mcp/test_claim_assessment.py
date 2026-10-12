"""The MCP claim tools decide only through the canonical claim path (Trust Repair Pass 1, R3-02).

Review 3 found ``mcp/claim_assessment.py`` running its own SRIA decision. That
decision read report-wide levels, compared nothing, and skipped uncertainty,
discrepancy and policy. On the same input it returned ``valid`` where
``engcore.claims.assess_claim`` returned INSUFFICIENT_EVIDENCE or CONTRADICTED.
Every case below holds the two paths to the same record.
"""

from __future__ import annotations

import ast
import copy
import pathlib

import pytest

from claims_support import battery_inputs, claim, et_inputs
from engcore.claims import ClaimTarget, DecisionBinding, EvidenceRequirement, QuantityOfInterest, assess_claim
from engcore.mcp import example_electrothermal_payload, run_electrothermal_case
from engcore.mcp.battery import example_battery_payload, run_battery_case
from engcore.mcp.capabilities import production_registry
from engcore.mcp.claim_assessment import (
    CLAIM_ASSESSMENT_ERROR_SCHEMA,
    ClaimAssessmentError,
    assess_claim_request,
    claim_from_case_request,
)
from engcore.mcp.server import assess_claim as assess_claim_tool
from engcore.mcp.server import assess_scientific_claim
from engcore.scientific.results.validation import ValidationLevel as L
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import DiscrepancyKind, ModelDiscrepancy

REGISTRY = production_registry()
DISCREPANCY = {"kind": "unknown", "rationale": "model-form discrepancy has not been quantified for this claim"}
SOURCE = pathlib.Path(__file__).resolve().parents[2] / "src" / "engcore" / "mcp" / "claim_assessment.py"


POINT_COMPARISON = {"required_channels": [], "coverage_factor": None, "require_supported_discrepancy": False}


def _request(system, case, quantity, level, target, *, operator="<", tolerance=None,
             statement="Rely on this quantity.", decision="d-1"):
    comparison = {"operator": operator, "target": target.to_dict()}
    if tolerance is not None:
        comparison["tolerance"] = tolerance.to_dict()
    return {
        "system": system,
        "case": copy.deepcopy(case),
        "quantity_name": quantity,
        "decision": {"id": decision, "statement": statement},
        "required_levels": [level.value],
        "discrepancy": dict(DISCREPANCY),
        "comparison": comparison,
        "uncertainty": dict(POINT_COMPARISON),
    }


def _canonical(system, inputs, quantity, level, target, *, operator="<", tolerance=None,
               statement="Rely on this quantity.", decision="d-1"):
    from engcore.claims import ClaimKind
    from engcore.scientific.ir.constraints import ConstraintOperator

    op = ConstraintOperator(operator)
    return assess_claim(
        claim(
            claim_id=f"mcp-assess:{system}:{decision}",
            statement=statement,
            kind=ClaimKind.TOLERANCE_BAND if op is ConstraintOperator.EQUAL else ClaimKind.THRESHOLD,
            operator=op,
            tolerance=tolerance,
            operating_context={},
            known_inputs=inputs,
            qoi=QuantityOfInterest(quantity, str(target.units)),
            target=ClaimTarget(value=target),
            decision=DecisionBinding(decision, statement),
            evidence=EvidenceRequirement((level,)),
            discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.UNKNOWN, rationale=DISCREPANCY["rationale"]),
        ),
        REGISTRY,
    ).to_dict()


ET_CASE = example_electrothermal_payload()
ET_REPORT = run_electrothermal_case(copy.deepcopy(ET_CASE)).reports[0]
BATTERY_CASE = example_battery_payload()
BATTERY_REPORT = run_battery_case(copy.deepcopy(BATTERY_CASE)).report


def _far_target(report, quantity):
    value = report.values[quantity]
    return Quantity(abs(value.magnitude) * 10 + 1.0, str(value.units))


# The six level-scoping divergences Review 3 reproduced. Each run attains the level for SOME quantity and
# never for this one, so the canonical answer is INSUFFICIENT_EVIDENCE and MCP must not say otherwise.
PARITY = [
    ("electrothermal", "time_constant", L.ANALYTICALLY_VERIFIED),
    ("battery", "terminal_voltage", L.ANALYTICALLY_VERIFIED),
    ("battery", "open_circuit_voltage", L.ANALYTICALLY_VERIFIED),
    ("battery", "heat_generation", L.ANALYTICALLY_VERIFIED),
    ("battery", "final_state_of_charge", L.ANALYTICALLY_VERIFIED),
    ("battery", "final_temperature", L.DIMENSIONALLY_VALID),
]


@pytest.mark.parametrize("system, quantity, level", PARITY, ids=[f"{s}:{q}:{l.value}" for s, q, l in PARITY])
def test_a_level_attained_for_another_quantity_is_never_borrowed(system, quantity, level):
    case, report, inputs = (
        (ET_CASE, ET_REPORT, et_inputs()) if system == "electrothermal" else (BATTERY_CASE, BATTERY_REPORT, battery_inputs())
    )
    assert level in report.attained_levels  # the run DID attain it, for another quantity
    target = _far_target(report, quantity)
    mcp = assess_claim_tool(_request(system, case, quantity, level, target))
    canonical = _canonical(system, inputs, quantity, level, target)
    assert canonical["verdict"] == "insufficient_evidence"
    assert mcp == canonical
    assert mcp["assurance"]["verdict"] != "valid"


def test_a_false_decision_statement_is_contradicted_not_valid():
    """Review 3 D1: the run gives 319.28 K, and the decision says "below 310 K"."""
    statement = "The body stays below 310 K at the end of the interval; accept the part."
    target = Quantity(310.0, "kelvin")
    mcp = assess_claim_tool(_request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, target, statement=statement))
    canonical = _canonical("electrothermal", et_inputs(), "final_temperature", L.ANALYTICALLY_VERIFIED, target, statement=statement)
    assert mcp == canonical
    assert mcp["verdict"] == "contradicted" and mcp["comparison"]["outcome"] == "violated"
    assert mcp["result"]["value"]["magnitude"] > 310.0


def test_a_true_claim_is_supported_by_both_paths_identically():
    target = Quantity(353.15, "kelvin")
    mcp = assess_claim_request(_request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, target))
    canonical = _canonical("electrothermal", et_inputs(), "final_temperature", L.ANALYTICALLY_VERIFIED, target)
    assert mcp == canonical and mcp["verdict"] == "supported"


@pytest.mark.parametrize("operator, target, tolerance", [
    ("==", Quantity(319.28, "kelvin"), Quantity(0.5, "kelvin")),
    (">", Quantity(300.0, "kelvin"), None),
    ("<", Quantity(80.0, "degree_Celsius"), None),
    ("<=", Quantity(40.0, "degree_Celsius"), None),
], ids=["band", "greater", "degC-less", "degC-less-equal"])
def test_every_comparison_shape_matches_the_canonical_path(operator, target, tolerance):
    mcp = assess_claim_tool(_request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, target,
                                     operator=operator, tolerance=tolerance))
    canonical = _canonical("electrothermal", et_inputs(), "final_temperature", L.ANALYTICALLY_VERIFIED, target,
                           operator=operator, tolerance=tolerance)
    assert mcp == canonical and mcp["verdict"] in ("supported", "contradicted")


def test_the_uncertainty_demand_is_never_made_for_the_caller():
    request = _request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, Quantity(353.15, "kelvin"))
    request.pop("uncertainty")
    with pytest.raises(ClaimAssessmentError, match="uncertainty is required"):
        assess_claim_request(request)
    request["uncertainty"] = {"required_channels": ["numerical"], "coverage_factor": None, "require_supported_discrepancy": False}
    record = assess_claim_request(request)
    assert record["uncertainty"]["demanded"] == ["numerical"]
    assert record["verdict"] != "supported"  # no quantified NUMERICAL channel: UNKNOWN, never zero


def test_an_answer_routed_to_another_capability_is_refused(monkeypatch):
    from engcore.mcp import claim_assessment as module

    genuine = module.assess_structured_claim

    def rerouted(claim, **kw):
        record = genuine(claim, **kw)
        record["plan"]["content"]["capability"]["capability_id"] = "benchmark.nafems_t3"
        return record

    monkeypatch.setattr(module, "assess_structured_claim", rerouted)
    request = _request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, Quantity(353.15, "kelvin"))
    with pytest.raises(ClaimAssessmentError, match="routed to"):
        assess_claim_request(request)


def test_an_insufficient_credibility_report_stays_insufficient():
    case = copy.deepcopy(BATTERY_CASE)
    case["cell"]["limits"].pop("continuous_discharge_c_rate")
    target = _far_target(BATTERY_REPORT, "terminal_voltage")
    mcp = assess_claim_request(_request("battery", case, "terminal_voltage", L.DIMENSIONALLY_VALID, target))
    assert mcp["verdict"] == "insufficient_evidence"
    assert mcp["assurance"] is None or mcp["assurance"]["verdict"] != "valid"


def test_the_claim_shape_is_exactly_assess_scientific_claim():
    payload = claim(operating_context={}, known_inputs=et_inputs()).to_dict()
    assert assess_claim_request({"claim": payload}) == assess_scientific_claim(payload)


def test_a_free_text_statement_without_a_comparison_is_refused():
    request = _request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, Quantity(310.0, "kelvin"))
    request.pop("comparison")
    with pytest.raises(ClaimAssessmentError, match="comparison is required"):
        assess_claim_request(request)
    refused = assess_claim_tool(request)
    assert refused["schema"] == CLAIM_ASSESSMENT_ERROR_SCHEMA and refused["status"] == "refused"
    assert "assurance" not in refused and "verdict" not in refused


def test_report_index_is_refused_rather_than_mapped_to_an_instance():
    request = _request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, Quantity(353.15, "kelvin"))
    request["report_index"] = 0
    with pytest.raises(ClaimAssessmentError, match="report_index"):
        assess_claim_request(request)


def test_a_multi_stage_case_is_not_resolved_by_the_transport():
    case = copy.deepcopy(ET_CASE)
    second = copy.deepcopy(case["stages"][0])
    second["component_id"] = "R2"
    case["stages"].append(second)
    record = assess_claim_request(_request("electrothermal", case, "final_temperature", L.ANALYTICALLY_VERIFIED, Quantity(353.15, "kelvin")))
    assert record["status"] == "not_executed" and record["verdict"] == "insufficient_evidence"


@pytest.mark.parametrize("field, value, match", [
    ("required_levels", [], "cannot be inferred"),
    ("discrepancy", None, "discrepancy must be an object"),
    ("system", "nonexistent", "has no registered claim capability"),
])
def test_an_incomplete_request_is_refused(field, value, match):
    request = _request("electrothermal", ET_CASE, "final_temperature", L.ANALYTICALLY_VERIFIED, Quantity(353.15, "kelvin"))
    request[field] = value
    with pytest.raises(ClaimAssessmentError, match=match):
        claim_from_case_request(request)


def test_a_claim_and_a_case_description_cannot_be_mixed():
    payload = claim(operating_context={}, known_inputs=et_inputs()).to_dict()
    with pytest.raises(ClaimAssessmentError, match="not both"):
        assess_claim_request({"claim": payload, "system": "electrothermal"})


def test_the_transport_builds_no_authority_of_its_own():
    """The structural half: the shadow path's construction cannot come back unnoticed."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    forbidden = {"Arbiter", "trusting_authority", "obligations_from_charter", "CampaignCharter",
                 "CredibilityReportCritic", "evidence_from_credibility_report", "derive_claim_verdict"}
    assert not (names | imported) & forbidden
