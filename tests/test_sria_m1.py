"""SRIA V0.1 — M1 contract and trust-boundary tests.

Runs under pytest, and standalone via ``python -m tests.test_sria_m1`` so the
suite does not depend on pytest being installed.

The twelve numbered tests below are the M1 acceptance conditions. They are
written as *boundary* proofs rather than API smoke tests: each one tries to do
the wrong thing and asserts that the architecture refuses.
"""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

from src.engcore.scientific import (
    ProvenanceRecord,
    Quantity,
    ScientificResult,
    Uncertainty,
    ValidationLevel,
)
from src.engcore.sria.admission import (
    DecisionBinding,
    _issue_registrar_capability,
)
from src.engcore.sria import (
    AcceptanceCriterion,
    AdmissionAttempt,
    AdmissionAuthority,
    AdmissionAuthorityError,
    AdmissionAuthorityRegistry,
    AdmissionDeclaration,
    AdmissionError,
    AdmissionOutcome,
    Assessment,
    AssessmentProvenance,
    AssessmentVerdict,
    AttributedCause,
    BeliefUpdateGateway,
    BlameAssignment,
    BeliefWriteViolation,
    CalibrationKeyContamination,
    CampaignCharter,
    CampaignType,
    CensoringType,
    CharterAmendment,
    CharterError,
    ClaimBinding,
    ClaimType,
    ConfidenceRequirement,
    DecisionProvenance,
    DetectedBy,
    DiscrepancyKind,
    Disposition,
    DomainPackContractError,
    EnvironmentSignature,
    Evidence,
    EvidenceProvenance,
    EvidenceStatus,
    ExecutorType,
    FeasibilityViolation,
    FidelityLevel,
    HardFeasibilityGate,
    LifecycleViolation,
    ModelDiscrepancy,
    OutcomeContractError,
    ReservedNotImplemented,
    ResearchAction,
    Retryability,
    RunOutcome,
    ScientificBelief,
    SourceClass,
    StructureComponent,
    StructureSignature,
    SubjectModel,
    TerminalDecision,
    UncertaintyChannel,
    UncertaintyContractError,
    UncertaintyDeclaration,
    build_calibration_key,
    guard_from_packs,
    require_executable,
    require_implemented_source,
    validate_domain_pack,
)
from src.engcore.sria.actions import FeasibilityVerdict
from src.engcore.sria.trust import assert_no_llm_dependencies, find_forbidden_imports

REPO_ROOT = Path(__file__).resolve().parents[1]
SCIENTIFIC_DIR = REPO_ROOT / "src" / "engcore" / "scientific"
SRIA_DIR = REPO_ROOT / "src" / "engcore" / "sria"


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


# =====================================================================
# Fixtures — deterministic, synthetic, no physical domain
# =====================================================================

def make_uncertainty() -> UncertaintyDeclaration:
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="synthetic fixture asserts no model-form discrepancy",
        ),
        channels={UncertaintyChannel.NUMERICAL: Uncertainty.unknown()},
    )


def make_evidence(evidence_id: str = "ev-1") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="peak_response"),
        claim_payload={"value": 1.5, "units": "volt"},
        uncertainty=make_uncertainty(),
        provenance_ref="run-001",
        domain_pack_ref="demo.pack",
    )


def make_assessment(assessment_id: str = "as-1") -> Assessment:
    return Assessment(
        verdict=AssessmentVerdict.PASS,
        provenance=AssessmentProvenance(
            assessment_id=assessment_id,
            critic_id="critic.residual",
            critic_version="1.0",
        ),
        rationale="residual within declared tolerance",
    )


#: Test-only admission authority. Production code obtains one from the Arbiter,
#: which M1 does not implement; a fixed secret keeps these tests deterministic.
TEST_AUTHORITY = AdmissionAuthority("arbiter.test", secret="m1-test-secret")


def make_registry() -> AdmissionAuthorityRegistry:
    return AdmissionAuthorityRegistry([TEST_AUTHORITY])


def make_gateway() -> BeliefUpdateGateway:
    return BeliefUpdateGateway(authorities=make_registry())


#: M3.1 required an accepting declaration to name a VALID assurance decision.
#: M3.2 made that binding non-forgeable, and M3.3 made the mechanism one-way:
#: the Arbiter draws a random code and registers only its commitment, so the
#: authority holds no key material. M1's tests play the Arbiter role directly —
#: without importing the assurance layer, which sits above this one.
TEST_ARBITER_ID = "arbiter.m1.synthetic"
#: M3.4: registration needs a registrar capability. These tests play the
#: Arbiter role, so they hold one — obtaining it is exactly the seam an
#: ordinary AdmissionAuthority holder does not have.
TEST_REGISTRAR = _issue_registrar_capability(TEST_ARBITER_ID)


def valid_binding(evidence: Evidence, verdict: str = "valid") -> DecisionBinding:
    """A genuine capability for this record, minted as a real Arbiter would."""
    decision_id = f"dec-{evidence.evidence_id}"
    decision_hash = f"hash-{evidence.evidence_id}"
    payload = AdmissionAuthority.authorization_payload(
        decision_id=decision_id,
        decision_hash=decision_hash,
        subject_record_hash=evidence.record_hash,
        verdict=verdict,
        policy_id="sria.arbiter",
        policy_version="test",
        arbiter_id=TEST_ARBITER_ID,
    )
    code = secrets.token_hex(32)
    TEST_AUTHORITY.register_authorization(
        TEST_REGISTRAR, AdmissionAuthority.commitment_for(code, payload), payload
    )
    return DecisionBinding(
        decision_id=decision_id,
        decision_hash=decision_hash,
        verdict=verdict,
        policy_id="sria.arbiter",
        policy_version="test",
        arbiter_id=TEST_ARBITER_ID,
        authorization_code=code,
    )


def make_admission(
    evidence: Evidence, admitted: bool = True
) -> AdmissionDeclaration:
    """A properly issued declaration, bound to that evidence record."""
    return TEST_AUTHORITY.issue(
        admitted=admitted,
        subject_record_hash=evidence.record_hash,
        authorization=valid_binding(evidence) if admitted else None,
        arbiter_version="0.1",
        rationale="all critics passed" if admitted else "critic failed",
    )


def assessed_evidence(evidence_id: str = "ev-1") -> Evidence:
    return make_evidence(evidence_id).with_assessment(make_assessment())


def accepted_evidence(evidence_id: str = "ev-1") -> Evidence:
    evidence = assessed_evidence(evidence_id)
    return evidence.admit(make_admission(evidence))


def make_scientific_result() -> ScientificResult:
    return ScientificResult(
        result_id="res-1",
        values={"peak_response": Quantity(1.5, "volt")},
        provenance=ProvenanceRecord(run_id="run-001"),
    )


class DemoPack:
    """Tiny pack proving the Domain Pack interface. Not a real domain."""

    pack_id = "demo.pack"
    pack_version = "0.1"

    def model_references(self):
        return ("demo.linear_response",)

    def parameter_semantics(self):
        return {"gain": "output per unit input"}

    def qois(self):
        return ("peak_response",)

    def scope(self):
        return None

    def assumptions(self):
        return ("linear response", "steady state")

    def fidelity_ladder(self):
        return (
            FidelityLevel(level_id="coarse", rank=0),
            FidelityLevel(level_id="fine", rank=1),
        )

    def extract_covariates(self, subject):
        # Computational covariates only — no physics names.
        return {"state_count": 4.0, "condition_estimate": 12.0}

    def domain_critics(self):
        return ()

    def semantic_terms(self):
        return ("peak_response", "gain", "demo.pack")


class OverreachingPack(DemoPack):
    """A pack that tries to own platform responsibilities."""

    def research_strategy(self):  # pragma: no cover - must be rejected first
        return "explore"


# =====================================================================
# 1. Raw simulation result cannot directly update belief
# =====================================================================

def test_raw_result_cannot_update_belief():
    gateway = make_gateway()
    result = make_scientific_result()

    _raises(BeliefWriteViolation, gateway.submit, result)
    # Not even a plain payload dict sneaks through.
    _raises(BeliefWriteViolation, gateway.submit, {"value": 1.5})
    _raises(BeliefWriteViolation, gateway.submit, None)
    assert len(gateway.belief) == 0


def test_belief_cannot_be_written_outside_gateway():
    belief = ScientificBelief()
    entry = object()

    # The write method exists but demands the gateway's unforgeable token.
    _raises(BeliefWriteViolation, belief._apply, "not-a-token", entry)
    _raises(BeliefWriteViolation, belief._apply, None, entry)
    assert len(belief) == 0


def test_gateway_token_cannot_be_forged():
    from src.engcore.sria.gateway import _GatewayToken

    _raises(BeliefWriteViolation, _GatewayToken)


# =====================================================================
# 2. Candidate evidence cannot influence belief before admission
# =====================================================================

def test_candidate_evidence_cannot_influence_belief():
    gateway = make_gateway()

    candidate = make_evidence()
    assert candidate.status is EvidenceStatus.CANDIDATE
    assert candidate.is_belief_bearing is False
    _raises(BeliefWriteViolation, gateway.submit, candidate)

    assessed = candidate.with_assessment(make_assessment())
    assert assessed.status is EvidenceStatus.ASSESSED
    _raises(BeliefWriteViolation, gateway.submit, assessed)

    # Storage is not acceptance: nothing reached belief.
    assert len(gateway.belief) == 0
    assert gateway.belief.keys() == ()


def test_refused_admission_does_not_reach_belief():
    gateway = make_gateway()
    assessed = assessed_evidence()
    refused = assessed.admit(make_admission(assessed, admitted=False))

    # M1.1: a declined admission is procedural, NOT a scientific verdict.
    assert refused.status is EvidenceStatus.ASSESSED
    assert refused.status is assessed.status
    _raises(BeliefWriteViolation, gateway.submit, refused)
    assert len(gateway.belief) == 0


def test_accepted_status_without_admission_is_refused():
    # Fabricate ACCEPTED status without an admission declaration.
    forged = Evidence(
        evidence_id="ev-forged",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="x"),
        claim_payload={"value": 1.0},
        uncertainty=make_uncertainty(),
        provenance_ref="run-001",
        domain_pack_ref="demo.pack",
        status=EvidenceStatus.ACCEPTED,
    )
    gateway = make_gateway()
    _raises(AdmissionError, gateway.submit, forged)


# =====================================================================
# M1.1 — admission failure is procedural, not epistemic
# =====================================================================

def test_declined_admission_does_not_invalidate_evidence():
    assessed = assessed_evidence()
    refused = assessed.admit(make_admission(assessed, admitted=False))

    # Scientific standing is untouched.
    assert refused.status is EvidenceStatus.ASSESSED
    assert refused.status is not EvidenceStatus.INVALID
    # No lifecycle event was emitted at all.
    assert refused.lifecycle_log == assessed.lifecycle_log
    # But the attempt is auditable.
    assert len(refused.admission_attempts) == 1
    attempt = refused.admission_attempts[0]
    assert attempt.outcome is AdmissionOutcome.REFUSED
    assert attempt.succeeded is False
    assert "critic failed" in attempt.reason

    # The evidence can still be admitted later by a fresh decision.
    later = refused.admit(make_admission(refused))
    assert later.status is EvidenceStatus.ACCEPTED
    assert len(later.admission_attempts) == 2


def test_invalidation_is_an_explicit_scientific_decision():
    assessed = assessed_evidence()
    invalidated = assessed.invalidate("model applied outside its validity domain")
    assert invalidated.status is EvidenceStatus.INVALID
    assert invalidated.lifecycle_log[-1].reason.startswith("model applied")

    # An unexplained invalidation is refused: INVALID is a verdict.
    _raises(LifecycleViolation, assessed.invalidate, "   ")


def test_gateway_rejection_leaves_scientific_standing_unchanged():
    gateway = make_gateway()
    stranger = AdmissionAuthority("arbiter.rogue", secret="not-registered")
    evidence = assessed_evidence()
    # An authority that has been told no commitment cannot sign this.
    _raises(
        AdmissionAuthorityError,
        stranger.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=valid_binding(evidence),
    )
    # Give the stranger its own registered commitment so it *can* sign, and
    # prove the gateway still refuses it for being an unregistered issuer.
    stranger_payload = AdmissionAuthority.authorization_payload(
        decision_id="d-stranger",
        decision_hash="h-stranger",
        subject_record_hash=evidence.record_hash,
        verdict="valid",
    )
    stranger_code = secrets.token_hex(32)
    stranger.register_authorization(
        _issue_registrar_capability("arbiter.stranger"),
        AdmissionAuthority.commitment_for(stranger_code, stranger_payload),
        stranger_payload,
    )
    fabricated = stranger.issue(
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=DecisionBinding(
            decision_id="d-stranger",
            decision_hash="h-stranger",
            verdict="valid",
            authorization_code=stranger_code,
        ),
        rationale="self-granted",
    )
    presented = evidence.admit(fabricated)
    assert presented.status is EvidenceStatus.ACCEPTED  # locally claimed

    _raises(AdmissionAuthorityError, gateway.submit, presented)

    # Belief untouched, and the evidence was NOT scientifically invalidated.
    assert len(gateway.belief) == 0
    assert presented.status is not EvidenceStatus.INVALID
    # The refusal is auditable at the gateway.
    assert len(gateway.rejection_log) == 1
    assert gateway.rejection_log[0].outcome is AdmissionOutcome.UNAUTHORIZED


# =====================================================================
# M1.1 — admission authority
# =====================================================================

def test_fabricated_admission_is_rejected():
    gateway = make_gateway()
    evidence = assessed_evidence()

    # 1. Hand-built declaration with no issuer signature at all.
    unsigned = AdmissionDeclaration(
        admitted=True,
        arbiter_id="arbiter.test",
        subject_record_hash=evidence.record_hash,
        authorization=valid_binding(evidence),
    )
    _raises(AdmissionAuthorityError, gateway.submit, evidence.admit(unsigned))

    # 2. Signature copied from a real declaration onto a forged one.
    genuine = make_admission(evidence)
    tampered = AdmissionDeclaration(
        admitted=True,
        arbiter_id="arbiter.test",
        subject_record_hash=evidence.record_hash,
        authorization=valid_binding(evidence),
        issuer_id=genuine.issuer_id,
        issued_signature=genuine.issued_signature,
        rationale="tampered rationale",
    )
    _raises(AdmissionAuthorityError, gateway.submit, evidence.admit(tampered))

    # 3. An unregistered authority. M3.2 stops this at issue(): the rogue
    #    recognises no Arbiter, so it cannot sign an accepting declaration at
    #    all — a stronger refusal than the gateway rejection M1.1 relied on.
    rogue = AdmissionAuthority("arbiter.rogue", secret="s")
    _raises(
        AdmissionAuthorityError,
        rogue.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=valid_binding(evidence),
    )

    # 4. A gateway trusting nobody admits nothing, even a valid declaration.
    empty = BeliefUpdateGateway()
    assert empty.authorities.authority_ids == ()
    _raises(AdmissionAuthorityError, empty.submit, accepted_evidence())
    assert len(empty.belief) == 0

    assert len(gateway.belief) == 0
    assert len(gateway.rejection_log) == 2


def test_authorized_admission_succeeds():
    gateway = make_gateway()
    evidence = accepted_evidence()
    entry = gateway.submit(evidence)
    assert entry.admitted_by == "arbiter.test"
    assert len(gateway.belief) == 1
    assert gateway.rejection_log == ()


def test_admission_cannot_be_replayed_onto_another_record():
    """A declaration is bound to one record, even for an identical claim."""
    first = assessed_evidence("ev-a")
    declaration = make_admission(first)

    # Different record, identical scientific claim.
    second = make_evidence("ev-b").with_assessment(make_assessment())
    assert second.content_hash == first.content_hash
    assert second.record_hash != first.record_hash

    _raises(AdmissionError, second.admit, declaration)


def test_admission_declaration_round_trips_and_still_verifies():
    evidence = assessed_evidence()
    declaration = make_admission(evidence)
    reloaded = AdmissionDeclaration.from_dict(
        json.loads(json.dumps(declaration.to_dict()))
    )
    assert reloaded == declaration
    assert TEST_AUTHORITY.verifies(reloaded) is True

    registry = make_registry()
    attempt = registry.verify(
        reloaded, subject_record_hash=evidence.record_hash
    )
    assert attempt.outcome is AdmissionOutcome.ADMITTED


# =====================================================================
# 3. Accepted evidence can pass through the Belief Update Gateway
# =====================================================================

def test_accepted_evidence_passes_gateway():
    gateway = make_gateway()
    evidence = accepted_evidence()
    assert evidence.status is EvidenceStatus.ACCEPTED

    entry = gateway.submit(evidence)
    assert entry.evidence_id == "ev-1"
    assert entry.admitted_by == TEST_AUTHORITY.authority_id
    assert entry.content_hash == evidence.content_hash

    assert len(gateway.belief) == 1
    assert gateway.belief.supports(evidence.belief_key)
    assert len(gateway.belief.contributions(evidence.belief_key)) == 1


# =====================================================================
# 4. Suspended evidence no longer contributes through the active view
# =====================================================================

def test_suspended_evidence_leaves_active_view():
    gateway = make_gateway()
    evidence = accepted_evidence()
    gateway.submit(evidence)
    key = evidence.belief_key
    assert gateway.belief.supports(key)
    snapshot_before = gateway.belief.snapshot_ref()

    suspended = evidence.suspend("superseding measurement pending")
    gateway.update_standing(suspended)

    assert suspended.status is EvidenceStatus.SUSPENDED
    assert gateway.belief.supports(key) is False
    assert len(gateway.belief) == 0
    assert gateway.belief.snapshot_ref() != snapshot_before

    # The audit trail still records that it once contributed.
    assert len(gateway.belief.audit_log()) == 1

    # Reinstatement is a fresh scientific judgement, not a lifecycle move.
    # update_standing() lowers standing only; restoring influence has to go
    # back through the authorized admission path.
    reinstated = suspended.reinstate("measurement did not arrive")
    _raises(AdmissionError, gateway.update_standing, reinstated)
    assert gateway.belief.supports(key) is False
    assert len(gateway.belief.audit_log()) == 1


def test_mutated_evidence_cannot_replace_accepted_evidence():
    gateway = make_gateway()
    evidence = accepted_evidence()
    gateway.submit(evidence)

    # Same id, different scientific content -> different content and record hash.
    tampered = Evidence(
        evidence_id=evidence.evidence_id,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="peak_response"),
        claim_payload={"value": 999.0, "units": "volt"},
        uncertainty=make_uncertainty(),
        provenance_ref="run-001",
        domain_pack_ref="demo.pack",
        status=EvidenceStatus.ACCEPTED,
    )
    assert tampered.content_hash != evidence.content_hash
    assert tampered.record_hash != evidence.record_hash
    _raises(BeliefWriteViolation, gateway.update_standing, tampered)


def test_content_identity_is_not_record_identity():
    """Same scientific claim, different sources -> distinct evidence records.

    Sharing a content hash is correct and useful: it is how corroboration is
    recognised. Collapsing the records would silently double-count one source
    or discard the other.
    """
    simulated = Evidence(
        evidence_id="ev-sim",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="peak_response"),
        claim_payload={"value": 1.5, "units": "volt"},
        uncertainty=make_uncertainty(),
        provenance_ref="run-simulation-001",
        domain_pack_ref="demo.pack",
    )
    measured = Evidence(
        evidence_id="ev-meas",
        source_class=SourceClass.MEASUREMENT,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="peak_response"),
        claim_payload={"value": 1.5, "units": "volt"},
        uncertainty=make_uncertainty(),
        provenance_ref="lab-run-77",
        domain_pack_ref="demo.pack",
    )

    # Scientific Content Identity: identical claim -> identical hash. Valid.
    assert simulated.content_hash == measured.content_hash

    # Evidence Record Identity: distinct records must stay distinct.
    assert simulated.record_hash != measured.record_hash
    assert simulated.evidence_id != measured.evidence_id
    assert simulated.provenance_ref != measured.provenance_ref
    assert simulated.source_class is not measured.source_class

    # Provenance survives a round-trip on both records.
    for original in (simulated, measured):
        reloaded = Evidence.from_dict(json.loads(json.dumps(original.to_dict())))
        assert reloaded.provenance_ref == original.provenance_ref
        assert reloaded.source_class is original.source_class
        assert reloaded.record_hash == original.record_hash

    # Both can reach belief independently and both are retained.
    gateway = make_gateway()
    for original in (simulated, measured):
        assessed = original.with_assessment(make_assessment())
        gateway.submit(assessed.admit(make_admission(assessed)))

    assert len(gateway.belief) == 2
    contributions = gateway.belief.contributions(simulated.belief_key)
    assert len(contributions) == 2
    assert {c.evidence_id for c in contributions} == {"ev-sim", "ev-meas"}
    # Same content identity, preserved separate record identities.
    assert len({c.content_hash for c in contributions}) == 1
    assert len({c.record_hash for c in contributions}) == 2


def test_content_hash_detects_altered_claim_on_reload():
    evidence = accepted_evidence()
    payload = evidence.to_dict()
    payload["claim_payload"] = {"value": 42.0, "units": "volt"}
    _raises(Exception, Evidence.from_dict, payload)


# =====================================================================
# 5. Evidence lifecycle is append-only / auditable
# =====================================================================

def test_lifecycle_is_append_only_and_auditable():
    evidence = make_evidence()
    assert len(evidence.lifecycle_log) == 1

    assessed = evidence.with_assessment(make_assessment())
    accepted = assessed.admit(make_admission(assessed))
    suspended = accepted.suspend("pending review")

    logs = [
        evidence.lifecycle_log,
        assessed.lifecycle_log,
        accepted.lifecycle_log,
        suspended.lifecycle_log,
    ]
    # Each stage strictly extends the previous one, prefix preserved.
    for earlier, later in zip(logs, logs[1:]):
        assert len(later) == len(earlier) + 1
        assert later[: len(earlier)] == earlier

    statuses = [e.status for e in suspended.lifecycle_log]
    assert statuses == [
        EvidenceStatus.CANDIDATE,
        EvidenceStatus.ASSESSED,
        EvidenceStatus.ACCEPTED,
        EvidenceStatus.SUSPENDED,
    ]

    # Earlier objects are untouched: history cannot be rewritten in place.
    assert evidence.status is EvidenceStatus.CANDIDATE
    assert len(evidence.lifecycle_log) == 1

    # Frozen: no in-place mutation of standing.
    _raises(Exception, setattr, evidence, "status", EvidenceStatus.ACCEPTED)


def test_illegal_lifecycle_transitions_are_refused():
    candidate = make_evidence()
    # Candidate cannot be admitted without assessment.
    _raises(LifecycleViolation, candidate.admit, make_admission(candidate))
    # Candidate cannot be suspended.
    _raises(LifecycleViolation, candidate.suspend, "nope")

    invalid = candidate.invalidate("bad binding")
    # INVALID is terminal.
    _raises(LifecycleViolation, invalid.with_assessment, make_assessment())

    superseded = accepted_evidence().supersede("ev-2")
    _raises(LifecycleViolation, superseded.reinstate, "nope")


def test_assessments_accumulate():
    evidence = make_evidence().with_assessment(make_assessment("as-1"))
    evidence = evidence.with_assessment(make_assessment("as-2"))
    assert len(evidence.assessments) == 2
    # A second assessment does not add a redundant lifecycle event.
    assert len(evidence.lifecycle_log) == 2


# =====================================================================
# 6. Domain scientific semantics do not become structure calibration keys
# =====================================================================

def test_domain_semantics_cannot_key_calibration():
    guard = guard_from_packs([DemoPack()])
    environment = EnvironmentSignature(
        hardware_class="cpu.x86_64",
        precision="float64",
        solver_build=("scipy.linalg", "1.18.0"),
    )

    clean = StructureSignature(
        structure_kind="linear_system",
        components=(StructureComponent(kind="dense_block", multiplicity=4),),
        attributes={"state_count": "4"},
    )
    key = build_calibration_key(clean, environment, guard=guard)
    assert key.key.startswith("calib/v1/")

    # Structure named after the domain.
    contaminated_kind = StructureSignature(structure_kind="demo.pack.linear_system")
    _raises(
        CalibrationKeyContamination,
        build_calibration_key,
        contaminated_kind,
        environment,
        guard=guard,
    )

    # Structure carrying a domain QoI as an attribute value.
    contaminated_attr = StructureSignature(
        structure_kind="linear_system",
        attributes={"tracked": "peak_response"},
    )
    _raises(
        CalibrationKeyContamination,
        build_calibration_key,
        contaminated_attr,
        environment,
        guard=guard,
    )

    # Component-level contamination is caught too.
    contaminated_component = StructureSignature(
        structure_kind="linear_system",
        components=(StructureComponent(kind="gain_block"),),
    )
    _raises(
        CalibrationKeyContamination,
        build_calibration_key,
        contaminated_component,
        environment,
        guard=guard,
    )


def test_calibration_keys_are_versioned_and_order_independent():
    a = StructureComponent(kind="dense_block", multiplicity=2)
    b = StructureComponent(kind="sparse_block", multiplicity=3)
    left = StructureSignature(structure_kind="mixed", components=(a, b))
    right = StructureSignature(structure_kind="mixed", components=(b, a))
    assert left.digest == right.digest

    env = EnvironmentSignature(hardware_class="cpu", precision="float64")
    k1 = build_calibration_key(left, env, key_version=1)
    k2 = build_calibration_key(left, env, key_version=2)
    assert k1.key != k2.key
    assert "v1" in k1.key and "v2" in k2.key

    # Environment is part of identity: precision change changes the key.
    env32 = EnvironmentSignature(hardware_class="cpu", precision="float32")
    assert build_calibration_key(left, env32).key != k1.key

    composed = left.compose(
        StructureSignature(structure_kind="extra", components=(a,)),
        structure_kind="coupled",
    )
    assert len(composed.components) == 3


# =====================================================================
# 7. Failure disposition and cause are independent
# =====================================================================

def test_disposition_and_cause_are_independent():
    causes = [
        AttributedCause.SCIENTIFIC,
        AttributedCause.NUMERICAL,
        AttributedCause.INFRASTRUCTURE,
        AttributedCause.INFEASIBLE,
        AttributedCause.HYPOTHESIS_CONTRADICTION,
        AttributedCause.INCONCLUSIVE,
        AttributedCause.NONE,
    ]
    built = 0
    for disposition in Disposition:
        for cause in causes:
            censoring = (
                CensoringType.RIGHT_CENSORED_BUDGET
                if disposition is Disposition.KILLED_CENSORED
                else CensoringType.NONE
            )
            outcome = RunOutcome(
                disposition=disposition,
                attributed_cause=cause,
                censoring_type=censoring,
                informative_for_pf=True,
            )
            assert outcome.disposition is disposition
            assert outcome.attributed_cause is cause
            built += 1
    assert built == len(Disposition) * len(causes)

    # The distinctions that must never collapse are genuinely distinct.
    numerical = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.NUMERICAL,
        informative_for_pf=True,
    )
    infrastructure = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.INFRASTRUCTURE,
        informative_for_pf=False,
    )
    assert numerical.disposition is infrastructure.disposition
    assert numerical.attributed_cause is not infrastructure.attributed_cause


def test_censored_run_must_declare_censoring_type():
    _raises(
        OutcomeContractError,
        RunOutcome,
        disposition=Disposition.KILLED_CENSORED,
        attributed_cause=AttributedCause.NONE,
    )
    censored = RunOutcome(
        disposition=Disposition.KILLED_CENSORED,
        censoring_type=CensoringType.RIGHT_CENSORED_WALLCLOCK,
        completion_fraction=0.4,
        retryability=Retryability.RETRYABLE,
    )
    assert censored.is_censored is True
    assert censored.completion_fraction == 0.4


def test_informative_outcomes_are_not_only_successes():
    infeasible = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.INFEASIBLE,
        completion_fraction=0.0,
        informative_for_pf=True,
    )
    contradiction = RunOutcome(
        disposition=Disposition.PARTIAL,
        attributed_cause=AttributedCause.HYPOTHESIS_CONTRADICTION,
        completion_fraction=0.0,
        informative_for_pf=True,
    )
    assert infeasible.yielded_information is True
    assert contradiction.yielded_information is True


def test_completion_fraction_is_bounded_and_flags_explicit():
    _raises(
        OutcomeContractError,
        RunOutcome,
        disposition=Disposition.PARTIAL,
        completion_fraction=1.4,
    )
    _raises(
        OutcomeContractError,
        RunOutcome,
        disposition=Disposition.SUCCESS,
        informative_for_pf="yes",
    )


# =====================================================================
# 8. Infrastructure failure can be marked informative_for_pf = False
# =====================================================================

def test_infrastructure_failure_not_informative_for_pf():
    outcome = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.INFRASTRUCTURE,
        blame_assignment=BlameAssignment.PLATFORM,
        completion_fraction=0.0,
        retryability=Retryability.RETRYABLE,
        informative_for_pf=False,
        detected_by=DetectedBy.RUNTIME,
        salvageable_artifacts=("partial.log",),
        detail="node lost power",
    )
    assert outcome.informative_for_pf is False
    assert outcome.attributed_cause is AttributedCause.INFRASTRUCTURE
    assert outcome.salvageable_artifacts == ("partial.log",)

    # A scientific failure on the same disposition stays informative.
    scientific = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.SCIENTIFIC,
        informative_for_pf=True,
    )
    assert scientific.informative_for_pf is True

    reloaded = RunOutcome.from_dict(json.loads(json.dumps(outcome.to_dict())))
    assert reloaded.informative_for_pf is False


# =====================================================================
# 9. Model discrepancy declaration is explicit
# =====================================================================

def test_model_discrepancy_must_be_declared():
    # Omitting the declaration entirely is refused.
    _raises(
        TypeError,
        UncertaintyDeclaration,
        subject_model=SubjectModel.PREDICTION_MODEL,
    )
    # Passing something that is not a declaration is refused.
    _raises(
        UncertaintyContractError,
        UncertaintyDeclaration,
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=None,
    )
    # A constrained prior without a reference is not a constraint.
    _raises(
        UncertaintyContractError,
        ModelDiscrepancy,
        kind=DiscrepancyKind.CONSTRAINED_PRIOR,
    )

    declared = ModelDiscrepancy(
        kind=DiscrepancyKind.CONSTRAINED_PRIOR,
        reference="prior/thermal-discrepancy/v2",
    )
    decl = UncertaintyDeclaration(
        subject_model=SubjectModel.OBSERVATION_MODEL,
        discrepancy=declared,
        channels={
            UncertaintyChannel.ALEATORIC: Uncertainty.unknown(),
            UncertaintyChannel.MODEL_FORM: Uncertainty.unknown(),
        },
    )
    assert decl.subject_model is SubjectModel.OBSERVATION_MODEL
    assert decl.discrepancy.reference == "prior/thermal-discrepancy/v2"
    # Undeclared channels report UNKNOWN rather than silently zero.
    assert decl.channel(UncertaintyChannel.NUMERICAL).is_quantified is False
    assert decl.quantified_channels == ()

    # Evidence cannot exist without an uncertainty declaration at all.
    _raises(
        Exception,
        Evidence,
        evidence_id="ev-x",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="x"),
        claim_payload={},
        uncertainty=None,
        provenance_ref="run-1",
        domain_pack_ref="demo.pack",
    )


# =====================================================================
# 10. Provenance references survive serialization / reload
# =====================================================================

def test_provenance_survives_serialization():
    evidence_prov = EvidenceProvenance(
        evidence_id="ev-1",
        run_provenance_ref="run-001",
        producer="sim.extractor",
        producer_version="0.1",
        created_at="2026-08-06T00:00:00Z",
        source_refs=("artifact://a", "artifact://b"),
    )
    reloaded = EvidenceProvenance.from_dict(
        json.loads(json.dumps(evidence_prov.to_dict()))
    )
    assert reloaded == evidence_prov
    assert reloaded.run_provenance_ref == "run-001"

    assessment_prov = AssessmentProvenance(
        assessment_id="as-1",
        critic_id="critic.residual",
        critic_version="1.0",
        inputs_ref=("ev-1",),
        assessed_at="2026-08-06T00:01:00Z",
    )
    assert (
        AssessmentProvenance.from_dict(
            json.loads(json.dumps(assessment_prov.to_dict()))
        )
        == assessment_prov
    )

    # Reserved decision provenance round-trips even though no Strategist exists.
    decision = DecisionProvenance(
        decision_id="dec-1",
        belief_snapshot_ref="abc123",
        candidate_actions=("act-1", "act-2"),
        scores={"act-1": 0.4, "act-2": 0.6},
        chosen_action="act-2",
        reason="reserved field layout only",
        policy_id="none",
        human_override=False,
    )
    assert (
        DecisionProvenance.from_dict(json.loads(json.dumps(decision.to_dict())))
        == decision
    )

    # A full evidence envelope keeps every reference and its content hash.
    evidence = accepted_evidence()
    round_tripped = Evidence.from_dict(json.loads(json.dumps(evidence.to_dict())))
    assert round_tripped.content_hash == evidence.content_hash
    assert round_tripped.provenance_ref == evidence.provenance_ref
    assert round_tripped.domain_pack_ref == evidence.domain_pack_ref
    assert round_tripped.status is EvidenceStatus.ACCEPTED
    assert len(round_tripped.lifecycle_log) == len(evidence.lifecycle_log)
    assert round_tripped.admission.arbiter_id == TEST_AUTHORITY.authority_id
    assert round_tripped.record_hash == evidence.record_hash
    assert len(round_tripped.admission_attempts) == len(evidence.admission_attempts)

    # Core run provenance is reused unchanged and still round-trips.
    core = ProvenanceRecord(run_id="run-001", inputs={"gain": Quantity(2.0, "volt")})
    assert ProvenanceRecord.from_dict(
        json.loads(json.dumps(core.to_dict()))
    ).run_id == "run-001"


# =====================================================================
# 11. Reserved source classes do not require implementation
# =====================================================================

def test_reserved_source_classes_are_representable_not_implemented():
    for reserved in (
        SourceClass.MEASUREMENT,
        SourceClass.LITERATURE,
        SourceClass.BENCHMARK,
    ):
        evidence = Evidence(
            evidence_id=f"ev-{reserved.value}",
            source_class=reserved,
            claim_type=ClaimType.PARAMETER_VALUE,
            claim_binding=ClaimBinding(subject_kind="parameter", subject_ref="gain"),
            claim_payload={"value": 2.0},
            uncertainty=make_uncertainty(),
            provenance_ref="ref-001",
            domain_pack_ref="demo.pack",
        )
        # Representation and round-trip work without any ingestion code.
        assert (
            Evidence.from_dict(json.loads(json.dumps(evidence.to_dict()))).source_class
            is reserved
        )
        # But the ingestion path refuses explicitly rather than half-working.
        _raises(ReservedNotImplemented, require_implemented_source, reserved)

    require_implemented_source(SourceClass.SIMULATION)  # implemented: no raise

    # Reserved campaign type and executor behave the same way.
    from src.engcore.sria import require_implemented_campaign_type

    _raises(
        ReservedNotImplemented,
        require_implemented_campaign_type,
        CampaignType.OPEN_RESEARCH,
    )
    physical = ResearchAction(
        action_id="act-physical",
        executor_type=ExecutorType.PHYSICAL,
        target_ref="rig-1",
    )
    _raises(ReservedNotImplemented, require_executable, physical)
    require_executable(
        ResearchAction(
            action_id="act-sim",
            executor_type=ExecutorType.SIMULATION,
            target_ref="model-1",
        )
    )


# =====================================================================
# 12. No LLM dependency in the scientific import graph
# =====================================================================

def test_no_llm_dependency_in_scientific_core():
    assert SCIENTIFIC_DIR.is_dir(), f"missing {SCIENTIFIC_DIR}"
    assert SRIA_DIR.is_dir(), f"missing {SRIA_DIR}"

    violations = find_forbidden_imports([SCIENTIFIC_DIR, SRIA_DIR])
    assert violations == (), f"forbidden imports: {violations}"

    assert_no_llm_dependencies([SCIENTIFIC_DIR, SRIA_DIR])


def test_llm_detector_actually_detects(tmp_path=None):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        offender = Path(tmp) / "bad_module.py"
        offender.write_text("import anthropic\n", encoding="utf-8")
        violations = find_forbidden_imports([Path(tmp)])
        assert len(violations) == 1
        assert violations[0][2] == "anthropic"

        offender.write_text("from langchain.chains import X\n", encoding="utf-8")
        assert find_forbidden_imports([Path(tmp)])[0][2] == "langchain"


def test_scientific_core_does_not_import_sria():
    """Layering runs one way only."""
    from src.engcore.sria.trust import scan_imports

    for filename, modules in scan_imports(SCIENTIFIC_DIR).items():
        for module in modules:
            assert "sria" not in module, f"{filename} imports {module}"


# =====================================================================
# Campaign charter
# =====================================================================

def test_decision_campaign_requires_a_terminal_decision():
    _raises(
        CharterError,
        CampaignCharter,
        campaign_id="camp-1",
        campaign_type=CampaignType.DECISION,
    )

    charter = CampaignCharter(
        campaign_id="camp-1",
        campaign_type=CampaignType.DECISION,
        terminal_decisions=(
            TerminalDecision(
                decision_id="d1",
                statement="Select the cheaper design that meets the limit",
                options=("design_a", "design_b"),
            ),
        ),
        utility_reference="utility/cost-vs-margin/v1",
        total_budget={"compute": Quantity(500.0, "hour")},
        confidence_requirements=(
            ConfidenceRequirement(
                requirement_id="c1",
                required_levels=(ValidationLevel.NUMERICALLY_CONVERGED,),
                threshold=0.95,
            ),
        ),
        acceptance_criteria=(
            AcceptanceCriterion(criterion_id="a1", statement="Margin >= 10%"),
        ),
    )
    assert charter.campaign_type is CampaignType.DECISION
    reloaded = CampaignCharter.from_dict(json.loads(json.dumps(charter.to_dict())))
    assert reloaded.campaign_id == "camp-1"
    assert reloaded.total_budget["compute"].magnitude == 500.0


def test_charter_amendment_history_is_append_only():
    charter = CampaignCharter(
        campaign_id="camp-1",
        terminal_decisions=(
            TerminalDecision(decision_id="d1", statement="Pick one"),
        ),
    )
    assert charter.amendment_history == ()

    amended = charter.amend(
        CharterAmendment(
            amendment_id="am-1",
            reason="budget increased after scoping review",
            author="owner",
        ),
        total_budget={"compute": Quantity(100.0, "hour")},
    )
    assert len(amended.amendment_history) == 1
    assert amended.amendment_history[0].changed_fields == ("total_budget",)
    # The original is untouched.
    assert charter.amendment_history == ()

    again = amended.amend(
        CharterAmendment(amendment_id="am-2", reason="added acceptance criterion"),
        acceptance_criteria=(
            AcceptanceCriterion(criterion_id="a1", statement="Margin >= 10%"),
        ),
    )
    assert len(again.amendment_history) == 2
    assert again.amendment_history[:1] == amended.amendment_history

    # An amendment must state a reason and must change something.
    _raises(CharterError, CharterAmendment, amendment_id="am-3", reason="  ")
    _raises(
        CharterError,
        again.amend,
        CharterAmendment(amendment_id="am-4", reason="no-op"),
    )
    # Identity is not amendable.
    _raises(
        CharterError,
        again.amend,
        CharterAmendment(amendment_id="am-5", reason="rename"),
        campaign_id="camp-2",
    )


# =====================================================================
# Actions — hard feasibility precedes ranking
# =====================================================================

class _BudgetConstraint:
    constraint_id = "budget.max_hours"

    def evaluate(self, action):
        cost = action.expected_cost.get("compute")
        hours = cost.magnitude if cost is not None else 0.0
        return FeasibilityVerdict(
            constraint_id=self.constraint_id,
            feasible=hours <= 10.0,
            reason="" if hours <= 10.0 else f"{hours} h exceeds 10 h cap",
        )


def test_hard_feasibility_gate_filters_before_ranking():
    gate = HardFeasibilityGate([_BudgetConstraint()])
    cheap = ResearchAction(
        action_id="cheap",
        executor_type=ExecutorType.SIMULATION,
        target_ref="model-1",
        expected_cost={"compute": Quantity(2.0, "hour")},
    )
    dear = ResearchAction(
        action_id="dear",
        executor_type=ExecutorType.SIMULATION,
        target_ref="model-1",
        expected_cost={"compute": Quantity(50.0, "hour")},
    )

    assert gate.is_feasible(cheap) is True
    assert gate.is_feasible(dear) is False
    assert tuple(a.action_id for a in gate.filter([cheap, dear])) == ("cheap",)
    _raises(FeasibilityViolation, gate.require_feasible, dear)

    # A veto must carry a reason.
    _raises(
        Exception,
        FeasibilityVerdict,
        constraint_id="c",
        feasible=False,
        reason="",
    )

    # M1 ships no utility ranking to be tempted into using.
    assert not hasattr(gate, "rank")
    assert not hasattr(gate, "score")

    reloaded = ResearchAction.from_dict(json.loads(json.dumps(cheap.to_dict())))
    assert reloaded.expected_cost["compute"].magnitude == 2.0


# =====================================================================
# Domain pack boundary
# =====================================================================

def test_domain_pack_contract_and_boundary():
    validate_domain_pack(DemoPack())

    # A pack that reaches for platform responsibilities is refused.
    _raises(DomainPackContractError, validate_domain_pack, OverreachingPack())

    class Incomplete:
        pack_id = "incomplete"
        pack_version = "0.1"

    _raises(DomainPackContractError, validate_domain_pack, Incomplete())

    pack = DemoPack()
    covariates = pack.extract_covariates(None)
    assert set(covariates) == {"state_count", "condition_estimate"}
    assert all(isinstance(v, float) for v in covariates.values())

    ladder = pack.fidelity_ladder()
    assert [level.rank for level in ladder] == [0, 1]


def test_evidence_belief_key_is_domain_neutral():
    evidence = make_evidence()
    assert evidence.belief_key == "qoi_value|qoi:peak_response"
    qualified = Evidence(
        evidence_id="ev-q",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.PARAMETER_VALUE,
        claim_binding=ClaimBinding(
            subject_kind="parameter",
            subject_ref="gain",
            qualifiers={"temperature": "300K"},
        ),
        claim_payload={"value": 2.0},
        uncertainty=make_uncertainty(),
        provenance_ref="run-2",
        domain_pack_ref="demo.pack",
    )
    assert qualified.belief_key == "parameter_value|parameter:gain;temperature=300K"


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 — M1 contract and trust-boundary tests")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"SRIA M1 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"SRIA M1 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
