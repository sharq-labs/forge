"""K2 scored multi-parameter Arrhenius inference runner.

This runner executes the frozen K2 preregistration without changing its science:

1. evaluate the synthetic truth through the K1.5 admission boundary;
2. generate the primary seeded observations;
3. build the 61x61 forward grid exactly once;
4. score the multi-condition and weak C2-only reference posteriors;
5. reuse the same forward grid for all 20 recovery datasets;
6. report the preregistered acceptance criteria and deterministic replay;
7. optionally perform the expensive full serial-vs-parallel CPU parity check.

The LLM is not a numerical source here. Every reported scientific number is
computed by the repository from frozen declarations, admitted solver results and
NumPy posterior arithmetic.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.kinetics_k2.k2_config import (  # noqa: E402
    MULTI_CONDITION_IDS,
    PARAMETER_NAMES,
    PRIMARY_SEED,
    RECOVERY_SEEDS,
    REFERENCE_GRID_SIZE,
    TRUTH_COORDINATES,
    WEAK_CONDITION_IDS,
    parameter_grid,
)
from experiments.kinetics_k2.k2_forward import (  # noqa: E402
    ForwardBuildResult,
    ForwardBuildStats,
    build_forward_table_with_stats,
    observation_set_from_truth_means,
    truth_means,
)
from src.engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    ObservationSet,
    PosteriorGrid,
    gaussian_grid_posterior,
)


PREREG_COMMIT = "824a4167a7ebead813dc3b023b9ace31742e3789"
K15_FROZEN_COMMIT = "f479777d67295355fbf3fcf7877cd834d30eee99"


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _jsonable_truth_means(means: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value.to_dict() for key, value in means.items()}


def _save_forward_cache(
    path: Path,
    table: AdmittedForwardTable,
    stats: ForwardBuildStats,
    *,
    source_commit: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    audit = {
        "schema": "k2_forward_cache_v1",
        "source_commit": source_commit,
        "prereg_commit": PREREG_COMMIT,
        "grid_size": REFERENCE_GRID_SIZE,
        "parameter_names": list(table.parameter_names),
        "observation_keys": list(table.observation_keys),
        "condition_ids": list(MULTI_CONDITION_IDS),
        "admission_refs": [list(row) for row in table.admission_refs],
        "rejection_reasons": list(table.rejection_reasons),
        "stats": stats.to_dict(),
    }
    np.savez_compressed(
        path,
        points=table.points,
        values=table.values,
        admissible_mask=table.admissible_mask,
        audit_json=np.asarray(json.dumps(audit, sort_keys=True, separators=(",", ":"))),
    )


def _load_forward_cache(
    path: Path,
    observations: ObservationSet,
    *,
    source_commit: str,
) -> ForwardBuildResult:
    if not path.exists():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=False) as payload:
        points = np.asarray(payload["points"], dtype=np.float64)
        values = np.asarray(payload["values"], dtype=np.float64)
        mask = np.asarray(payload["admissible_mask"], dtype=bool)
        audit = json.loads(str(payload["audit_json"].item()))

    if audit.get("schema") != "k2_forward_cache_v1":
        raise RuntimeError("forward cache schema is not K2 v1")
    if audit.get("source_commit") != source_commit:
        raise RuntimeError(
            "forward cache was produced by a different source commit; refusing "
            "stale scientific numerics"
        )
    if audit.get("prereg_commit") != PREREG_COMMIT:
        raise RuntimeError("forward cache is not bound to the frozen K2 preregistration")
    if tuple(audit.get("parameter_names", ())) != PARAMETER_NAMES:
        raise RuntimeError("forward cache parameter names do not match frozen K2")
    if tuple(audit.get("condition_ids", ())) != MULTI_CONDITION_IDS:
        raise RuntimeError("forward cache condition declarations do not match frozen K2")
    if tuple(audit.get("observation_keys", ())) != observations.keys:
        raise RuntimeError("forward cache observation columns do not match K2 observations")

    frozen_points = parameter_grid()
    if not np.array_equal(points, frozen_points):
        raise RuntimeError("forward cache grid does not match the frozen 61x61 K2 grid")

    table = AdmittedForwardTable(
        parameter_names=PARAMETER_NAMES,
        observation_keys=observations.keys,
        points=points,
        values=values,
        admissible_mask=mask,
        admission_refs=tuple(
            tuple(row) for row in audit.get("admission_refs", ())
        ),
        rejection_reasons=tuple(audit.get("rejection_reasons", ())),
    )
    raw_stats = audit.get("stats", {})
    stats = ForwardBuildStats(
        parameter_points=int(raw_stats["parameter_points"]),
        condition_attempts=int(raw_stats["condition_attempts"]),
        condition_admitted=int(raw_stats["condition_admitted"]),
        condition_rejected=int(raw_stats["condition_rejected"]),
        point_admitted=int(raw_stats["point_admitted"]),
        point_rejected=int(raw_stats["point_rejected"]),
        workers=int(raw_stats["workers"]),
    )
    return ForwardBuildResult(table=table, stats=stats)


def _contains(interval: list[float] | tuple[float, float], truth: float) -> bool:
    return float(interval[0]) <= float(truth) <= float(interval[1])


def _posterior_checks(
    multi: PosteriorGrid,
    weak: PosteriorGrid,
) -> dict[str, Any]:
    multi_summary = multi.summary()
    weak_summary = weak.summary()
    truth_log, truth_e = TRUTH_COORDINATES

    weight_sum = float(np.sum(multi.weights))
    a2 = bool(
        np.any(multi.admissible_mask)
        and np.all(np.isfinite(multi.weights))
        and np.all(multi.weights >= 0.0)
        and abs(weight_sum - 1.0) <= 1.0e-12
    )

    intervals = multi_summary["credible_95"]
    a3 = _contains(intervals[0], truth_log) and _contains(intervals[1], truth_e)

    means = multi_summary["mean"]
    log_error = abs(float(means[0]) - truth_log)
    e_error = abs(float(means[1]) - truth_e)
    a4 = log_error <= 0.50 and e_error <= 250.0

    multi_det = float(multi_summary["covariance_determinant"])
    weak_det = float(weak_summary["covariance_determinant"])
    det_ratio = (
        multi_det / weak_det
        if math.isfinite(multi_det) and math.isfinite(weak_det) and weak_det > 0.0
        else float("nan")
    )
    a5 = bool(math.isfinite(det_ratio) and multi_det >= 0.0 and det_ratio <= 0.50)

    multi_std = [float(value) for value in multi_summary["std"]]
    weak_std = [float(value) for value in weak_summary["std"]]
    multi_geo = math.sqrt(multi_std[0] * multi_std[1])
    weak_geo = math.sqrt(weak_std[0] * weak_std[1])
    ridge_ratio = multi_geo / weak_geo if weak_geo > 0.0 else float("nan")
    a6 = bool(math.isfinite(ridge_ratio) and ridge_ratio <= 0.80)

    replay = gaussian_grid_posterior(
        _CURRENT_FORWARD_TABLE[0], _CURRENT_PRIMARY_OBSERVATIONS[0]
    )
    a8 = bool(
        np.array_equal(multi.weights, replay.weights)
        and np.array_equal(multi.log_likelihood, replay.log_likelihood)
    )

    return {
        "A2_finite_posterior": {
            "pass": a2,
            "weight_sum": weight_sum,
        },
        "A3_truth_in_95pct_marginals": {
            "pass": bool(a3),
            "truth": [truth_log, truth_e],
            "credible_95": intervals,
        },
        "A4_point_accuracy": {
            "pass": bool(a4),
            "absolute_error": [log_error, e_error],
            "limits": [0.50, 250.0],
        },
        "A5_identifiability_gain": {
            "pass": a5,
            "multi_covariance_determinant": multi_det,
            "weak_covariance_determinant": weak_det,
            "ratio": det_ratio,
            "maximum_ratio": 0.50,
        },
        "A6_ridge_reduction": {
            "pass": a6,
            "multi_geometric_mean_std": multi_geo,
            "weak_geometric_mean_std": weak_geo,
            "ratio": ridge_ratio,
            "maximum_ratio": 0.80,
        },
        "A8_deterministic_replay": {
            "pass": a8,
        },
    }


# These single-element holders keep _posterior_checks pure in its public
# signature while letting A8 re-score the exact current table/observation pair.
# They are process-local runner state, never scientific configuration.
_CURRENT_FORWARD_TABLE: list[AdmittedForwardTable] = []
_CURRENT_PRIMARY_OBSERVATIONS: list[ObservationSet] = []


def _recovery_check(
    table: AdmittedForwardTable,
    means: Mapping[str, Any],
) -> dict[str, Any]:
    covered = [0, 0]
    rows: list[dict[str, Any]] = []
    for seed in RECOVERY_SEEDS:
        observations = observation_set_from_truth_means(
            means,
            seed=seed,
            condition_ids=MULTI_CONDITION_IDS,
            dataset_id=f"K2-recovery-{seed}",
        )
        posterior = gaussian_grid_posterior(table, observations)
        summary = posterior.summary()
        intervals = summary["credible_95"]
        contains = [
            _contains(intervals[0], TRUTH_COORDINATES[0]),
            _contains(intervals[1], TRUTH_COORDINATES[1]),
        ]
        for index, item in enumerate(contains):
            covered[index] += int(item)
        rows.append(
            {
                "seed": int(seed),
                "contains_truth": contains,
                "mean": summary["mean"],
                "credible_95": intervals,
            }
        )
    return {
        "pass": covered[0] >= 15 and covered[1] >= 15,
        "coverage_counts": covered,
        "required_each": 15,
        "datasets": len(RECOVERY_SEEDS),
        "runs": rows,
    }


def _cpu_parity(
    reference: AdmittedForwardTable,
    observations: ObservationSet,
    points: np.ndarray,
    *,
    progress_every: int,
) -> dict[str, Any]:
    print("\nCPU parity: building full serial reference (expensive, one-time)...")
    started = time.perf_counter()

    def progress(done: int, total: int) -> None:
        if progress_every > 0 and (done % progress_every == 0 or done == total):
            print(f"  serial parity {done:,}/{total:,} points", flush=True)

    serial = build_forward_table_with_stats(
        points,
        observations,
        condition_ids=MULTI_CONDITION_IDS,
        workers=1,
        progress_callback=progress,
    )
    wall = time.perf_counter() - started

    mask_equal = np.array_equal(reference.admissible_mask, serial.table.admissible_mask)
    both = reference.admissible_mask & serial.table.admissible_mask
    if np.any(both):
        ref_values = reference.values[both]
        serial_values = serial.table.values[both]
        scale = np.maximum(np.maximum(np.abs(ref_values), np.abs(serial_values)), 1.0e-300)
        relative = np.abs(ref_values - serial_values) / scale
        max_relative = float(np.max(relative))
    else:
        max_relative = 0.0
    values_pass = bool(max_relative <= 1.0e-6)

    reference_posterior = gaussian_grid_posterior(reference, observations)
    serial_posterior = gaussian_grid_posterior(serial.table, observations)
    posterior_max_abs = float(
        np.max(np.abs(reference_posterior.weights - serial_posterior.weights))
    )
    posterior_pass = posterior_max_abs <= 1.0e-12
    return {
        "pass": bool(mask_equal and values_pass and posterior_pass),
        "mask_equal": bool(mask_equal),
        "max_relative_forward_difference": max_relative,
        "forward_tolerance": 1.0e-6,
        "posterior_max_absolute_difference": posterior_max_abs,
        "posterior_tolerance": 1.0e-12,
        "serial_stats": serial.stats.to_dict(),
        "serial_wall_seconds": wall,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workers",
        default="auto",
        help="Forward process count or 'auto'; hardware names are never used.",
    )
    parser.add_argument(
        "--forward-cache",
        default="experiments/kinetics_k2/artifacts/k2_forward_61x61.npz",
    )
    parser.add_argument(
        "--reuse-forward-cache",
        action="store_true",
        help="Reuse only a cache produced by this exact source commit/prereg/grid.",
    )
    parser.add_argument(
        "--cpu-parity",
        action="store_true",
        help="Also build the full serial grid for A9; intentionally expensive.",
    )
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--output",
        default="experiments/kinetics_k2/artifacts/k2_results.json",
    )
    args = parser.parse_args()

    source_commit = _git_head()
    print("K2 scored reference inference")
    print(f"source commit: {source_commit}")
    print(f"prereg commit: {PREREG_COMMIT}")
    print(f"grid: {REFERENCE_GRID_SIZE}x{REFERENCE_GRID_SIZE} = {REFERENCE_GRID_SIZE ** 2:,} points")

    print("\nA1 / synthetic truth: evaluating all frozen conditions through K1.5...")
    truth_started = time.perf_counter()
    means = truth_means(condition_ids=MULTI_CONDITION_IDS)
    truth_wall = time.perf_counter() - truth_started
    primary = observation_set_from_truth_means(
        means,
        seed=PRIMARY_SEED,
        condition_ids=MULTI_CONDITION_IDS,
        dataset_id="K2-primary",
    )
    print(f"truth conditions admitted in {truth_wall:.3f}s")

    points = parameter_grid()
    cache_path = (_REPO_ROOT / args.forward_cache).resolve()
    forward_started = time.perf_counter()
    if args.reuse_forward_cache:
        print(f"\nForward grid: loading verified cache {cache_path}")
        build = _load_forward_cache(
            cache_path,
            primary,
            source_commit=source_commit,
        )
        forward_wall = 0.0
    else:
        print(f"\nForward grid: evaluating {len(points):,} parameter points...")

        def progress(done: int, total: int) -> None:
            if args.progress_every > 0 and (
                done % args.progress_every == 0 or done == total
            ):
                elapsed = time.perf_counter() - forward_started
                rate = done / elapsed if elapsed > 0.0 else 0.0
                remaining = (total - done) / rate if rate > 0.0 else float("nan")
                print(
                    f"  {done:,}/{total:,} points | {rate:,.2f} point/s | "
                    f"ETA {remaining / 60.0:,.1f} min",
                    flush=True,
                )

        build = build_forward_table_with_stats(
            points,
            primary,
            condition_ids=MULTI_CONDITION_IDS,
            workers=args.workers,
            progress_callback=progress,
        )
        forward_wall = time.perf_counter() - forward_started
        _save_forward_cache(
            cache_path,
            build.table,
            build.stats,
            source_commit=source_commit,
        )
        print(f"forward cache saved: {cache_path}")

    table = build.table
    print(
        f"forward: {build.stats.point_admitted:,}/{build.stats.parameter_points:,} "
        f"points admitted | {build.stats.condition_admitted:,}/"
        f"{build.stats.condition_attempts:,} condition evaluations admitted | "
        f"workers={build.stats.workers} | wall={forward_wall:.2f}s"
    )

    _CURRENT_FORWARD_TABLE[:] = [table]
    _CURRENT_PRIMARY_OBSERVATIONS[:] = [primary]

    print("\nPosterior: scoring multi-condition and weak C2 control...")
    score_started = time.perf_counter()
    multi = gaussian_grid_posterior(table, primary)
    weak_observations = primary.subset(
        WEAK_CONDITION_IDS,
        dataset_id="K2-primary-weak-C2",
    )
    weak = gaussian_grid_posterior(table, weak_observations)
    posterior_checks = _posterior_checks(multi, weak)
    recovery = _recovery_check(table, means)
    score_wall = time.perf_counter() - score_started

    criteria: dict[str, Any] = {
        "A1_truth_condition_admissibility": {
            "pass": True,
            "conditions": list(MULTI_CONDITION_IDS),
        },
        **posterior_checks,
        "A7_repeated_recovery": recovery,
        "A9_cpu_execution_parity": {
            "pass": None,
            "status": "not_run",
        },
        "A10_gpu_parity_if_enabled": {
            "pass": None,
            "status": "not_enabled",
        },
    }

    if args.cpu_parity:
        criteria["A9_cpu_execution_parity"] = _cpu_parity(
            table,
            primary,
            points,
            progress_every=args.progress_every,
        )

    required_without_a9 = (
        "A1_truth_condition_admissibility",
        "A2_finite_posterior",
        "A3_truth_in_95pct_marginals",
        "A4_point_accuracy",
        "A5_identifiability_gain",
        "A6_ridge_reduction",
        "A7_repeated_recovery",
        "A8_deterministic_replay",
    )
    science_pass = all(bool(criteria[name]["pass"]) for name in required_without_a9)
    a9_pass = criteria["A9_cpu_execution_parity"]["pass"]
    if science_pass and a9_pass is True:
        overall = "PASS_PENDING_OPTIONAL_GPU_OR_FREEZE_REVIEW"
    elif science_pass and a9_pass is None:
        overall = "SCIENCE_PASS_A9_NOT_RUN"
    else:
        overall = "FAIL_OR_FINDING"

    result = {
        "experiment_id": "K2",
        "status": overall,
        "prereg_commit": PREREG_COMMIT,
        "k15_frozen_commit": K15_FROZEN_COMMIT,
        "source_commit": source_commit,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "truth_coordinates": list(TRUTH_COORDINATES),
        "truth_means": _jsonable_truth_means(means),
        "primary_observations": primary.to_dict(),
        "forward": {
            "stats": build.stats.to_dict(),
            "wall_seconds": forward_wall,
            "cache": str(cache_path),
        },
        "multi_posterior": multi.summary(),
        "weak_c2_posterior": weak.summary(),
        "criteria": criteria,
        "timing": {
            "truth_wall_seconds": truth_wall,
            "posterior_and_recovery_wall_seconds": score_wall,
        },
        "claim_boundary": (
            "synthetic computational recovery study only; no physical reactor "
            "measurement or experimental validation is claimed"
        ),
    }

    output = (_REPO_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print("\nPrimary multi-condition posterior")
    print(json.dumps(multi.summary(), indent=2))
    print("\nWeak C2 posterior")
    print(json.dumps(weak.summary(), indent=2))
    print("\nAcceptance")
    for name, payload in criteria.items():
        print(f"{name}: {payload.get('pass')}" + (f" ({payload.get('status')})" if payload.get("status") else ""))
    print(f"\nSTATUS: {overall}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
