import pytest

from engcore.mcp.scenario_uq import SCENARIO_UQ_SCHEMA, scenario_envelope


def _answer(value, *, verdict="supported", unit="kelvin"):
    return {
        "status": "completed",
        "system": "electrothermal",
        "verdict": verdict,
        "results": [{
            "subject": "R1",
            "values": {
                "final_temperature": {
                    "schema": "quantity/1", "magnitude": value, "units": unit,
                }
            },
        }],
    }


def test_envelope_is_unit_aware_and_non_probabilistic():
    result = scenario_envelope(
        [_answer(300.0), _answer(80.33, unit="degC")],
        scenario_ids=["cold", "hot"],
    )
    assert result["schema"] == SCENARIO_UQ_SCHEMA
    assert result["probability_model"] is None
    interval = result["intervals"][0]
    assert interval["lower"]["magnitude"] == pytest.approx(300.0)
    assert interval["upper"]["magnitude"] == pytest.approx(353.48)
    assert interval["confidence_level"] is None


def test_a_not_supported_scenario_remains_visible_beside_the_bounds():
    result = scenario_envelope(
        [_answer(300.0), _answer(340.0, verdict="not_supported")],
        scenario_ids=["nominal", "outside"],
    )
    assert result["all_scenarios_supported"] is False
    assert result["scenario_verdicts"][1] == {
        "scenario_id": "outside", "verdict": "not_supported"
    }


def test_duplicate_ids_and_single_scenarios_are_refused():
    with pytest.raises(ValueError, match="at least two"):
        scenario_envelope([_answer(300)], scenario_ids=["only"])
    with pytest.raises(ValueError, match="unique"):
        scenario_envelope(
            [_answer(300), _answer(301)], scenario_ids=["same", "same"]
        )
