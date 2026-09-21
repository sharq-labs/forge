"""Derive the flagship OCV authority from CALIBRATION cells only.

Method
------
Each NASA cell alternates charge and discharge. Discharge ``n`` is followed by
charge ``n+1`` on the **same cell**, minutes apart, at the same ambient. Over
the charge's constant-current phase the two branches overlap in charge state,
and there::

    V_d(z) = OCV(z) - I_d R_eff(z)        (discharge, current out)
    V_c(z) = OCV(z) + I_c R_eff(z)        (charge, current in)

so both unknowns follow from the pair::

    OCV(z)   = (I_c V_d(z) + I_d V_c(z)) / (I_c + I_d)
    R_eff(z) = (V_c(z) - V_d(z)) / (I_c + I_d)

This is the classical pseudo-OCV construction. Using two branches of one cell
rather than two rates across different cells is what keeps cell-to-cell spread
and the temperature difference between a 2 A and a 4 A run out of the result.

Above the charge phase's reach
-------------------------------
The constant-current charge starts where the discharge ended and stops when the
cell reaches 4.2 V, so it covers roughly the lower three quarters of the charge
axis. Above that only the discharge branch exists, and the ohmic correction
there is an **extrapolation**: ``R_eff`` is held at its value at the top of the
overlap. That is recorded on the curve and in the report; it is not presented
as a measured two-branch average.

The charge state axis
---------------------
``z = 1 - q / Q_BASIS`` with ``Q_BASIS`` the manufacturer's 2 Ah rating, a
declared constant. Nothing here is fitted, so the curve does not depend on any
parameter a later stage will estimate. A cell that delivers less than its rating
simply stops at a charge state above zero.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile
from typing import Any

import numpy as np
import scipy.io as sio

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

from acquire import ARCHIVE_SHA256, sha256_bytes  # noqa: E402

#: The declared charge-state basis. The manufacturer's rating, not a fit.
Q_BASIS_AH = 2.0

#: Knot positions of the emitted curve, on the charge-state axis.
KNOT_COUNT = 21

#: A charge sample counts as constant-current when it carries at least this
#: current; below it the charger has entered constant voltage and the branch no
#: longer moves along the charge axis in a usable way.
CHARGE_CC_MIN_A = 1.0

#: A discharge sample counts as loaded at this fraction of the run's own median
#: load. Rest samples are excluded from the branch.
DISCHARGE_LOADED_FRACTION = 0.8

#: The relaxed anchor at full charge: the last sample of the charge cycle, whose
#: current has fallen to essentially nothing.
ANCHOR_MAX_CURRENT_A = 0.05

#: A knot needs this many calibration pairs behind it. The ends of the raw
#: coverage are reached by one pair each, and a knot resting on one pair is a
#: single experiment presented as a curve. The declared interval is shortened
#: until every interior knot clears this, which is why the authority refuses
#: near the very bottom of the discharge rather than answering there from one
#: trajectory.
MIN_SUPPORT_PAIRS = 5


def _series(cycle) -> dict[str, np.ndarray] | None:
    d = cycle.data
    try:
        arrays = {
            "t": np.atleast_1d(np.asarray(d.Time, dtype=float)),
            "v": np.atleast_1d(np.asarray(d.Voltage_measured, dtype=float)),
            "i": np.atleast_1d(np.asarray(d.Current_measured, dtype=float)),
            "T": np.atleast_1d(np.asarray(d.Temperature_measured, dtype=float)),
        }
    except AttributeError:
        return None
    n = min(len(v) for v in arrays.values())
    if n < 10:
        return None
    out = {k: v[:n] for k, v in arrays.items()}
    if not all(np.all(np.isfinite(v)) for v in out.values()):
        return None
    if np.any(np.diff(out["t"]) <= 0.0):
        return None
    return out


def _cumulative_ah(t: np.ndarray, i: np.ndarray) -> np.ndarray:
    dt_h = np.diff(t) / 3600.0
    mean = 0.5 * (i[1:] + i[:-1])
    return np.concatenate([[0.0], np.cumsum(mean * dt_h)])


def branches(cells: list[str], members: dict[str, bytes], wanted_cycles: dict[str, set[int]]):
    """Yield one (discharge, following charge) pair per selected discharge."""
    for key in sorted(members):
        cell_id = os.path.basename(key.split("::")[1])[:-4]
        if cell_id not in cells:
            continue
        mat = sio.loadmat(
            io.BytesIO(members[key]), squeeze_me=True, struct_as_record=False
        )
        names = [n for n in mat if not n.startswith("__")]
        cycles = list(mat[names[0]].cycle)
        discharge_index = 0
        for position, cycle in enumerate(cycles):
            if cycle.type != "discharge":
                continue
            discharge_index += 1
            if discharge_index not in wanted_cycles.get(cell_id, set()):
                continue
            following = None
            for later in cycles[position + 1 :]:
                if later.type == "charge":
                    following = later
                    break
                if later.type == "discharge":
                    break
            if following is None:
                continue
            d = _series(cycle)
            c = _series(following)
            if d is None or c is None:
                continue
            yield cell_id, discharge_index, float(cycle.ambient_temperature), d, c


def pair_curve(d: dict[str, np.ndarray], c: dict[str, np.ndarray]):
    """One (z, OCV) sample set from one discharge/charge pair, or None."""
    # -- discharge branch, loaded portion only, on the declared z axis
    load = np.abs(d["i"])
    nominal = float(np.median(load[load > 0.2])) if np.any(load > 0.2) else 0.0
    if nominal <= 0.0:
        return None
    loaded = load >= DISCHARGE_LOADED_FRACTION * nominal
    removed = _cumulative_ah(d["t"], -d["i"])  # positive out
    z_d = 1.0 - removed / Q_BASIS_AH
    zd = z_d[loaded]
    vd = d["v"][loaded]
    Td = d["T"][loaded]
    i_d = float(np.median(-d["i"][loaded]))
    if i_d <= 0.0 or zd.size < 10:
        return None
    z_end = float(z_d[-1])

    # -- charge branch, constant-current portion, starting where the cell was
    cc = c["i"] >= CHARGE_CC_MIN_A
    if int(cc.sum()) < 10:
        return None
    added = _cumulative_ah(c["t"], np.where(c["i"] > 0.0, c["i"], 0.0))
    z_c = z_end + added / Q_BASIS_AH
    zc = z_c[cc]
    vc = c["v"][cc]
    Tc = c["T"][cc]
    i_c = float(np.median(c["i"][cc]))
    if i_c <= 0.0:
        return None

    # -- the relaxed anchor at the end of the constant-voltage phase
    relaxed = c["i"] <= ANCHOR_MAX_CURRENT_A
    anchor = None
    if np.any(relaxed):
        tail = np.where(relaxed)[0]
        if tail[-1] == len(c["i"]) - 1:
            anchor = (float(z_c[tail[-1]]), float(c["v"][tail[-1]]))

    # -- put both branches on one ascending grid and combine where they overlap
    order_d = np.argsort(zd)
    order_c = np.argsort(zc)
    zd_s, vd_s, Td_s = zd[order_d], vd[order_d], Td[order_d]
    zc_s, vc_s, Tc_s = zc[order_c], vc[order_c], Tc[order_c]

    low = max(zd_s[0], zc_s[0])
    high = min(zd_s[-1], zc_s[-1])
    if high - low < 0.2:
        return None
    grid = np.linspace(low, high, 200)
    vd_g = np.interp(grid, zd_s, vd_s)
    vc_g = np.interp(grid, zc_s, vc_s)
    Td_g = np.interp(grid, zd_s, Td_s)
    Tc_g = np.interp(grid, zc_s, Tc_s)

    ocv = (i_c * vd_g + i_d * vc_g) / (i_c + i_d)
    r_eff = (vc_g - vd_g) / (i_c + i_d)

    # -- above the charge branch: the discharge branch with a held correction
    top_mask = zd_s > high
    extended_z = np.array([], dtype=float)
    extended_ocv = np.array([], dtype=float)
    if np.any(top_mask):
        r_top = float(r_eff[-1])
        extended_z = zd_s[top_mask]
        extended_ocv = vd_s[top_mask] + i_d * r_top

    return {
        "z_overlap": grid,
        "ocv_overlap": ocv,
        "r_eff": r_eff,
        "z_extended": extended_z,
        "ocv_extended": extended_ocv,
        "anchor": anchor,
        "i_discharge": i_d,
        "i_charge": i_c,
        "overlap": (float(low), float(high)),
        "temperature_discharge_c": (float(Td_g.min()), float(Td_g.max())),
        "temperature_charge_c": (float(Tc_g.min()), float(Tc_g.max())),
    }


def main() -> int:
    with open(os.path.join(EVIDENCE, "DATA_SELECTION.json"), encoding="utf-8") as handle:
        selection = json.load(handle)
    calibration = sorted(
        {
            item["cell"]
            for item in selection["selected"]
            if item["split"] == "calibration"
        }
    )
    wanted: dict[str, set[int]] = {}
    for item in selection["selected"]:
        if item["split"] != "calibration":
            continue
        wanted.setdefault(item["cell"], set()).add(item["cycle_index"])
    print("calibration cells:", calibration, file=sys.stderr)

    archive = os.environ.get("FORGE_S3_ARCHIVE", "D:/forge-s3-data/nasa_battery.zip")
    payload = open(archive, "rb").read()
    if sha256_bytes(payload) != ARCHIVE_SHA256:
        raise SystemExit("archive digest does not match the pinned value")
    members: dict[str, bytes] = {}
    outer = zipfile.ZipFile(io.BytesIO(payload))
    for name in outer.namelist():
        if not name.endswith(".zip"):
            continue
        inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
        for member in inner.namelist():
            if member.lower().endswith(".mat"):
                key = f"{os.path.basename(name)}::{os.path.basename(member)}"
                members.setdefault(key, inner.read(member))

    samples: list[dict[str, Any]] = []
    anchors: list[float] = []
    pairs_used: list[dict[str, Any]] = []
    for cell_id, cycle_index, ambient, d, c in branches(calibration, members, wanted):
        result = pair_curve(d, c)
        if result is None:
            continue
        samples.append(result)
        if result["anchor"] is not None:
            anchors.append(result["anchor"][1])
        pairs_used.append(
            {
                "cell": cell_id,
                "discharge_cycle": cycle_index,
                "ambient_temperature_c": ambient,
                "discharge_current_a": round(result["i_discharge"], 4),
                "charge_current_a": round(result["i_charge"], 4),
                "overlap_z": [round(x, 4) for x in result["overlap"]],
                "extended_points": int(result["z_extended"].size),
                "r_eff_ohm": [
                    round(float(np.min(result["r_eff"])), 5),
                    round(float(np.max(result["r_eff"])), 5),
                ],
                "discharge_temperature_c": [
                    round(x, 2) for x in result["temperature_discharge_c"]
                ],
                "charge_temperature_c": [
                    round(x, 2) for x in result["temperature_charge_c"]
                ],
            }
        )
        print(
            f"  {cell_id} d{cycle_index}: overlap "
            f"[{result['overlap'][0]:.3f},{result['overlap'][1]:.3f}] "
            f"+{result['z_extended'].size} extended",
            file=sys.stderr,
        )

    if not samples:
        raise SystemExit("no calibration charge/discharge pair produced a curve")

    # -- one knot grid, the median across pairs at each knot -----------------
    #
    # The top of the grid is full charge itself, and its value is the measured
    # relaxed voltage at the end of the constant-voltage phase. That is the one
    # point on this axis where the open-circuit voltage was observed directly
    # rather than reconstructed, and every trajectory starts there.
    if not anchors:
        raise SystemExit(
            "no calibration pair ended with a relaxed sample, so full charge has "
            "no measured anchor and the top of the curve would be an extrapolation"
        )
    anchor_value = float(np.median(anchors))

    curves = []
    for s in samples:
        z = np.concatenate([s["z_overlap"], s["z_extended"]])
        v = np.concatenate([s["ocv_overlap"], s["ocv_extended"]])
        order = np.argsort(z)
        curves.append((z[order], v[order]))

    def support_at(knot: float) -> list[float]:
        return [
            float(np.interp(knot, z, v)) for z, v in curves if z[0] <= knot <= z[-1]
        ]

    # Raise the bottom until every interior knot clears the support floor. The
    # top is fixed at full charge, so only the lower edge moves.
    lowest = max(min(float(z[0]) for z, _ in curves), 0.0)
    knots = np.linspace(lowest, 1.0, KNOT_COUNT)
    step = 1.0 / (KNOT_COUNT - 1) / 8.0
    while lowest < 0.5:
        knots = np.linspace(lowest, 1.0, KNOT_COUNT)
        if all(len(support_at(k)) >= MIN_SUPPORT_PAIRS for k in knots[:-1]):
            break
        lowest += step
    else:  # pragma: no cover - would mean the calibration set is unusable
        raise SystemExit("no lower bound gives every knot the declared support")

    values: list[float] = []
    spreads: list[float] = []
    support: list[int] = []
    for index, knot in enumerate(knots):
        if index == len(knots) - 1:
            values.append(anchor_value)
            spreads.append(
                float(np.percentile(anchors, 75) - np.percentile(anchors, 25))
            )
            support.append(len(anchors))
            continue
        column = support_at(knot)
        values.append(float(np.median(column)))
        spreads.append(float(np.percentile(column, 75) - np.percentile(column, 25)))
        support.append(len(column))
    anchor_used = True

    # -- strict monotonicity ------------------------------------------------
    # The model inverts nothing, but a non-monotone open-circuit voltage is not
    # a property of this chemistry, and the corpus refuses a tabulated form
    # whose independent axis does not ascend. Enforced by a declared isotonic
    # pass rather than by silently reordering samples.
    monotone = list(values)
    adjusted = 0
    for index in range(1, len(monotone)):
        if monotone[index] <= monotone[index - 1]:
            monotone[index] = monotone[index - 1] + 1e-6
            adjusted += 1

    record = {
        "schema": "battery_thermal_flagship_s3_ocv_authority/1",
        "method": (
            "pseudo-OCV by charge/discharge branch averaging within one cell, "
            "with an IR-corrected discharge branch above the charge phase's reach"
        ),
        "archive_sha256": ARCHIVE_SHA256,
        "charge_state_basis_ah": Q_BASIS_AH,
        "charge_state_basis_note": (
            "the manufacturer's 2 Ah rating, a declared constant. No fitted "
            "quantity enters this curve"
        ),
        "derived_from_split": "calibration",
        "calibration_cells": calibration,
        "pairs": pairs_used,
        "knots": [round(float(x), 6) for x in knots],
        "values_v": [round(x, 6) for x in monotone],
        "median_before_monotonic_pass_v": [round(x, 6) for x in values],
        "monotonic_adjustments": adjusted,
        "interquartile_spread_v": [round(x, 6) for x in spreads],
        "support_pairs_per_knot": support,
        "relaxed_anchor_used": anchor_used,
        "relaxed_anchor_v": round(float(np.median(anchors)), 6) if anchors else None,
        "interval": [round(float(knots[0]), 6), round(float(knots[-1]), 6)],
        "interpolation": "linear",
        "extrapolation_policy": (
            "refused. Outside [%.4f, %.4f] the declared curve returns "
            "OUTSIDE_VALIDATED_DOMAIN and the kernel propagates the refusal"
            % (knots[0], knots[-1])
        ),
        "temperature_condition": (
            "cells at 22-24 degC ambient; the cell itself reaches about 55 degC "
            "during the 4 A branches. The curve carries no temperature axis and "
            "does not claim one"
        ),
        "what_it_is_not": (
            "not an equilibrium open-circuit voltage. Branch averaging cancels "
            "the ohmic and polarization drop to first order but not the "
            "hysteresis between the two directions, and the two branches are "
            "not at identical temperature"
        ),
        "uncertainty": (
            "the interquartile spread across calibration pairs at each knot is "
            "the authority's own scatter and is carried into the uncertainty "
            "budget as an open-circuit-voltage contribution"
        ),
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    out = os.path.join(EVIDENCE, "OCV_AUTHORITY.json")
    with open(out, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")
    print(f"pairs used: {len(samples)}")
    print(f"interval: [{knots[0]:.4f}, {knots[-1]:.4f}]  knots: {KNOT_COUNT}")
    print(f"monotonic adjustments: {adjusted}")
    print(f"median IQR across knots: {np.median(spreads) * 1000:.2f} mV")
    print("values (V):", " ".join(f"{x:.4f}" for x in monotone))
    print("sha256", hashlib.sha256(open(out, "rb").read()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
