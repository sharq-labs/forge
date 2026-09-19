from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math

import numpy as np

from ..errors import InvalidScientificProblem
from .candidate import DiscoveredEquationCandidate, DiscoveryCandidateStatus
from .dataset import DiscoveryDataset


@dataclass(frozen=True)
class SparseDiscoveryPolicy:
    max_terms: int = 3
    maximum_candidates: int = 2000
    complexity_penalty: float = 1e-4
    holdout_rmse_limit: float = 0.05
    minimum_holdout_improvement: float = 0.0

    def __post_init__(self) -> None:
        if int(self.max_terms) < 1:
            raise ValueError("discovery max_terms must be >=1")
        if int(self.maximum_candidates) < 1:
            raise ValueError("maximum_candidates must be >=1")
        penalty = float(self.complexity_penalty)
        limit = float(self.holdout_rmse_limit)
        improvement = float(self.minimum_holdout_improvement)
        if (
            not math.isfinite(penalty)
            or penalty < 0
            or not math.isfinite(limit)
            or limit < 0
            or not math.isfinite(improvement)
            or improvement < 0
        ):
            raise ValueError(
                "discovery penalties/limits must be finite and non-negative"
            )
        object.__setattr__(self, "max_terms", int(self.max_terms))
        object.__setattr__(self, "maximum_candidates", int(self.maximum_candidates))
        object.__setattr__(self, "complexity_penalty", penalty)
        object.__setattr__(self, "holdout_rmse_limit", limit)
        object.__setattr__(
            self, "minimum_holdout_improvement", improvement
        )


def _fit(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    design = np.column_stack([np.ones(len(x)), x])
    coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank < design.shape[1]:
        raise InvalidScientificProblem(
            "candidate feature set is rank-deficient"
        )
    prediction = design @ coefficients
    rmse = float(np.sqrt(np.mean((prediction - y) ** 2)))
    return coefficients[1:], float(coefficients[0]), rmse


def _rmse(
    x: np.ndarray,
    y: np.ndarray,
    coefficients: np.ndarray,
    intercept: float,
) -> float:
    prediction = intercept + x @ coefficients
    return float(np.sqrt(np.mean((prediction - y) ** 2)))


def discover_sparse_equations(
    dataset: DiscoveryDataset,
    policy: SparseDiscoveryPolicy = SparseDiscoveryPolicy(),
) -> tuple[DiscoveredEquationCandidate, ...]:
    calibration_y = dataset.target_vector(dataset.calibration_indices)
    holdout_y = dataset.target_vector(dataset.holdout_indices)
    feature_count = len(dataset.features)
    candidates = []
    attempted = 0
    baseline = float(
        np.sqrt(np.mean((holdout_y - np.mean(calibration_y)) ** 2))
    )

    for term_count in range(1, min(policy.max_terms, feature_count) + 1):
        for indices in combinations(range(feature_count), term_count):
            attempted += 1
            if attempted > policy.maximum_candidates:
                break
            calibration_x = dataset.matrix(dataset.calibration_indices)[:, indices]
            holdout_x = dataset.matrix(dataset.holdout_indices)[:, indices]
            try:
                coefficients, intercept, calibration_rmse = _fit(
                    calibration_x, calibration_y
                )
            except InvalidScientificProblem:
                continue
            holdout_rmse = _rmse(
                holdout_x, holdout_y, coefficients, intercept
            )
            feature_names = tuple(
                dataset.features[index].name for index in indices
            )
            status = (
                DiscoveryCandidateStatus.SURVIVED_HOLDOUT
                if (
                    holdout_rmse <= policy.holdout_rmse_limit
                    and baseline - holdout_rmse
                    >= policy.minimum_holdout_improvement
                )
                else DiscoveryCandidateStatus.FAILED_HOLDOUT
            )
            candidate_id = (
                f"{dataset.dataset_id}:{'-'.join(feature_names)}:{attempted}"
            )
            candidates.append(
                DiscoveredEquationCandidate(
                    candidate_id,
                    feature_names,
                    tuple(float(x) for x in coefficients),
                    intercept,
                    calibration_rmse,
                    holdout_rmse,
                    term_count,
                    dataset.context_digest,
                    dataset.evidence_digests,
                    status,
                )
            )
        if attempted > policy.maximum_candidates:
            break

    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.status
                is not DiscoveryCandidateStatus.SURVIVED_HOLDOUT,
                (item.holdout_rmse or float("inf"))
                + policy.complexity_penalty * item.complexity,
                item.candidate_id,
            ),
        )
    )
