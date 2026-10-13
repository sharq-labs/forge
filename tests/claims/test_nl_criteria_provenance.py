"""F1 (hostile review, CRITICAL): a language model may not author the criteria a claim is judged by.

The reproduced defect: the user wrote "305 K ± 0.5 K", the model's proposal said
309.75 K, the adapter grounded the inputs and nothing else, and the claim was
SUPPORTED against the model's number. Every test here offers one AI-authored
criterion and requires the adapter to fail closed: no compiled claim, nothing
executable, the model's value returned as advisory only.

Two independent re-reviews then showed that reading criteria out of free
English with phrase lists cannot be made safe (prepositions read as
comparisons, failure conditions read as requirements, negations cut off by a
line break, requirements worded outside the lexicon). Criteria are therefore
grounded only from CONTROLLED SENTENCES the adapter parses completely; every
other sentence leaves the criterion ungrounded. The exploits of both re-reviews
are pinned below.
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
    sentences,
    stated_numbers,
)
from engcore.claims.adapters.nl import UNGROUNDED, compile_natural_language
from engcore.claims.contract import SCIENTIFIC_FIELDS
from engcore.mcp.capabilities import production_registry
from engcore.product.runtime import prepare_simulation, run_proposed_simulation
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.units.quantity import Quantity
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


def _with_comparison(payload, sentence: str, *, evidence=True, inputs=None) -> Prose:
    """The payload's inputs and decision, with ``sentence`` cited as the comparison."""
    prose = state_inputs(Prose(), payload if inputs is None else inputs)
    prose.say(("claim.comparison", sentence))
    if evidence:
        levels = " and ".join(level.replace("_", " ") for level in payload["evidence"]["required_levels"])
        prose.say(("claim.evidence", f"The decision requires {levels} evidence."))
    prose.policy["uncertainty"] = payload["uncertainty"]
    prose.say("It is for this decision: ", ("claim.decision", payload["decision"]["statement"]))
    return prose


def _et_with(sentence: str, **changes) -> tuple[Prose, dict]:
    payload = et_claim().to_dict()
    for key, value in changes.items():
        payload[key] = value
    return _with_comparison(payload, sentence), copy.deepcopy(payload)


# ---------------------------------------------------------------------------
# Positive controls: every controlled form compiles.
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
    "the temperature at probe must remain 305.0 kelvin +/- 0.5 kelvin!",
])
def test_a_band_is_read_in_each_controlled_form(registry, sentence) -> None:
    payload = t3_claim().to_dict()
    payload["target"]["value"]["magnitude"] = 305.0
    result = _compile(_with_comparison(payload, sentence), copy.deepcopy(payload), registry)
    assert result.status == "ready", result.findings


@pytest.mark.parametrize("phrase, operator", [
    ("below", "<"), ("at most", "<="), ("no more than", "<="), ("above", ">"), ("at least", ">="), ("not less than", ">="),
])
def test_each_controlled_threshold_phrase_grounds_exactly_its_operator(registry, phrase, operator) -> None:
    payload = et_claim().to_dict()
    payload["operator"] = operator
    prose = _with_comparison(payload, f"The final temperature must be {phrase} 353.15 kelvin.")
    assert _compile(prose, copy.deepcopy(payload), registry).status != UNGROUNDED
    for other in {"<", "<=", ">", ">="} - {operator}:
        wrong = copy.deepcopy(payload)
        wrong["operator"] = other
        _assert_fails_closed(_compile(prose, wrong, registry), "operator")


def test_a_bound_written_in_another_unit_is_read_by_conversion(registry) -> None:
    prose, proposal = _et_with("The final temperature must stay below 80 degC.")
    assert _compile(prose, proposal, registry).status == "ready"  # 353.15 K is 80 degC
    proposal["target"]["value"]["magnitude"] = 353.0
    _assert_fails_closed(_compile(prose, proposal, registry), "target")


def test_a_bound_named_as_a_stated_input_is_a_reference_never_a_copied_number(registry) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below the ambient temperature.")
    by_reference = copy.deepcopy(payload)
    by_reference["target"] = {**by_reference["target"], "value": None, "input_ref": "stages[0].body.ambient_temperature"}
    result = _compile(prose, by_reference, registry)
    assert {p.field: p.provenance for p in result.provenance}["target"] is CriterionProvenance.COMPUTED_FROM_GROUNDED, result.findings
    by_value = copy.deepcopy(payload)
    by_value["target"]["value"]["magnitude"] = payload["known_inputs"]["stages[0].body.ambient_temperature"]["magnitude"]
    _assert_fails_closed(_compile(prose, by_value, registry), "target")
    other_input = copy.deepcopy(by_reference)
    other_input["target"]["input_ref"] = "stages[0].body.initial_temperature"
    _assert_fails_closed(_compile(prose, other_input, registry), "target")


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
    """The laundering path: prepare -> ungrounded advisory -> run_simulation(advisory)."""
    from engcore.product.runtime import run_simulation

    prose, proposal = _f1_case()
    laundered = run_simulation(proposal, registry)
    assert laundered["criteria_authority"]["authority"] == "caller_authored"
    assert laundered["record"]["criteria_authority"]["authority"] == "caller_authored"
    proposal["target"]["value"]["magnitude"] = 305.0
    grounded = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)
    assert grounded["record"]["criteria_authority"]["authority"] == "grounded"
    assert {p["field"] for p in grounded["record"]["criteria_authority"]["provenance"]} == set(SCIENTIFIC_FIELDS)
    assert laundered["view"]["verdict_qualifier"] == "criteria authored by the caller, not grounded"
    assert grounded["view"]["verdict_qualifier"] is None


def test_r9_who_authored_the_criteria_is_bound_into_the_record_and_re_derived(registry) -> None:
    """Re-review R9: the label lives in the digested record; 'grounded' is re-grounded on read-back, never trusted."""
    from engcore.claims.assessment import AssessmentForgeryError, verify_assessment
    from engcore.product.runtime import run_simulation

    prose, proposal = _f1_case()
    proposal["target"]["value"]["magnitude"] = 305.0
    grounded = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)["record"]
    assert verify_assessment(grounded, registry).to_dict() == grounded            # re-grounds and re-derives

    forged = copy.deepcopy(grounded)                                              # the user's text rewritten after the fact
    forged["criteria_authority"]["source_text"] = forged["criteria_authority"]["source_text"].replace("305 K", "309 K")
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(forged, registry)

    caller = run_simulation(proposal, registry)["record"]
    assert verify_assessment(caller, registry).to_dict() == caller
    promoted = copy.deepcopy(caller)                                              # a caller record relabelled as grounded
    promoted["criteria_authority"] = copy.deepcopy(grounded["criteria_authority"])
    promoted["criteria_authority"]["source_text"] = "The final temperature must stay below 999 kelvin."
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(promoted, registry)
    unlabelled = copy.deepcopy(caller)
    del unlabelled["criteria_authority"]
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(unlabelled, registry)


def test_prepare_simulation_shows_the_advisory_value_and_never_compiles_it(registry) -> None:
    prose, proposal = _f1_case()
    view = prepare_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)
    assert view["ready"] is False and view["compilation"] is None
    assert view["advisory"]["target"]["value"]["magnitude"] == 309.75


# ---------------------------------------------------------------------------
# The original eight: every way a model could author a criterion.
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
    prose.say(("claim.evidence", "The decision requires analytically verified evidence."))  # a second, narrower statement
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
# First re-review (F1-A .. F1-J) against the controlled forms.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", [
    "The final temperature must never exceed 353.15 kelvin.",
    "The final temperature cannot exceed 353.15 kelvin.",
    "The final temperature must not be below 353.15 kelvin under load.",
    "The final temperature must stay below 353.15 kelvin over a 10 s pulse.",
    "The final temperature must stay below 353.15 kelvin and above freezing.",
    "The final temperature must stay below 330 kelvin; the soak chamber is held above 353.15 kelvin.",
    "The final temperature must stay below 353.15 kelvin while the ambient is 300 kelvin.",
])
@pytest.mark.parametrize("operator", ["<", "<=", ">", ">="])
def test_no_comparison_is_read_from_a_sentence_outside_the_controlled_forms(registry, sentence, operator) -> None:
    payload = et_claim().to_dict()
    proposal = copy.deepcopy(payload)
    proposal["operator"] = operator
    result = _compile(_with_comparison(payload, sentence), proposal, registry)
    assert result.status == UNGROUNDED and result.compiled is None
    assert {"qoi", "operator", "target"} <= set(result.advisory)


def test_f1b_a_number_from_another_sentence_cannot_be_the_bound(registry) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below 330 kelvin.")
    prose.say("The soak chamber is held above 353.15 kelvin.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "target")
    prose.cite("claim.comparison", "The soak chamber is held above 353.15 kelvin.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "qoi")


@pytest.mark.parametrize("sentence", [
    "The junction temperature must stay below 353.15 kelvin.",
    "The final body is hot and its temperature must stay below 353.15 kelvin.",
    "Below 353.15 kelvin is where the final temperature must stay.",
    "The maximum final temperature must stay below 353.15 kelvin.",           # R6: a sub-phrase of the subject
    "In this case the final temperature must stay below 353.15 kelvin.",       # R6: words bridged by a stopword
])
def test_the_quantity_is_the_whole_subject_of_the_sentence(registry, sentence) -> None:
    prose, proposal = _et_with(sentence)
    _assert_fails_closed(_compile(prose, proposal, registry), "qoi")


@pytest.mark.parametrize("words", [
    "Results without uncertainty quantification are rejected.",
    "A point comparison is not acceptable.",
    "A point comparison is acceptable.",
])
def test_no_sentence_waives_uncertainty(registry, words) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", words))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


def test_an_evidence_requirement_worded_outside_the_controlled_form_is_not_read(registry) -> None:
    payload = et_claim().to_dict()
    payload["evidence"]["required_levels"] = ["numerically_converged"]
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.", evidence=False)
    prose.say(("claim.evidence", "Numerically converged results are needed and they must be validated experimentally."))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "evidence")


def test_an_evidence_word_in_another_sentence_blocks_the_bar(registry) -> None:
    prose, proposal = _faithful(et_claim())
    prose.say("The design was validated against the supplier sheet.")
    _assert_fails_closed(_compile(prose, proposal, registry), "evidence")


def test_an_aleatory_demand_cannot_be_dropped(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"]}
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", "Quantify numerical and aleatory uncertainty."))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


def test_a_policy_cannot_silently_drop_a_stricter_stated_requirement(registry) -> None:
    payload = t3_claim().to_dict()
    prose = state_claim(payload)
    prose.say("Experimental validation is required as well.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry, evidence=payload["evidence"]), "evidence")


@pytest.mark.parametrize("written, misread", [
    ("1,200 kelvin", 1.2), ("1,200 kelvin", 1200.0),
    ("−180 kelvin", 180.0), ("−180 kelvin", -180.0),
    ("1/2 kelvin", 1.0), ("1/2 kelvin", 0.5), ("10^3 kelvin", 10.0),
    ("100 kelvin rise", 100.0),
    ("300 kelvin during the 1,200 kelvin soak", 300.0),
    ("2.500 kelvin", 2.5), ("2.500 kelvin", 2500.0),                           # R8: a grouping look-alike
])
def test_a_bound_this_reader_could_misread_grounds_nothing(registry, written, misread) -> None:
    payload = et_claim().to_dict()
    payload["operator"] = ">"
    payload["target"]["value"]["magnitude"] = misread
    prose = _with_comparison(payload, f"The final temperature must stay above {written}.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "target")


def test_the_number_reader_marks_ambiguous_writing() -> None:
    def read(text):
        return [(n.magnitude, n.unit, n.readable) for n in stated_numbers(text, 0, len(text))]
    assert read("305 K") == [(305.0, "kelvin", True)]
    assert not read("1,500 K")[0][2]
    assert not read("−18 degC")[0][2]
    assert all(not r[2] for r in read("5×10^3 Pa")[1:])
    assert not read("100 kPa gauge")[0][2]
    assert not read("10 A (peak)")[0][2]                                          # R8: a bracketed modifier
    assert not read("1.000.000 Pa")[0][2]                                         # R8: never skipped silently
    assert read("R1 and R-134a") == []


def test_a_bare_number_is_not_a_coverage_factor(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 1.0}
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", "Quantify numerical uncertainty over 1 load case with coverage factor 3."))
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


# ---------------------------------------------------------------------------
# Second re-review (R1 .. R10).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", [
    "The final temperature under full load reaches 353.15 kelvin.",             # R1: a preposition, no comparison
    "The final temperature over a 10 s pulse settles at 353.15 kelvin.",
    "The final temperature heats up to 353.15 kelvin.",
    "The design fails if the final temperature exceeds 353.15 kelvin.",         # R2: the failure condition
    "Reject the part when the final temperature rises above 353.15 kelvin.",
    "Avoid a final temperature above 353.15 kelvin.",
    "It is false that the\nfinal temperature must stay below 353.15 kelvin.",   # R3: a line break inside a sentence
    "Never, e.g. during a pulse, should the final temperature exceed 353.15 kelvin.",  # R3: an abbreviation
])
@pytest.mark.parametrize("operator", ["<", "<=", ">", ">="])
def test_r1_r3_prepositions_failure_framing_and_split_negations_ground_nothing(registry, sentence, operator) -> None:
    payload = et_claim().to_dict()
    proposal = copy.deepcopy(payload)
    proposal["operator"] = operator
    result = _compile(_with_comparison(payload, sentence), proposal, registry)
    assert result.status == UNGROUNDED and result.compiled is None


def test_r3_a_line_break_is_whitespace_and_an_abbreviation_is_not_a_sentence_end() -> None:
    text = "It is false that the\nfinal temperature must stay low. Never, e.g. during a pulse, exceed it."
    bodies = [s.text for s in sentences(text)]
    assert bodies == ["It is false that the final temperature must stay low",
                      "Never, e.g. during a pulse, exceed it"]


def test_a_retraction_in_another_sentence_blocks_the_comparison(registry) -> None:
    payload = et_claim().to_dict()
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.say("That final temperature limit does not apply to this part.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "qoi")


def test_r4_an_unrelated_k_is_never_a_coverage_factor(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": None}
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", "Quantify numerical uncertainty."))
    prose.say("The insulation has k = 0.04 W/(m K).")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


@pytest.mark.parametrize("extra", [
    "The prediction must agree with lab measurements.",
    "Calibrate it against the test rig.",
])
def test_r5_an_evidence_demand_in_other_words_blocks_the_bar(registry, extra) -> None:
    prose, proposal = _faithful(et_claim())
    prose.say(extra)
    _assert_fails_closed(_compile(prose, proposal, registry), "evidence")


def test_r5_an_uncertainty_demand_in_other_words_blocks_the_demand(registry) -> None:
    payload = et_claim().to_dict()
    payload["uncertainty"] = {**payload["uncertainty"], "required_channels": ["numerical"]}
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", "Quantify numerical uncertainty."))
    prose.say("Measurement variability matters too.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry), "uncertainty")


def test_r5_a_policy_coverage_factor_below_the_stated_one_is_refused(registry) -> None:
    payload = et_claim().to_dict()
    demand = {**payload["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 1.0}
    payload["uncertainty"] = demand
    prose = _with_comparison(payload, "The final temperature must stay below 353.15 kelvin.")
    prose.policy.pop("uncertainty")
    prose.say("Quantify numerical uncertainty with coverage factor 2.")
    _assert_fails_closed(_compile(prose, copy.deepcopy(payload), registry, uncertainty=demand), "uncertainty")


def test_r2_a_counterfactual_input_states_no_value() -> None:
    text = "If the ambient temperature were 290 K the cell would pass."
    start = text.index("290 K")
    with pytest.raises(Ungrounded):
        ground_input(text, {"cell.ambient_temperature": (start, start + 5)}, TokenLedger(), "cell.ambient_temperature",
                     Quantity(290.0, "kelvin").to_dict())


@pytest.mark.parametrize("text, value", [
    ("The busbar material is aluminium rather than copper.", "copper"),           # R7: contrastive
    ("The material is aluminium, not copper.", "copper"),
    ("The ambient temperature is 300 K and the initial temperature is 350 K.", None),
])
def test_r7_an_input_is_the_whole_value_of_its_own_sentence(text, value) -> None:
    if value is None:
        start = text.index("300 K")
        path, raw = "stages[0].body.initial_temperature", Quantity(300.0, "kelvin").to_dict()
    else:
        start = text.index(value)
        path, raw = "busbar.material", value
    with pytest.raises(Ungrounded):
        ground_input(text, {path: (start, start + len(value or "300 K"))}, TokenLedger(), path, raw)


def test_an_input_stated_twice_is_not_read() -> None:
    text = "The heat capacity is 50 J/K. Correction: The heat capacity is 60 J/K."
    start = text.index("50 J/K")
    with pytest.raises(Ungrounded):
        ground_input(text, {"body.heat_capacity": (start, start + 6)}, TokenLedger(), "body.heat_capacity",
                     Quantity(50.0, "joule / kelvin").to_dict())


def test_the_quantity_records_used_above_are_readable_so_each_refusal_is_the_one_tested() -> None:
    """Without this, a malformed record would make every refusal above pass for the wrong reason."""
    text = "The heat capacity is 50 J/K."
    start = text.index("50 J/K")
    assert ground_input(text, {"body.heat_capacity": (start, start + 6)}, TokenLedger(), "body.heat_capacity",
                        Quantity(50.0, "joule / kelvin").to_dict()) is not None


def test_a_conditional_input_sentence_states_no_value_even_in_the_controlled_form() -> None:
    text = "When cold, the ambient temperature is 290 K."
    start = text.index("290 K")
    with pytest.raises(Ungrounded, match="conditional"):
        ground_input(text, {"cell.ambient_temperature": (start, start + 5)}, TokenLedger(), "cell.ambient_temperature",
                     Quantity(290.0, "kelvin").to_dict())


def test_an_input_is_read_only_from_a_sentence_about_that_input() -> None:
    text = "The ambient temperature is 300 K."
    start = text.index("300 K")
    with pytest.raises(Ungrounded, match="not 'initial temperature'"):
        ground_input(text, {"body.initial_temperature": (start, start + 5)}, TokenLedger(), "body.initial_temperature",
                     Quantity(300.0, "kelvin").to_dict())


def test_a_false_flag_is_a_value_not_a_negation() -> None:
    text = "The coating flag is false."
    start = text.index("false")
    assert ground_input(text, {"body.coating_flag": (start, start + 5)}, TokenLedger(), "body.coating_flag", False) is None


def test_a_flag_is_the_whole_word() -> None:
    text = "The coating flag is untrue."
    start = text.index("untrue")
    with pytest.raises(Ungrounded):
        ground_input(text, {"body.coating_flag": (start, start + 6)}, TokenLedger(), "body.coating_flag", True)


def test_r10_a_negated_decision_is_not_the_decision(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["decision"] = {**proposal["decision"], "statement": "release the board for production"}
    prose.say(("claim.decision", "We will not release the board for production."))
    _assert_fails_closed(_compile(prose, proposal, registry), "decision")


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
    ("at most", {ConstraintOperator.LESS_EQUAL}),
    ("must stay below", {ConstraintOperator.LESS_THAN}),
    ("at least", {ConstraintOperator.GREATER_EQUAL}),
    ("above", {ConstraintOperator.GREATER_THAN}),
    ("within", {ConstraintOperator.EQUAL}),
    ("below, and above", {ConstraintOperator.LESS_THAN, ConstraintOperator.GREATER_THAN}),
    ("must not exceed", set()),
    ("is", set()),
])
def test_operator_phrases_are_the_controlled_ones_only(words, expected) -> None:
    assert operators_stated(words) == expected


def test_the_grounding_module_is_the_only_criterion_authority_in_the_adapter() -> None:
    import inspect

    source = inspect.getsource(nl.compile_natural_language)
    assert source.count("compile_claim(") == 1
    assert source.index("if advisory:") < source.index("compile_claim(proposal")
    assert grounding.ADMISSIBLE_PROVENANCE == frozenset(CriterionProvenance) - {CriterionProvenance.AI_PROPOSED}
