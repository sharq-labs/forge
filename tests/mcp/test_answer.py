from engcore.mcp.answer import ANSWER_SCHEMA, summarize_engineering_run
from engcore.mcp.problem import example_electrothermal_payload
from engcore.mcp.server import run_engineering_problem


def _flatten(value, prefix=""):
    flat = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            flat.update(_flatten(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            flat.update(_flatten(child, f"{prefix}[{index}]"))
    else:
        flat[prefix] = value
    return flat


def test_incomplete_intent_produces_questions_and_no_answered_values():
    run = run_engineering_problem("جهد المصدر 5 فولت")
    answer = summarize_engineering_run(run)

    assert answer["schema"] == ANSWER_SCHEMA
    assert answer["status"] == "needs_input"
    assert answer["results"] == []
    assert answer["questions"]
    assert answer["execution"]["result"] is None


def test_answer_groups_values_limits_uncertainty_and_evidence_without_upgrading():
    run = run_engineering_problem(
        "مقاومة في نظام حراري كهربائي",
        _flatten(example_electrothermal_payload()),
    )
    answer = summarize_engineering_run(run)

    assert answer["status"] == "completed"
    assert answer["system"] == "electrothermal"
    assert answer["verdict"] == "supported"
    result = answer["results"][0]
    assert result["values"]["final_temperature"]["units"] == "kelvin"
    assert result["verdict"]["value"] == "supported"
    assert result["uncertainty"]["status"] == "not_quantified"
    assert result["uncertainty"]["intervals"] == []
    assert result["applicability"]["violated"] == []
    assert result["evidence"]["checks"]
    assert result["evidence"]["established_levels"]
    assert result["evidence"]["provenance"]
    assert answer["execution"] == run


def test_under_evidenced_run_stays_under_evidenced_in_the_answer():
    description = (
        "source voltage 5 volt; reference resistance 10 ohm; "
        "temperature coefficient 0.00393 1/kelvin; "
        "reference temperature 293.15 kelvin; heat capacity 2.5 joule/kelvin; "
        "ambient conductance 0.05 watt/kelvin; ambient temperature 300 kelvin; "
        "initial temperature 300 kelvin; duration 120 second"
    )
    answer = summarize_engineering_run(run_engineering_problem(description))

    assert answer["verdict"] == "insufficient_evidence"
    assert answer["results"][0]["verdict"]["verdict_reasons"]
    assert answer["results"][0]["applicability"]["unknown"]
