"""Battery Flagship B3, Phases 6-9: what the data is, how good it is, how uncertain, how split.

    python -X utf8 benchmarks/battery_flagship_b3/audit/prepare_b3.py

Writes, before any fit, under benchmarks/battery_flagship_b3/:

    DATA_QUALITY.json   Phase 7 audit (anomalies reported, nothing cleaned)
    OBSERVATIONS.json   the DERIVED observation table: every discharge-conditioned
                        row with its raw strings, z, partition, region and the
                        Phase 8 budget, pinned to the raw file's SHA-256

Neither file contains a model prediction. :func:`payloads` builds both in
memory so a test can check their digests without rewriting committed evidence.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_b3_evidence", HERE / "b3_evidence.py")
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)


def encode(payload: dict) -> bytes:
    return (json.dumps(payload, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def payloads() -> dict[str, dict]:
    raw = E.verify_raw()
    quality = E.quality_audit()

    points = E.discharge_points()
    budget = E.uncertainty_budget(points)
    table = []
    for p in points:
        table.append({**p, "uncertainty": budget[p["observation_id"]]})
    held = [p for p in points if p["partition"] == "held_out"]
    regions = {}
    for name, low, high in E.REGIONS:
        regions[name] = {
            "bounds_z": [low, min(high, 1.0)],
            "calibration": sum(1 for p in points if p["region"] == name and p["partition"] == "calibration"),
            "held_out": sum(1 for p in held if p["region"] == name),
        }
    observations = {
        "schema": "battery_flagship_b3_observations/1",
        "derived_from": {"file": f"benchmarks/battery_flagship_b3/evidence/raw/{E.INCR_OCV}", "sha256": raw[E.INCR_OCV]},
        "derivation": "rows 102..201 of the raw file (the discharge branch without the shared top row); z = Q / Q_top with Q_top the Q of row 100; no smoothing, resampling, interpolation or removal",
        "voltage_meaning": "interrupt-relaxed voltage after an UNDOCUMENTED rest, discharge-conditioned: a pseudo-OCV, not equilibrium OCV and not loaded terminal voltage",
        "q_top_ah": E.q_top_ah(),
        "split_rule": f"order by ascending z; index i; held out iff i % {E.HELD_OUT_MODULUS} == {E.HELD_OUT_RESIDUE}",
        "counts": {"total": len(points), "calibration": len(points) - len(held), "held_out": len(held), "regions": regions},
        "observations": table,
    }
    return {"DATA_QUALITY.json": quality, "OBSERVATIONS.json": observations}


def main() -> int:
    built = payloads()
    for name, payload in built.items():
        (E.ROUND / name).write_bytes(encode(payload))
    quality, observations = built["DATA_QUALITY.json"], built["OBSERVATIONS.json"]
    print(f"DATA_QUALITY.json: {sum(f['status'] == 'ANOMALY' for f in quality['findings'])} anomalies, "
          f"{sum(f['status'] == 'FAIL' for f in quality['findings'])} failures")
    print(f"OBSERVATIONS.json: {observations['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
