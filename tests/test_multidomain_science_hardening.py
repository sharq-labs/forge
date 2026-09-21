import copy
import ast
from pathlib import Path

import pytest

from engcore.assembly.certification import certify_authorized_multiphysics_run
from engcore.assembly.domainpacks import (
    production_domain_packs,
    production_composition_packs,
    production_execution_packs,
)
from engcore.assembly.multiphysics import (
    AuthorizedMultiphysicsRun,
    execute_authorized_graph_plan,
)
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.planning import (
    ContextOfUse,
    EngineeringComponent,
    EngineeringIntent,
    FactRole,
    FidelityRequest,
    IntentFact,
    IntentQuantityOfInterest,
    PlannerPolicy,
    PlanningStatus,
    SimulationHorizon,
    plan_engineering_intent,
)
from engcore.planning.production import production_planning_registries
from engcore.scientific.certification_core import verify_certification_record
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def _intent(*, omit=(), overrides=None):
    values = {
        "thermal.heat_capacity": (FactRole.PARAMETER, Quantity(100, "J/K")),
        "thermal.ambient_conductance": (FactRole.PARAMETER, Quantity(1, "W/K")),
        "thermal.ambient_temperature": (FactRole.BOUNDARY_CONDITION, Quantity(300, "K")),
        "thermal.initial_temperature": (FactRole.INITIAL_CONDITION, Quantity(300, "K")),
        "material.reference_resistance": (FactRole.PARAMETER, Quantity(10, "ohm")),
        "material.temperature_coefficient": (FactRole.PARAMETER, Quantity(0.0039, "1/K")),
        "material.reference_temperature": (FactRole.PARAMETER, Quantity(293.15, "K")),
        "electrical.source_voltage": (FactRole.BOUNDARY_CONDITION, Quantity(12, "V")),
    }
    for path, value in (overrides or {}).items():
        values[path] = values[path][0], value
    return EngineeringIntent(
        "closed-loop electrothermal feedback",
        ContextOfUse(
            "predict terminal state",
            "single resistor self heating",
            "incorrect terminal temperature",
            require_independent_verification=True,
        ),
        (EngineeringComponent("system", "electrothermal.feedback"),),
        (),
        tuple(
            IntentFact(path, role, value)
            for path, (role, value) in values.items()
            if path not in omit
        ),
        (
            IntentQuantityOfInterest(
                "temperature", "final_temperature", "K", "system"
            ),
        ),
        simulation_horizon=SimulationHorizon(
            Quantity(0, "s"), Quantity(10, "s")
        ),
    )


def test_production_fidelity_ladder_is_registered_and_selects_feedback():
    intent = _intent()
    intent = EngineeringIntent(
        intent.statement,
        intent.context,
        intent.components,
        intent.interfaces,
        intent.facts,
        intent.qois,
        simulation_horizon=intent.simulation_horizon,
        fidelity=FidelityRequest(
            "system.electrothermal.coupling",
            "1",
            minimum_rung="one_way",
            preferred_rung="feedback",
        ),
    )

    planning = _plan(intent)

    assert planning.status is PlanningStatus.READY
    assert planning.fidelity is not None
    assert planning.fidelity.selected_rung == "feedback"
    assert planning.fidelity.available_rungs == ("feedback",)


def test_battery_science_is_registered_as_an_atomic_production_domain_pack():
    registrations = {
        item.manifest.pack_id: item
        for item in production_domain_packs().list(enabled_only=True)
    }

    battery = registrations["battery.cell"]
    assert battery.manifest.domain == "battery"
    assert battery.manifest.capabilities == ("battery:cell_terminal_state",)
    assert len(battery.manifest.models) == 4
    assert len(battery.manifest.realizations) == 4
    assert len(battery.manifest.solvers) == 1


def test_production_planning_has_no_domain_implementation_imports():
    """Domain Packs are the sole realization/solver authority in planning."""

    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "engcore"
        / "planning"
        / "production.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        (node.level, node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert not any(
        module == "engcore.domains"
        or module.startswith("engcore.domains.")
        or (level > 0 and (
            module == "domains" or module.startswith("domains.")
        ))
        for level, module in imported
    )


def test_production_realizations_and_solvers_come_from_enabled_domain_packs():
    registries = production_planning_registries()
    enabled = production_domain_packs().list(enabled_only=True)

    expected_realizations = {
        realization.key
        for registration in enabled
        for realization in registration.provider.realizations()
    }
    expected_solvers = {
        factory().identity.key
        for registration in enabled
        for factory in registration.provider.solver_factories()
    }

    assert {item.key for item in registries.realizations} == expected_realizations
    assert {item.identity.key for item in registries.solvers.list()} == expected_solvers


def _plan(intent):
    return plan_engineering_intent(
        intent,
        production_planning_registries(),
        PlannerPolicy(
            capability_by_qoi={
                "temperature": "system.electrothermal_feedback"
            }
        ),
    )


def test_feedback_public_flow_roundtrips_certifies_and_rejects_tampering():
    planning = _plan(_intent())
    assert planning.status is PlanningStatus.READY
    graph_plan = planning.graph_plans[0]
    assert graph_plan.coupling_plan.time.coupling_window == Quantity(1, "s")

    store = InMemoryBulkStore()
    authorized = execute_authorized_graph_plan(
        graph_plan,
        run_id="hardening-regression",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store),
        store=store,
    )
    assert all(item.result.valid for item in authorized.system_validation)
    assert all(
        item.run.result.verification.decision.value == "verified"
        for item in authorized.system_verification
    )
    assert AuthorizedMultiphysicsRun.from_dict(
        authorized.to_dict()
    ) == authorized
    certification = certify_authorized_multiphysics_run(
        authorized, commit_sha="0" * 40
    )
    assert verify_certification_record(certification).verified

    mutations = (
        ("composition_snapshot", "authority_digest"),
        ("run", "run_id"),
    )
    for section, key in mutations:
        payload = copy.deepcopy(authorized.to_dict())
        payload[section][key] = "tampered"
        with pytest.raises(InvalidScientificProblem):
            AuthorizedMultiphysicsRun.from_dict(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        ("thermal.heat_capacity", Quantity(0, "J/K")),
        ("thermal.ambient_conductance", Quantity(0, "W/K")),
        ("material.reference_resistance", Quantity(0, "ohm")),
    ),
)
def test_nonpositive_parameters_are_refused(path, value):
    planning = _plan(_intent(overrides={path: value}))
    assert planning.status is PlanningStatus.NEEDS_CLARIFICATION
    assert any(
        gap.blocking and gap.kind.value == "system_applicability_violated"
        for gap in planning.gaps
    )


def test_missing_required_input_is_a_gap_not_a_crash():
    planning = _plan(_intent(omit={"electrical.source_voltage"}))
    assert planning.status is PlanningStatus.NEEDS_CLARIFICATION
    assert any(
        gap.kind.value == "graph_external_input_missing"
        for gap in planning.gaps
    )
