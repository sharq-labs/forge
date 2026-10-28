"""Ordering controls for sparse discovery; selection scores are not final evidence."""

from dataclasses import replace

import pytest

from engcore.scientific.discovery import (
    DiscoveryDataset, DiscoveryFeature, SparseDiscoveryPolicy, discover_sparse_equations,
)
from engcore.scientific.discovery import symbolic_regression as sr
from engcore.scientific.equations import Symbol
from engcore.scientific.units.quantity import Quantity


def dataset():
    # Dimensionless synthetic feature columns; no evaluator data or physical claim.
    return DiscoveryDataset(
        "ordering", (
            DiscoveryFeature("z_exact", Symbol("x"), (1., 2., 3., 4., 5., 6.),
                             tuple({"x": Quantity(x, "1")} for x in (1, 2, 3, 4, 5, 6))),
            DiscoveryFeature("a_other", Symbol("square"), (1., 4., 9., 16., 25., 36.),
                             tuple({"square": Quantity(x, "1")} for x in (1, 4, 9, 16, 25, 36))),
        ), (0., 0., 0., 0., 0., 0.), (0, 1, 2, 3), (4, 5), "a" * 64, ("b" * 64,),
    )


@pytest.mark.parametrize("errors,expected", [
    ((0.0, 0.01), ("z_exact", "a_other")),
    ((0.02, 0.01), ("a_other", "z_exact")),
    ((0.0, 0.0), ("a_other", "z_exact")),
])
def test_scores_order_candidates_without_treating_zero_as_missing(monkeypatch, errors, expected):
    # Control scores at the numerical boundary to test exact zero independently
    # of platform-specific least-squares roundoff; fitting still executes.
    scores = iter(errors)
    monkeypatch.setattr(sr, "_rmse", lambda *args: next(scores))
    data = replace(dataset(), target=(1., 2., 3., 4., 5., 6.))
    result = discover_sparse_equations(data, SparseDiscoveryPolicy(max_terms=1))
    assert tuple(c.feature_names[0] for c in result) == expected
    assert {c.holdout_rmse for c in result} == set(errors)


def test_native_zero_target_has_real_zero_error_and_deterministic_ties():
    result = discover_sparse_equations(dataset(), SparseDiscoveryPolicy(max_terms=1))
    assert all(c.holdout_rmse == 0.0 for c in result)
    assert tuple(c.feature_names[0] for c in result) == ("a_other", "z_exact")


def test_complexity_penalty_still_applies_to_zero_error():
    result = discover_sparse_equations(dataset(), SparseDiscoveryPolicy(max_terms=2))
    assert [c.complexity for c in result] == [1, 1, 2]


def test_zero_fit_is_not_promoted_to_independent_verification():
    from engcore.scientific.discovery import DiscoveryCandidateStatus

    result = discover_sparse_equations(dataset(), SparseDiscoveryPolicy(max_terms=1))
    assert all(c.status is DiscoveryCandidateStatus.SURVIVED_HOLDOUT for c in result)
    assert all(c.status is not DiscoveryCandidateStatus.INDEPENDENTLY_VERIFIED for c in result)
