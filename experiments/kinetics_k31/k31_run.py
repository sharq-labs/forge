"""K3.1 scored predictive-admission conditioning runner.

This successor preserves the original K3 failure and reuses its frozen H1/H2
predictive cache.  Every posterior is first audited against predictive
admission.  Unsupported mass above the preregistered budget fails closed;
otherwise UQ is explicitly conditional on predictive admission.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.kinetics_k2.k2_config import (  # noqa: E402
    MULTI_CONDITION_IDS,
    PRIMARY_SEED,
    RECOVERY_SEEDS,
    REFERENCE_GRID_SIZE,
    WEAK_CONDITION_IDS,
)
from experiments.kinetics_k2.k2_forward import (  # noqa: E402
    observation_set_from_truth_means,
    truth_means,
)
from experiments.kinetics_k3.k3_config import (  # noqa: E402
    HOLDOUT_IDS,
    K2_SCIENTIFIC_SOURCE_COMMIT,
    PRIMARY_HOLDOUT_SEED,
    REPEATED_HOLDOUT_SEEDS,
    k3_reference_twin,
    sigma_for_observable,
)
from experiments.kinetics_k3.k3_forward import (  # noqa: E402
    holdout_observation_set_from_truth_means,
    holdout_template_observations,
    holdout_truth_means,
)
from experiments.kinetics_k3.k3_run import (  # noqa: E402
    CREDIBLE_MASS,
    PREREG_COMMIT as K3_PREREG_COMMIT,
    _canonical_results,
    _contains,
    _finite_result,
    _load_holdout_cache,
    _load_k2_forward_cache,
    _quantity_value,
    _specs,
    _variance_decomposition,
)
from src.engcore.domains.kinetics.cstr.problem import (  # noqa: E402
    CA_FINAL_METRIC,
    CSTR_MODEL,
    T_FINAL_METRIC,
)
from src.engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    PosteriorGrid,
    gaussian_grid_posterior,
)
from src.engcore.scientific import ModelReference  # noqa: E402
from src.engcore.uq import (  # noqa: E402
    PredictiveAdmissionAudit,
    PredictiveObservableSpec,
    QuantifiedPredictiveResult,
    UQProblemError,
    condition_posterior_on_predictive_admission,
    posterior_predictive_uq,
)

K31_SCHEMA = "kinetics_k31_predictive_admission_conditioning_results_v1"
K31_PREREG_COMMIT = "bfb2439fdea769779ea0aaec747353708146add6"
K3_SCORED_SOURCE_COMMIT = "68fcc6a6a9ea305016119a86238aa9329ef33b9c"
MAX_UNSUPPORTED_POSTERIOR_MASS = 1.0e-12


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


def _uq_all(
    posterior: PosteriorGrid,
    table: AdmittedForwardTable,
    specs: tuple[PredictiveObservableSpec, ...],
    *,
    source_prefix: str,
) -> dict[str, QuantifiedPredictiveResult]:
    twin = k3_reference_twin()
    model = ModelReference(CSTR_MODEL.model_id, CSTR_MODEL.version)
    source = (
        f"{source_prefix}|k31-prereg:{K31_PREREG_COMMIT}|"
        f"k3-prereg:{K3_PREREG_COMMIT}|k2-source:{K2_SCIENTIFIC_SOURCE_COMMIT}"
    )
    return {
        spec.observation_key: posterior_predictive_uq(
            posterior,
            table,
            spec,
            twin=twin.reference,
            model=model,
            source_ref=source,
            credible_mass=CREDIBLE_MASS,
        )
        for spec in specs
    }


def _audit_ok(audit: PredictiveAdmissionAudit) -> bool:
    return bool(
        abs((audit.supported_mass + audit.unsupported_mass) - 1.0) <= 1.0e-12
        and audit.unsupported_mass <= MAX_UNSUPPORTED_POSTERIOR_MASS
    )


def _canonical_bundle(
    results: Mapping[str, QuantifiedPredictiveResult],
    audit: PredictiveAdmissionAudit,
) -> str:
    payload = {
        "results": {key: results[key].to_dict() for key in sorted(results)},
        "support_conditioning": audit.to_dict(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _policy_selfcheck() -> bool:
    """Scored pure-logic check matching K3.1 S3."""
    from src.engcore.inference import AdmittedForwardTable

    points = np.asarray([[0.0], [1.0]], dtype=np.float64)
    table = AdmittedForwardTable(
        parameter_names=("x",),
        observation_keys=("H:y",),
        points=points,
        values=np.asarray([[1.0], [2.0]], dtype=np.float64),
        admissible_mask=np.asarray([True, False]),
        admission_refs=(("ok",), ()),
        rejection_reasons=("", "controlled rejection"),
    )

    zero = PosteriorGrid(
        parameter_names=("x",),
        points=points,
        weights=np.asarray([1.0, 0.0]),
        log_likelihood=np.asarray([0.0, -np.inf]),
        admissible_mask=np.asarray([True, True]),
        dataset_id="k31-selfcheck-zero",
    )
    z = condition_posterior_on_predictive_admission(
        zero,
        table,
        maximum_unsupported_mass=MAX_UNSUPPORTED_POSTERIOR_MASS,
    )
    zero_ok = np.array_equal(z.posterior.weights, zero.weights)

    bad = PosteriorGrid(
        parameter_names=("x",),
        points=points,
        weights=np.asarray([0.9, 0.1]),
        log_likelihood=np.asarray([0.0, -1.0]),
        admissible_mask=np.asarray([True, True]),
        dataset_id="k31-selfcheck-bad",
    )
    try:
        condition_posterior_on_predictive_admission(
            bad,
            table,
            maximum_unsupported_mass=MAX_UNSUPPORTED_POSTERIOR_MASS,
        )
    except UQProblemError:
        bad_rejected = True
    else:
        bad_rejected = False
    return bool(zero_ok and bad_rejected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--k2-forward-cache",
        default="experiments/kinetics_k2/artifacts/k2_forward_61x61.npz",
    )
    parser.add_argument(
        "--holdout-forward-cache",
        default="experiments/kinetics_k3/artifacts/k3_holdout_forward_61x61.npz",
    )
    parser.add_argument(
        "--output",
        default="experiments/kinetics_k31/artifacts/k31_results.json",
    )
    args = parser.parse_args()

    source_commit = _git_head()
    print("K3.1 scored explicit predictive-admission conditioning")
    print(f"source commit: {source_commit}")
    print(f"K3.1 prereg commit: {K31_PREREG_COMMIT}")
    print(f"K3 scored cache producer: {K3_SCORED_SOURCE_COMMIT}")
    print(f"maximum unsupported posterior mass: {MAX_UNSUPPORTED_POSTERIOR_MASS:.1e}")
    print(f"grid: {REFERENCE_GRID_SIZE}x{REFERENCE_GRID_SIZE} = {REFERENCE_GRID_SIZE ** 2:,} points")

    print("\nReconstructing frozen K2 posteriors...")
    k2_means = truth_means(condition_ids=MULTI_CONDITION_IDS)
    primary_obs = observation_set_from_truth_means(
        k2_means,
        seed=PRIMARY_SEED,
        condition_ids=MULTI_CONDITION_IDS,
        dataset_id="K2-primary",
    )
    k2_table, k2_stats = _load_k2_forward_cache(
        (_REPO_ROOT / args.k2_forward_cache).resolve(),
        primary_obs,
    )
    multi_raw = gaussian_grid_posterior(k2_table, primary_obs)
    weak_obs = primary_obs.subset(
        WEAK_CONDITION_IDS,
        dataset_id="K2-primary-weak-C2",
    )
    weak_raw = gaussian_grid_posterior(k2_table, weak_obs)

    print("Loading frozen K3 H1/H2 predictive cache...")
    h_truth = holdout_truth_means(condition_ids=HOLDOUT_IDS)
    template = holdout_template_observations(h_truth)
    holdout_build = _load_holdout_cache(
        (_REPO_ROOT / args.holdout_forward_cache).resolve(),
        template,
        source_commit=K3_SCORED_SOURCE_COMMIT,
    )
    h_table = holdout_build.table
    print(
        f"verified cache: {holdout_build.stats.point_admitted:,}/"
        f"{holdout_build.stats.parameter_points:,} points admitted"
    )

    multi, multi_audit = _condition(multi_raw, h_table)
    weak, weak_audit = _condition(weak_raw, h_table)
    print(f"primary unsupported mass: {multi_audit.unsupported_mass:.17g}")
    print(f"weak-C2 unsupported mass: {weak_audit.unsupported_mass:.17g}")

    specs = _specs(template)
    primary_uq = _uq_all(multi, h_table, specs, source_prefix="K3.1-primary")
    weak_uq = _uq_all(weak, h_table, specs, source_prefix="K3.1-primary-weak-C2")

    # S1/S2 primary records; repeated records are appended below.
    support_audits: list[PredictiveAdmissionAudit] = [multi_audit, weak_audit]

    # S4: preserve K3 U1/U2/U3.
    u1 = len(h_truth) == 4 and all(
        f"{condition_id}:{observable}" in h_truth
        for condition_id in HOLDOUT_IDS
        for observable in (CA_FINAL_METRIC, T_FINAL_METRIC)
    )
    u2_details = {key: _finite_result(result) for key, result in primary_uq.items()}
    u2 = len(u2_details) == 4 and all(u2_details.values())

    u3_details: dict[str, Any] = {}
    u3_flags: list[bool] = []
    for key, result in primary_uq.items():
        observable = key.split(":", 1)[1]
        passed, detail = _variance_decomposition(result, sigma_for_observable(observable))
        u3_details[key] = {"pass": passed, **detail}
        u3_flags.append(passed)
    u3 = len(u3_flags) == 4 and all(u3_flags)

    # S5: K3 U4.
    primary_latent = {
        key: _contains(result, h_truth[key], total=False)
        for key, result in primary_uq.items()
    }
    s5 = len(primary_latent) == 4 and all(primary_latent.values())

    # S6/S7: repeated coverage, with a support budget check for every posterior.
    latent_counts = {key: 0 for key in primary_uq}
    noisy_counts = {key: 0 for key in primary_uq}
    repeated_rows: list[dict[str, Any]] = []
    if len(RECOVERY_SEEDS) != len(REPEATED_HOLDOUT_SEEDS):
        raise RuntimeError("K3.1 paired seed vectors differ in length")

    print("\nRepeated predictive coverage with support accounting...")
    for index, (inference_seed, holdout_seed) in enumerate(
        zip(RECOVERY_SEEDS, REPEATED_HOLDOUT_SEEDS), 1
    ):
        repeated_obs = observation_set_from_truth_means(
            k2_means,
            seed=inference_seed,
            condition_ids=MULTI_CONDITION_IDS,
            dataset_id=f"K2-recovery-{inference_seed}",
        )
        raw = gaussian_grid_posterior(k2_table, repeated_obs)
        posterior, audit = _condition(raw, h_table)
        support_audits.append(audit)
        uq = _uq_all(
            posterior,
            h_table,
            specs,
            source_prefix=f"K3.1-recovery-{inference_seed}",
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
                "support_conditioning": audit.to_dict(),
                "latent_coverage": latent_flags,
                "noisy_predictive_coverage": noisy_flags,
            }
        )
        print(
            f"  repeated {index:02d}/20 | unsupported={audit.unsupported_mass:.3e}",
            flush=True,
        )

    s1 = all(_audit_ok(audit) for audit in support_audits)
    s2 = all(
        audit.unsupported_mass <= MAX_UNSUPPORTED_POSTERIOR_MASS
        for audit in support_audits
    )
    s3 = _policy_selfcheck()
    s4 = bool(u1 and u2 and u3)
    s6 = all(count >= 15 for count in latent_counts.values())
    s7 = all(count >= 15 for count in noisy_counts.values())

    # S8: information gain survives propagation.
    s8_details: dict[str, Any] = {}
    s8_flags: list[bool] = []
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
        s8_details[key] = {
            "pass": passed,
            "multi_epistemic_std": multi_std,
            "weak_epistemic_std": weak_std,
            "ratio": ratio,
            "maximum_ratio": 0.80,
        }
        s8_flags.append(passed)
    s8 = len(s8_flags) == 4 and all(s8_flags)

    # S9: deterministic replay includes the support audit.
    replay_multi, replay_audit = _condition(multi_raw, h_table)
    replay_uq = _uq_all(
        replay_multi,
        h_table,
        specs,
        source_prefix="K3.1-primary",
    )
    s9 = _canonical_bundle(primary_uq, multi_audit) == _canonical_bundle(
        replay_uq, replay_audit
    )

    # S10: exact Twin/model/evidence/support binding.
    twin = k3_reference_twin()
    expected_model = (CSTR_MODEL.model_id, CSTR_MODEL.version)
    s10_details: dict[str, bool] = {}
    for key, result in primary_uq.items():
        s10_details[key] = bool(
            result.twin == twin.reference
            and result.posterior_dataset_id == "K2-primary"
            and result.model.key == expected_model
            and result.observation_key == key
            and f"k31-prereg:{K31_PREREG_COMMIT}" in result.source_ref
            and f"k3-prereg:{K3_PREREG_COMMIT}" in result.source_ref
            and f"k2-source:{K2_SCIENTIFIC_SOURCE_COMMIT}" in result.source_ref
        )
    s10 = len(s10_details) == 4 and all(s10_details.values()) and _audit_ok(multi_audit)

    acceptance = {
        "S1_support_accounting_explicit": {
            "pass": bool(s1),
            "posteriors_checked": len(support_audits),
        },
        "S2_unsupported_mass_budget": {
            "pass": bool(s2),
            "maximum_allowed": MAX_UNSUPPORTED_POSTERIOR_MASS,
            "maximum_observed": max(a.unsupported_mass for a in support_audits),
        },
        "S3_fail_closed_regression": {"pass": bool(s3)},
        "S4_k3_u1_u2_u3_preserved": {
            "pass": bool(s4),
            "truth_holdout_admissibility": bool(u1),
            "finite_outputs": {"pass": bool(u2), "by_observable": u2_details},
            "variance_decomposition": {"pass": bool(u3), "by_observable": u3_details},
        },
        "S5_primary_latent_truth_coverage": {
            "pass": bool(s5),
            "by_observable": primary_latent,
        },
        "S6_repeated_latent_coverage": {
            "pass": bool(s6),
            "coverage_counts": latent_counts,
            "required_each": 15,
            "datasets": 20,
        },
        "S7_repeated_noisy_predictive_coverage": {
            "pass": bool(s7),
            "coverage_counts": noisy_counts,
            "required_each": 15,
            "datasets": 20,
        },
        "S8_information_gain_survives_propagation": {
            "pass": bool(s8),
            "by_observable": s8_details,
        },
        "S9_deterministic_replay": {"pass": bool(s9)},
        "S10_twin_evidence_binding": {
            "pass": bool(s10),
            "by_observable": s10_details,
        },
        "S11_regression_safety": {
            "pass": None,
            "status": "pending_full_regression",
        },
    }

    science_pass = all(acceptance[f"S{i}_{name}"]["pass"] for i, name in (
        (1, "support_accounting_explicit"),
        (2, "unsupported_mass_budget"),
        (3, "fail_closed_regression"),
        (4, "k3_u1_u2_u3_preserved"),
        (5, "primary_latent_truth_coverage"),
        (6, "repeated_latent_coverage"),
        (7, "repeated_noisy_predictive_coverage"),
        (8, "information_gain_survives_propagation"),
        (9, "deterministic_replay"),
        (10, "twin_evidence_binding"),
    ))

    payload = {
        "schema": K31_SCHEMA,
        "status": "SCIENCE_PASS_S11_PENDING" if science_pass else "SCIENCE_FAIL",
        "source_commit": source_commit,
        "k31_prereg_commit": K31_PREREG_COMMIT,
        "k3_prereg_commit": K3_PREREG_COMMIT,
        "k3_scored_cache_producer": K3_SCORED_SOURCE_COMMIT,
        "k2_scientific_source": K2_SCIENTIFIC_SOURCE_COMMIT,
        "maximum_unsupported_posterior_mass": MAX_UNSUPPORTED_POSTERIOR_MASS,
        "k2_forward_stats": k2_stats.to_dict(),
        "holdout_forward_stats": holdout_build.stats.to_dict(),
        "primary_support_conditioning": multi_audit.to_dict(),
        "weak_support_conditioning": weak_audit.to_dict(),
        "primary_uq": {key: value.to_dict() for key, value in sorted(primary_uq.items())},
        "weak_uq": {key: value.to_dict() for key, value in sorted(weak_uq.items())},
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
