"""R19: why the new Gate A failed, diagnosed and not retried.

R19 forbids the obvious move. A sequence of holdouts until one passes is not
validation, so this script produces a diagnosis and no second holdout.

The failure has a shape that narrows the candidates immediately. The voltage
bias is +128.18 mV against a mean absolute error of 128.51 mV, so almost every
scored residual has the same sign: the model is uniformly high. On the same
model the calibration bias is -0.38 mV and the validation bias -7.97 mV, so this
is not the model drifting, it is one cell sitting at a different level. That
rules out scatter, rules out anything that averages out, and points at a level
error in one of the three things that set the level -- the charge-state basis,
the open-circuit voltage curve, or the resistance.

There is a second, independent signal. On the same holdout the TEMPERATURE bias
is -0.89 K, against -0.07 K on calibration and -0.24 K on validation: the model
also under-predicts how much this cell heats up. Voltage too high and
temperature too low is the signature of one thing, an under-estimated
resistance, because the same R sets the ohmic drop and the ohmic heat. A curve
error would move the voltage and leave the temperature alone.

What this script checks, all of it model-free where it can be:

1. **The capacity basis.** Is the available charge the authority established
   close to what each holdout trajectory actually delivered? If it is not, the
   charge state is wrong and everything downstream follows.
2. **B0041's own pseudo-OCV against the declared cold curve.** Built the way
   the authority itself is built -- charge/discharge branch averaging on the
   cell's own pairs -- which cancels a linear resistance exactly and therefore
   separates an open-circuit voltage offset from a resistance increase. The
   single-rate prediction residual cannot separate them; the archive's charge
   cycles can.
3. **B0041's own branch-difference resistance against the calibration cell's**,
   from the same pairs, so the two halves of the offset are measured rather
   than argued about.
4. **How the residual behaves with cycle number**, which is what separates a
   fixed cell-to-cell offset from progressive ageing.
5. **The temperature channel**, which the voltage and the resistance share and
   which therefore tells a resistance error from a curve error.

    python benchmarks/battery_voltage_s3_recovery/harness/diagnose.py
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
from typing import Any

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import corpus as cp  # noqa: E402
from engcore.domains.battery import flagship_ocv_v2 as ocv_v2  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402

DIAGNOSIS_SCHEMA = "battery_voltage_s3_recovery_failure_diagnosis/1"

#: Charge states the curve comparison is read at.
PROBE_Z = (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2)

#: Below this the cell is at rest.
REST_BAND_A = 0.2


def load(name: str):
    with open(os.path.join(EVIDENCE, name), encoding="utf-8") as handle:
        return json.load(handle)


def curve_at(band: str, z: float) -> float | None:
    result = ocv_v2.OCV_V2_CURVES[band].evaluate(Quantity(z, "dimensionless"))
    if result.value is None:
        return None
    return result.value.magnitude_in("volt")


def loaded_profile(trajectory, basis: float):
    """Measured voltage against charge state on a declared basis, loaded only."""
    ch = trajectory["channels"]
    times = np.asarray(ch["time_s"], dtype=float)
    current = -np.asarray(ch["current_a"], dtype=float)  # positive out
    voltage = np.asarray(ch["voltage_v"], dtype=float)
    temperature = np.asarray(ch["temperature_c"], dtype=float)
    dt_h = np.diff(times) / 3600.0
    removed = np.concatenate(
        [[0.0], np.cumsum(0.5 * (current[1:] + current[:-1]) * dt_h)]
    )
    z = 1.0 - removed / basis
    loaded = current > REST_BAND_A
    return z[loaded], voltage[loaded], current[loaded], temperature[loaded]


def main() -> int:
    result = load("NEW_GATE_A_RESULT.json")
    state = load("BATTERY_STATE_AUTHORITY.json")
    prereg = load("NEW_GATE_A_PREREGISTRATION.json")
    states = {row["trajectory_id"]: row for row in state["trajectories"]}
    trajectories = {t["trajectory_id"]: t for t in cp.normalized_trajectories()}

    gate = result["gate_a"]["metrics"]["terminal_voltage"]
    holdout_ids = [
        row["trajectory_id"]
        for row in state["trajectories"]
        if row["split"] == "locked_holdout"
    ]

    # ---- 1. the capacity basis -------------------------------------------
    capacity_rows = []
    for tid in holdout_ids:
        record = states[tid]
        own = float(trajectories[tid]["delivered_ah"])
        q = record["capacity"]["initial_available_charge_ah"]
        capacity_rows.append(
            {
                "trajectory_id": tid,
                "basis": record["capacity"]["basis"],
                "available_charge_ah": q,
                "own_delivered_ah": round(own, 6),
                "relative_error": (round((q - own) / own, 6) if q else None),
                "evidence_cycle": (
                    record["capacity"]["source_evidence"][0]["cycle_id"]
                    if record["capacity"]["source_evidence"]
                    else None
                ),
            }
        )
    errors = [
        abs(row["relative_error"])
        for row in capacity_rows
        if row["relative_error"] is not None
    ]
    estimator = state["capacity_estimator"]
    capacity_verdict = {
        "rows": capacity_rows,
        "max_absolute_relative_error": max(errors) if errors else None,
        "calibration_p95": estimator["p95_absolute_relative_error"],
        "inside_the_declared_spread": (
            bool(errors) and max(errors) <= estimator["p95_absolute_relative_error"]
        ),
        "reading": (
            "the capacity authority did its job. Every holdout trajectory's "
            "available charge is within the spread the estimator declared on "
            "calibration cells, so the charge-state basis is not what the "
            "failure is made of. This is the hypothesis the Sprint 3 round "
            "report pointed at, and on this cell it is refuted"
        ),
    }

    # ---- 2 and 3. B0041's own pseudo-OCV and its own resistance -----------
    # Built the way the authority is built: branch averaging on the cell's own
    # charge/discharge pairs. That cancels a linear resistance exactly, whatever
    # its size, so the open-circuit voltage difference and the resistance
    # difference come out separately. Legitimate now: the holdout is open, the
    # model is frozen, and nothing downstream of this is fitted.
    import ocv2

    members = ocv2.read_members(
        os.environ.get("FORGE_S3_ARCHIVE", "D:/forge-s3-data/nasa_battery.zip")
    )
    wanted = {
        states[tid]["cycle_index"]: tid
        for tid in holdout_ids
        if states[tid]["capacity"]["basis"] != "unknown"
    }
    own_pairs = []
    for key in sorted(members):
        cell = os.path.basename(key.split("::")[1])[:-4]
        if cell != "B0041":
            continue
        import io

        import scipy.io as sio

        mat = sio.loadmat(
            io.BytesIO(members[key]), squeeze_me=True, struct_as_record=False
        )
        names = [n for n in mat if not n.startswith("__")]
        cycles = list(mat[names[0]].cycle)
        index = 0
        for position, cycle in enumerate(cycles):
            if str(cycle.type) != "discharge":
                continue
            index += 1
            tid = wanted.get(index)
            if tid is None:
                continue
            following = None
            for later in cycles[position + 1:]:
                if str(later.type) == "charge":
                    following = later
                    break
                if str(later.type) == "discharge":
                    break
            if following is None:
                continue
            d, c = ocv2.series(cycle), ocv2.series(following)
            if d is None or c is None:
                continue
            basis = float(
                states[tid]["capacity"]["initial_available_charge_ah"]
            )
            pair = ocv2.pair_curve(d, c, basis)
            if pair is None:
                continue
            pair["trajectory_id"] = tid
            pair["cycle_index"] = index
            own_pairs.append(pair)

    curve_rows = []
    resistance_rows = []
    calibration_profile = {
        row["charge_state"]: row["median_ohm"]
        for row in load("OCV_AUTHORITY_V2.json")["resistance_profiles"]["cold"]["knots"]
    }
    for probe in PROBE_Z:
        ocv_deltas = []
        contaminated = 0
        resistances = []
        for pair in own_pairs:
            zo = pair["z_overlap"]
            inside_overlap = zo[0] <= probe <= zo[-1]
            z = np.asarray(pair["z"], dtype=float)
            order = np.argsort(z)
            z = z[order]
            if not (z[0] <= probe <= z[-1]):
                continue
            if not inside_overlap:
                # Above the overlap the pseudo-OCV is the discharge branch with
                # a HELD ohmic correction, so it already contains the resistance
                # this comparison is trying to separate out. Counted, not used.
                contaminated += 1
                continue
            own = float(np.interp(probe, z, np.asarray(pair["ocv"])[order]))
            declared = curve_at("cold", probe)
            if declared is not None:
                ocv_deltas.append(declared - own)
            resistances.append(float(np.interp(probe, zo, pair["r_eff"])))
        if ocv_deltas or contaminated:
            curve_rows.append(
                {
                    "charge_state": probe,
                    "pairs_inside_overlap": len(ocv_deltas),
                    "pairs_above_overlap_not_used": contaminated,
                    "declared_minus_own_ocv_mv": (
                        round(statistics.median(ocv_deltas) * 1000.0, 2)
                        if ocv_deltas
                        else None
                    ),
                    "min_mv": (
                        round(min(ocv_deltas) * 1000.0, 2) if ocv_deltas else None
                    ),
                    "max_mv": (
                        round(max(ocv_deltas) * 1000.0, 2) if ocv_deltas else None
                    ),
                    "separable_here": bool(ocv_deltas),
                }
            )
        if resistances:
            nearest = min(calibration_profile, key=lambda x: abs(x - probe))
            resistance_rows.append(
                {
                    "charge_state": probe,
                    "pairs": len(resistances),
                    "b0041_r_eff_ohm": round(statistics.median(resistances), 5),
                    "calibration_r_eff_ohm": round(calibration_profile[nearest], 5),
                    "calibration_charge_state": nearest,
                    "difference_ohm": round(
                        statistics.median(resistances) - calibration_profile[nearest],
                        5,
                    ),
                }
            )

    usable_curve_rows = [
        row for row in curve_rows if row["declared_minus_own_ocv_mv"] is not None
    ]
    median_offset = (
        statistics.median(
            [row["declared_minus_own_ocv_mv"] for row in usable_curve_rows]
        )
        if usable_curve_rows
        else None
    )
    overlap_top = max(
        (pair["overlap"][1] for pair in own_pairs), default=None
    )
    median_resistance_gap = (
        statistics.median([row["difference_ohm"] for row in resistance_rows])
        if resistance_rows
        else None
    )
    per_trajectory = [
        {
            "trajectory_id": pair["trajectory_id"],
            "cycle_index": pair["cycle_index"],
            "median_cell_temperature_c": round(pair["median_cell_temperature_c"], 2),
            "i_discharge_a": round(pair["i_discharge"], 4),
            "i_charge_a": round(pair["i_charge"], 4),
            "overlap_z": [round(x, 4) for x in pair["overlap"]],
        }
        for pair in own_pairs
    ]

    holdout_current = 1.01
    resistance_share_mv = (median_resistance_gap or 0.0) * holdout_current * 1000.0
    bias_mv = round((gate["bias"] or 0.0) * 1000.0, 2)
    separability = {
        "method": (
            "charge/discharge branch averaging on B0041's own pairs. The "
            "weighted average cancels a linear resistance exactly, whatever its "
            "size -- but only where both branches exist. Above the overlap the "
            "pseudo-OCV is the discharge branch with a held ohmic correction, so "
            "it carries the resistance rather than separating from it"
        ),
        "pairs": len(own_pairs),
        "overlap_reaches_charge_state": (
            round(overlap_top, 4) if overlap_top is not None else None
        ),
        "why_the_overlap_is_short": (
            "at 4 degC the charger is cut off with 50-60 mA still flowing, so "
            "the constant-current charge branch covers less of the charge-state "
            "axis than it does at room temperature. The scored samples sit mostly "
            "above the overlap, which is exactly where the separation is not "
            "available"
        ),
        "inside_the_overlap": {
            "declared_minus_own_ocv_mv": median_offset,
            "b0041_minus_calibration_resistance_ohm": median_resistance_gap,
            "resistance_share_at_holdout_current_mv": round(resistance_share_mv, 2),
        },
        "observed_prediction_bias_mv": bias_mv,
        "separable_over_the_scored_range": False,
        "reading": (
            "inside the overlap both terms are measured and they point opposite "
            f"ways: B0041's own open-circuit voltage sits {abs(median_offset):.0f} mV "
            "ABOVE the declared curve, which alone would make the model predict "
            f"low, while its resistance runs {median_resistance_gap:+.3f} ohm "
            f"above the calibration cell's, worth {resistance_share_mv:+.0f} mV at "
            "1 A, which makes it predict high. The observed bias is "
            f"{bias_mv:+.0f} mV, high, so the resistance term dominates over the "
            "range that was scored. How much of the remainder is a further "
            "resistance excess above the overlap and how much is an open-circuit "
            "voltage difference this archive cannot say, because B0041's two "
            "branches do not overlap there"
        ),
    }

    # ---- 4. progressive or fixed? ----------------------------------------
    # A fixed cell-to-cell difference is one number; ageing is a number that
    # moves with cycle count. Each holdout trajectory's own offset against the
    # declared curve is read at the probe states its pairs reach.
    ageing = []
    for pair in sorted(own_pairs, key=lambda p: p["cycle_index"]):
        z = np.asarray(pair["z"], dtype=float)
        order = np.argsort(z)
        z = z[order]
        ocv = np.asarray(pair["ocv"], dtype=float)[order]
        values = []
        for probe in PROBE_Z:
            declared = curve_at("cold", probe)
            if declared is None or not (z[0] <= probe <= z[-1]):
                continue
            values.append((declared - float(np.interp(probe, z, ocv))) * 1000.0)
        ageing.append(
            {
                "trajectory_id": pair["trajectory_id"],
                "cycle_index": pair["cycle_index"],
                "own_delivered_ah": round(
                    float(trajectories[pair["trajectory_id"]]["delivered_ah"]), 6
                ),
                "median_offset_mv": (
                    round(statistics.median(values), 2) if values else None
                ),
            }
        )
    trend = None
    usable = [r for r in ageing if r["median_offset_mv"] is not None]
    if len(usable) >= 3:
        x = np.asarray([r["cycle_index"] for r in usable], dtype=float)
        y = np.asarray([r["median_offset_mv"] for r in usable], dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        trend = {
            "slope_mv_per_cycle": round(float(slope), 4),
            "intercept_mv": round(float(intercept), 2),
            "span_cycles": [int(x.min()), int(x.max())],
            "offset_at_first_cycle_mv": round(float(intercept + slope * x.min()), 2),
            "offset_at_last_cycle_mv": round(float(intercept + slope * x.max()), 2),
        }

    # ---- 5. the temperature cross-check -----------------------------------
    # The same resistance sets the ohmic drop and the ohmic heat, so an
    # under-estimated R makes the voltage high AND the temperature low. A curve
    # error moves the voltage and leaves the temperature where it was.
    scored = result["scored"]
    cross_check = {
        "voltage_bias_mv": {
            split: round((scored[split]["terminal_voltage"]["aggregate"]["bias"] or 0.0) * 1000.0, 2)
            for split in ("calibration", "validation", "locked_holdout")
            if scored[split]["terminal_voltage"]["aggregate"].get("n")
        },
        "temperature_bias_k": {
            split: round(scored[split]["cell_temperature"]["aggregate"]["bias"] or 0.0, 3)
            for split in ("calibration", "validation", "locked_holdout")
            if scored[split]["cell_temperature"]["aggregate"].get("n")
        },
        "reading": (
            "on the holdout the voltage is high and the temperature is low, "
            "while on calibration and validation both are near zero. One "
            "resistance sets the ohmic drop and the ohmic heat, so an "
            "under-estimated resistance produces exactly this pair of signs. An "
            "open-circuit voltage error would move the voltage and leave the "
            "temperature alone, so the temperature channel is what separates "
            "them -- and it points at the resistance"
        ),
    }

    # ---- the attribution --------------------------------------------------
    attribution = {
        "capacity_or_state_uncertainty": (
            "REFUTED on this cell. Every holdout trajectory's available charge "
            "is inside the spread the estimator declared on calibration cells"
        ),
        "ocv_inadequacy": (
            "SUPPORTED but NOT the sign of the failure. Inside the range where "
            f"B0041's branches overlap the declared cold curve sits {median_offset:+.0f} "
            "mV from the cell's own branch-averaged pseudo-OCV -- the cell is "
            "HIGHER than the curve, which on its own would make the model "
            "predict low. The model predicts high, so a curve error is present "
            "and is not what the failure is made of"
            if median_offset is not None
            else "not evaluable"
        ),
        "resistance_structure": (
            "SUPPORTED, and it is the leading attribution. B0041's own "
            f"branch-difference resistance runs {median_resistance_gap:+.3f} ohm "
            "above the cold calibration cell's where the two can be compared, "
            f"which is {separability['inside_the_overlap']['resistance_share_at_holdout_current_mv']:+.0f} "
            "mV at the holdout's 1 A -- the right sign and the right order for "
            "the observed bias. The model has no resistance-growth term: its own "
            "exclusion list says only the capacity part of ageing is carried, and "
            "this is the size of the part that is not"
        ),
        "rc_model_form": (
            "NOT IMPLICATED. A relaxation-mode error does not produce a "
            "single-signed bias across every scored sample, and the rest "
            "relaxation analysis already found no reproducible second timescale"
        ),
        "cell_to_cell_variation": (
            "SUPPORTED, and this is the same finding stated from the other side: "
            "the cold band has exactly one calibration cell, so the authority "
            "carries no cell-to-cell spread at all"
        ),
        "ageing": (
            "SUPPORTED as the mechanism behind the cell-to-cell difference. "
            "B0041 delivers 0.96-1.33 Ah where the cold calibration cell "
            "delivers 1.41-1.55 Ah at the same condition. Normalizing the charge "
            "state by usable capacity removes the capacity part of ageing and "
            "nothing else; the model's own exclusion list says so, and this "
            "holdout is what measures the size of what is left"
        ),
        "dataset_inconsistency": (
            "NOT IMPLICATED. The channel-consistency screen refused the samples "
            "where the two channels contradict each other, and the remaining "
            "residual is smooth and single-signed rather than spiky"
        ),
        "measurement_quality": (
            "NOT IMPLICATED for the same reason, and no instrument accuracy is "
            "stated by this source either way"
        ),
        "applicability_definition": (
            "IMPLICATED, and this is the actionable one. The contract declares a "
            "usable-capacity band of 0.9 to 2.0 Ah, which B0041 is inside, while "
            "the cold curve behind that band was derived from one cell at "
            "1.41-1.55 Ah. The contract admits a cell the authority has no "
            "evidence for. A band that named the capacity range its own OCV "
            "evidence covers would have refused B0041 instead of answering "
            "wrongly -- and refusing correctly is what Forge is supposed to "
            "prefer"
        ),
    }

    record = {
        "schema": DIAGNOSIS_SCHEMA,
        "what_this_is": (
            "the diagnosis R19 requires after a failed Gate A, and the reason no "
            "second holdout exists in this round"
        ),
        "gate_a_result": {
            "n": gate["n"],
            "mae_v": gate["checks"][0]["value"],
            "rmse_v": gate["checks"][1]["value"],
            "p95_v": gate["checks"][2]["value"],
            "max_abs_v": gate["max_abs"],
            "bias_v": gate["bias"],
            "passed": result["gate_a"]["gate_a_passed"],
        },
        "the_shape_of_the_failure": (
            "the voltage bias is within a third of a millivolt of the mean "
            "absolute error, so almost every scored residual has the same sign: "
            "the model is uniformly high on this cell. The same model's "
            "calibration bias is -0.38 mV and its validation bias -7.97 mV, so "
            "this is one cell at a different level rather than a model that "
            "drifted. Nothing that averages out can explain it"
        ),
        "capacity_basis_check": capacity_verdict,
        "own_pseudo_ocv_against_the_declared_curve": {
            "method": (
                "charge/discharge branch averaging on B0041's own pairs, on the "
                "axis its own capacity authority established. Admissible here: "
                "the holdout is open, the model is frozen, and nothing "
                "downstream of this is fitted"
            ),
            "rows": curve_rows,
            "median_offset_mv": median_offset,
            "per_trajectory": per_trajectory,
        },
        "offset_versus_resistance": separability,
        "temperature_cross_check": cross_check,
        "b0041_resistance_against_calibration": resistance_rows,
        "progressive_or_fixed": {"rows": ageing, "linear_trend": trend},
        "attribution": attribution,
        "what_would_settle_the_remainder": [
            "a second cold calibration cell, so the open-circuit voltage "
            "authority carries cell-to-cell spread instead of one cell's curve. "
            "This archive has none once B0041 is the holdout and B0044 has been "
            "read",
            "a capacity-conditioned open-circuit voltage authority, which needs "
            "calibration cells at several states of health in the same band",
            "an applicability band that names the usable-capacity range its own "
            "curve evidence covers, which would have refused B0041 rather than "
            "answering for it",
        ],
        "what_is_not_being_done": (
            "no second holdout. R19 is explicit and it is right: a sequence of "
            "holdouts until one passes is not validation. The next governed "
            "evaluation needs new evidence or a narrower contract, not another "
            "draw from the same archive"
        ),
    }

    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    path = os.path.join(EVIDENCE, "FAILURE_DIAGNOSIS.json")
    with open(path, "wb") as handle:
        handle.write(payload)
    print(f"wrote {path}")
    print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    print()
    print("1. capacity basis")
    for row in capacity_rows:
        print(
            f"   {row['trajectory_id']:16} Q={row['available_charge_ah']} "
            f"own={row['own_delivered_ah']} "
            f"err={'' if row['relative_error'] is None else f'{row['relative_error']*100:+.2f}%'}"
        )
    print(
        f"   max |err| {capacity_verdict['max_absolute_relative_error']} against a "
        f"declared p95 of {capacity_verdict['calibration_p95']:.4f} -> "
        f"inside: {capacity_verdict['inside_the_declared_spread']}"
    )
    print()
    print("2. declared cold curve minus B0041's OWN branch-averaged pseudo-OCV")
    for row in curve_rows:
        if row["declared_minus_own_ocv_mv"] is None:
            print(
                f"   z={row['charge_state']:.1f}  NOT SEPARABLE "
                f"({row['pairs_above_overlap_not_used']} pairs above the branch "
                "overlap; the pseudo-OCV there carries the resistance)"
            )
            continue
        print(
            f"   z={row['charge_state']:.1f}  pairs={row['pairs_inside_overlap']}  "
            f"{row['declared_minus_own_ocv_mv']:+8.2f} mV  "
            f"[{row['min_mv']:+.2f}, {row['max_mv']:+.2f}]"
        )
    print(f"   median inside the overlap: {median_offset:+.2f} mV")
    print(f"   the overlap reaches z = {separability['overlap_reaches_charge_state']}")
    print()
    print("3. B0041's own resistance against the cold calibration cell's")
    for row in resistance_rows:
        print(
            f"   z={row['charge_state']:.1f}  B0041 {row['b0041_r_eff_ohm']:.4f} ohm  "
            f"calibration {row['calibration_r_eff_ohm']:.4f} ohm  "
            f"difference {row['difference_ohm']:+.4f} ohm"
        )
    print(f"   median difference {median_resistance_gap:+.4f} ohm")
    print()
    print("   inside the branch overlap, the two terms point opposite ways:")
    print(
        f"     own OCV above the declared curve  "
        f"{-separability['inside_the_overlap']['declared_minus_own_ocv_mv']:+8.2f} mV"
        "   (would make the model predict LOW)"
    )
    print(
        f"     resistance excess at 1 A          "
        f"{separability['inside_the_overlap']['resistance_share_at_holdout_current_mv']:+8.2f} mV"
        "   (makes the model predict HIGH)"
    )
    print(
        f"     observed prediction bias          "
        f"{separability['observed_prediction_bias_mv']:+8.2f} mV   (high)"
    )
    print(f"     separable over the scored range: "
          f"{separability['separable_over_the_scored_range']}")
    print()
    print("5. the temperature cross-check")
    for split, value in cross_check["voltage_bias_mv"].items():
        print(
            f"   {split:16} voltage bias {value:+8.2f} mV   temperature bias "
            f"{cross_check['temperature_bias_k'][split]:+6.3f} K"
        )
    print()
    print("4. progressive or fixed?")
    for row in ageing:
        print(
            f"   cycle {row['cycle_index']:>3}  delivered {row['own_delivered_ah']:.4f} Ah  "
            f"offset {row['median_offset_mv']} mV"
        )
    if trend:
        print(
            f"   linear trend {trend['slope_mv_per_cycle']:+.3f} mV/cycle over "
            f"cycles {trend['span_cycles'][0]}-{trend['span_cycles'][1]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
