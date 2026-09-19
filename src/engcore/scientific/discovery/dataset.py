from __future__ import annotations

from dataclasses import dataclass
import math
import re

import numpy as np

from ..errors import InvalidScientificProblem
from ..equations import Expression, infer_dimension

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DiscoveryFeature:
    name: str
    expression: Expression
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        values = tuple(float(x) for x in self.values)
        if not name or not values:
            raise InvalidScientificProblem(
                "discovery feature requires name and values"
            )
        if any(not math.isfinite(x) for x in values):
            raise InvalidScientificProblem(
                f"discovery feature {name!r} contains non-finite values"
            )
        if not infer_dimension(self.expression, {}).is_dimensionless:
            raise InvalidScientificProblem(
                f"discovery feature {name!r} must be dimensionless"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "values", values)


@dataclass(frozen=True)
class DiscoveryDataset:
    dataset_id: str
    features: tuple[DiscoveryFeature, ...]
    target: tuple[float, ...]
    calibration_indices: tuple[int, ...]
    holdout_indices: tuple[int, ...]
    context_digest: str
    evidence_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        dataset_id = str(self.dataset_id).strip()
        target = tuple(float(x) for x in self.target)
        context = str(self.context_digest).strip().lower()
        evidence = tuple(
            sorted(set(str(x).strip().lower() for x in self.evidence_digests))
        )
        features = tuple(self.features)
        if not dataset_id or not target or not features:
            raise InvalidScientificProblem(
                "discovery dataset requires id, features and target"
            )
        if any(not isinstance(feature, DiscoveryFeature) for feature in features):
            raise InvalidScientificProblem(
                "discovery dataset features must be DiscoveryFeature records"
            )
        names = [feature.name for feature in features]
        if len(names) != len(set(names)):
            raise InvalidScientificProblem(
                "discovery dataset feature names must be unique"
            )
        count = len(target)
        if any(len(feature.values) != count for feature in features):
            raise InvalidScientificProblem(
                "all discovery features must align with target length"
            )
        if any(not math.isfinite(x) for x in target):
            raise InvalidScientificProblem(
                "discovery target contains non-finite values"
            )
        calibration = tuple(sorted(set(int(i) for i in self.calibration_indices)))
        holdout = tuple(sorted(set(int(i) for i in self.holdout_indices)))
        if not calibration or not holdout:
            raise InvalidScientificProblem(
                "discovery requires non-empty calibration and holdout partitions"
            )
        if set(calibration) & set(holdout):
            raise InvalidScientificProblem(
                "discovery calibration and holdout partitions must be disjoint"
            )
        if any(i < 0 or i >= count for i in calibration + holdout):
            raise InvalidScientificProblem(
                "discovery split indices lie outside dataset"
            )
        if not _SHA256.fullmatch(context):
            raise InvalidScientificProblem(
                "discovery context_digest must be lowercase SHA-256"
            )
        if not evidence or any(not _SHA256.fullmatch(x) for x in evidence):
            raise InvalidScientificProblem(
                "discovery dataset requires evidence SHA-256 identities"
            )
        object.__setattr__(self, "dataset_id", dataset_id)
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "calibration_indices", calibration)
        object.__setattr__(self, "holdout_indices", holdout)
        object.__setattr__(self, "context_digest", context)
        object.__setattr__(self, "evidence_digests", evidence)

    def matrix(self, indices: tuple[int, ...]) -> np.ndarray:
        return np.asarray(
            [[feature.values[i] for feature in self.features] for i in indices],
            dtype=float,
        )

    def target_vector(self, indices: tuple[int, ...]) -> np.ndarray:
        return np.asarray([self.target[i] for i in indices], dtype=float)
