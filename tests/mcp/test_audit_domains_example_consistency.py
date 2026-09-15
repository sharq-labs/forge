"""Audit CAP-05: the flagship electro-thermal example agrees with the part it cites.

The example says every number is "FROM A REAL DATASHEET" -- the Bourns
PWR220T-20 record in ``benchmarks/ai_designs/components.json`` -- and declared
copper's 0.00393/K coefficient against the part's +/-100 ppm/K, copper's 343 K
Debye temperature for a thick film on alumina, a 400 K ceiling against the
part's 155 C, and a body whose 2.5 J/K could not be the heat capacity of the
20 cm^3 it declared, convecting off a 0.6 m plate.

This cross-checks every declared part property against that record, and checks
the body declaration against itself: its heat capacity against its volume, its
characteristic length against its volume and area, and its ambient conductance
against the forced laminar flat-plate correlation over its own declared length.
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest

from engcore.mcp.problem import example_electrothermal_payload
from engcore.scientific.units.quantity import Quantity

REPO = pathlib.Path(__file__).resolve().parents[2]
C_TO_K = 273.15


def _record():
    data = json.loads(
        (REPO / "benchmarks" / "ai_designs" / "components.json").read_text(encoding="utf-8")
    )
    return next(r for r in data["resistors"] if r["id"] == "bourns-pwr220t-20")


def _q(text: str, unit: str) -> float:
    magnitude, _, units = text.partition(" ")
    return Quantity(float(magnitude), units).magnitude_in(unit)


@pytest.fixture(scope="module")
def stage():
    return example_electrothermal_payload()["stages"][0]


def test_the_temperature_coefficient_is_the_parts_not_coppers(stage) -> None:
    record = _record()
    alpha = _q(stage["conductor"]["temperature_coefficient"], "1/kelvin")
    r_ref = _q(stage["conductor"]["reference_resistance"], "ohm")
    band = next(
        row for row in record["temperature_coefficient_ppm_per_k"]
        if row["from_ohm"] <= r_ref <= row["to_ohm"]
    )
    assert abs(alpha) * 1e6 <= band["value"] + 1e-9
    assert record["resistance_range_ohm"]["min"] <= r_ref <= record["resistance_range_ohm"]["max"]


def test_no_elemental_metal_limits_are_declared_for_a_thick_film(stage) -> None:
    record = _record()
    # A thick film on alumina is not an elemental metal: the Bloch-Grueneisen
    # floor the rated record's Debye conditions rest on does not describe it,
    # so no material limits -- and above all no Debye temperature -- are declared.
    assert "thick film" in record["technology"]
    limits = stage["conductor"].get("limits", {})
    assert "debye_temperature" not in limits
    # The part's one sourced material limit still binds, on the element.
    assert _q(stage["conductor"]["element"]["permissible_element_temperature"], "kelvin") == (
        pytest.approx(record["operating_temperature_range_c"][1] + C_TO_K)
    )
    if "maximum_operating_temperature" in limits:
        assert _q(limits["maximum_operating_temperature"], "kelvin") == pytest.approx(
            record["operating_temperature_range_c"][1] + C_TO_K
        )


def test_the_ratings_and_element_data_are_the_parts(stage) -> None:
    record = _record()
    ratings = stage["conductor"]["ratings"]
    assert _q(ratings["rated_power"], "watt") == record["rated_power_w"]
    assert _q(ratings["rated_power_temperature"], "kelvin") == pytest.approx(
        record["rated_power_ambient_c"] + C_TO_K
    )
    assert _q(ratings["zero_power_temperature"], "kelvin") == pytest.approx(
        record["derating"]["zero_power_c"] + C_TO_K
    )
    r_ref = _q(stage["conductor"]["reference_resistance"], "ohm")
    assert _q(ratings["maximum_working_voltage"], "volt") == pytest.approx(
        min(math.sqrt(record["rated_power_w"] * r_ref), record["maximum_working_voltage_v"]),
        abs=5e-3,
    )
    element = stage["conductor"]["element"]
    assert _q(element["element_to_body_thermal_resistance"], "kelvin/watt") == record[
        "thermal_resistance_k_per_w"
    ]


def test_the_body_heat_capacity_is_a_solid_of_its_declared_volume(stage) -> None:
    body = stage["body"]
    capacity = _q(body["heat_capacity"], "joule/kelvin")
    volume = _q(body["applicability"]["body_volume"], "meter**3")
    # Every engineering solid sits between about 1 and 4.5 MJ/(m^3 K).
    assert 1.0e6 <= capacity / volume <= 4.5e6


def test_the_characteristic_length_is_volume_over_area(stage) -> None:
    app = stage["body"]["applicability"]
    length = _q(app["characteristic_length"], "meter")
    assert length == pytest.approx(
        _q(app["body_volume"], "meter**3") / _q(app["surface_area"], "meter**2"), rel=1e-6
    )


def test_the_ambient_conductance_is_the_correlation_over_the_declared_plate(stage) -> None:
    body = stage["body"]
    app = body["applicability"]
    reynolds = (
        _q(app["fluid_velocity"], "meter/second")
        * _q(app["convection_length"], "meter")
        / _q(app["fluid_kinematic_viscosity"], "meter**2/second")
    )
    nusselt = 0.664 * math.sqrt(reynolds) * _q(app["fluid_prandtl_number"], "dimensionless") ** (1 / 3)
    h = nusselt * _q(app["fluid_conductivity"], "watt/meter/kelvin") / _q(app["convection_length"], "meter")
    assert _q(body["ambient_conductance"], "watt/kelvin") == pytest.approx(
        h * _q(app["surface_area"], "meter**2"), rel=0.01
    )
    # And the plate is one a TO-220 part can be screwed to, not 0.6 m long.
    assert _q(app["convection_length"], "meter") <= 0.2
