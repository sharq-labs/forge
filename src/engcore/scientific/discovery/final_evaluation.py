"""Final evaluation of a frozen selection on a separately supplied dataset.

This is numerical testing, not experimental validation or independent custody.
Lineage IDs are declarations checked for overlap, not authenticated identities.
The final limit is capped by the frozen policy, but only external custody can
prove it was committed before the final data existed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from ..errors import InvalidScientificProblem
from .candidate import DiscoveredEquationCandidate, DiscoveryCandidateStatus
from .dataset import DiscoveryDataset, DiscoveryFeature
from .symbolic_regression import SparseDiscoveryPolicy, discover_sparse_equations, _rmse


# A frozen record's checks run once, in its constructor; a field changed afterwards (object.__setattr__) skips them.
# These rebuild the nested records through their constructors where they are used and require the same value back.
# In-process code is trusted beyond this: untrusted input must cross a serialization or process boundary.
def _checked_policy(policy: SparseDiscoveryPolicy) -> None:
    try:
        rebuilt = SparseDiscoveryPolicy(**asdict(policy))
    except ValueError as exc:
        raise InvalidScientificProblem(f"frozen search policy no longer satisfies its constructor: {exc}") from exc
    if rebuilt != policy:
        raise InvalidScientificProblem("frozen search policy changed after it was built")


def _checked_dataset(dataset: DiscoveryDataset) -> None:
    if type(dataset) is not DiscoveryDataset or any(type(f) is not DiscoveryFeature for f in dataset.features):
        raise InvalidScientificProblem("an exact DiscoveryDataset of exact DiscoveryFeatures is required (no subclasses)")
    features = tuple(DiscoveryFeature(f.name, f.expression, f.values, f.sample_bindings) for f in dataset.features)
    rebuilt = DiscoveryDataset(**({f.name: getattr(dataset, f.name) for f in fields(DiscoveryDataset)}
                                  | {"features": features}))
    if rebuilt != dataset:
        raise InvalidScientificProblem("discovery dataset changed after it was built")


@dataclass(frozen=True)
class FrozenDiscoverySelection:
    development: DiscoveryDataset
    policy: SparseDiscoveryPolicy
    candidate: DiscoveredEquationCandidate
    final_rmse_limit: float

    def __post_init__(self):
        # exact types: a subclass could override these checks or the identities they rest on
        if (type(self.development) is not DiscoveryDataset or type(self.policy) is not SparseDiscoveryPolicy
                or type(self.candidate) is not DiscoveredEquationCandidate):
            raise InvalidScientificProblem("typed development data, search policy and candidate required (no subclasses)")
        _checked_policy(self.policy)
        _checked_dataset(self.development)
        limit = float(self.final_rmse_limit)
        if not math.isfinite(limit) or limit < 0:
            raise InvalidScientificProblem("final RMSE limit must be finite and non-negative")
        if limit > self.policy.holdout_rmse_limit:
            raise InvalidScientificProblem("final RMSE limit cannot be looser than the frozen policy's holdout limit")
        if not self.development.sample_ids or not self.development.group_ids:
            raise InvalidScientificProblem("final testing requires sample and physical group lineage IDs")
        ranked = discover_sparse_equations(self.development, self.policy)
        if (not ranked or self.candidate != ranked[0] or self.candidate.fingerprint != ranked[0].fingerprint
                or self.candidate.status is not DiscoveryCandidateStatus.SURVIVED_HOLDOUT):
            raise InvalidScientificProblem("only the selected surviving winner may be frozen")
        object.__setattr__(self, "final_rmse_limit", limit)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps({"schema": "frozen_discovery_selection/2",
            "candidate": self.candidate.fingerprint, "final_rmse_limit": self.final_rmse_limit,
            "development": self.development.fingerprint, "policy": asdict(self.policy)},
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evaluate_final_test(selection: FrozenDiscoverySelection,
                        final_data: DiscoveryDataset) -> DiscoveredEquationCandidate:
    """Score only the frozen winner. Never refit, rank, or return alternatives."""
    if type(selection) is not FrozenDiscoverySelection or type(final_data) is not DiscoveryDataset:
        raise InvalidScientificProblem("an exact FrozenDiscoverySelection and DiscoveryDataset are required (no subclasses)")
    # re-check the selection (and its nested policy and data) and the final data where they are used
    FrozenDiscoverySelection(selection.development, selection.policy, selection.candidate, selection.final_rmse_limit)
    _checked_dataset(final_data)
    development, candidate = selection.development, selection.candidate
    if not final_data.sample_ids or not final_data.group_ids:
        raise InvalidScientificProblem("final testing requires sample and physical group lineage IDs")
    if (set(development.sample_ids) & set(final_data.sample_ids)
            or set(development.group_ids) & set(final_data.group_ids)):
        raise InvalidScientificProblem("final test overlaps development sample/group lineage")
    if final_data.context_digest != development.context_digest:
        raise InvalidScientificProblem("final test context differs from development")
    old = {f.name: f for f in development.features}
    new = {f.name: f for f in final_data.features}
    if any(name not in new or old[name].expression.to_dict() != new[name].expression.to_dict()
           for name in candidate.feature_names):
        raise InvalidScientificProblem("final test feature expressions differ from the frozen model")
    if set(development.evidence_digests) & set(final_data.evidence_digests):
        raise InvalidScientificProblem("final test shares evidence with development")
    seen = {(tuple(old[name].values[i] for name in candidate.feature_names), development.target[i])
            for i in range(len(development.target))}
    if any((tuple(new[name].values[i] for name in candidate.feature_names), final_data.target[i]) in seen
           for i in range(len(final_data.target))):
        raise InvalidScientificProblem("final test rows duplicate development rows")
    matrix = np.asarray([new[name].values for name in candidate.feature_names], dtype=float).T
    final_y = np.asarray(final_data.target, dtype=float)
    error = _rmse(matrix, final_y, np.asarray(candidate.coefficients), candidate.intercept)
    # the same rule selection used, with the baseline prediction fixed by the development calibration rows
    baseline = float(np.sqrt(np.mean((final_y - np.mean(development.target_vector(development.calibration_indices))) ** 2)))
    survived = (error <= selection.final_rmse_limit
                and baseline - error >= selection.policy.minimum_holdout_improvement)
    binding = hashlib.sha256(json.dumps({"schema": "discovery_final_test/1",
        "selection": selection.fingerprint, "final_data": final_data.fingerprint,
        "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "numpy_version": np.__version__},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return replace(candidate, holdout_rmse=error, evaluation_role="final_test",
                   discovery_binding_digest=binding,
                   status=(DiscoveryCandidateStatus.SURVIVED_HOLDOUT if survived
                           else DiscoveryCandidateStatus.FAILED_HOLDOUT))
