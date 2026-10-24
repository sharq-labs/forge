"""The v1 problem view of a v2 specification, for the frozen v1 arms (the Minimal Mind adapter and the v1 baselines).

The v2 pack is written once, in the repsem problem schema.  The frozen v1 code reads the older problem schema, so this
module translates a specification into it.  The translation picks columns by DECLARED ROLE (never by name):
the one CONTROLLED_INPUT is the current, the one MEASUREMENT the voltage, the one NUISANCE_VARIABLE the temperature,
and the one STATE_VARIABLE's declared initial value is ``z0``.  Everything else is copied from the declaration:

* bars in volts become bars in millivolts;
* the OCV declaration (measured knots, or the fitted table's knots and bounds) is copied as is;
* a declared voltage standard uncertainty becomes DECLARED_TYPE_B, a missing one UNKNOWN;
* the applicability margins map onto v1's schema: temperature margin -> ``temperature_C.widen_by``, protocol-level
  margin -> ``current_A.widen_by`` (v1 checks the largest current), the OCV support -> ``soc.min/max``.
  This is v1's own, coarser domain rule (v1 has no charge-state range from calibration and no level check); it is
  what the frozen v1 baselines implement, and it is recorded as a known difference, not repaired here.
"""

from __future__ import annotations

from typing import Any, Mapping

from benchmarks.battery_rediscovery_v1.candidate import common as v1common
from engcore.mind.repsem import RoleTable, VariableRole

V1_SETS = {"within_unit_heldout": "within_cell_heldout", "cross_unit_heldout": "cross_cell_heldout"}


def _one(roles: RoleTable, role: VariableRole, clock: str) -> str:
    names = [n for n in roles.names(role) if n != clock]
    if len(names) != 1:
        raise ValueError(f"the v1 problem view needs exactly one {role.value}, found {names}")
    return names[0]


def v1_problem(spec: Mapping[str, Any]) -> v1common.Problem:
    roles = RoleTable.from_spec(spec)
    clock = spec["clock"]
    cur, volt = _one(roles, VariableRole.CONTROLLED_INPUT, clock), _one(roles, VariableRole.MEASUREMENT, clock)
    temp, state = _one(roles, VariableRole.NUISANCE_VARIABLE, clock), _one(roles, VariableRole.STATE_VARIABLE, clock)
    levels = [n for n in roles.names(VariableRole.FIXED_PROTOCOL_CONDITION) if n != clock]

    def traj(t: Mapping[str, Any]) -> dict[str, Any]:
        c = t["columns"]
        return {"id": t["id"], "cell": t["unit_id"], "kind": t["kind"], "t_s": c[clock], "current_A": c[cur],
                "voltage_V": c[volt], "temperature_C": c[temp], "z0": t["initial_state"][state],
                "capacity_Ah": t["conditions"]["capacity_As"] / 3600.0}

    sets: dict[str, Any] = {"calibration": {"trajectories": [traj(t) for t in spec["sets"]["calibration"]]}}
    acceptance = {}
    for ours, theirs in V1_SETS.items():
        if spec["sets"].get(ours):
            sets[theirs] = {"subsets": {k: [traj(t) for t in v] for k, v in spec["sets"][ours].items()}}
            for k in spec["sets"][ours]:
                bar = spec["acceptance"][f"{ours}/{k}"]
                acceptance[f"{theirs}/{k}"] = {"rmse_mV_max": bar["rmse_max"] * 1e3, "p95_abs_mV_max": bar["p95_abs_max"] * 1e3}
    decl = spec["declared_family"]
    b = decl["parameter_bounds"]
    ocv = decl["ocv"]
    if ocv["status"] == "MEASURED_FIXED":
        ocv_v1 = {"status": "MEASURED_FIXED", "interpolation": "linear", "knots_z_V": decl["constants"]["ocv_knots"]}
    else:
        ocv_v1 = {"status": "UNKNOWN_FITTED_TABLE", "knots_soc": list(ocv["knots_soc"]), "bounds_V": list(ocv["bounds_V"])}
    noise = spec["measurement_noise"]
    voltage = ({"status": "DECLARED_TYPE_B", "standard_uncertainty": noise["sigma"]} if noise.get("sigma") is not None
               else {"status": "UNKNOWN"})
    app = spec["applicability"]
    widen = app.get("widen", {})
    level_margin = max([float(widen.get(n, 0.0)) for n in levels if n in app.get("variables", ())] or [0.0])
    raw = {"schema": v1common.PROBLEM_SCHEMA, "problem_id": spec["problem_id"],
           "declared_model": {"family": "thevenin_1rc", "requested_parameters": list(spec["requested_parameters"]),
                              "bounds": {"R0_ohm": b["R0"], "R1_ohm": b["R1"], "C1_F": b["C1"]}, "ocv": ocv_v1},
           "conventions": {"rest_band_A": spec["conventions"]["rest_band_A"], "hold": spec["conventions"]["hold"]},
           "measurement_uncertainty": {"voltage_V": voltage},
           "acceptance": acceptance,
           "applicability": {"temperature_C": {"widen_by": float(widen.get(temp, 0.0))},
                             "current_A": {"widen_by": level_margin},
                             "soc": {"min": app["soc_support"][0], "max": app["soc_support"][1]}},
           "sets": sets}
    return v1common.Problem(raw)


__all__ = ["V1_SETS", "v1_problem"]
