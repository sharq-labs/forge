from engcore.mcp.context import CONTEXT_SCHEMA, evaluate_context


def _answer(value=340.0, verdict="supported"):
    return {
        "status": "completed",
        "verdict": verdict,
        "results": [{
            "subject": "R1",
            "values": {"final_temperature": {
                "schema": "quantity/1", "magnitude": value, "units": "kelvin"
            }},
        }],
    }


CRITERION = [{
    "criterion_id": "thermal-limit",
    "subject": "R1",
    "quantity": "final_temperature",
    "operator": "<=",
    "threshold": "350 kelvin",
}]


def test_supported_point_can_meet_or_fail_the_context():
    met = evaluate_context(_answer(340), CRITERION)
    failed = evaluate_context(_answer(360), CRITERION)
    assert met["schema"] == CONTEXT_SCHEMA
    assert met["decision"] == "meets_context"
    assert failed["decision"] == "does_not_meet_context"


def test_numerical_pass_with_insufficient_evidence_is_indeterminate():
    result = evaluate_context(_answer(340, "insufficient_evidence"), CRITERION)
    assert result["criteria"][0]["numerical_status"] == "satisfied"
    assert result["decision"] == "indeterminate_evidence"


def test_scenario_interval_straddling_limit_is_indeterminate_uncertainty():
    uncertainty = {
        "scenario_verdicts": [
            {"scenario_id": "a", "verdict": "supported"},
            {"scenario_id": "b", "verdict": "supported"},
        ],
        "intervals": [{
            "subject": "R1",
            "quantity": "final_temperature",
            "lower": {"magnitude": 340, "units": "kelvin"},
            "upper": {"magnitude": 360, "units": "kelvin"},
            "method": "declared_scenario_envelope",
        }],
    }
    result = evaluate_context(_answer(), CRITERION, uncertainty=uncertainty)
    assert result["criteria"][0]["numerical_status"] == "indeterminate"
    assert result["decision"] == "indeterminate_uncertainty"


def test_offset_unit_threshold_is_compared_dimensionally():
    criterion = [{**CRITERION[0], "threshold": "76.85 degC"}]
    result = evaluate_context(_answer(350), criterion)
    assert result["criteria"][0]["numerical_status"] == "satisfied"
