from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Mapping

import numpy as np

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..equations import Expression, infer_dimension
from ..equations.evaluation import evaluate_expression
from ..units.quantity import Quantity

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DiscoveryFeature:
    name: str
    expression: Expression
    values: tuple[float, ...]
    sample_bindings: tuple[Mapping[str, Quantity], ...] = ()

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
        bindings = tuple(MappingProxyType(dict(row)) for row in self.sample_bindings)
        if bindings and len(bindings) != len(values):
            raise InvalidScientificProblem("feature bindings must align with values")
        for value, row in zip(values, bindings or ({},) * len(values)):
            if any(not isinstance(q, Quantity) for q in row.values()):
                raise InvalidScientificProblem("feature bindings require Quantity values")
            if not infer_dimension(self.expression, {k: q.units for k, q in row.items()}).is_dimensionless:
                raise InvalidScientificProblem(f"discovery feature {name!r} must be dimensionless")
            expected = evaluate_expression(self.expression, row).magnitude_in("1")
            if value != expected:
                raise InvalidScientificProblem("feature values do not match the declared expression and bindings")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "sample_bindings", bindings)

    def to_dict(self) -> dict:
        return {"name": self.name, "expression": self.expression.to_dict(),
                "values": list(self.values), "sample_bindings": [
                    {k: q.to_dict() for k, q in row.items()} for row in self.sample_bindings]}


@dataclass(frozen=True)
class DiscoveryDataset:
    """Calibration and selection data. ``holdout_indices`` is the legacy name
    for selection rows; these rows are NOT an independent final test.
    Sample/group IDs describe physical lineage, never arbitrary row splits.
    """
    dataset_id: str
    features: tuple[DiscoveryFeature, ...]
    target: tuple[float, ...]
    calibration_indices: tuple[int, ...]
    holdout_indices: tuple[int, ...]
    context_digest: str
    evidence_digests: tuple[str, ...]
    sample_ids: tuple[str, ...] = ()
    group_ids: tuple[str, ...] = ()

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
        for row_index in range(count):
            shared: dict[str, Quantity] = {}
            for feature in features:
                if not feature.sample_bindings:
                    continue
                for name, quantity in feature.sample_bindings[row_index].items():
                    if name in shared:
                        reference = shared[name]
                        try:
                            agrees = quantity.magnitude_in(reference.units) == reference.magnitude
                        except UnitCompatibilityError:
                            agrees = False
                        if not agrees:
                            raise InvalidScientificProblem(
                                f"shared symbol {name!r} has conflicting bindings in row {row_index}"
                            )
                    else:
                        shared[name] = quantity
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
        for field in ("sample_ids", "group_ids"):
            ids = tuple(getattr(self, field))
            if ids and (len(ids) != count or any(type(x) is not str or not x.strip() for x in ids)):
                raise InvalidScientificProblem(f"{field} must align with rows and be non-empty strings")
            if field == "sample_ids" and len(ids) != len(set(ids)):
                raise InvalidScientificProblem("sample_ids must be unique")
            object.__setattr__(self, field, ids)

    @property
    def fingerprint(self) -> str:
        payload = {"schema": "discovery_dataset/2", "dataset_id": self.dataset_id,
                   "features": [f.to_dict() for f in self.features], "target": self.target,
                   "calibration_indices": self.calibration_indices,
                   "selection_indices": self.holdout_indices, "context": self.context_digest,
                   "evidence": self.evidence_digests, "sample_ids": self.sample_ids,
                   "group_ids": self.group_ids}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                         allow_nan=False).encode()).hexdigest()

    def matrix(self, indices: tuple[int, ...]) -> np.ndarray:
        return np.asarray(
            [[feature.values[i] for feature in self.features] for i in indices],
            dtype=float,
        )

    def target_vector(self, indices: tuple[int, ...]) -> np.ndarray:
        return np.asarray([self.target[i] for i in indices], dtype=float)
