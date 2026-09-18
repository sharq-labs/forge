"""CORE-3: the production capability declarations tell the truth about their systems.

Every hand-written fact in ``engcore.mcp.capabilities`` is checked here against
a real run or a real record, so a declaration that drifts from its system fails
instead of routing claims to a capability that no longer does what it says.
"""

from __future__ import annotations

import copy

import pytest

from engcore.claims import (
    CapabilityExecutionRefused,
    ClaimKind,
    InputRole,
    RouteKind,
    build_case,
)
from engcore.mcp import describe_electrothermal_case, example_electrothermal_payload, run_electrothermal_case
from engcore.mcp.battery import describe_battery_case, example_battery_payload, run_battery_case
from engcore.mcp.capabilities import (
    BATTERY_CAPABILITY_ID,
    ELECTROTHERMAL_CAPABILITY_ID,
    NAFEMS_T3_CAPABILITY_ID,
    battery_capability,
    electrothermal_capability,
    nafems_t3_capability,
    production_registry,
)
from engcore.mcp.errors import MissingFieldError
from engcore.mcp.evidence import CredibilityVerdict
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity, dimensionality


@pytest.fixture(scope="module")
def registry():
    return production_registry()


@pytest.fixture(scope="module")
def et_report():
    return run_electrothermal_case(example_electrothermal_payload()).reports[0]


@pytest.fixture(scope="module")
def battery_report():
    return run_battery_case(example_battery_payload()).report


def _active_models(report) -> set[str]:
    return {record.model_id for record in report.validity}


def _predicted_active(declaration, case_paths) -> set[str]:
    return {
        model.model_id
        for model in declaration.models
        if model.always_active
        or any(path == prefix or path.startswith(prefix + ".") for prefix in model.activation for path in case_paths)
    }


def _paths(node, prefix=""):
    if isinstance(node, dict):
        for key, child in node.items():
            yield from _paths(child, f"{prefix}.{key}" if prefix else key)
    elif isinstance(node, list):
        for child in node:
            yield from _paths(child, f"{prefix}[]")
    else:
        yield prefix


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


def test_the_production_registry_is_built_once_and_is_deterministic(registry) -> None:
    assert production_registry() is registry
    assert [d.capability_id for d in registry] == [NAFEMS_T3_CAPABILITY_ID, BATTERY_CAPABILITY_ID, ELECTROTHERMAL_CAPABILITY_ID]
    # A second, independent build declares the same facts.
    assert electrothermal_capability().digest == registry.get(ELECTROTHERMAL_CAPABILITY_ID).digest
    assert battery_capability().digest == registry.get(BATTERY_CAPABILITY_ID).digest
    assert nafems_t3_capability().digest == registry.get(NAFEMS_T3_CAPABILITY_ID).digest


def test_every_production_declaration_is_executable_and_decides_both_claim_shapes(registry) -> None:
    for declaration in registry:
        assert declaration.executable
        assert declaration.claim_shapes == frozenset(ClaimKind)


# ---------------------------------------------------------------------------
# Inputs are the case descriptions, not a copy of them
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "capability_id, describe",
    [(ELECTROTHERMAL_CAPABILITY_ID, describe_electrothermal_case), (BATTERY_CAPABILITY_ID, describe_battery_case)],
)
def test_inputs_are_derived_field_for_field_from_the_case_description(registry, capability_id, describe) -> None:
    declaration = registry.get(capability_id)
    fields = {f.path: f for f in describe().fields}
    assert {i.path for i in declaration.inputs} == set(fields)
    for item in declaration.inputs:
        field = fields[item.path]
        assert item.kind.value == field.kind
        assert item.model_id == field.model_id and item.model_input == field.model_input
        assert item.unlocks_conditions == tuple(sorted(set(field.unlocks)))
        if field.kind == "quantity":
            assert item.dimension == field.dimension == dimensionality(field.unit_exemplar)
        if item.path != "cell.limits.cell_thermal_conductance":
            assert item.required == field.required


def test_the_one_requiredness_correction_is_what_the_battery_run_enforces(registry) -> None:
    item = registry.get(BATTERY_CAPABILITY_ID).input("cell.limits.cell_thermal_conductance")
    assert item.required is True
    assert "REQUIRED by the run" in item.description
    case = example_battery_payload()
    del case["cell"]["limits"]["cell_thermal_conductance"]
    with pytest.raises(MissingFieldError, match="cell_thermal_conductance"):
        run_battery_case(case)


def test_roles_classify_initial_and_boundary_conditions_explicitly(registry) -> None:
    et = registry.get(ELECTROTHERMAL_CAPABILITY_ID)
    assert et.input("stages[0].body.initial_temperature").role is InputRole.INITIAL_CONDITION
    assert et.input("stages[0].body.ambient_temperature").role is InputRole.BOUNDARY_CONDITION
    assert et.input("stages[0].body.applicability.biot_number") is None
    assert et.input("stages[0].body.applicability.surface_area").role is InputRole.APPLICABILITY
    assert et.input("coupling.tolerance").role is InputRole.NUMERICS
    battery = registry.get(BATTERY_CAPABILITY_ID)
    assert battery.input("load.state_of_charge").role is InputRole.INITIAL_CONDITION
    assert battery.input("thermal.ambient_temperature").role is InputRole.BOUNDARY_CONDITION
    assert battery.input("march.steps").role is InputRole.NUMERICS


@pytest.mark.parametrize(
    "capability_id, example",
    [(ELECTROTHERMAL_CAPABILITY_ID, example_electrothermal_payload), (BATTERY_CAPABILITY_ID, example_battery_payload)],
)
def test_every_path_of_the_example_case_is_a_declared_input(registry, capability_id, example) -> None:
    declared = {i.path for i in registry.get(capability_id).inputs}
    assert set(_paths(example())) <= declared


# ---------------------------------------------------------------------------
# Outputs, models, levels: pinned against real runs
# ---------------------------------------------------------------------------


def test_produced_quantities_are_what_the_reports_carry(registry, et_report, battery_report) -> None:
    for capability_id, report in ((ELECTROTHERMAL_CAPABILITY_ID, et_report), (BATTERY_CAPABILITY_ID, battery_report)):
        declaration = registry.get(capability_id)
        assert {q.name for q in declaration.produces} == set(report.values)
        for quantity in declaration.produces:
            assert dimensionality(report.values[quantity.name].units) == quantity.dimension


def test_per_stage_quantities_are_selected_by_component_id(registry) -> None:
    for quantity in registry.get(ELECTROTHERMAL_CAPABILITY_ID).produces:
        assert (quantity.instance_key, quantity.instance_path) == ("component_id", "stages[].component_id")
    assert all(q.instance_key is None for q in registry.get(BATTERY_CAPABILITY_ID).produces)


def test_declared_models_and_versions_cover_what_the_runs_assess(registry, et_report, battery_report) -> None:
    for capability_id, report in ((ELECTROTHERMAL_CAPABILITY_ID, et_report), (BATTERY_CAPABILITY_ID, battery_report)):
        declared = {m.key for m in registry.get(capability_id).models}
        assert {(r.model_id, r.version) for r in report.validity} <= declared
        for model in registry.get(capability_id).models:
            assert model.definition is not None and model.definition.key == model.key


@pytest.mark.parametrize(
    "edit",
    ["example", "minimal", "limits", "regulation"],
)
def test_model_activation_predicts_which_models_an_electrothermal_run_assesses(registry, edit) -> None:
    case = example_electrothermal_payload()
    stage = case["stages"][0]
    if edit == "minimal":
        stage["conductor"] = {k: stage["conductor"][k] for k in ("reference_resistance", "temperature_coefficient", "reference_temperature")}
        stage["body"] = {k: v for k, v in stage["body"].items() if k != "applicability"}
        case.pop("source_ratings")
        case.pop("coupling")
    elif edit == "limits":
        stage["conductor"]["limits"] = {"linearization_band": "50 kelvin"}
    elif edit == "regulation":
        case["source_regulation"] = {"output_resistance": "0.01 ohm"}
    report = run_electrothermal_case(copy.deepcopy(case)).reports[0]
    predicted = _predicted_active(registry.get(ELECTROTHERMAL_CAPABILITY_ID), set(_paths(case)))
    assert predicted == _active_models(report)


def test_declared_unassessable_conditions_are_exactly_what_a_run_leaves_unknown(registry, et_report, battery_report) -> None:
    battery = registry.get(BATTERY_CAPABILITY_ID)
    observed = {
        (record.model_id, name)
        for record in battery_report.validity
        for name in record.assessment.unknown
    }
    declared = {(u.model_id, u.condition) for u in battery.unassessable_conditions}
    assert declared == observed
    assert len(declared) == 10
    # The electro-thermal boundary assembles the body's applicability, so it
    # declares nothing unassessable, and its example leaves nothing unknown.
    assert registry.get(ELECTROTHERMAL_CAPABILITY_ID).unassessable_conditions == ()
    assert not any(record.assessment.unknown for record in et_report.validity)


def test_battery_models_are_always_active(registry, battery_report) -> None:
    declaration = registry.get(BATTERY_CAPABILITY_ID)
    assert all(m.always_active for m in declaration.models)
    assert _active_models(battery_report) == {m.model_id for m in declaration.models}


def test_attainable_levels_bound_what_the_examples_attain(registry, et_report, battery_report) -> None:
    for capability_id, report in ((ELECTROTHERMAL_CAPABILITY_ID, et_report), (BATTERY_CAPABILITY_ID, battery_report)):
        declaration = registry.get(capability_id)
        assert set(report.attained_levels) <= declaration.attainable()
        checks = {check.name: check for check in report.validation}
        for level in declaration.attainable_levels:
            assert checks[level.check_name].establishes is level.level


def test_cross_solver_validation_is_not_declared_attainable_on_the_mcp_path(registry) -> None:
    declaration = registry.get(ELECTROTHERMAL_CAPABILITY_ID)
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in declaration.attainable()
    route = declaration.route("electrical.dc.external_simulator")
    assert route.kind is RouteKind.SOLVER_ROUTE and route.pinned_route == "electrical.dc.external_simulator"


def test_no_production_capability_claims_quantified_uncertainty(registry, et_report, battery_report) -> None:
    for declaration in registry:
        assert dict(declaration.uncertainty.quantified) == {}
    for report in (et_report, battery_report):
        assert all(not report.uncertainty[name].is_quantified for name in report.values)


def test_provided_capabilities_come_from_the_realizations_the_systems_bind(registry) -> None:
    for capability_id in (ELECTROTHERMAL_CAPABILITY_ID, BATTERY_CAPABILITY_ID):
        for provided in registry.get(capability_id).provides:
            assert provided.basis.startswith("realization:")
    (t3,) = registry.get(NAFEMS_T3_CAPABILITY_ID).provides
    assert t3.basis.startswith("stated:")


# ---------------------------------------------------------------------------
# NAFEMS T3
# ---------------------------------------------------------------------------


def _t3_point():
    from engcore.domains.thermal_models.nafems_t3_oracle import CONDITIONS

    return dict(CONDITIONS)


def test_t3_inputs_are_its_model_inputs_and_each_unlocks_its_own_condition(registry) -> None:
    from engcore.domains.thermal_models.nafems_t3 import MODEL

    declaration = registry.get(NAFEMS_T3_CAPABILITY_ID)
    physical = {i.path: i for i in declaration.inputs if i.model_id is not None}
    assert set(physical) == {spec.name for spec in MODEL.inputs} == {c.name for c in MODEL.validity.conditions}
    for name, item in physical.items():
        assert item.unlocks_conditions == (name,)
        assert item.required is False


def test_t3_runs_at_its_declared_point_and_attains_the_benchmark_level(registry) -> None:
    declaration = registry.get(NAFEMS_T3_CAPABILITY_ID)
    case = build_case(declaration, _t3_point())
    run = declaration.executor(case, run_id="t3-capability")
    (instance,) = run.reports
    assert instance.instance is None
    assert instance.report.verdict is CredibilityVerdict.SUPPORTED
    assert ValidationLevel.BENCHMARK_VALIDATED in instance.report.attained_levels
    assert set(instance.report.attained_levels) <= declaration.attainable()


def test_t3_refuses_a_case_about_another_bar_before_running(registry, monkeypatch) -> None:
    import engcore.mcp.nafems_t3 as vertical

    def must_not_run(**_):  # pragma: no cover - reaching it is the failure
        raise AssertionError("physics ran for an operating point T3 does not describe")

    monkeypatch.setattr(vertical, "run_nafems_t3_credibility", must_not_run)
    declaration = registry.get(NAFEMS_T3_CAPABILITY_ID)
    point = _t3_point()
    point["conductivity"] = Quantity(36.0, "watt / meter / kelvin")
    with pytest.raises(CapabilityExecutionRefused, match="conductivity"):
        declaration.executor(build_case(declaration, point), run_id="t3-other-bar")


def test_the_t3_benchmark_route_is_the_trusted_oracle(registry) -> None:
    route = registry.get(NAFEMS_T3_CAPABILITY_ID).route("nafems.p18.t3.oracle")
    assert route.kind is RouteKind.BENCHMARK
    evidence = route.oracle_provider()
    assert evidence.is_trusted and tuple(evidence.identity.key) == route.oracle


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


def test_the_electrothermal_executor_names_each_report_by_its_component(registry) -> None:
    declaration = registry.get(ELECTROTHERMAL_CAPABILITY_ID)
    case = example_electrothermal_payload()
    second = copy.deepcopy(case["stages"][0])
    second["component_id"] = "R2"
    case["stages"].append(second)
    run = declaration.executor(case, run_id="et-two-stages")
    assert [r.instance for r in run.reports] == ["R1", "R2"]


def test_the_battery_executor_reports_the_whole_case(registry) -> None:
    run = registry.get(BATTERY_CAPABILITY_ID).executor(example_battery_payload(), run_id="battery-capability")
    (instance,) = run.reports
    assert instance.instance is None and instance.report.run_id == "battery-capability"


# ---------------------------------------------------------------------------
# Routing over the production registry: declared identifiers only
# ---------------------------------------------------------------------------


def _matched(registry, quantity, dimension, required=()):
    return sorted(
        m.capability_id
        for m in registry.match(quantity=quantity, dimension=dimension, required=required, claim_kind=ClaimKind.THRESHOLD)
        if m.matched
    )


def test_a_shared_quantity_matches_every_system_that_produces_it(registry) -> None:
    assert _matched(registry, "final_temperature", "[temperature]") == [BATTERY_CAPABILITY_ID, ELECTROTHERMAL_CAPABILITY_ID]


def test_declared_scientific_capabilities_narrow_the_match(registry) -> None:
    assert _matched(registry, "final_temperature", "[temperature]", ("battery:cell_terminal_state",)) == [BATTERY_CAPABILITY_ID]
    assert _matched(registry, "final_temperature", "[temperature]", ("electrical:temperature_dependent_resistance",)) == [
        ELECTROTHERMAL_CAPABILITY_ID
    ]
    assert _matched(registry, "temperature_at_probe", "[temperature]") == [NAFEMS_T3_CAPABILITY_ID]


def test_a_quantity_in_the_wrong_dimension_matches_nothing(registry) -> None:
    assert _matched(registry, "final_temperature", dimensionality("volt")) == []
    assert _matched(registry, "stress", dimensionality("pascal")) == []
