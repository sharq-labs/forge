"""Trusted consensus requires scientific agreement and verified artifact bytes."""

from __future__ import annotations

import pytest

from engcore.domains.electrical.dc_consensus import DC_CONSENSUS_THRESHOLDS
from engcore.execution.consensus import TrustedConsensusGate
from engcore.scientific.consensus import (
    CrossSolverConsensus,
    IndependenceDimension,
    SOLVER_INDEPENDENCE_DIMENSIONS,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.independence_evidence import (
    ArtifactFingerprint,
    RouteIndependenceEvidence,
)
from engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    bound_over,  # IND-02: a level needs results, not a mapping of numbers
    route,
    route_declarations_for_tests,
)


def _consensus(*, agree: bool = True, complete: bool = True) -> CrossSolverConsensus:
    routes = (route("a"), route("b"))
    values = {
        "a": {"x": 1.0, **({"y": 2.0} if complete else {})},
        "b": {"x": 1.0 if agree else 1.5, "y": 2.0},
    }
    return bound_over(
        consensus_id="trusted-gate-test",
        routes=routes,
        values=values,
        thresholds=DC_CONSENSUS_THRESHOLDS,
        tolerance_key="agreement_rel_tol",
        required_outputs=("x", "y"),
    )


def _evidence_for(consensus: CrossSolverConsensus):
    records = []
    bytes_by_route = {}
    for route_record in consensus.routes:
        assert route_record.dependencies is not None
        canonical = route_record.dependencies.canonical()
        artifacts = {}
        route_bytes = {}
        for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
            dimension_artifacts = set()
            dimension_bytes = {}
            for index, dependency_identity in enumerate(sorted(canonical[dimension])):
                name = f"{route_record.route_id}-{dimension.value}-{index}"
                payload = (
                    f"artifact:{route_record.route_id}:{dimension.value}:"
                    f"{dependency_identity}"
                ).encode()
                dimension_artifacts.add(
                    ArtifactFingerprint.from_bytes(
                        name,
                        payload,
                        kind="test-artifact",
                        dependency_identity=dependency_identity,
                    )
                )
                dimension_bytes[name] = payload
            artifacts[dimension] = frozenset(dimension_artifacts)
            route_bytes[dimension] = dimension_bytes
        records.append(
            RouteIndependenceEvidence(
                route_id=route_record.route_id,
                dependency_digest=route_record.dependencies.digest,
                artifacts=artifacts,
            )
        )
        bytes_by_route[route_record.route_id] = route_bytes
    return tuple(records), bytes_by_route


def test_scientific_consensus_and_verified_disjoint_artifacts_keep_cross_solver_level():
    consensus = _consensus()
    evidence, artifact_bytes = _evidence_for(consensus)
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED

    decision = TrustedConsensusGate().assess(
        consensus,
        evidence,
        artifact_bytes=artifact_bytes,
    )

    assert decision.validated
    assert decision.independence.strongly_independent
    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert decision.check.earns_its_level
    assert any("artifact independence" in line for line in decision.check.evidence)
    assert TrustedConsensusGate().require_validated(
        consensus,
        evidence,
        artifact_bytes=artifact_bytes,
    ).establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_digest_declarations_without_bytes_withhold_trusted_level():
    consensus = _consensus()
    evidence, _ = _evidence_for(consensus)

    decision = TrustedConsensusGate().assess(consensus, evidence)

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert not decision.validated
    assert "no artifact bytes supplied" in decision.check.detail


def test_forged_fingerprint_cannot_keep_cross_solver_level():
    consensus = _consensus()
    evidence, artifact_bytes = _evidence_for(consensus)
    left, right = evidence
    artifacts = dict(left.artifacts)
    genuine = next(iter(artifacts[IndependenceDimension.IMPLEMENTATION]))
    artifacts[IndependenceDimension.IMPLEMENTATION] = frozenset(
        {
            ArtifactFingerprint(
                "f" * 64,
                genuine.name,
                kind=genuine.kind,
                dependency_identity=genuine.dependency_identity,
            )
        }
    )
    forged = RouteIndependenceEvidence(
        left.route_id,
        left.dependency_digest,
        artifacts,
    )

    decision = TrustedConsensusGate().assess(
        consensus,
        (forged, right),
        artifact_bytes=artifact_bytes,
    )

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert not decision.validated
    assert "supplied bytes hash to" in decision.check.detail


def test_missing_route_artifact_evidence_downgrades_pass_without_rewriting_outcome():
    consensus = _consensus()
    evidence, artifact_bytes = _evidence_for(consensus)

    decision = TrustedConsensusGate().assess(
        consensus,
        evidence[:1],
        artifact_bytes=artifact_bytes,
    )

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert not decision.validated
    assert "no artifact evidence supplied" in decision.check.detail
    with pytest.raises(ScientificValidationError, match="not established"):
        decision.require_validated()


def test_shared_verified_bytes_defeat_trusted_independence_even_under_different_labels():
    consensus = _consensus()
    evidence, artifact_bytes = _evidence_for(consensus)
    left, right = evidence
    shared_bytes = b"same-runtime-bytes"

    left_route, right_route = consensus.routes
    assert left_route.dependencies is not None and right_route.dependencies is not None
    left_identity = next(
        iter(left_route.dependencies.canonical()[IndependenceDimension.IMPLEMENTATION])
    )
    right_identity = next(
        iter(right_route.dependencies.canonical()[IndependenceDimension.BACKEND])
    )

    left_artifacts = dict(left.artifacts)
    right_artifacts = dict(right.artifacts)
    left_artifacts[IndependenceDimension.IMPLEMENTATION] = frozenset(
        {
            ArtifactFingerprint.from_bytes(
                "wrapper-a",
                shared_bytes,
                kind="source",
                dependency_identity=left_identity,
            )
        }
    )
    right_artifacts[IndependenceDimension.BACKEND] = frozenset(
        {
            ArtifactFingerprint.from_bytes(
                "binary-b",
                shared_bytes,
                kind="binary",
                dependency_identity=right_identity,
            )
        }
    )
    evidence = (
        RouteIndependenceEvidence(
            left.route_id, left.dependency_digest, left_artifacts
        ),
        RouteIndependenceEvidence(
            right.route_id, right.dependency_digest, right_artifacts
        ),
    )
    left_bytes = dict(artifact_bytes[left.route_id])
    right_bytes = dict(artifact_bytes[right.route_id])
    left_bytes[IndependenceDimension.IMPLEMENTATION] = {"wrapper-a": shared_bytes}
    right_bytes[IndependenceDimension.BACKEND] = {"binary-b": shared_bytes}

    decision = TrustedConsensusGate().assess(
        consensus,
        evidence,
        artifact_bytes={left.route_id: left_bytes, right.route_id: right_bytes},
    )

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert not decision.independence.artifact_disjoint
    assert "share implementation/runtime artifacts" in decision.check.detail


def test_artifact_evidence_cannot_promote_an_incomplete_consensus():
    consensus = _consensus(complete=False)
    evidence, artifact_bytes = _evidence_for(consensus)
    assert consensus.establishes is None

    decision = TrustedConsensusGate().assess(
        consensus,
        evidence,
        artifact_bytes=artifact_bytes,
    )

    assert decision.independence.strongly_independent
    assert decision.check.establishes is None
    assert "cannot promote" in decision.check.detail


def test_artifact_evidence_cannot_promote_a_scientific_disagreement():
    consensus = _consensus(agree=False)
    evidence, artifact_bytes = _evidence_for(consensus)
    assert consensus.to_check().outcome is ValidationOutcome.FAIL

    decision = TrustedConsensusGate().assess(
        consensus,
        evidence,
        artifact_bytes=artifact_bytes,
    )

    assert decision.independence.strongly_independent
    assert decision.check.outcome is ValidationOutcome.FAIL
    assert decision.check.establishes is None


def test_evidence_for_a_stale_dependency_declaration_withholds_the_level():
    consensus = _consensus()
    evidence, artifact_bytes = _evidence_for(consensus)
    left, right = evidence
    stale = RouteIndependenceEvidence(
        route_id=left.route_id,
        dependency_digest="0" * 64,
        artifacts=left.artifacts,
    )

    decision = TrustedConsensusGate().assess(
        consensus,
        (stale, right),
        artifact_bytes=artifact_bytes,
    )

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert "evidence binds dependency digest" in decision.check.detail


def test_unknown_evidence_route_is_refused_instead_of_ignored():
    consensus = _consensus()
    evidence, artifact_bytes = _evidence_for(consensus)
    evidence = list(evidence)
    sample = evidence[0]
    evidence.append(
        RouteIndependenceEvidence(
            route_id="ghost",
            dependency_digest=sample.dependency_digest,
            artifacts=sample.artifacts,
        )
    )

    with pytest.raises(ScientificValidationError, match="not being compared"):
        TrustedConsensusGate().assess(
            consensus,
            evidence,
            artifact_bytes=artifact_bytes,
        )


def _declared_consensus(*routes) -> CrossSolverConsensus:
    return bound_over(
        consensus_id="trusted-gate-relabelling",
        routes=routes,
        values={item.route_id: {"x": 1.0, "y": 2.0} for item in routes},
        thresholds=DC_CONSENSUS_THRESHOLDS,
        tolerance_key="agreement_rel_tol",
        required_outputs=("x", "y"),
    )


def _backend_evidence(route_record, backend_rows):
    """Distinct genuine artifacts everywhere except BACKEND, which ``backend_rows`` supplies."""
    canonical = route_record.dependencies.canonical()
    artifacts, route_bytes = {}, {}
    for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
        rows = backend_rows if dimension is IndependenceDimension.BACKEND else [
            (f"{route_record.route_id}-{dimension.value}-{index}",
             f"artifact:{route_record.route_id}:{identity}".encode(), identity)
            for index, identity in enumerate(sorted(canonical[dimension]))
        ]
        artifacts[dimension] = frozenset(
            ArtifactFingerprint.from_bytes(name, payload, kind="binary", dependency_identity=identity)
            for name, payload, identity in rows
        )
        route_bytes[dimension] = {name: payload for name, payload, _ in rows}
    return (
        RouteIndependenceEvidence(route_record.route_id, route_record.dependencies.digest, artifacts),
        route_bytes,
    )


def test_relabelling_a_routes_own_backend_as_its_shared_library_cannot_keep_the_level():
    """The Round 1A bypass, end to end through the trusted gate.

    Both routes really load one linear-algebra library, declared under a
    different identity in each (``ext:vendor-a:linear-algebra`` and
    ``ext:vendor-b:linear-algebra``) -- the declaration-level blind spot artifact
    evidence exists for. Presenting that library's bytes is refused as shared
    machinery. Before Round 1A, presenting each route's OWN backend bytes a
    second time, bound to the linear-algebra identity, kept
    CROSS_SOLVER_VALIDATED: every identity carried a verified label, and the
    shared-artifact check only compared routes with each other.
    """
    a = route("a", backend={"ext:test:a:backend", "ext:vendor-a:linear-algebra"})
    b = route("b", backend={"ext:test:b:backend", "ext:vendor-b:linear-algebra"})
    consensus = _declared_consensus(a, b)
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED

    own = {"a": b"route a's own backend binary", "b": b"route b's own backend binary"}
    shared_library = b"the one linear-algebra binary both routes load"

    def decide(second_payload):
        records = [
            _backend_evidence(item, [
                (f"{item.route_id}-backend.so", own[item.route_id], f"ext:test:{item.route_id}:backend"),
                (f"{item.route_id}-linalg.so", second_payload(item.route_id),
                 f"ext:vendor-{item.route_id}:linear-algebra"),
            ])
            for item in (a, b)
        ]
        return TrustedConsensusGate().assess(
            consensus,
            [record for record, _ in records],
            artifact_bytes={"a": records[0][1], "b": records[1][1]},
        )

    relabelled = decide(lambda route_id: own[route_id])
    assert relabelled.validated is False
    assert relabelled.check.establishes is not ValidationLevel.CROSS_SOLVER_VALIDATED
    assert not relabelled.independence.all_routes_verified
    assert "cannot establish more than one declared dependency" in relabelled.check.detail
    assert relabelled.check.outcome is ValidationOutcome.PASS  # the agreement itself is not rewritten

    honest_but_shared = decide(lambda route_id: shared_library)
    assert honest_but_shared.validated is False
    assert honest_but_shared.independence.all_routes_verified
    assert honest_but_shared.independence.shared_artifacts

    distinct = decide(lambda route_id: f"route {route_id}'s own linear-algebra binary".encode())
    assert distinct.validated is True
    assert distinct.check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert distinct.independence.strongly_independent
    assert any(
        line.endswith("evidences ext:vendor-a:linear-algebra") for line in distinct.check.evidence
    )
    assert "does not show the routes used those artifacts at runtime" in distinct.check.detail
