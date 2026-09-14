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
    route,
    route_declarations_for_tests,
)


def _consensus(*, agree: bool = True, complete: bool = True) -> CrossSolverConsensus:
    routes = (route("a"), route("b"))
    values = {
        "a": {"x": 1.0, **({"y": 2.0} if complete else {})},
        "b": {"x": 1.0 if agree else 1.5, "y": 2.0},
    }
    return CrossSolverConsensus.over(
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
        artifacts = {}
        route_bytes = {}
        for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
            name = f"{route_record.route_id}-{dimension.value}"
            payload = f"artifact:{route_record.route_id}:{dimension.value}".encode()
            artifacts[dimension] = frozenset(
                {
                    ArtifactFingerprint.from_bytes(
                        name,
                        payload,
                        kind="test-artifact",
                    )
                }
            )
            route_bytes[dimension] = {name: payload}
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

    left_artifacts = dict(left.artifacts)
    right_artifacts = dict(right.artifacts)
    left_artifacts[IndependenceDimension.IMPLEMENTATION] = frozenset(
        {ArtifactFingerprint.from_bytes("wrapper-a", shared_bytes, kind="source")}
    )
    right_artifacts[IndependenceDimension.BACKEND] = frozenset(
        {ArtifactFingerprint.from_bytes("binary-b", shared_bytes, kind="binary")}
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
