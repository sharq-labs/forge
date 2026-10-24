"""Build the candidate-visible v2 problem pack (evaluator side; the candidate never imports this module).

    python -m benchmarks.battery_rediscovery_v2.build_pack [--nasa-dir D:/forge-data/nasa_pcoe_battery]

Inputs, each verified against a pinned sha256 before it is read:
* three raw files of the public aging archive (cells 38, 39 and 40 at 44 C; never used by v0, v1 or the repsem
  repair);
* the LG HG2 pulse-window split files and measured OCV of the identifiability study (``data/*.json``), re-split here by
  state-of-charge set point instead of by current level (v1 split them by level).

Nothing is fitted here and no voltage is compared with any model.  Selection uses protocol covariates only (ambient,
load level, cycle order, set point).  Every source identity is replaced by a pseudonym; the mapping goes to
``evaluator/IDENTITY_MAP.json`` and the input digests to ``evaluator/PACK_PROVENANCE.json`` (both evaluator-only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
from typing import Any

import numpy as np

from .candidate.common import (
    FITTED_OCV_BOUNDS_V, FITTED_OCV_KNOTS_SOC, MANIFEST_SCHEMA, SPEC_SCHEMA, write_json,
)
from .candidate.families import EQUATIONS, ocv_parameter_names

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PACK = HERE / "candidate" / "pack"
EVAL = HERE / "evaluator"
NASA_DEFAULT = pathlib.Path("D:/forge-data/nasa_pcoe_battery")
LG_SRC = ROOT / "benchmarks" / "battery_1rc_identifiability" / "data"

NASA_ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"
NASA_FILES = {"B0038": "41d4a6977e3f3a46623f80ad8f6e5ba6ad83a2746403f71966c88a4722ffd409",
              "B0039": "0ea0a44622b61f13306cfc9c7080c7a6a8eb187da38607bfdc776974fcb5f000",
              "B0040": "1d7eb3dbf82bda46837831756999d911211b9ed0cc892c7e2e8d7f9059a5e013"}
NASA_SUBDIR = "extracted/3. BatteryAgingARC_25-44"
NASA_PSEUDONYM = {"B0038": "A", "B0039": "B", "B0040": "C"}
NASA_REST_BAND_A = 0.01
NASA_LEVELS_A = (1.0, 2.0, 4.0)

#: Discharge ordinals (0-based, per cell, discharge cycles only) chosen from the protocol census before any fit: in the
#: 44 C chamber the cells run at two load levels; early 1 A and 2 A runs calibrate, later ones are within-cell held out,
#: and cell C's early runs are the cross-cell set.  (A 24 C, 4 A problem was considered and dropped before any fit: at
#: 4 A the runs stop at the cutoff early, so the causal capacity basis is 0.56 Ah for one cell and 1.24 Ah for another,
#: and the charge state would mean different things in different cells.)
NASA_DESIGN = {
    "Q1": {"ambient_C": 44, "calibration": {"B0038": (14, 15, 39, 40), "B0039": (14, 15, 39, 40)},
           "within": {"B0038": (37, 38, 43, 44), "B0039": (37, 38, 43, 44)}, "cross": {"B0040": (14, 15, 39, 40)}},
}
LG_FILES = ("calibration.json", "heldout_pulses.json", "ocv.json")
LG_REST_BAND_A = 0.075
SOC_GROUP_GAP = 0.03

QUESTIONS = {
    "MODEL_ADEQUACY": "Does the declared family, calibrated on the calibration set, describe the calibration data within "
                      "the declared adequacy bar? SUPPORTED = adequate; NOT_SUPPORTED = inadequate.",
    "IDENTIFIABILITY": "Are the requested parameters identifiable from the calibration observations under the declared "
                       "measurement uncertainty? SUPPORTED = every requested parameter identifiable; NOT_SUPPORTED = not "
                       "all identifiable.",
    "WITHIN_CELL_GENERALIZATION": "Does the calibrated family predict the within-cell held-out set within its declared "
                                  "acceptance bar, inside the declared applicability domain? SUPPORTED / NOT_SUPPORTED.",
    "CROSS_CELL_TRANSFER": "Does the calibrated family predict the cross-cell held-out set within its declared acceptance "
                           "bar, inside the declared applicability domain? SUPPORTED / NOT_SUPPORTED.",
    "MODEL_DISCREPANCY": "Are the calibration residuals compatible with the declared measurement uncertainty and the "
                         "parameter uncertainty? SUPPORTED = compatible; NOT_SUPPORTED = model-form error resolved beyond "
                         "them.",
    "vocabulary": "Every answer is one of SUPPORTED, NOT_SUPPORTED, REVIEW, NOT_ASSESSABLE, REFUSED. REVIEW, "
                  "NOT_ASSESSABLE and REFUSED are non-committal: they never count as support.",
    "set_rule": "A held-out subset is judged only inside the declared applicability domain: an in-domain subset that "
                "fails its bar makes the set NOT_SUPPORTED; a subset holding any trajectory outside the domain is not "
                "scored, so the set cannot be SUPPORTED from it.",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _var(name: str, role: str, unit: str, basis: str, **kw: Any) -> dict[str, Any]:
    return {"name": name, "role": role, "unit": unit, "source": "protocol_metadata", "basis": basis, **kw}


def _variables(level_basis: str, latent_extra: tuple[str, ...] = (), knots: tuple[float, ...] = ()) -> list[dict]:
    out = [
        _var("t_s", "FIXED_PROTOCOL_CONDITION", "s", "the logger's sampling schedule"),
        _var("current_A", "CONTROLLED_INPUT", "A", "the cycler applies the programmed load current; positive is discharge"),
        _var("level_A", "FIXED_PROTOCOL_CONDITION", "A", level_basis),
        _var("soc", "STATE_VARIABLE", "1", "charge state: evolves by coulomb counting of the applied current from the "
             "declared initial state over the declared capacity basis; no column is recorded", driven_by=["current_A"]),
        _var("voltage_V", "MEASUREMENT", "V", "terminal voltage, the measured response"),
        _var("temperature_C", "NUISANCE_VARIABLE", "degC", "cell temperature, logged, not controlled"),
        _var("R0", "LATENT_PARAMETER", "ohm", "declared family parameter: series resistance"),
        _var("R1", "LATENT_PARAMETER", "ohm", "declared family parameter: RC-branch resistance"),
        _var("C1", "LATENT_PARAMETER", "F", "declared family parameter: RC-branch capacitance"),
    ]
    for name, z in zip(latent_extra, knots):
        out.append(_var(name, "LATENT_PARAMETER", "V", f"declared family parameter: fitted OCV table value at z = {z}"))
    return out


def _traj(tid: str, unit: str, kind: str, t, i, level: float, v, temp, z0: float, q_As: float) -> dict[str, Any]:
    cols = {"t_s": [float(x) for x in t], "current_A": [float(x) for x in i], "level_A": [float(level)] * len(t),
            "voltage_V": [float(x) for x in v], "temperature_C": [float(x) for x in temp]}
    for k, col in cols.items():
        if not all(math.isfinite(x) for x in col):
            raise SystemExit(f"{tid}: non-finite {k} value (refused, never repaired)")
    if any(b <= a for a, b in zip(cols["t_s"], cols["t_s"][1:])):
        raise SystemExit(f"{tid}: time is not strictly increasing (refused, never repaired)")
    return {"id": tid, "unit_id": unit, "kind": kind, "columns": cols, "initial_state": {"soc": float(z0)},
            "conditions": {"initial_polarization": 0.0, "capacity_As": float(q_As)}}


# ---- the aging archive (Q1) ----------------------------------------------------------------------------------------
def _nasa_cycles(nasa_dir: pathlib.Path, cell: str) -> tuple[list[Any], str]:
    import scipy.io as sio  # noqa: PLC0415

    path = nasa_dir / NASA_SUBDIR / f"{cell}.mat"
    raw = path.read_bytes()
    if _sha(raw) != NASA_FILES[cell]:
        raise SystemExit(f"{cell}: bytes do not match the pinned digest")
    m = sio.loadmat(path, squeeze_me=True, struct_as_record=False)[cell]
    return [c for c in m.cycle if c.type == "discharge"], _sha(raw)


def _arrays(c: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    d = c.data
    return (np.asarray(d.Time, float), -np.asarray(d.Current_measured, float), np.asarray(d.Voltage_measured, float),
            np.asarray(d.Temperature_measured, float))


def _delivered_Ah(c: Any) -> float:
    t, i, _, _ = _arrays(c)
    load = i[1:] > NASA_REST_BAND_A
    return float(np.sum(i[1:][load] * np.diff(t)[load])) / 3600.0


def _level(i: np.ndarray) -> float:
    loaded = i[i > 0.3]
    med = float(np.median(loaded))
    return min(NASA_LEVELS_A, key=lambda lv: abs(lv - med))


def build_nasa(pid: str, nasa_dir: pathlib.Path) -> tuple[dict, dict, dict]:
    design = NASA_DESIGN[pid]
    cells = sorted({c for part in ("calibration", "within", "cross") for c in design[part]})
    cycles, srcs = {}, {}
    for cell in cells:
        cycles[cell], srcs[f"{NASA_SUBDIR}/{cell}.mat"] = _nasa_cycles(nasa_dir, cell)
    ident: dict[str, Any] = {}
    sets: dict[str, list] = {}
    tags = {"calibration": "c", "within": "w", "cross": "x"}
    for part in ("calibration", "within", "cross"):
        out, n = [], 0
        for cell in sorted(design[part]):
            for ordinal in design[part][cell]:
                c = cycles[cell][ordinal]
                if int(c.ambient_temperature) != design["ambient_C"]:
                    raise SystemExit(f"{cell} discharge {ordinal}: ambient {c.ambient_temperature}, not the design's")
                t, i, v, temp = _arrays(c)
                basis_Ah = max(_delivered_Ah(e) for e in cycles[cell][:ordinal])
                n += 1
                tid = f"{pid}-{tags[part]}{n:02d}"
                level = _level(i)
                ident[tid] = {"source_file": f"{NASA_SUBDIR}/{cell}.mat", "cell": cell, "discharge_ordinal": ordinal,
                              "level_A": level, "capacity_basis_Ah": basis_Ah}
                out.append(_traj(tid, NASA_PSEUDONYM[cell], "cc_discharge_then_rest", t, i, level, v, temp, 1.0,
                                 basis_Ah * 3600.0))
        sets[part] = out
    knots = FITTED_OCV_KNOTS_SOC
    names = ocv_parameter_names(len(knots))
    chamber = design["ambient_C"]
    description = (f"Three sibling cells of one batch in a {chamber} C chamber. Each run: constant-current discharge at a "
                   "protocol-set level (1 A or 2 A) from full charge to the cell's cutoff voltage, then rest; about 10 s "
                   "sampling. Calibration: early runs of cells A and B at both levels. Within-cell held-out: later runs of "
                   "A and B at both levels. Cross-cell held-out: early runs of cell C at both levels. The open-circuit "
                   "voltage was not measured.")
    bar = {"rmse_max": 0.050, "p95_abs_max": 0.090}
    spec = {
        "schema": SPEC_SCHEMA, "problem_id": pid, "description": description, "clock": "t_s", "observable": "voltage_V",
        "variables": _variables("the load level the protocol set for the run", names, knots),
        "declared_family": {
            "family_id": "rc1_fitted_ocv/1", "rival": "rint_fitted_ocv/1", "equations": EQUATIONS,
            "parameter_bounds": {"R0": [0.0001, 1.0], "R1": [1e-05, 1.0], "C1": [1.0, 1000000.0],
                                 **{n: list(FITTED_OCV_BOUNDS_V) for n in names}},
            "constants": {"ocv_knots_soc": list(knots)},
            "ocv": {"status": "UNKNOWN_FITTED_TABLE", "representation": "piecewise-linear table on the declared knots; "
                    "the knot values are latent parameters", "knots_soc": list(knots), "bounds_V": list(FITTED_OCV_BOUNDS_V)}},
        "requested_parameters": ["R0", "R1", "C1"],
        "measurement_noise": {"sigma": None, "independent": None, "status": "UNKNOWN",
                              "basis": "no accuracy statement is published for the logger; the uncertainty is never set "
                                       "to zero and no residual estimate replaces it"},
        "adequacy_bar": dict(bar),
        "acceptance": {"within_unit_heldout/later_cycles": dict(bar), "cross_unit_heldout/other_cell": dict(bar)},
        "applicability": {"variables": ["level_A", "soc", "temperature_C"],
                          "widen": {"level_A": 0.05, "soc": 0.02, "temperature_C": 1.0},
                          "basis": "the calibration set's range of each listed variable (the charge state through the "
                                   "family's reconstruction), widened by the declared scope margins; the margins are a "
                                   "scope policy, not a measurement accuracy",
                          "soc_support": [0.0, 1.0]},
        "conventions": {"current_sign": "positive is discharge", "hold": "backward", "rest_band_A": NASA_REST_BAND_A,
                        "initial_state": "soc = 1 at sample 0 (full charge, then rest)",
                        "initial_polarization": "0 V at sample 0 (the run starts from rest)",
                        "capacity_basis": "per trajectory: the largest charge delivered by an earlier discharge of the "
                                          "same cell (causal)", "scored_samples": "every sample after the first"},
        "questions": QUESTIONS,
        "sets": {"calibration": sets["calibration"], "within_unit_heldout": {"later_cycles": sets["within"]},
                 "cross_unit_heldout": {"other_cell": sets["cross"]}},
    }
    return spec, ident, {"raw_sha256": srcs, "archive_sha256": NASA_ARCHIVE_SHA256}


# ---- the LG HG2 pulses (Q2) ---------------------------------------------------------------------------------------
def _lg(name: str) -> tuple[dict, str]:
    path = LG_SRC / name
    raw = path.read_bytes()
    pinned = path.with_suffix(".sha256").read_bytes().split()[0].decode()
    if _sha(raw) != pinned:
        raise SystemExit(f"{name}: bytes do not match the pinned digest")
    return json.loads(raw), pinned


def soc_groups(windows: list[dict]) -> list[list[dict]]:
    """Group pulse windows by state-of-charge set point: sorted by z0 descending, a new group starts when z0 falls more
    than SOC_GROUP_GAP below the group's first window."""
    groups: list[list[dict]] = []
    for w in sorted(windows, key=lambda w: (-w["z0"], w["level_A"])):
        if groups and groups[-1][0]["z0"] - w["z0"] <= SOC_GROUP_GAP:
            groups[-1].append(w)
        else:
            groups.append([w])
    return groups


def build_lg() -> tuple[dict, dict, dict]:
    cal, d1 = _lg("calibration.json")
    held, d2 = _lg("heldout_pulses.json")
    ocv, d3 = _lg("ocv.json")
    q = cal["q_hppc_Ah"]
    assert held["q_hppc_Ah"] == q == ocv["q_hppc_Ah"]
    groups = soc_groups(cal["windows"] + held["windows"])
    # rank 0 = highest set point; calibration takes the even ranks and the lowest set point, held-out the rest
    cal_ranks = {r for r in range(len(groups)) if r % 2 == 0} | {len(groups) - 1}
    ident: dict[str, Any] = {}
    parts: dict[str, list] = {"calibration": [], "within": []}
    counters = {"calibration": 0, "within": 0}
    for r, g in enumerate(groups):
        part = "calibration" if r in cal_ranks else "within"
        for w in sorted(g, key=lambda w: w["level_A"]):
            counters[part] += 1
            tid = f"Q2-{'c' if part == 'calibration' else 'w'}{counters[part]:02d}"
            ident[tid] = {"source_role": "calibration" if w in cal["windows"] else "heldout_pulses", "step": w["step"],
                          "level_A": w["level_A"], "soc_group_rank": r}
            parts[part].append(_traj(tid, "A", "rest_pulse_rest", w["time_s"], w["current_A"], w["level_A"],
                                     w["voltage_V"], w["temperature_C"], w["z0"], q * 3600.0))
    knots = sorted([[k[0], k[1]] for k in ocv["knots_z_V_sample"]])
    bar = {"rmse_max": 0.015, "p95_abs_max": 0.030}
    spec = {
        "schema": SPEC_SCHEMA, "problem_id": "Q2",
        "description": f"One cell at 25 C ambient. 10 s discharge pulses at four protocol-set current levels (3, 6, 12 and "
                       f"18 A), each with its preceding and following rest (0.1 s sampling), at {len(groups)} state-of-charge "
                       "set points. Calibration: the pulses at alternate set points, including the highest and the lowest. "
                       "Within-cell held-out: the pulses at the other set points. No second cell is supplied. The OCV "
                       "was measured from long rests and is fixed.",
        "clock": "t_s", "observable": "voltage_V",
        "variables": _variables("the pulse current level the protocol set for the window"),
        "declared_family": {
            "family_id": "rc1_measured_ocv/1", "rival": "rint_measured_ocv/1", "equations": EQUATIONS,
            "parameter_bounds": {"R0": [0.001, 0.2], "R1": [0.0001, 0.2], "C1": [1.0, 1000000.0]},
            "constants": {"ocv_knots": knots},
            "ocv": {"status": "MEASURED_FIXED", "interpolation": "linear", "knots_z_V": knots}},
        "requested_parameters": ["R0", "R1", "C1"],
        "measurement_noise": {"sigma": 0.005 / 3 ** 0.5, "independent": None, "status": "DECLARED_TYPE_B",
                              "half_width": 0.005, "distribution": "uniform",
                              "basis": "publisher's instrument accuracy statement (0.1 % of the 5 V full scale); a bound "
                                       "on the error, not a statement that errors are independent"},
        "adequacy_bar": dict(bar),
        "acceptance": {"within_unit_heldout/pulses_alternate_soc": dict(bar)},
        "applicability": {"variables": ["level_A", "soc", "temperature_C"],
                          "widen": {"level_A": 0.075, "soc": 0.02, "temperature_C": 1.0},
                          "basis": "the calibration set's range of each listed variable (the charge state through the "
                                   "family's reconstruction), widened by the published current (0.075 A) and temperature "
                                   "(1 C) accuracies and a 0.02 charge-state scope margin",
                          "soc_support": [knots[0][0], knots[-1][0]]},
        "conventions": {"current_sign": "positive is discharge", "hold": "backward", "rest_band_A": LG_REST_BAND_A,
                        "initial_state": "soc per window, from the coulomb count",
                        "initial_polarization": "0 V at the window start (at least 590 s of rest before each pulse)",
                        "capacity_basis": "one charge for every window (the whole characterisation record)",
                        "scored_samples": "every sample after the first"},
        "questions": QUESTIONS,
        "sets": {"calibration": parts["calibration"], "within_unit_heldout": {"pulses_alternate_soc": parts["within"]}},
    }
    return spec, ident, {"split_sha256": {"calibration.json": d1, "heldout_pulses.json": d2, "ocv.json": d3},
                         "soc_groups": [[round(w["z0"], 4) for w in g] for g in groups],
                         "calibration_ranks": sorted(cal_ranks)}


def build_all(nasa_dir: pathlib.Path = NASA_DEFAULT) -> dict[str, tuple[dict, dict, dict]]:
    return {"Q1": build_nasa("Q1", nasa_dir), "Q2": build_lg()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasa-dir", type=pathlib.Path, default=NASA_DEFAULT)
    a = ap.parse_args(argv)
    manifest = {"schema": MANIFEST_SCHEMA, "problems": {}}
    identity, provenance = {}, {}
    for pid, (spec, ident, srcs) in build_all(a.nasa_dir).items():
        sha = write_json(PACK / f"{pid}.json", spec)
        manifest["problems"][pid] = {"file": f"{pid}.json", "sha256": sha}
        identity[pid] = ident
        provenance[pid] = {**srcs, "pack_sha256": sha}
    write_json(PACK / "MANIFEST.json", manifest)
    write_json(EVAL / "IDENTITY_MAP.json", identity)
    write_json(EVAL / "PACK_PROVENANCE.json", provenance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
