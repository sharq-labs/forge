"""The claim layer's integrity invariants, each tied to the tests that hold it.

A list of principles in a document is a claim nobody checks. This file is the
list, executable: every invariant names at least two tests, and each named test
must exist in the file it is attributed to. Deleting or renaming a test that
holds an invariant fails here, pointing at the invariant it left unguarded.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent

#: invariant -> ((file relative to tests/, test function name), ...)
INVARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    "1. unknown never improves a claim": (
        ("claims/test_claims_compiler.py", "test_removing_any_input_never_makes_a_claim_more_ready"),
        ("claims/test_claims_uncertainty.py", "test_losing_a_quantified_record_never_firms_up_the_answer"),
        ("claims/test_claims_assessment.py", "test_removing_a_discrepancy_declaration_never_firms_up_the_answer"),
        ("claims/test_claims_verdict.py", "test_without_a_demanded_channel_the_comparison_is_a_point_check_and_ignores_known_uncertainty"),
    ),
    "2. adding missing evidence never makes a result worse unless it contradicts": (
        ("claims/test_claims_compiler.py", "test_a_claim_that_is_not_ready_never_becomes_ready_by_losing_inputs"),
        ("claims/test_claims_uncertainty.py", "test_a_quantified_attributed_channel_can_support_a_claim_that_demands_it"),
        ("claims/test_claims_assessment.py", "test_asking_for_more_evidence_never_firms_up_the_answer"),
    ),
    "3. caller assertions are not evidence": (
        ("claims/test_claims_contract.py", "test_constructed_statement_prose_is_kept_for_the_record_but_not_parsed"),
        ("claims/test_claims_assessment.py", "test_a_demanded_discrepancy_needs_support_that_unknown_and_bare_zero_do_not_give"),
        ("claims/test_claims_compiler.py", "test_an_unknown_or_unsupported_zero_discrepancy_cannot_meet_a_discrepancy_demand"),
    ),
    "4. planner decisions are not evidence": (
        ("claims/test_claims_planning.py", "test_unattainable_evidence_and_uncertainty_work_are_planned_as_unavailable"),
        ("claims/test_claims_production_capabilities.py", "test_cross_solver_validation_is_not_declared_attainable_on_the_mcp_path"),
        ("claims/test_claims_routes.py", "test_production_routes_are_classified_without_trusting_their_declarations"),
    ),
    "5. natural-language interpretation is not validation": (
        ("claims/test_claims_compiler.py", "test_compilation_is_deterministic_and_reads_no_prose"),
        ("claims/test_claims_capabilities.py", "test_matching_reads_declared_identifiers_never_prose"),
        ("claims/test_claims_contract.py", "test_prose_ids_and_output_format_do_not_change_scientific_identity"),
    ),
    "6. two solvers agreeing does not validate the model against reality": (
        ("claims/test_claims_routes.py", "test_production_routes_are_classified_without_trusting_their_declarations"),
        ("claims/test_claims_routes.py", "test_the_prediction_agrees_with_the_consensus_on_every_pinned_pair"),
    ),
    "7. verification and validation remain distinct": (
        ("claims/test_claims_assessment.py", "test_verification_cannot_satisfy_a_validation_requirement"),
        ("claims/test_claims_assessment.py", "test_an_electrothermal_threshold_claim_is_supported_or_contradicted_by_its_bound"),
    ),
    "8. no missing uncertainty becomes zero": (
        ("claims/test_claims_assessment.py", "test_a_demanded_uncertainty_channel_that_is_unknown_leaves_the_claim_undecided"),
        ("claims/test_claims_uncertainty.py", "test_unknown_stays_unknown_and_is_shown_when_no_channel_is_demanded"),
        ("claims/test_claims_verdict.py", "test_an_unusable_channel_decides_nothing"),
        ("claims/test_claims_uncertainty.py", "test_an_unattributable_record_never_enters_a_channel_and_leaves_the_demand_unmet"),
    ),
    "9. no missing model discrepancy becomes zero": (
        ("claims/test_claims_contract.py", "test_an_explicitly_unknown_discrepancy_is_accepted_and_never_becomes_zero"),
        ("test_scientific_decision_readiness_sprint0.py", "test_sprint1_bridge_refuses_to_invent_model_discrepancy"),
        ("claims/test_claims_contract.py", "test_a_missing_field_is_refused_rather_than_defaulted"),
    ),
    "10. no missing operating condition is silently defaulted": (
        ("claims/test_claims_compiler.py", "test_a_required_input_the_caller_says_is_unknown_is_not_defaulted"),
        ("claims/test_claims_compiler.py", "test_a_missing_required_input_is_asked_for_with_its_declared_dimension"),
        ("claims/test_claims_capabilities.py", "test_the_case_builder_writes_exactly_what_was_stated"),
        ("claims/test_claims_planning.py", "test_numerics_are_part_of_what_is_run"),
    ),
    "11. applicability is checked before output is treated as evidence": (
        ("claims/test_claims_selection.py", "test_an_outside_model_is_never_evidence_bearing_even_when_it_is_the_only_one"),
        ("claims/test_claims_assessment.py", "test_a_model_outside_its_domain_never_contradicts_the_claim"),
        ("claims/test_claims_selection.py", "test_a_model_that_cannot_evaluate_its_validity_is_rejected"),
        ("claims/test_claims_selection.py", "test_executability_alone_selects_nothing"),
    ),
    "12. every terminal assessment is traceable": (
        ("claims/test_claims_assessment.py", "test_an_assessed_record_answers_every_question_a_reader_asks"),
        ("claims/test_claims_assessment.py", "test_every_explanation_item_points_at_a_value_the_record_holds"),
        ("claims/test_claims_readback.py", "test_an_edited_record_is_refused"),
        ("claims/test_claims_readback.py", "test_an_untouched_record_reads_back_to_the_same_answer"),
    ),
}


def _functions(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_bytes().decode("utf-8-sig"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


@pytest.mark.parametrize("invariant", sorted(INVARIANTS))
def test_every_invariant_is_held_by_tests_that_exist(invariant) -> None:
    held_by = INVARIANTS[invariant]
    assert len(held_by) >= 2, f"{invariant!r} is held by fewer than two tests"
    for relative, name in held_by:
        path = TESTS / relative
        assert path.exists(), f"{invariant!r}: {relative} does not exist"
        assert name in _functions(path), f"{invariant!r}: {relative} has no test {name}"


def test_the_list_is_the_twelve_the_layer_promises() -> None:
    assert [int(key.split(".")[0]) for key in sorted(INVARIANTS, key=lambda k: int(k.split(".")[0]))] == list(range(1, 13))
