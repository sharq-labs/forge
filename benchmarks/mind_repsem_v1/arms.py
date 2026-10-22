"""The four ablation arms, on the synthetic fixtures only (no battery data, answer or truth).

OLD_MIND                  battery_rediscovery_v1's Mind arm, unchanged (``candidate.mind_arm.mind``, which runs the
                          byte-exact ``engcore.mind.minimal``), posed each fixture through the v1 pack format.
SEMANTIC_ROLES_ONLY       the same Mind, adapter and translation, but its PREDICTION probe is posed by declared roles:
                          the CONTROLLED_INPUT current is a settable input, the STATE_VARIABLE charge is not a free
                          covariate, and only the NUISANCE temperature stays passive.  The v1 vocabulary is unchanged, so
                          adequacy and discrepancy remain NOT_ASSESSABLE and identifiability keeps v1's relaxation proxy.
REPRESENTATION_ONLY       ``engcore.mind.repsem.assess`` (claim states, refusal conditions, declared-family judgments)
                          under the v1 adapter's two-class semantics (:func:`legacy_role_table`): no state, no latent
                          parameter, every non-clock column a passive covariate.
REPRESENTATION_PLUS_ROLES ``assess`` under the problem's declared roles.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.battery_rediscovery_v1.candidate import common as v1common
from benchmarks.battery_rediscovery_v1.candidate import mind_arm as v1
from engcore.mind.minimal import ConclusionKind
from engcore.mind.repsem import RoleTable, VariableRole, assess, legacy_role_table

from . import fixtures as fx

ARMS = ("OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES")
_V1_SETS = {"within_unit_heldout": "within_cell_heldout", "cross_unit_heldout": "cross_cell_heldout"}


# ---- the v1 pack format, filled by role (never by column name) -----------------------------------------------------
def _one(roles: RoleTable, role: VariableRole, clock: str) -> str:
    names = [n for n in roles.names(role) if n != clock]
    if len(names) != 1:
        raise ValueError(f"the v1 pack format needs exactly one {role.value}, found {names}")
    return names[0]


def to_v1(spec: Mapping[str, Any]) -> v1common.Problem:
    roles = RoleTable.from_spec(spec)
    clock = spec["clock"]
    cur, volt = _one(roles, VariableRole.CONTROLLED_INPUT, clock), _one(roles, VariableRole.MEASUREMENT, clock)
    temp, state = _one(roles, VariableRole.NUISANCE_VARIABLE, clock), _one(roles, VariableRole.STATE_VARIABLE, clock)
    consts = spec["declared_family"]["constants"]

    def traj(t: Mapping[str, Any]) -> dict[str, Any]:
        c = t["columns"]
        return {"id": t["id"], "cell": t["unit_id"], "kind": "fixture", "t_s": c[clock], "current_A": c[cur],
                "voltage_V": c[volt], "temperature_C": c[temp], "z0": t["initial_state"][state],
                "capacity_Ah": consts["capacity_As"] / 3600.0}

    sets: dict[str, Any] = {"calibration": {"trajectories": [traj(t) for t in spec["sets"]["calibration"]]}}
    acceptance = {}
    for ours, theirs in _V1_SETS.items():
        if spec["sets"].get(ours):
            sets[theirs] = {"subsets": {k: [traj(t) for t in v] for k, v in spec["sets"][ours].items()}}
            for k in spec["sets"][ours]:
                bar = spec["acceptance"][f"{ours}/{k}"]
                acceptance[f"{theirs}/{k}"] = {"rmse_mV_max": bar["rmse_max"] * 1e3, "p95_abs_mV_max": bar["p95_abs_max"] * 1e3}
    b = spec["declared_family"]["parameter_bounds"]
    noise = spec["measurement_noise"]
    raw = {"schema": v1common.PROBLEM_SCHEMA, "problem_id": spec["problem_id"],
           "declared_model": {"family": "thevenin_1rc", "bounds": {"R0_ohm": b["R0"], "R1_ohm": b["R1"], "C1_F": b["C1"]},
                              "ocv": {"status": "MEASURED_FIXED", "interpolation": "linear", "knots_z_V": consts["ocv_knots"]},
                              "requested_parameters": list(spec["requested_parameters"])},
           "conventions": {"rest_band_A": 0.01, "hold": "backward"},
           "measurement_uncertainty": {"voltage_V": {"status": "DECLARED_TYPE_B", "standard_uncertainty": noise["sigma"]}
                                       if noise.get("sigma") is not None else {"status": "UNKNOWN"}},
           "sets": sets, "acceptance": acceptance}
    return v1common.Problem(raw)


# ---- OLD_MIND --------------------------------------------------------------------------------------------------
def old_mind(spec: Mapping[str, Any]) -> dict[str, str]:
    out = v1.mind(to_v1(spec), seeds=(v1.PRIMARY_SEED,))
    return {axis: a["disposition"] for axis, a in out["answers"].items()}


# ---- SEMANTIC_ROLES_ONLY ---------------------------------------------------------------------------------------
def _roles_load_pool(trajs: Sequence[v1common.Trajectory], band: float, ocv_knots: np.ndarray) -> v1.Pool:
    """v1's loaded-sample pool with the measured OCV, posed by role: settable (t_on, current), covariate (temperature).
    The charge state is used only through its dynamics (to form the observable), never as a free covariate."""
    X, C, y, refs, sc = [], [], [], [], []
    for tr, z in zip(trajs, v1._z(trajs)):
        for s, e in v1._runs(tr.current, band):
            for k in range(s, e + 1):
                if z[k] <= v1.MIN_SOC:
                    continue
                i, t_on = abs(tr.current[k]), tr.t[k] - tr.t[s - 1]
                X.append([t_on, i]); C.append([tr.temperature[k] + v1.KELVIN]); sc.append(i)
                y.append((float(np.interp(z[k], ocv_knots[:, 0], ocv_knots[:, 1])) - tr.voltage[k]) / i)
                refs.append(f"{tr.traj_id}#{k}")
    return v1.Pool(("t_on_s", "I_A"), ("T_K",), np.array(X, float).reshape(-1, 2), np.array(C, float).reshape(-1, 1),
                   np.array(y, float), refs, v1._dt_median(trajs), np.array(sc, float), "ohm")


def roles_mind(spec: Mapping[str, Any]) -> dict[str, str]:
    problem = to_v1(spec)
    roles = RoleTable.from_spec(spec)
    if not roles.names(VariableRole.CONTROLLED_INPUT) or problem.ocv_knots is None:
        raise ValueError("SEMANTIC_ROLES_ONLY is defined for a declared controlled input and a measured OCV")
    pid, band, seed, s = problem.problem_id, problem.rest_band, v1.PRIMARY_SEED, str(v1.PRIMARY_SEED)
    cal = problem.calibration()
    rec, run, _ = v1.run_probe(pid, "RELAXATION", v1.relax_pool(cal, band), seed)
    if run is None:
        rx = v1.TRANSLATION["RELAXATION"]["problem_refused"]
    else:
        rx, _key = v1._translate("RELAXATION", run, "t_off_s")
    answers = {"IDENTIFIABILITY": rx, "MODEL_ADEQUACY": v1common.NOT_ASSESSABLE, "MODEL_DISCREPANCY": v1common.NOT_ASSESSABLE}
    pool = _roles_load_pool(cal, band, problem.ocv_knots)
    for set_name, axis in (("within_cell_heldout", "WITHIN_CELL_GENERALIZATION"), ("cross_cell_heldout", "CROSS_CELL_TRANSFER")):
        sets = problem.heldout(set_name)
        if sets is None:
            answers[axis] = v1common.NOT_ASSESSABLE
            continue
        subs = []
        for subset, trajs in sets.items():
            ho = _roles_load_pool(trajs, band, problem.ocv_knots)
            region = v1._region(ho)
            if region is None:
                subs.append(v1common.NOT_ASSESSABLE)
                continue
            rec, run, mp = v1.run_probe(pid, f"PREDICTION[{set_name}/{subset}]", pool, seed, region)
            if run is None:
                subs.append(v1common.REFUSED)
            elif run.conclusion.kind is ConclusionKind.LAW:
                ev = v1._evaluate_law(run, mp, ho, problem.acceptance(set_name, subset), problem.voltage_sigma())
                subs.append(v1common.SUPPORTED if ev["meets_bar"] else v1common.NOT_SUPPORTED)
            else:
                subs.append(v1.TRANSLATION["PREDICTION"][run.conclusion.kind.value])
        answers[axis] = v1common.combine(subs)
    return answers


# ---- the representation arms -----------------------------------------------------------------------------------
def representation_only(spec: Mapping[str, Any]) -> dict[str, str]:
    a = assess(spec, fx.FAMILIES, roles=legacy_role_table(spec))
    return {axis: c.disposition.value for axis, c in a.claims.items()}


def combined(spec: Mapping[str, Any]) -> dict[str, str]:
    a = assess(spec, fx.FAMILIES)
    return {axis: c.disposition.value for axis, c in a.claims.items()}


RUN = {"OLD_MIND": old_mind, "REPRESENTATION_ONLY": representation_only, "SEMANTIC_ROLES_ONLY": roles_mind,
       "REPRESENTATION_PLUS_ROLES": combined}

__all__ = ["ARMS", "RUN", "combined", "old_mind", "representation_only", "roles_mind", "to_v1"]
