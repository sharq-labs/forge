"""F1 (hostile review, CRITICAL): a language model may not author the criteria a claim is judged by.

The reproduced defect: the user wrote "305 K ± 0.5 K", the model's proposal said
309.75 K, the adapter grounded the inputs and nothing else, and the claim was
SUPPORTED against the model's number. Every test here offers one AI-authored
criterion and requires the adapter to fail closed: no compiled claim, nothing
executable, the model's value returned as advisory only.

The second half is the independent re-review of the first fix (exploits F1-A
to F1-J): a cited span that merely CONTAINS a matching token is not grounding.
The comparison is read from one sentence by the adapter itself, numbers are
read only when written plainly, and an input is read only after its own name.
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
    TokenLedger,
    Ungrounded,
    ground_input,
    operators_stated,
    stated_numbers,
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
    return state_claim(payload), copy.deepcopy(payload)


def _compile(prose, proposal, registry, **extra_policy):
    return compile_natural_language(prose.text, proposal, prose.spans, registry, policy={**prose.policy, **extra_policy})


def _assert_fails_closed(result, field: str) -> None:
    assert result.status == UNGROUNDED, (result.status, result.findings)
    assert result.compiled is None
    assert field in result.advisory, (field, result.findings)
    assert any(p.field == field and p.provenance is CriterionProvenance.AI_PROPOSED for p in result.provenance)


def _with_comparison(payload, sentence: str, *, evidence=True) -> Prose:
    """The payload's inputs and decision, with ``sentence`` cited as the comparison."""
    prose = state_inputs(Prose(), payload)
    prose.say(("claim.comparison", sentence))
    if evidence:
        levels = " and ".join(level.replace("_", " ") for level in payload["evidence"]["required_levels"])
        prose.say(("claim.evidence", f"The decision requires {levels} evidence."))
    prose.policy["uncertainty"] = payload["uncertainty"]
    prose.say("It is for this decision: ", ("claim.decision", payload["decision"]["statement"]))
    return prose


# ---------------------------------------------------------------------------
# Positive controls: a proposal the text fully states compiles normally.
# ---------------------------------------------------------------------------


def test_a_fully_grounded_proposal_compiles_and_records_why_each_field_holds_its_value(registry) -> None:
    prose, proposal = _faithful(t3_claim())
    result = _compile(prose, proposal, registry)
    assert result.status == "ready", result.findings
    assert result.advisory == {}
    by_field = {p.field: p.provenance for p in result.provenance}
    assert set(by_field) == set(SCIENTIFIC_FIELDS)
    assert all(p.admissible for p in result.provenance)
    assert by_field["target"] is CriterionProvenance.SOURCE_GROUNDED
    assert by_field["kind"] is CriterionProvenance.COMPUTED_FROM_GROUNDED
    assert by_field["uncertainty"] is CriterionProvenance.POLICY_BOUND
    assert by_field["discrepancy"] is CriterionProvenance.LEAST_AUTHORITY
    assert result.compiled.claim.statement == prose.text.strip()  # the user's words, not the model's paraphrase


@pytest.mark.parametrize("sentence", [
    "The temperature at probe must be 305.0 kelvin ± 0.5 kelvin.",
    "The temperature at the probe must stay within 0.5 kelvin of 305.0 kelvin.",
    "The temperature at probe must be 305K ± 0.5K.",
])
def test_a_band_is_read_in_either_written_form(registry, sentence) -> None:
    payload = t3_claim().to_dict()
    payload["target"]["value"]["magnitude"] = 305.0
    result = _compile(_with_comparison(payload, sentence), copy.deepcopy(payload), registry)
    assert result.status == "ready", result.findings


def test_a_bound_written_in_another_unit_is_read_by_conversion(registry) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below 80 degC.")
    assert _compile(prose, copy.deepcopy(payload), registry).status == "ready"  # 353.15 K is 80 degC
    payload["target"]["value"]["magnitude"] = 353.0
    _assert_fails_closed(_compile(prose, payload, registry), "target")


# ---------------------------------------------------------------------------
# The reproduced CRITICAL: 305 K stated, 309.75 K proposed.
# ---------------------------------------------------------------------------


def _f1_case():
    payload = t3_claim().to_dict()
    prose = _with_comparison(payload, "The temperature at probe must be 305 K ± 0.5 K.")
    return prose, copy.deepcopy(payload)  # the proposal keeps 309.75 K: the model's number


def test_f1_the_model_changing_305_k_to_309_75_k_cannot_compile(registry) -> None:
    prose, proposal = _f1_case()
    assert proposal["target"]["value"]["magnitude"] == 309.75
    result = _compile(prose, proposal, registry)
    _assert_fails_closed(result, "target")
    assert result.advisory["target"]["value"]["magnitude"] == 309.75


def test_f1_the_product_flow_never_runs_or_assesses_the_models_target(registry) -> None:
    prose, proposal = _f1_case()
    run = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)
    assert run["record"] is None and run["view"] is None
    assert run["preparation"]["status"] == UNGROUNDED and run["preparation"]["ready"] is False
    assert run["preparation"]["compilation"] is None


def test_f1_the_same_text_with_the_users_own_target_compiles(registry) -> None:
    prose, proposal = _f1_case()
    proposal["target"]["value"]["magnitude"] = 305.0
    result = _compile(prose, proposal, registry)
    assert result.status == "ready", result.findings
    record = assess_claim(result.compiled.claim, registry).to_dict()
    assert record["claim"]["target"]["value"]["magnitude"] == 305.0  # a verdict about the bound the user wrote


def test_f1g_an_advisory_claim_resubmitted_as_a_structured_claim_says_who_authored_its_criteria(registry) -> None:
    """The laundering path: prepare -> ungrounded advisory -> run_simulation(advisory). Its record cannot pass for grounded."""
    from engcore.product.runtime import run_simulation

    prose, proposal = _f1_case()
    laundered = run_simulation(proposal, registry)
    assert laundered["criteria_authority"]["authority"] == "caller_authored"
    assert laundered["criteria_authority"]["grounded"] is False
    proposal["target"]["value"]["magnitude"] = 305.0
    grounded = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)
    assert grounded["criteria_authority"]["authority"] == "grounded" and grounded["criteria_authority"]["grounded"] is True
    assert {p["field"] for p in grounded["criteria_authority"]["provenance"]} == set(SCIENTIFIC_FIELDS)


def test_prepare_simulation_shows_the_advisory_value_and_never_compiles_it(registry) -> None:
    prose, proposal = _f1_case()
    view = prepare_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)
    assert view["ready"] is False and view["compilation"] is None
    assert view["advisory"]["target"]["value"]["magnitude"] == 309.75


# ---------------------------------------------------------------------------
# Every way a model could author a criterion.
# ---------------------------------------------------------------------------


def test_the_model_inventing_a_target_with_no_comparison_cited_fails_closed(registry) -> None:
    prose, proposal = _faithful(et_claim())
    del prose.spans["claim.comparison"]
    _assert_fails_closed(_compile(prose, proposal, registry), "target")


def test_the_model_inventing_a_number_and_citing_a_real_sentence_fails_closed(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["target"]["value"]["magnitude"] = 360.0
    _assert_fails_closed(_compile(prose, proposal, registry), "target")


def test_the_model_changing_the_operator_fails_closed(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["operator"] = ">"
    _assert_fails_closed(_compile(prose, proposal, registry), "operator")


def test_the_model_loosening_the_tolerance_fails_closed(registry) -> None:
    prose, proposal = _faithful(t3_claim())
    proposal["tolerance"]["magnitude"] = 5.0
    _assert_fails_closed(_compile(prose, proposal, registry), "tolerance")


def test_the_model_weakening_the_required_evidence_fails_closed(registry) -> None:
    prose, proposal = _faithful(t3_claim())
    proposal["evidence"]["required_levels"] = ["dimensionally_valid"]
    _assert_fails_closed(_compile(prose, proposal, registry), "evidence")


def test_the_model_dropping_one_of_two_stated_levels_fails_closed_even_citing_another_sentence(registry) -> None:
    payload = t3_claim().to_dict()
    payload["evidence"]["required_levels"] = ["analytically_verified", "benchmark_validated"]
    prose = state_claim(payload)
    prose.say(("claim.evidence", "Analytically verified evidence is the bar."))  # the model cites a narrower sentence
    proposal = copy.deepcopy(payload)
    proposal["evidence"]["required_levels"] = ["analytically_verified"]
    _assert_fails_closed(_compile(prose, proposal, registry), "evidence")


def test_the_model_removing_a_stated_uncertainty_channel_fails_closed(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 2.0}
    prose = state_claim(payload)
    proposal = copy.deepcopy(payload)
    proposal["uncertainty"]["required_channels"] = []
    proposal["uncertainty"]["coverage_factor"] = None
    _assert_fails_closed(_compile(prose, proposal, registry), "uncertainty")


def test_the_model_altering_the_coverage_factor_fails_closed(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 2.0}
    prose = state_claim(payload)
    proposal = copy.deepcopy(payload)
    proposal["uncertainty"]["coverage_factor"] = 1.0
    _assert_fails_closed(_compile(prose, proposal, registry), "uncertainty")


def test_the_model_supplying_a_known_benchmark_value_from_memory_fails_closed(registry) -> None:
    """The NAFEMS T3 reference is 309.75 K. A model that knows it may not substitute it for the user's bound."""
    prose, proposal = _f1_case()
    proposal["target"]["value"] = {**proposal["target"]["value"], "magnitude": 309.75, "units": "kelvin"}
    _assert_fails_closed(_compile(prose, proposal, registry), "target")


def test_a_decision_context_is_never_taken_from_the_model(registry) -> None:
    from engcore.claims.governance.policy import builtin_context

    prose, proposal = _faithful(t3_claim())
    proposal["decision_context"] = builtin_context(
        "research_exploration", influence="low", consequence="low", owner="the model"
    ).to_dict()
    _assert_fails_closed(_compile(prose, proposal, registry), "decision_context")


@pytest.mark.parametrize("field, value", [
    ("required_capabilities", ["thermal:body_temperature"]),
    ("input_uncertainty", {"anything": 1}),
])
def test_selection_and_distribution_declarations_are_never_read_from_prose(registry, field, value) -> None:
    prose, proposal = _faithful(et_claim())
    proposal[field] = value
    result = _compile(prose, proposal, registry)
    assert result.status in (UNGROUNDED, "refused") and result.compiled is None


# ---------------------------------------------------------------------------
# Re-review F1-A: the comparison is read, never matched loosely; negation blocks it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", [
    "The final temperature must never exceed 353.15 kelvin.",
    "The final temperature cannot exceed 353.15 kelvin.",
    "The final temperature must not be below 353.15 kelvin under load.",
    "The final temperature must stay below 353.15 kelvin over a 10 s pulse.",
    "The final temperature must stay below 353.15 kelvin and above freezing.",
])
@pytest.mark.parametrize("operator", ["<", "<=", ">", ">="])
def test_f1a_a_negated_or_doubly_compared_sentence_grounds_no_operator(registry, sentence, operator) -> None:
    payload = et_claim().to_dict()
    proposal = copy.deepcopy(payload)
    proposal["operator"] = operator
    result = _compile(_with_comparison(payload, sentence), proposal, registry)
    assert result.status == UNGROUNDED and result.compiled is None
    assert {"operator", "target"} & set(result.advisory)


@pytest.mark.parametrize("operator, grounded", [(">=", True), (">", False), ("<", False), ("<=", False)])
def test_f1a_a_negation_that_is_itself_the_comparison_phrase_is_read_exactly(registry, operator, grounded) -> None:
    payload = et_claim().to_dict()
    proposal = copy.deepcopy(payload)
    proposal["operator"] = operator
    result = _compile(_with_comparison(payload, "The final temperature is not below 353.15 kelvin."), proposal, registry)
    assert (result.status != UNGROUNDED) is grounded, result.findings


# ---------------------------------------------------------------------------
# Re-review F1-B: the bound is the one bound of the stated comparison.
# ---------------------------------------------------------------------------


def test_f1b_a_number_from_another_sentence_cannot_be_the_bound(registry) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below 330 kelvin.")
    prose.say("The soak chamber is held above 353.15 kelvin.")
    proposal = copy.deepcopy(payload)  # the model proposes 353.15 K, the chamber's number
    _assert_fails_closed(_compile(prose, proposal, registry), "target")
    prose.cite("claim.comparison", "The soak chamber is held above 353.15 kelvin.")
    _assert_fails_closed(_compile(prose, proposal, registry), "qoi")


def test_f1b_a_sentence_with_two_candidate_bounds_states_none(registry) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin while the ambient is 300 kelvin.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "target")


def test_f1b_a_bound_that_is_also_an_input_is_a_reference_never_a_second_use(registry) -> None:
    payload = et_claim().to_dict()
    ambient = payload["known_inputs"]["stages[0].body.ambient_temperature"]
    prose = Prose()
    stated = dict(payload, known_inputs={k: v for k, v in payload["known_inputs"].items() if k != "stages[0].body.ambient_temperature"})
    state_inputs(prose, stated)
    sentence = f"The final temperature must stay below the ambient temperature of {ambient['magnitude']!r} kelvin."
    prose.say(("claim.comparison", sentence))
    value_at = prose.spans["claim.comparison"][0] + sentence.index(f"{ambient['magnitude']!r} kelvin")
    prose.spans["stages[0].body.ambient_temperature"] = (value_at, value_at + len(f"{ambient['magnitude']!r} kelvin"))
    prose.say(("claim.evidence", "The decision requires analytically verified evidence."))
    prose.say("It is for this decision: ", ("claim.decision", payload["decision"]["statement"]))
    prose.policy["uncertainty"] = payload["uncertainty"]
    by_value = copy.deepcopy(payload)
    by_value["target"]["value"] = {**by_value["target"]["value"], "magnitude": ambient["magnitude"]}
    _assert_fails_closed(_compile(prose, by_value, registry), "target")   # one statement grounds one field
    by_reference = copy.deepcopy(payload)
    by_reference["target"] = {**by_reference["target"], "value": None, "input_ref": "stages[0].body.ambient_temperature"}
    result = _compile(prose, by_reference, registry)
    assert {p.field: p.provenance for p in result.provenance}["target"] is CriterionProvenance.COMPUTED_FROM_GROUNDED, result.findings


# ---------------------------------------------------------------------------
# Re-review F1-C: the quantity is named as a phrase, before the comparison, in that sentence.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", [
    "The junction temperature must stay below 353.15 kelvin; the final stage is bolted down.",
    "The final body is hot and its temperature must stay below 353.15 kelvin.",
    "Below 353.15 kelvin is where the final temperature must stay.",
])
def test_f1c_the_quantity_is_not_assembled_from_scattered_words(registry, sentence) -> None:
    payload = et_claim().to_dict()
    _assert_fails_closed(_compile(_with_comparison(payload, sentence), copy.deepcopy(payload), registry), "qoi")


# ---------------------------------------------------------------------------
# Re-review F1-D: a waiver of uncertainty is never read from prose.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("words", [
    "Results without uncertainty quantification are rejected.",
    "A point comparison is not acceptable.",
    "A point comparison is acceptable.",
])
def test_f1d_no_sentence_waives_uncertainty(registry, words) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", words))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


# ---------------------------------------------------------------------------
# Re-review F1-E: ordinary wording cannot silently drop a requirement.
# ---------------------------------------------------------------------------


def test_f1e_a_requirement_written_another_way_is_still_read(registry) -> None:
    payload = et_claim().to_dict()
    payload["evidence"]["required_levels"] = ["numerically_converged"]
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.", evidence=False)
    prose.say(("claim.evidence", "Numerically converged results are needed and they must be validated experimentally."))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "evidence")


def test_f1e_an_evidence_word_the_reader_cannot_place_blocks_the_bar(registry) -> None:
    payload = et_claim().to_dict()
    prose = state_claim(payload)
    prose.say("The design was validated against the supplier sheet.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "evidence")


def test_f1e_an_aleatory_demand_cannot_be_dropped(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"]}
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", "Quantify numerical and aleatory uncertainty."))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


def test_f1e_a_policy_cannot_silently_drop_a_stricter_stated_requirement(registry) -> None:
    payload = t3_claim().to_dict()
    prose = state_claim(payload)
    prose.say("Experimental validation is required as well.")
    result = _compile(prose, copy.deepcopy(payload), registry, evidence=payload["evidence"])
    _assert_fails_closed(result, "evidence")


# ---------------------------------------------------------------------------
# Re-review F1-F: numbers are read only when written plainly.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("written, misread", [
    ("1,200 kelvin", 1.2),
    ("1,200 kelvin", 1200.0),
    ("−180 kelvin", 180.0),
    ("−180 kelvin", -180.0),
    ("1/2 kelvin", 2.0),
    ("10^3 kelvin", 3.0),
    ("100 kelvin rise", 100.0),
])
def test_f1f_a_number_this_reader_could_misread_grounds_nothing(registry, written, misread) -> None:
    payload = et_claim().to_dict()
    payload["operator"] = ">"
    payload["target"]["value"]["magnitude"] = misread
    prose = _with_comparison(payload, f"The final temperature must stay above {written}.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "target")


def test_f1f_a_misreadable_number_beside_a_plain_bound_still_blocks_the_comparison(registry) -> None:
    """The unreadable 1,200 K could be the user's real bound: the plain 300 K beside it is not read as the bound."""
    payload = et_claim().to_dict()
    payload["operator"] = ">"
    payload["target"]["value"]["magnitude"] = 300.0
    prose = _with_comparison(payload, "The final temperature must stay above 300 kelvin during the 1,200 kelvin soak.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "target")


def test_f1f_the_number_reader_marks_ambiguous_writing() -> None:
    def read(text):
        return [(n.magnitude, n.unit, n.readable) for n in stated_numbers(text, 0, len(text))]
    assert read("305 K") == [(305.0, "kelvin", True)]
    assert read("-18 degC")[0][:2] == (-18.0, "degree_Celsius") and read("-18 degC")[0][2]
    assert not read("1,500 K")[0][2]
    assert not read("−18 degC")[0][2]
    assert all(not r[2] for r in read("5×10^3 Pa")[1:])
    assert not read("100 kPa gauge")[0][2]
    assert read("R1 and R-134a") == []


# ---------------------------------------------------------------------------
# Re-review F1-H: the coverage factor is the number the text calls the coverage factor.
# ---------------------------------------------------------------------------


def test_f1h_a_bare_number_is_not_a_coverage_factor(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 1.0}
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", "Quantify numerical uncertainty over 1 load case with coverage factor 3."))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


# ---------------------------------------------------------------------------
# Inputs: read after their own name (F1-B for inputs, F1-J).
# ---------------------------------------------------------------------------


def test_an_input_is_read_after_its_own_name_not_from_a_neighbouring_value() -> None:
    text = "The ambient temperature is 300 K and the initial temperature is 350 K."
    start = text.index("300 K")
    spans = {"stages[0].body.initial_temperature": (start, start + 5)}
    with pytest.raises(Ungrounded):
        ground_input(text, spans, TokenLedger(), "stages[0].body.initial_temperature", {"magnitude": 300.0, "units": "kelvin"})


def test_a_negated_sentence_states_no_input_value() -> None:
    text = "The material is aluminium, not copper."
    start = text.index("copper")
    with pytest.raises(Ungrounded):
        ground_input(text, {"body.material": (start, start + 6)}, TokenLedger(), "body.material", "copper")


def test_a_flag_is_a_whole_word() -> None:
    text = "The coating flag is untrue."
    start = text.index("untrue")
    with pytest.raises(Ungrounded):
        ground_input(text, {"body.coating_flag": (start, start + 6)}, TokenLedger(), "body.coating_flag", True)


def test_a_decision_statement_must_be_a_statement(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["decision"] = {**proposal["decision"], "statement": "a"}
    _assert_fails_closed(_compile(prose, proposal, registry), "decision")


# ---------------------------------------------------------------------------
# Policy: the application, never the model, may bind a criterion.
# ---------------------------------------------------------------------------


def test_a_policy_bound_evidence_bar_replaces_what_the_text_does_not_state(registry) -> None:
    payload = t3_claim().to_dict()
    prose = state_claim(payload)
    start, end = prose.spans.pop("claim.evidence")
    prose.text = prose.text[:start] + " " * (end - start) + prose.text[end:]  # the sentence is gone, offsets kept
    proposal = copy.deepcopy(payload)
    del proposal["evidence"]
    result = _compile(prose, proposal, registry, evidence=payload["evidence"])
    assert result.status == "ready", result.findings
    assert {p.field: p.provenance for p in result.provenance}["evidence"] is CriterionProvenance.POLICY_BOUND


def test_a_proposal_contradicting_the_policy_fails_closed(registry) -> None:
    prose, proposal = _faithful(t3_claim())
    bar = copy.deepcopy(proposal["evidence"])
    proposal["evidence"]["required_levels"] = ["dimensionally_valid"]
    _assert_fails_closed(_compile(prose, proposal, registry, evidence=bar), "evidence")


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
    _assert_fails_closed(_compile(prose, proposal, registry), "a_future_criterion")


@pytest.mark.parametrize(("words", "expected"), [
    ("must not exceed", {ConstraintOperator.LESS_EQUAL}),
    ("stays below", {ConstraintOperator.LESS_THAN}),
    ("at least", {ConstraintOperator.GREATER_EQUAL}),
    ("exceeds", {ConstraintOperator.GREATER_THAN}),
    ("within", {ConstraintOperator.EQUAL}),
    ("below, and above", {ConstraintOperator.LESS_THAN, ConstraintOperator.GREATER_THAN}),
    ("is", set()),
])
def test_operator_phrases_are_read_longest_first_and_never_twice(words, expected) -> None:
    assert operators_stated(words) == expected


def test_the_grounding_module_is_the_only_criterion_authority_in_the_adapter() -> None:
    import inspect

    source = inspect.getsource(nl.compile_natural_language)
    assert source.count("compile_claim(") == 1
    assert source.index("if advisory:") < source.index("compile_claim(proposal")
    assert grounding.ADMISSIBLE_PROVENANCE == frozenset(CriterionProvenance) - {CriterionProvenance.AI_PROPOSED}
