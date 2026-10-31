"""Bounded public L1 integration run and exact replay; no hidden or final data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

from engcore.mind.repsem.assess import ReplayMismatch, canonical_bytes
from engcore.mind.repsem.v2 import assess
from engcore.scientific.units.quantity import Quantity
from .fixtures import CASES, build
from .models import contracts


def reference(spec):
    """Through-origin analytic least squares on exactly the engine's scored rows.

    Repsem omits each trajectory's initial row. No truth or final data is used.
    This L1 reference has the same known equation as the engine, no UQ claim.
    """
    units = {v["name"]: v["unit"] for v in spec["variables"]}
    currents, voltages = [], []
    for trajectory in spec["sets"]["calibration"]:
        columns = trajectory["columns"]
        currents.extend(Quantity(x, units["current"]).magnitude_in("A") for x in columns["current"][1:])
        voltages.extend(Quantity(x, units["voltage"]).magnitude_in("V") for x in columns["voltage"][1:])
    denominator = sum(x * x for x in currents)
    estimate = None if denominator == 0 else sum(x * y for x, y in zip(currents, voltages)) / denominator
    return {"method": "analytic_through_origin_least_squares", "resistance_ohm": estimate,
            "observations": len(currents), "available_rows": sum(len(t["columns"]["time"]) for t in spec["sets"]["calibration"]),
            "uncertainty": None, "evaluation_role": "calibration"}


def build_bundle():
    families = contracts()
    cases = {}
    for case in CASES:
        spec = build(case)
        cases[case] = {"problem": spec, "assessment": assess(spec, families).to_dict(), "reference": reference(spec)}
    source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
    return {"schema": "forge.rediscovery.development/1", "scope": "PUBLIC_SYNTHETIC_L1_DEVELOPMENT",
            "level": "L1_PARAMETER_ESTIMATION", "blindfold": False, "source": source,
            "assumptions": {"data": "public synthetic noiseless controls", "truth": "public R=2 ohm; misspecified adds 1 V",
                            "sigma": "where present, 0.01 V assumed analysis resolution; no noise was generated",
                            "uncertainty": "conditional on declared assumptions; calibration NOT_TESTED",
                            "physical_validation": "NOT_RUN", "evaluation_role": "calibration only"},
            "final_evaluation": "NOT_RUN", "cases": cases}


def replay_bundle(record):
    if canonical_bytes(record) != canonical_bytes(build_bundle()):
        raise ReplayMismatch("development fixture, model, source or output changed")
    return "EXACT"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--output", type=Path, help="create a new JSON record; existing files are never overwritten")
    group.add_argument("--replay", type=Path, help="re-execute and compare the complete record")
    args = parser.parse_args()
    started = perf_counter()
    if args.replay:
        print(replay_bundle(json.loads(args.replay.read_text(encoding="utf-8"))))
    else:
        payload = canonical_bytes(build_bundle()).decode() + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(payload)
            print(str(args.output.resolve()))
        else:
            print(payload, end="")
    print(json.dumps({"local_elapsed_seconds": perf_counter() - started,
                      "timing_scope": "whole development command; not per-method performance evidence"}), file=sys.stderr)


if __name__ == "__main__":
    main()
