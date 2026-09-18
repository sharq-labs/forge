"""Sprint 1 — production credibility report -> SRIA decision evidence.

The tests are deliberately end-to-end across the stable layers:

MCP credibility report -> integration bridge -> SRIA Evidence
-> registered process critic -> charter obligations -> Arbiter decision.

Nothing here fabricates a validation level or a scientific value.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.integration.decision_evidence import (
    CredibilityReportCritic,
    DecisionEvidenceBridgeError,
    decision_context_ref,
    evidence_from_credibility_report,
)
from engcore.mcp import (
    CredibilityVerdict,
    example_electrothermal_payload,
    run_electrothermal_case,
)
from engcore.mcp.battery import example_battery_payload, run_battery_case
from engcore.scientific import Quantity, Uncertainty, UncertaintyKind, ValidationLevel
from engcore.sria import (
    CampaignCharter,
    ConfidenceRequirement,
    DiscrepancyKind,
    TerminalDecision,
    UncertaintyChannel,
)
from engcore.sria.assurance import (
    Arbiter,
    AssuranceVerdict,
    CriticVerdict,
    budget_from_declaration,
    model_discrepancy_check,
    obligations_from_charter,
    trusting_authority,
)


def _charter(
    *,
    campaign_id: str = "bridge-campaign",
    decision_id: str = "accept-result",
    required_levels: tuple[ValidationLevel, ...] = (),
) -> CampaignCharter:
    requirements = ()
    if required_levels:
        requirements = (
            ConfidenceRequirement(
                requirement_id="scientific-confidence",
                description="decision may rely only on the declared evidence level",
                required_levels=required_levels,
            ),
        )
    return CampaignCharter(
        campaign_id=campaign_id,
        terminal_decisions=(
            TerminalDecision(
                decision_id=decision_id,
                statement="Decide whether this scientific result may be relied on",
            ),
        ),
        confidence_requirements=requirements,
    )


def _electrothermal_report():
    run = run_electrothermal_case(example_electrothermal_payload())
    report = run.reports[0]
    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert report.attained_levels
    return report


def _evidence(report, charter, *, evidence_id="bridge-evidence", value_name=None):
    value_name = value_name or next(iter(report.values))
    return evidence_from_credibility_report(
        report,
        evidence_id=evidence_id,
        value_name=value_name,
        domain_pack_ref="electrothermal",
        charter=charter,
        decision_id=charter.terminal_decisions[0].decision_id,
        operating_context_ref="fixture:nominal-operating-point",
    )


def _decision(report, evidence, charter, *, extra_uncertainty=()):
    critic = CredibilityReportCritic()
    obligations = obligations_from_charter(
        charter,
        required_uncertainty_channels=extra_uncertainty,
    )
    authority = trusting_authority(
        f"arbiter.{evidence.evidence_id}",
        (critic,),
        policies=(obligations,),
        secret=f"secret-{evidence.evidence_id}",
    )
    arbiter = Arbiter(authority, critics=(critic,))
    assessment = arbiter.run_critic(
        critic.critic_id,
        report,
        evidence,
        charter,
        subject=evidence,
        assessment_id=f"assessment-{evidence.evidence_id}",
    )
    budget = budget_from_declaration(
        evidence.belief_key,
        evidence.uncertainty,
    )
    decision = arbiter.decide(
        decision_id=f"decision-{evidence.evidence_id}",
        assessments=(assessment,),
        obligations=obligations,
        evidence=evidence,
        budget=budget,
    )
    return assessment, decision


def test_bridge_derives_claim_value_units_and_provenance_from_report() -> None:
    report = _electrothermal_report()
    charter = _charter()
    name = next(iter(report.values))
    quantity = report.values[name]

    evidence = _evidence(report, charter, value_name=name)

    assert evidence.claim_binding.subject_ref == name
    assert evidence.claim_payload == {
        "value": quantity.magnitude,
        "units": str(quantity.units),
    }
    assert evidence.provenance_ref == report.provenance.run_id
    assert evidence.metadata["source_report_run_id"] == report.run_id
    assert evidence.metadata["credibility_verdict"] == report.verdict.value
    assert evidence.metadata["evidence_basis"] == report.evidence_basis


def test_bridge_context_is_bound_to_exact_charter_and_terminal_decision() -> None:
    report = _electrothermal_report()
    charter_a = _charter(campaign_id="campaign-a", decision_id="d-a")
    charter_b = _charter(campaign_id="campaign-b", decision_id="d-b")

    a = _evidence(report, charter_a, evidence_id="a")
    b = _evidence(report, charter_b, evidence_id="b")

    assert a.context_ref != b.context_ref
    assert a.content_hash != b.content_hash
    # The bridge also makes the belief key context-sensitive through a
    # reserved ClaimBinding qualifier; evidence from two decisions is not
    # grouped as one contribution.
    assert a.belief_key != b.belief_key
    assert a.claim_binding.qualifiers["context_ref"] == a.context_ref


def test_context_helper_refuses_a_decision_not_owned_by_the_charter() -> None:
    charter = _charter()
    with pytest.raises(DecisionEvidenceBridgeError, match="not a terminal decision"):
        decision_context_ref(charter, "some-other-decision")


def test_default_model_form_discrepancy_is_unknown_not_zero() -> None:
    report = _electrothermal_report()
    evidence = _evidence(report, _charter())

    assert evidence.uncertainty.discrepancy.kind is DiscrepancyKind.UNKNOWN

    budget = budget_from_declaration(evidence.belief_key, evidence.uncertainty)
    check, findings = model_discrepancy_check(budget, mandatory=True)
    assert check.outcome is CriticVerdict.INCONCLUSIVE
    assert {finding.code for finding in findings} == {
        "domain.model_discrepancy_unknown"
    }


def test_attained_validation_level_can_satisfy_existing_charter_requirement() -> None:
    report = _electrothermal_report()
    level = sorted(report.attained_levels, key=lambda item: item.value)[0]
    charter = _charter(required_levels=(level,))
    evidence = _evidence(report, charter)

    assessment, decision = _decision(report, evidence, charter)

    check = assessment.check(f"validation_level:{level.value}")
    assert check is not None
    assert check.outcome is CriticVerdict.PASS
    assert decision.verdict is AssuranceVerdict.VALID


def test_unattained_external_validation_level_blocks_decision() -> None:
    report = _electrothermal_report()
    required = ValidationLevel.EXPERIMENTALLY_VALIDATED
    assert required not in report.attained_levels

    charter = _charter(required_levels=(required,))
    evidence = _evidence(report, charter)

    assessment, decision = _decision(report, evidence, charter)

    check = assessment.check(f"validation_level:{required.value}")
    assert check is not None
    assert check.outcome is CriticVerdict.NOT_ASSESSED
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
    assert any(
        result.obligation_id.startswith("confidence:")
        and not result.satisfied
        for result in decision.obligation_results
    )


def test_report_evidence_binding_is_rechecked_by_registered_critic() -> None:
    report = _electrothermal_report()
    charter = _charter()
    evidence = _evidence(report, charter)

    tampered = dataclasses.replace(
        evidence,
        claim_payload={
            "value": float(evidence.claim_payload["value"]) * 1000.0,
            "units": evidence.claim_payload["units"],
        },
        content_hash="",
    )

    critic = CredibilityReportCritic()
    assessment = critic.assess(
        report,
        tampered,
        charter,
        assessment_id="tamper-assessment",
    )
    assert assessment.verdict is CriticVerdict.FAIL
    assert assessment.check("credibility_report_binding").outcome is CriticVerdict.FAIL




def test_critic_refuses_evidence_bound_to_a_different_charter() -> None:
    report = _electrothermal_report()
    charter_a = _charter(campaign_id="context-a", decision_id="decision-a")
    charter_b = _charter(campaign_id="context-b", decision_id="decision-b")
    evidence = _evidence(report, charter_a)

    critic = CredibilityReportCritic()
    assessment = critic.assess(
        report,
        evidence,
        charter_b,
        assessment_id="wrong-charter",
    )

    assert assessment.verdict is CriticVerdict.FAIL
    binding = assessment.check("credibility_report_binding")
    assert binding is not None
    assert binding.outcome is CriticVerdict.FAIL
    assert "charter" in binding.detail.lower()


def test_missing_battery_uncertainty_becomes_explicit_unknown_at_decision_boundary() -> None:
    run = run_battery_case(example_battery_payload())
    report = run.report
    assert "final_temperature" in report.values
    assert "final_temperature" not in report.uncertainty

    charter = _charter(campaign_id="battery-campaign", decision_id="battery-decision")
    evidence = evidence_from_credibility_report(
        report,
        evidence_id="battery-final-temperature",
        value_name="final_temperature",
        domain_pack_ref="battery",
        charter=charter,
        decision_id="battery-decision",
    )

    assert evidence.uncertainty.discrepancy.kind is DiscrepancyKind.UNKNOWN
    budget = budget_from_declaration(evidence.belief_key, evidence.uncertainty)
    assert budget.entry(UncertaintyChannel.NUMERICAL).state.value == "unknown"

    _assessment, decision = _decision(
        report,
        evidence,
        charter,
        extra_uncertainty=(UncertaintyChannel.NUMERICAL,),
    )
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
    numerical = [
        result
        for result in decision.obligation_results
        if result.obligation_id == "uncertainty:numerical"
    ]
    assert numerical and numerical[0].satisfied is False


def test_quantified_uncertainty_without_source_is_refused_not_guessed() -> None:
    report = _electrothermal_report()
    name = next(iter(report.values))
    unit = str(report.values[name].units)
    unattributed = Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(0.01, unit),
        method="fixture",
        # source_kind intentionally omitted
    )
    report = dataclasses.replace(report, uncertainty={name: unattributed})

    with pytest.raises(DecisionEvidenceBridgeError, match="declares no source_kind"):
        _evidence(report, _charter(), value_name=name)


def test_bridge_does_not_promote_insufficient_report_to_valid() -> None:
    report = run_battery_case(example_battery_payload()).report
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    charter = _charter(campaign_id="battery-gap", decision_id="d-gap")
    evidence = evidence_from_credibility_report(
        report,
        evidence_id="battery-gap-evidence",
        value_name="final_temperature",
        domain_pack_ref="battery",
        charter=charter,
        decision_id="d-gap",
    )

    assessment, decision = _decision(report, evidence, charter)

    assert assessment.verdict is CriticVerdict.INCONCLUSIVE
    assert decision.verdict is AssuranceVerdict.INCONCLUSIVE
