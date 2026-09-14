"""Artifact evidence strengthens, but never replaces, route declarations."""

from __future__ import annotations

import pytest

from engcore.scientific.consensus import (
    IndependenceDimension,
    RouteDependencies,
    SolveRoute,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.independence_evidence import (
    ArtifactFingerprint,
    RouteIndependenceEvidence,
    assess_independence_evidence,
    require_strong_independence,
)
from engcore.scientific.solvers.protocol import SolverIdentity


_REQUIRED = (
    IndependenceDimension.PREPROCESSING,
    IndependenceDimension.NUMERICAL_METHOD,
    IndependenceDimension.IMPLEMENTATION,
    IndependenceDimension.BACKEND,
)


def _dependencies(prefix: str) -> RouteDependencies:
    return RouteDependencies(
        {
            IndependenceDimension.PROBLEM_DECLARATION: {"ext:shared:problem"},
            IndependenceDimension.PREPROCESSING: {f"ext:{prefix}:pre"},
            IndependenceDimension.NUMERICAL_METHOD: {f"ext:{prefix}:method"},
            IndependenceDimension.IMPLEMENTATION: {f"ext:{prefix}:implementation"},
            IndependenceDimension.BACKEND: {f"ext:{prefix}:backend"},
        }
    )


def _route(route_id: str, prefix: str) -> SolveRoute:
    return SolveRoute(
        route_id=route_id,
        solver=SolverIdentity(f"solver.{prefix}", "1", backend=prefix),
        dependencies=_dependencies(prefix),
    )


def _evidence(route: SolveRoute, seed: int) -> RouteIndependenceEvidence:
    assert route.dependencies is not None
    artifacts = {}
    for offset, dimension in enumerate(_REQUIRED):
        digit = format(seed + offset, "x")[-1]
        artifacts[dimension] = frozenset(
            {ArtifactFingerprint(digest=digit * 64, name=f"{route.route_id}:{dimension.value}")}
        )
    return RouteIndependenceEvidence(
        route_id=route.route_id,
        dependency_digest=route.dependencies.digest,
        artifacts=artifacts,
    )


def test_disjoint_complete_artifacts_establish_strong_evidence():
    left, right = _route("left", "a"), _route("right", "b")
    report = assess_independence_evidence(
        (left, right), (_evidence(left, 1), _evidence(right, 8))
    )
    assert report.all_routes_verified
    assert report.artifact_disjoint
    assert report.strongly_independent
    assert require_strong_independence(
        (left, right), (_evidence(left, 1), _evidence(right, 8))
    ) == report


def test_different_labels_on_same_artifact_are_detected_as_shared_machinery():
    left, right = _route("left", "a"), _route("right", "b")
    left_evidence, right_evidence = _evidence(left, 1), _evidence(right, 8)
    shared = "f" * 64
    left_map = dict(left_evidence.artifacts)
    right_map = dict(right_evidence.artifacts)
    left_map[IndependenceDimension.IMPLEMENTATION] = frozenset(
        {ArtifactFingerprint(shared, "wrapper-a", kind="source")}
    )
    right_map[IndependenceDimension.BACKEND] = frozenset(
        {ArtifactFingerprint(shared, "binary-b", kind="binary")}
    )
    left_evidence = RouteIndependenceEvidence(
        left.route_id, left.dependencies.digest, left_map  # type: ignore[union-attr]
    )
    right_evidence = RouteIndependenceEvidence(
        right.route_id, right.dependencies.digest, right_map  # type: ignore[union-attr]
    )

    report = assess_independence_evidence((left, right), (left_evidence, right_evidence))
    assert report.all_routes_verified
    assert not report.artifact_disjoint
    assert not report.strongly_independent
    assert report.shared_artifacts[0].routes == ("left", "right")
    assert set(report.shared_artifacts[0].names) == {"wrapper-a", "binary-b"}


def test_evidence_must_bind_the_exact_dependency_declaration():
    route = _route("left", "a")
    evidence = _evidence(route, 1)
    forged = RouteIndependenceEvidence(
        route_id=route.route_id,
        dependency_digest="0" * 64,
        artifacts=evidence.artifacts,
    )
    report = assess_independence_evidence((route,), (forged,))
    assert not report.all_routes_verified
    assert "evidence binds dependency digest" in report.route_findings[0][1][0]


def test_every_solver_independence_dimension_requires_artifact_evidence():
    route = _route("left", "a")
    evidence = _evidence(route, 1)
    incomplete = dict(evidence.artifacts)
    del incomplete[IndependenceDimension.BACKEND]
    item = RouteIndependenceEvidence(
        route.route_id,
        route.dependencies.digest,  # type: ignore[union-attr]
        incomplete,
    )
    report = assess_independence_evidence((route,), (item,))
    assert not report.all_routes_verified
    assert any("backend" in reason for reason in report.route_findings[0][1])


def test_missing_route_evidence_is_unverified_not_independent_by_silence():
    left, right = _route("left", "a"), _route("right", "b")
    report = assess_independence_evidence((left, right), (_evidence(left, 1),))
    assert not report.all_routes_verified
    assert not report.strongly_independent
    assert dict(report.route_findings)["right"] == ("no artifact evidence supplied",)


def test_extra_evidence_for_a_route_not_compared_is_refused():
    left, right = _route("left", "a"), _route("right", "b")
    with pytest.raises(ScientificValidationError, match="not being compared"):
        assess_independence_evidence((left,), (_evidence(left, 1), _evidence(right, 8)))


def test_route_evidence_round_trips_without_weakening_digests():
    route = _route("left", "a")
    evidence = _evidence(route, 1)
    restored = RouteIndependenceEvidence.from_dict(evidence.to_dict())
    assert restored == evidence
    assert restored.evidence_gap(route) == ()


def test_two_routes_are_required_even_when_one_routes_evidence_is_complete():
    route = _route("left", "a")
    report = assess_independence_evidence((route,), (_evidence(route, 1),))
    assert report.all_routes_verified
    assert not report.strongly_independent
    with pytest.raises(ScientificValidationError, match="at least two"):
        require_strong_independence((route,), (_evidence(route, 1),))
