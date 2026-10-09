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
