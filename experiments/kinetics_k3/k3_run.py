"""K3 scored posterior-predictive uncertainty runner.

The runner reuses the frozen K2 posterior support, evaluates the preregistered
H1/H2 holdouts through the K1.5 admissibility boundary, propagates the K2
posterior into predictive space, and scores U1-U9. U10 (full repository
regression) is deliberately a post-run freeze gate.

No LLM-produced numerical value enters this file's scientific outputs.
"""

from __future__ import annotations

import argparse
import json
import math
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
    WEAK_CONDITION_IDS,
    parameter_grid,
)
from experiments.kinetics_k2.k2_forward import (  # noqa: E402
    ForwardBuildStats,
    observation_set_from_truth_means,
    truth_means,
)
from experiments.kinetics_k3.k3_config import (  # noqa: E402
    HOLDOUT_IDS,
    K2_PREREG_COMMIT,
    K2_SCIENTIFIC_SOURCE_COMMIT,
    PREREG_COMMIT,
    PRIMARY_HOLDOUT_SEED,
    REPEATED_HOLDOUT_SEEDS,
    k3_reference_twin,
    sigma_for_observable,
)
from experiments.kinetics_k3.k3_forward import (  # noqa: E402
    HoldoutForwardBuildResult,
    build_holdout_forward_table_with_stats,
    holdout_observation_set_from_truth_means,
    holdout_template_observations,
    holdout_truth_means,
)
from src.engcore.domains.kinetics.cstr.problem import (  # noqa: E402
    CA_FINAL_METRIC,
    CSTR_MODEL,
    T_FINAL_METRIC,
)
from src.engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    ObservationSet,
    PosteriorGrid,
    gaussian_grid_posterior,
)
from src.engcore.scientific import ModelReference, Quantity  # noqa: E402
from src.engcore.uq import (  # noqa: E402
    PredictiveObservableSpec,
    QuantifiedPredictiveResult,
    posterior_predictive_uq,
)

K3_SCHEMA = "kinetics_k3_quantified_uq_results_v1"
K2_CACHE_SCHEMA = "k2_forward_cache_v1"
K3_HOLDOUT_CACHE_SCHEMA = "k3_holdout_forward_cache_v1"
CREDIBLE_MASS = 0.95


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


def _load_k2_forward_cache(
    path: Path,
    observations: ObservationSet,
) -> tuple[AdmittedForwardTable, ForwardBuildStats]:
    """Load only the frozen K2 scientific-source cache.

    K3 must not rebuild or silently reinterpret K2's fitted forward evidence.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=False) as payload:
        points = np.asarray(payload["points"], dtype=np.float64)
        values = np.asarray(payload["values"], dtype=np.float64)
        mask = np.asarray(payload["admissible_mask"], dtype=bool)
        audit = json.loads(str(payload["audit_json"].item()))

    if audit.get("schema") != K2_CACHE_SCHEMA:
        raise RuntimeError("K2 cache schema is not the frozen v1 format")
    if audit.get("source_commit") != K2_SCIENTIFIC_SOURCE_COMMIT:
        raise RuntimeError(
            "K2 cache was not produced by the frozen K2 scientific source "
            f"{K2_SCIENTIFIC_SOURCE_COMMIT}"
        )
    if audit.get("prereg_commit") != K2_PREREG_COMMIT:
        raise RuntimeError("K2 cache is not bound to the frozen K2 preregistration")
    if int(audit.get("grid_size", -1)) != REFERENCE_GRID_SIZE:
        raise RuntimeError("K2 cache grid size differs from the frozen declaration")
    if tuple(audit.get("parameter_names", ())) != PARAMETER_NAMES:
        raise RuntimeError("K2 cache parameter names differ from the frozen declaration")
    if tuple(audit.get("condition_ids", ())) != MULTI_CONDITION_IDS:
        raise RuntimeError("K2 cache condition ids differ from the frozen declaration")
    if tuple(audit.get("observation_keys", ())) != observations.keys:
        raise RuntimeError("K2 cache observation columns do not match K3's K2 dataset")

    frozen_points = parameter_grid()
    if not np.array_equal(points, frozen_points):
        raise RuntimeError("K2 cache parameter support differs from the frozen grid")

    table = AdmittedForwardTable(
        parameter_names=PARAMETER_NAMES,
        observation_keys=observations.keys,
        points=points,
        values=values,
        admissible_mask=mask,
        admission_refs=tuple(tuple(row) for row in audit.get("admission_refs", ())),
        rejection_reasons=tuple(audit.get("rejection_reasons", ())),
    )
    raw = audit.get("stats", {})
    stats = ForwardBuildStats(
        parameter_points=int(raw["parameter_points"]),
        condition_attempts=int(raw["condition_attempts"]),
        condition_admitted=int(raw["condition_admitted"]),
        condition_rejected=int(raw["condition_rejected"]),
        point_admitted=int(raw["point_admitted"]),
        point_rejected=int(raw["point_rejected"]),
        workers=int(raw["workers"]),
    )
    return table, stats


def _save_holdout_cache(
    path: Path,
    build: HoldoutForwardBuildResult,
    *,
    source_commit: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = build.table
    audit = {
        "schema": K3_HOLDOUT_CACHE_SCHEMA,
        "producer_commit": source_commit,
        "k3_prereg_commit": PREREG_COMMIT,
        "k2_scientific_source_commit": K2_SCIENTIFIC_SOURCE_COMMIT,
        "parameter_names": list(table.parameter_names),
        "observation_keys": list(table.observation_keys),
        "condition_ids": list(HOLDOUT_IDS),
        "admission_refs": [list(row) for row in table.admission_refs],
        "rejection_reasons": list(table.rejection_reasons),
        "stats": build.stats.to_dict(),
    }
    np.savez_compressed(
        path,
        points=table.points,
        values=table.values,
        admissible_mask=table.admissible_mask,
        audit_json=np.asarray(json.dumps(audit, sort_keys=True, separators=(",", ":"))),
    )


def _load_holdout_cache(
    path: Path,
    observations: ObservationSet,
    *,
    source_commit: str,
) -> HoldoutForwardBuildResult:
    if not path.exists():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=False) as payload:
        points = np.asarray(payload["points"], dtype=np.float64)
        values = np.asarray(payload["values"], dtype=np.float64)
        mask = np.asarray(payload["admissible_mask"], dtype=bool)
        audit = json.loads(str(payload["audit_json"].item()))

    if audit.get("schema") != K3_HOLDOUT_CACHE_SCHEMA:
        raise RuntimeError("holdout cache schema is not K3 v1")
    if audit.get("producer_commit") != source_commit:
        raise RuntimeError(
            "holdout cache was produced by a different implementation commit; "
            "refusing stale predictive numerics"
        )
    if audit.get("k3_prereg_commit") != PREREG_COMMIT:
        raise RuntimeError("holdout cache is not bound to the frozen K3 preregistration")
    if audit.get("k2_scientific_source_commit") != K2_SCIENTIFIC_SOURCE_COMMIT:
        raise RuntimeError("holdout cache is not bound to the frozen K2 science")
    if tuple(audit.get("parameter_names", ())) != PARAMETER_NAMES:
        raise RuntimeError("holdout cache parameter names differ")
    if tuple(audit.get("condition_ids", ())) != HOLDOUT_IDS:
        raise RuntimeError("holdout cache conditions differ from K3")
    if tuple(audit.get("observation_keys", ())) != observations.keys:
        raise RuntimeError("holdout cache observation columns differ from K3")
    frozen_points = parameter_grid()
    if not np.array_equal(points, frozen_points):
        raise RuntimeError("holdout cache parameter support differs from K2")

    table = AdmittedForwardTable(
        parameter_names=PARAMETER_NAMES,
        observation_keys=observations.keys,
        points=points,
        values=values,
        admissible_mask=mask,
        admission_refs=tuple(tuple(row) for row in audit.get("admission_refs", ())),
        rejection_reasons=tuple(audit.get("rejection_reasons", ())),
    )
    raw = audit.get("stats", {})
    stats = ForwardBuildStats(
        parameter_points=int(raw["parameter_points"]),
        condition_attempts=int(raw["condition_attempts"]),
        condition_admitted=int(raw["condition_admitted"]),
        condition_rejected=int(raw["condition_rejected"]),
        point_admitted=int(raw["point_admitted"]),
        point_rejected=int(raw["point_rejected"]),
        workers=int(raw["workers"]),
    )
    return HoldoutForwardBuildResult(table=table, stats=stats)


def _quantity_value(q: Quantity, unit: str) -> float:
    return float(q.magnitude_in(unit))


def _contains(result: QuantifiedPredictiveResult, truth: Quantity, *, total: bool) -> bool:
    interval = result.total_interval if total else result.epistemic_interval
    assert interval.lower is not None and interval.upper is not None
    unit = result.mean.units
    value = truth.magnitude_in(unit)
    return (
        interval.lower.magnitude_in(unit) <= value <= interval.upper.magnitude_in(unit)
    )


def _specs(template: ObservationSet) -> tuple[PredictiveObservableSpec, ...]:
    specs: list[PredictiveObservableSpec] = []
    for obs in template.observations:
        specs.append(
            PredictiveObservableSpec(
                observation_key=obs.key,
                unit=obs.value.units,
                observation_sigma=obs.sigma,
            )
        )
    return tuple(specs)


def _uq_all(
    posterior: PosteriorGrid,
    holdout_table: AdmittedForwardTable,
    specs: tuple[PredictiveObservableSpec, ...],
    *,
    source_prefix: str,
) -> dict[str, QuantifiedPredictiveResult]:
    twin = k3_reference_twin()
    model = ModelReference(CSTR_MODEL.model_id, CSTR_MODEL.version)
    return {
        spec.observation_key: posterior_predictive_uq(
            posterior,
            holdout_table,
            spec,
            twin=twin.reference,
            model=model,
            source_ref=(
                f"{source_prefix}|k3-prereg:{PREREG_COMMIT}|"
                f"k2-source:{K2_SCIENTIFIC_SOURCE_COMMIT}"
            ),
            credible_mass=CREDIBLE_MASS,
        )
        for spec in specs
    }


def _canonical_results(results: Mapping[str, QuantifiedPredictiveResult]) -> str:
    payload = {key: results[key].to_dict() for key in sorted(results)}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _finite_result(result: QuantifiedPredictiveResult) -> bool:
    quantities = (
        result.mean,
        result.epistemic_standard_uncertainty,
        result.total_standard_uncertainty,
    )
    if not all(math.isfinite(q.magnitude) and q.magnitude >= 0.0 for q in quantities[1:]):
        return False
    if not math.isfinite(result.mean.magnitude):
        return False
    for interval in (result.epistemic_interval, result.total_interval):
        if interval.lower is None or interval.upper is None:
            return False
        lower = interval.lower.magnitude_in(result.mean.units)
        upper = interval.upper.magnitude_in(result.mean.units)
        if not (math.isfinite(lower) and math.isfinite(upper) and lower <= upper):
            return False
        if not interval.is_quantified:
            return False
    return True


def _variance_decomposition(
    result: QuantifiedPredictiveResult,
    sigma: Quantity,
) -> tuple[bool, dict[str, float]]:
    unit = result.mean.units
    e_var = result.epistemic_variance
    t_var = result.total_variance
    noise_var = sigma.magnitude_in(unit) ** 2
    error = abs(t_var - (e_var + noise_var))
    tolerance = 1.0e-12 * max(1.0, t_var)
    return error <= tolerance, {
        "epistemic_variance": e_var,
        "noise_variance": noise_var,
        "total_variance": t_var,
        "absolute_error": error,
        "tolerance": tolerance,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", default="auto")
    parser.add_argument(
        "--k2-forward-cache",
        default="experiments/kinetics_k2/artifacts/k2_forward_61x61.npz",
    )
    parser.add_argument(
        "--holdout-forward-cache",
        default="experiments/kinetics_k3/artifacts/k3_holdout_forward_61x61.npz",
    )
    parser.add_argument("--reuse-holdout-cache", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--output",
        default="experiments/kinetics_k3/artifacts/k3_results.json",
    )
    args = parser.parse_args()

    source_commit = _git_head()
    print("K3 scored posterior-predictive uncertainty")
    print(f"source commit: {source_commit}")
    print(f"prereg commit: {PREREG_COMMIT}")
    print(f"frozen K2 source: {K2_SCIENTIFIC_SOURCE_COMMIT}")
    print(f"grid: {REFERENCE_GRID_SIZE}x{REFERENCE_GRID_SIZE} = {REFERENCE_GRID_SIZE ** 2:,} points")

    # ---- frozen K2 inference source ---------------------------------
    print("\nK2 inference source: reconstructing frozen primary observations...")
    k2_truth_started = time.perf_counter()
    k2_means = truth_means(condition_ids=MULTI_CONDITION_IDS)
    primary_obs = observation_set_from_truth_means(
        k2_means,
        seed=PRIMARY_SEED,
        condition_ids=MULTI_CONDITION_IDS,
        dataset_id="K2-primary",
    )
    k2_truth_wall = time.perf_counter() - k2_truth_started
    k2_cache_path = (_REPO_ROOT / args.k2_forward_cache).resolve()
    k2_table, k2_stats = _load_k2_forward_cache(k2_cache_path, primary_obs)
    multi = gaussian_grid_posterior(k2_table, primary_obs)
    weak_obs = primary_obs.subset(WEAK_CONDITION_IDS, dataset_id="K2-primary-weak-C2")
    weak = gaussian_grid_posterior(k2_table, weak_obs)
    print(
        f"K2 cache verified: {int(np.count_nonzero(k2_table.admissible_mask)):,}/"
        f"{len(k2_table.admissible_mask):,} points admitted | truth wall={k2_truth_wall:.3f}s"
    )

    # ---- U1 and holdout predictive support --------------------------
    print("\nU1 / holdout truth: evaluating H1/H2 through K1.5...")
    holdout_truth_started = time.perf_counter()
    h_truth = holdout_truth_means(condition_ids=HOLDOUT_IDS)
    holdout_truth_wall = time.perf_counter() - holdout_truth_started
    u1 = len(h_truth) == 4 and all(
        f"{condition_id}:{observable}" in h_truth
        for condition_id in HOLDOUT_IDS
        for observable in (CA_FINAL_METRIC, T_FINAL_METRIC)
    )
    print(f"holdout truth admitted in {holdout_truth_wall:.3f}s")

    template = holdout_template_observations(h_truth)
    points = parameter_grid()
    holdout_cache_path = (_REPO_ROOT / args.holdout_forward_cache).resolve()
    holdout_started = time.perf_counter()
    if args.reuse_holdout_cache:
        print(f"\nHoldout grid: loading verified cache {holdout_cache_path}")
        holdout_build = _load_holdout_cache(
            holdout_cache_path,
            template,
            source_commit=source_commit,
        )
        holdout_wall = 0.0
    else:
        print(f"\nHoldout grid: evaluating {len(points):,} parameter points across H1/H2...")

        def progress(done: int, total: int) -> None:
            if args.progress_every > 0 and (done % args.progress_every == 0 or done == total):
                print(f"  holdout {done:,}/{total:,} points", flush=True)

        holdout_build = build_holdout_forward_table_with_stats(
            points,
            template,
            condition_ids=HOLDOUT_IDS,
            workers=args.workers,
            progress_callback=progress,
        )
        holdout_wall = time.perf_counter() - holdout_started
        _save_holdout_cache(
            holdout_cache_path,
            holdout_build,
            source_commit=source_commit,
        )
        print(f"holdout cache saved: {holdout_cache_path}")

    h_table = holdout_build.table
    print(
        f"holdout: {holdout_build.stats.point_admitted:,}/{holdout_build.stats.parameter_points:,} "
        f"points admitted | {holdout_build.stats.condition_admitted:,}/"
        f"{holdout_build.stats.condition_attempts:,} condition evaluations admitted | "
        f"workers={holdout_build.stats.workers} | wall={holdout_wall:.2f}s"
    )

    specs = _specs(template)
    primary_uq = _uq_all(
        multi,
        h_table,
        specs,
        source_prefix="K3-primary",
    )
    weak_uq = _uq_all(
        weak,
        h_table,
        specs,
        source_prefix="K3-primary-weak-C2",
    )

    # ---- U2 ----------------------------------------------------------
    u2_details = {key: _finite_result(result) for key, result in primary_uq.items()}
    u2 = all(u2_details.values()) and len(u2_details) == 4

    # ---- U3 ----------------------------------------------------------
    u3_details: dict[str, Any] = {}
    u3_flags: list[bool] = []
    for key, result in primary_uq.items():
        observable = key.split(":", 1)[1]
        passed, detail = _variance_decomposition(result, sigma_for_observable(observable))
        u3_details[key] = {"pass": passed, **detail}
        u3_flags.append(passed)
    u3 = all(u3_flags) and len(u3_flags) == 4

    # ---- U4 ----------------------------------------------------------
    u4_details = {
        key: _contains(result, h_truth[key], total=False)
        for key, result in primary_uq.items()
    }
    u4 = all(u4_details.values()) and len(u4_details) == 4

    # ---- U5/U6 repeated coverage ------------------------------------
    latent_counts = {key: 0 for key in primary_uq}
    noisy_counts = {key: 0 for key in primary_uq}
    repeated_rows: list[dict[str, Any]] = []

    if len(RECOVERY_SEEDS) != len(REPEATED_HOLDOUT_SEEDS):
        raise RuntimeError("K3 prereg paired seed vectors differ in length")

    print("\nRepeated predictive coverage: 20 frozen inference/holdout pairs...")
    for index, (inference_seed, holdout_seed) in enumerate(
        zip(RECOVERY_SEEDS, REPEATED_HOLDOUT_SEEDS), 1
    ):
        repeated_obs = observation_set_from_truth_means(
            k2_means,
            seed=inference_seed,
            condition_ids=MULTI_CONDITION_IDS,
            dataset_id=f"K2-recovery-{inference_seed}",
        )
        posterior = gaussian_grid_posterior(k2_table, repeated_obs)
        uq = _uq_all(
            posterior,
            h_table,
            specs,
            source_prefix=f"K3-recovery-{inference_seed}",
        )
        noisy = holdout_observation_set_from_truth_means(
            h_truth,
            seed=holdout_seed,
            condition_ids=HOLDOUT_IDS,
            dataset_id=f"K3-holdout-{holdout_seed}",
        )
        noisy_by_key = {item.key: item.value for item in noisy.observations}
        latent_flags: dict[str, bool] = {}
        noisy_flags: dict[str, bool] = {}
        for key, result in uq.items():
            latent_ok = _contains(result, h_truth[key], total=False)
            noisy_ok = _contains(result, noisy_by_key[key], total=True)
            latent_flags[key] = latent_ok
            noisy_flags[key] = noisy_ok
            latent_counts[key] += int(latent_ok)
            noisy_counts[key] += int(noisy_ok)
        repeated_rows.append(
            {
                "inference_seed": int(inference_seed),
                "holdout_seed": int(holdout_seed),
                "latent_coverage": latent_flags,
                "noisy_predictive_coverage": noisy_flags,
            }
        )
        print(f"  repeated {index:02d}/20", flush=True)

    u5 = all(count >= 15 for count in latent_counts.values())
    u6 = all(count >= 15 for count in noisy_counts.values())

    # ---- U7 ----------------------------------------------------------
    u7_details: dict[str, Any] = {}
    u7_flags: list[bool] = []
    for key in primary_uq:
        multi_std = _quantity_value(
            primary_uq[key].epistemic_standard_uncertainty,
            primary_uq[key].mean.units,
        )
        weak_std = _quantity_value(
            weak_uq[key].epistemic_standard_uncertainty,
            weak_uq[key].mean.units,
        )
        ratio = multi_std / weak_std if weak_std > 0.0 else float("inf")
        passed = math.isfinite(ratio) and ratio <= 0.80
        u7_details[key] = {
            "pass": passed,
            "multi_epistemic_std": multi_std,
            "weak_epistemic_std": weak_std,
            "ratio": ratio,
            "maximum_ratio": 0.80,
        }
        u7_flags.append(passed)
    u7 = all(u7_flags) and len(u7_flags) == 4

    # ---- U8 ----------------------------------------------------------
    replay_uq = _uq_all(
        multi,
        h_table,
        specs,
        source_prefix="K3-primary",
    )
    primary_canonical = _canonical_results(primary_uq)
    replay_canonical = _canonical_results(replay_uq)
    u8 = primary_canonical == replay_canonical

    # ---- U9 ----------------------------------------------------------
    twin = k3_reference_twin()
    expected_model = (CSTR_MODEL.model_id, CSTR_MODEL.version)
    u9_details: dict[str, bool] = {}
    for key, result in primary_uq.items():
        u9_details[key] = bool(
            result.twin == twin.reference
            and result.posterior_dataset_id == "K2-primary"
            and result.model.key == expected_model
            and result.observation_key == key
            and result.source_ref
            and result.epistemic_interval.method == "weighted_posterior_predictive_discrete"
            and result.total_interval.method == "weighted_posterior_predictive_gaussian_mixture"
        )
    u9 = all(u9_details.values()) and len(u9_details) == 4

    acceptance = {
        "U1_truth_holdout_admissibility": {"pass": bool(u1)},
        "U2_finite_quantified_outputs": {"pass": bool(u2), "by_observable": u2_details},
        "U3_exact_variance_decomposition": {"pass": bool(u3), "by_observable": u3_details},
        "U4_primary_latent_truth_coverage": {"pass": bool(u4), "by_observable": u4_details},
        "U5_repeated_latent_coverage": {
            "pass": bool(u5),
            "coverage_counts": latent_counts,
            "required_each": 15,
            "datasets": 20,
        },
        "U6_repeated_noisy_predictive_coverage": {
            "pass": bool(u6),
            "coverage_counts": noisy_counts,
            "required_each": 15,
            "datasets": 20,
        },
        "U7_information_gain_survives_propagation": {
            "pass": bool(u7),
            "by_observable": u7_details,
        },
        "U8_deterministic_replay": {"pass": bool(u8)},
        "U9_twin_bound_scientific_output": {"pass": bool(u9), "by_observable": u9_details},
        "U10_regression_safety": {"pass": None, "status": "pending_full_regression"},
    }

    science_pass = all(
        acceptance[f"U{i}_{suffix}"]["pass"]
        for i, suffix in (
            (1, "truth_holdout_admissibility"),
            (2, "finite_quantified_outputs"),
            (3, "exact_variance_decomposition"),
            (4, "primary_latent_truth_coverage"),
            (5, "repeated_latent_coverage"),
            (6, "repeated_noisy_predictive_coverage"),
            (7, "information_gain_survives_propagation"),
            (8, "deterministic_replay"),
            (9, "twin_bound_scientific_output"),
        )
    )
    status = "SCIENCE_PASS_U10_PENDING" if science_pass else "SCIENCE_FAIL"

    payload = {
        "schema": K3_SCHEMA,
        "status": status,
        "scientific_source_commit": source_commit,
        "prereg_commit": PREREG_COMMIT,
        "k2_scientific_source_commit": K2_SCIENTIFIC_SOURCE_COMMIT,
        "k2_prereg_commit": K2_PREREG_COMMIT,
        "twin": twin.to_dict(),
        "k2_forward_stats": k2_stats.to_dict(),
        "holdout_forward_stats": holdout_build.stats.to_dict(),
        "timing_seconds": {
            "k2_truth": k2_truth_wall,
            "holdout_truth": holdout_truth_wall,
            "holdout_forward": holdout_wall,
        },
        "holdout_truth_means": {key: h_truth[key].to_dict() for key in sorted(h_truth)},
        "primary": {key: primary_uq[key].to_dict() for key in sorted(primary_uq)},
        "weak_control": {key: weak_uq[key].to_dict() for key in sorted(weak_uq)},
        "repeated": repeated_rows,
        "acceptance": acceptance,
    }

    output_path = (_REPO_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print("\nPrimary posterior-predictive UQ")
    for key in sorted(primary_uq):
        item = primary_uq[key]
        assert item.epistemic_interval.lower is not None
        assert item.epistemic_interval.upper is not None
        assert item.total_interval.lower is not None
        assert item.total_interval.upper is not None
        unit = item.mean.units
        print(
            f"  {key}: mean={item.mean.magnitude_in(unit):.12g} {unit} | "
            f"epi_std={item.epistemic_standard_uncertainty.magnitude_in(unit):.12g} | "
            f"epi95=[{item.epistemic_interval.lower.magnitude_in(unit):.12g}, "
            f"{item.epistemic_interval.upper.magnitude_in(unit):.12g}] | "
            f"total_std={item.total_standard_uncertainty.magnitude_in(unit):.12g} | "
            f"total95=[{item.total_interval.lower.magnitude_in(unit):.12g}, "
            f"{item.total_interval.upper.magnitude_in(unit):.12g}]"
        )

    print("\nAcceptance")
    for name, record in acceptance.items():
        value = record["pass"]
        print(f"  {name}: {value}")
    print(f"\nSTATUS: {status}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
