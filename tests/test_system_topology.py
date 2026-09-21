from dataclasses import replace

import pytest

from engcore.planning.production import production_planning_registries
from engcore.assembly.domainpacks import production_composition_packs, production_execution_packs
from engcore.assembly.multiphysics import AuthorizedMultiphysicsRun, execute_authorized_graph_plan
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.planning import (
    ContextOfUse, EngineeringComponent, EngineeringIntent, FactRole,
    IntentFact, IntentQuantityOfInterest, PlannerPolicy, SimulationHorizon,
    plan_engineering_intent,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.twins import ScientificTwin, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.systems import (
    ComponentConnection, ComponentDefinition, ComponentInstance,
    ConstraintBinding, SystemDefinition,
)
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator


def _graph_plan():
    facts = (
        IntentFact("thermal.heat_capacity", FactRole.PARAMETER, Quantity(100, "J/K")),
        IntentFact("thermal.ambient_conductance", FactRole.PARAMETER, Quantity(1, "W/K")),
        IntentFact("thermal.ambient_temperature", FactRole.BOUNDARY_CONDITION, Quantity(300, "K")),
        IntentFact("thermal.initial_temperature", FactRole.INITIAL_CONDITION, Quantity(300, "K")),
        IntentFact("material.reference_resistance", FactRole.PARAMETER, Quantity(10, "ohm")),
        IntentFact("material.temperature_coefficient", FactRole.PARAMETER, Quantity(0.0039, "1/K")),
        IntentFact("material.reference_temperature", FactRole.PARAMETER, Quantity(293.15, "K")),
        IntentFact("electrical.source_voltage", FactRole.BOUNDARY_CONDITION, Quantity(12, "V")),
    )
    intent = EngineeringIntent(
        "topology test", ContextOfUse("predict", "system", "error"),
        (EngineeringComponent("system", "electrothermal.feedback"),), (), facts,
        (IntentQuantityOfInterest("temperature", "final_temperature", "K", "system"),),
        simulation_horizon=SimulationHorizon(Quantity(0, "s"), Quantity(2, "s")),
    )
    return plan_engineering_intent(
        intent, production_planning_registries(),
        PlannerPolicy(capability_by_qoi={"temperature": "system.electrothermal_feedback"}),
    ).graph_plans[0]


def _graph():
    return _graph_plan().graph


def _topology(graph):
    root_twin = ScientificTwin("system-root", "1", TwinKind.CONCEPT)
    twins = {root_twin.reference.key: root_twin}
    definitions = []
    instances = [ComponentInstance("root", "assembly", "1", root_twin.reference)]
    for participant in graph.participants:
        twin = ScientificTwin(f"twin-{participant.participant_id}", "1", TwinKind.CONCEPT)
        twins[twin.reference.key] = twin
        definitions.append(ComponentDefinition(participant.participant_id, "1", participant.ports))
        instances.append(ComponentInstance(
            participant.participant_id, participant.participant_id, "1", twin.reference,
            parent_id="root", participant_id=participant.participant_id,
        ))
    definitions.append(ComponentDefinition("assembly", "1"))
    connections = tuple(ComponentConnection(
        edge.edge_id, edge.edge_id,
        edge.source.participant_id, edge.source.port_id,
        edge.target.participant_id, edge.target.port_id,
    ) for edge in graph.edges)
    return SystemDefinition("electrothermal-system", "1", tuple(definitions), tuple(instances), connections), twins


def test_hierarchical_topology_roundtrips_and_binds_exact_graph_and_twins():
    graph = _graph()
    topology, twins = _topology(graph)

    topology.validate_against(graph, twins)
    restored = SystemDefinition.from_dict(topology.to_dict())

    assert restored == topology
    assert restored.digest == topology.digest
    assert len([item for item in topology.instances if item.parent_id == "root"]) == 3


def test_topology_refuses_connection_or_twin_authority_drift():
    graph = _graph()
    topology, twins = _topology(graph)
    first = topology.connections[0]
    with pytest.raises(InvalidScientificProblem, match="undeclared component port"):
        replace(topology, connections=(replace(first, source_port_id="wrong"), *topology.connections[1:]))

    missing = dict(twins)
    missing.pop(topology.instances[0].twin.key)
    with pytest.raises(InvalidScientificProblem, match="no exact ScientificTwin authority"):
        topology.validate_against(graph, missing)


def test_topology_is_bound_through_authorized_execution_roundtrip():
    graph_plan = _graph_plan()
    topology, twins = _topology(graph_plan.graph)
    graph_plan = replace(graph_plan, system_definition=topology)
    store = InMemoryBulkStore()

    authorized = execute_authorized_graph_plan(
        graph_plan,
        run_id="topology-bound",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store),
        store=store,
        topology_twins=twins,
    )

    restored = AuthorizedMultiphysicsRun.from_dict(authorized.to_dict())
    assert restored.graph_plan.system_definition == topology
    assert restored.graph_plan.system_definition.digest == topology.digest


def test_executable_plan_refuses_unenforced_topology_constraints():
    graph_plan = _graph_plan()
    topology, _ = _topology(graph_plan.graph)
    constrained = replace(
        topology,
        constraints=(ConstraintDefinition(
            "impossible-temperature", "temperature",
            ConstraintOperator.LESS_EQUAL, Quantity(0, "K"),
        ),),
        constraint_bindings=(ConstraintBinding(
            "temperature-limit", "thermal", "impossible-temperature"
        ),),
    )

    with pytest.raises(ValueError, match="constraint_enforcement"):
        replace(graph_plan, system_definition=constrained)


def test_topology_refuses_duplicate_participant_or_edge_authority():
    graph = _graph()
    topology, _ = _topology(graph)
    leaf = next(item for item in topology.instances if item.participant_id)
    duplicate = replace(leaf, instance_id=f"{leaf.instance_id}-duplicate")
    with pytest.raises(InvalidScientificProblem, match="more than one instance"):
        replace(topology, instances=(*topology.instances, duplicate)).validate_graph(graph)

    connection = topology.connections[0]
    duplicate_connection = replace(connection, connection_id=f"{connection.connection_id}-duplicate")
    with pytest.raises(InvalidScientificProblem, match="more than one connection"):
        replace(topology, connections=(*topology.connections, duplicate_connection)).validate_graph(graph)
