"""Acquisition: NASA PCoE Li-ion battery archive -> normalized trajectories.

This is the I/O half of the dataset boundary and it does no science. It
verifies bytes, reads the vendor format, applies the preregistered quality
screen, and writes one deterministic JSON per retained trajectory plus a
provenance record.

Everything here is reproducible from the archive digest alone:

    python benchmarks/battery_thermal_flagship_s3/harness/acquire.py \
        --archive D:/forge-s3-data/nasa_battery.zip

The archive itself is NOT vendored: it is 200 MB and the normalized subset is
what the campaign reads. Its SHA-256 is pinned below, the normalized files
carry it, and a mismatch stops the run.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys
import zipfile
from typing import Any

import numpy as np
import scipy.io as sio

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")

#: The exact bytes this campaign was built on.
ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"
ARCHIVE_BYTES = 209708670
ARCHIVE_URL = (
    "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
)
ARCHIVE_LANDING = "https://www.nasa.gov/intelligent-systems-division/"

#: Every cell the archive contains, with the operating conditions its own
#: README states. Read off the README text, never inferred from the data.
#: ``profile`` is the discharge load description; ``pulsed`` marks the square-
#: wave profiles.
CELL_CONDITIONS: dict[str, dict[str, Any]] = {
    **{
        cell: {
            "group": "FY08Q4",
            "readme": "README.txt",
            "profile": "constant current 2 A",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0005", "B0006", "B0007", "B0018")
    },
    **{
        cell: {
            "group": "25_26_27_28",
            "readme": "README.txt",
            "profile": "0.05 Hz square wave, 4 A amplitude, 50% duty",
            "pulsed": True,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0025", "B0026", "B0027", "B0028")
    },
    **{
        cell: {
            "group": "29_30_31_32",
            "readme": "README_29_30_31_32.txt",
            "profile": "constant current 4 A",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0029", "B0030", "B0031", "B0032")
    },
    **{
        cell: {
            "group": "33_34_36",
            "readme": "README_33_34_36.txt",
            "profile": "constant current 4 A (B0033, B0034) / 2 A (B0036)",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0033", "B0034", "B0036")
    },
    **{
        cell: {
            "group": "38_39_40",
            "readme": "README_38_39_40.txt",
            "profile": "constant current, multiple levels (1, 2, 4 A)",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0038", "B0039", "B0040")
    },
    **{
        cell: {
            "group": "41_42_43_44",
            "readme": "README_41_42_43_44.txt",
            "profile": "constant current, 4 A and 1 A",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0041", "B0042", "B0043", "B0044")
    },
    **{
        cell: {
            "group": "45_46_47_48",
            "readme": "README_45_46_47_48.txt",
            "profile": "constant current 1 A",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0045", "B0046", "B0047", "B0048")
    },
    **{
        cell: {
            "group": "49_50_51_52",
            "readme": "README_49_50_51_52.txt",
            "profile": "constant current 2 A",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0049", "B0050", "B0051", "B0052")
    },
    **{
        cell: {
            "group": "53_54_55_56",
            "readme": "README_53_54_55_56.txt",
            "profile": "constant current 2 A",
            "pulsed": False,
            "rated_capacity_ah": 2.0,
            "charge": "CC 1.5 A to 4.2 V then CV to 20 mA",
        }
        for cell in ("B0053", "B0054", "B0055", "B0056")
    },
}

# ---------------------------------------------------------------------------
# The quality screen. Every threshold below is a property of the MEASUREMENT,
# never of how well any model predicts it. No model has been run when this
# executes, and the screen is committed before any model scores anything.
# ---------------------------------------------------------------------------

#: A cycle whose first sample is not close to the CC-CV end voltage did not
#: start from the "fully charged" initial condition the protocol declares, and
#: its initial state of charge is therefore unknown.
MIN_START_VOLTAGE_V = 4.00

#: The delivered capacity a cycle must show to be a discharge at all. The NASA
#: README itself warns of runs with "very low" capacity whose cause "has not
#: been fully analyzed"; those are excluded rather than modelled.
MIN_DELIVERED_AH = 0.9
MAX_DELIVERED_AH = 2.4

#: A sampling interval this long cannot resolve the polarization relaxation the
#: 1-RC branch represents.
MAX_SAMPLE_INTERVAL_S = 60.0

#: Fewer points than this is not a trajectory worth marching.
MIN_SAMPLES = 40

#: The load must be recognisably one constant level while current flows. This
#: screens the square-wave cells, whose 20 s period is sampled at about 10 s
#: and therefore cannot be reconstructed between samples at all.
MAX_LOAD_RELATIVE_SPREAD = 0.05

#: Physically implausible channel readings.
MIN_TEMPERATURE_C = -40.0
MAX_TEMPERATURE_C = 120.0
MIN_VOLTAGE_V = 0.5
MAX_VOLTAGE_V = 5.0


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _channels(cycle) -> dict[str, np.ndarray] | None:
    data = cycle.data
    try:
        arrays = {
            "time_s": np.atleast_1d(np.asarray(data.Time, dtype=float)),
            "voltage_v": np.atleast_1d(np.asarray(data.Voltage_measured, dtype=float)),
            "current_a": np.atleast_1d(np.asarray(data.Current_measured, dtype=float)),
            "temperature_c": np.atleast_1d(
                np.asarray(data.Temperature_measured, dtype=float)
            ),
        }
    except AttributeError:
        return None
    length = min(len(v) for v in arrays.values())
    if length < 2:
        return None
    return {k: v[:length] for k, v in arrays.items()}


def screen(channels: dict[str, np.ndarray], conditions: dict[str, Any]) -> list[str]:
    """Every reason this trajectory is not usable. Empty means retained."""
    reasons: list[str] = []
    t = channels["time_s"]
    v = channels["voltage_v"]
    i = channels["current_a"]
    temperature = channels["temperature_c"]

    if not (
        np.all(np.isfinite(t))
        and np.all(np.isfinite(v))
        and np.all(np.isfinite(i))
        and np.all(np.isfinite(temperature))
    ):
        reasons.append("non_finite_channel")
        return reasons
    if len(t) < MIN_SAMPLES:
        reasons.append(f"too_few_samples:{len(t)}")
    if np.any(np.diff(t) <= 0.0):
        reasons.append("time_not_strictly_increasing")
        return reasons
    if float(np.max(np.diff(t))) > MAX_SAMPLE_INTERVAL_S:
        reasons.append(f"sample_interval_above_{MAX_SAMPLE_INTERVAL_S:g}s")
    if conditions["pulsed"]:
        reasons.append("pulsed_profile_aliased_by_sampling")
    if float(v[0]) < MIN_START_VOLTAGE_V:
        reasons.append(f"start_voltage_{float(v[0]):.3f}V_below_full_charge")
    if float(v.min()) < MIN_VOLTAGE_V or float(v.max()) > MAX_VOLTAGE_V:
        reasons.append("voltage_out_of_plausible_range")
    if (
        float(temperature.min()) < MIN_TEMPERATURE_C
        or float(temperature.max()) > MAX_TEMPERATURE_C
    ):
        reasons.append("temperature_out_of_plausible_range")

    # Discharge current is negative in this source; magnitudes above the noise
    # floor are the loaded part of the trace.
    loaded = np.abs(i) > 0.2
    if int(loaded.sum()) < MIN_SAMPLES // 2:
        reasons.append("too_few_loaded_samples")
        return reasons
    load = np.abs(i[loaded])
    spread = float(load.std() / max(load.mean(), 1e-12))
    if spread > MAX_LOAD_RELATIVE_SPREAD:
        reasons.append(f"load_not_one_level:relative_spread_{spread:.3f}")
    if np.any(i[loaded] > 0.0):
        reasons.append("loaded_samples_include_charge_current")

    dt_h = np.diff(t) / 3600.0
    mean_i = 0.5 * (np.abs(i[1:]) + np.abs(i[:-1]))
    delivered = float(np.sum(mean_i * dt_h))
    if delivered < MIN_DELIVERED_AH:
        reasons.append(f"delivered_{delivered:.3f}Ah_below_screen")
    if delivered > MAX_DELIVERED_AH:
        reasons.append(f"delivered_{delivered:.3f}Ah_above_screen")
    return reasons


def read_archive(path: str) -> tuple[str, dict[str, bytes]]:
    payload = open(path, "rb").read()
    digest = sha256_bytes(payload)
    if digest != ARCHIVE_SHA256:
        raise SystemExit(
            f"archive digest {digest} does not match the pinned "
            f"{ARCHIVE_SHA256}; this is not the bytes this campaign was built on"
        )
    if len(payload) != ARCHIVE_BYTES:
        raise SystemExit("archive byte length does not match the pinned value")
    members: dict[str, bytes] = {}
    outer = zipfile.ZipFile(io.BytesIO(payload))
    for name in outer.namelist():
        if not name.endswith(".zip"):
            continue
        group = os.path.basename(name)
        inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
        for member in inner.namelist():
            if not member.lower().endswith(".mat"):
                continue
            key = f"{group}::{os.path.basename(member)}"
            members[key] = inner.read(member)
    return digest, members


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out", default=EVIDENCE)
    args = parser.parse_args()

    digest, members = read_archive(args.archive)
    os.makedirs(args.out, exist_ok=True)

    inventory: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    seen_cells: dict[str, str] = {}

    for key in sorted(members):
        group_zip, base = key.split("::")
        cell_id = base[:-4]
        conditions = CELL_CONDITIONS.get(cell_id)
        if conditions is None:
            continue
        # B0025-B0028 appear in two group archives with identical bytes. The
        # first occurrence wins and the duplicate is recorded, so no cell is
        # normalized twice under two member paths.
        member_digest = sha256_bytes(members[key])
        if cell_id in seen_cells:
            inventory.append(
                {
                    "cell": cell_id,
                    "member": key,
                    "skipped": "duplicate_of:" + seen_cells[cell_id],
                    "member_sha256": member_digest,
                }
            )
            continue
        seen_cells[cell_id] = key

        mat = sio.loadmat(
            io.BytesIO(members[key]), squeeze_me=True, struct_as_record=False
        )
        names = [n for n in mat if not n.startswith("__")]
        cycles = mat[names[0]].cycle
        cycles = cycles if hasattr(cycles, "__len__") else [cycles]

        discharge_index = 0
        for cycle in cycles:
            if cycle.type != "discharge":
                continue
            discharge_index += 1
            channels = _channels(cycle)
            trajectory_id = f"{cell_id}.d{discharge_index:04d}"
            if channels is None:
                inventory.append(
                    {
                        "trajectory_id": trajectory_id,
                        "cell": cell_id,
                        "retained": False,
                        "reasons": ["unreadable_channels"],
                    }
                )
                continue
            ambient_c = float(cycle.ambient_temperature)
            reasons = screen(channels, conditions)
            t = channels["time_s"]
            i = channels["current_a"]
            loaded = np.abs(i) > 0.2
            dt_h = np.diff(t) / 3600.0
            delivered = float(
                np.sum(0.5 * (np.abs(i[1:]) + np.abs(i[:-1])) * dt_h)
            )
            record = {
                "trajectory_id": trajectory_id,
                "cell": cell_id,
                "cycle_index": discharge_index,
                "group": conditions["group"],
                "member": key,
                "member_sha256": member_digest,
                "member_bytes": len(members[key]),
                "ambient_temperature_c": ambient_c,
                "samples": int(len(t)),
                "duration_s": float(t[-1]),
                "max_interval_s": float(np.max(np.diff(t))),
                "load_current_a": (
                    float(np.abs(i[loaded]).mean()) if loaded.any() else 0.0
                ),
                "delivered_ah": delivered,
                "start_voltage_v": float(channels["voltage_v"][0]),
                "end_voltage_v": float(channels["voltage_v"][-1]),
                "start_temperature_c": float(channels["temperature_c"][0]),
                "max_temperature_c": float(channels["temperature_c"].max()),
                "profile": conditions["profile"],
                "retained": not reasons,
                "reasons": reasons,
            }
            inventory.append(record)
            if not reasons:
                retained.append(
                    {
                        **record,
                        "channels": {
                            "time_s": [float(x) for x in t],
                            "voltage_v": [
                                float(x) for x in channels["voltage_v"]
                            ],
                            "current_a": [float(x) for x in i],
                            "temperature_c": [
                                float(x) for x in channels["temperature_c"]
                            ],
                        },
                    }
                )
        print(f"read {cell_id}: {discharge_index} discharge cycles", file=sys.stderr)

    summary = {
        "schema": "battery_thermal_flagship_s3_inventory/1",
        "archive_sha256": digest,
        "archive_bytes": ARCHIVE_BYTES,
        "archive_url": ARCHIVE_URL,
        "screen": {
            "min_start_voltage_v": MIN_START_VOLTAGE_V,
            "min_delivered_ah": MIN_DELIVERED_AH,
            "max_delivered_ah": MAX_DELIVERED_AH,
            "max_sample_interval_s": MAX_SAMPLE_INTERVAL_S,
            "min_samples": MIN_SAMPLES,
            "max_load_relative_spread": MAX_LOAD_RELATIVE_SPREAD,
            "basis": (
                "every threshold is a property of the measurement. No model "
                "has been calibrated or scored when this runs."
            ),
        },
        "counts": {
            "inspected": len(inventory),
            "retained": len(retained),
        },
        "trajectories": [
            {k: v for k, v in item.items() if k != "channels"} for item in inventory
        ],
    }
    write_json(os.path.join(args.out, "INVENTORY.json"), summary)
    write_json(
        os.path.join(args.out, "trajectories.json"),
        {
            "schema": "battery_thermal_flagship_s3_trajectories/1",
            "archive_sha256": digest,
            "trajectories": retained,
        },
    )
    print(f"inspected {len(inventory)}, retained {len(retained)}")
    return 0


def write_json(path: str, payload: Any) -> None:
    text = json.dumps(payload, indent=1, sort_keys=False, allow_nan=False)
    # Bytes, not text: a CRLF translation here would move every digest computed
    # downstream from these files.
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")


if __name__ == "__main__":
    raise SystemExit(main())
