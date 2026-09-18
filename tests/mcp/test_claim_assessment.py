"""Sprint 4 — generic structured scientific claim assessment."""

from __future__ import annotations

import copy

import pytest

from engcore.mcp import (
    CredibilityVerdict,
    example_electrothermal_payload,
    run_electrothermal_case,
)
from engcore.mcp.battery import example_battery_payload, run_battery_case
from engcore.mcp.claim_assessment import (
    CLAIM_ASSESSMENT_SCHEMA,
    ClaimAssessmentError,
    assess_claim_request,
)
from engcore.scientific.results.validation import ValidationLevel


def _request(
    *,
    system: str,
    case,
    quantity_name: str,
    required_levels,
    decision_id: str = "d1",
):
    return {
        "system": system,
        "case": copy.deepcopy(case),
        "quantity_name": quantity_name,
        "decision": {
            "id": decision_id,
            "statement": "Use this structured scientific claim for the declared decision.",
        },
        "required_levels": [level.value for level in required_levels],
        "discrepancy": {
            "kind": "zero_declared",
            "rationale": (
                "test fixture declaration only; the API requires this statement "
                "explicitly and never invents it"
            ),
        },
    }


def test_supported_report_and_attained_level_can_reach_valid() -> None:
    case = example_electrothermal_payload()
    direct = run_electrothermal_case(copy.deepcopy(case)).reports[0]
    assert direct.verdict is CredibilityVerdict.SUPPORTED
    assert direct.attained_levels
    required = (sorted(direct.attained_levels, key=lambda level: level.value)[0],)
    quantity_name = next(iter(direct.values))

    result = assess_claim_request(
        _request(
            system="electrothermal",
            case=case,
            quantity_name=quantity_name,
            required_levels=required,
        )
    )

    assert result["schema"] == CLAIM_ASSESSMENT_SCHEMA
    assert result["status"] == "assessed"
    assert result["credibility"]["verdict"] == "supported"
    assert result["assurance"]["verdict"] == "valid"
    assert result["assurance"]["unmet_obligations"] == []
    assert result["claim"]["source_closure_complete"] is False
    assert result["decision"]["charter_digest"] in result["claim"]["context_ref"]


def test_missing_requested_level_fails_closed_as_inconclusive() -> None:
    case = example_electrothermal_payload()
    direct = run_electrothermal_case(copy.deepcopy(case)).reports[0]
    assert ValidationLevel.EXPERIMENTALLY_VALIDATED not in direct.attained_levels
    quantity_name = next(iter(direct.values))

    result = assess_claim_request(
        _request(
            system="electrothermal",
            case=case,
            quantity_name=quantity_name,
            required_levels=(ValidationLevel.EXPERIMENTALLY_VALIDATED,),
        )
    )

    assert result["assurance"]["verdict"] == "inconclusive"
    assert result["assurance"]["unmet_obligations"]
    assert (
        "experimentally_validated"
        in result["credibility"]["missing_required_levels"]
    )


def test_attained_level_cannot_hide_an_insufficient_credibility_report() -> None:
    case = example_battery_payload()
    direct = run_battery_case(copy.deepcopy(case)).report
    assert direct.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert direct.attained_levels
    required = (sorted(direct.attained_levels, key=lambda level: level.value)[0],)
    quantity_name = next(iter(direct.values))

    result = assess_claim_request(
        _request(
            system="battery",
            case=case,
            quantity_name=quantity_name,
            required_levels=required,
        )
    )

    assert required[0].value in result["credibility"]["attained_levels"]
    assert result["credibility"]["verdict"] == "insufficient_evidence"
    assert result["assurance"]["verdict"] == "inconclusive"
    assert any(
        item["obligation_id"] == "critic:process"
        and item["satisfied"] is False
        for item in result["assurance"]["obligations"]
    )


def test_assessment_refuses_to_guess_a_decision_standard() -> None:
    request = _request(
        system="electrothermal",
        case=example_electrothermal_payload(),
        quantity_name="final_temperature",
        required_levels=(ValidationLevel.DIMENSIONALLY_VALID,),
    )
    request["required_levels"] = []

    with pytest.raises(ClaimAssessmentError, match="cannot be inferred"):
        assess_claim_request(request)


def test_assessment_requires_an_explicit_discrepancy_declaration() -> None:
    request = _request(
        system="electrothermal",
        case=example_electrothermal_payload(),
        quantity_name="final_temperature",
        required_levels=(ValidationLevel.DIMENSIONALLY_VALID,),
    )
    request.pop("discrepancy")

    with pytest.raises(ClaimAssessmentError, match="discrepancy must be an object"):
        assess_claim_request(request)


def test_multiple_reports_require_explicit_selection() -> None:
    case = example_electrothermal_payload()
    second = copy.deepcopy(case["stages"][0])
    second["component_id"] = "R2"
    second["body"]["body_id"] = "B2"
    case["stages"].append(second)

    direct = run_electrothermal_case(copy.deepcopy(case))
    assert len(direct.reports) == 2
    quantity_name = next(iter(direct.reports[0].values))
    required = tuple(direct.reports[0].attained_levels)
    assert required

    request = _request(
        system="electrothermal",
        case=case,
        quantity_name=quantity_name,
        required_levels=(required[0],),
    )
    with pytest.raises(ClaimAssessmentError, match="report_index is required"):
        assess_claim_request(request)

    request["report_index"] = 0
    result = assess_claim_request(request)
    assert result["report_index"] == 0
