from __future__ import annotations

import math
import pytest

from engcore.credibility.assurance_bundle import AssuranceBundle
from engcore.credibility.evidence_graph import (
    EvidenceAuthority, EvidenceEdge, EvidenceGraph, EvidenceNode, EvidenceRelation,
)
from engcore.execution.orchestration import AttemptState, SimulationAttempt
from engcore.scientific.certification_core import CertificationGateResult
from engcore.scientific.replay_core import ArtifactIdentity, ReplayTolerance, compare_numeric
from engcore.scientific.validation_core import (
    StageResult, ValidationIssue, ValidationSeverity, ValidationStage,
)
from engcore.scientific.verification import IndependenceEvidence, IndependenceLevel
from engcore.uq.budget import Correlation
from engcore.uq.model_form import ModelFormEstimate, ModelFormStatus


def test_assurance_bundle_refuses_non_digest_identity():
    with pytest.raises(ValueError, match="SHA-256"):
        AssuranceBundle("x", "b"*64, "c"*64, "d"*64, "e"*64, "f"*64)


def test_evidence_edge_cannot_reference_itself():
    with pytest.raises(Exception):
        EvidenceEdge("a", "a", EvidenceRelation.SUPPORTS)


def test_validation_stage_cannot_pass_with_fatal_issue():
    issue = ValidationIssue("fatal", "fatal condition", ValidationSeverity.FATAL)
    with pytest.raises(Exception):
        StageResult(ValidationStage.CONTRACT, True, (issue,))


def test_replay_nonfinite_values_never_match():
    assert not compare_numeric(math.nan, math.nan, ReplayTolerance()).matched
    assert not compare_numeric(math.inf, math.inf, ReplayTolerance()).matched


def test_certification_digest_shape_is_validated():
    with pytest.raises(ValueError):
        CertificationGateResult("fast", True, "short")


def test_full_independence_cannot_list_shared_components():
    with pytest.raises(ValueError):
        IndependenceEvidence("p", "v", IndependenceLevel.EXTERNAL, ("same_solver",))


def test_invalid_correlation_above_one_is_refused():
    with pytest.raises(ValueError):
        Correlation("a", "b", 1.01)


def test_validated_model_form_cannot_have_zero_half_width():
    with pytest.raises(ValueError):
        ModelFormEstimate("temperature", "kelvin", ModelFormStatus.VALIDATED, 0.0, ("c1","c2"), ("v1","v2"), 1.0, "bad")


def test_failed_simulation_attempt_requires_failure_identity():
    with pytest.raises(ValueError):
        SimulationAttempt("a", AttemptState.DIVERGED)
