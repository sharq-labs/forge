"""Read-only diagnostic for the K3 predictive-support admission failure.

This utility does not alter K2/K3 scientific artifacts. It inspects the already
saved K2 and K3 forward caches, reconstructs the frozen primary/weak K2
posteriors, and reports posterior mass carried by parameter points that are
admitted for K2 fitting but rejected at the K3 holdout conditions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.kinetics_k2.k2_config import (  # noqa: E402
    MULTI_CONDITION_IDS,
    PRIMARY_SEED,
    WEAK_CONDITION_IDS,
)
from experiments.kinetics_k2.k2_forward import (  # noqa: E402
    observation_set_from_truth_means,
    truth_means,
)
from src.engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    gaussian_grid_posterior,
)


def _load_cache(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    with np.load(path, allow_pickle=False) as payload:
        points = np.asarray(payload["points"], dtype=np.float64)
        values = np.asarray(payload["values"], dtype=np.float64)
        mask = np.asarray(payload["admissible_mask"], dtype=bool)
        audit = json.loads(str(payload["audit_json"].item()))
    return points, values, mask, audit


def main() -> None:
    k2_path = _REPO_ROOT / "experiments/kinetics_k2/artifacts/k2_forward_61x61.npz"
    k3_path = _REPO_ROOT / "experiments/kinetics_k3/artifacts/k3_holdout_forward_61x61.npz"

    k2_points, k2_values, k2_mask, k2_audit = _load_cache(k2_path)
    k3_points, _k3_values, k3_mask, k3_audit = _load_cache(k3_path)
    if not np.array_equal(k2_points, k3_points):
        raise RuntimeError("K2 and K3 caches do not share identical parameter support")

    means = truth_means(condition_ids=MULTI_CONDITION_IDS)
    primary = observation_set_from_truth_means(
        means,
        seed=PRIMARY_SEED,
        condition_ids=MULTI_CONDITION_IDS,
        dataset_id="K2-primary",
    )
    weak = primary.subset(WEAK_CONDITION_IDS, dataset_id="K2-primary-weak-C2")

    k2_table = AdmittedForwardTable(
        parameter_names=tuple(k2_audit["parameter_names"]),
        observation_keys=tuple(k2_audit["observation_keys"]),
        points=k2_points,
        values=k2_values,
        admissible_mask=k2_mask,
        admission_refs=tuple(tuple(row) for row in k2_audit["admission_refs"]),
        rejection_reasons=tuple(k2_audit["rejection_reasons"]),
    )
    multi = gaussian_grid_posterior(k2_table, primary)
    weak_post = gaussian_grid_posterior(k2_table, weak)

    unsupported = k2_mask & ~k3_mask
    print(f"K2 admitted points: {int(np.count_nonzero(k2_mask)):,}/{len(k2_mask):,}")
    print(f"K3 holdout admitted points: {int(np.count_nonzero(k3_mask)):,}/{len(k3_mask):,}")
    print(f"K2-admitted but K3-rejected points: {int(np.count_nonzero(unsupported)):,}")
    print(f"primary unsupported posterior mass: {float(np.sum(multi.weights[unsupported])):.17g}")
    print(f"weak-C2 unsupported posterior mass: {float(np.sum(weak_post.weights[unsupported])):.17g}")

    indices = np.flatnonzero(unsupported)
    ranked = sorted(
        indices,
        key=lambda i: max(float(multi.weights[i]), float(weak_post.weights[i])),
        reverse=True,
    )
    print("\nUnsupported points (highest posterior relevance first):")
    reasons = tuple(k3_audit.get("rejection_reasons", ()))
    for i in ranked:
        coordinate = k2_points[i]
        reason = reasons[i] if i < len(reasons) else ""
        print(
            f"index={int(i):4d} log_k0={coordinate[0]:.12g} E/R={coordinate[1]:.12g} "
            f"multi_w={float(multi.weights[i]):.17g} weak_w={float(weak_post.weights[i]):.17g}"
        )
        if reason:
            print(f"  reason: {reason}")


if __name__ == "__main__":
    main()
