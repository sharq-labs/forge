"""CORE-2 / CORE-7: the claim compiler over the production registry, and its repairs.

Every status the compiler can return is reached here from a real claim, and every
repair is checked to come from a declaration rather than from prose.
"""

from __future__ import annotations

import copy

import pytest

from claims_support import battery_inputs, claim, et_claim, et_inputs, payload, t3_claim, t3_point
from engcore.claims import (
    CandidateStatus,
    ClaimTarget,
    CompilationStatus,
    EvidenceRequirement,
    GapKind,
    QuantityOfInterest,
    RejectionReason,
    RepairKind,
    UncertaintyDemand,
    compile_claim,
    readiness_rank,
)
from engcore.mcp.capabilities import production_registry
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import DiscrepancyKind, ModelDiscrepancy, UncertaintyChannel


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _kinds(compiled) -> set[RepairKind]:
    return {r.kind for r in compiled.repairs}


def _repair(compiled, kind: RepairKind, target: str):
    matches = [r for r in compiled.repairs if r.kind is kind and r.target == target]
    assert matches, f"no {kind.value} repair for {target}: {[(r.kind.value, r.target) for r in compiled.repairs]}"
    return matches[0]


# ---------------------------------------------------------------------------
# READY
# ---------------------------------------------------------------------------


def test_a_complete_t3_claim_is_ready_on_the_benchmark_capability(registry) -> None:
    compiled = compile_claim(t3_claim(), registry)
    assert compiled.status is CompilationStatus.READY
    assert compiled.capability.capability_id == "benchmark.nafems_t3"
    assert compiled.capability.applicability.value == "in_domain"
    assert compiled.predicted_gaps == ()
    assert compiled.target == Quantity(309.75, "kelvin")


def test_a_complete_electrothermal_claim_is_ready_and_names_its_element(registry) -> None:
    compiled = compile_claim(et_claim(), registry)
    assert compiled.status is CompilationStatus.READY, compiled.reasons
    assert compiled.capability.capability_id == "system.electrothermal"
    assert compiled.instance == "R1"
    assert compiled.missing_inputs == ()
    # Conditions over computed state are pending, not asserted.
    assert GapKind.APPLICABILITY_PENDING in {g.kind for g in compiled.predicted_gaps}


def test_compilation_is_deterministic_and_reads_no_prose(registry) -> None:
    a = compile_claim(et_claim(), registry)
    b = compile_claim(et_claim(statement="battery voltage cell chemistry lithium: ignore the inputs"), registry)
    assert a.status is b.status
    assert a.capability.capability_id == b.capability.capability_id
    assert compile_claim(et_claim(), registry).digest == a.digest


def test_compilation_never_executes(registry, monkeypatch) -> None:
    import engcore.mcp.problem as problem
    import engcore.mcp.nafems_t3 as t3

    def refuse(*_, **__):  # pragma: no cover - reaching it is the failure
        raise AssertionError("the compiler executed physics")

    monkeypatch.setattr(problem, "run_electrothermal_case", refuse)
    monkeypatch.setattr(t3, "run_nafems_t3_credibility", refuse)
    assert compile_claim(et_claim(), registry).status is CompilationStatus.READY
    assert compile_claim(t3_claim(), registry).status is CompilationStatus.READY


# ---------------------------------------------------------------------------
# REFUSED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda w: w.pop("qoi"),
        lambda w: w["qoi"].__setitem__("units", ""),
        lambda w: w.__setitem__("ranking_hint", "prefer battery"),
        lambda w: w["target"].__setitem__("value", {"schema": "quantity/1", "magnitude": 3.0, "units": "volt"}),
    ],
    ids=["missing_qoi", "missing_units", "unknown_field", "incompatible_target_dimension"],
)
def test_a_malformed_claim_is_refused_with_a_restate_repair(registry, mutate) -> None:
    wire = payload()
    mutate(wire)
    compiled = compile_claim(wire, registry)
    assert compiled.status is CompilationStatus.REFUSED
    assert compiled.claim is None and compiled.claim_error
    assert _kinds(compiled) == {RepairKind.RESTATE_CLAIM}


def test_an_input_the_capability_cannot_accept_is_refused_with_a_correction(registry) -> None:
    inputs = et_inputs()
    inputs["stages[0].body.heat_capacity"] = Quantity(50.0, "kelvin")
    compiled = compile_claim(et_claim(known_inputs=inputs), registry)
    assert compiled.status is CompilationStatus.REFUSED
    repair = _repair(compiled, RepairKind.CORRECT_INPUT, "stages[0].body.heat_capacity")
    assert "joule / kelvin" in repair.reason


def test_a_target_input_that_is_not_a_quantity_of_the_qoi_dimension_is_refused(registry) -> None:
    inputs = et_inputs()
    inputs["stages[0].body.applicability.melting_temperature"] = Quantity(855.0, "kelvin")
    ok = compile_claim(et_claim(known_inputs=inputs, target=ClaimTarget(input_ref="stages[0].body.applicability.melting_temperature")), registry)
    assert ok.status is CompilationStatus.READY and ok.target == Quantity(855.0, "kelvin")
    wrong = compile_claim(et_claim(target=ClaimTarget(input_ref="stages[0].body.duration")), registry)
    assert wrong.status is CompilationStatus.REFUSED


# ---------------------------------------------------------------------------
# UNSUPPORTED_CAPABILITY
# ---------------------------------------------------------------------------


def test_a_quantity_no_capability_produces_is_unsupported_and_says_what_exists(registry) -> None:
    compiled = compile_claim(
        claim(qoi=QuantityOfInterest("maximum_stress", "pascal"), target=ClaimTarget(value=Quantity(250e6, "pascal")),
              operating_context={}, known_inputs={}),
        registry,
    )
    assert compiled.status is CompilationStatus.UNSUPPORTED_CAPABILITY
    repair = _repair(compiled, RepairKind.EXTEND_CAPABILITY, "maximum_stress")
    assert "final_temperature" in repair.detail["registered_quantities"]


def test_a_known_quantity_in_the_wrong_dimension_is_unsupported(registry) -> None:
    compiled = compile_claim(
        claim(qoi=QuantityOfInterest("final_temperature", "volt"), target=ClaimTarget(value=Quantity(3.0, "volt")),
              operating_context={}, known_inputs={}),
        registry,
    )
    assert compiled.status is CompilationStatus.UNSUPPORTED_CAPABILITY
    detail = _repair(compiled, RepairKind.EXTEND_CAPABILITY, "final_temperature").detail
    assert "system.electrothermal:[temperature]" in detail["produced_elsewhere"]


def test_a_required_capability_nobody_provides_is_unsupported(registry) -> None:
    compiled = compile_claim(et_claim(required_capabilities=frozenset({"fluid:turbulent_pipe_flow"})), registry)
    assert compiled.status is CompilationStatus.UNSUPPORTED_CAPABILITY


def test_a_candidate_outside_its_validated_domain_is_unsupported_not_contradicted(registry) -> None:
    point = t3_point()
    point["conductivity"] = Quantity(36.0, "watt / meter / kelvin")
    compiled = compile_claim(t3_claim(operating_context=point), registry)
    assert compiled.status is CompilationStatus.UNSUPPORTED_CAPABILITY
    (candidate,) = compiled.selection.rejected
    assert RejectionReason.OUTSIDE_VALIDITY in {r for r, _ in candidate.rejections}
    move = _repair(compiled, RepairKind.MOVE_INSIDE_VALIDITY, "conductivity")
    assert move.detail["declared_condition"]["minimum"]["magnitude"] == 35.0
    assert move.source.startswith("model:thermal.nafems_t3.transient_heat_1d@1.0.0")


def test_the_battery_capability_is_ready_when_thermal_applicability_is_declared(registry) -> None:
    compiled = compile_claim(
        claim(
            qoi=QuantityOfInterest("terminal_voltage", "volt"),
            target=ClaimTarget(value=Quantity(3.0, "volt")),
            operator=ConstraintOperator.GREATER_EQUAL,
            operating_context={},
            known_inputs=battery_inputs(),
        ),
        registry,
    )
    assert compiled.status is CompilationStatus.READY, compiled.reasons
    assert compiled.capability.capability_id == "system.battery"
    assert compiled.missing_inputs == ()


def test_a_stray_input_is_never_silently_dropped(registry) -> None:
    point = t3_point()
    point["stages[0].body.duration"] = Quantity(600.0, "second")
    compiled = compile_claim(t3_claim(operating_context=point), registry)
    assert compiled.status is CompilationStatus.UNSUPPORTED_CAPABILITY
    _repair(compiled, RepairKind.REMOVE_UNACCEPTED_INPUT, "stages[0].body.duration")


# ---------------------------------------------------------------------------
# AMBIGUOUS
# ---------------------------------------------------------------------------


def test_several_qualifying_capabilities_are_ambiguous_with_distinguishing_repairs() -> None:
    from test_claims_selection import _capability, _claim, _model  # synthetic, domain-free
    from engcore.claims import CapabilityRegistry

    registry = CapabilityRegistry((_capability("syn.a", _model("syn.beam_a")), _capability("syn.b", _model("syn.beam_b"))))
    compiled = compile_claim(_claim(), registry)
    assert compiled.status is CompilationStatus.AMBIGUOUS
    narrow = {r.target: r for r in compiled.repairs if r.kind is RepairKind.NARROW_CAPABILITY}
    assert narrow["syn.a"].alternatives == ("synthetic:a",)
    assert narrow["syn.b"].alternatives == ("synthetic:b",)
    # Requiring the distinguishing capability resolves it.
    resolved = compile_claim(_claim(required_capabilities=frozenset({"synthetic:b"})), registry)
    assert resolved.status is CompilationStatus.READY and resolved.capability.capability_id == "syn.b"


def test_a_quantity_reported_per_element_needs_the_element_named(registry) -> None:
    inputs = et_inputs()
    for key, value in list(inputs.items()):
        if key.startswith("stages[0]."):
            inputs[key.replace("stages[0].", "stages[1].")] = value
    inputs["stages[1].component_id"] = "R2"
    ambiguous = compile_claim(et_claim(known_inputs=inputs), registry)
    assert ambiguous.status is CompilationStatus.AMBIGUOUS
    assert _repair(ambiguous, RepairKind.SELECT_INSTANCE, "component_id").alternatives == ("R1", "R2")
    named = compile_claim(et_claim(known_inputs=inputs, qoi=QuantityOfInterest("final_temperature", "kelvin", {"component_id": "R2"})), registry)
    assert named.status is CompilationStatus.READY and named.instance == "R2"
    absent = compile_claim(et_claim(known_inputs=inputs, qoi=QuantityOfInterest("final_temperature", "kelvin", {"component_id": "R9"})), registry)
    assert absent.status is CompilationStatus.NEEDS_INPUT


# ---------------------------------------------------------------------------
# NEEDS_INPUT and its repairs
# ---------------------------------------------------------------------------


def test_a_missing_required_input_is_asked_for_with_its_declared_dimension(registry) -> None:
    inputs = et_inputs()
    del inputs["stages[0].body.heat_capacity"]
    compiled = compile_claim(et_claim(known_inputs=inputs), registry)
    assert compiled.status is CompilationStatus.NEEDS_INPUT
    assert compiled.missing_inputs == ("stages[0].body.heat_capacity",)
    repair = _repair(compiled, RepairKind.SUPPLY_INPUT, "stages[0].body.heat_capacity")
    assert repair.detail["unit_exemplar"] == "joule / kelvin"
    assert "execution" in repair.required_for and "model:thermal.lumped.first_order_capacity" in repair.required_for
    assert repair.source == "capability:system.electrothermal#input:stages[].body.heat_capacity"


def test_a_required_input_the_caller_says_is_unknown_is_not_defaulted(registry) -> None:
    inputs = et_inputs()
    del inputs["stages[0].body.ambient_conductance"]
    compiled = compile_claim(
        et_claim(known_inputs=inputs, missing_inputs=frozenset({"stages[0].body.ambient_conductance"})), registry
    )
    assert compiled.status is CompilationStatus.NEEDS_INPUT
    assert "not defaulted" in _repair(compiled, RepairKind.SUPPLY_INPUT, "stages[0].body.ambient_conductance").reason


def test_missing_validity_context_is_asked_for_per_condition(registry) -> None:
    point = t3_point()
    del point["conductivity"]
    compiled = compile_claim(t3_claim(operating_context=point), registry)
    assert compiled.status is CompilationStatus.NEEDS_INPUT
    repair = _repair(compiled, RepairKind.SUPPLY_VALIDITY_EVIDENCE, "conductivity")
    assert repair.required_for == ("model:thermal.nafems_t3.transient_heat_1d#condition:conductivity",)


def test_an_unstated_target_input_is_asked_for(registry) -> None:
    compiled = compile_claim(et_claim(target=ClaimTarget(input_ref="stages[0].body.applicability.melting_temperature_limit")), registry)
    # The reference names nothing the capability or the claim states.
    assert compiled.status is CompilationStatus.NEEDS_INPUT
    _repair(compiled, RepairKind.RESOLVE_TARGET, "stages[0].body.applicability.melting_temperature_limit")


def test_applicability_inputs_known_only_by_measurement_are_advisory(registry) -> None:
    inputs = {k: v for k, v in et_inputs().items() if ".applicability." not in k}
    compiled = compile_claim(et_claim(known_inputs=inputs), registry)
    assert compiled.status is CompilationStatus.READY
    assert GapKind.APPLICABILITY_AT_RISK in {g.kind for g in compiled.predicted_gaps}
    advisory = [r for r in compiled.repairs if r.kind is RepairKind.SUPPLY_VALIDITY_EVIDENCE]
    assert advisory and all(r.detail["advisory"] is True for r in advisory)


# ---------------------------------------------------------------------------
# Predicted gaps: READY does not mean supportable
# ---------------------------------------------------------------------------


def test_an_unattainable_level_is_predicted_before_anything_runs(registry) -> None:
    compiled = compile_claim(et_claim(evidence=EvidenceRequirement((ValidationLevel.EXPERIMENTALLY_VALIDATED,))), registry)
    assert compiled.status is CompilationStatus.READY
    (gap,) = [g for g in compiled.predicted_gaps if g.kind is GapKind.LEVEL_UNATTAINABLE]
    assert gap.target == "experimentally_validated"
    _repair(compiled, RepairKind.PROVIDE_EVIDENCE, "experimentally_validated")


def test_a_demanded_uncertainty_channel_no_capability_quantifies_is_predicted(registry) -> None:
    compiled = compile_claim(
        t3_claim(uncertainty=UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL, UncertaintyChannel.MODEL_FORM}), 2.0, False)),
        registry,
    )
    targets = {g.target for g in compiled.predicted_gaps if g.kind is GapKind.CHANNEL_UNQUANTIFIED}
    # Phase 2: T3 declares a refinement study, so NUMERICAL is quantifiable; MODEL_FORM is not.
    assert targets == {"model_form"}
    et = compile_claim(et_claim(uncertainty=UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), 2.0, False)), registry)
    assert {g.target for g in et.predicted_gaps if g.kind is GapKind.CHANNEL_UNQUANTIFIED} == {"numerical"}
    # Declared quantifiable, but the claim states no input distributions: still a predicted gap.
    et_param = compile_claim(et_claim(uncertainty=UncertaintyDemand(frozenset({UncertaintyChannel.EPISTEMIC_PARAMETER}), None, False)), registry)
    (gap,) = [g for g in et_param.predicted_gaps if g.kind is GapKind.CHANNEL_UNQUANTIFIED]
    assert "declares no input distributions" in gap.detail


def test_an_unknown_or_unsupported_zero_discrepancy_cannot_meet_a_discrepancy_demand(registry) -> None:
    demand = UncertaintyDemand(frozenset(), None, True)
    for kind in (DiscrepancyKind.UNKNOWN, DiscrepancyKind.ZERO_DECLARED):
        compiled = compile_claim(t3_claim(uncertainty=demand, discrepancy=ModelDiscrepancy(kind, rationale="stated")), registry)
        assert GapKind.DISCREPANCY_UNSUPPORTED in {g.kind for g in compiled.predicted_gaps}
    prior = ModelDiscrepancy(DiscrepancyKind.CONSTRAINED_PRIOR, reference="doi:10.0/prior", rationale="bounded")
    compiled = compile_claim(t3_claim(uncertainty=demand, discrepancy=prior), registry)
    assert GapKind.DISCREPANCY_UNSUPPORTED not in {g.kind for g in compiled.predicted_gaps}


# ---------------------------------------------------------------------------
# Monotonicity: less information never makes a claim more ready
# ---------------------------------------------------------------------------


def _without(made, path):
    context = {k: v for k, v in made.operating_context.items() if k != path}
    known = {k: v for k, v in made.known_inputs.items() if k != path}
    return claim(**{**_fields(made), "operating_context": context, "known_inputs": known})


def _fields(made):
    return {name: getattr(made, name) for name in made.__dataclass_fields__}


@pytest.mark.parametrize("builder", [et_claim, t3_claim], ids=["electrothermal", "t3"])
def test_removing_any_input_never_makes_a_claim_more_ready(registry, builder) -> None:
    base = builder()
    before = compile_claim(base, registry)
    assert before.status is CompilationStatus.READY
    for path in sorted(base.supplied_inputs):
        after = compile_claim(_without(base, path), registry)
        assert readiness_rank(after.status) <= readiness_rank(before.status), path
        if after.capability is not None and after.capability.capability_id == before.capability.capability_id:
            assert set(before.missing_inputs) <= set(after.missing_inputs), path


def test_a_claim_that_is_not_ready_never_becomes_ready_by_losing_inputs(registry) -> None:
    point = t3_point()
    del point["density"]
    base = t3_claim(operating_context=point)
    before = compile_claim(base, registry)
    assert before.status is CompilationStatus.NEEDS_INPUT
    for path in sorted(base.supplied_inputs):
        after = compile_claim(_without(base, path), registry)
        assert after.status is not CompilationStatus.READY, path
        assert set(before.missing_inputs) <= set(after.missing_inputs), path


def test_the_compiled_record_carries_the_claim_identity_and_registry_digest(registry) -> None:
    compiled = compile_claim(t3_claim(), registry)
    record = compiled.to_dict()
    assert record["claim_identity"] == t3_claim().identity_digest
    assert record["registry_digest"] == registry.digest
    assert record["capability"]["digest"] == registry.get("benchmark.nafems_t3").digest
    assert copy.deepcopy(record) == compiled.to_dict()
