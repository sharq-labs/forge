"""Evidence gaps and next experiment -- evidence gaps that point at their records, and next experiments derived from declarations."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from claims_support import battery_inputs, claim, et_claim, et_inputs, t3_claim, t3_point
from engcore.claims import (
    AssessmentForgeryError,
    CapabilityRegistry,
    ClaimTarget,
    DecisionBinding,
    ExperimentAction,
    GapClass,
    InputDistribution,
    InputUncertainty,
    QuantityOfInterest,
    UncertaintyCapability,
    UncertaintyDemand,
    analyze_gaps,
    assess_claim,
    builtin_context,
    recommend_next,
    verify_assessment,
)
from engcore.mcp.capabilities import ELECTROTHERMAL_CAPABILITY_ID, production_registry
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel as C

K = "kelvin"


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _et_missing_heat_capacity():
    inputs = et_inputs()
    del inputs["stages[0].body.heat_capacity"]
    return et_claim(known_inputs=inputs)


def _unknown_applicability():
    inputs = et_inputs()
    # The conductor's temperature coefficient unlocks the material model's range condition when stated.
    optional = [k for k in inputs if k.endswith("conductor.reference_temperature")]
    for key in optional:
        del inputs[key]
    return et_claim(known_inputs=inputs)


SCENARIOS = {
    "t3_supported": lambda: t3_claim(),
    "et_supported": lambda: et_claim(),
    "et_contradicted": lambda: et_claim(target=ClaimTarget(value=Quantity(310.0, K))),
    "missing_input": _et_missing_heat_capacity,
    "unknown_input": lambda: et_claim(missing_inputs=frozenset({"source_voltage"}), known_inputs={k: v for k, v in et_inputs().items() if k != "source_voltage"}),
    "battery_unsupported": lambda: claim(qoi=QuantityOfInterest("final_temperature", K), operating_context={}, known_inputs=battery_inputs()),
    "t3_tight_band": lambda: t3_claim(uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL}), None, False), tolerance=Quantity(0.0002, K)),
    "t3_model_form": lambda: t3_claim(uncertainty=UncertaintyDemand(frozenset({C.MODEL_FORM}), None, False)),
    "t3_discrepancy": lambda: t3_claim(uncertainty=UncertaintyDemand(frozenset(), None, True)),
    "et_parameter_undeclared": lambda: et_claim(uncertainty=UncertaintyDemand(frozenset({C.EPISTEMIC_PARAMETER}), None, False)),
    "et_numerical": lambda: et_claim(uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL}), None, False)),
    "et_high_high": lambda: et_claim(decision_context=builtin_context("engineering_decision", influence="high", consequence="high", owner="o")),
    "t3_other_point": lambda: t3_claim(operating_context={**t3_point(), "conductivity": Quantity(40.0, "watt / meter / kelvin")}),
    "et_level_missing": lambda: et_claim(evidence=type(et_claim().evidence)((type(et_claim().evidence.required_levels[0]).EXPERIMENTALLY_VALIDATED,))),
}


@pytest.fixture(scope="module")
def records(registry):
    return {name: assess_claim(make(), registry).to_dict() for name, make in SCENARIOS.items()}


def _resolve(record, pointer):
    node = record
    for part in pointer.strip("/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


# ---------------------------------------------------------------------------
# Phase 5
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_verdict_is_fully_explained_by_its_blocking_gaps(records, name) -> None:
    record = records[name]
    analysis = analyze_gaps(record)
    assert analysis.complete, analysis.to_dict()
    blocking = analysis.blocking
    if record["verdict"] == "insufficient_evidence":
        assert blocking
    else:
        assert not blocking
    assert record["evidence_gaps"] == analysis.to_dict()


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_gap_points_at_the_record_field_that_caused_it(records, name) -> None:
    record = records[name]
    for gap in record["evidence_gaps"]["gaps"]:
        if gap["source"].startswith("/"):
            _resolve(record, gap["source"])  # raises if the pointer names nothing


@pytest.mark.parametrize(
    "name, kind",
    [
        ("missing_input", GapClass.MISSING_INPUT),
        ("unknown_input", GapClass.MISSING_INPUT),
        ("battery_unsupported", GapClass.CAPABILITY_MISSING),
        ("t3_tight_band", GapClass.UNCERTAINTY_BAND_STRADDLES),
        ("t3_model_form", GapClass.MODEL_FORM_UNCERTAINTY_UNKNOWN),
        ("t3_discrepancy", GapClass.MODEL_FORM_UNCERTAINTY_UNKNOWN),
        ("et_parameter_undeclared", GapClass.PARAMETER_UQ_MISSING),
        ("et_numerical", GapClass.NUMERICAL_UQ_MISSING),
        ("et_high_high", GapClass.EXTERNAL_EVIDENCE_MISSING),
        ("t3_other_point", GapClass.MODEL_OUTSIDE_DOMAIN),
        ("et_level_missing", GapClass.VALIDATION_LEVEL_MISSING),
    ],
)
def test_each_insufficiency_is_classified_by_its_cause(records, name, kind) -> None:
    analysis = analyze_gaps(records[name])
    assert analysis.of_kind(kind), [g.gap_id for g in analysis.gaps]


def test_a_contradicted_claim_has_no_blocking_gap(records) -> None:
    assert records["et_contradicted"]["verdict"] == "contradicted"
    assert not analyze_gaps(records["et_contradicted"]).blocking


def test_a_verdict_the_record_does_not_explain_is_reported_not_hidden(records) -> None:
    doctored = json.loads(json.dumps(records["t3_supported"]))
    doctored["verdict"] = "insufficient_evidence"
    analysis = analyze_gaps(doctored)
    assert not analysis.complete and analysis.of_kind(GapClass.UNEXPLAINED)


def test_a_record_whose_gaps_were_edited_is_refused(records, registry) -> None:
    edited = json.loads(json.dumps(records["et_numerical"]))
    edited["evidence_gaps"]["gaps"] = []
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(edited, registry)
    edited = json.loads(json.dumps(records["et_numerical"]))
    edited["next_experiments"]["recommendations"] = []
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(edited, registry)


# ---------------------------------------------------------------------------
# Phase 6
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_recommendations_address_real_gaps_and_promise_nothing(records, registry, name) -> None:
    record = records[name]
    plan = recommend_next(record, registry)
    gap_ids = {g["gap_id"] for g in record["evidence_gaps"]["gaps"]}
    for rec in plan.to_dict()["recommendations"]:
        assert rec["addresses_gaps"] and set(rec["addresses_gaps"]) <= gap_ids
        assert rec["guarantees_support"] is False
        if rec["executable_by_forge"]:
            assert rec["required_capability"] in registry
    assert plan.to_dict() == record["next_experiments"]
    assert recommend_next(record, registry).digest == plan.digest  # deterministic


@pytest.mark.parametrize(
    "name, action, forge",
    [
        ("missing_input", ExperimentAction.PROVIDE_INPUT, True),
        ("t3_tight_band", ExperimentAction.REFINE_DISCRETIZATION, True),
        ("et_parameter_undeclared", ExperimentAction.DECLARE_INPUT_DISTRIBUTIONS, True),
        ("t3_model_form", ExperimentAction.QUANTIFY_MODEL_FORM, False),
        ("et_numerical", ExperimentAction.EXTEND_CAPABILITY, False),
        ("et_high_high", ExperimentAction.DECLARE_INPUT_DISTRIBUTIONS, True),
        ("t3_other_point", ExperimentAction.MOVE_OPERATING_POINT, True),
    ],
)
def test_the_first_recommendation_is_the_smallest_declared_action(records, registry, name, action, forge) -> None:
    first = recommend_next(records[name], registry).first
    assert first.action is action and first.executable_by_forge is forge, first.to_dict()


def test_parameter_recommendations_name_only_declared_perturbable_inputs(records, registry) -> None:
    first = recommend_next(records["et_parameter_undeclared"], registry).first
    declared = {p.path for p in registry.get(ELECTROTHERMAL_CAPABILITY_ID).perturbable}
    from engcore.claims import declared_path

    assert all(declared_path(p) in declared for p in first.target.split(","))
    assert first.executions == 93


def test_without_a_declaration_nothing_is_recommended_as_executable(records, registry) -> None:
    stripped = CapabilityRegistry(
        replace(d, perturbable=(), uncertainty=UncertaintyCapability({}, "none")) if d.capability_id == ELECTROTHERMAL_CAPABILITY_ID else d
        for d in registry
    )
    record = assess_claim(SCENARIOS["et_parameter_undeclared"](), stripped).to_dict()
    first = recommend_next(record, stripped).first
    assert first.action is ExperimentAction.EXTEND_CAPABILITY and not first.executable_by_forge


# ---------------------------------------------------------------------------
# Closing the loop: doing the recommended thing closes the gap it named
# ---------------------------------------------------------------------------


def test_supplying_the_recommended_input_closes_the_gap(records, registry) -> None:
    first = recommend_next(records["missing_input"], registry).first
    inputs = dict(_et_missing_heat_capacity().known_inputs)
    inputs[first.target] = et_inputs()[first.target]
    after = assess_claim(et_claim(known_inputs=inputs), registry).to_dict()
    assert after["verdict"] == "supported"
    assert not any(g["gap_id"] in first.addresses_gaps for g in after["evidence_gaps"]["gaps"])


def test_declaring_the_recommended_distributions_closes_the_parameter_gap(records, registry) -> None:
    inputs = et_inputs()
    amb = inputs["stages[0].body.ambient_temperature"]
    spec = InputUncertainty((InputDistribution("stages[0].body.ambient_temperature", "normal", amb, Quantity(0.5, K), "sensor datasheet"),), 93)
    after = assess_claim(et_claim(uncertainty=UncertaintyDemand(frozenset({C.EPISTEMIC_PARAMETER}), None, False), input_uncertainty=spec), registry).to_dict()
    assert after["verdict"] == "supported"
    assert not analyze_gaps(after).of_kind(GapClass.PARAMETER_UQ_MISSING)


def test_refining_as_recommended_narrows_the_band_but_is_not_promised_to_decide(records, registry) -> None:
    before = records["t3_tight_band"]
    first = recommend_next(before, registry).first
    assert first.action is ExperimentAction.REFINE_DISCRETIZATION
    finer = t3_claim(
        uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL}), None, False), tolerance=Quantity(0.0002, K),
        known_inputs={"numerics.n_cells": 320, "numerics.n_steps": 1280},
    )
    after = assess_claim(finer, registry).to_dict()
    width = lambda r: r["comparison"]["band_upper"]["magnitude"] - r["comparison"]["band_lower"]["magnitude"]
    assert width(after) < width(before)
    # The finer ladder resolves the band -- against the claim: the refined solution lies outside the 0.2 mK
    # tolerance over the whole band. An experiment addresses a gap; it never promises support.
    assert after["comparison"]["outcome"] == "violated" and after["verdict"] == "contradicted"
