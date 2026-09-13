"""Trusted consensus requires both scientific and artifact independence evidence."""

from __future__ import annotations

import hashlib

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


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _evidence_for(consensus: CrossSolverConsensus):
    records = []
    for route_record in consensus.routes:
        assert route_record.dependencies is not None
        artifacts = {
            dimension: frozenset(
                {
                    ArtifactFingerprint(
                        digest=_digest(f"{route_record.route_id}:{dimension.value}"),
                        name=f"{route_record.route_id}-{dimension.value}",
                        kind="test-artifact",
                    )
                }
            )
            for dimension in SOLVER_INDEPENDENCE_DIMENSIONS
        }
        records.append(
            RouteIndependenceEvidence(
                route_id=route_record.route_id,
                dependency_digest=route_record.dependencies.digest,
                artifacts=artifacts,
            )
        )
    return tuple(records)


def test_scientific_consensus_and_disjoint_artifacts_keep_cross_solver_level():
    consensus = _consensus()
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED

    decision = TrustedConsensusGate().assess(consensus, _evidence_for(consensus))

    assert decision.validated
    assert decision.independence.strongly_independent
    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert decision.check.earns_its_level
    assert any("artifact independence" in line for line in decision.check.evidence)
    assert TrustedConsensusGate().require_validated(
        consensus, _evidence_for(consensus)
    ).establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_missing_route_artifact_evidence_downgrades_pass_without_rewriting_outcome():
    consensus = _consensus()
    evidence = _evidence_for(consensus)[:1]

    decision = TrustedConsensusGate().assess(consensus, evidence)

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert not decision.validated
    assert "no artifact evidence supplied" in decision.check.detail
    with pytest.raises(ScientificValidationError, match="not established"):
        decision.require_validated()


def test_shared_artifact_bytes_defeat_trusted_independence_even_under_different_labels():
    consensus = _consensus()
    left, right = _evidence_for(consensus)
    shared = _digest("same-runtime-bytes")

    left_artifacts = dict(left.artifacts)
    right_artifacts = dict(right.artifacts)
    left_artifacts[IndependenceDimension.IMPLEMENTATION] = frozenset(
        {ArtifactFingerprint(shared, "wrapper-a", kind="source")}
    )
    right_artifacts[IndependenceDimension.BACKEND] = frozenset(
        {ArtifactFingerprint(shared, "binary-b", kind="binary")}
    )
    evidence = (
        RouteIndependenceEvidence(
            left.route_id, left.dependency_digest, left_artifacts
        ),
        RouteIndependenceEvidence(
            right.route_id, right.dependency_digest, right_artifacts
        ),
    )

    decision = TrustedConsensusGate().assess(consensus, evidence)

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert not decision.independence.artifact_disjoint
    assert "share implementation/runtime artifacts" in decision.check.detail


def test_artifact_evidence_cannot_promote_an_incomplete_consensus():
    consensus = _consensus(complete=False)
    assert consensus.establishes is None

    decision = TrustedConsensusGate().assess(consensus, _evidence_for(consensus))

    assert decision.independence.strongly_independent
    assert decision.check.establishes is None
    assert "cannot promote" in decision.check.detail


def test_artifact_evidence_cannot_promote_a_scientific_disagreement():
    consensus = _consensus(agree=False)
    assert consensus.to_check().outcome is ValidationOutcome.FAIL

    decision = TrustedConsensusGate().assess(consensus, _evidence_for(consensus))

    assert decision.independence.strongly_independent
    assert decision.check.outcome is ValidationOutcome.FAIL
    assert decision.check.establishes is None


def test_evidence_for_a_stale_dependency_declaration_withholds_the_level():
    consensus = _consensus()
    left, right = _evidence_for(consensus)
    stale = RouteIndependenceEvidence(
        route_id=left.route_id,
        dependency_digest="0" * 64,
        artifacts=left.artifacts,
    )

    decision = TrustedConsensusGate().assess(consensus, (stale, right))

    assert decision.check.outcome is ValidationOutcome.PASS
    assert decision.check.establishes is None
    assert "evidence binds dependency digest" in decision.check.detail


def test_unknown_evidence_route_is_refused_instead_of_ignored():
    consensus = _consensus()
    evidence = list(_evidence_for(consensus))
    sample = evidence[0]
    evidence.append(
        RouteIndependenceEvidence(
            route_id="ghost",
            dependency_digest=sample.dependency_digest,
            artifacts=sample.artifacts,
        )
    )

    with pytest.raises(ScientificValidationError, match="not being compared"):
        TrustedConsensusGate().assess(consensus, evidence)
