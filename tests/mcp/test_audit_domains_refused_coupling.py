"""Audit CAP-06: a refused coupled run neither claims its criterion nor misnames its stage.

Two series stages; the second (R2, alpha -0.004/K on a nearly insulated body)
drives its own resistance through zero and the loop stops with
``transfer_refused``. Before the fix:

* the coupling block said ``"criterion": "met"``, because the refused sweep
  stores an iterate change of 0 and the criterion is read off that number;
* the one report the refusal produces was published under component_id
  ``R1``, because the response zipped the payload's stages with the reports
  in order, and the refused property solve was R2's.
"""

from __future__ import annotations

import copy

import pytest

from engcore.mcp.problem import example_electrothermal_payload, run_electrothermal_case
from engcore.mcp.server import run_electrothermal


def _two_stage(volts: str = "8 volt"):
    base = copy.deepcopy(example_electrothermal_payload())
    first = base["stages"][0]
    second = copy.deepcopy(first)
    second["component_id"] = "R2"
    conductor = second["conductor"]
    conductor["reference_resistance"] = "10 ohm"
    conductor["temperature_coefficient"] = "-0.004 1/kelvin"
    conductor["ratings"] = {
        "rated_power": "500 watt",
        "rated_power_temperature": "298.15 kelvin",
        "zero_power_temperature": "623.15 kelvin",
        "maximum_working_voltage": "100 volt",
    }
    conductor["element"] = {
        "element_to_body_thermal_resistance": "0.1 kelvin/watt",
        "permissible_element_temperature": "600 kelvin",
    }
    body = second["body"]
    body["heat_capacity"] = "2.5 joule/kelvin"
    body["ambient_conductance"] = "0.002 watt/kelvin"   # nearly insulated -> runaway
    body["duration"] = "5000 second"
    applicability = body["applicability"]
    applicability["conductance_excursion_bound"] = "300 kelvin"
    applicability["capacity_excursion_bound"] = "300 kelvin"
    applicability["surface_emissivity"] = "0.01 dimensionless"
    for key in (
        "fluid_velocity",
        "fluid_conductivity",
        "fluid_kinematic_viscosity",
        "fluid_prandtl_number",
        "convection_length",
    ):
        applicability.pop(key, None)
    base["stages"].append(second)
    base["source_voltage"] = volts
    return base


@pytest.mark.parametrize("volts", ["6 volt", "8 volt", "14 volt"])
def test_a_refused_run_does_not_report_its_criterion_met(volts) -> None:
    out = run_electrothermal(_two_stage(volts))
    assert out["coupling"]["outcome"] == "transfer_refused"
    assert out["coupling"]["criterion"] != "met"
    for stage in out["stages"]:
        assert stage["report"]["coupling"]["criterion"] != "met"


def test_the_refused_report_is_published_under_the_stage_that_was_refused() -> None:
    payload = _two_stage()
    case = run_electrothermal_case(payload)
    refused_problem = case.run.refusal.result.problem_id
    assert refused_problem.endswith("R2")

    out = run_electrothermal(payload)
    assert [stage["component_id"] for stage in out["stages"]] == ["R2"]
    # And its values are R2's: a resistance driven through zero.
    assert out["stages"][0]["report"]["values"]["resistance"]["magnitude"] < 0.0
