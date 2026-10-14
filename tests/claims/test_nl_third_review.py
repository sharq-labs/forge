"""Hostile review F1, third pass: inputs, closed-world reading, policy authority and live verification.

A1  an input is read only from a sentence whose subject IS the input, and no other sentence speaks about it
A2  every sentence of the text is accounted for; one nothing reads makes the claim UNGROUNDED
A3  criteria a policy fixed are labelled ``policy_bound``; a record cannot relabel them ``grounded``
A4  a criteria authority is verified when the record is built, not only on read-back
A5  a policy may not replace a comparison the user wrote
A6  a unit spelling with more than one standard definition is not read
A7  an input written like a grouped integer is not read
"""

from __future__ import annotations

import copy

import pytest

from claims_support import et_claim, t3_claim
from engcore.claims import assess_claim
from engcore.claims.adapters.grounding import TokenLedger, Ungrounded, ground_input, read_comparison
from engcore.claims.adapters.nl import UNGROUNDED
from engcore.claims.assessment import AssessmentForgeryError, grounded_criteria, verify_assessment
from engcore.claims.errors import ClaimLayerError
from engcore.mcp.capabilities import production_registry
from engcore.product.runtime import POLICY_BOUND_QUALIFIER, run_proposed_simulation, run_simulation
from engcore.scientific.units.quantity import Quantity
from nl_support import Prose, state_inputs
from test_nl_criteria_provenance import _assert_fails_closed, _compile, _et_with, _f1_case, _faithful

K = lambda v: Quantity(v, "kelvin").to_dict()  # noqa: E731


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _ground(text: str, value: str, path: str = "cell.ambient_temperature", raw=None):
    start = text.index(value)
    return ground_input(text, {path: (start, start + len(value))}, TokenLedger(), path, raw if raw is not None else K(290.0))


# ---- A1 -------------------------------------------------------------------------------------------------


def test_a1_the_input_name_or_its_path_grounds() -> None:
    assert _ground("The ambient temperature is 290 K.", "290 K") is not None
    assert _ground("cell.ambient_temperature is 290 K.", "290 K") is not None


@pytest.mark.parametrize("text", [
    "The minimum ambient temperature is 290 K.",                                                     # a qualifier
    "The nighttime ambient temperature is 290 K. The daytime ambient temperature is 330 K.",       # two cases
    "The ambient temperature is 290 K. During the day the ambient temperature rises to 330 K.",    # a change
    "The ambient temperature is 290 K. Correction: the ambient temperature is 330 K.",
])
def test_a1_an_input_qualified_or_spoken_about_elsewhere_is_not_read(text) -> None:
    with pytest.raises(Ungrounded):
        _ground(text, "290 K")


def test_a1_sibling_paths_are_other_inputs_but_a_bare_name_beside_them_is_ambiguous() -> None:
    siblings = "stages[0].body.initial_temperature is 290 K. stages[1].body.initial_temperature is 310 K."
    assert _ground(siblings, "290 K", "stages[0].body.initial_temperature") is not None
    with pytest.raises(Ungrounded, match="another sentence"):
        _ground("The initial temperature is 290 K. stages[1].body.initial_temperature is 310 K.", "290 K",
                "stages[0].body.initial_temperature")
    # an input whose name extends this one's ("rated power temperature") is a different input
    rated = "ratings.rated_power is 20.0 W. ratings.rated_power_temperature is 298.15 K."
    assert _ground(rated, "20.0 W", "ratings.rated_power", Quantity(20.0, "watt").to_dict()) is not None
    with pytest.raises(Ungrounded, match="another sentence"):
        _ground("The rated power is 20.0 W. The rated power temperature is 298.15 K.", "20.0 W",
                "ratings.rated_power", Quantity(20.0, "watt").to_dict())


# ---- A2 -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("extra", [
    "That limit is waived during burn-in.",
    "Apply a safety margin of 20 K.",
    "Report the result at 95 % confidence.",
    "The prediction must be compared with prototype data.",
    "The clearance must be at least 5 in. unless the board is potted.",
    "We are designing a power stage.",
])
def test_a2_a_sentence_nothing_reads_makes_the_claim_ungrounded(registry, extra) -> None:
    prose, proposal = _faithful(t3_claim())
    assert _compile(prose, copy.deepcopy(proposal), registry).status == "ready"
    prose.say(extra)
    result = _compile(prose, proposal, registry)
    assert result.status == UNGROUNDED and result.compiled is None
    assert result.advisory["unread_sentences"], result.findings


def test_a2_an_input_statement_the_model_misread_still_only_withholds_an_answer(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["known_inputs"]["stages[0].body.heat_capacity"]["magnitude"] = 77.0
    result = _compile(prose, proposal, registry)
    assert result.status == "needs_input" and "unread_sentences" not in (result.advisory or {})


def test_a2_a_conditional_statement_about_a_declared_input_is_not_accounted_for(registry) -> None:
    prose, proposal = _faithful(et_claim())
    prose.say("stages[0].body.ambient_temperature is 290.0 kelvin unless the fan stops.")
    result = _compile(prose, proposal, registry)
    assert result.status == UNGROUNDED
    assert any("unless the fan stops" in sentence for sentence in result.advisory["unread_sentences"])


@pytest.mark.parametrize("extra, path", [
    ("That limit is waived during burn-in.", "that_limit"),
    ("The limit is 400 K for flight hardware.", "limit"),
])
@pytest.mark.parametrize("how", ["missing", "known"])
def test_fourth_review_blocker_an_invented_input_cannot_hide_a_sentence(registry, extra, path, how) -> None:
    prose, proposal = _faithful(t3_claim())
    prose.say((path, extra) if how == "known" else extra)
    if how == "missing":
        proposal["missing_inputs"] = sorted({*proposal.get("missing_inputs", []), path})
    else:
        proposal["known_inputs"] = {**proposal["known_inputs"], path: extra.split(" is ", 1)[1].rstrip(".")}
        start = prose.text.index(extra)
        prose.spans[path] = (start, start + len(extra))
    result = _compile(prose, proposal, registry)
    assert result.status != "ready", (result.status, result.findings)
    if how == "missing":  # the reviewer's route: before the fix this compiled READY with the sentence hidden
        assert result.status == UNGROUNDED and result.compiled is None, (result.status, result.findings)
        assert any(extra.rstrip(".") in sentence for sentence in result.advisory["unread_sentences"])


# ---- A3 -------------------------------------------------------------------------------------------------


def _fully_grounded():
    prose, proposal = _f1_case()
    proposal["target"]["value"]["magnitude"] = 305.0
    proposal["uncertainty"] = {**proposal["uncertainty"], "required_channels": ["numerical"], "coverage_factor": 2.0}
    prose.policy.pop("uncertainty")
    prose.say(("claim.uncertainty", "Quantify numerical uncertainty with coverage factor 2."))
    return prose, proposal


def test_a3_only_criteria_read_from_the_text_are_labelled_grounded(registry) -> None:
    prose, proposal = _fully_grounded()
    run = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)
    assert run["record"]["criteria_authority"]["authority"] == "grounded", run["preparation"]
    assert run["view"]["verdict_qualifier"] is None
    assert verify_assessment(run["record"], registry).to_dict() == run["record"]


def _all_by_policy():
    payload = t3_claim().to_dict()
    payload["target"]["value"]["magnitude"] = 305.0
    prose = state_inputs(Prose(), payload)
    policy = {k: copy.deepcopy(payload[k]) for k in ("kind", "qoi", "operator", "target", "tolerance", "evidence",
                                                     "uncertainty", "decision")}
    return prose, payload, policy


def test_a3_criteria_a_policy_fixed_are_policy_bound_and_say_so(registry) -> None:
    prose, payload, policy = _all_by_policy()
    run = run_proposed_simulation(prose.text, copy.deepcopy(payload), prose.spans, registry, policy=policy)
    block = run["record"]["criteria_authority"]
    assert block["authority"] == "policy_bound" and block["grounded"] is False
    assert set(policy) <= set(block["policy_fields"]) and len(block["policy_digest"]) == 64
    assert run["view"]["verdict_qualifier"] == POLICY_BOUND_QUALIFIER
    assert verify_assessment(run["record"], registry).to_dict() == run["record"]


def test_a3_a_policy_bound_record_relabelled_grounded_is_a_forgery(registry) -> None:
    prose, payload, policy = _all_by_policy()
    record = run_proposed_simulation(prose.text, copy.deepcopy(payload), prose.spans, registry, policy=policy)["record"]
    relabelled = copy.deepcopy(record)
    block = relabelled["criteria_authority"]
    block.update(authority="grounded", grounded=True)
    for key in ("policy_fields", "policy_digest"):
        block.pop(key)
    with pytest.raises(AssessmentForgeryError, match="does not re-derive"):
        verify_assessment(relabelled, registry)


def test_a3_the_statement_must_be_the_text_the_criteria_were_grounded_in(registry) -> None:
    prose, proposal = _fully_grounded()
    record = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)["record"]
    claim = copy.deepcopy(record["claim"])
    claim["statement"] = "The probe temperature is comfortably inside its band."
    with pytest.raises(ClaimLayerError, match="not the source text"):
        assess_claim(claim, registry, criteria_authority=record["criteria_authority"])


# ---- A4 -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("block", [{"authority": "grounded"}, {"authority": "policy_bound"},
                                   {"authority": "caller_authored", "grounded": True}])
def test_a4_a_live_assessment_refuses_an_unverified_authority_block(registry, block) -> None:
    prose, proposal = _fully_grounded()
    with pytest.raises(ClaimLayerError):
        assess_claim(proposal, registry, criteria_authority=block)
    with pytest.raises(ClaimLayerError):
        run_simulation(proposal, registry, criteria_authority=block)


def test_a4_a_genuine_block_for_another_claim_is_refused(registry) -> None:
    prose, proposal = _fully_grounded()
    block = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)["record"]["criteria_authority"]
    other = copy.deepcopy(proposal)
    other["target"]["value"]["magnitude"] = 309.75
    with pytest.raises(ClaimLayerError):
        assess_claim(other, registry, criteria_authority=block)


def test_a4_the_block_builder_itself_grants_nothing(registry) -> None:
    prose, proposal = _fully_grounded()
    forged = grounded_criteria("The temperature at probe must be 309.75 K ± 0.5 K.", prose.spans, {}, [])
    with pytest.raises(ClaimLayerError):
        assess_claim(proposal, registry, criteria_authority=forged)


# ---- A5 -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("policy_target", [373.15, 333.15])  # looser and stricter than the stated 353.15 K
def test_a5_a_policy_target_cannot_replace_the_users_stated_bound(registry, policy_target) -> None:
    prose, proposal = _et_with("The final temperature must stay below 353.15 kelvin.")
    policy_value = {**proposal["target"], "value": K(policy_target)}
    proposal["target"] = copy.deepcopy(policy_value)  # the model agrees with the policy: only the TEXT disagrees
    result = _compile(prose, proposal, registry, target=policy_value)
    _assert_fails_closed(result, "target")
    assert any("would replace" in finding for finding in result.findings), result.findings


def test_a5_a_policy_that_agrees_with_the_stated_comparison_accounts_for_it(registry) -> None:
    prose, proposal = _et_with("The final temperature must stay below 353.15 kelvin.")
    result = _compile(prose, proposal, registry, target=copy.deepcopy(proposal["target"]),
                      operator=proposal["operator"])
    assert result.status != UNGROUNDED, result.findings


def test_a5_a_policy_operator_cannot_flip_the_stated_one(registry) -> None:
    prose, proposal = _et_with("The final temperature must stay below 353.15 kelvin.")
    proposal["operator"] = ">"  # the model agrees with the policy: only the TEXT disagrees
    result = _compile(prose, proposal, registry, operator=">")
    _assert_fails_closed(result, "operator")
    assert any("would replace" in finding for finding in result.findings), result.findings


# ---- A6 / A7 --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", ["The tank volume must be at least 50 gallon.",
                                      "The payload mass must be at most 2 ton.",
                                      "The heater power must be below 3 hp.",
                                      "The bracket load must be at most 20 lb.",
                                      "The cable run must be at most 2 mile."])
def test_a6_an_ambiguous_unit_is_not_read_in_a_bound(sentence) -> None:
    with pytest.raises(Ungrounded, match="more than one standard definition"):
        read_comparison(sentence, (0, len(sentence)))


def test_a6_an_ambiguous_unit_is_not_read_in_an_input() -> None:
    with pytest.raises(Ungrounded, match="more than one standard definition"):
        _ground("The tank volume is 50 gallon.", "50 gallon", "tank.tank_volume", Quantity(50, "gallon").to_dict())


def test_a6_an_unambiguous_unit_still_reads() -> None:
    sentence = "The tank volume must be at least 50 liter."
    assert read_comparison(sentence, (0, len(sentence))).target == Quantity(50, "liter")


def test_a7_an_input_written_like_a_grouped_integer_is_not_read() -> None:
    mass = Quantity(1.2, "kilogram").to_dict()
    with pytest.raises(Ungrounded, match="grouped integer"):
        _ground("The cell mass is 1.200 kg.", "1.200 kg", "cell.cell_mass", mass)
    assert _ground("The cell mass is 1.2000 kg.", "1.2000 kg", "cell.cell_mass", mass) is not None


# ---- fifth review BLOCKER A/B: only a sentence ground_input READ accounts for an input ----------------------


@pytest.mark.parametrize("extra_missing", [[], ["stages[9].body.heat_capacity"]])
def test_fifth_review_a_sentence_no_input_read_never_makes_a_claim_ready(registry, extra_missing) -> None:
    prose, proposal = _faithful(et_claim())
    prose.say("heat_capacity is 77 J/K and that limit is waived during burn-in.")
    proposal["missing_inputs"] = sorted({*proposal.get("missing_inputs", []), *extra_missing})
    result = _compile(prose, proposal, registry)
    assert result.status == UNGROUNDED and result.compiled is None, (result.status, result.findings)
    assert any("waived during burn-in" in s for s in result.advisory["unread_sentences"])
    run = run_proposed_simulation(prose.text, proposal, prose.spans, registry, policy=prose.policy)
    assert run["record"] is None and run["view"] is None


def test_fifth_review_a_misread_input_is_listed_not_silently_dropped(registry) -> None:
    prose, proposal = _faithful(et_claim())
    proposal["known_inputs"]["stages[0].body.heat_capacity"]["magnitude"] = 77.0
    result = _compile(prose, proposal, registry)
    assert result.status == "needs_input"
    assert any("heat_capacity" in s for s in result.advisory["sentences_not_read"])

# ---- sixth review -------------------------------------------------------------------------------------------


def test_sixth_review_a_policy_bound_claim_reads_exactly_one_stated_comparison(registry) -> None:
    prose, proposal = _et_with("The final temperature must stay below 353.15 kelvin.")
    prose.say(("claim.comparison", "The final temperature must stay below 400 kelvin."))  # the model cites the looser
    proposal["target"] = {**proposal["target"], "value": K(400.0)}
    result = _compile(prose, proposal, registry, qoi=copy.deepcopy(proposal["qoi"]))
    assert result.status == UNGROUNDED and result.compiled is None, (result.status, result.findings)
    assert any("reads exactly one" in finding for finding in result.findings)


@pytest.mark.parametrize("value", ["A123 and that limit is waived during burn-in", "R1 unless cooled"])
def test_sixth_review_a_text_input_is_one_token(value) -> None:
    text = f"The cell id is {value}."
    with pytest.raises(Ungrounded):
        _ground(text, value, "cell.cell_id", value)
    assert _ground("The cell id is A123.", "A123", "cell.cell_id", "A123") is None  # a token still grounds