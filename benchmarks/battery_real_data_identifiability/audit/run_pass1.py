"""Battery Practical Pass 1: ingest the vendored A123 HysPowerTest bytes, split, and run the 1RC identifiability gate.

Usage (from the repository root)::

    python benchmarks/battery_real_data_identifiability/audit/run_pass1.py [--check]

Writes RECEIPT.json, QUALITY.json, SPLIT.json and IDENTIFIABILITY_GATE.json next to this
directory, as LF-only UTF-8 bytes. ``--check`` writes nothing and exits non-zero if the
committed RECEIPT.json, QUALITY.json or SPLIT.json differ from a fresh run, or if the gate's
decision or reasons differ. Nothing here calibrates, validates or produces evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engcore.domains.battery.real_data import (
    SplitPolicy,
    SplitUnit,
    VoltageNoiseDeclaration,
    assess_thevenin_1rc_identifiability,
    build_split,
    ingest_dataset,
    quality_report,
)
from engcore.domains.battery.real_data.identifiability import gate_record_digest
from engcore.domains.battery.real_data.quality import holdout_structure_report
from engcore.domains.battery.real_data import sources
from engcore.scientific.corpus import DatasetSplit
from engcore.scientific.units.quantity import Quantity

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RAW = ROOT / "benchmarks" / "battery_flagship_b3" / "evidence" / "raw"

SPLIT_POLICY = SplitPolicy(
    policy_id="jahn2024.a123_01.hyspowertest.by_test_sequence",
    unit=SplitUnit.TEST_SEQUENCE,
    calibration=(sources.HYSPOWERTEST_SOC100.test_sequence_id,),
    holdout=(sources.HYSPOWERTEST_SOC50.test_sequence_id,),
    holdout_role=DatasetSplit.VALIDATION,
    rationale=(
        "The dataset holds ONE physical cell, so no cell-level holdout exists and none is claimed. The unit is the "
        "test sequence (one raw file each). SOC100 is calibration because it is the only sequence with a discharge "
        "interruption at mid state of charge followed by a rest, a choice made from the current profile alone; "
        "SOC50 is held out and is read by no fit in this pass. The holdout supports within-cell statements only."
    ),
)

NOISE = VoltageNoiseDeclaration(
    sigma=Quantity(1.0, "millivolt"),
    source=(
        "BaSyTec CTS voltage accuracy 1 mV, distributor-transcribed technical data recorded in "
        "benchmarks/battery_flagship_b3/evidence/PROVENANCE.json"
    ),
    basis=(
        "the stated accuracy taken as a per-sample scale; it is conservative against the 0.19 mV 16-bit "
        "quantization step observed in the record. The gate's widths use the larger of this and the residual RMS "
        "(inflated for residual autocorrelation); its stability and consistency checks use the smaller."
    ),
)


def run() -> dict[str, bytes]:
    raw = {d.group_id: (RAW / d.published_filename).read_bytes() for d in sources.JAHN_2024_HYSPOWERTEST_FILES}
    dataset = ingest_dataset(
        sources.JAHN_2024_DATASET_ID,
        sources.JAHN_2024_SOURCE,
        sources.JAHN_2024_HYSPOWERTEST_FILES,
        raw,
        declared_assumptions=sources.JAHN_2024_HYSPOWERTEST_ASSUMPTIONS,
    )
    split = build_split(dataset, SPLIT_POLICY)
    gate = assess_thevenin_1rc_identifiability(dataset, split, NOISE)
    receipt = dataset.receipt.to_dict() | {"receipt_digest": dataset.receipt.digest}
    held = set(split.holdout_groups)
    quality = {"receipt_digest": dataset.receipt.digest,
               "reports": [holdout_structure_report(s) if s.group_id in held else quality_report(s)
                           for s in dataset.series]}
    split_record = split.to_dict() | {"split_digest": split.digest}
    gate_record = gate.to_dict() | {"gate_digest": gate.digest}

    def dump(value) -> bytes:
        return (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")

    return {
        "RECEIPT.json": dump(receipt),
        "QUALITY.json": dump(quality),
        "SPLIT.json": dump(split_record),
        "IDENTIFIABILITY_GATE.json": dump(gate_record),
    }


def _numeric_differences(a, b, where, rtol=1e-6, atol=1e-12) -> list[str]:
    """Every number in the committed gate record must match a fresh run within a declared tolerance."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return [f"{where}: keys differ"]
        out = []
        for key in sorted(a):
            if key == "gate_digest":
                continue
            out += _numeric_differences(a[key], b[key], f"{where}.{key}", rtol, atol)
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{where}: lengths differ"]
        out = []
        for n, (x, y) in enumerate(zip(a, b)):
            out += _numeric_differences(x, y, f"{where}[{n}]", rtol, atol)
        return out
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return [] if abs(a - b) <= atol + rtol * max(abs(a), abs(b)) else [f"{where}: {a!r} != {b!r}"]
    return [] if a == b else [f"{where}: {a!r} != {b!r}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = run()
    if not args.check:
        for name, data in outputs.items():
            (HERE / name).write_bytes(data)
        gate = json.loads(outputs["IDENTIFIABILITY_GATE.json"])
        print(f"decision {gate['decision']} ({gate['action']})")
        for reason in gate["reasons"]:
            print(f"  - {reason}")
        return 0
    problems = []
    for name in ("RECEIPT.json", "QUALITY.json", "SPLIT.json"):
        if (HERE / name).read_bytes() != outputs[name]:
            problems.append(f"{name} differs from a fresh run")
    committed = json.loads((HERE / "IDENTIFIABILITY_GATE.json").read_bytes())
    fresh = json.loads(outputs["IDENTIFIABILITY_GATE.json"])
    for key in ("decision", "action", "reasons", "receipt_digest", "split_digest"):
        if committed[key] != fresh[key]:
            problems.append(f"IDENTIFIABILITY_GATE.json {key} differs from a fresh run")
    if gate_record_digest(committed) != committed.get("gate_digest"):
        problems.append("IDENTIFIABILITY_GATE.json gate_digest does not match its own contents")
    problems.extend(_numeric_differences(committed, fresh, "IDENTIFIABILITY_GATE.json"))
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
