"""SRIA V0.1 M3.1 — assurance semantics tests.

Runs under pytest, and standalone via
``python -m tests.test_sria_m31_semantics``.

Each test guards an *epistemic* distinction — the kind that is invisible in
the arithmetic and only shows up when someone acts on the verdict.
"""

from __future__ import annotations

import json
import sys

from src.engcore.scientific import (
    ConvergenceState,
    ProvenanceRecord,
    Quantity,
    ScientificResult,
    SolverIdentity,
    Uncertainty,
    UncertaintyKind,
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from src.engcore.sria import (
    AdmissionAuthority,
    AdmissionAuthorityError,
    AdmissionAuthorityRegistry,
    AssessmentVerdict,
    AttributedCause,
    BeliefUpdateGateway,
    CampaignCharter,
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Disposition,
    Evidence,
    EvidenceStatus,
    ModelDiscrepancy,
    RunOutcome,
    SourceClass,
    SubjectModel,
    TerminalDecision,
    UncertaintyChannel,
    UncertaintyDeclaration,
)
from src.engcore.sria.admission import DecisionBinding
from src.engcore.sria.assurance import (
    Arbiter,
    ArbiterDecision,
    AssuranceVerdict,
    CalibrationCriticAdapter,
    ChannelEntry,
    ChannelState,
    CriticClass,
    CriticVerdict,
    Finding,
    NumericalCritic,
    ObligationSet,
    Severity,
    UncertaintyBudget,
    model_discrepancy_check,
    obligations_from_charter,
)
from src.engcore.sria.assurance.assessment import FindingImpact
from src.engcore.sria.calibration import CalibrationReport, CalibrationVerdict

AUTHORITY = AdmissionAuthority("arbiter.m31", secret="m31-secret")


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


def registry() -> AdmissionAuthorityRegistry:
    return AdmissionAuthorityRegistry([AUTHORITY])


def quantified(magnitude: float = 1e-12) -> Uncertainty:
    return Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(magnitude, "volt"),
        method="residual bound",
    )


def declaration() -> UncertaintyDeclaration:
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="campaign models discrepancy as zero",
        ),
        channels={UncertaintyChannel.NUMERICAL: quantified()},
    )


def budget() -> UncertaintyBudget:
    return UncertaintyBudget(
        value_name="V",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN,
                uncertainty=quantified(),
            ),
            ChannelEntry(
                channel=UncertaintyChannel.ALEATORIC,
                state=ChannelState.NOT_APPLICABLE,
                rationale="deterministic solve",
            ),
        ),
        declaration=declaration(),
    )


def good_result(rid: str = "res-ok") -> ScientificResult:
    return ScientificResult(
        result_id=rid,
        values={"V": Quantity(9.0, "volt")},
        provenance=ProvenanceRecord(run_id="run-1"),
        solver=SolverIdentity(solver_id="demo", version="1"),
        convergence=ConvergenceState.CONVERGED,
        validation=ValidationReport(
            checks=(
                ValidationCheck(
                    name="linear_system_residual",
                    outcome=ValidationOutcome.PASS,
                    residual=1e-15,
                    tolerance=1e-9,
                    establishes=ValidationLevel.NUMERICALLY_CONVERGED,
                ),
            )
        ),
    )


def clean_run() -> RunOutcome:
    return RunOutcome(
        disposition=Disposition.SUCCESS,
        attributed_cause=AttributedCause.NONE,
        informative_for_pf=True,
    )


def evidence_for(result: ScientificResult, eid: str = "ev-31") -> Evidence:
    """Evidence already carrying an assessment, so it is ASSESSED.

    M1 forbids CANDIDATE -> ACCEPTED; admission always follows assessment.
    """
    return _raw_evidence(result, eid).with_assessment(
        numerical_assessment(result).to_evidence_assessment()
    )


def _raw_evidence(result: ScientificResult, eid: str) -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="V"),
        claim_payload={"value": 9.0, "units": "volt"},
        uncertainty=declaration(),
        provenance_ref=result.provenance.run_id,
        domain_pack_ref="demo",
    )


def charter_obligations(campaign_id="camp-31", **kw) -> ObligationSet:
    charter = CampaignCharter(
        campaign_id=campaign_id,
        terminal_decisions=(TerminalDecision(decision_id="d", statement="s"),),
    )
    return obligations_from_charter(charter, **kw)


def numerical_assessment(result=None, aid="as-n"):
    return NumericalCritic().assess(
        result or good_result(),
        assessment_id=aid,
        budget=budget(),
        run_outcome=clean_run(),
    )


# =====================================================================
# 1. Calibration failure != scientific invalidity
# =====================================================================

def test_untrusted_calibration_blocks_but_does_not_invalidate():
    """An untrusted runtime cost model cannot falsify a computed voltage."""
    obligations = charter_obligations(
        required_critics=(CriticClass.NUMERICAL, CriticClass.CALIBRATION),
        required_calibration_verdicts=(CalibrationVerdict.TRUSTED,),
    )
    calibration = CalibrationCriticAdapter().assess(
        [
            CalibrationReport(
                model_id="cost.runtime",
                model_version="cost/1",
                verdict=CalibrationVerdict.UNTRUSTED,
            )
        ],
        assessment_id="as-cal",
        subject_ref="res-ok",
        required_verdicts=(CalibrationVerdict.TRUSTED,),
    )
    decision = Arbiter(AUTHORITY).decide(
        decision_id="d1",
        subject_ref="res-ok",
        assessments=[numerical_assessment(), calibration],
        obligations=obligations,
        budget=budget(),
    )
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
    assert decision.verdict is not AssuranceVerdict.INVALID

    # No calibration finding claims to invalidate the subject.
    for finding in calibration.findings:
        assert finding.invalidates_subject is False
        assert finding.impact is FindingImpact.ASSURANCE_BLOCKING


def test_degraded_and_insufficient_calibration_also_only_block():
    for verdict in (
        CalibrationVerdict.DEGRADED,
        CalibrationVerdict.INSUFFICIENT_DATA,
    ):
        calibration = CalibrationCriticAdapter().assess(
            [
                CalibrationReport(
                    model_id="m", model_version="1", verdict=verdict
                )
            ],
            assessment_id=f"as-{verdict.value}",
            subject_ref="res-ok",
            required_verdicts=(CalibrationVerdict.TRUSTED,),
        )
        decision = Arbiter(AUTHORITY).decide(
            decision_id=f"d-{verdict.value}",
            subject_ref="res-ok",
            assessments=[numerical_assessment(), calibration],
            obligations=charter_obligations(
                required_critics=(CriticClass.NUMERICAL, CriticClass.CALIBRATION),
                required_calibration_verdicts=(CalibrationVerdict.TRUSTED,),
            ),
            budget=budget(),
        )
        assert decision.verdict is not AssuranceVerdict.VALID
        assert decision.verdict is not AssuranceVerdict.INVALID
        assert all(not f.invalidates_subject for f in calibration.findings)


# =====================================================================
# 2. INVALID invariant
# =====================================================================

def test_invalid_requires_an_evidence_invalidating_finding():
    """None of the 'absence' conditions may reach INVALID on their own."""
    obligations = charter_obligations(
        required_critics=(CriticClass.NUMERICAL, CriticClass.DOMAIN),
        required_checks=("residual_evidence",),
        required_uncertainty_channels=(UncertaintyChannel.NUMERICAL,),
    )

    # missing diagnostics + skipped critic + unevaluated obligations together
    bare = ScientificResult(
        result_id="res-bare",
        values={"V": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.CONVERGED,
    )
    decision = Arbiter(AUTHORITY).decide(
        decision_id="d-absent",
        subject_ref="res-bare",
        assessments=[
            NumericalCritic().assess(
                bare,
                assessment_id="as-n",
                budget=budget(),
                mandatory_checks=("residual_evidence",),
                run_outcome=clean_run(),
            )
        ],
        obligations=obligations,
        budget=budget(),
    )
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
    assert decision.verdict is not AssuranceVerdict.INVALID


def test_demonstrated_non_convergence_supports_invalid():
    failed = ScientificResult(
        result_id="res-nc",
        values={"V": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.FAILED,
    )
    assessment = NumericalCritic().assess(
        failed, assessment_id="as-n", budget=budget(), run_outcome=clean_run()
    )
    assert assessment.invalidating_findings
    decision = Arbiter(AUTHORITY).decide(
        decision_id="d-nc",
        subject_ref="res-nc",
        assessments=[assessment],
        obligations=charter_obligations(
            required_critics=(CriticClass.NUMERICAL,)
        ),
        budget=budget(),
    )
    assert decision.verdict is AssuranceVerdict.INVALID
    assert any("invalidating" in r for r in decision.reasons)


def test_evidence_invalidating_findings_must_be_blocking():
    _raises(
        ValueError,
        Finding,
        code="x",
        severity=Severity.ADVISORY,
        category="c",
        impact=FindingImpact.EVIDENCE_INVALIDATING,
    )


# =====================================================================
# 3. ZERO_DECLARED: unsupported vs contradicted
# =====================================================================

def test_unsupported_zero_discrepancy_blocks_only():
    record, findings = model_discrepancy_check(budget(), mandatory=True)
    assert record.outcome is CriticVerdict.INCONCLUSIVE
    assert record.outcome is not CriticVerdict.FAIL
    assert findings[0].code == "domain.zero_discrepancy_unsupported"
    assert findings[0].invalidates_subject is False
    assert findings[0].impact is FindingImpact.ASSURANCE_BLOCKING


def test_contradicted_zero_discrepancy_supports_invalid():
    record, findings = model_discrepancy_check(
        budget(),
        contradicted_by="benchmark reference disagrees by 12%",
        mandatory=True,
    )
    assert record.outcome is CriticVerdict.FAIL
    assert findings[0].code == "domain.zero_discrepancy_contradicted"
    assert findings[0].invalidates_subject is True
    assert findings[0].severity is Severity.BLOCKING


def test_supported_zero_discrepancy_remains_visible():
    record, findings = model_discrepancy_check(
        budget(), supported_by="study X", mandatory=True
    )
    assert record.outcome is CriticVerdict.PASS
    assert findings[0].code == "domain.zero_discrepancy_declared"
    assert findings[0].invalidates_subject is False


# =====================================================================
# 4-5. Trust chain and the direct-authority bypass
# =====================================================================

def full_obligations() -> ObligationSet:
    return charter_obligations(required_critics=(CriticClass.NUMERICAL,))


def valid_flow():
    """Produce a VALID decision plus the Arbiter that issued it."""
    result = good_result()
    evidence = evidence_for(result)
    arbiter = Arbiter(AUTHORITY)
    decision = arbiter.decide(
        decision_id="d-valid",
        subject_ref=evidence.evidence_id,
        assessments=[numerical_assessment(result)],
        obligations=full_obligations(),
        budget=budget(),
    )
    return arbiter, decision, evidence


def test_valid_decision_reaches_the_gateway():
    arbiter, decision, evidence = valid_flow()
    assert decision.verdict is AssuranceVerdict.VALID

    declaration_ = arbiter.authorize_admission(decision, evidence)
    assert declaration_.authorization is not None
    assert declaration_.authorization.decision_hash == decision.decision_hash
    assert declaration_.authorization.verdict == "valid"

    gateway = BeliefUpdateGateway(authorities=registry())
    admitted = evidence.admit(declaration_)
    entry = gateway.submit(admitted)
    assert entry.evidence_id == evidence.evidence_id
    assert len(gateway.belief) == 1


def test_trusted_authority_cannot_admit_without_a_decision():
    """THE bypass test: registration proves who, not that anything was assessed."""
    result = good_result()
    evidence = evidence_for(result)
    gateway = BeliefUpdateGateway(authorities=registry())

    # AUTHORITY is registered and trusted by this gateway.
    assert AUTHORITY.authority_id in gateway.authorities.authority_ids

    # M3.2 refuses this at signing time: an accepting declaration with no
    # traceable authorization is never produced in the first place.
    _raises(
        AdmissionAuthorityError,
        AUTHORITY.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        rationale="I hold the authority, therefore admit",
    )
    assert len(gateway.belief) == 0


def test_non_valid_decisions_cannot_produce_an_accepting_declaration():
    result = good_result()
    evidence = evidence_for(result)
    gateway = BeliefUpdateGateway(authorities=registry())

    for verdict, decision_id in (
        (AssuranceVerdict.INCONCLUSIVE, "d-inc"),
        (AssuranceVerdict.INVALID, "d-inv"),
        (AssuranceVerdict.NOT_ASSESSED, "d-na"),
    ):
        arbiter = Arbiter(AUTHORITY)
        # An empty obligation set yields INCONCLUSIVE; a failed result yields
        # INVALID; no assessments yields NOT_ASSESSED.
        if verdict is AssuranceVerdict.INCONCLUSIVE:
            decision = arbiter.decide(
                decision_id=decision_id,
                subject_ref=evidence.evidence_id,
                assessments=[numerical_assessment(result)],
                obligations=ObligationSet(campaign_id="none"),
                budget=budget(),
            )
        elif verdict is AssuranceVerdict.INVALID:
            failed = ScientificResult(
                result_id="res-f",
                values={"V": Quantity(1.0, "volt")},
                provenance=ProvenanceRecord(run_id="r"),
                convergence=ConvergenceState.FAILED,
            )
            decision = arbiter.decide(
                decision_id=decision_id,
                subject_ref=evidence.evidence_id,
                assessments=[
                    NumericalCritic().assess(
                        failed,
                        assessment_id="as-f",
                        budget=budget(),
                        run_outcome=clean_run(),
                    )
                ],
                obligations=full_obligations(),
                budget=budget(),
            )
        else:
            decision = arbiter.decide(
                decision_id=decision_id,
                subject_ref=evidence.evidence_id,
                assessments=[],
                obligations=full_obligations(),
            )

        assert decision.verdict is verdict
        declaration_ = arbiter.authorize_admission(decision, evidence)
        assert declaration_.admitted is False
        # Even if the declining declaration is presented, nothing is admitted.
        _raises(Exception, gateway.submit, evidence.admit(declaration_))

    assert len(gateway.belief) == 0


def test_fabricated_arbiter_decision_is_rejected():
    """A hand-built VALID decision cannot be signed."""
    arbiter, _real, evidence = valid_flow()
    fabricated = ArbiterDecision(
        decision_id="d-fake",
        subject_ref=evidence.evidence_id,
        verdict=AssuranceVerdict.VALID,
        obligation_results=(),
        assessment_refs=(),
        reasons=("I say so",),
    )
    _raises(ValueError, arbiter.authorize_admission, fabricated, evidence)


def test_tampered_decision_binding_is_rejected_by_the_gateway():
    """The binding is inside the signed payload, so editing it breaks the seal."""
    arbiter, decision, evidence = valid_flow()
    genuine = arbiter.authorize_admission(decision, evidence)

    from src.engcore.sria.admission import AdmissionDeclaration

    tampered = AdmissionDeclaration(
        admitted=True,
        arbiter_id=genuine.arbiter_id,
        subject_record_hash=genuine.subject_record_hash,
        authorization=DecisionBinding(
            decision_id="d-other",
            decision_hash="deadbeef",
            verdict="valid",
        ),
        issuer_id=genuine.issuer_id,
        issued_signature=genuine.issued_signature,
    )
    gateway = BeliefUpdateGateway(authorities=registry())
    _raises(AdmissionAuthorityError, gateway.submit, evidence.admit(tampered))
    assert len(gateway.belief) == 0


def test_binding_with_a_non_valid_verdict_is_refused():
    result = good_result()
    evidence = evidence_for(result)
    gateway = BeliefUpdateGateway(authorities=registry())
    _raises(
        AdmissionAuthorityError,
        AUTHORITY.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=DecisionBinding(
            decision_id="d",
            decision_hash="h",
            verdict="inconclusive",     # not VALID
        ),
    )
    assert len(gateway.belief) == 0


# =====================================================================
# 6. Unevaluated charter requirements fail closed
# =====================================================================

def test_unevaluated_charter_requirement_blocks_valid():
    """A ValidationLevel obligation M3 cannot evaluate must not be assumed met."""
    from src.engcore.sria import ConfidenceRequirement

    charter = CampaignCharter(
        campaign_id="camp-level",
        terminal_decisions=(TerminalDecision(decision_id="d", statement="s"),),
        confidence_requirements=(
            ConfidenceRequirement(
                requirement_id="c1",
                description="must be experimentally validated",
                required_levels=(ValidationLevel.EXPERIMENTALLY_VALIDATED,),
            ),
        ),
    )
    obligations = obligations_from_charter(
        charter, required_critics=(CriticClass.NUMERICAL,)
    )
    assert any(
        o.target.startswith("validation_level:") for o in obligations.obligations
    )

    decision = Arbiter(AUTHORITY).decide(
        decision_id="d-level",
        subject_ref="res-ok",
        assessments=[numerical_assessment()],
        obligations=obligations,
        budget=budget(),
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
    assert any("not evaluable in M3" in r for r in decision.reasons)
    unmet = decision.unmet_obligations
    assert any("validation_level" in u for u in unmet)


# =====================================================================
# 7. NOT_ASSESSED provenance round-trip
# =====================================================================

def test_not_assessed_survives_the_m1_mapping():
    """The frozen M1 verdict loses NOT_ASSESSED; provenance keeps it."""
    bare = ScientificResult(
        result_id="res-bare",
        values={"V": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.CONVERGED,
    )
    assessment = NumericalCritic().assess(
        bare,
        assessment_id="as-na",
        budget=budget(),
        mandatory_checks=("residual_evidence",),
        run_outcome=clean_run(),
    )
    assert assessment.verdict is CriticVerdict.NOT_ASSESSED

    mapped = assessment.to_evidence_assessment()
    assert mapped.verdict is AssessmentVerdict.INCONCLUSIVE
    assert mapped.provenance.metadata["critic_verdict"] == "not_assessed"

    # And it survives serialization, so a replay can still tell them apart.
    from src.engcore.sria.evidence import Assessment

    reloaded = Assessment.from_dict(json.loads(json.dumps(mapped.to_dict())))
    assert reloaded.verdict is AssessmentVerdict.INCONCLUSIVE
    assert reloaded.provenance.metadata["critic_verdict"] == "not_assessed"

    # A genuinely inconclusive critic is distinguishable from the above.
    from src.engcore.sria.assurance import CriticAssessment as _CA
    from src.engcore.sria.provenance import AssessmentProvenance

    inconclusive = _CA(
        assessment_id="as-inc",
        critic_id="demo",
        critic_version="1",
        critic_class=CriticClass.DOMAIN,
        subject_ref="res",
        verdict=CriticVerdict.INCONCLUSIVE,
        provenance=AssessmentProvenance(
            assessment_id="as-inc", critic_id="demo", critic_version="1"
        ),
        summary="checked, could not conclude",
    )
    mapped2 = inconclusive.to_evidence_assessment()
    assert mapped2.verdict is AssessmentVerdict.INCONCLUSIVE
    assert mapped2.provenance.metadata["critic_verdict"] == "inconclusive"
    assert (
        mapped.provenance.metadata["critic_verdict"]
        != mapped2.provenance.metadata["critic_verdict"]
    )

    # The full critic assessment also round-trips with its impact fields.
    from src.engcore.sria.assurance import CriticAssessment

    round_tripped = CriticAssessment.from_dict(
        json.loads(json.dumps(assessment.to_dict()))
    )
    assert round_tripped.verdict is CriticVerdict.NOT_ASSESSED


# =====================================================================
# 8. Updated adversarial matrix
# =====================================================================

def test_corrected_adversarial_matrix():
    """Expected verdicts after the M3.1 semantic correction."""
    obligations = charter_obligations(
        required_critics=(CriticClass.NUMERICAL, CriticClass.DOMAIN),
        required_checks=("residual_evidence",),
        required_uncertainty_channels=(UncertaintyChannel.NUMERICAL,),
    )
    outcomes: dict[str, AssuranceVerdict] = {}

    def decide(name, assessments, obs=None, bud=None):
        arbiter = Arbiter(AUTHORITY)
        d = arbiter.decide(
            decision_id=f"d-{name}",
            subject_ref="res",
            assessments=assessments,
            obligations=obs or obligations,
            budget=bud or budget(),
        )
        outcomes[name] = d.verdict
        return d

    # missing residual -> INCONCLUSIVE
    bare = ScientificResult(
        result_id="res-bare",
        values={"V": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.CONVERGED,
    )
    decide(
        "missing_residual",
        [
            NumericalCritic().assess(
                bare,
                assessment_id="a",
                budget=budget(),
                mandatory_checks=("residual_evidence",),
                run_outcome=clean_run(),
            )
        ],
    )

    # non-converged -> INVALID
    failed = ScientificResult(
        result_id="res-nc",
        values={"V": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.FAILED,
    )
    decide(
        "non_converged",
        [
            NumericalCritic().assess(
                failed, assessment_id="a", budget=budget(), run_outcome=clean_run()
            )
        ],
    )

    # unknown required numerical uncertainty -> INCONCLUSIVE
    unknown_budget = UncertaintyBudget(
        value_name="V",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL, state=ChannelState.UNKNOWN
            ),
        ),
        declaration=declaration(),
    )
    decide(
        "unknown_numerical_uncertainty",
        [numerical_assessment()],
        bud=unknown_budget,
    )

    # skipped required domain critic -> INCONCLUSIVE
    decide("skipped_domain_critic", [numerical_assessment()])

    # untrusted auxiliary calibration -> INCONCLUSIVE
    decide(
        "untrusted_calibration",
        [
            numerical_assessment(),
            CalibrationCriticAdapter().assess(
                [
                    CalibrationReport(
                        model_id="c",
                        model_version="1",
                        verdict=CalibrationVerdict.UNTRUSTED,
                    )
                ],
                assessment_id="a-cal",
                subject_ref="res",
                required_verdicts=(CalibrationVerdict.TRUSTED,),
            ),
        ],
        obs=charter_obligations(
            required_critics=(CriticClass.NUMERICAL, CriticClass.CALIBRATION),
            required_calibration_verdicts=(CalibrationVerdict.TRUSTED,),
        ),
    )

    expected = {
        "missing_residual": AssuranceVerdict.INCONCLUSIVE,
        "non_converged": AssuranceVerdict.INVALID,
        "unknown_numerical_uncertainty": AssuranceVerdict.INCONCLUSIVE,
        "skipped_domain_critic": AssuranceVerdict.INCONCLUSIVE,
        "untrusted_calibration": AssuranceVerdict.INCONCLUSIVE,
    }
    assert outcomes == expected, f"{outcomes} != {expected}"

    # Only the genuinely refuted case is INVALID.
    invalid = [k for k, v in outcomes.items() if v is AssuranceVerdict.INVALID]
    assert invalid == ["non_converged"]


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M3.1 — assurance semantics tests")
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
        print(f"M3.1 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M3.1 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
