"""Big Rock S: the foundations reach MCP through describe -> plan -> run, as transport only."""

from __future__ import annotations

from engcore.mcp.foundations import describe_engineering_platform, plan_product, run_product_screening

DRONE = {"takeoff_mass": {"magnitude": 2.0, "unit": "kg", "source_ref": "spec:mass-budget"},
         "rotor_diameter": {"magnitude": 0.254, "unit": "m", "source_ref": "catalog:prop"},
         "rotor_count": {"magnitude": 4, "unit": "dimensionless", "source_ref": "template"},
         "air_density": {"magnitude": 1.225, "unit": "kg/m^3", "source_ref": "env:isa"},
         "gravity": {"magnitude": 9.80665, "unit": "m/s^2", "source_ref": "env:g0"}}


def test_describe_reads_off_records():
    d = describe_engineering_platform()
    assert {p["product"] for p in d["products"]} == {"drone", "hvac", "motor", "vehicle"}
    assert all(i["status"] == "UNKNOWN" for p in d["products"] for i in p["inputs"])
    assert {s["kind"] for s in d["geometry"]["shapes"]} == {"rectangle", "disk", "box", "cylinder"}
    assert [r["rung_id"] for r in d["fidelity_ladder"]["rungs"]][-1] == "experimental"
    assert all(p["health"] in ("not_installed", "broken", "available") for p in d["providers"])


def test_plan_and_screening_refuse_until_inputs_are_declared_with_sources():
    plan = plan_product("drone")
    assert plan["status"] == "planned" and "takeoff_mass" in plan["unknown_inputs"]
    assert run_product_screening("drone")["status"] == "refused"
    bare = dict(DRONE, takeoff_mass={"magnitude": 2.0, "unit": "kg"})
    assert run_product_screening("drone", bare)["status"] == "refused"
    ok = run_product_screening("drone", DRONE)
    assert ok["status"] == "computed" and ok["verdict"] == "insufficient_evidence"
    assert ok["result"]["classification"] == "ideal_momentum_theory_lower_bound_not_validated"
    assert run_product_screening("vehicle")["status"] == "refused"
    assert plan_product("submarine")["status"] == "refused"


def test_the_coupled_hover_chain_is_reachable_and_refuses_until_every_coupled_input_is_declared():
    partial = run_product_screening("drone", DRONE, screening="coupled_hover")
    assert partial["status"] == "refused" and "UNKNOWN" in partial["message"] and "prop_power_coefficient" in partial["message"]
    extra = {"prop_thrust_coefficient": (0.11, "dimensionless"), "prop_power_coefficient": (0.045, "dimensionless"),
             "motor_kv": (920, "rpm/V"), "motor_resistance": (0.1, "ohm"), "motor_no_load_current": (0.5, "A"),
             "motor_resistance_reference_temperature": (293.15, "K"), "winding_temperature_coefficient": (0.00393, "1/K"),
             "esc_efficiency": (0.95, "dimensionless"), "battery_open_circuit_voltage": (16.0, "V"),
             "battery_internal_resistance": (0.02, "ohm"), "battery_capacity": (5, "A*h"), "ambient_temperature": (298.15, "K"),
             "motor_thermal_resistance": (8, "K/W"), "winding_temperature_limit": (453.15, "K")}
    full = dict(DRONE, **{k: {"magnitude": m, "unit": u, "source_ref": "fixture:illustrative"} for k, (m, u) in extra.items()})
    ok = run_product_screening("drone", full, screening="coupled_hover")
    assert ok["status"] == "computed" and ok["verdict"] == "insufficient_evidence"
    assert ok["result"]["classification"] == "coupled_steady_hover_screening_not_validated" and ok["result"]["uncertainty"] == "UNKNOWN"
    assert ok["result"]["winding_temperature"]["unit"] == "kelvin"
    assert run_product_screening("drone", full, screening="cfd")["status"] == "refused"
    assert plan_product("drone")["screenings"] == ["hover_screening", "coupled_hover"]
