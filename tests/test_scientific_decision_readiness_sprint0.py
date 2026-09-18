"""Sprint 0 — structural pins for decision-to-evidence closure.

These are strict expected failures, not implementation tests.  They encode
surviving audit findings without prescribing the concrete adapter/class that
will eventually close them.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from engcore.scientific import oracles
from engcore.sria.assurance.arbiter import Arbiter
from engcore.sria.assurance import obligations_from_charter


def test_sdr01_production_tree_has_a_sria_bridge() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "engcore"
    imports: list[str] = []
    patterns = (
        re.compile(r"\bfrom\s+engcore\.sria\b"),
        re.compile(r"\bimport\s+engcore\.sria\b"),
        re.compile(r"\bfrom\s+\.\.sria\b"),
        re.compile(r"\bfrom\s+\.sria\b"),
    )

    for path in root.rglob("*.py"):
        # The bridge must be outside SRIA; SRIA importing itself proves nothing.
        if "sria" in path.relative_to(root).parts:
            continue
        source = path.read_text(encoding="utf-8")
        if any(pattern.search(source) for pattern in patterns):
            imports.append(str(path.relative_to(root)))

    assert imports, (
        "no production module outside src/engcore/sria imports SRIA; "
        "ScientificResult/CredibilityEvidenceReport cannot currently enter "
        "the SRIA evidence/decision path"
    )


def test_sdr03_arbiter_can_evaluate_charter_validation_levels() -> None:
    source = inspect.getsource(Arbiter.decide)
    assert "validation-level obligations are recorded but not evaluated" not in source
    assert "obligation {target} is not evaluable in M3" not in source


def test_sdr06_production_has_reviewed_trusted_external_oracle() -> None:
    registry = oracles._TRUSTED_ORACLE_DECLARATIONS
    assert registry
    declaration = registry[("nafems.p18.t3.transient_heat_1d", "1")]
    assert declaration["kind"] == "benchmark_dataset"
    assert len(declaration["evidence_digest"]) == 64


# ---------------------------------------------------------------------------
# Pass 2 — executable production traces
# ---------------------------------------------------------------------------

import dataclasses

from engcore.mcp import (
    CredibilityVerdict,
    example_electrothermal_payload,
    run_electrothermal_case,
)
from engcore.mcp.battery import example_battery_payload, run_battery_case
from engcore.mcp.sria_bridge import CredibilityReportCritic, evidence_from_credibility_report


def test_sdr04_verification_only_support_cannot_satisfy_a_validated_use() -> None:
    """The MCP layer already owns the right fail-closed evidence-basis rule.

    This is a CLOSED sub-invariant of SDR-04 and must survive the future bridge:
    a numerically credible result is not silently upgraded to evidence that the
    model matches the world.
    """
    outcome = run_electrothermal_case(example_electrothermal_payload())
    report = outcome.reports[0]

    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert report.evidence_basis == "VERIFICATION_ONLY"

    decision_grade = dataclasses.replace(
        report,
        required_evidence_basis="VALIDATED",
    )
    assert (
        decision_grade.verdict
        is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    )
    assert decision_grade.missing_evidence_basis == "VALIDATED"


def test_sdr05_battery_quantitative_values_close_the_uncertainty_chain() -> None:
    """Every quantitative value used by a later claim needs an uncertainty state.

    UNKNOWN is acceptable.  Silence is not: an absent entry cannot be mapped
    honestly into SRIA's decomposed uncertainty budget without inventing what
    the solver never declared.
    """
    report = run_battery_case(example_battery_payload()).report

    missing = sorted(set(report.values) - set(report.uncertainty))
    assert not missing, (
        "battery report has quantitative values with no uncertainty record: "
        f"{missing}"
    )


from engcore.sria import (
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Evidence,
    ModelDiscrepancy,
    SourceClass,
    SubjectModel,
    UncertaintyDeclaration,
    CampaignCharter,
    ConfidenceRequirement,
    TerminalDecision,
)


def _audit_uncertainty() -> UncertaintyDeclaration:
    """Minimal explicit declaration for structural evidence-identity probes."""
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.ZERO_DECLARED),
    )


def test_sdr02_belief_key_separates_different_contexts() -> None:
    base = dict(
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="temperature"),
        claim_payload={"value": 350.0, "units": "kelvin"},
        uncertainty=_audit_uncertainty(),
        provenance_ref="run-1",
        domain_pack_ref="thermal",
    )
    screening = Evidence(
        evidence_id="screening",
        context_ref="context:screening",
        **base,
    )
    certification = Evidence(
        evidence_id="certification",
        context_ref="context:certification",
        **base,
    )

    # Context already changes scientific-content identity: that part is good.
    assert screening.content_hash != certification.content_hash

    # The surviving gap: contribution grouping is still context-blind.
    assert screening.belief_key != certification.belief_key


def test_sdr07_evidence_records_source_dependency_closure() -> None:
    fields = Evidence.__dataclass_fields__
    assert "source_refs" in fields
    assert "source_closure_complete" in fields

    incomplete = Evidence(
        evidence_id="lineage-a",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="temperature"),
        claim_payload={"value": 350.0, "units": "kelvin"},
        uncertainty=_audit_uncertainty(),
        provenance_ref="run-a",
        domain_pack_ref="thermal",
        context_ref="context:lineage",
    )
    assert incomplete.independence_roots == ("run:run-a",)
    assert incomplete.source_closure_complete is False


from engcore.mcp.systems import SYSTEMS


def test_sdr09_conflicting_claims_remain_distinct_records() -> None:
    """Conflict is representable without averaging two incompatible values."""
    base = dict(
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="temperature"),
        uncertainty=_audit_uncertainty(),
        provenance_ref="run-conflict",
        domain_pack_ref="thermal",
        context_ref="context:same-use",
    )
    low = Evidence(
        evidence_id="temperature-low",
        claim_payload={"value": 350.0, "units": "kelvin"},
        **base,
    )
    high = Evidence(
        evidence_id="temperature-high",
        claim_payload={"value": 370.0, "units": "kelvin"},
        **base,
    )

    assert low.belief_key == high.belief_key
    assert low.content_hash != high.content_hash
    assert low.record_hash != high.record_hash


def test_sdr10_public_boundary_has_a_cross_domain_decision_tool() -> None:
    server_path = Path(__file__).resolve().parents[1] / "src" / "engcore" / "mcp" / "server.py"
    source = server_path.read_text(encoding="utf-8")
    registered = set(
        re.findall(
            r'server\\.add_tool\\(\\s*\\w+,\\s*name="([^"]+)"',
            source,
        )
    )
    assert "assess_claim" in registered


def test_sprint1_bridge_derives_claim_value_from_report() -> None:
    report = run_electrothermal_case(example_electrothermal_payload()).reports[0]
    quantity_name = next(iter(report.values))
    evidence = evidence_from_credibility_report(
        report,
        quantity_name=quantity_name,
        evidence_id="bridge-evidence",
        domain_pack_ref="electrothermal",
        context_ref="campaign:test#decision:d1",
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="fixture only: model discrepancy deliberately declared zero",
        ),
    )

    quantity = report.values[quantity_name]
    assert evidence.claim_binding.subject_ref == quantity_name
    assert evidence.claim_payload["value"] == quantity.magnitude
    assert evidence.claim_payload["units"] == str(quantity.units)
    assert evidence.provenance_ref == report.provenance.run_id
    assert evidence.context_ref == "campaign:test#decision:d1"


def test_sprint1_bridge_refuses_to_invent_model_discrepancy() -> None:
    report = run_electrothermal_case(example_electrothermal_payload()).reports[0]
    quantity_name = next(iter(report.values))
    with pytest.raises(TypeError):
        evidence_from_credibility_report(
            report,
            quantity_name=quantity_name,
            evidence_id="bridge-no-discrepancy",
            domain_pack_ref="electrothermal",
            context_ref="campaign:test#decision:d1",
            discrepancy=None,
        )


def test_sprint1_credibility_critic_exposes_attained_validation_levels() -> None:
    report = run_electrothermal_case(example_electrothermal_payload()).reports[0]
    critic = CredibilityReportCritic()
    assessment = critic.assess(report, assessment_id="cred-1")

    by_name = {check.name: check for check in assessment.checks}
    for level in report.attained_levels:
        assert by_name[f"validation_level:{level.value}"].outcome.value == "pass"


def test_sprint1_charter_validation_level_can_be_resolved_by_arbiter() -> None:
    from engcore.sria.admission import AdmissionAuthority
    from engcore.sria.assurance import trusting_authority

    report = run_electrothermal_case(example_electrothermal_payload()).reports[0]
    attained = sorted(report.attained_levels, key=lambda x: x.value)
    assert attained
    required = attained[0]

    charter = CampaignCharter(
        campaign_id="bridge-campaign",
        terminal_decisions=(
            TerminalDecision(decision_id="d1", statement="Use the computed QOI"),
        ),
        confidence_requirements=(
            ConfidenceRequirement(
                requirement_id="r1",
                required_levels=(required,),
                description="fixture requirement",
            ),
        ),
    )
    obligations = obligations_from_charter(charter)
    critic = CredibilityReportCritic()
    authority = trusting_authority(
        "bridge-authority",
        critics=(critic,),
        policies=(obligations,),
    )
    arbiter = Arbiter(authority, critics=(critic,))

    quantity_name = next(iter(report.values))
    evidence = evidence_from_credibility_report(
        report,
        quantity_name=quantity_name,
        evidence_id="bridge-decision-evidence",
        domain_pack_ref="electrothermal",
        context_ref=f"charter:{charter.digest}#decision:d1",
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="fixture only",
        ),
    )

    mandatory = tuple(o.target for o in obligations.obligations if o.target.startswith("validation_level:"))
    assessment = arbiter.run_critic(
        critic.critic_id,
        report,
        subject=evidence,
        assessment_id="credibility-levels",
        mandatory_checks=mandatory,
    )
    decision = arbiter.decide(
        decision_id="decision-1",
        evidence=evidence,
        assessments=(assessment,),
        obligations=obligations,
    )

    level_result = next(
        item for item in decision.obligation_results
        if item.obligation_id.startswith("confidence:")
    )
    assert level_result.satisfied is True



def test_sprint1_assurance_refuses_a_different_report_with_the_same_run_id() -> None:
    from engcore.sria.assurance import trusting_authority

    report = run_electrothermal_case(example_electrothermal_payload()).reports[0]
    altered = dataclasses.replace(report, notes="same run id, different report content")

    critic = CredibilityReportCritic()
    charter = CampaignCharter(
        campaign_id="digest-campaign",
        terminal_decisions=(
            TerminalDecision(decision_id="d1", statement="Use the computed QOI"),
        ),
    )
    obligations = obligations_from_charter(charter)
    authority = trusting_authority(
        "digest-authority",
        (critic,),
        policies=(obligations,),
    )
    arbiter = Arbiter(authority, critics=(critic,))

    quantity_name = next(iter(report.values))
    evidence = evidence_from_credibility_report(
        report,
        quantity_name=quantity_name,
        evidence_id="digest-bound-evidence",
        domain_pack_ref="electrothermal",
        context_ref=f"charter:{charter.digest}#decision:d1",
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="fixture only",
        ),
    )

    assessment = arbiter.run_critic(
        critic.critic_id,
        altered,
        subject=evidence,
        assessment_id="altered-report-assessment",
    )
    decision = arbiter.decide(
        decision_id="digest-decision",
        evidence=evidence,
        assessments=(assessment,),
        obligations=obligations,
    )

    assert "altered-report-assessment" in decision.refused_assessments
    assert any("not bound to the credibility report" in r for r in decision.reasons)



def test_validation_level_issuer_flag_must_be_an_explicit_bool() -> None:
    from engcore.sria.assurance import trusting_authority
    from engcore.sria.assurance.assessment import (
        CriticAssessment,
        CriticClass,
        CriticVerdict,
    )
    from engcore.sria.provenance import AssessmentProvenance

    class AmbiguousIssuer:
        critic_id = "ambiguous-level-issuer"
        critic_version = "1"
        critic_class = CriticClass.PROCESS
        validation_level_issuer = "false"

        def assess(self, evidence, *, assessment_id):
            return CriticAssessment(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                critic_class=self.critic_class,
                subject_ref=evidence.record_hash,
                verdict=CriticVerdict.PASS,
                provenance=AssessmentProvenance(
                    assessment_id=assessment_id,
                    critic_id=self.critic_id,
                    critic_version=self.critic_version,
                ),
            )

    with pytest.raises(TypeError, match="explicit bool"):
        trusting_authority("bad-issuer-authority", critics=(AmbiguousIssuer(),))
