"""PR #50 stacked follow-up: honest model-form discrepancy at the MCP -> SRIA bridge."""

from __future__ import annotations

from engcore.mcp import example_electrothermal_payload, run_electrothermal_case
from engcore.mcp.sria_bridge import evidence_from_credibility_report
from engcore.sria import DiscrepancyKind, ModelDiscrepancy
from engcore.sria.assurance import budget_from_declaration, model_discrepancy_check
from engcore.sria.assurance.assessment import CriticVerdict


def _report():
    return run_electrothermal_case(example_electrothermal_payload()).reports[0]


def test_bridge_defaults_missing_model_discrepancy_to_unknown_not_zero() -> None:
    report = _report()
    name = next(iter(report.values))

    evidence = evidence_from_credibility_report(
        report,
        quantity_name=name,
        evidence_id="unknown-discrepancy",
        domain_pack_ref="electrothermal",
        context_ref="charter:test#decision:d1",
    )

    assert evidence.uncertainty.discrepancy.kind is DiscrepancyKind.UNKNOWN


def test_unknown_model_discrepancy_is_assurance_blocking_not_a_pass() -> None:
    report = _report()
    name = next(iter(report.values))
    evidence = evidence_from_credibility_report(
        report,
        quantity_name=name,
        evidence_id="unknown-discrepancy-budget",
        domain_pack_ref="electrothermal",
        context_ref="charter:test#decision:d1",
    )

    budget = budget_from_declaration(evidence.belief_key, evidence.uncertainty)
    check, findings = model_discrepancy_check(budget, mandatory=True)

    assert check.outcome is CriticVerdict.INCONCLUSIVE
    assert {finding.code for finding in findings} == {
        "domain.model_discrepancy_unknown"
    }


def test_explicit_zero_discrepancy_remains_an_explicit_separate_claim() -> None:
    report = _report()
    name = next(iter(report.values))
    evidence = evidence_from_credibility_report(
        report,
        quantity_name=name,
        evidence_id="zero-discrepancy",
        domain_pack_ref="electrothermal",
        context_ref="charter:test#decision:d1",
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="fixture declaration only",
        ),
    )

    assert evidence.uncertainty.discrepancy.kind is DiscrepancyKind.ZERO_DECLARED
