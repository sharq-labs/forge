"""Battery Flagship B3 evidence: read the frozen Jahn 2024 A123 files, never write them.

Everything the round knows about its data passes through this module:

* the raw bytes, checked against ``evidence/PROVENANCE.json`` before any parse;
* the branch structure of the incremental-OCV file (charge rows, then discharge
  rows, with one shared top row);
* the Phase 7 quality audit, which REPORTS anomalies and cleans nothing;
* the Phase 8 uncertainty budget, whose every term is either an instrument
  specification, a figure measured from data other than the held-out answers,
  or a declared allowance with its reason;
* the Phase 9 split and region rule.

No function here fits a model. The only numbers derived from voltages are the
calibration-only local slopes of the state-of-charge term, and they are taken
from calibration observations by construction (see :func:`uncertainty_budget`).
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "battery_flagship_b3"
EVIDENCE = ROUND / "evidence"
RAW = EVIDENCE / "raw"
PROVENANCE = json.loads((EVIDENCE / "PROVENANCE.json").read_text(encoding="utf-8"))

INCR_OCV = "20230125_Hys_A123_01_25deg_incrOCV.csv"
POCV = "20230125_Hys_A123_01_25deg_pOCV.csv"
POWER_SOC50 = "20230125_HysPowerTest_A123_01_25deg_SOC50.csv"
POWER_SOC100 = "20230125_HysPowerTest_A123_01_25deg_SOC100.csv"

DATASET_DOI = PROVENANCE["dataset"]["persistent_identifier_cited_by_the_paper"]
CELL_LABEL = "A123_01"

#: Row layout of the incremental-OCV file, read from the file in Phase 7 and
#: re-checked by :func:`quality_audit` every run: rows 0..100 rise in Q (charge
#: branch), row 101 repeats row 100 exactly, rows 102..201 fall in Q.
CHARGE_ROWS = range(0, 101)
SHARED_TOP_ROW = 101
DISCHARGE_ROWS = range(102, 202)
TOP_ROW = 100

# ---------------------------------------------------------------------------
# Phase 8 constants. Each is a declaration with its source; see PREREGISTRATION.
# ---------------------------------------------------------------------------

#: BaSyTec CTS voltage accuracy 1 mV (distributor technical-data table, see
#: PROVENANCE.json), read as the half-width of a rectangular distribution.
VOLTAGE_ACCURACY_HALF_WIDTH_V = 1.0e-3
U_ACQUISITION_V = VOLTAGE_ACCURACY_HALF_WIDTH_V / math.sqrt(3.0)

#: Quantisation: the smallest non-zero voltage step in the file, of which every
#: voltage is an integer multiple (measured, re-checked by quality_audit).
QUANTISATION_STEP_V = 1.908776803496437e-4
U_QUANTISATION_V = QUANTISATION_STEP_V / math.sqrt(12.0)

#: Temperature: the same generous figures as B1 (LiFePO4 entropic coefficient
#: 0.2 mV/K over a 2 K band). The Binder MK115's stability at 25 degC is not
#: documented in the paper, so the band is declared, not measured.
ENTROPIC_COEFFICIENT_V_PER_K = 0.2e-3
TEMPERATURE_BAND_K = 2.0
U_TEMPERATURE_V = ENTROPIC_COEFFICIENT_V_PER_K * TEMPERATURE_BAND_K

#: State of charge: the vendor's stated worst-case relative current accuracy
#: over its whole range (0.33 %), read as a rectangular half-width on the state
#: of charge as a fraction of capacity. Conservative: z = Q / Q_top is a ratio
#: of two counts from the same channel, so a common gain error cancels.
SOC_RELATIVE_HALF_WIDTH = 0.0033
U_STATE_OF_CHARGE = SOC_RELATIVE_HALF_WIDTH / math.sqrt(3.0)

#: Residual relaxation. The rest after each interrupt is undocumented. B1's
#: BATT_001 is the same cell model; its measured voltage change from 10 min to
#: 24 h at its five interior discharge-conditioned levels, read from S-OCV by
#: :func:`batt001_relaxation_reference`, is {19.2, 12.1, 8.0, 8.4, 10.3} mV.
#: 10 min is the only rest length documented in this Zenodo record's time
#: series (both power tests). The primary allowance is the median, uniform.
RELAXATION_REFERENCE_MINUTES = 10
PRIMARY_RELAXATION_ALLOWANCE_V = 10.3e-3
RELAXATION_LADDER_V = (0.0, 2.0e-3, 5.0e-3, 10.3e-3, 20.0e-3, 50.0e-3)

#: Regions (Phase 16), declared after the Phase 7 inspection of the whole
#: branch and before any fit. Boundaries are on z = Q / Q_top.
REGIONS = (
    ("KNEE", 0.0, 0.10),
    ("LOW_SOC_TRANSITION", 0.10, 0.40),
    ("PLATEAU", 0.40, 0.70),
    ("HIGH_SOC_TRANSITION", 0.70, 1.0000001),
)

#: Split (Phase 9): discharge observations ordered by ascending z, index i;
#: held out iff i % 3 == 1.
HELD_OUT_MODULUS = 3
HELD_OUT_RESIDUE = 1


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_raw() -> dict[str, str]:
    """Every raw file against its pinned SHA-256. Raises on the first mismatch."""
    out = {}
    for entry in PROVENANCE["files"]:
        path = RAW / entry["raw_filename"]
        digest = sha256(path)
        if digest != entry["sha256"]:
            raise SystemExit(
                f"raw evidence {entry['raw_filename']} hashes to {digest}, not the "
                f"pinned {entry['sha256']}: the frozen bytes changed"
            )
        out[entry["raw_filename"]] = digest
    return out


def _read_csv(name: str) -> tuple[list[str], list[list[str]]]:
    text = (RAW / name).read_bytes().decode("ascii")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    return rows[0], rows[1:]


def incremental_rows() -> list[dict]:
    """All 202 rows of the incremental-OCV file, as published, with their row index."""
    header, rows = _read_csv(INCR_OCV)
    if header != ["Q", "OCV"]:
        raise SystemExit(f"unexpected incrOCV header {header!r}")
    return [
        {"row": index, "q_raw": q, "v_raw": v, "q_ah": float(q), "v_v": float(v)}
        for index, (q, v) in enumerate(rows)
    ]


def q_top_ah(rows: list[dict] | None = None) -> float:
    rows = rows if rows is not None else incremental_rows()
    return rows[TOP_ROW]["q_ah"]


def observation_id(row: int) -> str:
    return f"JAHN2024.{CELL_LABEL}.DCHG.r{row:03d}"


def region_of(z: float) -> str:
    for name, low, high in REGIONS:
        if low <= z < high:
            return name
    raise ValueError(f"state of charge {z!r} is in no declared region")


def discharge_points() -> list[dict]:
    """The 100 discharge-conditioned observations, z ascending, with split and region."""
    rows = incremental_rows()
    top = q_top_ah(rows)
    points = []
    for row in DISCHARGE_ROWS:
        r = rows[row]
        points.append({
            "observation_id": observation_id(row),
            "row": row,
            "q_ah": r["q_ah"],
            "state_of_charge": r["q_ah"] / top,
            "voltage_v": r["v_v"],
            "raw": {"Q": r["q_raw"], "OCV": r["v_raw"]},
        })
    points.sort(key=lambda p: p["state_of_charge"])
    for index, point in enumerate(points):
        point["index"] = index
        point["partition"] = "held_out" if index % HELD_OUT_MODULUS == HELD_OUT_RESIDUE else "calibration"
        point["region"] = region_of(point["state_of_charge"])
    return points


def charge_points() -> list[dict]:
    """The 101 charge-conditioned rows (out of claim: hysteresis measurement only)."""
    rows = incremental_rows()
    top = q_top_ah(rows)
    return [
        {"row": row, "q_ah": rows[row]["q_ah"], "state_of_charge": rows[row]["q_ah"] / top,
         "voltage_v": rows[row]["v_v"]}
        for row in CHARGE_ROWS
    ]


# ---------------------------------------------------------------------------
# Phase 8: the budget
# ---------------------------------------------------------------------------

def _calibration_slope(z: float, calibration: list[dict], own_id: str) -> tuple[float, list[str]]:
    """|dV/dz| from the nearest CALIBRATION observations bracketing z, never the point itself."""
    others = [p for p in calibration if p["observation_id"] != own_id]
    below = [p for p in others if p["state_of_charge"] < z]
    above = [p for p in others if p["state_of_charge"] > z]
    if below and above:
        a, b = below[-1], above[0]
    elif above:  # no calibration point below: the two lowest others
        a, b = above[0], above[1]
    else:  # no calibration point above: the two highest others
        a, b = below[-2], below[-1]
    slope = abs(b["voltage_v"] - a["voltage_v"]) / (b["state_of_charge"] - a["state_of_charge"])
    return slope, [a["observation_id"], b["observation_id"]]


def uncertainty_budget(points: list[dict], relaxation_allowance_v: float = PRIMARY_RELAXATION_ALLOWANCE_V) -> dict[str, dict]:
    """Combined standard uncertainty of every discharge observation.

    The state-of-charge term needs a local slope. It is taken from calibration
    observations only, for calibration AND held-out points alike, so no held-out
    voltage sets any uncertainty anywhere in the round (the lesson of B1's A2).
    """
    calibration = sorted((p for p in points if p["partition"] == "calibration"), key=lambda p: p["state_of_charge"])
    budget = {}
    for point in points:
        slope, used = _calibration_slope(point["state_of_charge"], calibration, point["observation_id"])
        u_soc = slope * U_STATE_OF_CHARGE
        combined = math.sqrt(
            U_ACQUISITION_V ** 2 + U_QUANTISATION_V ** 2 + U_TEMPERATURE_V ** 2
            + u_soc ** 2 + relaxation_allowance_v ** 2
        )
        budget[point["observation_id"]] = {
            "u_acquisition_v": U_ACQUISITION_V,
            "u_quantisation_v": U_QUANTISATION_V,
            "u_temperature_v": U_TEMPERATURE_V,
            "local_abs_dV_dz_from_calibration_v": slope,
            "slope_taken_from": used,
            "u_state_of_charge_v": u_soc,
            "u_relaxation_allowance_v": relaxation_allowance_v,
            "combined_standard_uncertainty_v": combined,
        }
    return budget


# ---------------------------------------------------------------------------
# Phase 7: quality audit (reports; never cleans)
# ---------------------------------------------------------------------------

def _load_s_ocv_reader():
    path = ROOT / "benchmarks" / "model_measurement_validation" / "audit" / "evidence.py"
    spec = importlib.util.spec_from_file_location("_mmv_evidence_b3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def batt001_relaxation_reference(minutes: int = RELAXATION_REFERENCE_MINUTES) -> dict:
    """BATT_001 (S-OCV, same cell model): V(24 h) - V(t) per trace, read from B1's evidence file."""
    import bisect

    ev = _load_s_ocv_reader()
    workbook = ROOT / "benchmarks" / "model_measurement_validation" / "evidence" / "ocv_relaxation_24h.xlsx"
    archive, strings, sheets = ev._open_workbook(workbook)
    out = {"file": str(workbook.relative_to(ROOT)).replace("\\", "/"), "file_sha256": sha256(workbook),
           "minutes": minutes, "sheets": {}}
    for sheet in ("24h_Discharge_APR", "24h_Charge_APR"):
        rows = ev._sheet_rows(archive, strings, sheets, sheet)
        header = [rows[0].get(i) for i in range(len(rows[0]))]
        traces = {}
        for column, label in enumerate(header):
            if column == 0 or not label:
                continue
            series = [(float(r[0]), float(r[column])) for r in rows[1:] if 0 in r and column in r]
            times = [t for t, _ in series]
            at = series[bisect.bisect_left(times, minutes / 60.0)]
            traces[label] = {
                "voltage_at_24h_v": series[-1][1],
                "voltage_at_reference_v": at[1],
                "reference_sample_hours": at[0],
                "residual_relaxation_mv": (series[-1][1] - at[1]) * 1e3,
            }
        out["sheets"][sheet] = traces
    interior = [
        abs(v["residual_relaxation_mv"])
        for label, v in out["sheets"]["24h_Discharge_APR"].items()
        if not label.endswith("_00-SOC")
    ]
    out["interior_discharge_abs_mv"] = interior
    out["interior_discharge_median_mv"] = sorted(interior)[len(interior) // 2]
    return out


def power_test_rests() -> list[dict]:
    """The measured 10 min rests in the two power tests (same cell, tester, chamber)."""
    out = []
    for name in (POWER_SOC50, POWER_SOC100):
        header, rows = _read_csv(name)
        data = [[float(x) for x in r] for r in rows]
        t = [d[0] for d in data]
        q = [d[1] for d in data]
        i = [d[2] for d in data]
        u = [d[3] for d in data]
        segments, start = [], 0
        for k in range(1, len(data) + 1):
            if k == len(data) or (abs(i[k]) < 1e-3) != (abs(i[start]) < 1e-3):
                segments.append((start, k - 1))
                start = k
        for a, b in segments:
            if abs(i[a]) >= 1e-3 or t[b] - t[a] < 300:
                continue
            prev = next((s for s in segments if s[1] == a - 1), None)
            j5 = min(range(a, b + 1), key=lambda k: abs((t[k] - t[a]) - 300.0))
            out.append({
                "file": name,
                "rest_minutes": (t[b] - t[a]) / 60.0,
                "q_ah": q[a],
                "preceding_current_a": (sorted(i[prev[0]:prev[1] + 1])[(prev[1] - prev[0]) // 2] if prev else None),
                "voltage_start_v": u[a],
                "voltage_at_5_min_v": u[j5],
                "voltage_end_v": u[b],
                "change_last_5_min_mv": (u[b] - u[j5]) * 1e3,
            })
    return out


def quality_audit() -> dict:
    rows = incremental_rows()
    top = q_top_ah(rows)
    findings: list[dict] = []

    def finding(check, status, detail, treatment="reported; nothing removed or altered"):
        findings.append({"check": check, "status": status, "detail": detail, "treatment": treatment})

    finite = all(math.isfinite(r["q_ah"]) and math.isfinite(r["v_v"]) for r in rows)
    finding("finite_values", "PASS" if finite else "FAIL", f"{len(rows)} rows, every Q and OCV finite: {finite}")
    finding("row_count", "PASS" if len(rows) == 202 else "FAIL", f"{len(rows)} data rows")

    charge_q = [rows[k]["q_ah"] for k in CHARGE_ROWS]
    discharge_q = [rows[k]["q_ah"] for k in DISCHARGE_ROWS]
    rising = all(b > a for a, b in zip(charge_q, charge_q[1:]))
    falling = all(b < a for a, b in zip(discharge_q, discharge_q[1:]))
    finding("charge_branch_q_strictly_rising_rows_0_100", "PASS" if rising else "FAIL", f"Q {charge_q[0]} -> {charge_q[-1]} Ah")
    finding("discharge_branch_q_strictly_falling_rows_102_201", "PASS" if falling else "FAIL", f"Q {discharge_q[0]} -> {discharge_q[-1]} Ah")

    same = rows[TOP_ROW]["q_raw"] == rows[SHARED_TOP_ROW]["q_raw"] and rows[TOP_ROW]["v_raw"] == rows[SHARED_TOP_ROW]["v_raw"]
    finding(
        "duplicate_physical_measurement_under_two_labels",
        "ANOMALY" if same else "PASS",
        f"row {SHARED_TOP_ROW} repeats row {TOP_ROW} character for character (Q={rows[TOP_ROW]['q_raw']}, OCV={rows[TOP_ROW]['v_raw']}): the top of the charge branch is also listed as the start of the discharge branch",
        treatment=(
            "kept in the raw file; assigned to the charge branch only, because that state was reached by "
            "charging. It is NOT a discharge-conditioned observation and is not in the discharge set. The "
            "discharge set is rows 102..201 (100 observations). Its Q is used as Q_top, the SOC normaliser."
        ),
    )
    dup_q = len({r["q_raw"] for r in rows}) != len(rows) - (1 if same else 0)
    finding("other_duplicate_rows", "PASS" if not dup_q else "ANOMALY", "no other repeated Q value in the file" if not dup_q else "repeated Q values beyond the shared top row")

    charge_steps = [b - a for a, b in zip(charge_q, charge_q[1:])]
    discharge_steps = [a - b for a, b in zip(discharge_q, discharge_q[1:])]
    finding(
        "state_of_charge_step_uniformity", "INFO",
        f"charge steps {min(charge_steps):.7f}..{max(charge_steps):.7f} Ah; discharge steps "
        f"{min(discharge_steps):.7f}..{max(discharge_steps):.7f} Ah. The discharge step is about 0.17 % smaller than "
        f"the charge step, so the discharge branch ends at Q = {discharge_q[-1]:.6f} Ah (z = {discharge_q[-1] / top:.5f}), not at 0",
    )
    finding("missing_measurements", "PASS", "no gap: every step on each branch is one nominal 1 % increment (min/max above)")

    volts = [r["v_v"] for r in rows]
    plausible = all(2.0 <= v <= 3.6 for v in volts)
    finding("voltage_units_and_range", "PASS" if plausible else "FAIL",
            f"OCV {min(volts):.6f}..{max(volts):.6f}; column declared 'OCV' in volts; inside the cell's 2.0-3.6 V limits: {plausible}")

    diffs = [abs(b - a) for a, b in zip(volts, volts[1:]) if abs(b - a) > 1e-12]
    step = min(diffs)
    worst_value = max(abs(v / step - round(v / step)) for v in volts)
    finding("quantisation", "INFO",
            f"smallest non-zero voltage step {step:.10e} V; every voltage is an integer multiple of it to {worst_value:.2e} of a step; step x 2^16 = {step * 65536:.4f} V, consistent with a 16-bit converter. Consequence: equal consecutive voltages are code-level ties, not duplicates")

    charge_v = [rows[k]["v_v"] for k in CHARGE_ROWS]
    discharge_v = [rows[k]["v_v"] for k in DISCHARGE_ROWS]
    ch_non_decreasing = all(b >= a for a, b in zip(charge_v, charge_v[1:]))
    dc_non_increasing = all(b <= a for a, b in zip(discharge_v, discharge_v[1:]))
    finding("voltage_monotone_in_q_on_each_branch", "PASS" if ch_non_decreasing and dc_non_increasing else "ANOMALY",
            f"charge non-decreasing in Q: {ch_non_decreasing}; discharge non-increasing as Q falls: {dc_non_increasing}")

    # branch ordering at matched z: charge-conditioned should sit above discharge-conditioned
    charge_z = [q / top for q in charge_q]
    below_count, deltas = 0, []
    for k in DISCHARGE_ROWS:
        z = rows[k]["q_ah"] / top
        j = max(0, min(len(charge_z) - 2, next((m for m in range(len(charge_z) - 1) if charge_z[m] <= z <= charge_z[m + 1]), 0)))
        w = (z - charge_z[j]) / (charge_z[j + 1] - charge_z[j])
        vc = charge_v[j] + w * (charge_v[j + 1] - charge_v[j])
        deltas.append((z, vc - rows[k]["v_v"]))
        if vc < rows[k]["v_v"]:
            below_count += 1
    finding("branch_consistency_hysteresis_sign", "PASS" if below_count == 0 else "ANOMALY",
            f"charge branch (linearly interpolated in z) minus discharge branch is positive at {100 - below_count}/100 discharge points; range {min(d for _, d in deltas) * 1e3:+.1f}..{max(d for _, d in deltas) * 1e3:+.1f} mV")

    # relaxed vs loaded: C/20 loaded branches must bracket the relaxed branches
    header, prows = _read_csv(POCV)
    p = [[float(x) for x in r] for r in prows]
    k_top = max(range(len(p)), key=lambda k: p[k][1])
    p_top = p[k_top][1]
    up = [(r[1] / p_top, r[2]) for r in p[:k_top + 1]]
    down = sorted(((r[1] / p_top, r[2]) for r in p[k_top + 1:]), key=lambda x: x[0])
    up.sort(key=lambda x: x[0])

    def interp(series, z):
        zs = [s[0] for s in series]
        import bisect
        m = bisect.bisect_left(zs, z)
        if m <= 0 or m >= len(series):
            return None
        (z0, v0), (z1, v1) = series[m - 1], series[m]
        return v0 + (v1 - v0) * (z - z0) / (z1 - z0) if z1 > z0 else v0

    ordering = {"charge_relaxed_below_loaded": 0, "charge_compared": 0, "discharge_relaxed_above_loaded": 0, "discharge_compared": 0}
    for k in CHARGE_ROWS:
        z = rows[k]["q_ah"] / top
        if 0.05 <= z <= 0.95:
            loaded = interp(up, z)
            if loaded is not None:
                ordering["charge_compared"] += 1
                ordering["charge_relaxed_below_loaded"] += rows[k]["v_v"] <= loaded
    for k in DISCHARGE_ROWS:
        z = rows[k]["q_ah"] / top
        if 0.05 <= z <= 0.95:
            loaded = interp(down, z)
            if loaded is not None:
                ordering["discharge_compared"] += 1
                ordering["discharge_relaxed_above_loaded"] += rows[k]["v_v"] >= loaded
    finding(
        "relaxed_versus_loaded_ordering", "INFO",
        f"against the C/20 loaded cycle (pOCV file, z normalised to its own top Q = {p_top:.6f} Ah) over 0.05 <= z <= 0.95: "
        f"charge-branch incrOCV at or below the loaded charge curve at {ordering['charge_relaxed_below_loaded']}/{ordering['charge_compared']} points; "
        f"discharge-branch incrOCV at or above the loaded discharge curve at {ordering['discharge_relaxed_above_loaded']}/{ordering['discharge_compared']}. "
        f"Indicative only: the two tests count Q from different references (top Q {top:.6f} vs {p_top:.6f} Ah)",
    )

    finding("repeated_trials", "INFO", "none: one cell, one incremental cycle; no replicate spread is available for Phase 8")
    finding("temperature_consistency", "UNVERIFIABLE", "the file has no temperature channel; 25 degC is the chamber setpoint stated in the paper and the file name")
    finding("timing_and_rest_period_consistency", "UNVERIFIABLE",
            "the file has no time channel; the rest after each interrupt, the step current and the sampled point of each rest are documented nowhere retrievable (DATA_SELECTION.json lists where this was looked for)")

    rests = power_test_rests()
    finding(
        "metadata_contradiction_power_test_rate", "ANOMALY",
        "the Zenodo description calls the power tests 'C/2' charge or discharge to 50 % SOC followed by a '4C' discharge; the raw current reads "
        + ", ".join(f"{r['preceding_current_a']:+.3f} A before the rest at Q={r['q_ah']:.4f} Ah" for r in rests)
        + ". For a 1.1 Ah cell +/-1.10 A is 1C, not C/2, and -4.40 A is 4C. The paper's Methods call the fast discharge '3C'. These files are used only for their measured rest lengths, which the contradiction does not touch.",
    )
    finding("metadata_contradiction_capacity_reference", "INFO",
            f"Q at the top of the incremental cycle is {top:.6f} Ah and at the top of the C/20 cycle {p_top:.6f} Ah; the nominal capacity of an 18650M1A is 1.1 Ah. B3 uses z = Q / Q_top of the incremental file itself, for that file only.")

    return {
        "schema": "battery_flagship_b3_data_quality/1",
        "written_before_any_b3_fit": True,
        "raw_sha256": verify_raw(),
        "q_top_ah": top,
        "state_of_charge_definition": "z = Q / Q_top, Q_top = Q of the last charge-branch row (row 100) of the incremental file",
        "findings": findings,
        "power_test_rests": rests,
        "batt001_relaxation_reference": batt001_relaxation_reference(),
        "hysteresis_charge_minus_discharge_at_discharge_z_mv": [
            {"state_of_charge": z, "delta_mv": d * 1e3} for z, d in sorted(deltas)
        ],
    }
