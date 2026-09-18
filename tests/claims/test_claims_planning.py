"""CORE-5: the experiment plan -- deterministic, digestible, bound, and never executed."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from claims_support import et_claim, et_inputs, t3_claim
from engcore.claims import (
    CapabilityRegistry,
    CompilationStatus,
    DecisionBinding,
    EvidenceRequirement,
    ExperimentPlan,
    PlanningError,
    QuantityOfInterest,
    RequestedOutput,
    StepAvailability,
    StepKind,
    UncertaintyDemand,
    compile_claim,
    plan_experiment,
    verify_plan,
)
from engcore.mcp.capabilities import production_registry
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import DiscrepancyKind, ModelDiscrepancy, UncertaintyChannel


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def plan_for(made, registry):
    compiled = compile_claim(made, registry)
    assert compiled.status is CompilationStatus.READY, compiled.reasons
    return plan_experiment(compiled, registry)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_the_same_request_always_yields_the_same_plan(registry) -> None:
    a = plan_for(t3_claim(), registry)
    b = plan_for(t3_claim(), registry)
    assert a.digest == b.digest and a.to_dict() == b.to_dict() and a.run_id == b.run_id


def test_ids_prose_and_output_format_do_not_change_the_plan(registry) -> None:
    base = plan_for(t3_claim(), registry)
    other = plan_for(
        t3_claim(claim_id="another", statement="Reworded entirely.", requested_outputs=frozenset(RequestedOutput)),
        registry,
    )
    assert other.digest == base.digest
    assert other.charter_digest == base.charter_digest


@pytest.mark.parametrize(
    "change",
    [
        {"known_inputs": {**et_inputs(), "stages[0].body.heat_capacity": Quantity(51.0, "joule / kelvin")}},
        {"decision": DecisionBinding("d-1", "A different intended use.")},
        {"evidence": EvidenceRequirement((ValidationLevel.ANALYTICALLY_VERIFIED, ValidationLevel.DIMENSIONALLY_VALID))},
        {"discrepancy": ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED, rationale="assumed")},
        {"uncertainty": UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), 2.0, False)},
        {"target": replace(et_claim().target, value=Quantity(350.0, "kelvin"))},
    ],
    ids=["input", "decision", "levels", "discrepancy", "uncertainty", "target"],
)
def test_a_relevant_change_yields_a_different_plan_and_charter(registry, change) -> None:
    base = plan_for(et_claim(), registry)
    changed = plan_for(et_claim(**change), registry)
    assert changed.digest != base.digest
    assert changed.charter_digest != base.charter_digest
    assert changed.context_ref != base.context_ref


def test_numerics_are_part_of_what_is_run(registry) -> None:
    base = plan_for(t3_claim(), registry)
    finer = plan_for(t3_claim(known_inputs={"numerics.n_cells": 320}), registry)
    assert finer.digest != base.digest
    assert finer.case["numerics"] == {"n_cells": 320}
    assert "numerics.n_cells" not in finer.content["system_defaulted_numerics"]
    assert base.content["system_defaulted_numerics"] == ["numerics.n_cells", "numerics.n_steps"]


def test_an_unrelated_capability_changing_does_not_change_the_plan(registry) -> None:
    changed = CapabilityRegistry(
        replace(d, version="2") if d.capability_id == "system.battery" else d for d in registry
    )
    assert changed.digest != registry.digest
    assert plan_for(et_claim(), changed).digest == plan_for(et_claim(), registry).digest


def test_the_selected_capability_version_is_bound(registry) -> None:
    changed = CapabilityRegistry(
        replace(d, version="2") if d.capability_id == "system.electrothermal" else d for d in registry
    )
    assert plan_for(et_claim(), changed).digest != plan_for(et_claim(), registry).digest


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


def test_the_plan_names_models_versions_case_routes_and_decision(registry) -> None:
    plan = plan_for(et_claim(), registry)
    content = plan.content
    assert content["capability"]["capability_id"] == "system.electrothermal"
    models = {(m["model_id"], m["version"], m["instance"]) for m in content["models"]}
    assert ("thermal.lumped.first_order_capacity", "0.1.0", "stages[0]") in models
    assert content["case"]["stages"][0]["component_id"] == "R1"
    assert content["qoi"]["instance"] == "R1"
    assert plan.context_ref == f"charter:{plan.charter.digest}#decision:d-1"
    assert dict(plan.charter.metadata)["claim_identity"] == et_claim().identity_digest


def test_the_step_graph_orders_execution_before_evidence_before_decision(registry) -> None:
    plan = plan_for(et_claim(), registry)
    order = plan.order
    assert order[0].startswith("execute:")
    assert order[-3:] == ("assemble_evidence", "assure", "compare")
    validity = plan.steps_of(StepKind.ASSESS_VALIDITY)
    assert {s.subject for s in validity} >= {"thermal.lumped.first_order_capacity", "electrical.dc.kcl"}
    for step in plan.steps:
        for dependency in step.depends_on:
            assert order.index(dependency) < order.index(step.step_id)


def test_unattainable_evidence_and_uncertainty_work_are_planned_as_unavailable(registry) -> None:
    plan = plan_for(
        et_claim(
            evidence=EvidenceRequirement((ValidationLevel.EXPERIMENTALLY_VALIDATED,)),
            uncertainty=UncertaintyDemand(frozenset({UncertaintyChannel.MODEL_FORM}), 2.0, False),
        ),
        registry,
    )
    unavailable = {s.step_id for s in plan.unavailable_steps}
    assert {"check:experimentally_validated", "uncertainty:model_form"} <= unavailable
    assert plan.step("check:experimentally_validated").detail["is_validation"] is True


def test_the_t3_plan_requires_the_trusted_oracle_comparison(registry) -> None:
    plan = plan_for(t3_claim(), registry)
    (oracle,) = plan.steps_of(StepKind.ORACLE_COMPARISON)
    assert oracle.availability is StepAvailability.PLANNED
    assert oracle.detail["could_establish"] == "benchmark_validated" and oracle.detail["is_validation"] is True
    (check,) = plan.steps_of(StepKind.VALIDATION_CHECK)
    assert check.detail["check_name"] == "nafems_t3_external_benchmark"


def test_a_per_element_plan_binds_the_element(registry) -> None:
    inputs = et_inputs()
    for key, value in list(inputs.items()):
        if key.startswith("stages[0]."):
            inputs[key.replace("stages[0].", "stages[1].")] = value
    inputs["stages[1].component_id"] = "R2"
    plan = plan_for(et_claim(known_inputs=inputs, qoi=QuantityOfInterest("final_temperature", "kelvin", {"component_id": "R2"})), registry)
    assert plan.instance == "R2"
    lumped = [s for s in plan.steps_of(StepKind.ASSESS_VALIDITY) if s.subject == "thermal.lumped.first_order_capacity"]
    assert sorted(s.detail["instance"] for s in lumped) == ["stages[0]", "stages[1]"]


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_only_a_ready_claim_can_be_planned(registry) -> None:
    inputs = et_inputs()
    del inputs["stages[0].body.heat_capacity"]
    compiled = compile_claim(et_claim(known_inputs=inputs), registry)
    with pytest.raises(PlanningError, match="needs_input"):
        plan_experiment(compiled, registry)


def test_a_claim_compiled_against_another_registry_is_refused(registry) -> None:
    compiled = compile_claim(et_claim(), registry)
    other = CapabilityRegistry(replace(d, version="2") if d.capability_id == "system.battery" else d for d in registry)
    with pytest.raises(PlanningError, match="another registry"):
        plan_experiment(compiled, other)


def test_planning_never_executes(registry, monkeypatch) -> None:
    import engcore.mcp.problem as problem
    import engcore.mcp.nafems_t3 as t3

    def refuse(*_, **__):  # pragma: no cover - reaching it is the failure
        raise AssertionError("planning executed physics")

    monkeypatch.setattr(problem, "run_electrothermal_case", refuse)
    monkeypatch.setattr(t3, "run_nafems_t3_credibility", refuse)
    plan_for(et_claim(), registry)
    plan_for(t3_claim(), registry)


# ---------------------------------------------------------------------------
# Read-back and forgery
# ---------------------------------------------------------------------------


def test_a_plan_round_trips_and_verifies_against_a_fresh_replan(registry) -> None:
    plan = plan_for(et_claim(), registry)
    back = ExperimentPlan.from_dict(json.loads(json.dumps(plan.to_dict())))
    assert back.digest == plan.digest
    verify_plan(back, compile_claim(et_claim(), registry), registry)


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda w: w["content"]["case"].__setitem__("source_voltage", "50.0 volt"), "core digest"),
        (lambda w: w["content"]["models"][0].__setitem__("version", "9.9.9"), "core digest"),
        (lambda w: w["content"]["qoi"].__setitem__("instance", "R9"), "core digest"),
        (lambda w: w["content"]["comparison"]["target"].__setitem__("magnitude", 999.0), "core digest"),
        (lambda w: w["content"].__setitem__("run_id", "claim-0000000000000000"), "run_id"),
        (lambda w: w["content"]["decision"].__setitem__("statement", "a different use"), "terminal decision"),
        (lambda w: w["content"]["evidence_requirements"].__setitem__("required_levels", ["dimensionally_valid"]), "required levels"),
        (lambda w: w["content"]["evidence_requirements"]["discrepancy"].__setitem__("kind", "zero_declared"), "discrepancy"),
        (lambda w: w["charter"]["metadata"].__setitem__("plan_core", "0" * 64), "another plan"),
        (lambda w: w["steps"][0]["detail"].__setitem__("injected", True), "core digest"),
        (lambda w: w.__setitem__("order", list(reversed(w["order"]))), "execution order"),
        (lambda w: w.__setitem__("verdict", "supported"), "unknown field"),
    ],
    ids=["case", "model_version", "instance", "target", "run_id", "decision", "levels", "discrepancy", "charter", "step", "order", "extra"],
)
def test_an_edited_plan_is_refused_on_read(registry, mutate, fragment) -> None:
    wire = copy.deepcopy(plan_for(et_claim(), registry).to_dict())
    mutate(wire)
    with pytest.raises(PlanningError, match=fragment):
        ExperimentPlan.from_dict(wire)


def test_a_plan_for_one_claim_cannot_stand_for_another(registry) -> None:
    plan = plan_for(et_claim(), registry)
    other = compile_claim(et_claim(target=replace(et_claim().target, value=Quantity(340.0, "kelvin"))), registry)
    with pytest.raises(PlanningError, match="not the plan this claim produces"):
        verify_plan(plan, other, registry)
