"""Artifact evidence strengthens declarations only after byte verification."""

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


def _evidence(route: SolveRoute, seed: int):
    assert route.dependencies is not None
    artifacts = {}
    artifact_bytes = {}
    for offset, dimension in enumerate(_REQUIRED):
        name = f"{route.route_id}:{dimension.value}"
        payload = f"artifact:{route.route_id}:{dimension.value}:{seed + offset}".encode()
        artifacts[dimension] = frozenset(
            {ArtifactFingerprint.from_bytes(name, payload, kind="test-artifact")}
        )
        artifact_bytes[dimension] = {name: payload}
    return (
        RouteIndependenceEvidence(
            route_id=route.route_id,
            dependency_digest=route.dependencies.digest,
            artifacts=artifacts,
        ),
        artifact_bytes,
    )


def _pair():
    left, right = _route("left", "a"), _route("right", "b")
    left_evidence, left_bytes = _evidence(left, 1)
    right_evidence, right_bytes = _evidence(right, 8)
    return (
        left,
        right,
        (left_evidence, right_evidence),
        {"left": left_bytes, "right": right_bytes},
    )


def test_disjoint_complete_verified_artifacts_establish_strong_evidence():
    left, right, evidence, artifact_bytes = _pair()
    report = assess_independence_evidence(
        (left, right), evidence, artifact_bytes=artifact_bytes
    )
    assert report.all_routes_verified
    assert report.artifact_disjoint
    assert report.strongly_independent
    assert require_strong_independence(
        (left, right), evidence, artifact_bytes=artifact_bytes
    ) == report


def test_digest_strings_without_bytes_do_not_establish_independence():
    left, right, evidence, _ = _pair()
    report = assess_independence_evidence((left, right), evidence)
    assert not report.all_routes_verified
    assert not report.strongly_independent
    assert all(
        any("no artifact bytes supplied" in reason for reason in reasons)
        for _, reasons in report.route_findings
    )


def test_forged_digest_is_recomputed_and_rejected():
    left, right, evidence, artifact_bytes = _pair()
    left_evidence, right_evidence = evidence
    forged_map = dict(left_evidence.artifacts)
    original = next(iter(forged_map[IndependenceDimension.IMPLEMENTATION]))
    forged_map[IndependenceDimension.IMPLEMENTATION] = frozenset(
        {
            ArtifactFingerprint(
                digest="f" * 64,
                name=original.name,
                kind=original.kind,
            )
        }
    )
    forged = RouteIndependenceEvidence(
        left_evidence.route_id,
        left_evidence.dependency_digest,
        forged_map,
    )
    report = assess_independence_evidence(
        (left, right),
        (forged, right_evidence),
        artifact_bytes=artifact_bytes,
    )
    assert not report.all_routes_verified
    assert not report.strongly_independent
    assert any(
        "supplied bytes hash to" in reason
        for reason in dict(report.route_findings)["left"]
    )


def test_different_labels_on_same_verified_bytes_are_detected_as_shared_machinery():
    left, right, evidence, artifact_bytes = _pair()
    left_evidence, right_evidence = evidence
    shared_bytes = b"the same runtime artifact bytes"

    left_map = dict(left_evidence.artifacts)
    right_map = dict(right_evidence.artifacts)
    left_map[IndependenceDimension.IMPLEMENTATION] = frozenset(
        {ArtifactFingerprint.from_bytes("wrapper-a", shared_bytes, kind="source")}
    )
    right_map[IndependenceDimension.BACKEND] = frozenset(
        {ArtifactFingerprint.from_bytes("binary-b", shared_bytes, kind="binary")}
    )
    left_evidence = RouteIndependenceEvidence(
        left.route_id, left.dependencies.digest, left_map  # type: ignore[union-attr]
    )
    right_evidence = RouteIndependenceEvidence(
        right.route_id, right.dependencies.digest, right_map  # type: ignore[union-attr]
    )
    left_bytes = dict(artifact_bytes["left"])
    right_bytes = dict(artifact_bytes["right"])
    left_bytes[IndependenceDimension.IMPLEMENTATION] = {"wrapper-a": shared_bytes}
    right_bytes[IndependenceDimension.BACKEND] = {"binary-b": shared_bytes}

    report = assess_independence_evidence(
        (left, right),
        (left_evidence, right_evidence),
        artifact_bytes={"left": left_bytes, "right": right_bytes},
    )
    assert report.all_routes_verified
    assert not report.artifact_disjoint
    assert not report.strongly_independent
    assert report.shared_artifacts[0].routes == ("left", "right")
    assert set(report.shared_artifacts[0].names) == {"wrapper-a", "binary-b"}


def test_evidence_must_bind_the_exact_dependency_declaration():
    route = _route("left", "a")
    evidence, artifact_bytes = _evidence(route, 1)
    forged = RouteIndependenceEvidence(
        route_id=route.route_id,
        dependency_digest="0" * 64,
        artifacts=evidence.artifacts,
    )
    report = assess_independence_evidence(
        (route,), (forged,), artifact_bytes={route.route_id: artifact_bytes}
    )
    assert not report.all_routes_verified
    assert "evidence binds dependency digest" in report.route_findings[0][1][0]


def test_every_solver_independence_dimension_requires_artifact_evidence():
    route = _route("left", "a")
    evidence, artifact_bytes = _evidence(route, 1)
    incomplete = dict(evidence.artifacts)
    del incomplete[IndependenceDimension.BACKEND]
    item = RouteIndependenceEvidence(
        route.route_id,
        route.dependencies.digest,  # type: ignore[union-attr]
        incomplete,
    )
    report = assess_independence_evidence(
        (route,), (item,), artifact_bytes={route.route_id: artifact_bytes}
    )
    assert not report.all_routes_verified
    assert any("backend" in reason for reason in report.route_findings[0][1])


def test_missing_route_evidence_is_unverified_not_independent_by_silence():
    left, right, evidence, artifact_bytes = _pair()
    report = assess_independence_evidence(
        (left, right), evidence[:1], artifact_bytes=artifact_bytes
    )
    assert not report.all_routes_verified
    assert not report.strongly_independent
    assert dict(report.route_findings)["right"] == ("no artifact evidence supplied",)


def test_extra_evidence_for_a_route_not_compared_is_refused():
    left, right, evidence, artifact_bytes = _pair()
    with pytest.raises(ScientificValidationError, match="not being compared"):
        assess_independence_evidence(
            (left,), evidence, artifact_bytes=artifact_bytes
        )


def test_extra_bytes_for_a_route_not_compared_are_refused():
    left, right, evidence, artifact_bytes = _pair()
    with pytest.raises(ScientificValidationError, match="artifact bytes supplied"):
        assess_independence_evidence(
            (left,), evidence[:1], artifact_bytes=artifact_bytes
        )


def test_route_evidence_round_trips_but_must_be_reverified_against_bytes():
    route = _route("left", "a")
    evidence, artifact_bytes = _evidence(route, 1)
    restored = RouteIndependenceEvidence.from_dict(evidence.to_dict())
    assert restored == evidence
    assert restored.evidence_gap(route)
    assert restored.evidence_gap(route, artifact_bytes) == ()


def test_two_routes_are_required_even_when_one_routes_evidence_is_verified():
    route = _route("left", "a")
    evidence, artifact_bytes = _evidence(route, 1)
    report = assess_independence_evidence(
        (route,),
        (evidence,),
        artifact_bytes={route.route_id: artifact_bytes},
    )
    assert report.all_routes_verified
    assert not report.strongly_independent
    with pytest.raises(ScientificValidationError, match="at least two"):
        require_strong_independence(
            (route,),
            (evidence,),
            artifact_bytes={route.route_id: artifact_bytes},
        )
