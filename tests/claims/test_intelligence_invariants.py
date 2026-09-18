"""The Scientific Intelligence Core's fourteen load-bearing invariants, each tied to the tests that hold it.

Same discipline as ``test_claims_invariants.py`` (whose twelve remain): an invariant is held by at least two
named tests that must exist, and every guard added by Phases 1-10 is also a mutant in
``test_claims_mutations.py`` that one of these properties kills.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

TESTS = pathlib.Path(__file__).resolve().parents[1]

INVARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    "1. UNKNOWN can never improve an answer": (
        ("claims/test_phase2_production_uq.py", "test_every_rule_failure_is_unknown_never_zero"),
        ("claims/test_phase2_production_uq.py", "test_a_refused_level_makes_the_channel_unknown"),
        ("claims/test_phase7_8_sensitivity_challenge.py", "test_a_domain_end_is_unknown_beyond_not_holds"),
    ),
    "2. removing evidence can never increase assurance": (
        ("claims/test_phase2_production_uq.py", "test_removing_uq_evidence_cannot_improve_the_verdict"),
        ("claims/test_phase9_10_impact_bundle.py", "test_an_edit_with_a_recomputed_digest_is_still_refused"),
        ("test_verdict_monotonicity.py", "test_removing_the_only_level_bearing_check_never_strengthens"),
    ),
    "3. caller assertions are not evidence": (
        ("claims/test_phase4_external_evidence.py", "test_an_unpinned_measurement_is_weak_however_good_it_looks"),
        ("claims/test_phase2_production_uq.py", "test_input_distributions_are_declarations_bound_to_stated_values"),
        ("claims/test_phase3_policy.py", "test_consequence_is_stated_never_inferred"),
    ),
    "4. planner output is not evidence": (
        ("claims/test_phase5_6_gaps_and_next.py", "test_recommendations_address_real_gaps_and_promise_nothing"),
        ("claims/test_phase5_6_gaps_and_next.py", "test_refining_as_recommended_narrows_the_band_but_is_not_promised_to_decide"),
        ("claims/test_phase7_8_sensitivity_challenge.py", "test_a_challenge_never_changes_the_verdict"),
    ),
    "5. model applicability precedes evidence-bearing execution": (
        ("claims/test_phase2_production_uq.py", "test_a_distribution_that_leaves_the_validated_domain_is_unknown_not_truncated"),
        ("claims/test_phase4_external_evidence.py", "test_a_pinned_measurement_falls_short_for_exactly_the_stated_reason"),
        ("claims/test_claims_selection.py", "test_an_outside_model_is_never_evidence_bearing_even_when_it_is_the_only_one"),
    ),
    "6. verification does not become validation": (
        ("claims/test_phase4_external_evidence.py", "test_offered_external_evidence_never_changes_the_verdict_or_the_levels"),
        ("claims/test_phase3_policy.py", "test_policy_findings_name_their_authoritative_record"),
        ("claims/test_claims_assessment.py", "test_verification_cannot_satisfy_a_validation_requirement"),
    ),
    "7. solver agreement does not prove real-world correctness": (
        ("claims/test_phase2_production_uq.py", "test_numerical_uq_cannot_satisfy_model_form"),
        ("claims/test_claims_routes.py", "test_production_routes_are_classified_without_trusting_their_declarations"),
    ),
    "8. missing uncertainty never becomes zero": (
        ("claims/test_phase2_production_uq.py", "test_every_rule_failure_is_unknown_never_zero"),
        ("claims/test_phase2_production_uq.py", "test_combined_uncertainty_cannot_masquerade_as_a_single_channel"),
        ("claims/test_phase4_external_evidence.py", "test_a_benchmark_is_admissible_only_when_trusted_and_exactly_applicable"),
    ),
    "9. missing discrepancy never becomes zero": (
        ("claims/test_phase5_6_gaps_and_next.py", "test_each_insufficiency_is_classified_by_its_cause"),
        ("claims/test_claims_contract.py", "test_an_explicitly_unknown_discrepancy_is_accepted_and_never_becomes_zero"),
        ("claims/test_nl_adapter.py", "test_a_proposal_cannot_declare_discrepancy_zero"),
    ),
    "10. missing boundary conditions are never silently defaulted": (
        ("claims/test_nl_adapter.py", "test_an_invented_value_is_moved_to_missing_never_defaulted"),
        ("claims/test_phase5_6_gaps_and_next.py", "test_supplying_the_recommended_input_closes_the_gap"),
        ("claims/test_claims_compiler.py", "test_a_required_input_the_caller_says_is_unknown_is_not_defaulted"),
    ),
    "11. contradiction requires admissible evidence": (
        ("claims/test_phase7_8_sensitivity_challenge.py", "test_nothing_weak_or_undeclared_can_weaken_a_claim"),
        ("claims/test_phase7_8_sensitivity_challenge.py", "test_admissible_external_evidence_that_disagrees_weakens_and_weak_evidence_cannot"),
        ("claims/test_claims_assessment.py", "test_a_model_outside_its_domain_never_contradicts_the_claim"),
    ),
    "12. evidence stays bound to its exact context and decision": (
        ("claims/test_sria_context_authority.py", "test_same_qoi_same_value_wrong_charter_cannot_become_valid"),
        ("claims/test_sria_context_authority.py", "test_same_evidence_wrong_decision_id_cannot_become_valid"),
        ("claims/test_sria_context_authority.py", "test_same_evidence_changed_context_cannot_become_valid"),
        ("claims/test_phase3_policy.py", "test_changing_the_policy_changes_claim_identity_and_the_charter"),
    ),
    "13. higher risk never requires less evidence within a policy family": (
        ("claims/test_phase3_policy.py", "test_more_risk_never_requires_less_evidence_within_a_profile"),
        ("claims/test_phase3_policy.py", "test_higher_risk_under_one_profile_never_yields_a_stronger_verdict"),
        ("claims/test_phase3_policy.py", "test_a_higher_risk_policy_that_demands_less_is_refused"),
    ),
    "14. a policy cannot grant scientific evidence": (
        ("claims/test_phase3_policy.py", "test_no_decision_context_ever_strengthens_a_verdict"),
        ("claims/test_phase3_policy.py", "test_a_policy_cannot_grant_what_the_run_lacks"),
        ("claims/test_phase3_policy.py", "test_the_effective_claim_only_ever_gains_requirements"),
    ),
}

#: Every Phase 1-10 guard that has a mutant, by mutant name in test_claims_mutations.MUTANTS.
GUARDED_BY_MUTANTS = (
    "arbiter_context_ignored",
    "unknown_numerical_filed_as_zero",
    "asymptotic_range_unchecked",
    "unusable_runs_dropped",
    "policy_not_applied",
    "policy_findings_ignored",
    "risk_monotonicity_unchecked",
    "unpinned_external_trusted",
    "bundle_rederivation_skipped",
    "guard_band_bypassed",
)


def _functions(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_bytes().decode("utf-8-sig"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


@pytest.mark.parametrize("invariant", sorted(INVARIANTS))
def test_every_invariant_is_held_by_tests_that_exist(invariant) -> None:
    held_by = INVARIANTS[invariant]
    assert len(held_by) >= 2
    for relative, name in held_by:
        path = TESTS / relative
        assert path.exists(), f"{invariant!r}: {relative} does not exist"
        assert name in _functions(path), f"{invariant!r}: {relative} has no test {name}"


def test_the_list_is_the_fourteen_the_session_promised() -> None:
    assert sorted(int(k.split(".")[0]) for k in INVARIANTS) == list(range(1, 15))


def test_every_new_guard_has_a_mutant_that_is_run() -> None:
    from test_claims_mutations import MUTANTS

    names = {m[0] for m in MUTANTS}
    assert set(GUARDED_BY_MUTANTS) <= names, sorted(set(GUARDED_BY_MUTANTS) - names)
