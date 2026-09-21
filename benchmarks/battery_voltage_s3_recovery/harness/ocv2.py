"""R4: the open-circuit voltage authority, re-derived on a measured charge axis.

What changed, and why it had to
------------------------------
Sprint 3's pseudo-OCV put every calibration pair on one declared axis,
``z = 1 - q / 2.0 Ah``. That axis is wrong by 20-33 % for every cell in this
archive and wrong by a *different* amount for each, so pooling pairs on it
smears cells that are at different true depths of discharge into the same knot.
The curve's own interquartile spread across pairs was 45 mV at the median knot,
and the offset between what calibration cells and validation cells said at the
same knot was 17 mV.

Re-derived on ``z = 1 - q / Q_available``, with ``Q_available`` read from each
pair's own prior cycles, the same pairs give a median spread of 23 mV and a
calibration-to-validation offset of 2.7 mV. The axis was carrying most of what
looked like cell-to-cell variation in the curve.

Because the axis is part of the relation, this is a different open-circuit
voltage authority and therefore a different model, and it is emitted under its
own version rather than written over the Sprint 3 table.

Conditioned on cell temperature, not on ambient
-----------------------------------------------
The first attempt conditioned on ambient and produced a degenerate cold curve.
The reason is worth recording: at 4 degC ambient the 4 A discharges self-heat to
23-41 degC, so they are not cold measurements at all, while the 1 A discharges
at the same ambient stay at 6-13 degC. Ambient labels the chamber; the
open-circuit voltage relation, if it has a temperature axis, follows the cell.

So the conditioning variable is the median measured cell temperature over the
loaded discharge branch, and the bands are declared below.

Pooling the two bands is emitted as well, and it is not a curve anybody should
choose: it is the evidence that the bands are different relations. If one curve
served both, pooling would not widen the spread.

Every calibration-cell discharge with an establishable state contributes, not
only the ones the campaign selected as prediction targets. An authority is
better for more calibration evidence and the selection stride exists to bound
campaign cost, which does not apply here.

Method, otherwise unchanged from Sprint 3
-----------------------------------------
Pseudo-OCV by charge/discharge branch averaging within one cell, weighted by
the two currents so the ohmic and polarization drops cancel to first order;
linear interpolation between knots; extrapolation refused. Calibration cells
only -- no validation or holdout cell contributes a knot, and the holdout
cell's trajectories are not read at all.

One thing did change besides the axis. Sprint 3's top knot was the relaxed tail
of the charge's constant-voltage phase. On a capacity-normalized axis that tail
is not the state ``z = 1`` names, and at low ambient the charger stops before
reaching it, so the knot at ``z = 1`` is instead the median **opening rest
sample of the discharges themselves** -- the same instant the initial-state
authority reads, and a direct measurement of open-circuit voltage at exactly
the state the march starts from.

    python benchmarks/battery_voltage_s3_recovery/harness/ocv2.py
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

import corpus as cp  # noqa: E402

OCV_AUTHORITY_SCHEMA = "battery_voltage_s3_recovery_ocv_authority/1"
ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"

#: Knot positions on the charge-state axis. Sprint 3's spacing, unchanged.
KNOT_COUNT = 21

#: A charge sample counts as constant-current at or above this current.
CHARGE_CC_MIN_A = 1.0

#: A discharge sample counts as loaded at this fraction of the run's own median.
DISCHARGE_LOADED_FRACTION = 0.5

#: The charge's relaxed tail, recorded for comparison with Sprint 3's anchor.
#: It is no longer the top knot; see the module docstring.
ANCHOR_MAX_CURRENT_A = 0.05

#: A knot needs this many independent pairs before it is admitted.
MIN_SUPPORT_PAIRS = 7

#: Cell-temperature bands the curve is conditioned on, in degrees Celsius, read
#: off the measured median over each pair's loaded discharge branch. The split
#: is where this archive's evidence actually separates: the 1 A discharges at
#: 4 degC ambient sit at 6-13 degC and everything else sits above 20 degC, with
#: nothing measured in between.
CELL_TEMPERATURE_BANDS = (
    ("cold", -40.0, 20.0),
    ("warm", 20.0, 120.0),
)


def temperature_band(celsius: float) -> str:
    for name, low, high in CELL_TEMPERATURE_BANDS:
        if low <= celsius < high:
            return name
    return "undeclared"

#: The frozen voltage acceptance tolerance. A knot whose interquartile spread
#: across calibration pairs exceeds it is a knot the authority disagrees with
#: itself about by more than the campaign's own definition of agreement, so the
#: interval stops there. Carried from the Sprint 3 preregistration.
ACCEPTANCE_TOLERANCE_V = 0.050


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_members(path: str) -> dict[str, bytes]:
    payload = open(path, "rb").read()
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
                members.setdefault(
                    f"{os.path.basename(name)}::{os.path.basename(member)}",
                    inner.read(member),
                )
    return members


def series(cycle):
    data = cycle.data
    try:
        arrays = {
            "t": np.atleast_1d(np.asarray(data.Time, dtype=float)),
            "v": np.atleast_1d(np.asarray(data.Voltage_measured, dtype=float)),
            "i": np.atleast_1d(np.asarray(data.Current_measured, dtype=float)),
            "T": np.atleast_1d(np.asarray(data.Temperature_measured, dtype=float)),
        }
    except AttributeError:
        return None
    n = min(len(v) for v in arrays.values())
    if n < 2:
        return None
    out = {k: v[:n] for k, v in arrays.items()}
    if not all(np.all(np.isfinite(v)) for v in out.values()):
        return None
    if np.any(np.diff(out["t"]) <= 0.0):
        return None
    return out


def cumulative_ah(t: np.ndarray, i: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(0.5 * (i[1:] + i[:-1]) * np.diff(t) / 3600.0)])


def pair_curve(d, c, basis: float) -> dict[str, Any] | None:
    """One (z, OCV, R_eff) sample set from one discharge/charge pair."""
    load = np.abs(d["i"])
    if not np.any(load > 0.2):
        return None
    nominal = float(np.median(load[load > 0.2]))
    loaded = load >= DISCHARGE_LOADED_FRACTION * nominal
    removed = cumulative_ah(d["t"], -d["i"])
    z_d = 1.0 - removed / basis
    zd, vd, Td = z_d[loaded], d["v"][loaded], d["T"][loaded]
    i_d = float(np.median(-d["i"][loaded]))
    if i_d <= 0.0 or zd.size < 10:
        return None
    z_end = float(z_d[-1])

    cc = c["i"] >= CHARGE_CC_MIN_A
    if int(cc.sum()) < 10:
        return None
    added = cumulative_ah(c["t"], np.where(c["i"] > 0.0, c["i"], 0.0))
    z_c = z_end + added / basis
    zc, vc = z_c[cc], c["v"][cc]
    i_c = float(np.median(c["i"][cc]))
    if i_c <= 0.0:
        return None

    order_d, order_c = np.argsort(zd), np.argsort(zc)
    zd_s, vd_s, Td_s = zd[order_d], vd[order_d], Td[order_d]
    zc_s, vc_s = zc[order_c], vc[order_c]
    low, high = max(zd_s[0], zc_s[0]), min(zd_s[-1], zc_s[-1])
    if high - low < 0.2:
        return None
    grid = np.linspace(low, high, 200)
    vd_g = np.interp(grid, zd_s, vd_s)
    vc_g = np.interp(grid, zc_s, vc_s)
    Td_g = np.interp(grid, zd_s, Td_s)
    ocv = (i_c * vd_g + i_d * vc_g) / (i_c + i_d)
    r_eff = (vc_g - vd_g) / (i_c + i_d)
    median_cell_temperature_c = float(np.median(Td))

    top = zd_s > high
    extended_z = zd_s[top] if np.any(top) else np.array([], dtype=float)
    extended_ocv = (
        vd_s[top] + i_d * float(r_eff[-1]) if np.any(top) else np.array([], dtype=float)
    )

    relaxed = c["i"] <= ANCHOR_MAX_CURRENT_A
    anchor = None
    if np.any(relaxed):
        tail = np.where(relaxed)[0]
        if tail[-1] == len(c["i"]) - 1:
            anchor = (float(z_c[tail[-1]]), float(c["v"][tail[-1]]))

    # The knot at z = 1 is the discharge's own opening rest sample. On this axis
    # z = 1 *is* the state the trajectory starts from, and that sample measures
    # its open-circuit voltage directly -- the same instant the initial-state
    # authority reads. The charge cycle's relaxed tail is a different state on a
    # capacity-normalized axis, and at low ambient the charger stops before
    # reaching it at all.
    opening_rest = (
        float(d["v"][0]) if abs(float(d["i"][0])) < 0.2 else None
    )

    return {
        "z": np.concatenate([grid, extended_z]),
        "ocv": np.concatenate([ocv, extended_ocv]),
        "z_overlap": grid,
        "r_eff": r_eff,
        "anchor": anchor,
        "i_discharge": i_d,
        "i_charge": i_c,
        "overlap": (float(low), float(high)),
        "temperature_discharge_c": (float(Td_g.min()), float(Td_g.max())),
        "median_cell_temperature_c": median_cell_temperature_c,
        "temperature_band": temperature_band(median_cell_temperature_c),
        "opening_rest_v": opening_rest,
        "z_end": z_end,
    }


def assemble(pairs: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    """Median curve over pairs, with support and spread at every knot."""
    if not pairs:
        return None
    anchors = [p["anchor"][1] for p in pairs if p["anchor"] is not None]
    knots = np.linspace(0.0, 1.0, KNOT_COUNT)
    values: list[float] = []
    spreads: list[float] = []
    support: list[int] = []
    for z in knots:
        samples = []
        for p in pairs:
            zs, vs = p["z"], p["ocv"]
            order = np.argsort(zs)
            zs, vs = zs[order], vs[order]
            if zs[0] <= z <= zs[-1]:
                samples.append(float(np.interp(z, zs, vs)))
        support.append(len(samples))
        if len(samples) >= MIN_SUPPORT_PAIRS:
            values.append(float(np.median(samples)))
            spreads.append(
                float(np.percentile(samples, 75) - np.percentile(samples, 25))
            )
        else:
            values.append(float("nan"))
            spreads.append(float("nan"))

    # Admit the longest run of knots that has support AND whose spread is inside
    # the frozen acceptance tolerance. The floor is derived, not chosen.
    admitted = [
        index
        for index in range(KNOT_COUNT)
        if support[index] >= MIN_SUPPORT_PAIRS
        and np.isfinite(spreads[index])
        and spreads[index] <= ACCEPTANCE_TOLERANCE_V
    ]
    if not admitted:
        return None
    # one contiguous block ending at the top
    top = max(admitted)
    floor_index = top
    while floor_index - 1 in admitted:
        floor_index -= 1
    keep = list(range(floor_index, top + 1))

    z_keep = [float(knots[i]) for i in keep]
    v_keep = [values[i] for i in keep]
    spread_keep = [spreads[i] for i in keep]
    support_keep = [support[i] for i in keep]

    # z = 1 is the state every trajectory starts from on this axis, and the
    # march begins there, so the curve has to answer there rather than refuse.
    # The knot is the median opening rest voltage of the band's own pairs: a
    # direct measurement of open-circuit voltage at exactly that state.
    opening = [p["opening_rest_v"] for p in pairs if p["opening_rest_v"] is not None]
    anchor_used = False
    if opening and len(opening) >= MIN_SUPPORT_PAIRS and z_keep[-1] < 1.0:
        z_keep.append(1.0)
        v_keep.append(float(np.median(opening)))
        spread_keep.append(
            float(np.percentile(opening, 75) - np.percentile(opening, 25))
        )
        support_keep.append(len(opening))
        anchor_used = True

    # Monotonic in charge state: a pseudo-OCV that falls with charge would make
    # the kernel non-physical. Adjustments are counted and reported.
    adjustments = 0
    for index in range(1, len(v_keep)):
        if v_keep[index] < v_keep[index - 1]:
            v_keep[index] = v_keep[index - 1]
            adjustments += 1

    return {
        "curve_id": label,
        "pairs": len(pairs),
        "knots": [round(x, 6) for x in z_keep],
        "values_v": [round(x, 6) for x in v_keep],
        "interquartile_spread_v": [round(x, 6) for x in spread_keep],
        "support_pairs_per_knot": support_keep,
        "interval": [round(z_keep[0], 6), round(z_keep[-1], 6)],
        "median_interquartile_spread_v": round(float(np.median(spread_keep)), 6),
        "max_interquartile_spread_v": round(float(np.max(spread_keep)), 6),
        "opening_rest_knot_used": anchor_used,
        "opening_rest_v": round(float(np.median(opening)), 6) if opening else None,
        "opening_rest_pairs": len(opening),
        "charge_relaxed_anchor_v": (
            round(float(np.median(anchors)), 6) if anchors else None
        ),
        "why_not_the_charge_relaxed_anchor": (
            "on a capacity-normalized axis the charge cycle's relaxed tail is "
            "not the state z = 1 names, and at low ambient the charger stops "
            "before reaching that tail at all"
        ),
        "monotonic_adjustments": adjustments,
        "charge_state_floor": round(z_keep[0], 6),
        "discharge_temperature_c": [
            round(min(p["temperature_discharge_c"][0] for p in pairs), 2),
            round(max(p["temperature_discharge_c"][1] for p in pairs), 2),
        ],
        "currents_a": {
            "discharge": sorted({round(p["i_discharge"], 2) for p in pairs}),
            "charge": sorted({round(p["i_charge"], 2) for p in pairs}),
        },
    }


def resistance_profile(pairs: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """The measured branch-difference resistance, on the same axis.

    This is a measurement, not a fit: ``(V_charge - V_discharge)/(i_c + i_d)``
    at a common charge state. R5 asks whether R0 needs a charge-state axis, and
    this is the evidence that answers it without running a model.
    """
    knots = np.linspace(0.05, 1.0, 20)
    rows = []
    for z in knots:
        samples = []
        for p in pairs:
            zs = p["z_overlap"]
            if zs[0] <= z <= zs[-1]:
                samples.append(float(np.interp(z, zs, p["r_eff"])))
        if len(samples) >= MIN_SUPPORT_PAIRS:
            rows.append(
                {
                    "charge_state": round(float(z), 4),
                    "pairs": len(samples),
                    "median_ohm": round(float(np.median(samples)), 6),
                    "p25_ohm": round(float(np.percentile(samples, 25)), 6),
                    "p75_ohm": round(float(np.percentile(samples, 75)), 6),
                }
            )
    ratio = None
    if len(rows) >= 2:
        ratio = round(rows[0]["median_ohm"] / rows[-1]["median_ohm"], 4)
    return {
        "curve_id": label,
        "knots": rows,
        "low_over_high_ratio": ratio,
        "what_it_is": (
            "(V_charge - V_discharge) / (i_charge + i_discharge) at a common "
            "charge state: the resistance the two branches imply, measured "
            "with no model and no fit"
        ),
    }


def _block(row: dict[str, Any], corner: str) -> tuple[str, str, float]:
    return (row["cell"], corner, round(abs(row["load_current_a"]) * 2.0) / 2.0)


def calibration_pool() -> dict[str, dict[int, dict[str, Any]]]:
    """Every screened calibration discharge inside a declared cycle block.

    A **block** is one cell at one ambient corner and one nominal load. The
    campaign's selection takes a stride through each block to bound how many
    trajectories it predicts; that stride does not bound what an authority may
    be derived from, so every screened discharge of the block is used.

    The block's *cycle range* does bind: it is the lowest and highest cycle the
    corpus selected for that block, and nothing outside it is admitted. That
    matters because the capacity-normalized axis removes the capacity part of
    ageing and not the rest of it -- pooling a cell's whole life widens the
    curve's spread even on the corrected axis, which is a measurement worth
    recording rather than a nuisance to average away.

    Validation and holdout cells are excluded by cell identity, and
    :func:`corpus.refuse_holdout` checks the result rather than trusting it.
    """
    selection = json.load(
        open(os.path.join(EVIDENCE, "SELECTION.json"), encoding="utf-8")
    )
    state = json.load(
        open(os.path.join(EVIDENCE, "BATTERY_STATE_AUTHORITY.json"), encoding="utf-8")
    )
    cells = {
        row["cell"] for row in selection["selected"] if row["split"] == "calibration"
    }
    other = {
        row["cell"]
        for row in selection["selected"]
        if row["split"] != "calibration"
    }
    overlap = sorted(cells & other)
    if overlap:
        raise SystemExit(f"cells in calibration and another split: {overlap}")

    blocks: dict[tuple[str, str, float], list[int]] = {}
    for row in selection["selected"]:
        if row["split"] != "calibration" or row.get("applicability") != "inside":
            continue
        blocks.setdefault(_block(row, row["corner"]), []).append(row["cycle_index"])
    ranges = {key: (min(v), max(v)) for key, v in blocks.items()}
    print(
        "declared calibration blocks: "
        + ", ".join(
            f"{k[0]}/{k[1]}/{k[2]:g}A cycles {v[0]}-{v[1]}"
            for k, v in sorted(ranges.items())
        ),
        file=sys.stderr,
    )

    inventory = cp.cycle_inventory()
    relative = state["capacity_estimator"][
        "adopted_relative_standard_uncertainty"
    ]
    bands = state["charge_termination_bands"]["by_corner"]
    wanted: dict[str, dict[int, dict[str, Any]]] = {}
    refused = 0
    outside_block = 0
    for item in cp.normalized_trajectories():
        if item["cell"] not in cells:
            continue
        corner = (
            "low_ambient"
            if item["ambient_temperature_c"] <= cp.LOW_AMBIENT_C[1]
            else "room_ambient"
        )
        window = ranges.get(_block(item, corner))
        if window is None or not window[0] <= item["cycle_index"] <= window[1]:
            outside_block += 1
            continue
        band = bands.get(corner, {}).get("band_a")
        row = {
            "trajectory_id": item["trajectory_id"],
            "cell": item["cell"],
            "group": item["group"],
            "cycle_index": item["cycle_index"],
            "ambient_temperature_c": item["ambient_temperature_c"],
            "load_current_a": item["load_current_a"],
            "corner": corner,
        }
        capacity, initial = cp.establish_states(
            row,
            item,
            inventory,
            full_charge_anchor_v=4.188513,
            anchor_tolerance_v=ACCEPTANCE_TOLERANCE_V,
            capacity_relative_uncertainty=relative,
            termination_current_band=tuple(band) if band else None,
        )
        if not (capacity.is_known and initial.is_known):
            refused += 1
            continue
        row["basis_ah"] = capacity.initial_available_charge.magnitude_in(
            "ampere_hour"
        )
        wanted.setdefault(item["cell"], {})[item["cycle_index"]] = row
    cp.refuse_holdout(
        selection,
        [r["trajectory_id"] for c in wanted.values() for r in c.values()],
    )
    print(
        f"calibration pool: {sum(len(v) for v in wanted.values())} discharges "
        f"with an established state, {refused} refused, "
        f"{outside_block} outside a declared block",
        file=sys.stderr,
    )
    return wanted


def main() -> int:
    wanted = calibration_pool()

    archive = os.environ.get("FORGE_S3_ARCHIVE", "D:/forge-s3-data/nasa_battery.zip")
    members = read_members(archive)

    collected: list[dict[str, Any]] = []
    for key in sorted(members):
        cell = os.path.basename(key.split("::")[1])[:-4]
        if cell not in wanted:
            continue
        mat = sio.loadmat(
            io.BytesIO(members[key]), squeeze_me=True, struct_as_record=False
        )
        names = [n for n in mat if not n.startswith("__")]
        cycles = list(mat[names[0]].cycle)
        discharge_index = 0
        for position, cycle in enumerate(cycles):
            if str(cycle.type) != "discharge":
                continue
            discharge_index += 1
            row = wanted[cell].get(discharge_index)
            if row is None:
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
            d, c = series(cycle), series(following)
            if d is None or c is None:
                continue
            basis = float(row["basis_ah"])
            result = pair_curve(d, c, basis)
            if result is None:
                continue
            result["cell"] = cell
            result["discharge_index"] = discharge_index
            result["corner"] = row["corner"]
            result["basis_ah"] = basis
            collected.append(result)

    bands = sorted({p["temperature_band"] for p in collected})
    print(
        "pairs by cell-temperature band: "
        + ", ".join(
            f"{b}={sum(1 for p in collected if p['temperature_band'] == b)}"
            for b in bands
        ),
        file=sys.stderr,
    )
    curves = {"pooled": assemble(collected, "pooled")}
    profiles = {"pooled": resistance_profile(collected, "pooled")}
    for band in bands:
        subset = [p for p in collected if p["temperature_band"] == band]
        curves[band] = assemble(subset, band)
        profiles[band] = resistance_profile(subset, band)

    record = {
        "schema": OCV_AUTHORITY_SCHEMA,
        "version": "2",
        "supersedes": "battery_thermal_flagship_s3_ocv_authority/1",
        "why_a_new_authority": (
            "the charge-state axis is part of the relation. Sprint 3's axis was "
            "the manufacturer's 2 Ah rating; this one is each pair's own "
            "measured available charge, read from cycles prior to it. A curve "
            "on a different axis is a different open-circuit voltage relation "
            "and therefore a different model, not a correction to the old one"
        ),
        "method": (
            "pseudo-OCV by charge/discharge branch averaging within one cell, "
            "weighted by the two currents; measured relaxed anchor at the top; "
            "linear interpolation; extrapolation refused"
        ),
        "archive_sha256": ARCHIVE_SHA256,
        "charge_state_basis": (
            "z = 1 - q / Q_available, with Q_available established per "
            "trajectory by engcore.domains.battery.capacity from prior cycles"
        ),
        "derived_from_split": "calibration",
        "calibration_cells": sorted({p["cell"] for p in collected}),
        "cell_temperature_bands_c": [
            {"band": name, "low": low, "high": high}
            for name, low, high in CELL_TEMPERATURE_BANDS
        ],
        "conditioned_on": (
            "median measured cell temperature over the loaded discharge "
            "branch. Ambient is not the conditioning variable: at 4 degC "
            "ambient the 4 A discharges self-heat to 23-41 degC and are not "
            "cold measurements"
        ),
        "acceptance_tolerance_v": ACCEPTANCE_TOLERANCE_V,
        "min_support_pairs": MIN_SUPPORT_PAIRS,
        "floor_rule": (
            "the lowest knot of the contiguous admitted block, where a knot is "
            f"admitted only with at least {MIN_SUPPORT_PAIRS} pairs behind it "
            "and an interquartile spread across those pairs inside the frozen "
            "acceptance tolerance"
        ),
        "pairs_used": [
            {
                "cell": p["cell"],
                "discharge_cycle": p["discharge_index"],
                "corner": p["corner"],
                "basis_ah": round(p["basis_ah"], 6),
                "i_discharge": round(p["i_discharge"], 4),
                "i_charge": round(p["i_charge"], 4),
                "overlap_z": [round(x, 4) for x in p["overlap"]],
                "temperature_discharge_c": [
                    round(x, 2) for x in p["temperature_discharge_c"]
                ],
                "median_cell_temperature_c": round(
                    p["median_cell_temperature_c"], 2
                ),
                "temperature_band": p["temperature_band"],
            }
            for p in collected
        ],
        "curves": {k: v for k, v in curves.items() if v is not None},
        "resistance_profiles": profiles,
        "what_it_is_not": (
            "not an equilibrium open-circuit voltage. Branch averaging does not "
            "cancel the hysteresis between the two directions and the branches "
            "are not at identical temperature within a band. The pooled curve "
            "is emitted as evidence that the bands differ, not as a curve to "
            "use; the banded curves do not interpolate between bands and refuse "
            "outside their own charge-state interval"
        ),
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    out = os.path.join(EVIDENCE, "OCV_AUTHORITY_V2.json")
    with open(out, "wb") as handle:
        handle.write(payload)
    print(f"\nwrote {out}")
    print(f"sha256 {sha256_bytes(payload)}")
    for name, curve in record["curves"].items():
        print(
            f"  curve {name:14} pairs={curve['pairs']:3d} "
            f"interval [{curve['interval'][0]:.4f},{curve['interval'][1]:.4f}] "
            f"knots={len(curve['knots']):2d} "
            f"median IQR {curve['median_interquartile_spread_v']*1000:6.2f} mV "
            f"max IQR {curve['max_interquartile_spread_v']*1000:6.2f} mV "
            f"adjustments={curve['monotonic_adjustments']}"
        )
    for name, profile in profiles.items():
        if profile["knots"]:
            print(
                f"  R_eff {name:14} "
                f"z={profile['knots'][0]['charge_state']:.2f} "
                f"{profile['knots'][0]['median_ohm']:.4f} ohm -> "
                f"z={profile['knots'][-1]['charge_state']:.2f} "
                f"{profile['knots'][-1]['median_ohm']:.4f} ohm   "
                f"ratio {profile['low_over_high_ratio']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
