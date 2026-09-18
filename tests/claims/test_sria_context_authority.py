"""Phase 1 -- context authority lives in SRIA, not only in the claim layer.

The claim layer refused foreign-context evidence before the Arbiter saw it, but the Arbiter itself would
decide VALID over evidence carrying another decision's ``context_ref`` (audit N2). These cases go straight
to the Arbiter, bypassing ``claims.context``, so they test the authority's own invariant.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from claims_support import t3_claim
from engcore.claims import (
    ClaimTarget,
    DecisionBinding,
    assemble_evidence,
    assess_claim,
    compile_claim,
    execute_plan,
    plan_experiment,
)
from engcore.mcp.capabilities import production_registry
from engcore.mcp.sria_bridge import CredibilityReportCritic
from engcore.scientific.units.quantity import Quantity
from engcore.sria.assurance import (
    Arbiter,
    CriticClass,
    ObligationKind,
    charter_context_ref,
    obligations_from_charter,
    parse_charter_context_ref,
    trusting_authority,
)
from engcore.sria.charter import CampaignCharter, ConfidenceRequirement, TerminalDecision


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _planned(made, registry):
    compiled = compile_claim(made, registry)
    plan = plan_experiment(compiled, registry)
    execution = execute_plan(plan, registry, dict(made.supplied_inputs))
    evidence = assemble_evidence(plan, made, execution.report).evidence
    return plan, execution.report, evidence


@pytest.fixture(scope="module")
def run_a(registry):
    return _planned(t3_claim(), registry)


def _decide(report, evidence, obligations, *, decision_id="p1"):
    critic = CredibilityReportCritic()
    arbiter = Arbiter(trusting_authority("p1", critics=(critic,), policies=(obligations,)), critics=(critic,))
    assessment = arbiter.run_critic(
        critic.critic_id, report, subject=evidence, assessment_id=f"a:{decision_id}",
        mandatory_checks=("validation_level:benchmark_validated",),
    )
    return arbiter.decide(decision_id=decision_id, evidence=evidence, assessments=(assessment,), obligations=obligations)


def _relabel(evidence, context_ref):
    """The same measurement, value and QOI, relabelled for another context (identity re-derived)."""
    return replace(evidence, context_ref=context_ref, content_hash="")


def _bound(plan, *, decision_id=None):
    return obligations_from_charter(
        plan.charter, required_critics=(CriticClass.PROCESS,),
        context_decision_id=plan.decision_id if decision_id is None else decision_id,
    )


# ---------------------------------------------------------------------------
# The four required cases
# ---------------------------------------------------------------------------


def test_correct_context_preserves_the_existing_valid_decision(run_a) -> None:
    plan, report, evidence = run_a
    unbound = obligations_from_charter(plan.charter, required_critics=(CriticClass.PROCESS,))
    decision = _decide(report, evidence, unbound)
    assert decision.verdict.value == "valid"
    assert not any(r.obligation_id.startswith("context:") for r in decision.obligation_results)
    bound = _decide(report, evidence, _bound(plan))
    assert bound.verdict.value == "valid"
    (ctx,) = [r for r in bound.obligation_results if r.obligation_id.startswith("context:")]
    assert ctx.satisfied


def test_same_qoi_same_value_wrong_charter_cannot_become_valid(registry, run_a) -> None:
    plan_a, report_a, evidence_a = run_a
    plan_b, _, _ = _planned(t3_claim(decision=DecisionBinding("d-2", "Another use.")), registry)
    for obligations in (
        obligations_from_charter(plan_b.charter, required_critics=(CriticClass.PROCESS,)),
        _bound(plan_b),
    ):
        decision = _decide(report_a, evidence_a, obligations)
        assert decision.verdict.value == "inconclusive"
        assert any("charter" in r for r in decision.reasons)


def test_same_evidence_wrong_decision_id_cannot_become_valid(run_a) -> None:
    plan, report, evidence = run_a
    forged = _relabel(evidence, charter_context_ref(plan.charter.digest, "some-other-decision"))
    assert forged.claim_payload == evidence.claim_payload and forged.record_hash != evidence.record_hash
    decision = _decide(report, forged, _bound(plan))
    assert decision.verdict.value == "inconclusive"
    assert any(r.obligation_id.startswith("context:") and not r.satisfied for r in decision.obligation_results)


def test_evidence_for_one_terminal_decision_cannot_serve_another_of_the_same_charter(run_a) -> None:
    plan, report, evidence = run_a
    charter = CampaignCharter(
        campaign_id="two-decisions",
        terminal_decisions=(TerminalDecision("d-1", "first"), TerminalDecision("d-2", "second")),
        confidence_requirements=(ConfidenceRequirement(requirement_id="lvl", required_levels=plan.charter.confidence_requirements[0].required_levels, description="x"),),
    )
    for_d1 = _relabel(evidence, charter_context_ref(charter.digest, "d-1"))
    ok = _decide(report, for_d1, obligations_from_charter(charter, required_critics=(CriticClass.PROCESS,), context_decision_id="d-1"))
    assert ok.verdict.value == "valid"
    wrong = _decide(report, for_d1, obligations_from_charter(charter, required_critics=(CriticClass.PROCESS,), context_decision_id="d-2"))
    assert wrong.verdict.value == "inconclusive"


def test_same_evidence_changed_context_cannot_become_valid(registry, run_a) -> None:
    """A changed claim (another target) is another charter; the old evidence does not carry over."""
    plan_a, report_a, evidence_a = run_a
    plan_c, _, _ = _planned(t3_claim(target=ClaimTarget(value=Quantity(309.8, "kelvin"))), registry)
    assert plan_c.charter.digest != plan_a.charter.digest
    assert _decide(report_a, evidence_a, _bound(plan_c)).verdict.value == "inconclusive"


# ---------------------------------------------------------------------------
# Fail-closed edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["charter:", "charter:abc", "charter:#decision:d-1", "charter:abc#decision:", "charter:a#decision:b#decision:c"])
def test_a_malformed_claim_to_a_charter_is_never_read_as_no_claim(run_a, ref) -> None:
    plan, report, evidence = run_a
    assert parse_charter_context_ref(ref) == ("", "")
    forged = _relabel(evidence, ref)
    for obligations in (
        obligations_from_charter(plan.charter, required_critics=(CriticClass.PROCESS,)),
        replace(obligations_from_charter(plan.charter, required_critics=(CriticClass.PROCESS,)), charter_digest=""),
    ):
        assert _decide(report, forged, obligations).verdict.value != "valid"


def test_charter_bound_evidence_under_a_policy_with_no_charter_is_not_valid(run_a) -> None:
    plan, report, evidence = run_a
    loose = replace(obligations_from_charter(plan.charter, required_critics=(CriticClass.PROCESS,)), charter_digest="")
    assert _decide(report, evidence, loose).verdict.value == "inconclusive"


def test_an_empty_context_cannot_satisfy_a_required_context(run_a) -> None:
    plan, report, evidence = run_a
    assert _decide(report, _relabel(evidence, ""), _bound(plan)).verdict.value == "inconclusive"


def test_a_required_context_naming_another_charter_is_unsatisfiable(run_a) -> None:
    plan, report, evidence = run_a
    bound = _bound(plan)
    (ob,) = bound.of_kind(ObligationKind.REQUIRED_CONTEXT)
    forged_set = replace(bound, obligations=tuple(
        replace(o, target=charter_context_ref("f" * 64, plan.decision_id)) if o is ob else o for o in bound.obligations
    ))
    other = _relabel(evidence, charter_context_ref("f" * 64, plan.decision_id))
    # The evidence names charter f..f and so does the obligation, but the POLICY is plan's charter.
    assert _decide(report, other, forged_set).verdict.value == "inconclusive"


def test_a_policy_cannot_be_bound_to_a_decision_its_charter_never_made(run_a) -> None:
    plan, _, _ = run_a
    with pytest.raises(ValueError, match="terminal decision"):
        obligations_from_charter(plan.charter, context_decision_id="not-declared")


def test_a_wrong_context_is_never_invalid(registry, run_a) -> None:
    """INVALID requires evidence-invalidating findings; a mislabelled context is not a refutation."""
    plan_a, report_a, evidence_a = run_a
    plan_b, _, _ = _planned(t3_claim(decision=DecisionBinding("d-9", "x")), registry)
    assert _decide(report_a, evidence_a, _bound(plan_b)).verdict.value == "inconclusive"


def test_a_decision_with_no_evidence_cannot_satisfy_a_required_context(run_a) -> None:
    plan, report, evidence = run_a
    critic = CredibilityReportCritic()
    obligations = _bound(plan)
    arbiter = Arbiter(trusting_authority("p1", critics=(critic,), policies=(obligations,)), critics=(critic,))
    assessment = arbiter.run_critic(critic.critic_id, report, subject=evidence, assessment_id="x",
                                    mandatory_checks=("validation_level:benchmark_validated",))
    decision = arbiter.decide(decision_id="noev", subject_ref=evidence.record_hash, assessments=(assessment,),
                              obligations=obligations)
    assert decision.verdict.value != "valid"


def test_the_claim_path_binds_its_policy_to_its_decision(registry) -> None:
    result = assess_claim(t3_claim(), registry)
    assert result.verdict.value == "supported"
    ids = [o["obligation_id"] for o in result.to_dict()["assurance"]["obligations"]]
    assert "context:d-1" in ids


def test_context_ref_helpers_round_trip() -> None:
    ref = charter_context_ref("ab" * 32, "d-1")
    assert parse_charter_context_ref(ref) == ("ab" * 32, "d-1")
    assert parse_charter_context_ref("context:free-text") is None
    with pytest.raises(ValueError):
        charter_context_ref("", "d")
