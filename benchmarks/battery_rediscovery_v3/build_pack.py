"""Build the v3 CandidateBundle (evaluator side; the candidate never imports this module).

    python -m benchmarks.battery_rediscovery_v3.build_pack

Inputs are the ELIGIBLE_PRIMARY_V3 units of ``EvaluatorVault/CENSUS.json`` plus the two v2 problems as the SECONDARY
BRIDGE SET, each verified against a pinned digest before it is read.  Nothing is fitted here and no voltage is compared
with any model.  Every rule below is structural (protocol segments, sample timing, charge counting, protocol order) and
was fixed before the pack was built; a trajectory that fails a rule is excluded with its reason in
``EvaluatorVault/ELIGIBILITY.json``, never repaired.

Problem kinds (all in the GEN1 problem schema ``forge.mind.repsem.problem/1``):

* **GITT pulses, measured OCV** (24 problems: 12 cells x {beginning of life, latest common RPT}).  One cell per problem.
  A window is the last 600 s of the rest before a 2.5 A, 288 s pulse, the pulse, and the first 3000 s of the following
  rest.  A window is admitted iff its pre-rest is >= 600 s at |I| <= 0.01 A, its pulse lasts the protocol duration
  (288 +- 2 s) with every sample within 2 % of 2.5 A, and its post-rest is >= 3000 s.  The full pulses are ranked from
  the highest charge state (rank 0) down; calibration = even ranks plus the lowest rank, within-cell held-out = the
  others (the v2 rule, inherited).  Cross-cell held-out = the partner cell's within-cell windows at the same RPT (partner:
  the next cell in its rig/ageing group, A->B->C->A and F->G->H->F, fixed from metadata).
  Charge state: 1 at the end of the pre-GITT rest, coulomb-counted (backward hold, full resolution) over the GITT's total
  discharged charge, so 0 at the end of the file.  Measured OCV: the voltage of the last sample before each CALIBRATION
  pulse (>= 3600 s relaxed) and the last sample of the file (6 h relaxed, charge state 0); no held-out voltage enters the
  OCV.  Decimation: all samples within 2 s after any current change, the 2 samples before any change, and one sample per
  2 s of pulse, per 20 s of post-rest and per 60 s of pre-rest.  Voltage uncertainty UNKNOWN.  Bars: the pulse class,
  15 / 30 mV (inherited verbatim from v1/v2).  Bounds and scope margins inherited from v2 (Q2 bounds; Q1 margins).
* **Constant-current rate tests, fitted OCV** (3 problems, one cell each).  Each run: discharge from full charge (CC-CV
  to 4.2 V, C/100 termination, 2 h rest) to 2.5 V at a protocol rate, then the following rest until the next current.
  Calibration = the cell's 0.5 A and 7.5 A runs; within-cell held-out = its 2.5 A and 5 A runs (rate interpolation);
  cross-cell held-out = the partner cell's 2.5 A and 5 A runs (02->03->04->02).  Capacity basis per cell: the charge
  delivered by that cell's 0.5 A run (the protocol's capacity check, which precedes the other rates).  Bars: the
  aging-archive class, 50 / 90 mV (inherited).  Fitted OCV on the GEN1 knots.  Uncertainty UNKNOWN.
* **Aging-archive discharges, fitted OCV** (5 problems, one cell each, no cross-cell set: the sibling cells' cutoff
  voltages differ, so their charge-state coordinate means something different).  A discharge is admitted iff the
  preceding charge ends at <= 30 mA (protocol 20 mA + 10 mA band), its loaded median is within 5 % of the declared level,
  and it ends in rest.  Calibration = the first 4 admitted discharges with ordinal >= 1; within-cell held-out = the first 4
  admitted discharges with ordinal >= half the cell's discharge count.  Capacity basis: the largest charge delivered by an
  earlier discharge of the same cell (causal, v2).  Bars 50 / 90 mV.  Uncertainty UNKNOWN.
* **Bridge** (2 problems): the v2 pack's Q1 and Q2, byte-identical.  Never counted in the primary conclusion.

Every source identity is replaced by a pseudonym; the mapping goes to ``EvaluatorVault/IDENTITY_MAP.json`` and the input
digests to ``EvaluatorVault/PACK_PROVENANCE.json`` (both evaluator-only).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
from typing import Any

import numpy as np

from benchmarks.battery_rediscovery_v2 import build_pack as v2bp
from benchmarks.battery_rediscovery_v2.candidate.common import (
    FITTED_OCV_BOUNDS_V, FITTED_OCV_KNOTS_SOC, MANIFEST_SCHEMA, SPEC_SCHEMA, write_json,
)
from benchmarks.battery_rediscovery_v2.candidate.families import EQUATIONS, ocv_parameter_names

from . import extract

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACK = HERE / "CandidateBundle"
VAULT = HERE / "EvaluatorVault"
DATA = pathlib.Path("D:/forge-data")
V2_PACK = ROOT / "benchmarks" / "battery_rediscovery_v2" / "candidate" / "pack"
BRIDGE = ("Q1", "Q2")

REST_BAND_A = 0.01
SCOPE_WIDEN = {"level_A": 0.05, "soc": 0.02, "temperature_C": 1.0}          # v2 Q1 scope margins, inherited
PULSE_BAR = {"rmse_max": 0.015, "p95_abs_max": 0.030}                      # v1/v2 pulse class, inherited
ARCHIVE_BAR = {"rmse_max": 0.050, "p95_abs_max": 0.090}                    # v1/v2 aging-archive class, inherited
MEASURED_BOUNDS = {"R0": [0.001, 0.2], "R1": [0.0001, 0.2], "C1": [1.0, 1000000.0]}   # v2 Q2
FITTED_BOUNDS = {"R0": [0.0001, 1.0], "R1": [1e-05, 1.0], "C1": [1.0, 1000000.0]}     # v2 Q1

GITT_LEVEL_A = 2.5
GITT_PULSE_S = 288.0
GITT_PULSE_TOL_S = 2.0
LEVEL_REL_TOL = 0.02
PRE_REST_S = 600.0
POST_REST_S = 3000.0
DENSE_AFTER_CHANGE_S = 2.0
GRID_S = {"pre": 60.0, "pulse": 2.0, "post": 20.0}
PARTNER = {"A": "B", "B": "C", "C": "A", "F": "G", "G": "H", "H": "F"}

CHEN_CELLS = ("LGM50_cell02", "LGM50_cell03", "LGM50_cell04")
CHEN_PARTNER = {"LGM50_cell02": "LGM50_cell03", "LGM50_cell03": "LGM50_cell04", "LGM50_cell04": "LGM50_cell02"}
CHEN_CAL_RATES = (0.5, 7.5)
CHEN_HELD_RATES = (2.5, 5.0)
CHEN_TERMINATION_A = 0.05

NASA_CELLS = {"B0029": "3. BatteryAgingARC_25-44", "B0030": "3. BatteryAgingARC_25-44",
              "B0031": "3. BatteryAgingARC_25-44", "B0032": "3. BatteryAgingARC_25-44",
              "B0051": "5. BatteryAgingARC_49_50_51_52"}
NASA_TERMINATION_A = 0.020
NASA_N_CAL = 4
NASA_N_HELD = 4

QUESTIONS = v2bp.QUESTIONS


class DesignRefused(Exception):
    """A unit cannot meet the fixed design: the problem is excluded (recorded), never relaxed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _variables(level_basis: str, knots: tuple[float, ...] = ()) -> list[dict]:
    return v2bp._variables(level_basis, ocv_parameter_names(len(knots)), knots)


def _traj(tid, unit, kind, t, i, level, v, temp, z0, q_As) -> dict[str, Any]:
    return v2bp._traj(tid, unit, kind, t, i, level, v, temp, z0, q_As)


def _check_pin(path: pathlib.Path, sha: str) -> bytes:
    raw = path.read_bytes()
    if _sha(raw) != sha:
        raise SystemExit(f"{path}: bytes do not match the pinned digest")
    return raw


def _measured_family(knots: list[list[float]]) -> dict[str, Any]:
    return {"family_id": "rc1_measured_ocv/1", "rival": "rint_measured_ocv/1", "equations": EQUATIONS,
            "parameter_bounds": {k: list(v) for k, v in MEASURED_BOUNDS.items()}, "constants": {"ocv_knots": knots},
            "ocv": {"status": "MEASURED_FIXED", "interpolation": "linear", "knots_z_V": knots}}


def _fitted_family() -> dict[str, Any]:
    names = ocv_parameter_names(len(FITTED_OCV_KNOTS_SOC))
    return {"family_id": "rc1_fitted_ocv/1", "rival": "rint_fitted_ocv/1", "equations": EQUATIONS,
            "parameter_bounds": {**{k: list(v) for k, v in FITTED_BOUNDS.items()},
                                 **{n: list(FITTED_OCV_BOUNDS_V) for n in names}},
            "constants": {"ocv_knots_soc": list(FITTED_OCV_KNOTS_SOC)},
            "ocv": {"status": "UNKNOWN_FITTED_TABLE", "representation": "piecewise-linear table on the declared knots; "
                    "the knot values are latent parameters", "knots_soc": list(FITTED_OCV_KNOTS_SOC),
                    "bounds_V": list(FITTED_OCV_BOUNDS_V)}}


NOISE_UNKNOWN = {"sigma": None, "independent": None, "status": "UNKNOWN",
                 "basis": "no accuracy statement is published for the instrument; the uncertainty is never set to zero and "
                          "no residual estimate replaces it"}


def _applicability(basis: str, soc_support: list[float]) -> dict[str, Any]:
    return {"variables": ["level_A", "soc", "temperature_C"], "widen": dict(SCOPE_WIDEN), "basis": basis,
            "soc_support": soc_support}


SCOPE_BASIS = ("the calibration set's range of each listed variable (the charge state through the family's "
               "reconstruction), widened by the declared scope margins; the margins are a scope policy, not a measurement "
               "accuracy")


# ---- GITT (Kirkaldy) ---------------------------------------------------------------------------------------------
def _read_gitt(name: str, sha: str) -> dict[str, np.ndarray]:
    path = DATA / "kirkaldy2024" / "v3_rpt" / name
    _check_pin(path, sha)
    a = np.loadtxt(path, delimiter=",", skiprows=1)
    t, v, i_mA, _q, temp = a.T
    return {"t": t, "v": v, "i": -i_mA / 1000.0, "T": temp}


def _segments(i: np.ndarray) -> list[tuple[int, int, str]]:
    """Maximal runs of rest (|I| <= band), discharge (I > band) and charge (I < -band): (first, last, kind)."""
    kind = np.where(i > REST_BAND_A, "D", np.where(i < -REST_BAND_A, "C", "R"))
    out, s = [], 0
    for k in range(1, i.size + 1):
        if k == i.size or kind[k] != kind[s]:
            out.append((s, k - 1, str(kind[s])))
            s = k
    return out


def _keep(t: np.ndarray, lo: int, hi: int, change_points: list[int], grid: dict[int, float]) -> np.ndarray:
    """Indices in [lo, hi] kept by the decimation rule (see the module docstring)."""
    keep = {lo, hi}
    for c in change_points:
        for k in range(max(lo, c - 2), c):
            keep.add(k)
        k = c
        while k <= hi and t[k] - t[c] <= DENSE_AFTER_CHANGE_S + 1e-9:
            keep.add(k)
            k += 1
    for start, step in grid.items():
        nxt = t[start]
        for k in range(start, hi + 1):
            if t[k] >= nxt - 1e-9:
                keep.add(k)
                nxt = t[k] + step
            if k + 1 <= hi and k + 1 in grid:
                break
    return np.array(sorted(k for k in keep if lo <= k <= hi))


def gitt_windows(d: dict[str, np.ndarray]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    t, i = d["t"], d["i"]
    segs = _segments(i)
    first_d = next(n for n, s in enumerate(segs) if s[2] == "D")
    if segs[first_d - 1][2] != "R":
        raise SystemExit("the GITT does not start its discharge from rest")
    start = segs[first_d - 1][1]                        # last sample of the pre-GITT rest: charge state 1
    dq = np.zeros_like(t)
    dq[1:] = np.where(i[1:] > 0, i[1:], 0.0) * np.diff(t)   # backward hold
    cum = np.cumsum(dq) - np.cumsum(dq)[start]
    q_total = float(cum[-1])
    z = 1.0 - cum / q_total
    windows, excluded = [], []
    for n in range(first_d, len(segs)):
        s0, s1, kind = segs[n]
        if kind != "D":
            continue
        pre, post = segs[n - 1], (segs[n + 1] if n + 1 < len(segs) else None)
        dur = t[s1] - t[s0 - 1]
        why = []
        if pre[2] != "R" or t[pre[1]] - t[pre[0]] < PRE_REST_S:
            why.append("pre-rest shorter than 600 s")
        if abs(dur - GITT_PULSE_S) > GITT_PULSE_TOL_S:
            why.append(f"pulse lasts {dur:.1f} s, not the protocol 288 s (ends at the cutoff)")
        if np.any(np.abs(i[s0:s1 + 1] - GITT_LEVEL_A) > LEVEL_REL_TOL * GITT_LEVEL_A):
            why.append("pulse current leaves the 2 % band around 2.5 A")
        if post is None or post[2] != "R" or t[post[1]] - t[post[0]] < POST_REST_S:
            why.append("post-rest shorter than 3000 s")
        if why:
            excluded.append({"pulse_start_s": float(t[s0]), "why": why})
            continue
        lo = int(np.searchsorted(t, t[s0 - 1] - PRE_REST_S, side="left"))
        hi = int(np.searchsorted(t, t[s1] + POST_REST_S, side="right") - 1)
        idx = _keep(t, lo, hi, [s0, s1 + 1], {lo: GRID_S["pre"], s0: GRID_S["pulse"], s1 + 1: GRID_S["post"]})
        windows.append({"idx": idx, "pre_end": s0 - 1, "z_pre_end": float(z[s0 - 1]), "v_pre_end": float(d["v"][s0 - 1]),
                        "pulse_start_s": float(t[s0])})
    meta = {"q_total_As": q_total, "z_end": float(z[-1]), "v_end": float(d["v"][-1]),
            "final_rest_s": float(t[segs[-1][1]] - t[segs[-1][0]]) if segs[-1][2] == "R" else 0.0,
            "pulses_admitted": len(windows), "pulses_excluded": excluded, "z": z}
    return windows, meta


def _rank_split(windows: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    order = sorted(range(len(windows)), key=lambda k: -windows[k]["z_pre_end"])
    cal = {r for r in range(len(order)) if r % 2 == 0} | {len(order) - 1}
    return sorted(order[r] for r in cal), sorted(order[r] for r in range(len(order)) if r not in cal)


def build_gitt(pid: str, expt: int, cell: str, rpt: int, unit: str, partner_unit: str,
               members: dict[str, Any]) -> tuple[dict, dict, dict, dict]:
    own_name = extract.member_name(expt, cell, rpt)
    par_cell = PARTNER[cell]
    par_name = extract.member_name(expt, par_cell, rpt)
    d_own, d_par = _read_gitt(own_name, members[own_name]["sha256"]), _read_gitt(par_name, members[par_name]["sha256"])
    w_own, m_own = gitt_windows(d_own)
    w_par, m_par = gitt_windows(d_par)
    cal_k, held_k = _rank_split(w_own)
    _pc, par_held_k = _rank_split(w_par)
    knots = sorted({(round(w_own[k]["z_pre_end"], 12), w_own[k]["v_pre_end"]) for k in cal_k}
                   | {(round(m_own["z_end"], 12), m_own["v_end"])})
    knots = [[float(z), float(v)] for z, v in knots]
    ident: dict[str, Any] = {}

    def trajs(d, m, ws, ks, tag, u, source):
        out = []
        for n, k in enumerate(ks, 1):
            w = ws[k]
            idx = w["idx"]
            tid = f"{pid}-{tag}{n:02d}"
            ident[tid] = {"source_file": source, "pulse_start_s": w["pulse_start_s"], "samples": int(idx.size)}
            out.append(_traj(tid, u, "rest_pulse_rest", d["t"][idx] - d["t"][idx[0]], d["i"][idx], GITT_LEVEL_A,
                             d["v"][idx], d["T"][idx], float(m["z"][idx[0]]), m["q_total_As"]))
        return out

    sets = {"calibration": trajs(d_own, m_own, w_own, cal_k, "c", unit, own_name),
            "within": trajs(d_own, m_own, w_own, held_k, "w", unit, own_name),
            "cross": trajs(d_par, m_par, w_par, par_held_k, "x", partner_unit, par_name)}
    spec = {
        "schema": SPEC_SCHEMA, "problem_id": pid,
        "description": "Two sibling cells of one batch at room temperature. Each run: from rest, a 288 s discharge pulse at "
                       "a protocol-set 2.5 A, then rest (0.1 s sampling under load, 1 s at rest); successive pulses step the "
                       "charge state down by about 4 %. Calibration: the pulses at alternate charge-state set points of cell "
                       f"{unit}, including the highest and the lowest. Within-cell held-out: cell {unit}'s other pulses. "
                       f"Cross-cell held-out: cell {partner_unit}'s pulses at the same alternate set points. The OCV was "
                       "measured on cell " + unit + " from the relaxed voltage before each calibration pulse and after the "
                       "final rest, and is fixed.",
        "clock": "t_s", "observable": "voltage_V", "variables": _variables("the pulse current level the protocol set"),
        "declared_family": _measured_family(knots), "requested_parameters": ["R0", "R1", "C1"],
        "measurement_noise": dict(NOISE_UNKNOWN), "adequacy_bar": dict(PULSE_BAR),
        "acceptance": {"within_unit_heldout/pulses_alternate_soc": dict(PULSE_BAR),
                       "cross_unit_heldout/partner_cell_pulses": dict(PULSE_BAR)},
        "applicability": _applicability(SCOPE_BASIS, [knots[0][0], knots[-1][0]]),
        "conventions": {"current_sign": "positive is discharge", "hold": "backward", "rest_band_A": REST_BAND_A,
                        "initial_state": "soc per window, coulomb-counted from 1 at the end of the rest before the first "
                                         "pulse over the run's total discharged charge",
                        "initial_polarization": "0 V at the window start (at least 3060 s of rest before each window)",
                        "capacity_basis": "per cell: the charge discharged over the whole pulse sequence",
                        "scored_samples": "every sample after the first"},
        "questions": QUESTIONS,
        "sets": {"calibration": sets["calibration"], "within_unit_heldout": {"pulses_alternate_soc": sets["within"]},
                 "cross_unit_heldout": {"partner_cell_pulses": sets["cross"]}},
    }
    elig = {"kind": "gitt_measured_ocv", "own": {"pulses_admitted": m_own["pulses_admitted"],
            "pulses_excluded": m_own["pulses_excluded"], "final_rest_s": m_own["final_rest_s"]},
            "partner": {"pulses_admitted": m_par["pulses_admitted"], "pulses_excluded": m_par["pulses_excluded"]},
            "n": {k: len(v) for k, v in sets.items()}, "ocv_knots": len(knots)}
    prov = {"raw_sha256": {own_name: members[own_name]["sha256"], par_name: members[par_name]["sha256"]}}
    return spec, ident, prov, elig


# ---- Chen 2020 rate tests --------------------------------------------------------------------------------------------
def _read_chen(cell: str, sha: str) -> dict[str, np.ndarray]:
    path = DATA / "chen2020_lgm50" / f"{cell}.csv"
    raw = _check_pin(path, sha)
    rows = list(csv.reader(raw.decode("utf-8", errors="strict").splitlines()))
    h = next(n for n, r in enumerate(rows) if r and r[0] == "Rec")
    body = [r for r in rows[h + 1:] if r]
    col = {name: n for n, name in enumerate(rows[h])}
    # reader convention, fixed before any fit: a record whose mode is not R, C or D is a logger marker and is dropped;
    # of two consecutive kept records with the same timestamp the first is kept (as for the LG HG2 exports)
    body = [r for r in body if r[col["Md"]] in ("R", "C", "D")]
    kept, last = [], None
    for r in body:
        t_ = float(r[col["Test Time [s]"]])
        if last is None or t_ > last:
            kept.append(r)
            last = t_
    f = lambda key: np.array([float(r[col[key]]) for r in kept])  # noqa: E731
    return {"t": f("Test Time [s]"), "i": f("Current [A]"), "v": f("Voltage [V]"), "T": f("Temperature Cell [degC]"),
            "md": np.array([r[col["Md"]] for r in kept])}


def chen_runs(d: dict[str, np.ndarray]) -> tuple[dict[float, dict[str, Any]], list[dict[str, Any]]]:
    i, md = d["i"], d["md"]
    load = (np.abs(i) > REST_BAND_A)
    segs, s = [], 0
    for k in range(1, i.size + 1):
        if k == i.size or load[k] != load[s] or (load[k] and md[k] != md[s]):
            segs.append((s, k - 1, ("C" if md[s] == "C" else "D") if load[s] else "R"))
            s = k
    runs, excluded = {}, []
    for n, (s0, s1, kind) in enumerate(segs):
        if kind != "D":
            continue
        prev_charge = [g for g in segs[:n] if g[2] == "C"]
        rate = float(np.median(np.abs(i[s0:s1 + 1])))
        why = []
        if not prev_charge or abs(i[prev_charge[-1][1]]) > CHEN_TERMINATION_A + REST_BAND_A:
            why.append("not preceded by a CC-CV charge ending at C/100 + 10 mA")
        if n == 0 or segs[n - 1][2] != "R":
            why.append("does not start from rest")
        nxt = segs[n + 1] if n + 1 < len(segs) else None
        if nxt is None or nxt[2] != "R":
            why.append("not followed by rest")
        if why:
            excluded.append({"start_s": float(d["t"][s0]), "rate_A": rate, "why": why})
            continue
        lo, hi = s0 - 1, nxt[1]
        runs[round(rate * 2) / 2] = {"lo": lo, "hi": hi, "rate": rate}
    return runs, excluded


def _delivered_As(d: dict[str, np.ndarray], lo: int, hi: int) -> float:
    i = np.abs(d["i"][lo + 1:hi + 1])
    return float(np.sum(np.where(i > REST_BAND_A, i, 0.0) * np.diff(d["t"][lo:hi + 1])))


def build_chen(pid: str, cell: str, unit: str, partner_unit: str, shas: dict[str, str]) -> tuple[dict, dict, dict, dict]:
    par = CHEN_PARTNER[cell]
    data = {c: _read_chen(c, shas[c]) for c in (cell, par)}
    runs = {c: chen_runs(data[c]) for c in data}
    ident: dict[str, Any] = {}
    basis = {c: _delivered_As(data[c], runs[c][0][0.5]["lo"], runs[c][0][0.5]["hi"]) for c in data}

    def trajs(c, rates, tag, u):
        out = []
        for n, rate in enumerate(rates, 1):
            r = runs[c][0][rate]
            d = data[c]
            sl = slice(r["lo"], r["hi"] + 1)
            tid = f"{pid}-{tag}{n:02d}"
            ident[tid] = {"source_file": f"{c}.csv", "rate_A": rate, "start_s": float(d["t"][r["lo"]])}
            out.append(_traj(tid, u, "cc_discharge_then_rest", d["t"][sl] - d["t"][r["lo"]], np.abs(d["i"][sl]),
                             rate, d["v"][sl], d["T"][sl], 1.0, basis[c]))
        return out

    sets = {"calibration": trajs(cell, CHEN_CAL_RATES, "c", unit), "within": trajs(cell, CHEN_HELD_RATES, "w", unit),
            "cross": trajs(par, CHEN_HELD_RATES, "x", partner_unit)}
    knots = FITTED_OCV_KNOTS_SOC
    spec = {
        "schema": SPEC_SCHEMA, "problem_id": pid,
        "description": "Two sibling cells of one batch in a room-temperature chamber. Each run: from full charge (CC-CV, "
                       "then 2 h rest), a constant-current discharge at a protocol-set rate (0.5, 2.5, 5 or 7.5 A) to the "
                       "cutoff voltage, then rest; 30 s sampling; the cell self-heats at the higher rates. Calibration: cell "
                       f"{unit}'s 0.5 A and 7.5 A runs. Within-cell held-out: cell {unit}'s 2.5 A and 5 A runs. Cross-cell "
                       f"held-out: cell {partner_unit}'s 2.5 A and 5 A runs. The open-circuit voltage was not measured.",
        "clock": "t_s", "observable": "voltage_V", "variables": _variables("the discharge rate the protocol set", knots),
        "declared_family": _fitted_family(), "requested_parameters": ["R0", "R1", "C1"],
        "measurement_noise": dict(NOISE_UNKNOWN), "adequacy_bar": dict(ARCHIVE_BAR),
        "acceptance": {"within_unit_heldout/intermediate_rates": dict(ARCHIVE_BAR),
                       "cross_unit_heldout/partner_cell_intermediate_rates": dict(ARCHIVE_BAR)},
        "applicability": _applicability(SCOPE_BASIS, [0.0, 1.0]),
        "conventions": {"current_sign": "positive is discharge", "hold": "backward", "rest_band_A": REST_BAND_A,
                        "initial_state": "soc = 1 at sample 0 (full charge, then rest)",
                        "initial_polarization": "0 V at sample 0 (the run starts from a 2 h rest)",
                        "capacity_basis": "per cell: the charge delivered by that cell's 0.5 A capacity-check run",
                        "scored_samples": "every sample after the first"},
        "questions": QUESTIONS,
        "sets": {"calibration": sets["calibration"], "within_unit_heldout": {"intermediate_rates": sets["within"]},
                 "cross_unit_heldout": {"partner_cell_intermediate_rates": sets["cross"]}},
    }
    elig = {"kind": "rate_tests_fitted_ocv", "runs": {c: sorted(runs[c][0]) for c in runs},
            "excluded": {c: runs[c][1] for c in runs}, "n": {k: len(v) for k, v in sets.items()}}
    return spec, ident, {"raw_sha256": {f"{c}.csv": shas[c] for c in (cell, par)}}, elig


# ---- NASA 43 C / 4 C single-cell problems ------------------------------------------------------------------------------
def _nasa(cell: str) -> tuple[list[Any], list[Any], str]:
    import scipy.io as sio  # noqa: PLC0415

    rel = f"extracted/{NASA_CELLS[cell]}/{cell}.mat"
    inventory = json.loads((DATA / "nasa_pcoe_battery" / "inventory.json").read_bytes())
    pinned = {f["extracted_to"]: f["sha256"] for inner in inventory["inner"] for f in inner["files"]}
    _check_pin(DATA / "nasa_pcoe_battery" / rel, pinned[rel])
    m = sio.loadmat(DATA / "nasa_pcoe_battery" / rel, squeeze_me=True, struct_as_record=False)[cell]
    return list(m.cycle), [c for c in m.cycle if c.type == "discharge"], pinned[rel]


def build_nasa(pid: str, cell: str, unit: str) -> tuple[dict, dict, dict, dict]:
    cycles, dis, sha = _nasa(cell)
    level_nom = min((1.0, 2.0, 4.0), key=lambda x: abs(x - float(np.median(
        [np.median(v2bp._arrays(c)[1][v2bp._arrays(c)[1] > 0.3]) for c in dis if np.any(v2bp._arrays(c)[1] > 0.3)]))))
    admitted, excluded = [], []
    order = [k for k, c in enumerate(cycles) if c.type == "discharge"]
    for ordinal, k in enumerate(order):
        c = cycles[k]
        t, i, v, temp = v2bp._arrays(c)
        why = []
        prev = [p for p in cycles[:k] if p.type == "charge"]
        ci = np.asarray(prev[-1].data.Current_measured, float) if prev else np.array([])
        if not ci.size or not np.isfinite(ci[-1]) or abs(ci[-1]) > NASA_TERMINATION_A + REST_BAND_A:
            why.append("preceding charge does not end at <= 30 mA")
        loaded = i[i > 0.3]
        if not loaded.size or abs(float(np.median(loaded)) - level_nom) > 0.05 * level_nom:
            why.append("loaded median current is not the declared level")
        if not (np.all(np.isfinite(t)) and np.all(np.isfinite(v)) and np.all(np.isfinite(i)) and np.all(np.isfinite(temp))):
            why.append("non-finite sample")
        if t.size < 3 or abs(i[-1]) > REST_BAND_A:
            why.append("does not end in rest")
        if ordinal == 0:
            why.append("no earlier discharge for the causal capacity basis")
        (excluded if why else admitted).append({"ordinal": ordinal, "why": why} if why else ordinal)
    n = len(order)
    cal = [o for o in admitted if o >= 1][:NASA_N_CAL]
    held = [o for o in admitted if o >= max(n // 2, cal[-1] + 1)][:NASA_N_HELD]
    if len(cal) < NASA_N_CAL or len(held) < NASA_N_HELD:
        raise DesignRefused({"why": f"{len(cal)} calibration and {len(held)} held-out discharges admitted; the fixed design "
                                    f"needs {NASA_N_CAL} and {NASA_N_HELD}", "discharges": n, "admitted": admitted,
                             "excluded": excluded})
    ident: dict[str, Any] = {}

    def trajs(ords, tag):
        out = []
        for m_, o in enumerate(ords, 1):
            c = dis[o]
            t, i, v, temp = v2bp._arrays(c)
            basis_Ah = max(v2bp._delivered_Ah(e) for e in dis[:o])
            tid = f"{pid}-{tag}{m_:02d}"
            ident[tid] = {"source_file": f"{NASA_CELLS[cell]}/{cell}.mat", "cell": cell, "discharge_ordinal": o,
                          "capacity_basis_Ah": basis_Ah}
            out.append(_traj(tid, unit, "cc_discharge_then_rest", t, i, level_nom, v, temp, 1.0, basis_Ah * 3600.0))
        return out

    sets = {"calibration": trajs(cal, "c"), "within": trajs(held, "w")}
    amb = int(dis[cal[0]].ambient_temperature)
    spec = {
        "schema": SPEC_SCHEMA, "problem_id": pid,
        "description": f"One cell in a {amb} C chamber. Each run: constant-current discharge at a protocol-set level "
                       f"({level_nom:g} A) from full charge to the cell's cutoff voltage, then rest; about 10-15 s sampling. "
                       "Calibration: early runs. Within-cell held-out: runs from the second half of the cell's life. No "
                       "second cell is supplied. The open-circuit voltage was not measured.",
        "clock": "t_s", "observable": "voltage_V", "variables": _variables("the load level the protocol set for the run",
                                                                        FITTED_OCV_KNOTS_SOC),
        "declared_family": _fitted_family(), "requested_parameters": ["R0", "R1", "C1"],
        "measurement_noise": dict(NOISE_UNKNOWN), "adequacy_bar": dict(ARCHIVE_BAR),
        "acceptance": {"within_unit_heldout/later_cycles": dict(ARCHIVE_BAR)},
        "applicability": _applicability(SCOPE_BASIS, [0.0, 1.0]),
        "conventions": {"current_sign": "positive is discharge", "hold": "backward", "rest_band_A": REST_BAND_A,
                        "initial_state": "soc = 1 at sample 0 (full charge, then rest)",
                        "initial_polarization": "0 V at sample 0 (the run starts from rest)",
                        "capacity_basis": "per trajectory: the largest charge delivered by an earlier discharge of the "
                                          "same cell (causal)", "scored_samples": "every sample after the first"},
        "questions": QUESTIONS,
        "sets": {"calibration": sets["calibration"], "within_unit_heldout": {"later_cycles": sets["within"]}},
    }
    elig = {"kind": "aging_archive_fitted_ocv", "discharges": n, "admitted": len(admitted), "excluded": excluded,
            "calibration_ordinals": cal, "heldout_ordinals": held, "n": {k: len(v) for k, v in sets.items()}}
    return spec, ident, {"raw_sha256": {f"{NASA_CELLS[cell]}/{cell}.mat": sha}}, elig


# ---- the whole bundle ---------------------------------------------------------------------------------------------------
def design() -> list[dict[str, Any]]:
    """The fixed problem list, in pseudonym order (no data is read here)."""
    out, n, units = [], 0, {}

    def unit(key: str) -> str:
        if key not in units:
            units[key] = f"u{len(units) + 1:02d}"
        return units[key]

    for expt in (4, 5):
        for rpt in extract.RPTS[expt]:
            for cell in extract.CELLS:
                n += 1
                out.append({"pid": f"P{n:02d}", "kind": "gitt", "expt": expt, "cell": cell, "rpt": rpt,
                            "unit": unit(f"kirkaldy/{expt}/{cell}"), "partner_unit": unit(f"kirkaldy/{expt}/{PARTNER[cell]}")})
    for cell in CHEN_CELLS:
        n += 1
        out.append({"pid": f"P{n:02d}", "kind": "chen", "cell": cell, "unit": unit(f"chen/{cell}"),
                    "partner_unit": unit(f"chen/{CHEN_PARTNER[cell]}")})
    for cell in NASA_CELLS:
        n += 1
        out.append({"pid": f"P{n:02d}", "kind": "nasa", "cell": cell, "unit": unit(f"nasa/{cell}")})
    return out


def build_all() -> dict[str, tuple[dict, dict, dict, dict]]:
    members = json.loads((VAULT / "EXTRACT_MANIFEST.json").read_bytes())["members"]
    chen_manifest = json.loads((ROOT / "benchmarks" / "measurements" / "chen2020_lgm50" / "manifest.json").read_bytes())
    chen_sha = {c: chen_manifest["files"][f"{c}.csv"]["sha256"] for c in CHEN_CELLS}
    out, refused = {}, {}
    for p in design():
        try:
            if p["kind"] == "gitt":
                out[p["pid"]] = build_gitt(p["pid"], p["expt"], p["cell"], p["rpt"], p["unit"], p["partner_unit"], members)
            elif p["kind"] == "chen":
                out[p["pid"]] = build_chen(p["pid"], p["cell"], p["unit"], p["partner_unit"], chen_sha)
            else:
                out[p["pid"]] = build_nasa(p["pid"], p["cell"], p["unit"])
        except DesignRefused as exc:
            refused[p["pid"]] = {"design": p, **exc.args[0]}
    return out, refused


def bridge() -> dict[str, bytes]:
    v2_manifest = json.loads((V2_PACK / "MANIFEST.json").read_bytes())
    out = {}
    for pid in BRIDGE:
        raw = (V2_PACK / f"{pid}.json").read_bytes()
        if _sha(raw) != v2_manifest["problems"][pid]["sha256"]:
            raise SystemExit(f"v2 pack {pid} differs from its manifest")
        out[pid] = raw
    return out


def spec_bytes(spec: dict[str, Any]) -> bytes:
    return (json.dumps(spec, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()


def main() -> int:
    PACK.mkdir(exist_ok=True)
    manifest = {"schema": MANIFEST_SCHEMA, "problems": {}}
    identity, provenance, eligibility = {}, {}, {}
    plan = {p["pid"]: p for p in design()}
    built, refused = build_all()
    for pid, (spec, ident, prov, elig) in built.items():
        sha = write_json(PACK / f"{pid}.json", spec)
        manifest["problems"][pid] = {"file": f"{pid}.json", "sha256": sha}
        identity[pid] = {"design": plan[pid], "trajectories": ident}
        provenance[pid] = {**prov, "pack_sha256": sha}
        eligibility[pid] = elig
        print(pid, plan[pid]["kind"], elig["n"], f"{len(spec_bytes(spec)) / 1e6:.2f} MB", flush=True)
    for pid, raw in bridge().items():
        (PACK / f"{pid}.json").write_bytes(raw)
        manifest["problems"][pid] = {"file": f"{pid}.json", "sha256": _sha(raw)}
        provenance[pid] = {"bridge_of": f"benchmarks/battery_rediscovery_v2/candidate/pack/{pid}.json", "pack_sha256": _sha(raw)}
    write_json(PACK / "MANIFEST.json", manifest)
    write_json(VAULT / "IDENTITY_MAP.json", identity)
    write_json(VAULT / "PACK_PROVENANCE.json", provenance)
    write_json(VAULT / "ELIGIBILITY.json", {"schema": "forge.battery_rediscovery_v3.eligibility/1",
                                            "rules": __doc__, "problems": eligibility, "refused_problems": refused,
                                            "primary_problems": sorted(identity), "bridge_problems": list(BRIDGE)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
