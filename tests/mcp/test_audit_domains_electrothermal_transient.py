"""Audit CAP-03: the self-heating transient holds R(T_final) over the whole interval.

The coupled electro-thermal run iterates a fixed point in which the lumped body
is integrated over its declared duration with ONE heat input, V^2 / R(T), and
R is evaluated at the end-of-interval temperature. That is a quasi-static
end-of-interval fixed point, not a transient: against an independent RK4 of
C dT/dt = V^2/R(T(t)) - hA (T - T_amb) the nominal copper example misstates
the rise by -1.8 %, a nickel element (alpha 0.0068/K, 8 V, 50 s) by -7.3 %
(56.5 K against 61.0 K), and all came back SUPPORTED, while the element
record's assumption "one resistance describes the element over the whole run"
had no condition.

Now ``electrical.dc.self_heated_resistor`` carries
``resistance_variation_utilization`` = |alpha| |T_final - T_0| / declared
``resistance_variation_budget`` <= 1, UNKNOWN when the budget is undeclared, and
the tool and system descriptions say "quasi-static end-of-interval fixed point".
"""

from __future__ import annotations

import copy

from engcore.domains.electrical import dc_applicability as dc_app
from engcore.mcp.problem import example_electrothermal_payload
from engcore.mcp.server import run_electrothermal
from engcore.mcp import server as mcp_server
from engcore.mcp.systems import ELECTROTHERMAL

SELF_HEATED = dc_app.SELF_HEATED_RESISTOR_MODEL.model_id


def _nickel(budget=None, volts="8 volt", duration="50 second"):
    case = copy.deepcopy(example_electrothermal_payload())
    stage = case["stages"][0]
    conductor, body = stage["conductor"], stage["body"]
    conductor["temperature_coefficient"] = "0.0068 1/kelvin"
    conductor["limits"] = {
        "linearization_band": "160 kelvin",
        "maximum_operating_temperature": "600 kelvin",
        "debye_temperature": "450 kelvin",
    }
    conductor["ratings"] = {
        "rated_power": "50 watt",
        "rated_power_temperature": "298.15 kelvin",
        "zero_power_temperature": "623.15 kelvin",
        "maximum_working_voltage": "50 volt",
    }
    conductor["element"] = {
        "element_to_body_thermal_resistance": "1 kelvin/watt",
        "permissible_element_temperature": "600 kelvin",
    }
    if budget is not None:
        conductor["element"]["resistance_variation_budget"] = budget
    body["applicability"]["conductance_excursion_bound"] = "200 kelvin"
    body["applicability"]["capacity_excursion_bound"] = "200 kelvin"
    body["duration"] = duration
    case["source_voltage"] = volts
    return case


def _stage(out):
    return out["stages"][0]


def _assessment(out, model_id):
    for record in _stage(out)["report"]["validity"]:
        if record["model_id"] == model_id:
            return record["assessment"]
    raise AssertionError(f"{model_id} not in the report")


def test_the_nickel_transient_is_not_supported_without_a_declared_budget() -> None:
    out = run_electrothermal(_nickel())
    assert _stage(out)["verdict"]["value"] != "supported"
    assessment = _assessment(out, SELF_HEATED)
    assert dc_app.RESISTANCE_VARIATION_UTILIZATION in assessment["unknown"]


def test_the_nickel_transient_violates_a_five_percent_budget() -> None:
    # |alpha| |T_final - T_0| = 0.0068 * 56.5 K = 0.384, against a 0.05 budget.
    out = run_electrothermal(_nickel(budget="0.05 dimensionless"))
    assessment = _assessment(out, SELF_HEATED)
    assert dc_app.RESISTANCE_VARIATION_UTILIZATION in assessment["violated"]
    assert _stage(out)["verdict"]["value"] == "not_supported"


def test_a_budget_wide_enough_for_the_variation_is_satisfied() -> None:
    out = run_electrothermal(_nickel(budget="0.5 dimensionless"))
    assessment = _assessment(out, SELF_HEATED)
    assert dc_app.RESISTANCE_VARIATION_UTILIZATION in assessment["satisfied"]


def test_the_utilization_is_the_variation_over_the_interval_not_from_the_reference() -> None:
    from engcore.scientific.units.quantity import Quantity as Q

    value = dc_app.resistance_variation_utilization(
        temperature_coefficient=Q(-0.002, "1/kelvin"),
        initial_body_temperature=Q(300.0, "kelvin"),
        body_temperature=Q(350.0, "kelvin"),
        resistance_variation_budget=Q(0.2, "dimensionless"),
    )
    assert abs(value.magnitude - 0.002 * 50.0 / 0.2) < 1e-12
    assert (
        dc_app.resistance_variation_utilization(
            temperature_coefficient=Q(0.004, "1/kelvin"),
            initial_body_temperature=Q(300.0, "kelvin"),
            body_temperature=Q(350.0, "kelvin"),
            resistance_variation_budget=None,
        )
        is None
    )


def test_the_descriptions_name_the_quasi_static_fixed_point() -> None:
    assert "quasi-static end-of-interval fixed point" in ELECTROTHERMAL.summary
    assert "quasi-static end-of-interval fixed point" in mcp_server._RUN_DESCRIPTION
