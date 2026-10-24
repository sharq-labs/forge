"""Build the candidate-visible problem pack from the existing preregistered split DATA files (evaluator side).

    python -m benchmarks.battery_rediscovery_v0.build_pack

Inputs are only the trajectory/split data files, each verified against its pinned .sha256; no result, outcome or
calibration record is read.  The splits are reused unchanged (cells and cycles/windows as preregistered); every source
identity (dataset, cell, file, cycle ordinal, digest) is replaced by a pseudonym, and the mapping is written to
``evaluator/IDENTITY_MAP.json`` (evaluator-only).  The declared inputs (model family, bounds, acceptance bars,
measurement uncertainty, applicability rule, conventions) are transcribed from the same preregistrations' DECLARED
sections, never from their outcomes.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from .candidate.common import PROBLEM_SCHEMA, write_json

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PACK = HERE / "candidate" / "pack"
EVAL = HERE / "evaluator"

P1_SRC = ROOT / "benchmarks" / "battery_1rc_closure" / "data"
P2_SRC = ROOT / "benchmarks" / "battery_1rc_identifiability" / "data"

QUESTIONS = {
    "MODEL_ADEQUACY": "Does the declared model family adequately describe the data in the declared domain? SUPPORTED = "
                      "adequate; NOT_SUPPORTED = inadequate.",
    "IDENTIFIABILITY": "Are the requested parameters identifiable from the supplied calibration observations? SUPPORTED = "
                       "every requested parameter identifiable; NOT_SUPPORTED = not all identifiable.",
    "WITHIN_CELL_GENERALIZATION": "Does calibration predict the within-cell held-out set, inside the declared domain and "
                                  "acceptance bar? SUPPORTED / NOT_SUPPORTED.",
    "CROSS_CELL_TRANSFER": "Does the evidence support transferring the calibrated model to the cross-cell held-out set? "
                           "SUPPORTED / NOT_SUPPORTED.",
    "MODEL_DISCREPANCY": "Are the declared model's residuals compatible with measurement and parameter uncertainty? "
                         "SUPPORTED = compatible; NOT_SUPPORTED = structured model-form error.",
    "vocabulary": "Every answer is one of SUPPORTED, NOT_SUPPORTED, REVIEW, NOT_ASSESSABLE, REFUSED. REVIEW, "
                  "NOT_ASSESSABLE and REFUSED are non-committal: they never count as support.",
}

MODEL_TEXT = ("V = OCV(z) - I*R0 - v1;  dv1/dt = I/C1 - v1/(R1*C1);  dz/dt = -I/(3600*Q).  Positive I is discharge. "
              "The Rint reduction (R1 = 0) is the declared rival.")


def _verified(path: pathlib.Path) -> bytes:
    raw = path.read_bytes()
    pinned = path.with_suffix(".sha256").read_bytes().split()[0].decode()
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise SystemExit(f"{path.name}: bytes do not match the pinned digest")
    return raw


def _traj(tid: str, cell: str, kind: str, d: dict, z0: float, cap: float) -> dict:
    return {"id": tid, "cell": cell, "kind": kind, "t_s": d["time_s"], "current_A": d["current_A"],
            "voltage_V": d["voltage_V"], "temperature_C": d["temperature_C"], "z0": z0, "capacity_Ah": cap}


def build_p1() -> tuple[dict, dict, dict]:
    pseud = {"B0005": "A", "B0007": "B", "B0006": "C"}
    files = {"calibration": "calibration.json", "within": "within_cell_holdout.json", "cross": "cross_cell_validation.json"}
    tags = {"calibration": "c", "within": "w", "cross": "x"}
    srcs, ident = {}, {}
    sets = {}
    for role, name in files.items():
        raw = _verified(P1_SRC / name)
        srcs[name] = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw)
        trajs = []
        for k, c in enumerate(data["cycles"]):
            tid = f"P1-{tags[role]}{k + 1:02d}"
            ident[tid] = {"source_file": f"benchmarks/battery_1rc_closure/data/{name}", "cell": c["cell"],
                          "ordinal": c["ordinal"], "cycle_index": c["cycle_index"]}
            trajs.append(_traj(tid, pseud[c["cell"]], "cc_discharge_then_rest", c, 1.0, c["capacity_basis_Ah"]))
        sets[role] = trajs
    problem = {
        "schema": PROBLEM_SCHEMA, "problem_id": "P1",
        "description": "Three sibling cells of one batch, one protocol: constant-current discharge from full charge to the "
                       "cell's cutoff, then rest; about 19 s sampling. Calibration: early cycles of cells A and B. "
                       "Within-cell held-out: the next cycles of A and B. Cross-cell held-out: early cycles of cell C.",
        "declared_model": {"family": "thevenin_1rc", "equations": MODEL_TEXT, "requested_parameters": ["R0", "R1", "C1"],
                           "bounds": {"R0_ohm": [0.0001, 1.0], "R1_ohm": [1e-05, 1.0], "C1_F": [1.0, 1000000.0]},
                           "ocv": {"status": "UNKNOWN_FITTED_TABLE", "knots_soc": [0.0, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4,
                                   0.5, 0.6, 0.7, 0.8, 0.9, 1.0], "bounds_V": [2.0, 4.5]}},
        "conventions": {"current_sign": "positive is discharge", "rest_band_A": 0.01, "hold": "backward",
                        "initial_polarization_V": 0.0, "initial_soc": "z0 = 1 at sample 0 (full charge, then rest)",
                        "capacity_basis": "per trajectory: the largest charge delivered by an earlier discharge of the same "
                                          "cell (causal)", "scored_samples": "every sample after the first"},
        "measurement_uncertainty": {"voltage_V": {"status": "UNKNOWN"}, "current_A": {"status": "UNKNOWN"},
                                    "temperature_C": {"status": "UNKNOWN"}},
        "acceptance": {"within_cell_heldout/later_cycles": {"rmse_mV_max": 50.0, "p95_abs_mV_max": 90.0},
                       "cross_cell_heldout/other_cell": {"rmse_mV_max": 50.0, "p95_abs_mV_max": 90.0}},
        "applicability": {"temperature_C": {"basis": "calibration measured minimum and maximum", "widen_by": 0.0},
                          "current_A": {"basis": "calibration maximum", "widen_by": 0.0},
                          "soc": {"min": 0.0, "max": 1.0},
                          "set_rule": "a held-out set that fails the bar is NOT_SUPPORTED; a set that meets it but holds "
                                      "any trajectory outside the domain cannot be SUPPORTED"},
        "questions": QUESTIONS,
        "sets": {"calibration": {"trajectories": sets["calibration"]},
                 "within_cell_heldout": {"subsets": {"later_cycles": sets["within"]}},
                 "cross_cell_heldout": {"subsets": {"other_cell": sets["cross"]}}},
    }
    return problem, ident, srcs


def build_p2() -> tuple[dict, dict, dict]:
    srcs, ident = {}, {}

    def load(name: str) -> dict:
        raw = _verified(P2_SRC / name)
        srcs[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    cal, pulses, cc, ocv = load("calibration.json"), load("heldout_pulses.json"), load("heldout_cc.json"), load("ocv.json")
    q = cal["q_hppc_Ah"]
    assert pulses["q_hppc_Ah"] == q == cc["q_hppc_Ah"] == ocv["q_hppc_Ah"]

    def windows(data: dict, role: str, tag: str) -> list[dict]:
        out = []
        for k, w in enumerate(data["windows"]):
            tid = f"P2-{tag}{k + 1:02d}"
            ident[tid] = {"source_file": f"benchmarks/battery_1rc_identifiability/data/{role}.json", "step": w["step"],
                          "level_A": w["level_A"]}
            out.append(_traj(tid, "A", "rest_pulse_rest", w, w["z0"], q))
        return out

    cc_trajs = []
    for k, t in enumerate(cc["tests"]):
        tid = f"P2-k{k + 1:02d}"
        ident[tid] = {"source_file": "benchmarks/battery_1rc_identifiability/data/heldout_cc.json", "test": t["test"]}
        cc_trajs.append(_traj(tid, "A", "rest_then_cc_discharge", t, t["z0"], q))
    knots = sorted([[k[0], k[1]] for k in ocv["knots_z_V_sample"]])
    problem = {
        "schema": PROBLEM_SCHEMA, "problem_id": "P2",
        "description": "One new cell at 25 C ambient. Calibration: 10 s discharge pulses at two current levels across SOC, "
                       "each with its preceding and following rest (0.1 s sampling). Within-cell held-out: pulses at two "
                       "other current levels, and one constant-current discharge from rest. No second cell is supplied. "
                       "The OCV was measured from long rests and is fixed.",
        "declared_model": {"family": "thevenin_1rc", "equations": MODEL_TEXT, "requested_parameters": ["R0", "R1", "C1"],
                           "bounds": {"R0_ohm": [0.001, 0.2], "R1_ohm": [0.0001, 0.2], "C1_F": [1.0, 1000000.0]},
                           "ocv": {"status": "MEASURED_FIXED", "knots_z_V": knots, "interpolation": "linear"}},
        "conventions": {"current_sign": "positive is discharge", "rest_band_A": 0.075, "hold": "backward",
                        "initial_polarization_V": 0.0, "initial_soc": "z0 per trajectory, from the coulomb count",
                        "capacity_basis": "one charge for every trajectory (the whole characterisation record)",
                        "scored_samples": "every sample after the first"},
        "measurement_uncertainty": {
            "voltage_V": {"status": "DECLARED_TYPE_B", "half_width": 0.005, "standard_uncertainty": 0.005 / 3 ** 0.5,
                          "distribution": "uniform", "basis": "publisher's instrument accuracy statement"},
            "current_A": {"status": "DECLARED_TYPE_B", "half_width": 0.075, "standard_uncertainty": 0.075 / 3 ** 0.5,
                          "distribution": "uniform", "basis": "publisher's instrument accuracy statement"},
            "temperature_C": {"status": "DECLARED_TYPE_B", "half_width": 1.0, "standard_uncertainty": 1.0 / 3 ** 0.5,
                              "distribution": "uniform", "basis": "publisher's sensor accuracy statement"},
            "time_s": {"status": "UNKNOWN"}},
        "acceptance": {"within_cell_heldout/pulses": {"rmse_mV_max": 15.0, "p95_abs_mV_max": 30.0},
                       "within_cell_heldout/cc": {"rmse_mV_max": 25.0, "p95_abs_mV_max": 50.0}},
        "applicability": {"temperature_C": {"basis": "calibration measured minimum and maximum", "widen_by": 1.0},
                          "current_A": {"basis": "calibration maximum", "widen_by": 0.075},
                          "soc": {"min": knots[0][0], "max": knots[-1][0]},
                          "set_rule": "a held-out set that fails the bar is NOT_SUPPORTED; a set that meets it but holds "
                                      "any trajectory outside the domain cannot be SUPPORTED"},
        "questions": QUESTIONS,
        "sets": {"calibration": {"trajectories": windows(cal, "calibration", "c")},
                 "within_cell_heldout": {"subsets": {"pulses": windows(pulses, "heldout_pulses", "h"), "cc": cc_trajs}}},
    }
    return problem, ident, srcs


def main() -> int:
    manifest = {"schema": "forge.battery_rediscovery.pack_manifest/1", "problems": {}}
    identity, provenance = {}, {}
    for pid, builder in (("P1", build_p1), ("P2", build_p2)):
        problem, ident, srcs = builder()
        sha = write_json(PACK / f"{pid}.json", problem)
        manifest["problems"][pid] = {"file": f"{pid}.json", "sha256": sha}
        identity[pid] = ident
        provenance[pid] = {"source_data_sha256": srcs, "pack_sha256": sha}
    write_json(PACK / "MANIFEST.json", manifest)
    write_json(EVAL / "IDENTITY_MAP.json", identity)
    write_json(EVAL / "PACK_PROVENANCE.json", provenance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
