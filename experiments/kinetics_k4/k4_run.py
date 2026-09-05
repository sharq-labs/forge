"""K4 scored model-adequacy and model-competition runner.

M1 is the frozen Arrhenius CSTR posterior from K2/K3.1.  M2 is the separately
declared constant-rate approximation fitted to the same C1/C2/C3 observations.
Both are scored only on the frozen H1/H2 observations using exact finite-mixture
predictive CDFs and log densities.

The runner never converts a score difference into a probability that a model is
true.  K4 evidence is bounded to this declared synthetic study.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.kinetics_k2.k2_config import (  # noqa: E402
    MULTI_CONDITION_IDS,
    PRIMARY_SEED,
    RECOVERY_SEEDS,
)
from experiments.kinetics_k2.k2_forward import (  # noqa: E402
    ForwardBuildStats,
    observation_set_from_truth_means,
    truth_means,
)
from experiments.kinetics_k3.k3_config import (  # noqa: E402
    HOLDOUT_IDS,
    PRIMARY_HOLDOUT_SEED,
    REPEATED_HOLDOUT_SEEDS,
    sigma_for_observable,
)
from experiments.kinetics_k3.k3_forward import (  # noqa: E402
    holdout_observation_set_from_truth_means,
    holdout_template_observations,
    holdout_truth_means,
)
from experiments.kinetics_k3.k3_run import (  # noqa: E402
    _load_holdout_cache,
    _load_k2_forward_cache,
    _specs,
)
from experiments.kinetics_k4.k4_config import (  # noqa: E402
    ARRHENIUS_MODEL_REF,
    CONSTANT_RATE_MODEL_REF,
    CREDIBLE_MASS,
    K3_CACHE_PRODUCER_COMMIT,
    MAX_UNSUPPORTED_POSTERIOR_MASS,
    PREREG_COMMIT,
    constant_rate_grid,
    k4_ensemble_twin,
)
from experiments.kinetics_k4.k4_forward import (  # noqa: E402
    CONSTANT_RATE_PARAMETER_NAMES,
    ConstantRateForwardBuildResult,
    build_constant_rate_forward_table_with_stats,
)
from src.engcore.adequacy import (  # noqa: E402
    PredictiveObservationAssessment,
    assess_predictive_observation,
    compare_log_predictive_scores,
)
from src.engcore.domains.kinetics.cstr.alternative_inference import (  # noqa: E402
    CONSTANT_RATE_INFERENCE_ADAPTER_ID,
)
from src.engcore.domains.kinetics.cstr.alternatives import (  # noqa: E402
    CONSTANT_RATE_CSTR_MODEL,
)
from src.engcore.domains.kinetics.cstr.problem import (  # noqa: E402
    CSTR_MODEL,
)
from src.engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    ObservationSet,
    PosteriorGrid,
    gaussian_grid_posterior,
)
from src.engcore.scientific import (  # noqa: E402
    ModelType,
    ModelValidationStatus,
    Quantity,
    TwinReference,
)
from src.engcore.uq import (  # noqa: E402
    PredictiveAdmissionAudit,
    PredictiveObservableSpec,
    condition_posterior_on_predictive_admission,
)

K4_SCHEMA = "kinetics_k4_model_adequacy_competition_results_v1"
M2_TRAIN_CACHE_SCHEMA = "k4_constant_rate_training_forward_cache_v1"
M2_HOLDOUT_CACHE_SCHEMA = "k4_constant_rate_holdout_forward_cache_v1"


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


def _save_m2_cache(
    path: Path,
    build: ConstantRateForwardBuildResult,
    *,
    schema: str,
    condition_ids: Sequence[str],
    source_commit: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = build.table
    audit = {
        "schema": schema,
        "producer_commit": source_commit,
        "k4_prereg_commit": PREREG_COMMIT,
        "model": CONSTANT_RATE_MODEL_REF.to_dict(),
        "adapter_id": CONSTANT_RATE_INFERENCE_ADAPTER_ID,
        "parameter_names": list(table.parameter_names),
        "observation_keys": list(table.observation_keys),
        "condition_ids": list(condition_ids),
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


def _load_m2_cache(
    path: Path,
    observations: ObservationSet,
    *,
    schema: str,
    condition_ids: Sequence[str],
    source_commit: str,
) -> ConstantRateForwardBuildResult:
    if not path.exists():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=False) as payload:
        points = np.asarray(payload["points"], dtype=np.float64)
        values = np.asarray(payload["values"], dtype=np.float64)
        mask = np.asarray(payload["admissible_mask"], dtype=bool)
        audit = json.loads(str(payload["audit_json"].item()))

    if audit.get("schema") != schema:
        raise RuntimeError("K4 M2 cache schema mismatch")
    if audit.get("producer_commit") != source_commit:
        raise RuntimeError("K4 M2 cache was produced by a different source commit")
    if audit.get("k4_prereg_commit") != PREREG_COMMIT:
        raise RuntimeError("K4 M2 cache is not bound to the frozen preregistration")
    if audit.get("model") != CONSTANT_RATE_MODEL_REF.to_dict():
        raise RuntimeError("K4 M2 cache model binding differs from the competitor")
    if audit.get("adapter_id") != CONSTANT_RATE_INFERENCE_ADAPTER_ID:
        raise RuntimeError("K4 M2 cache adapter identity differs")
    if tuple(audit.get("parameter_names", ())) != CONSTANT_RATE_PARAMETER_NAMES:
        raise RuntimeError("K4 M2 cache parameter names differ")
    if tuple(audit.get("condition_ids", ())) != tuple(condition_ids):
        raise RuntimeError("K4 M2 cache condition ids differ")
    if tuple(audit.get("observation_keys", ())) != observations.keys:
        raise RuntimeError("K4 M2 cache observation columns differ")
    frozen_points = constant_rate_grid()
    if not np.array_equal(points, frozen_points):
        raise RuntimeError("K4 M2 cache parameter support differs from frozen grid")

    table = AdmittedForwardTable(
        parameter_names=CONSTANT_RATE_PARAMETER_NAMES,
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
    return ConstantRateForwardBuildResult(table=table, stats=stats)


def _load_or_build_m2(
    path: Path,
    observations: ObservationSet,
    *,
    schema: str,
    condition_ids: Sequence[str],
    source_commit: str,
    workers: str | int,
    progress_every: int,
    rebuild: bool,
) -> tuple[ConstantRateForwardBuildResult, float, bool]:
    if path.exists() and not rebuild:
        try:
            return (
                _load_m2_cache(
                    path,
                    observations,
                    schema=schema,
                    condition_ids=condition_ids,
                    source_commit=source_commit,
                ),
                0.0,
                True,
            )
        except Exception as exc:
            print(f"existing M2 cache refused ({exc}); rebuilding", flush=True)

    points = constant_rate_grid()
    started = time.perf_counter()

    def progress(done: int, total: int) -> None:
        if progress_every > 0 and (done % progress_every == 0 or done == total):
            print(f"  M2 forward {done:,}/{total:,} points", flush=True)

    build = build_constant_rate_forward_table_with_stats(
        points,
        observations,
        condition_ids=condition_ids,
        workers=workers,
        source_commit=source_commit,
        progress_callback=progress,
    )
    wall = time.perf_counter() - started
    _save_m2_cache(
        path,
        build,
        schema=schema,
        condition_ids=condition_ids,
        source_commit=source_commit,
    )
    return build, wall, False


def _condition(
    posterior: PosteriorGrid,
    table: AdmittedForwardTable,
) -> tuple[PosteriorGrid, PredictiveAdmissionAudit]:
    result = condition_posterior_on_predictive_admission(
        posterior,
        table,
        maximum_unsupported_mass=MAX_UNSUPPORTED_POSTERIOR_MASS,
    )
    return result.posterior, result.audit


def _assess_model(
    posterior: PosteriorGrid,
    table: AdmittedForwardTable,
    specs: tuple[PredictiveObservableSpec, ...],
    observations: ObservationSet,
    *,
    model,
    twin: TwinReference,
    source_prefix: str,
    source_commit: str,
) -> tuple[PredictiveObservationAssessment, ...]:
    by_key = {item.key: item.value for item in observations.observations}
    if tuple(by_key) != tuple(spec.observation_key for spec in specs):
        raise RuntimeError("K4 held-out observation order differs from predictive schema")
    result: list[PredictiveObservationAssessment] = []
    for spec in specs:
        result.append(
            assess_predictive_observation(
                posterior,
                table,
                spec,
                by_key[spec.observation_key],
                twin=twin,
                model=model,
                source_ref=(
                    f"{source_prefix}|k4-prereg:{PREREG_COMMIT}|"
                    f"source:{source_commit}|heldout:{observations.dataset_id}"
                ),
                credible_mass=CREDIBLE_MASS,
            )
        )
    return tuple(result)


def _assessment_map(
    assessments: Sequence[PredictiveObservationAssessment],
) -> dict[str, dict[str, Any]]:
    return {item.observation_key: item.to_dict() for item in assessments}


def _canonical_primary(
    *,
    m1: Sequence[PredictiveObservationAssessment],
    m2: Sequence[PredictiveObservationAssessment],
    m1_audit: PredictiveAdmissionAudit,
    m2_audit: PredictiveAdmissionAudit,
    comparison,
) -> str:
    payload = {
        "m1": [item.to_dict() for item in m1],
        "m2": [item.to_dict() for item in m2],
        "m1_support": m1_audit.to_dict(),
        "m2_support": m2_audit.to_dict(),
        "comparison": comparison.to_dict(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _adequacy_math_selfcheck() -> bool:
    points = np.asarray([[0.0]], dtype=np.float64)
    posterior = PosteriorGrid(
        parameter_names=("p",),
        points=points,
        weights=np.asarray([1.0], dtype=np.float64),
        log_likelihood=np.asarray([0.0], dtype=np.float64),
        admissible_mask=np.asarray([True]),
        dataset_id="k4-selfcheck-fit",
    )
    table = AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=("H:y",),
        points=points,
        values=np.asarray([[10.0]], dtype=np.float64),
        admissible_mask=np.asarray([True]),
        admission_refs=(("selfcheck",),),
        rejection_reasons=("",),
    )
    spec = PredictiveObservableSpec(
        "H:y", "kelvin", Quantity(2.0, "kelvin")
    )
    result = assess_predictive_observation(
        posterior,
        table,
        spec,
        Quantity(10.0, "kelvin"),
        twin=TwinReference("k4-selfcheck", "1"),
        model=ARRHENIUS_MODEL_REF,
        source_ref="k4-selfcheck",
    )
    expected_log_density = -math.log(2.0 * math.sqrt(2.0 * math.pi))
    return bool(
        abs(result.predictive_cdf - 0.5) <= 1.0e-15
        and abs(result.two_sided_tail_probability - 1.0) <= 1.0e-15
        and abs(result.log_predictive_density - expected_log_density) <= 1.0e-15
        and abs(result.standardized_residual) <= 1.0e-15
        and result.covered_by_central_interval
    )


def _model_specific(
    assessments: Sequence[PredictiveObservationAssessment],
    expected_model,
    expected_dataset: str,
) -> bool:
    return all(
        item.model == expected_model
        and item.posterior_dataset_id == expected_dataset
        and item.source_ref
        for item in assessments
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", default="auto")
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--rebuild-m2-caches", action="store_true")
    parser.add_argument(
        "--k2-forward-cache",
        default="experiments/kinetics_k2/artifacts/k2_forward_61x61.npz",
    )
    parser.add_argument(
        "--m1-holdout-cache",
        default="experiments/kinetics_k3/artifacts/k3_holdout_forward_61x61.npz",
    )
    parser.add_argument(
        "--m2-training-cache",
        default="experiments/kinetics_k4/artifacts/k4_m2_training_121.npz",
    )
    parser.add_argument(
        "--m2-holdout-cache",
        default="experiments/kinetics_k4/artifacts/k4_m2_holdout_121.npz",
    )
    parser.add_argument(
        "--output",
        default="experiments/kinetics_k4/artifacts/k4_results.json",
    )
    args = parser.parse_args()

    source_commit = _git_head()
    twin = k4_ensemble_twin()
    print("K4 scored model adequacy and model competition")
    print(f"source commit: {source_commit}")
    print(f"prereg commit: {PREREG_COMMIT}")
    print(f"M1: {ARRHENIUS_MODEL_REF.model_id}@{ARRHENIUS_MODEL_REF.version}")
    print(f"M2: {CONSTANT_RATE_MODEL_REF.model_id}@{CONSTANT_RATE_MODEL_REF.version}")
    print(f"M2 grid: {len(constant_rate_grid())} points")

    # ---- Shared frozen synthetic evidence ------------------------------
    print("\nReconstructing frozen training and holdout evidence...")
    k2_means = truth_means(condition_ids=MULTI_CONDITION_IDS)
    primary_training = observation_set_from_truth_means(
        k2_means,
        seed=PRIMARY_SEED,
        condition_ids=MULTI_CONDITION_IDS,
        dataset_id="K2-primary",
    )
    m1_training_table, m1_training_stats = _load_k2_forward_cache(
        (_REPO_ROOT / args.k2_forward_cache).resolve(),
        primary_training,
    )

    h_truth = holdout_truth_means(condition_ids=HOLDOUT_IDS)
    holdout_template = holdout_template_observations(h_truth)
    specs = _specs(holdout_template)
    m1_holdout_build = _load_holdout_cache(
        (_REPO_ROOT / args.m1_holdout_cache).resolve(),
        holdout_template,
        source_commit=K3_CACHE_PRODUCER_COMMIT,
    )
    m1_holdout_table = m1_holdout_build.table
    primary_holdout = holdout_observation_set_from_truth_means(
        h_truth,
        seed=PRIMARY_HOLDOUT_SEED,
        condition_ids=HOLDOUT_IDS,
        dataset_id="K4-primary-holdout",
    )
    print(
        f"M1 frozen training admitted: {m1_training_stats.point_admitted:,}/"
        f"{m1_training_stats.parameter_points:,}; H1/H2: "
        f"{m1_holdout_build.stats.point_admitted:,}/"
        f"{m1_holdout_build.stats.parameter_points:,}"
    )

    # ---- M2 training/predictive grids ----------------------------------
    print("\nM2 training grid C1/C2/C3...")
    m2_train_build, m2_train_wall, train_reused = _load_or_build_m2(
        (_REPO_ROOT / args.m2_training_cache).resolve(),
        primary_training,
        schema=M2_TRAIN_CACHE_SCHEMA,
        condition_ids=MULTI_CONDITION_IDS,
        source_commit=source_commit,
        workers=args.workers,
        progress_every=args.progress_every,
        rebuild=bool(args.rebuild_m2_caches),
    )
    print(
        f"M2 training: {m2_train_build.stats.point_admitted}/"
        f"{m2_train_build.stats.parameter_points} points admitted | "
        f"workers={m2_train_build.stats.workers} | wall={m2_train_wall:.2f}s | "
        f"cache_reused={train_reused}"
    )

    print("\nM2 predictive grid H1/H2...")
    m2_holdout_build, m2_holdout_wall, holdout_reused = _load_or_build_m2(
        (_REPO_ROOT / args.m2_holdout_cache).resolve(),
        holdout_template,
        schema=M2_HOLDOUT_CACHE_SCHEMA,
        condition_ids=HOLDOUT_IDS,
        source_commit=source_commit,
        workers=args.workers,
        progress_every=args.progress_every,
        rebuild=bool(args.rebuild_m2_caches),
    )
    print(
        f"M2 holdout: {m2_holdout_build.stats.point_admitted}/"
        f"{m2_holdout_build.stats.parameter_points} points admitted | "
        f"workers={m2_holdout_build.stats.workers} | wall={m2_holdout_wall:.2f}s | "
        f"cache_reused={holdout_reused}"
    )

    m2_training_table = m2_train_build.table
    m2_holdout_table = m2_holdout_build.table

    # ---- Primary fit / score -------------------------------------------
    m1_primary_raw = gaussian_grid_posterior(m1_training_table, primary_training)
    m2_primary_raw = gaussian_grid_posterior(m2_training_table, primary_training)
    m1_primary, m1_primary_audit = _condition(m1_primary_raw, m1_holdout_table)
    m2_primary, m2_primary_audit = _condition(m2_primary_raw, m2_holdout_table)
    print(f"\nM1 primary unsupported predictive mass: {m1_primary_audit.unsupported_mass:.3e}")
    print(f"M2 primary unsupported predictive mass: {m2_primary_audit.unsupported_mass:.3e}")

    m1_primary_assess = _assess_model(
        m1_primary,
        m1_holdout_table,
        specs,
        primary_holdout,
        model=ARRHENIUS_MODEL_REF,
        twin=twin.reference,
        source_prefix="K4-primary-M1",
        source_commit=source_commit,
    )
    m2_primary_assess = _assess_model(
        m2_primary,
        m2_holdout_table,
        specs,
        primary_holdout,
        model=CONSTANT_RATE_MODEL_REF,
        twin=twin.reference,
        source_prefix="K4-primary-M2",
        source_commit=source_commit,
    )
    primary_comparison = compare_log_predictive_scores(
        ARRHENIUS_MODEL_REF,
        m1_primary_assess,
        CONSTANT_RATE_MODEL_REF,
        m2_primary_assess,
    )
    print(
        f"primary log score M1={primary_comparison.score_a:.6f} "
        f"M2={primary_comparison.score_b:.6f} "
        f"delta={primary_comparison.delta_a_minus_b:.6f}"
    )

    # ---- Repeated paired evaluation -----------------------------------
    if len(RECOVERY_SEEDS) != len(REPEATED_HOLDOUT_SEEDS):
        raise RuntimeError("K4 paired inference/holdout seed vectors differ")

    m1_coverage = {spec.observation_key: 0 for spec in specs}
    m1_residual_squares = {spec.observation_key: [] for spec in specs}
    support_audits: list[PredictiveAdmissionAudit] = [
        m1_primary_audit,
        m2_primary_audit,
    ]
    repeated_rows: list[dict[str, Any]] = []
    m1_wins = 0
    delta_sum = 0.0

    print("\nRepeated paired held-out model competition...")
    for index, (inference_seed, holdout_seed) in enumerate(
        zip(RECOVERY_SEEDS, REPEATED_HOLDOUT_SEEDS), 1
    ):
        training = observation_set_from_truth_means(
            k2_means,
            seed=inference_seed,
            condition_ids=MULTI_CONDITION_IDS,
            dataset_id=f"K2-recovery-{inference_seed}",
        )
        holdout = holdout_observation_set_from_truth_means(
            h_truth,
            seed=holdout_seed,
            condition_ids=HOLDOUT_IDS,
            dataset_id=f"K4-holdout-{holdout_seed}",
        )

        m1_raw = gaussian_grid_posterior(m1_training_table, training)
        m2_raw = gaussian_grid_posterior(m2_training_table, training)
        m1_post, m1_audit = _condition(m1_raw, m1_holdout_table)
        m2_post, m2_audit = _condition(m2_raw, m2_holdout_table)
        support_audits.extend((m1_audit, m2_audit))

        m1_assess = _assess_model(
            m1_post,
            m1_holdout_table,
            specs,
            holdout,
            model=ARRHENIUS_MODEL_REF,
            twin=twin.reference,
            source_prefix=f"K4-recovery-{inference_seed}-M1",
            source_commit=source_commit,
        )
        m2_assess = _assess_model(
            m2_post,
            m2_holdout_table,
            specs,
            holdout,
            model=CONSTANT_RATE_MODEL_REF,
            twin=twin.reference,
            source_prefix=f"K4-recovery-{inference_seed}-M2",
            source_commit=source_commit,
        )
        comparison = compare_log_predictive_scores(
            ARRHENIUS_MODEL_REF,
            m1_assess,
            CONSTANT_RATE_MODEL_REF,
            m2_assess,
        )
        delta_sum += comparison.delta_a_minus_b
        if comparison.delta_a_minus_b > 0.0:
            m1_wins += 1

        for item in m1_assess:
            m1_coverage[item.observation_key] += int(item.covered_by_central_interval)
            m1_residual_squares[item.observation_key].append(
                item.standardized_residual * item.standardized_residual
            )

        repeated_rows.append(
            {
                "inference_seed": int(inference_seed),
                "holdout_seed": int(holdout_seed),
                "training_dataset_id": training.dataset_id,
                "holdout_dataset_id": holdout.dataset_id,
                "M1": {
                    "model": ARRHENIUS_MODEL_REF.to_dict(),
                    "support_conditioning": m1_audit.to_dict(),
                    "assessments": _assessment_map(m1_assess),
                },
                "M2": {
                    "model": CONSTANT_RATE_MODEL_REF.to_dict(),
                    "support_conditioning": m2_audit.to_dict(),
                    "assessments": _assessment_map(m2_assess),
                },
                "comparison": comparison.to_dict(),
            }
        )
        print(
            f"  pair {index:02d}/20 | delta={comparison.delta_a_minus_b:+.6f} | "
            f"M1_unsupported={m1_audit.unsupported_mass:.2e} | "
            f"M2_unsupported={m2_audit.unsupported_mass:.2e}",
            flush=True,
        )

    m1_rms = {
        key: math.sqrt(float(np.mean(values)))
        for key, values in m1_residual_squares.items()
    }

    # ---- Deterministic primary replay ---------------------------------
    replay_m1, replay_m1_audit = _condition(m1_primary_raw, m1_holdout_table)
    replay_m2, replay_m2_audit = _condition(m2_primary_raw, m2_holdout_table)
    replay_m1_assess = _assess_model(
        replay_m1,
        m1_holdout_table,
        specs,
        primary_holdout,
        model=ARRHENIUS_MODEL_REF,
        twin=twin.reference,
        source_prefix="K4-primary-M1",
        source_commit=source_commit,
    )
    replay_m2_assess = _assess_model(
        replay_m2,
        m2_holdout_table,
        specs,
        primary_holdout,
        model=CONSTANT_RATE_MODEL_REF,
        twin=twin.reference,
        source_prefix="K4-primary-M2",
        source_commit=source_commit,
    )
    replay_comparison = compare_log_predictive_scores(
        ARRHENIUS_MODEL_REF,
        replay_m1_assess,
        CONSTANT_RATE_MODEL_REF,
        replay_m2_assess,
    )
    deterministic_replay = _canonical_primary(
        m1=m1_primary_assess,
        m2=m2_primary_assess,
        m1_audit=m1_primary_audit,
        m2_audit=m2_primary_audit,
        comparison=primary_comparison,
    ) == _canonical_primary(
        m1=replay_m1_assess,
        m2=replay_m2_assess,
        m1_audit=replay_m1_audit,
        m2_audit=replay_m2_audit,
        comparison=replay_comparison,
    )

    # ---- Acceptance ----------------------------------------------------
    a1 = _adequacy_math_selfcheck()
    a2 = bool(
        CONSTANT_RATE_CSTR_MODEL.model_type is ModelType.APPROXIMATION
        and CONSTANT_RATE_CSTR_MODEL.validation_status
        is ModelValidationStatus.UNVALIDATED
        and CONSTANT_RATE_MODEL_REF != ARRHENIUS_MODEL_REF
        and m2_train_build.table.parameter_names == CONSTANT_RATE_PARAMETER_NAMES
    )
    training_ids = set(MULTI_CONDITION_IDS)
    holdout_ids = set(HOLDOUT_IDS)
    a3 = bool(
        training_ids.isdisjoint(holdout_ids)
        and all(not key.startswith("H1:") and not key.startswith("H2:") for key in primary_training.keys)
        and all(key.startswith("H1:") or key.startswith("H2:") for key in holdout_template.keys)
    )
    a4 = bool(
        len(h_truth) == 4
        and all(audit.unsupported_mass <= MAX_UNSUPPORTED_POSTERIOR_MASS for audit in support_audits)
        and all(
            abs(audit.supported_mass + audit.unsupported_mass - 1.0) <= 1.0e-12
            for audit in support_audits
        )
    )
    a5 = all(count >= 15 for count in m1_coverage.values())
    a6 = all(math.isfinite(value) and value <= 1.75 for value in m1_rms.values())
    a7 = all(
        math.isfinite(value)
        for value in (
            primary_comparison.score_a,
            primary_comparison.score_b,
            primary_comparison.delta_a_minus_b,
        )
    )
    a8 = bool(m1_wins >= 14 and math.isfinite(delta_sum) and delta_sum > 0.0)

    model_specific_primary = bool(
        _model_specific(m1_primary_assess, ARRHENIUS_MODEL_REF, "K2-primary")
        and _model_specific(m2_primary_assess, CONSTANT_RATE_MODEL_REF, "K2-primary")
        and primary_comparison.model_a == ARRHENIUS_MODEL_REF
        and primary_comparison.model_b == CONSTANT_RATE_MODEL_REF
        and m1_primary_audit.posterior_dataset_id == "K2-primary"
        and m2_primary_audit.posterior_dataset_id == "K2-primary"
    )
    model_specific_repeated = all(
        row["M1"]["model"] == ARRHENIUS_MODEL_REF.to_dict()
        and row["M2"]["model"] == CONSTANT_RATE_MODEL_REF.to_dict()
        and row["comparison"]["model_a"] == ARRHENIUS_MODEL_REF.to_dict()
        and row["comparison"]["model_b"] == CONSTANT_RATE_MODEL_REF.to_dict()
        for row in repeated_rows
    )
    a9 = bool(model_specific_primary and model_specific_repeated)
    a10 = bool(deterministic_replay)
    a11 = bool(
        CSTR_MODEL.validation_status is ModelValidationStatus.SELF_CONSISTENT
        and CONSTANT_RATE_CSTR_MODEL.validation_status
        is ModelValidationStatus.UNVALIDATED
    )

    acceptance = {
        "A1_shared_adequacy_math": {"pass": bool(a1)},
        "A2_competitor_explicit_versioned": {
            "pass": bool(a2),
            "model": CONSTANT_RATE_MODEL_REF.to_dict(),
            "adapter_id": CONSTANT_RATE_INFERENCE_ADAPTER_ID,
        },
        "A3_fit_predict_separation": {
            "pass": bool(a3),
            "training_conditions": list(MULTI_CONDITION_IDS),
            "holdout_conditions": list(HOLDOUT_IDS),
        },
        "A4_numerical_admission": {
            "pass": bool(a4),
            "support_audits_checked": len(support_audits),
            "maximum_unsupported_mass": MAX_UNSUPPORTED_POSTERIOR_MASS,
            "maximum_observed_unsupported_mass": max(
                audit.unsupported_mass for audit in support_audits
            ),
        },
        "A5_arrhenius_repeated_predictive_adequacy": {
            "pass": bool(a5),
            "coverage_counts": m1_coverage,
            "required_each": 15,
            "datasets": 20,
        },
        "A6_arrhenius_standardized_residual_behavior": {
            "pass": bool(a6),
            "rms_by_observable": m1_rms,
            "maximum_rms": 1.75,
        },
        "A7_primary_comparison_finite": {
            "pass": bool(a7),
            "comparison": primary_comparison.to_dict(),
        },
        "A8_repeated_competition": {
            "pass": bool(a8),
            "M1_wins": int(m1_wins),
            "required_M1_wins": 14,
            "paired_datasets": 20,
            "sum_delta_M1_minus_M2": float(delta_sum),
        },
        "A9_model_specific_evidence": {"pass": bool(a9)},
        "A10_deterministic_replay": {"pass": bool(a10)},
        "A11_claim_boundary": {
            "pass": bool(a11),
            "M1_global_validation_status": CSTR_MODEL.validation_status.value,
            "M2_global_validation_status": CONSTANT_RATE_CSTR_MODEL.validation_status.value,
            "statement": (
                "predictive score preference is study-bounded evidence, not a "
                "truth probability, physical validation or universal superiority claim"
            ),
        },
        "A12_regression_safety": {
            "pass": None,
            "status": "pending_full_regression",
        },
    }
    science_pass = all(
        acceptance[key]["pass"]
        for key in acceptance
        if key != "A12_regression_safety"
    )

    payload = {
        "schema": K4_SCHEMA,
        "status": "SCIENCE_PASS_A12_PENDING" if science_pass else "SCIENCE_FAIL",
        "source_commit": source_commit,
        "k4_prereg_commit": PREREG_COMMIT,
        "twin": twin.to_dict(),
        "models": {
            "M1": ARRHENIUS_MODEL_REF.to_dict(),
            "M2": CONSTANT_RATE_MODEL_REF.to_dict(),
        },
        "claim_boundary": (
            "K4 compares out-of-sample predictive adequacy for this synthetic "
            "study only; no model probability or physical validation is claimed"
        ),
        "forward": {
            "M1_training": m1_training_stats.to_dict(),
            "M1_holdout": m1_holdout_build.stats.to_dict(),
            "M2_training": {
                **m2_train_build.stats.to_dict(),
                "wall_seconds_telemetry": m2_train_wall,
                "cache_reused": train_reused,
            },
            "M2_holdout": {
                **m2_holdout_build.stats.to_dict(),
                "wall_seconds_telemetry": m2_holdout_wall,
                "cache_reused": holdout_reused,
            },
        },
        "primary": {
            "training_dataset_id": primary_training.dataset_id,
            "holdout_dataset_id": primary_holdout.dataset_id,
            "M1": {
                "posterior": m1_primary.summary(),
                "support_conditioning": m1_primary_audit.to_dict(),
                "assessments": _assessment_map(m1_primary_assess),
            },
            "M2": {
                "posterior": m2_primary.summary(),
                "support_conditioning": m2_primary_audit.to_dict(),
                "assessments": _assessment_map(m2_primary_assess),
            },
            "comparison": primary_comparison.to_dict(),
        },
        "repeated": repeated_rows,
        "acceptance": acceptance,
    }

    output = (_REPO_ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print("\nAcceptance")
    for key, value in acceptance.items():
        print(f"{key}: {value['pass']}")
    print(f"\nSTATUS: {payload['status']}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
