"""F1 (hostile review, CRITICAL): a language model may not author the criteria a claim is judged by.

The reproduced defect: the user wrote "305 K ± 0.5 K", the model's proposal said
309.75 K, the adapter grounded the inputs and nothing else, and the claim was
SUPPORTED against the model's number. Every test here offers one AI-authored
criterion and requires the adapter to fail closed: no compiled claim, nothing
executable, the model's value returned as advisory only.
"""

from __future__ import annotations

import copy

import pytest

from claims_support import et_claim, t3_claim
from engcore.claims import assess_claim
from engcore.claims.adapters import grounding, nl
from engcore.claims.adapters.grounding import (
    ADAPTER_GROUNDED_FIELDS,
    FIELD_RULES,
    CriterionProvenance,
    operators_stated,
)
from engcore.claims.adapters.nl import UNGROUNDED, compile_natural_language
from engcore.claims.contract import SCIENTIFIC_FIELDS
from engcore.mcp.capabilities import production_registry
from engcore.product.runtime import prepare_simulation, run_proposed_simulation
from engcore.scientific.ir.constraints import ConstraintOperator
from nl_support import Prose, state_claim, state_inputs


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _faithful(made):
    payload = made.to_dict()
    prose = state_claim(payload)
    return prose, copy.deepcopy(payload)


def _assert_fails_closed(result, field: str) -> None:
    assert result.status == UNGROUNDED, result.findings
    assert result.compiled is None
    assert field in result.advisory
    assert any(p.field == field and p.provenance is CriterionProvenance.AI_PROPOSED for p in result.provenance)


# ---------------------------------------------------------------------------
# The positive control: a proposal the text fully states compiles normally.
# ---------------------------------------------------------------------------


def test_a_fully_grounded_proposal_compiles_and_records_why_each_field_holds_its_value(registry) -> None:
    prose, proposal = _faithful(t3_claim())
    result = compile_natural_language(prose.text, proposal, prose.spans, registry)
    assert result.status == "ready", result.findings
    assert result.advisory == {}
    by_field = {p.field: p.provenance for p in result.provenance}
    assert set(by_field) == set(SCIENTIFIC_FIELDS)
    assert all(p.admissible for p in result.provenance)
    assert by_field["target"] is CriterionProvenance.SOURCE_GROUNDED
    assert by_field["kind"] is CriterionProvenance.COMPUTED_FROM_GROUNDED
    assert by_field["discrepancy"] is CriterionProvenance.LEAST_AUTHORITY
    # The record keeps the user's words, not the model's paraphrase of them.
    assert result.compiled.claim.statement == prose.text.strip()


# ---------------------------------------------------------------------------
# The reproduced CRITICAL: 305 K stated, 309.75 K proposed.
# ---------------------------------------------------------------------------


def _f1_case():
    made = t3_claim()
    payload = made.to_dict()
    prose = state_inputs(Prose(), payload)
    prose.say(
        "The ", ("claim.qoi", "temperature at probe"), " must be ", ("claim.target", "305 K"), " ",
        ("claim.operator", "±"), " ", ("claim.tolerance", "0.5 K"), ".",
    )
    prose.say(("claim.evidence", "The decision requires benchmark validated evidence"), ".")
    prose.say(("claim.uncertainty", "A point comparison is acceptable"), ".")
    prose.say("It is for this decision: ", ("claim.decision", payload["decision"]["statement"]))
    return prose, copy.deepcopy(payload)  # the proposal keeps 309.75 K: the model's number


def test_f1_the_model_changing_305_k_to_309_75_k_cannot_compile(registry) -> None:
    prose, proposal = _f1_case()
    assert proposal["target"]["value"]["magnitude"] == 309.75
    result = compile_natural_language(prose.text, proposal, prose.spans, registry)
    _assert_fails_closed(result, "target")
    assert result.advisory["target"]["value"]["magnitude"] == 309.75


def test_f1_the_product_flow_never_runs_or_assesses_the_models_target(registry) -> None:
    prose, proposal = _f1_case()
    run = run_proposed_simulation(prose.text, proposal, prose.spans, registry)
    assert run["record"] is None and run["view"] is None
    assert run["preparation"]["status"] == UNGROUNDED and run["preparation"]["ready"] is False
    assert run["preparation"]["compilation"] is None


def test_f1_the_same_text_with_the_users_own_target_compiles(registry) -> None:
    prose, proposal = _f1_case()
    proposal["target"]["value"]["magnitude"] = 305.0
    result = compile_natural_language(prose.text, proposal, prose.spans, registry)
    assert result.status == "ready", result.findings
    record = assess_claim(result.compiled.claim, registry).to_dict()
    # Whatever the verdict is, it is a verdict about 305 K, the bound the user wrote.
    assert record["claim"]["target"]["value"]["magnitude"] == 305.0


# ---------------------------------------------------------------------------
# Every way a model could author a criterion.
# ---------------------------------------------------------------------------


def test_the_model_inventing_a_target_the_text_never_states_fails_closed(registry) -> None:
    prose, proposal = _faithful(et_claim())
    start, end = prose.spans.pop("claim.target")
    result = compile_natural_language(prose.text, proposal, prose.spans, registry)
    _assert_fails_closed(result, "target")


def test_the_model_modifying_a_stated_target_fails_closed(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["target"]["value"]["magnitude"] = 360.0
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "target")


def test_the_model_changing_the_operator_fails_closed(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["operator"] = ">"
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "operator")


def test_the_model_loosening_the_tolerance_fails_closed(registry) -> None:
    prose, proposal = _faithful(t3_claim())
    proposal["tolerance"]["magnitude"] = 5.0
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "tolerance")


def test_the_model_weakening_the_required_evidence_fails_closed(registry) -> None:
    prose, proposal = _faithful(t3_claim())
    proposal["evidence"]["required_levels"] = ["dimensionally_valid"]
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "evidence")


def test_the_model_dropping_one_of_two_stated_levels_fails_closed_even_citing_a_trimmed_span(registry) -> None:
    payload = t3_claim().to_dict()
    payload["evidence"]["required_levels"] = ["analytically_verified", "benchmark_validated"]
    prose = state_claim(payload)
    proposal = copy.deepcopy(payload)
    proposal["evidence"]["required_levels"] = ["analytically_verified"]
    start, _ = prose.spans["claim.evidence"]
    sentence = prose.text[start:]
    prose.spans["claim.evidence"] = (start, start + sentence.index("analytically verified") + len("analytically verified"))
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "evidence")


def test_the_model_removing_a_stated_uncertainty_channel_fails_closed(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 2.0}
    prose = state_claim(payload)
    proposal = copy.deepcopy(payload)
    proposal["uncertainty"]["required_channels"] = []
    proposal["uncertainty"]["coverage_factor"] = None
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "uncertainty")


def test_the_model_waiving_uncertainty_the_text_never_waived_fails_closed(registry) -> None:
    prose, proposal = _faithful(et_claim())
    start, end = prose.spans["claim.uncertainty"]
    text = prose.text[:start] + "Uncertainty matters here" + prose.text[end:]
    shift = len("Uncertainty matters here") - (end - start)
    spans = {k: (s + shift, e + shift) if s > start else (s, e) for k, (s, e) in prose.spans.items()}
    spans["claim.uncertainty"] = (start, start + len("Uncertainty matters here"))
    _assert_fails_closed(compile_natural_language(text, proposal, spans, registry), "uncertainty")


def test_the_model_altering_the_coverage_factor_fails_closed(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 2.0}
    prose = state_claim(payload)
    proposal = copy.deepcopy(payload)
    proposal["uncertainty"]["coverage_factor"] = 1.0
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "uncertainty")


def test_the_model_supplying_a_known_benchmark_value_from_memory_fails_closed(registry) -> None:
    """The NAFEMS T3 reference is 309.75 K. A model that knows it may not substitute it for the user's bound."""
    prose, proposal = _f1_case()
    proposal["target"]["value"] = {**proposal["target"]["value"], "magnitude": 309.75, "units": "kelvin"}
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "target")


def test_a_number_that_grounds_an_input_cannot_also_ground_the_bound(registry) -> None:
    """The model cites an input's stated value as the target: one statement grounds one field."""
    prose, proposal = _faithful(et_claim())
    voltage_span = prose.spans["source_voltage"]
    prose.spans["claim.target"] = voltage_span
    voltage = proposal["known_inputs"]["source_voltage"]
    proposal["target"]["value"] = {"schema": proposal["target"]["value"]["schema"], **{k: voltage[k] for k in ("magnitude", "units")}}
    proposal["qoi"]["units"] = voltage["units"]
    result = compile_natural_language(prose.text, proposal, prose.spans, registry)
    assert result.status in (UNGROUNDED, "refused") and result.compiled is None


def test_a_target_stated_in_another_unit_is_grounded_by_conversion(registry) -> None:
    payload = et_claim().to_dict()
    prose = state_inputs(Prose(), payload)
    prose.say("The ", ("claim.qoi", "final temperature"), " must stay ", ("claim.operator", "below"), " ",
              ("claim.target", "80 degC"), ".")
    prose.say(("claim.evidence", "The decision requires analytically verified evidence"), ".")
    prose.say(("claim.uncertainty", "A point comparison is acceptable"), ".")
    prose.say("It is for this decision: ", ("claim.decision", payload["decision"]["statement"]))
    result = compile_natural_language(prose.text, copy.deepcopy(payload), prose.spans, registry)
    assert result.status == "ready", result.findings  # 353.15 K is 80 degC
    payload["target"]["value"]["magnitude"] = 353.0
    assert compile_natural_language(prose.text, payload, prose.spans, registry).status == UNGROUNDED


# ---------------------------------------------------------------------------
# Policy: the application, never the model, may bind a criterion.
# ---------------------------------------------------------------------------


def test_a_policy_bound_evidence_bar_replaces_what_the_text_does_not_state(registry) -> None:
    payload = t3_claim().to_dict()
    prose = state_claim(payload)
    del prose.spans["claim.evidence"]
    proposal = copy.deepcopy(payload)
    del proposal["evidence"]
    policy = {"evidence": payload["evidence"]}
    result = compile_natural_language(prose.text, proposal, prose.spans, registry, policy=policy)
    assert result.status == "ready", result.findings
    assert {p.field: p.provenance for p in result.provenance}["evidence"] is CriterionProvenance.POLICY_BOUND


def test_a_proposal_contradicting_the_policy_fails_closed(registry) -> None:
    payload = t3_claim().to_dict()
    prose = state_claim(payload)
    proposal = copy.deepcopy(payload)
    proposal["evidence"]["required_levels"] = ["dimensionally_valid"]
    result = compile_natural_language(prose.text, proposal, prose.spans, registry, policy={"evidence": payload["evidence"]})
    _assert_fails_closed(result, "evidence")


def test_a_decision_context_is_never_taken_from_the_model(registry) -> None:
    from engcore.claims.governance.policy import builtin_context

    payload = t3_claim().to_dict()
    prose = state_claim(payload)
    proposal = copy.deepcopy(payload)
    proposal["decision_context"] = builtin_context(
        "research_exploration", influence="low", consequence="low", owner="the model"
    ).to_dict()
    _assert_fails_closed(compile_natural_language(prose.text, proposal, prose.spans, registry), "decision_context")


def test_prepare_simulation_shows_the_advisory_value_and_never_compiles_it(registry) -> None:
    prose, proposal = _f1_case()
    view = prepare_simulation(prose.text, proposal, prose.spans, registry)
    assert view["ready"] is False and view["compilation"] is None
    assert view["advisory"]["target"]["value"]["magnitude"] == 309.75


# ---------------------------------------------------------------------------
# Construction: the rule is total over the claim's identity, and fail-closed for anything new.
# ---------------------------------------------------------------------------


def test_every_scientific_field_has_exactly_one_grounding_route() -> None:
    assert set(FIELD_RULES) | ADAPTER_GROUNDED_FIELDS == set(SCIENTIFIC_FIELDS)
    assert not set(FIELD_RULES) & ADAPTER_GROUNDED_FIELDS


def test_a_field_added_to_the_claim_without_a_grounding_rule_is_ai_proposed(registry, monkeypatch) -> None:
    prose, proposal = _faithful(t3_claim())
    monkeypatch.setattr(nl, "SCIENTIFIC_FIELDS", SCIENTIFIC_FIELDS + ("a_future_criterion",))
    proposal["a_future_criterion"] = {"anything": 1}
    result = compile_natural_language(prose.text, proposal, prose.spans, registry)
    _assert_fails_closed(result, "a_future_criterion")


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("must not exceed", {ConstraintOperator.LESS_EQUAL}),
        ("stays below", {ConstraintOperator.LESS_THAN}),
        ("at least", {ConstraintOperator.GREATER_EQUAL}),
        ("exceeds", {ConstraintOperator.GREATER_THAN}),
        ("within", {ConstraintOperator.EQUAL}),
        ("below, and above", {ConstraintOperator.LESS_THAN, ConstraintOperator.GREATER_THAN}),
        ("is", set()),
    ],
)
def test_operator_phrases_are_read_longest_first_and_never_twice(words, expected) -> None:
    assert operators_stated(words) == expected


def test_the_grounding_module_is_the_only_criterion_authority_in_the_adapter() -> None:
    """The adapter has no second path that compiles a proposal without consulting the rules."""
    import inspect

    source = inspect.getsource(nl.compile_natural_language)
    assert source.count("compile_claim(") == 1
    assert source.index("if advisory:") < source.index("compile_claim(proposal")
    assert grounding.ADMISSIBLE_PROVENANCE == frozenset(CriterionProvenance) - {CriterionProvenance.AI_PROPOSED}
