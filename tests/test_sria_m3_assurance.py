"""SRIA V0.1 M3 — assurance layer tests.

Runs under pytest, and standalone via ``python -m tests.test_sria_m3_assurance``.

Includes an adversarial defect matrix: each injected defect must make VALID
unreachable through *declared semantics*, not through rules tuned until the
cases passed.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from src.engcore.domains.electrical.dc import DCCircuit, DCVoltageSource
from src.engcore.domains.electrical.dc import ElectricalNode, Resistor, solve_circuit
from src.engcore.scientific import (
    ConvergenceState,
    SolverIdentity,
    ProvenanceRecord,
    Quantity,
    ScientificResult,
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
    AdmissionDeclaration,
    BeliefUpdateGateway,
    BeliefWriteViolation,
    CampaignCharter,
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Evidence,
    EvidenceStatus,
    AttributedCause,
    Disposition,
    ModelDiscrepancy,
    RunOutcome,
    SourceClass,
    SubjectModel,
    TerminalDecision,
    UncertaintyChannel,
    UncertaintyDeclaration,
)
from src.engcore.sria.assurance import (
    Arbiter,
    ArbiterDecision,
    AssuranceVerdict,
    BudgetError,
    CalibrationCriticAdapter,
    ChannelEntry,
    ChannelState,
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    IncomparableUncertainty,
    NumericalCritic,
    ObligationKind,
    ObligationSet,
    Severity,
    UncertaintyBudget,
    ValidationObligation,
    budget_from_declaration,
    model_discrepancy_check,
    obligations_from_charter,
)
from src.engcore.sria.calibration import (
    CalibrationReport,
    CalibrationVerdict,
)
from src.engcore.sria.provenance import AssessmentProvenance

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSURANCE_DIR = REPO_ROOT / "src" / "engcore" / "sria" / "assurance"


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
# Fixtures
# =====================================================================

AUTHORITY = AdmissionAuthority("arbiter.m3", secret="m3-test-secret")


def clean_run() -> RunOutcome:
    """A completed, uncensored run. Without one, censoring and failure
    attribution are genuinely unassessable and the critic says so."""
    return RunOutcome(
        disposition=Disposition.SUCCESS,
        attributed_cause=AttributedCause.NONE,
        completion_fraction=1.0,
        informative_for_pf=True,
    )


def registry() -> AdmissionAuthorityRegistry:
    return AdmissionAuthorityRegistry([AUTHORITY])


def declaration(
    *,
    numerical: Uncertainty | None = None,
    discrepancy: ModelDiscrepancy | None = None,
) -> UncertaintyDeclaration:
    channels = {}
    if numerical is not None:
        channels[UncertaintyChannel.NUMERICAL] = numerical
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=discrepancy
        or ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="linear resistive network taken as exact for this campaign",
        ),
        channels=channels,
    )


def quantified(magnitude: float = 1e-12, units: str = "volt") -> Uncertainty:
    return Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(magnitude, units),
        method="linear-system residual bound",
    )


def good_result(result_id: str = "res-good") -> ScientificResult:
    return ScientificResult(
        result_id=result_id,
        values={"V:mid": Quantity(9.0, "volt")},
        provenance=ProvenanceRecord(run_id="run-1"),
        solver=SolverIdentity(solver_id="demo.linear", version="1"),
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


def evidence_for(result: ScientificResult, evidence_id: str = "ev-m3") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="V:mid"),
        claim_payload={"value": 9.0, "units": "volt"},
        uncertainty=declaration(numerical=quantified()),
        provenance_ref=result.provenance.run_id,
        domain_pack_ref="electrical.dc",
    )


def full_budget(*, numerical: Uncertainty | None = None) -> UncertaintyBudget:
    decl = declaration(numerical=numerical)
    return UncertaintyBudget(
        value_name="V:mid",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN if numerical else ChannelState.UNKNOWN,
                uncertainty=numerical or Uncertainty.unknown(),
            ),
            ChannelEntry(
                channel=UncertaintyChannel.ALEATORIC,
                state=ChannelState.NOT_APPLICABLE,
                rationale="deterministic linear solve; no stochastic input",
            ),
            ChannelEntry(
                channel=UncertaintyChannel.EPISTEMIC_PARAMETER,
                state=ChannelState.UNKNOWN,
            ),
            ChannelEntry(
                channel=UncertaintyChannel.MODEL_FORM,
                state=ChannelState.UNKNOWN,
            ),
        ),
        declaration=decl,
    )


class DemoDomainCritic:
    """Tiny Electrical-DC domain critic. Domain semantics stay in the domain."""

    critic_id = "electrical.dc.critic"
    critic_version = "1"
    domain_pack_ref = "electrical.dc"

    def __init__(self, *, discrepancy_supported_by: str = "") -> None:
        self._support = discrepancy_supported_by

    def assess_domain(
        self, result, *, assessment_id, budget=None, mandatory_checks=()
    ) -> CriticAssessment:
        mandatory = set(mandatory_checks)
        checks: list[CheckRecord] = []
        findings: list[Finding] = []

        voltages = [v for k, v in result.values.items() if k.startswith("V:")]
        within = all(abs(v.magnitude) <= 1e6 for v in voltages)
        checks.append(
            CheckRecord(
                name="physical_constraints",
                outcome=CriticVerdict.PASS if within else CriticVerdict.FAIL,
                mandatory="physical_constraints" in mandatory,
                detail=f"{len(voltages)} node voltage(s) within declared range",
                threshold=1e6,
                threshold_source="electrical.dc pack validity range",
            )
        )
        checks.append(
            CheckRecord(
                name="scope_validity",
                outcome=CriticVerdict.PASS,
                mandatory="scope_validity" in mandatory,
                detail="linear resistive steady-state network",
            )
        )
        if budget is not None:
            record, extra = model_discrepancy_check(
                budget,
                supported_by=self._support,
                mandatory="model_discrepancy_supported" in mandatory,
            )
            checks.append(record)
            findings.extend(extra)

        verdict = NumericalCritic._verdict(checks, findings)
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=CriticClass.DOMAIN,
            subject_ref=result.result_id,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
            ),
            checks=tuple(checks),
            findings=tuple(findings),
            summary=f"domain assessment: {verdict.value}",
        )


def standard_obligations(campaign_id: str = "camp-m3") -> ObligationSet:
    charter = CampaignCharter(
        campaign_id=campaign_id,
        terminal_decisions=(
            TerminalDecision(decision_id="d1", statement="Accept the divider result"),
        ),
    )
    return obligations_from_charter(
        charter,
        required_critics=(CriticClass.NUMERICAL, CriticClass.DOMAIN),
        required_checks=("residual_evidence",),
        required_domain_checks=("physical_constraints",),
        required_uncertainty_channels=(UncertaintyChannel.NUMERICAL,),
    )


def run_pipeline(
    *,
    result: ScientificResult,
    budget: UncertaintyBudget,
    obligations: ObligationSet,
    domain_critic=None,
    calibration_reports=(),
    required_calibration=(),
    mandatory_numerical=("residual_evidence",),
    subject_ref=None,
    run_outcome=None,
):
    """Result -> critics -> arbiter. Returns (assessments, decision, arbiter).

    The Arbiter instance is returned because M3.1 only lets an Arbiter
    authorize decisions it actually issued; a fresh instance would (rightly)
    refuse.

    ``subject_ref`` is the artifact the *decision* is about. Critics assess a
    result; admission is about an evidence record, so a flow that ends in
    admission decides about the evidence id. The Arbiter's binding check then
    prevents replaying a decision onto a different record.
    """
    run_outcome = clean_run() if run_outcome is None else run_outcome
    assessments = [
        NumericalCritic().assess(
            result,
            assessment_id="as-num",
            budget=budget,
            mandatory_checks=mandatory_numerical,
            run_outcome=run_outcome,
        )
    ]
    if domain_critic is not None:
        assessments.append(
            domain_critic.assess_domain(
                result,
                assessment_id="as-dom",
                budget=budget,
                mandatory_checks=obligations.required_domain_checks,
            )
        )
    if calibration_reports:
        assessments.append(
            CalibrationCriticAdapter().assess(
                calibration_reports,
                assessment_id="as-cal",
                subject_ref=result.result_id,
                required_verdicts=required_calibration,
            )
        )
    arbiter = Arbiter(AUTHORITY)
    decision = arbiter.decide(
        decision_id="dec-1",
        subject_ref=subject_ref or result.result_id,
        assessments=assessments,
        obligations=obligations,
        budget=budget,
    )
    return assessments, decision, arbiter


# =====================================================================
# 1-4. Uncertainty budget
# =====================================================================

def test_missing_diagnostics_cannot_become_pass():
    """(1) No residual evidence -> NOT_ASSESSED, never PASS."""
    bare = ScientificResult(
        result_id="res-bare",
        values={"x": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.CONVERGED,
    )
    assessment = NumericalCritic().assess(
        bare,
        assessment_id="a1",
        budget=full_budget(numerical=quantified()),
        mandatory_checks=("residual_evidence",),
    )
    residual = assessment.check("residual_evidence")
    assert residual.outcome is CriticVerdict.NOT_ASSESSED
    assert residual.outcome is not CriticVerdict.PASS
    assert assessment.verdict is CriticVerdict.NOT_ASSESSED
    assert "residual_evidence" in assessment.checks_skipped


def test_unknown_uncertainty_is_preserved_never_zeroed():
    """(2) UNKNOWN stays UNKNOWN and cannot be aggregated as zero."""
    budget = full_budget(numerical=None)
    entry = budget.entry(UncertaintyChannel.NUMERICAL)
    assert entry.state is ChannelState.UNKNOWN
    assert entry.is_quantified is False
    assert entry.uncertainty.is_quantified is False

    # Aggregation refuses rather than substituting zero.
    _raises(
        BudgetError,
        budget.aggregate,
        [UncertaintyChannel.NUMERICAL],
        assumptions=("independent",),
    )

    # An undeclared channel is reported UNKNOWN, not omitted.
    sparse = UncertaintyBudget(
        value_name="v",
        entries=(),
        declaration=declaration(),
    )
    assert sparse.entry(UncertaintyChannel.MODEL_FORM).state is ChannelState.UNKNOWN
    assert set(sparse.missing_channels) == set(UncertaintyChannel)

    # KNOWN cannot be asserted without a value.
    _raises(
        BudgetError,
        ChannelEntry,
        channel=UncertaintyChannel.MODEL_FORM,
        state=ChannelState.KNOWN,
    )


def test_numerical_and_model_form_remain_distinct():
    """(3) Distinct channels are not silently combined."""
    budget = UncertaintyBudget(
        value_name="v",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN,
                uncertainty=quantified(1e-9),
            ),
            ChannelEntry(
                channel=UncertaintyChannel.MODEL_FORM,
                state=ChannelState.KNOWN,
                uncertainty=quantified(0.5),
            ),
        ),
        declaration=declaration(),
    )
    assert (
        budget.entry(UncertaintyChannel.NUMERICAL).uncertainty
        != budget.entry(UncertaintyChannel.MODEL_FORM).uncertainty
    )
    # Cross-kind aggregation is refused by default.
    _raises(
        BudgetError,
        budget.aggregate,
        [UncertaintyChannel.NUMERICAL, UncertaintyChannel.MODEL_FORM],
        assumptions=("independent",),
    )
    # Allowed only with an explicit opt-in AND a stated assumption.
    record = budget.aggregate(
        [UncertaintyChannel.NUMERICAL, UncertaintyChannel.MODEL_FORM],
        assumptions=("channels are independent",),
        allow_cross_kind=True,
    )
    assert record.rule == "root_sum_square"
    assert record.assumptions == ("channels are independent",)
    assert len(record.channels_combined) == 2


def test_incompatible_quantities_cannot_be_combined():
    """(4) Different units and different semantics both refuse."""
    mixed_units = UncertaintyBudget(
        value_name="v",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN,
                uncertainty=quantified(1.0, "volt"),
            ),
            ChannelEntry(
                channel=UncertaintyChannel.ALEATORIC,
                state=ChannelState.KNOWN,
                uncertainty=quantified(1.0, "kelvin"),
            ),
        ),
        declaration=declaration(),
    )
    _raises(
        IncomparableUncertainty,
        mixed_units.aggregate,
        [UncertaintyChannel.NUMERICAL, UncertaintyChannel.ALEATORIC],
        assumptions=("independent",),
        allow_cross_kind=True,
    )

    interval = Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(-1.0, "volt"),
        upper=Quantity(1.0, "volt"),
        method="bound",
    )
    mixed_semantics = UncertaintyBudget(
        value_name="v",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN,
                uncertainty=quantified(1.0, "volt"),
            ),
            ChannelEntry(
                channel=UncertaintyChannel.ALEATORIC,
                state=ChannelState.BOUNDED,
                uncertainty=interval,
            ),
        ),
        declaration=declaration(),
    )
    _raises(
        IncomparableUncertainty,
        mixed_semantics.aggregate,
        [UncertaintyChannel.NUMERICAL, UncertaintyChannel.ALEATORIC],
        assumptions=("independent",),
        allow_cross_kind=True,
    )


def test_double_counting_a_channel_is_refused():
    _raises(
        BudgetError,
        UncertaintyBudget,
        value_name="v",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN,
                uncertainty=quantified(),
            ),
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN,
                uncertainty=quantified(),
            ),
        ),
        declaration=declaration(),
    )


def test_not_applicable_requires_a_rationale():
    _raises(
        BudgetError,
        ChannelEntry,
        channel=UncertaintyChannel.ALEATORIC,
        state=ChannelState.NOT_APPLICABLE,
    )


# =====================================================================
# 5-6. Critic purity
# =====================================================================

def test_numerical_critic_cannot_mutate_belief():
    """(5) The critic holds nothing that could write belief."""
    critic = NumericalCritic()
    for forbidden in ("submit", "belief", "gateway", "admit", "_apply"):
        assert not hasattr(critic, forbidden)

    gateway = BeliefUpdateGateway(authorities=registry())
    assessment = critic.assess(
        good_result(), assessment_id="a", budget=full_budget(numerical=quantified())
    )
    # Its output is not admissible evidence on its own.
    _raises(BeliefWriteViolation, gateway.submit, assessment)
    assert len(gateway.belief) == 0


def test_domain_critic_cannot_mutate_belief():
    """(6) Same purity rule for domain critics."""
    critic = DemoDomainCritic()
    for forbidden in ("submit", "belief", "gateway", "admit"):
        assert not hasattr(critic, forbidden)

    gateway = BeliefUpdateGateway(authorities=registry())
    assessment = critic.assess_domain(good_result(), assessment_id="a")
    _raises(BeliefWriteViolation, gateway.submit, assessment)
    assert len(gateway.belief) == 0


# =====================================================================
# 7-9. Admission path
# =====================================================================

def test_critic_pass_alone_cannot_admit():
    """(7) A PASS is evidence, not authority."""
    result = good_result()
    evidence = evidence_for(result)
    gateway = BeliefUpdateGateway(authorities=registry())

    assessment = NumericalCritic().assess(
        result,
        assessment_id="a",
        budget=full_budget(numerical=quantified()),
        run_outcome=clean_run(),
    )
    assert assessment.verdict is CriticVerdict.PASS

    assessed = evidence.with_assessment(assessment.to_evidence_assessment())
    # Still not admitted: no declaration exists.
    _raises(BeliefWriteViolation, gateway.submit, assessed)
    assert len(gateway.belief) == 0


def test_solver_success_alone_cannot_admit():
    """(8) A converged solve is not an admission."""
    result = good_result()
    assert result.convergence is ConvergenceState.CONVERGED
    evidence = evidence_for(result)
    gateway = BeliefUpdateGateway(authorities=registry())
    _raises(BeliefWriteViolation, gateway.submit, evidence)

    # Nor does forcing the lifecycle flag by hand.
    forced = Evidence(
        evidence_id="ev-forced",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="V:mid"),
        claim_payload={"value": 9.0},
        uncertainty=declaration(numerical=quantified()),
        provenance_ref="run-1",
        domain_pack_ref="electrical.dc",
        status=EvidenceStatus.ACCEPTED,
    )
    _raises(Exception, gateway.submit, forced)
    assert len(gateway.belief) == 0


def test_fabricated_arbiter_output_cannot_admit():
    """(9) Only a registered authority's declaration is accepted."""
    result = good_result()
    evidence = evidence_for(result)
    gateway = BeliefUpdateGateway(authorities=registry())

    # M3.2: a rogue authority recognises no Arbiter, so it cannot sign an
    # accepting declaration at all — refused before the gateway is reached.
    rogue = AdmissionAuthority("arbiter.rogue", secret="x")
    _raises(
        AdmissionAuthorityError,
        rogue.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
    )

    assessed = evidence.with_assessment(
        NumericalCritic()
        .assess(
            result,
            assessment_id="a",
            budget=full_budget(numerical=quantified()),
            run_outcome=clean_run(),
        )
        .to_evidence_assessment()
    )
    unsigned = AdmissionDeclaration(
        admitted=True,
        arbiter_id="arbiter.m3",
        subject_record_hash=evidence.record_hash,
    )
    # An unsigned declaration is refused by the gateway itself.
    _raises(AdmissionAuthorityError, gateway.submit, assessed.admit(unsigned))
    assert len(gateway.belief) == 0


# =====================================================================
# 10-13. Arbiter obligations
# =====================================================================

def test_skipping_a_mandatory_critic_prevents_valid():
    """(10) Domain critic required but not run."""
    result = good_result()
    budget = full_budget(numerical=quantified())
    obligations = standard_obligations()

    _assessments, decision, _arb = run_pipeline(
        result=result, budget=budget, obligations=obligations, domain_critic=None
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
    assert any("domain" in r for r in decision.reasons)


def test_untrusted_calibration_prevents_valid():
    """(11) A green solver does not hide an untrusted calibration."""
    result = good_result()
    budget = full_budget(numerical=quantified())
    charter = CampaignCharter(
        campaign_id="camp-cal",
        terminal_decisions=(TerminalDecision(decision_id="d", statement="s"),),
    )
    obligations = obligations_from_charter(
        charter,
        required_critics=(CriticClass.NUMERICAL, CriticClass.CALIBRATION),
        required_calibration_verdicts=(CalibrationVerdict.TRUSTED,),
    )
    untrusted = CalibrationReport(
        model_id="cost.bad",
        model_version="cost/1",
        verdict=CalibrationVerdict.UNTRUSTED,
    )
    _assessments, decision, _arb = run_pipeline(
        result=result,
        budget=budget,
        obligations=obligations,
        calibration_reports=(untrusted,),
        required_calibration=(CalibrationVerdict.TRUSTED,),
        mandatory_numerical=(),
    )
    # M3.1: an untrusted auxiliary calibration blocks certification; it does
    # not disprove the science.
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
    assert decision.verdict is not AssuranceVerdict.INVALID
    assert any("calibration" in r for r in decision.reasons)


def test_insufficient_data_is_distinct_from_untrusted():
    """(12) 'could not judge' != 'judged and bad'."""
    adapter = CalibrationCriticAdapter()
    insufficient = adapter.assess(
        [
            CalibrationReport(
                model_id="failure.none",
                model_version="f/1",
                verdict=CalibrationVerdict.INSUFFICIENT_DATA,
            )
        ],
        assessment_id="a-i",
        subject_ref="res",
    )
    untrusted = adapter.assess(
        [
            CalibrationReport(
                model_id="cost.bad",
                model_version="c/1",
                verdict=CalibrationVerdict.UNTRUSTED,
            )
        ],
        assessment_id="a-u",
        subject_ref="res",
    )
    # The per-model mapping is where the distinction lives.
    assert (
        insufficient.check("calibration:failure.none").outcome
        is CriticVerdict.NOT_ASSESSED
    )
    assert untrusted.check("calibration:cost.bad").outcome is CriticVerdict.FAIL
    assert insufficient.verdict is not untrusted.verdict
    assert untrusted.verdict is CriticVerdict.FAIL
    codes = {f.code for f in insufficient.findings}
    assert "calibration.insufficient_data" in codes


def test_zero_declared_discrepancy_stays_visible():
    """(13) ZERO_DECLARED is a choice, never a proof of exactness."""
    budget = full_budget(numerical=quantified())
    assert budget.declares_zero_discrepancy is True
    assert budget.model_discrepancy.kind is DiscrepancyKind.ZERO_DECLARED

    # Unsupported: flagged, but an unexamined assumption is not a refuted one.
    record, findings = model_discrepancy_check(budget, mandatory=True)
    assert record.outcome is CriticVerdict.INCONCLUSIVE
    assert findings[0].severity is Severity.MAJOR
    assert findings[0].invalidates_subject is False
    assert "never that the model is exact" in findings[0].message

    # Supported: still explicitly visible as a declared choice.
    record2, findings2 = model_discrepancy_check(
        budget, supported_by="benchmark study X", mandatory=True
    )
    assert record2.outcome is CriticVerdict.PASS
    assert findings2[0].code == "domain.zero_discrepancy_declared"
    assert "not a proof the model is exact" in findings2[0].message


def test_unquantified_required_channel_blocks_valid():
    """UNKNOWN where quantification is required blocks VALID, not ignored."""
    result = good_result()
    budget = full_budget(numerical=None)      # numerical UNKNOWN
    obligations = standard_obligations()
    _assessments, decision, _arb = run_pipeline(
        result=result,
        budget=budget,
        obligations=obligations,
        domain_critic=DemoDomainCritic(discrepancy_supported_by="study X"),
    )
    assert decision.verdict is not AssuranceVerdict.VALID
    assert any("uncertainty channel numerical" in r for r in decision.reasons)


def test_empty_obligations_cannot_produce_valid():
    result = good_result()
    decision = Arbiter(AUTHORITY).decide(
        decision_id="d",
        subject_ref=result.result_id,
        assessments=[
            NumericalCritic().assess(
                result, assessment_id="a", budget=full_budget(numerical=quantified())
            )
        ],
        obligations=ObligationSet(campaign_id="empty"),
        budget=full_budget(numerical=quantified()),
    )
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE


def test_no_assessments_is_not_assessed():
    decision = Arbiter(AUTHORITY).decide(
        decision_id="d",
        subject_ref="res",
        assessments=[],
        obligations=standard_obligations(),
    )
    assert decision.verdict is AssuranceVerdict.NOT_ASSESSED


def test_invalid_is_evidence_backed():
    """INVALID requires an actual failure, not a missing critic."""
    failed = ScientificResult(
        result_id="res-failed",
        values={"x": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.FAILED,
    )
    _assessments, decision, _arb = run_pipeline(
        result=failed,
        budget=full_budget(numerical=quantified()),
        obligations=standard_obligations(),
        domain_critic=DemoDomainCritic(discrepancy_supported_by="study X"),
    )
    assert decision.verdict is AssuranceVerdict.INVALID
    assert any("solver" in r or "convergence" in r for r in decision.reasons)

    # Whereas a merely-skipped critic is INCONCLUSIVE, not INVALID.
    _a2, d2, _arb2 = run_pipeline(
        result=good_result(),
        budget=full_budget(numerical=quantified()),
        obligations=standard_obligations(),
        domain_critic=None,
    )
    assert d2.verdict is AssuranceVerdict.INCONCLUSIVE


# =====================================================================
# 14-15. Suspension and replay
# =====================================================================

def test_suspended_evidence_leaves_active_belief():
    """(14) admitted -> suspended -> gone from the active view."""
    result = good_result()
    evidence = evidence_for(result)
    gateway = BeliefUpdateGateway(authorities=registry())

    budget = full_budget(numerical=quantified())
    obligations = standard_obligations()
    assessments, decision, arbiter = run_pipeline(
        result=result,
        budget=budget,
        obligations=obligations,
        domain_critic=DemoDomainCritic(discrepancy_supported_by="study X"),
        subject_ref=evidence.evidence_id,
    )
    assert decision.verdict is AssuranceVerdict.VALID

    assessed = evidence
    for assessment in assessments:
        assessed = assessed.with_assessment(assessment.to_evidence_assessment())
    admitted = assessed.admit(arbiter.authorize_admission(decision, assessed))
    gateway.submit(admitted)
    assert gateway.belief.supports(admitted.belief_key)

    suspended = admitted.suspend("superseding measurement pending")
    gateway.update_standing(suspended)
    assert gateway.belief.supports(admitted.belief_key) is False
    assert len(gateway.belief) == 0
    # The audit trail keeps the history.
    assert len(gateway.belief.audit_log()) == 1


def test_arbiter_decisions_are_replayable():
    """(15) Decision round-trips and maps onto M1 decision provenance."""
    result = good_result()
    _assessments, decision, _arb = run_pipeline(
        result=result,
        budget=full_budget(numerical=quantified()),
        obligations=standard_obligations(),
        domain_critic=DemoDomainCritic(discrepancy_supported_by="study X"),
    )
    reloaded = ArbiterDecision.from_dict(json.loads(json.dumps(decision.to_dict())))
    assert reloaded.verdict is decision.verdict
    assert reloaded.decision_id == decision.decision_id
    assert reloaded.assessment_refs == decision.assessment_refs
    assert reloaded.obligation_results == decision.obligation_results

    provenance = decision.to_decision_provenance()
    assert provenance.policy_id == "sria.arbiter"
    assert provenance.chosen_action == decision.verdict.value
    assert provenance.human_override is False


def test_admission_declaration_is_bound_to_its_subject():
    result = good_result()
    evidence = evidence_for(result)
    other = evidence_for(good_result("res-other"), evidence_id="ev-other")
    _assessments, decision, _arb = run_pipeline(
        result=result,
        budget=full_budget(numerical=quantified()),
        obligations=standard_obligations(),
        domain_critic=DemoDomainCritic(discrepancy_supported_by="study X"),
        subject_ref=evidence.evidence_id,
    )
    _raises(ValueError, _arb.authorize_admission, decision, other)


def test_non_valid_decision_yields_a_declining_declaration():
    result = good_result()
    evidence = evidence_for(result)
    _assessments, decision, _arb = run_pipeline(
        result=result,
        budget=full_budget(numerical=quantified()),
        obligations=standard_obligations(),
        domain_critic=None,      # mandatory critic skipped
        subject_ref=evidence.evidence_id,
    )
    assessed = evidence.with_assessment(_assessments[0].to_evidence_assessment())
    refusal = _arb.authorize_admission(decision, assessed)
    assert refusal.admitted is False

    # Declining leaves scientific standing untouched (M1.1 semantics).
    after = assessed.admit(refusal)
    assert after.status is EvidenceStatus.ASSESSED
    assert after.status is not EvidenceStatus.INVALID


# =====================================================================
# 16. Trust boundary
# =====================================================================

def test_no_llm_dependency_in_assurance():
    from src.engcore.sria.trust import assert_no_llm_dependencies, find_forbidden_imports

    assert ASSURANCE_DIR.is_dir()
    assert find_forbidden_imports([ASSURANCE_DIR]) == ()
    assert_no_llm_dependencies([ASSURANCE_DIR])


def test_assurance_does_not_import_a_domain():
    """The generic core must not depend on any scientific domain."""
    for path in sorted(ASSURANCE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "domains" not in node.module, f"{path.name} imports {node.module}"


# =====================================================================
# ADVERSARIAL DEFECT MATRIX — VALID must be unreachable in every row
# =====================================================================

def test_defect_matrix_fails_closed():
    obligations = standard_obligations()
    good_budget = full_budget(numerical=quantified())
    supported_domain = DemoDomainCritic(discrepancy_supported_by="study X")

    cases: list[tuple[str, dict]] = []

    # 1. missing residual
    cases.append(
        (
            "missing_residual",
            dict(
                result=ScientificResult(
                    result_id="res-nores",
                    values={"x": Quantity(1.0, "volt")},
                    provenance=ProvenanceRecord(run_id="r"),
                    convergence=ConvergenceState.CONVERGED,
                ),
                budget=good_budget,
                obligations=obligations,
                domain_critic=supported_domain,
            ),
        )
    )
    # 2. non-converged result
    cases.append(
        (
            "not_converged",
            dict(
                result=ScientificResult(
                    result_id="res-nc",
                    values={"x": Quantity(1.0, "volt")},
                    provenance=ProvenanceRecord(run_id="r"),
                    convergence=ConvergenceState.MAX_ITERATIONS,
                    validation=good_result().validation,
                ),
                budget=good_budget,
                obligations=obligations,
                domain_critic=supported_domain,
            ),
        )
    )
    # 3. unknown numerical uncertainty
    cases.append(
        (
            "unknown_numerical_uncertainty",
            dict(
                result=good_result(),
                budget=full_budget(numerical=None),
                obligations=obligations,
                domain_critic=supported_domain,
            ),
        )
    )
    # 4. skipped domain critic
    cases.append(
        (
            "skipped_domain_critic",
            dict(
                result=good_result(),
                budget=good_budget,
                obligations=obligations,
                domain_critic=None,
            ),
        )
    )
    # 5. unsupported ZERO_DECLARED discrepancy
    unsupported_obligations = obligations_from_charter(
        CampaignCharter(
            campaign_id="camp-disc",
            terminal_decisions=(TerminalDecision(decision_id="d", statement="s"),),
        ),
        required_critics=(CriticClass.NUMERICAL, CriticClass.DOMAIN),
        required_domain_checks=("model_discrepancy_supported",),
        required_uncertainty_channels=(UncertaintyChannel.NUMERICAL,),
    )
    cases.append(
        (
            "unsupported_zero_discrepancy",
            dict(
                result=good_result(),
                budget=good_budget,
                obligations=unsupported_obligations,
                domain_critic=DemoDomainCritic(),   # no support declared
            ),
        )
    )
    # 6. untrusted calibration
    cal_obligations = obligations_from_charter(
        CampaignCharter(
            campaign_id="camp-cal2",
            terminal_decisions=(TerminalDecision(decision_id="d", statement="s"),),
        ),
        required_critics=(CriticClass.NUMERICAL, CriticClass.CALIBRATION),
        required_calibration_verdicts=(CalibrationVerdict.TRUSTED,),
    )
    cases.append(
        (
            "untrusted_calibration",
            dict(
                result=good_result(),
                budget=good_budget,
                obligations=cal_obligations,
                calibration_reports=(
                    CalibrationReport(
                        model_id="c",
                        model_version="1",
                        verdict=CalibrationVerdict.UNTRUSTED,
                    ),
                ),
                required_calibration=(CalibrationVerdict.TRUSTED,),
                mandatory_numerical=(),
            ),
        )
    )

    outcomes = {}
    for name, kwargs in cases:
        _assessments, decision, _arb = run_pipeline(**kwargs)
        outcomes[name] = decision.verdict
        assert decision.verdict is not AssuranceVerdict.VALID, (
            f"defect {name!r} still reached VALID"
        )

    # Every defect produced a *reasoned* non-VALID verdict.
    assert set(outcomes) == {n for n, _ in cases}
    assert all(v is not AssuranceVerdict.VALID for v in outcomes.values())

    # 7. incompatible units — refused at budget level, never reaching a verdict
    _raises(
        IncomparableUncertainty,
        UncertaintyBudget(
            value_name="v",
            entries=(
                ChannelEntry(
                    channel=UncertaintyChannel.NUMERICAL,
                    state=ChannelState.KNOWN,
                    uncertainty=quantified(1.0, "volt"),
                ),
                ChannelEntry(
                    channel=UncertaintyChannel.ALEATORIC,
                    state=ChannelState.KNOWN,
                    uncertainty=quantified(1.0, "kelvin"),
                ),
            ),
            declaration=declaration(),
        ).aggregate,
        [UncertaintyChannel.NUMERICAL, UncertaintyChannel.ALEATORIC],
        assumptions=("independent",),
        allow_cross_kind=True,
    )

    # 8. fabricated admission — covered above, restated as a matrix row
    ev = evidence_for(good_result())
    gateway = BeliefUpdateGateway(authorities=registry())
    rogue = AdmissionAuthority("rogue", secret="x")
    _raises(
        AdmissionAuthorityError,
        rogue.issue,
        admitted=True,
        subject_record_hash=ev.record_hash,
    )
    assert len(gateway.belief) == 0


# =====================================================================
# REAL DOMAIN DEMONSTRATION — Electrical DC
# =====================================================================

GND = ElectricalNode("gnd", is_reference=True)


def divider_circuit() -> DCCircuit:
    return DCCircuit(
        circuit_id="divider",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(1.0, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),
        ),
    )


def test_end_to_end_electrical_dc_reaches_belief():
    """Real domain: result -> budget -> critics -> arbiter -> gateway -> belief."""
    result = solve_circuit(divider_circuit(), run_id="run-demo")
    assert result.convergence is ConvergenceState.CONVERGED

    # Numerical uncertainty derived from the residual the domain recorded.
    residuals = [c for c in result.validation.checks if c.residual is not None]
    assert residuals, "the DC domain should record a residual"
    budget = UncertaintyBudget(
        value_name="node_voltage:mid",
        entries=(
            ChannelEntry(
                channel=UncertaintyChannel.NUMERICAL,
                state=ChannelState.KNOWN,
                uncertainty=Uncertainty(
                    kind=UncertaintyKind.STANDARD,
                    standard_uncertainty=Quantity(
                        max(residuals[0].residual, 1e-15), "volt"
                    ),
                    method="linear-system residual",
                ),
            ),
            ChannelEntry(
                channel=UncertaintyChannel.ALEATORIC,
                state=ChannelState.NOT_APPLICABLE,
                rationale="deterministic linear solve",
            ),
        ),
        declaration=declaration(numerical=quantified()),
    )

    evidence = Evidence(
        evidence_id="ev-divider",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(
            subject_kind="qoi", subject_ref="node_voltage:mid"
        ),
        claim_payload={
            "value": result.value("node_voltage:mid").magnitude,
            "units": str(result.value("node_voltage:mid").units),
        },
        uncertainty=declaration(numerical=quantified()),
        provenance_ref=result.provenance.run_id,
        domain_pack_ref="electrical.dc",
    )

    assessments, decision, arbiter = run_pipeline(
        result=result,
        budget=budget,
        obligations=standard_obligations("camp-divider"),
        domain_critic=DemoDomainCritic(
            discrepancy_supported_by="hand-derived analytical divider values"
        ),
        subject_ref=evidence.evidence_id,
    )
    assert decision.verdict is AssuranceVerdict.VALID

    assessed = evidence
    for assessment in assessments:
        assessed = assessed.with_assessment(assessment.to_evidence_assessment())
    admitted = assessed.admit(arbiter.authorize_admission(decision, assessed))

    gateway = BeliefUpdateGateway(authorities=registry())
    entry = gateway.submit(admitted)
    assert entry.evidence_id == "ev-divider"
    assert gateway.belief.supports(admitted.belief_key)
    # 12 V across 1k + 3k -> 9 V at the midpoint.
    assert abs(result.value("node_voltage:mid").magnitude - 9.0) < 1e-9


def test_end_to_end_defective_result_does_not_reach_belief():
    """The same pipeline, one defect: no residual recorded."""
    solved = solve_circuit(divider_circuit(), run_id="run-defect")
    stripped = ScientificResult(
        result_id="res-stripped",
        values=solved.values,
        provenance=solved.provenance,
        convergence=solved.convergence,
        validation=ValidationReport(),      # diagnostics removed
    )

    assessments, decision, arbiter = run_pipeline(
        result=stripped,
        budget=full_budget(numerical=quantified()),
        obligations=standard_obligations("camp-defect"),
        domain_critic=DemoDomainCritic(discrepancy_supported_by="study X"),
        subject_ref="ev-defect",
    )
    assert decision.verdict is not AssuranceVerdict.VALID

    evidence = evidence_for(stripped, evidence_id="ev-defect")
    assessed = evidence
    for assessment in assessments:
        assessed = assessed.with_assessment(assessment.to_evidence_assessment())

    refusal = arbiter.authorize_admission(decision, assessed)
    assert refusal.admitted is False

    gateway = BeliefUpdateGateway(authorities=registry())
    after = assessed.admit(refusal)
    _raises(BeliefWriteViolation, gateway.submit, after)
    assert len(gateway.belief) == 0
    # And the refusal did not scientifically invalidate the evidence.
    assert after.status is not EvidenceStatus.INVALID


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M3 — assurance tests")
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
        print(f"M3 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M3 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
