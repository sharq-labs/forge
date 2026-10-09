"""Rock 2: the drone's coupled hover chain on the multiphysics runtime -- executes, converges, refuses honestly.

The input values below are ILLUSTRATIVE fixtures (labelled as such in their source refs), not product data.
Agreement with the independent closed-form solve is verification of the coupled arithmetic, not validation.
"""

from __future__ import annotations

import math

import pytest

from engcore.scientific.units.quantity import Quantity as Q
from engcore.systems.products import IN_REPOSITORY, CouplingStatus, TemplateRefusal, capability_report, coupled_hover_screening, drone_template
from engcore.systems.products.drone_coupled import COUPLED_INPUTS, build_runtime

VALUES = dict(
    takeoff_mass=Q(1.5, "kg"), gravity=Q(9.80665, "m/s^2"), air_density=Q(1.225, "kg/m^3"), rotor_count=Q(4, "dimensionless"),
    rotor_diameter=Q(0.254, "m"), prop_thrust_coefficient=Q(0.11, "dimensionless"), prop_power_coefficient=Q(0.045, "dimensionless"),
    motor_kv=Q(920, "rpm/V"), motor_resistance=Q(0.1, "ohm"), motor_no_load_current=Q(0.5, "A"),
    motor_resistance_reference_temperature=Q(293.15, "K"), winding_temperature_coefficient=Q(0.00393, "1/K"),
    esc_efficiency=Q(0.95, "dimensionless"), battery_open_circuit_voltage=Q(16.0, "V"), battery_internal_resistance=Q(0.02, "ohm"),
    battery_capacity=Q(5, "A*h"), ambient_temperature=Q(298.15, "K"), motor_thermal_resistance=Q(8, "K/W"))


def template(**changes):
    vals = {**VALUES, **changes}
    return drone_template({k: (v, "fixture:illustrative-not-product-data") for k, v in vals.items() if v is not None})


def closed_form(v):
    """Independent solve of the same equations: T_w is linear once I is fixed, then V_b from the quadratic."""
    m, g, rho = v["takeoff_mass"].magnitude_in("kg"), v["gravity"].magnitude_in("m/s^2"), v["air_density"].magnitude_in("kg/m^3")
    N, D = int(v["rotor_count"].magnitude_in("dimensionless")), v["rotor_diameter"].magnitude_in("m")
    ct, cp = v["prop_thrust_coefficient"].magnitude_in("dimensionless"), v["prop_power_coefficient"].magnitude_in("dimensionless")
    n = math.sqrt(m * g / N / (ct * rho * D ** 4))
    omega, p_shaft = 2 * math.pi * n, cp * rho * n ** 3 * D ** 5
    kv = v["motor_kv"].magnitude_in("rad/s/V")
    i0, r0 = v["motor_no_load_current"].magnitude_in("A"), v["motor_resistance"].magnitude_in("ohm")
    a, tref = v["winding_temperature_coefficient"].magnitude_in("1/K"), v["motor_resistance_reference_temperature"].magnitude_in("K")
    current = p_shaft / omega * kv + i0
    emf = omega / kv
    tamb, rth = v["ambient_temperature"].magnitude_in("K"), v["motor_thermal_resistance"].magnitude_in("K/W")
    # T = tamb + rth (I^2 r0 (1 + a (T - tref)) + emf i0)
    tw = (tamb + rth * (current ** 2 * r0 * (1 - a * tref) + emf * i0)) / (1 - rth * current ** 2 * r0 * a)
    r = r0 * (1 + a * (tw - tref))
    bus = N * (emf + current * r) * current / v["esc_efficiency"].magnitude_in("dimensionless")
    voc, rint = v["battery_open_circuit_voltage"].magnitude_in("V"), v["battery_internal_resistance"].magnitude_in("ohm")
    ib = (voc - math.sqrt(voc * voc - 4 * rint * bus)) / (2 * rint)
    return {"winding_temperature": tw, "bus_power": bus, "pack_current": ib, "bus_voltage": voc - ib * rint, "motor_current": current}


def test_the_coupled_chain_runs_on_the_runtime_and_matches_an_independent_solve():
    r = coupled_hover_screening(template())
    ref = closed_form(VALUES)
    assert r["classification"] == "coupled_steady_hover_screening_not_validated" and r["uncertainty"] == "UNKNOWN"
    assert r["iterations"] > 1  # a two-way fixed point, not a single pass
    assert r["winding_temperature"].magnitude_in("K") == pytest.approx(ref["winding_temperature"], abs=1e-5)
    assert r["bus_voltage"].magnitude_in("V") == pytest.approx(ref["bus_voltage"], abs=1e-8)
    assert r["pack_current"].magnitude_in("A") == pytest.approx(ref["pack_current"], rel=1e-8)
    assert r["bus_power"].magnitude_in("W") == pytest.approx(ref["bus_power"], rel=1e-7)
    assert abs(r["energy_balance_residual"].magnitude_in("W")) < 1e-9
    assert set(r["inputs"]) == set(COUPLED_INPUTS) and all(s.startswith("fixture:") for s in r["inputs"].values())
    assert "NOT an endurance prediction" in " ".join(r["notes"])
    # deterministic: the same declared inputs give the same run record
    assert coupled_hover_screening(template())["run_digest"] == r["run_digest"]


def test_the_thermal_feedback_is_load_bearing():
    hot = coupled_hover_screening(template())
    cold = coupled_hover_screening(template(winding_temperature_coefficient=Q(0, "1/K")))
    assert hot["bus_power"].magnitude_in("W") > cold["bus_power"].magnitude_in("W")
    assert hot["winding_temperature"].magnitude_in("K") > cold["winding_temperature"].magnitude_in("K")
    assert hot["run_digest"] != cold["run_digest"]


def test_unknown_inputs_are_refused_never_defaulted():
    for missing in ("prop_power_coefficient", "esc_efficiency", "motor_thermal_resistance", "ambient_temperature"):
        with pytest.raises(TemplateRefusal, match=f"{missing}.*UNKNOWN|UNKNOWN.*{missing}"):
            coupled_hover_screening(template(**{missing: None}))


def test_infeasible_operating_points_are_refused_without_a_result():
    # the battery cannot deliver the hover power through its internal resistance
    with pytest.raises(TemplateRefusal, match="battery cannot deliver"):
        coupled_hover_screening(template(battery_internal_resistance=Q(1.0, "ohm")))
    # thermal runaway: R_th I^2 R alpha > 1 has no steady fixed point; the runtime does not converge and nothing is reported
    with pytest.raises(TemplateRefusal, match="coupled hover refused"):
        coupled_hover_screening(template(motor_thermal_resistance=Q(100, "K/W")))
    with pytest.raises(TemplateRefusal, match="esc_efficiency"):
        coupled_hover_screening(template(esc_efficiency=Q(1.2, "dimensionless")))
    with pytest.raises(TemplateRefusal, match="rotor_count 6 disagrees with the 4 propulsion units"):
        coupled_hover_screening(drone_template().with_inputs({**{k: (v, "fixture") for k, v in VALUES.items()},
                                                             "rotor_count": (Q(6, "dimensionless"), "fixture")}))


def test_energy_crossings_are_declared_and_the_template_reports_the_coupling_as_iterative():
    runtime, _seeds, _x = build_runtime(template())
    conversions = {e.edge_id: e.conversion for e in runtime.graph.edges}
    assert conversions["shaft_power"] is not None and conversions["motor_heat"] is not None
    assert conversions["bus_current"] is None  # a current is not an energy crossing
    t = template()
    statuses = {(c.source, c.target): c.status for c in t.couplings}
    assert statuses[("motor_esc", "winding_thermal")] is CouplingStatus.ITERATIVE_EXECUTABLE
    assert statuses[("rotor_aerodynamics", "frame_structure")] is CouplingStatus.DECLARED_NOT_EXECUTABLE
    from engcore.providers import default_registry

    ready = {c.participant_id: c.readiness.value for c in capability_report(t, default_registry(), in_repository=IN_REPOSITORY)}
    assert ready["motor_esc"] == ready["battery_ecm"] == ready["winding_thermal"] == ready["propeller_static"]
