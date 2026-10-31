"""Support recovery in {x,x²,x³}+intercept, using the existing sparse engine.

The development wrapper reports all smallest compatible supports; no tie-breaking
can turn observationally indistinguishable supports into a unique recovery.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from benchmarks.rediscovery_l2.run import normalized, digest
from engcore.mind.repsem.assess import canonical_bytes, ReplayMismatch
from engcore.scientific.discovery import DiscoveryDataset, DiscoveryFeature, SparseDiscoveryPolicy, discover_sparse_equations, DiscoveryCandidateStatus
from engcore.scientific.equations import Symbol, PowerExpression
from engcore.scientific.equations.evaluation import evaluate_expression
from engcore.scientific.units.quantity import Quantity

GRAMMAR = {"features": ["x", "x2", "x3"], "intercept": True, "max_terms": 3,
           "normalization": {"x": "I / (1 A)", "y": "V / (1 V)"},
           "scope": "bounded polynomial support recovery; not unrestricted symbolic discovery"}


def evaluate(calibration, selection, resolution_volts, *, telemetry=None):
    calibration, selection = json.loads(canonical_bytes([calibration, selection]))
    x, y = normalized(calibration)
    sx, sy = normalized(selection)
    for key in ("sample_ids", "group_ids"):
        if set(calibration[key]) & set(selection[key]):
            raise ValueError(f"calibration/selection {key} overlap")
    if min(sx) < min(x) or max(sx) > max(x):
        raise ValueError("selection outside calibration domain")
    if resolution_volts is not None and (not math.isfinite(resolution_volts) or resolution_volts <= 0):
        raise ValueError("resolution must be unknown or finite and positive")
    bindings = tuple({"x": Quantity(v, "1")} for v in x + sx)
    expressions = (Symbol("x"), PowerExpression(Symbol("x"), 2), PowerExpression(Symbol("x"), 3))
    features = tuple(DiscoveryFeature(name, expr,
                      tuple(evaluate_expression(expr, row).magnitude_in("1") for row in bindings), bindings)
                     for name, expr in zip(GRAMMAR["features"], expressions))
    policy = SparseDiscoveryPolicy(max_terms=3, maximum_candidates=7,
                                    holdout_rmse_limit=resolution_volts if resolution_volts is not None else 0.)
    dataset = DiscoveryDataset("public-l3", features, tuple(y+sy), tuple(range(len(x))),
                tuple(range(len(x), len(x)+len(sx))), digest({"grammar": GRAMMAR, "policy": asdict(policy)}),
                (digest(calibration), digest(selection)), tuple(calibration["sample_ids"]+selection["sample_ids"]),
                tuple(calibration["group_ids"]+selection["group_ids"]))
    started = perf_counter()
    candidates = discover_sparse_equations(dataset, policy)
    engine_seconds = perf_counter()-started
    compatible = [c for c in candidates if resolution_volts is not None
                  and c.status is DiscoveryCandidateStatus.SURVIVED_HOLDOUT
                  and c.holdout_rmse <= resolution_volts]
    smallest = min((c.complexity for c in compatible), default=None)
    minimal = [c for c in compatible if c.complexity == smallest]
    decision = "ONE_MINIMAL_SUPPORT" if len(minimal) == 1 else "AMBIGUOUS" if minimal else "NONE_COMPATIBLE"
    if resolution_volts is None or max(y) == min(y) or not candidates:
        decision, minimal = "UNASSESSED", []
    def encode(candidate):
        result = asdict(candidate)
        result["status"] = candidate.status.value
        result["fingerprint"] = candidate.fingerprint
        return json.loads(canonical_bytes(result))
    started = perf_counter()
    # Dense polynomial reference: same rows, grammar and NumPy solver, one fit.
    design = np.vander(np.asarray(x), 4, increasing=True)
    coefficients, _, rank, _ = np.linalg.lstsq(design, np.asarray(y), rcond=None)
    prediction = np.vander(np.asarray(sx), 4, increasing=True) @ coefficients
    baseline = {"method": "dense_cubic_least_squares", "rank": int(rank), "unique_coefficients": bool(rank == 4),
                "coefficients": coefficients.tolist() if rank == 4 else None,
                "selection_rmse_volts": float(np.sqrt(np.mean((prediction - sy)**2))), "fits": 1}
    baseline_seconds = perf_counter()-started
    if telemetry is not None:
        telemetry.update(engine_seconds=engine_seconds, baseline_seconds=baseline_seconds,
                         scope="local solver calls; excludes shared normalization and feature construction")
    return {"grammar": GRAMMAR, "policy": asdict(policy), "dataset_digest": dataset.fingerprint,
            "evaluation_role": "selection", "final_evaluation": "NOT_RUN", "decision": decision,
            "selected": encode(minimal[0]) if len(minimal) == 1 else None,
            "minimal_supports": [list(c.feature_names) for c in minimal],
            "candidates": [encode(c) for c in candidates], "baseline": baseline,
            "budget": {"calibration_rows": len(x), "selection_rows": len(sx), "engine_supports_attempted": 7,
                       "engine_full_rank_fits": len(candidates), "baseline_fits": 1}}


def bundle(telemetry=None):
    from .fixtures import CASES, build
    cases = {}
    for name in CASES:
        timing = {}
        data = build(name)
        cases[name] = {"input": data, "result": evaluate(**data, telemetry=timing)}
        if telemetry is not None:
            telemetry[name] = timing
    return {"schema": "forge.rediscovery.l3.development/1", "blindfold": False,
            "assumptions": "Public noiseless synthetic controls; fixed 1 A/1 V normalization; 0.01 V development RMSE bar, not statistical significance or noise; selection only; no physical/final validation",
            "source": {**{p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")},
                       "normalization_helper": hashlib.sha256(Path(normalized.__code__.co_filename).read_bytes()).hexdigest()},
            "cases": cases}


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
            raise ReplayMismatch("L3 development record differs")
        print("EXACT")
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(canonical_bytes(actual).decode()+"\n")
        print(str(args.output.resolve()))
    print(json.dumps({"record_digest": digest(actual), "telemetry": telemetry}), file=sys.stderr)


if __name__ == "__main__":
    main()
