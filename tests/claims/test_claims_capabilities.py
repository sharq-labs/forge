"""CORE-3: capability declarations and the registry, on synthetic declarations.

Nothing here imports a domain: the declaration rules are generic, and the
production declarations have their own file.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from engcore.claims import (
    AttainableLevel,
    CapabilityDeclaration,
    CapabilityDeclarationError,
    CapabilityInputError,
    CapabilityRegistry,
    CapabilityRegistryError,
    CapabilityRun,
    ClaimKind,
    InputDeclaration,
    InputKind,
    InputRole,
    InstanceReport,
    MismatchReason,
    ProducedQuantity,
    ProvidedCapability,
    RouteDeclaration,
    RouteKind,
    UnassessableCondition,
    UncertaintyCapability,
    build_case,
    declared_path,
    input_problem,
)
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel


def _executor(case, *, run_id):  # pragma: no cover - never called here
    raise AssertionError("declarations are not executed in these tests")


def _inputs():
    return (
        InputDeclaration("body.heat_capacity", InputKind.QUANTITY, InputRole.PARAMETER, True, "joule / kelvin"),
        InputDeclaration("body.initial_temperature", InputKind.QUANTITY, InputRole.INITIAL_CONDITION, True, "kelvin"),
        InputDeclaration("body.rise_budget", InputKind.QUANTITY, InputRole.APPLICABILITY, False, "delta_degree_Celsius"),
        InputDeclaration("stages[].component_id", InputKind.IDENTIFIER, InputRole.IDENTITY, True),
        InputDeclaration("stages[].share", InputKind.FRACTION, InputRole.PARAMETER, False),
        InputDeclaration("numerics.steps", InputKind.COUNT, InputRole.NUMERICS, False),
        InputDeclaration("numerics.verbose", InputKind.FLAG, InputRole.NUMERICS, False),
    )


def declaration(**overrides) -> CapabilityDeclaration:
    fields = dict(
        capability_id="synthetic.body",
        version="1",
        domain="synthetic",
        summary="a synthetic capability for contract tests",
        provides=(ProvidedCapability("thermal:body_temperature", "stated: synthetic"),),
        inputs=_inputs(),
        produces=(
            ProducedQuantity("final_temperature", "kelvin"),
            ProducedQuantity("stage_temperature", "kelvin", instance_key="component_id", instance_path="stages[].component_id"),
        ),
        models=(),
        solvers=(),
        claim_shapes=frozenset({ClaimKind.THRESHOLD}),
        attainable_levels=(),
        uncertainty=UncertaintyCapability({}, "nothing is quantified"),
        routes=(RouteDeclaration("synthetic.primary", RouteKind.PRIMARY_SIMULATION, "the only route"),),
        executor=_executor,
    )
    fields.update(overrides)
    return CapabilityDeclaration(**fields)


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


def test_a_declaration_round_trips_as_a_description_with_the_same_digest() -> None:
    made = declaration()
    back = CapabilityDeclaration.from_dict(json.loads(json.dumps(made.to_dict())))
    assert back.digest == made.digest
    assert back == made
    assert back.executable is False  # a description does not re-arm a capability


def test_declaration_order_does_not_change_identity_and_executors_are_not_identity() -> None:
    a = declaration()
    b = declaration(inputs=tuple(reversed(_inputs())), executor=lambda case, *, run_id: None)
    assert a.digest == b.digest


def test_a_declared_fact_changes_identity() -> None:
    assert declaration(version="2").digest != declaration().digest
    assert declaration(claim_shapes=frozenset(ClaimKind)).digest != declaration().digest


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"inputs": _inputs() + (_inputs()[0],)}, "duplicate inputs"),
        ({"produces": ()}, "produces nothing"),
        ({"claim_shapes": frozenset()}, "no claim shape"),
        ({"routes": ()}, "exactly one PRIMARY_SIMULATION"),
        (
            {"routes": (RouteDeclaration("a", RouteKind.PRIMARY_SIMULATION, "a"), RouteDeclaration("b", RouteKind.PRIMARY_SIMULATION, "b"))},
            "exactly one PRIMARY_SIMULATION",
        ),
        (
            {"inputs": _inputs() + (InputDeclaration("x.y", InputKind.QUANTITY, InputRole.PARAMETER, False, "kelvin", model_id="m.absent", model_input="y"),)},
            "which is not declared",
        ),
        ({"produces": (ProducedQuantity("t", "kelvin", instance_key="k", instance_path="nowhere[].k"),)}, "undeclared input"),
        ({"attainable_levels": (AttainableLevel(ValidationLevel.ANALYTICALLY_VERIFIED, "check", "ghost", "never"),)}, "undeclared route"),
        ({"uncertainty": UncertaintyCapability({"not_produced": (UncertaintyChannel.NUMERICAL,)}, "b")}, "not produced"),
        ({"capability_id": "System Body"}, "dotted lowercase"),
        (
            {"unassessable_conditions": (UnassessableCondition("thermal.absent", "biot_number", "never assembled"),)},
            "undeclared model",
        ),
    ],
)
def test_contradictory_declarations_are_refused(overrides, fragment) -> None:
    with pytest.raises(CapabilityDeclarationError, match=fragment):
        declaration(**overrides)


def test_evidence_routes_must_name_what_carries_and_authorizes_them() -> None:
    with pytest.raises(CapabilityDeclarationError, match="must name its pinned_route"):
        RouteDeclaration("r", RouteKind.SOLVER_ROUTE, "a second solver", check_name="c")
    with pytest.raises(CapabilityDeclarationError, match="must name its oracle"):
        RouteDeclaration("r", RouteKind.BENCHMARK, "a benchmark", check_name="c")
    with pytest.raises(CapabilityDeclarationError, match="must name its analytic_reference"):
        RouteDeclaration("r", RouteKind.ANALYTIC_REFERENCE, "a reference", check_name="c")
    with pytest.raises(CapabilityDeclarationError, match="names the check"):
        RouteDeclaration("r", RouteKind.SOLVER_ROUTE, "a second solver", pinned_route="electrical.dc.native_mna")


def test_a_live_declaration_must_point_at_real_pins() -> None:
    primary = RouteDeclaration("p", RouteKind.PRIMARY_SIMULATION, "primary")
    with pytest.raises(CapabilityDeclarationError, match="not a pinned solve route"):
        declaration(routes=(primary, RouteDeclaration("r", RouteKind.SOLVER_ROUTE, "x", check_name="c", pinned_route="made.up.route")))
    with pytest.raises(CapabilityDeclarationError, match="not a pinned analytic reference"):
        declaration(routes=(primary, RouteDeclaration("r", RouteKind.ANALYTIC_REFERENCE, "x", check_name="c", analytic_reference="made.up")))
    with pytest.raises(CapabilityDeclarationError, match="no provider"):
        declaration(routes=(primary, RouteDeclaration("r", RouteKind.BENCHMARK, "x", check_name="c", oracle=("nafems.p18.t3.transient_heat_1d", "1"))))
    # A description read back from JSON has no executor, so it is not re-verified.
    described = declaration(executor=None, routes=(primary, RouteDeclaration("r", RouteKind.SOLVER_ROUTE, "x", check_name="c", pinned_route="made.up.route")))
    assert described.executable is False


def test_an_oracle_route_is_verified_against_the_trusted_pin() -> None:
    from engcore.domains.thermal_models.nafems_t3_oracle import nafems_t3_evidence
    from engcore.scientific.oracles import OracleEvidenceSet

    primary = RouteDeclaration("p", RouteKind.PRIMARY_SIMULATION, "primary")
    trusted = RouteDeclaration(
        "r", RouteKind.BENCHMARK, "x", check_name="c",
        oracle=("nafems.p18.t3.transient_heat_1d", "1"), oracle_provider=nafems_t3_evidence,
    )
    assert declaration(routes=(primary, trusted)).route("r").oracle == ("nafems.p18.t3.transient_heat_1d", "1")

    genuine = nafems_t3_evidence()
    forged_target = replace(genuine.observations[0], expected=Quantity(40.0, "degree_Celsius"))
    forged = OracleEvidenceSet.create(
        oracle_id=genuine.identity.oracle_id,
        version=genuine.identity.version,
        kind=genuine.identity.kind,
        reference=genuine.identity.reference,
        observations=(forged_target,),
    )
    assert not forged.is_trusted
    with pytest.raises(CapabilityDeclarationError, match="not trusted"):
        declaration(routes=(primary, replace(trusted, oracle_provider=lambda: forged)))
    with pytest.raises(CapabilityDeclarationError, match="the provider returns"):
        declaration(routes=(primary, replace(trusted, oracle=("another.oracle", "1"))))
    with pytest.raises(CapabilityDeclarationError, match="EXPERIMENTAL|establishes"):
        declaration(routes=(primary, replace(trusted, kind=RouteKind.EXPERIMENTAL)))


def test_serialized_facts_must_agree_with_what_they_derive_from() -> None:
    wire = declaration().to_dict()
    wire["inputs"][0]["dimension"] = "[length]"
    with pytest.raises(CapabilityDeclarationError, match="serialized dimension"):
        CapabilityDeclaration.from_dict(wire)
    wire = declaration().to_dict()
    wire["ranking"] = 1
    with pytest.raises(CapabilityDeclarationError, match="unknown field"):
        CapabilityDeclaration.from_dict(wire)


def test_attainable_levels_are_upper_bounds_never_unverified() -> None:
    with pytest.raises(CapabilityDeclarationError, match="UNVERIFIED"):
        AttainableLevel(ValidationLevel.UNVERIFIED, "c", None, "never")


# ---------------------------------------------------------------------------
# Inputs -> case
# ---------------------------------------------------------------------------


def test_the_case_builder_writes_exactly_what_was_stated() -> None:
    made = declaration()
    case = build_case(
        made,
        {
            "body.heat_capacity": Quantity(50.0, "joule / kelvin"),
            "body.initial_temperature": Quantity(26.85, "degree_Celsius"),
            "stages[0].component_id": "R1",
            "stages[1].component_id": "R2",
            "stages[1].share": Quantity(0.5, "dimensionless"),
            "numerics.steps": 20,
            "numerics.verbose": False,
        },
    )
    assert case == {
        "body": {"heat_capacity": "50.0 joule / kelvin", "initial_temperature": "26.85 degree_Celsius"},
        "stages": [{"component_id": "R1"}, {"component_id": "R2", "share": 0.5}],
        "numerics": {"steps": 20, "verbose": False},
    }
    assert Quantity.parse(case["body"]["heat_capacity"]) == Quantity(50.0, "joule / kelvin")


@pytest.mark.parametrize(
    "inputs, fragment",
    [
        ({"body.mass": Quantity(1.0, "kilogram")}, "declares no input"),
        ({"body.heat_capacity": Quantity(1.0, "kelvin")}, r"requires \["),
        ({"body.heat_capacity": 50}, "must be a Quantity"),
        ({"body.initial_temperature": Quantity(27.0, "delta_degree_Celsius")}, "absolute value"),
        ({"body.rise_budget": Quantity(27.0, "degree_Celsius")}, "a difference"),
        ({"stages[].component_id": "R1"}, "must name an element"),
        ({"body[0].heat_capacity": Quantity(1.0, "joule / kelvin")}, "declares no input|not an array element"),
        ({"stages[1].component_id": "R2"}, "numbered from 0 without gaps"),
        ({"stages[0].share": Quantity(0.5, "kelvin")}, "dimensionless"),
        ({"numerics.steps": True}, "positive integer"),
        ({"numerics.steps": 0}, "positive integer"),
        ({"numerics.verbose": 1}, "boolean"),
    ],
)
def test_the_case_builder_refuses_what_the_declaration_does_not_accept(inputs, fragment) -> None:
    with pytest.raises(CapabilityInputError, match=fragment):
        build_case(declaration(), inputs)


def test_one_rule_decides_acceptability_for_compiler_and_builder() -> None:
    made = declaration()
    item = made.input("stages[3].component_id")
    assert item is not None and item.path == declared_path("stages[3].component_id")
    assert input_problem(item, "stages[3].component_id", "R4") is None
    assert "text" in input_problem(item, "stages[3].component_id", 4)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_an_executor_returns_credibility_reports_one_per_instance() -> None:
    with pytest.raises(CapabilityDeclarationError, match="CredibilityEvidenceReport"):
        InstanceReport(None, {"verdict": "supported"})
    with pytest.raises(CapabilityDeclarationError, match="at least one"):
        CapabilityRun(reports=())


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_the_registry_refuses_duplicate_ids_and_names_what_exists() -> None:
    with pytest.raises(CapabilityRegistryError, match="duplicate capability ids"):
        CapabilityRegistry((declaration(), declaration()))
    registry = CapabilityRegistry((declaration(),))
    with pytest.raises(CapabilityRegistryError, match="synthetic.body"):
        registry.get("system.nothing")


def test_the_registry_indexes_what_is_declared_and_its_digest_follows_it() -> None:
    other = declaration(
        capability_id="synthetic.cell",
        provides=(ProvidedCapability("battery:cell_terminal_state", "stated: synthetic"),),
        produces=(ProducedQuantity("final_temperature", "kelvin"), ProducedQuantity("terminal_voltage", "volt")),
    )
    registry = CapabilityRegistry((other, declaration()))
    assert [d.capability_id for d in registry] == ["synthetic.body", "synthetic.cell"]
    assert {d.capability_id for d in registry.producing("final_temperature")} == {"synthetic.body", "synthetic.cell"}
    assert [d.capability_id for d in registry.providing("battery:cell_terminal_state")] == ["synthetic.cell"]
    assert registry.producing("nothing") == ()
    changed = CapabilityRegistry((replace(other, version="2"), declaration()))
    assert changed.digest != registry.digest


def test_matching_reports_every_reason_a_declaration_is_not_a_candidate() -> None:
    registry = CapabilityRegistry((declaration(), declaration(capability_id="synthetic.idle", executor=None)))
    by_id = {
        m.capability_id: m
        for m in registry.match(
            quantity="final_temperature",
            dimension="[length]",
            required=("battery:cell_terminal_state",),
            claim_kind=ClaimKind.TOLERANCE_BAND,
        )
    }
    reasons = {reason for reason, _ in by_id["synthetic.body"].reasons}
    assert reasons == {
        MismatchReason.DIMENSION_MISMATCH,
        MismatchReason.CAPABILITY_NOT_PROVIDED,
        MismatchReason.CLAIM_SHAPE_UNSUPPORTED,
    }
    assert MismatchReason.NOT_EXECUTABLE in {r for r, _ in by_id["synthetic.idle"].reasons}
    assert not any(m.matched for m in by_id.values())

    ok = registry.match(quantity="final_temperature", dimension="[temperature]", claim_kind=ClaimKind.THRESHOLD)
    assert [(m.capability_id, m.matched) for m in ok] == [("synthetic.body", True), ("synthetic.idle", False)]
    missing = registry.match(quantity="pressure", dimension="[mass] / [length] / [time] ** 2", claim_kind=ClaimKind.THRESHOLD)
    assert all(MismatchReason.QUANTITY_NOT_PRODUCED in {r for r, _ in m.reasons} for m in missing)


def test_matching_reads_declared_identifiers_never_prose() -> None:
    """No keyword science: a summary full of the right words matches nothing."""
    wordy = declaration(
        capability_id="synthetic.wordy",
        summary="temperature final_temperature thermal body heat kelvin battery voltage",
        produces=(ProducedQuantity("pressure_drop", "pascal"),),
        provides=(ProvidedCapability("fluid:pipe_flow", "stated: synthetic"),),
    )
    registry = CapabilityRegistry((wordy,))
    (result,) = registry.match(quantity="final_temperature", dimension="[temperature]", claim_kind=ClaimKind.THRESHOLD)
    assert not result.matched
    assert copy.deepcopy(result.to_dict())["matched"] is False
