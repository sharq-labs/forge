"""Calibration-only fitting followed by public selection diagnostics.

No hypothesis-test significance, final-test evidence or hidden-data isolation.
The caller's RMSE resolution is a development input, not a scientific policy.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from engcore.mind.repsem.assess import canonical_bytes, ReplayMismatch
from engcore.mind.repsem.families import bind, bind_trajectory
from engcore.mind.repsem.roles import RoleTable, RoleDeclaration, RoleSource, VariableRole as R
from engcore.mind.repsem.v2 import assess, adapt, PROBLEM_SCHEMA
from engcore.scientific.units.quantity import Quantity
from .models import contracts


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalized(part):
    if set(part) != {"current", "voltage", "current_unit", "voltage_unit", "sample_ids", "group_ids"}:
        raise ValueError("explicit observations, units and lineage required; unexpected fields refused")
    count = len(part["current"])
    if count < 2 or any(len(part[k]) != count for k in ("voltage", "sample_ids", "group_ids")):
        raise ValueError("unaligned or insufficient observations")
    for key in ("sample_ids", "group_ids"):
        if any(type(v) is not str or not v.strip() for v in part[key]):
            raise ValueError("nonempty lineage strings required")
    if len(set(part["sample_ids"])) != count:
        raise ValueError("duplicate sample identifiers")
    x = [Quantity(v, part["current_unit"]).magnitude_in("A") for v in part["current"]]
    y = [Quantity(v, part["voltage_unit"]).magnitude_in("V") for v in part["voltage"]]
    if any(not math.isfinite(v) for v in x + y):
        raise ValueError("finite observations required")
    return x, y


def problem(name, contract, calibration, x, y):
    variables = [RoleDeclaration(n, r, u, RoleSource.PROBLEM_SPECIFICATION, "public L2 development").to_dict()
                 for n, r, u in (("time", R.CONTROLLED_INPUT, "s"), ("current", R.CONTROLLED_INPUT, "A"),
                                  ("voltage", R.MEASUREMENT, "V"), ("coefficient", R.LATENT_PARAMETER, contract.parameter_units["coefficient"]))]
    return {"schema": PROBLEM_SCHEMA, "clock": "time", "observable": "voltage", "variables": variables,
            "declared_family": {"family_id": name, "parameter_bounds": {"coefficient": [0.1, 10.]}, "constants": {}},
            "requested_parameters": ["coefficient"], "applicability": {"variables": ["current"]},
            "calibration_lineage": calibration,
            "sets": {"calibration": [{"id": "calibration", "unit_id": "development",
                       "columns": {"time": list(range(len(x))), "current": x, "voltage": y}}]}}


def evaluate(calibration, selection, resolution_volts, *, telemetry=None):
    # Snapshot inputs before fitting. Selection never enters the fitting spec.
    calibration, selection = json.loads(canonical_bytes([calibration, selection]))
    x, y = normalized(calibration)
    sx, sy = normalized(selection)
    for key in ("sample_ids", "group_ids"):
        if set(calibration[key]) & set(selection[key]):
            raise ValueError(f"calibration/selection {key} overlap")
    if min(sx) < min(x[1:]) or max(sx) > max(x[1:]):
        raise ValueError("selection outside scored calibration current domain")
    if resolution_volts is not None and (not math.isfinite(resolution_volts) or resolution_volts <= 0):
        raise ValueError("resolution must be unknown or finite and positive")
    models = {}
    for name, contract in contracts().items():
        started = perf_counter()
        spec = problem(name, contract, calibration, x, y)
        record = assess(spec, {name: contract})
        estimate = record.hypothesis.parameter_set[0].estimate
        roles = RoleTable.from_spec({**spec, "schema": "forge.mind.repsem.problem/1"})
        family = adapt(contract, roles, "time", constant_units={}, condition_units={})
        bound = bind_trajectory(family, bind(family, roles, "time"), roles,
                                {"id": "selection", "unit_id": "selection", "columns":
                                 {"time": list(range(len(sx))), "current": sx, "voltage": sy}})
        prediction = family.simulate({"coefficient": estimate}, bound, {})[0]
        rmse = float(np.sqrt(np.mean((prediction - sy) ** 2)))
        engine_seconds = perf_counter() - started
        started = perf_counter()
        features = x[1:] if name == "linear" else [v*v for v in x[1:]]
        denominator = sum(v*v for v in features)
        reference = None if denominator == 0 else min(10., max(0.1, sum(a*b for a,b in zip(features, y[1:])) / denominator))
        ref_features = sx if name == "linear" else [v*v for v in sx]
        ref_rmse = None if reference is None else math.sqrt(sum((reference*a-b)**2 for a,b in zip(ref_features, sy)) / len(sy))
        reference_seconds = perf_counter() - started
        if telemetry is not None:
            telemetry[name] = {"engine_seconds": engine_seconds, "reference_seconds": reference_seconds,
                               "scope": "local fit+selection; engine includes contract and assessment bookkeeping"}
        models[name] = {"assessment": record.to_dict(), "estimate": estimate, "selection_rmse_volts": rmse,
                        "reference_estimate": reference, "reference_selection_rmse_volts": ref_rmse,
                        "identifiable_design": denominator > 0,
                        "budget": {"calibration_available": len(x), "calibration_scored": len(x)-1, "selection_scored": len(sx)}}
    compatible = [] if resolution_volts is None else [name for name, m in models.items()
                      if m["identifiable_design"] and m["selection_rmse_volts"] <= resolution_volts]
    decision = "UNASSESSED" if resolution_volts is None else ("ONE_COMPATIBLE" if len(compatible) == 1 else "AMBIGUOUS" if compatible else "NONE_COMPATIBLE")
    if any(not m["identifiable_design"] for m in models.values()):
        decision, compatible = "UNASSESSED", []
    return {"evaluation_role": "selection", "final_evaluation": "NOT_RUN", "decision": decision,
            "selected": compatible[0] if len(compatible) == 1 else None, "compatible": compatible,
            "resolution_volts": resolution_volts, "calibration_digest": digest(calibration),
            "selection_digest": digest(selection), "models": models}


def bundle(telemetry=None):
    from .fixtures import CASES, build
    cases = {}
    for name in CASES:
        timing = {}
        case = build(name)
        cases[name] = {"input": case, "result": evaluate(**case, telemetry=timing)}
        if telemetry is not None:
            telemetry[name] = timing
    return {"schema": "forge.rediscovery.l2.development/1", "blindfold": False,
            "assumptions": "Public noiseless fixtures; known linear/quadratic families; 0.01 V illustrative RMSE resolution, not noise or significance; selection only; final and physical validation NOT_RUN",
            "source": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}, "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--replay", type=Path)
    args = parser.parse_args()
    telemetry = {}
    actual = bundle(telemetry)
    if args.replay:
        if canonical_bytes(json.loads(args.replay.read_text(encoding="utf-8"))) != canonical_bytes(actual):
            raise ReplayMismatch("L2 development record differs")
        print("EXACT")
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(canonical_bytes(actual).decode() + "\n")
        print(str(args.output.resolve()))
    print(json.dumps({"record_digest": digest(actual), "telemetry": telemetry}), file=sys.stderr)


if __name__ == "__main__":
    main()
