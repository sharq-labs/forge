"""End-to-end NAFEMS T3 execution -> external validation -> SRIA decision."""

from __future__ import annotations

import pytest

from engcore.domains.thermal_models.nafems_t3 import (
    MODEL,
    NAFEMST3Numerics,
    QOI,
    solve_nafems_t3,
)
from engcore.mcp import CredibilityVerdict
from engcore.mcp.nafems_t3 import run_nafems_t3_credibility
from engcore.mcp.sria_bridge import CredibilityReportCritic, evidence_from_credibility_report
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.results.validation import ValidationLevel, ValidationOutcome
from engcore.sria import (
    CampaignCharter,
    ConfidenceRequirement,
    DiscrepancyKind,
    ModelDiscrepancy,
    TerminalDecision,
)
from engcore.sria.assurance import obligations_from_charter, trusting_authority
from engcore.sria.assurance.arbiter import Arbiter


def test_default_t3_execution_reproduces_the_external_target() -> None:
    result = solve_nafems_t3(run_id="t3-target")
    temperature = result.value(QOI)

    assert temperature.magnitude_in("degC") == pytest.approx(36.6, abs=0.05)
    assert result.convergence.value == "converged"
    assert result.validity[MODEL.model_id].status is ValidityStatus.IN_DOMAIN
    assert result.validation.claims(ValidationLevel.BENCHMARK_VALIDATED)

    oracle = next(
        check
        for check in result.validation.checks
        if check.name == "nafems_t3_external_benchmark"
    )
    assert oracle.outcome is ValidationOutcome.PASS
    assert oracle.establishes is ValidationLevel.BENCHMARK_VALIDATED


def test_t3_refinement_gate_is_separate_from_the_external_level() -> None:
    result = solve_nafems_t3(run_id="t3-refinement")
    refinement = next(
        check
        for check in result.validation.checks
        if check.name == "nafems_t3_refinement_sensitivity"
    )

    assert refinement.outcome is ValidationOutcome.PASS
    assert refinement.establishes is None
    assert refinement.residual is not None
    assert refinement.tolerance is not None
    assert refinement.residual <= refinement.tolerance


def _boundary_check(result):
    return next(c for c in result.validation.checks if c.name == "nafems_t3_boundary_conditions_held")


def test_t3_boundary_check_holds_on_the_real_solve() -> None:
    check = _boundary_check(solve_nafems_t3(run_id="t3-boundary"))
    assert check.outcome is ValidationOutcome.PASS and check.establishes is None
    assert check.residual is not None and check.residual <= check.tolerance


def test_t3_boundary_check_fails_when_the_interior_solve_did_not_see_the_boundary(monkeypatch) -> None:
    """The check used to compare the stored boundary node with the value written into it, so no solve could fail it.

    Here the interior solve is handed a right-hand side whose wall-adjacent entry is off by 0.1 %: the boundary
    node itself is still written exactly, so the old read-back would PASS this run.
    """
    import engcore.domains.thermal_models.nafems_t3 as t3

    real = t3.solve_banded

    def boundary_blind(l_and_u, banded, rhs):
        rhs = rhs.copy()
        rhs[-1] *= 0.999
        return real(l_and_u, banded, rhs)

    monkeypatch.setattr(t3, "solve_banded", boundary_blind)
    result = solve_nafems_t3(run_id="t3-boundary-blind")
    check = _boundary_check(result)
    assert check.outcome is ValidationOutcome.FAIL
    assert check.residual > 1e3 * check.tolerance
    assert result.provenance.metadata["right_boundary_final_excursion_k"] == pytest.approx(
        t3._right_excursion(t3._magnitude("end_time", "second")), abs=0.0
    )


def test_t3_boundary_check_sees_a_defect_confined_to_an_early_step(monkeypatch) -> None:
    """Review finding F6: a check on the last step alone passes a run whose boundary went wrong earlier."""
    import engcore.domains.thermal_models.nafems_t3 as t3

    real, calls = t3.solve_banded, {"n": 0}

    def blind_once(l_and_u, banded, rhs):
        calls["n"] += 1
        if calls["n"] == 3:  # the third step of the reported solve only
            rhs = rhs.copy()
            rhs[-1] *= 0.999
        return real(l_and_u, banded, rhs)

    monkeypatch.setattr(t3, "solve_banded", blind_once)
    check = _boundary_check(solve_nafems_t3(run_id="t3-boundary-blind-once"))
    assert check.outcome is ValidationOutcome.FAIL
    assert check.residual > 1e3 * check.tolerance


def test_t3_numerics_keep_the_probe_on_a_grid_node() -> None:
    with pytest.raises(ValueError, match="divisible by 5"):
        NAFEMST3Numerics(n_cells=82, n_steps=320)

    with pytest.raises(ValueError, match="at least 20"):
        NAFEMST3Numerics(n_cells=10, n_steps=320)


def test_t3_credibility_requires_and_attains_benchmark_validation() -> None:
    report = run_nafems_t3_credibility(run_id="t3-credibility")

    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert report.evidence_basis == "VALIDATED"
    assert ValidationLevel.BENCHMARK_VALIDATED in report.attained_levels
    assert report.required_levels == (ValidationLevel.BENCHMARK_VALIDATED,)


def test_t3_benchmark_level_reaches_sria_arbiter() -> None:
    report = run_nafems_t3_credibility(run_id="t3-decision")

    charter = CampaignCharter(
        campaign_id="nafems-t3-campaign",
        terminal_decisions=(
            TerminalDecision(
                decision_id="d1",
                statement="Accept this benchmark reproduction for the T3 verification use.",
            ),
        ),
        confidence_requirements=(
            ConfidenceRequirement(
                requirement_id="r1",
                required_levels=(ValidationLevel.BENCHMARK_VALIDATED,),
                description="T3 verification use requires an external benchmark level.",
            ),
        ),
    )
    obligations = obligations_from_charter(charter)
    critic = CredibilityReportCritic()
    authority = trusting_authority(
        "nafems-t3-authority",
        critics=(critic,),
        policies=(obligations,),
    )
    arbiter = Arbiter(authority, critics=(critic,))

    evidence = evidence_from_credibility_report(
        report,
        quantity_name=QOI,
        evidence_id="nafems-t3-evidence",
        domain_pack_ref="thermal:nafems-t3",
        context_ref=f"charter:{charter.digest}#decision:d1",
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.CONSTRAINED_PRIOR,
            reference="NAFEMS P18.T3 repository-pinned benchmark evidence",
            rationale=(
                "benchmark-only decision-path declaration; this does not "
                "assert zero model-form discrepancy or quantified UQ"
            ),
        ),
    )

    mandatory = tuple(
        obligation.target
        for obligation in obligations.obligations
        if obligation.target.startswith("validation_level:")
    )
    assessment = arbiter.run_critic(
        critic.critic_id,
        report,
        subject=evidence,
        assessment_id="nafems-t3-levels",
        mandatory_checks=mandatory,
    )
    decision = arbiter.decide(
        decision_id="nafems-t3-decision",
        evidence=evidence,
        assessments=(assessment,),
        obligations=obligations,
    )

    benchmark_result = next(
        item
        for item in decision.obligation_results
        if item.obligation_id.startswith("confidence:")
    )
    assert benchmark_result.satisfied is True
    assert not decision.refused_assessments
