"""Mutation kill-checks for the new validation/replay/UQ/V&V guards."""

from __future__ import annotations

import pytest

import engcore.scientific.validation_core.pipeline as validation_pipeline_module
import engcore.scientific.validation_core.gate as validation_gate_module
import engcore.scientific.replay_core.verifier as replay_verifier_module
import engcore.credibility.evidence_graph.policy as evidence_policy_module
import engcore.uq.model_form.promotion as model_form_promotion_module
import engcore.scientific.verification.adjudication as verification_adjudication_module
import engcore.scientific.certification_core.verifier as certification_verifier_module
import engcore.execution.orchestration.retry as retry_module

from engcore.credibility.evidence_graph import (
    EvidenceAuthority, EvidenceGraph, EvidenceNode, assess_graph,
)
from engcore.execution.orchestration import (
    AttemptState, ExecutionBudget, RetryDecision, SimulationAttempt, decide_retry,
)
from engcore.scientific.certification_core import (
    CertificationArtifact, CertificationGateResult, CertificationProfile,
    CertificationRecord, verify_certification_record,
)
from engcore.scientific.replay_core import (
    ArtifactIdentity, ReplayBundle, RuntimeEnvironment, verify_replay_bundle,
)
from engcore.scientific.validation_core import (
    StageResult, ValidationDecision, ValidationPipeline, ValidationReport,
    ValidationStage,
)
from engcore.scientific.verification import (
    IndependenceEvidence, IndependenceLevel, RouteComparison,
    VerificationDecision, adjudicate,
)
from engcore.uq.model_form import (
    ModelFormEstimate, ModelFormPolicy, ModelFormStatus,
    PromotionDecision, assess_promotion,
)


def validation_missing_stage_is_not_accepted():
    report = ValidationPipeline().assess(StageResult(ValidationStage.CONTRACT, True))
    assert report.decision is ValidationDecision.INCOMPLETE


def replay_environment_drift_is_not_verified():
    artifact = ArtifactIdentity("law", "x", "a" * 64)
    expected = ReplayBundle(
        "run", (artifact,), RuntimeEnvironment("Python 3.12", "linux", "b" * 64), 7
    )
    actual = ReplayBundle(
        "run", (artifact,), RuntimeEnvironment("Python 3.12", "linux", "c" * 64), 7
    )
    assert not replay_verifier_module.verify_replay_bundle(expected, actual).verified


def unknown_evidence_authority_is_not_admissible():
    graph = EvidenceGraph((
        EvidenceNode("e", EvidenceAuthority.UNKNOWN, "d" * 64, "unclassified"),
    ))
    assert not evidence_policy_module.assess_graph(graph).admissible


def unvalidated_model_form_is_not_promotable():
    estimate = ModelFormEstimate(
        ModelFormStatus.CALIBRATED_UNVALIDATED,
        1.0,
        ("c1", "c2"),
        (),
        None,
        "no holdout",
    )
    assert model_form_promotion_module.assess_promotion(estimate, ModelFormPolicy()).decision is PromotionDecision.REFUSED


def agreement_without_independence_is_not_verified():
    comparisons = (RouteComparison("primary", "verify", True, 0.0),)
    independence = (
        IndependenceEvidence(IndependenceLevel.PARTIAL, ("shared_model",)),
    )
    assert verification_adjudication_module.adjudicate(comparisons, independence) is VerificationDecision.INSUFFICIENT_INDEPENDENCE


def missing_certification_gate_is_not_verified():
    profile = CertificationProfile("prod", ("fast", "scientific"))
    record = CertificationRecord(
        "a" * 40,
        profile,
        (CertificationGateResult("fast", True, "b" * 64),),
        (CertificationArtifact("report", "c" * 64),),
    )
    assert not certification_verifier_module.verify_certification_record(record).verified


def retry_budget_is_not_bypassed():
    attempt = SimulationAttempt("a", AttemptState.FAILED, 0, "solver_failure")
    assert retry_module.decide_retry(attempt, 1, ExecutionBudget(max_attempts=1)).decision is RetryDecision.STOP_BUDGET


MUTANTS = (
    (
        "validation_missing_stage_accepted",
        validation_missing_stage_is_not_accepted,
        validation_pipeline_module,
        "gate_validation",
        lambda results, policy: ValidationReport(ValidationDecision.ACCEPTED, tuple(results)),
    ),
    (
        "replay_environment_ignored",
        replay_environment_drift_is_not_verified,
        replay_verifier_module,
        "verify_replay_bundle",
        lambda expected, actual: replay_verifier_module.ReplayVerification(True, ()),
    ),
    (
        "unknown_evidence_authority_admitted",
        unknown_evidence_authority_is_not_admissible,
        evidence_policy_module,
        "assess_graph",
        lambda graph, policy=evidence_policy_module.EvidenceGraphPolicy(): evidence_policy_module.EvidenceGraphAssessment(True, ()),
    ),
    (
        "model_form_holdout_ignored",
        unvalidated_model_form_is_not_promotable,
        model_form_promotion_module,
        "assess_promotion",
        lambda estimate, policy: model_form_promotion_module.PromotionReport(PromotionDecision.PROMOTABLE, ()),
    ),
    (
        "independence_gate_removed",
        agreement_without_independence_is_not_verified,
        verification_adjudication_module,
        "adjudicate",
        lambda comparisons, independence: VerificationDecision.VERIFIED,
    ),
    (
        "required_certification_gate_ignored",
        missing_certification_gate_is_not_verified,
        certification_verifier_module,
        "verify_certification_record",
        lambda record, policy=certification_verifier_module.CertificationPolicy(): certification_verifier_module.CertificationVerification(True, ()),
    ),
    (
        "retry_budget_ignored",
        retry_budget_is_not_bypassed,
        retry_module,
        "decide_retry",
        lambda attempt, attempt_count, budget: retry_module.RetryAssessment(RetryDecision.RETRY, "mutant"),
    ),
)


@pytest.mark.parametrize("name,property_fn,module,attribute,replacement", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_new_core_guard_mutations_are_killed(monkeypatch, name, property_fn, module, attribute, replacement):
    property_fn()
    with monkeypatch.context() as patched:
        patched.setattr(module, attribute, replacement)
        with pytest.raises(AssertionError):
            property_fn()
