"""BIG 12 contracts: canonical request identity, deterministic plan, state, serialization, tamper.

Gate F (identity sensitivity) and Gate K (deterministic planner) live here.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    AuthorityRef, ContentRef, ExecutionProfile, InitialStateSpec, LiteralInput, ModelSelection, NodeInput, NodeKind, NodeOutputSpec, NodeSpec, OperationalContext,
    OwnerState, PlanNode, ProviderBinding, RequestedObservable, SystemExecutionPlan, SystemRunRequest, SystemState, compile_plan,
)
from tests.system_runtime_fixtures import UNKNOWN, Knobs, build, sha


def _req(**kw):
    return build(**kw)[0]


# ------------------------------------------------------------------------------------------ Gate K: deterministic planner
def test_gate_k_the_plan_is_a_pure_function_of_the_serialized_request():
    request = _req()
    wire = json.dumps(request.to_dict(), sort_keys=True)
    restored = SystemRunRequest.from_dict(json.loads(wire))
    assert restored == request and restored.digest == request.digest
    first, second = compile_plan(request), compile_plan(restored)
    assert first.digest == second.digest
    assert [n.to_dict() for n in first.nodes] == [n.to_dict() for n in second.nodes]
    assert [n.node_id for n in first.nodes] == [n.node_id for n in compile_plan(request).nodes]
    # ...and the plan itself round-trips exactly
    assert SystemExecutionPlan.from_dict(json.loads(json.dumps(first.to_dict()))).digest == first.digest


def test_gate_k_the_planner_derives_material_environment_and_constraint_nodes_around_the_declared_ones():
    plan = compile_plan(_req())
    ids = [n.node_id for n in plan.nodes]
    assert {"env.thermal.ambient", "mat.thermal.k", "constraint.b_tmax"} <= set(ids)
    assert ids.index("env.thermal.ambient") < ids.index("thermal") < ids.index("report") < ids.index("constraint.b_tmax")
    derived = {n.node_id for n in plan.nodes if n.derived}
    assert derived == {"env.thermal.ambient", "mat.thermal.k", "constraint.b_tmax"}
    assert plan.node("thermal").depends_on == ("env.thermal.ambient", "heat", "mat.thermal.k")


# ------------------------------------------------------------------------------------------ Gate F: identity sensitivity
def _differs(base, other):
    assert other.digest != base.digest
    assert compile_plan(other).digest != compile_plan(base).digest


def test_gate_f_each_scientifically_relevant_input_changes_request_and_plan_identity_individually():
    base = _req()
    _differs(base, _req(conductivity=17.0))                    # material
    _differs(base, _req(ambient=(293.15, 296.15)))             # environment
    _differs(base, _req(scn_version="2"))                      # scenario
    _differs(base, _req(initial_temperature=310.0))            # initial state
    _differs(base, _req(limit=350.0))                          # constraint definition
    _differs(base, _req(knobs=Knobs(volts=3.8)))               # authority (its config is its identity)


def test_gate_f_provider_selection_version_and_digest_are_identity():
    base = _req()
    bound = replace(base, provider_bindings=(ProviderBinding("cell_solver", "pybamm", "26.8"),))
    _differs(base, bound)
    _differs(bound, replace(base, provider_bindings=(ProviderBinding("cell_solver", "pybamm", "26.9"),)))          # version
    _differs(bound, replace(base, provider_bindings=(ProviderBinding("cell_solver", "pybamm", "26.8", sha("build")),)))  # digest
    _differs(bound, replace(base, provider_bindings=(ProviderBinding("cell_solver", "tespy", "26.8"),)))          # a different provider
    _differs(base, replace(base, model_selections=(ModelSelection("cell", "spm", "1"),)))                          # explicit model selection


def test_gate_f_operational_facts_are_not_scientific_identity():
    base = _req()
    moved = _req(workspace="C:/tmp/anywhere/else")
    assert moved.digest == base.digest and compile_plan(moved).digest == compile_plan(base).digest
    assert moved.operational_digest != base.operational_digest                  # recorded, separately
    relabelled = replace(base, request_id="another-label")
    assert relabelled.digest == base.digest                                     # a caller label alone is not identity


# ------------------------------------------------------------------------------------------ request strictness / tamper
def test_the_request_refuses_unknown_missing_and_non_finite_content():
    wire = _req().to_dict()
    with pytest.raises(InvalidScientificProblem, match="unknown"):
        SystemRunRequest.from_dict({**wire, "surprise": 1})
    missing = dict(wire)
    del missing["observables"]
    with pytest.raises(InvalidScientificProblem, match="missing"):
        SystemRunRequest.from_dict(missing)
    bad = json.loads(json.dumps(wire))
    bad["initial_state"]["owners"][0]["values"][0]["value"]["magnitude"] = float("nan")
    with pytest.raises(Exception):
        SystemRunRequest.from_dict(bad)
    wrong_schema = {**wire, "schema": "forge.system_runtime.system_run_request/2"}
    with pytest.raises(InvalidScientificProblem, match="unsupported schema"):
        SystemRunRequest.from_dict(wrong_schema)


def test_a_tampered_request_is_a_different_request():
    base = _req()
    wire = json.loads(json.dumps(base.to_dict()))
    wire["scenario"]["digest"] = sha("another scenario")
    assert SystemRunRequest.from_dict(wire).digest != base.digest


def test_environment_must_be_present_or_explicitly_stated_absent():
    base = _req()
    with pytest.raises(InvalidScientificProblem, match="must state why"):
        replace(base, environment=None, environment_absent_reason="")
    with pytest.raises(InvalidScientificProblem, match="contradictory"):
        replace(base, environment_absent_reason="none needed")
    absent = replace(base, environment=None, environment_absent_reason="isothermal bench test, no environment")
    assert absent.digest != base.digest and SystemRunRequest.from_dict(absent.to_dict()) == absent


@pytest.mark.parametrize("mutate,match", [
    (lambda r: replace(r, nodes=r.nodes + (r.nodes[0],)), "duplicate"),
    (lambda r: replace(r, observables=r.observables + (r.observables[0],)), "duplicate"),
    (lambda r: replace(r, observables=()), "at least one requested observable"),
    (lambda r: replace(r, nodes=()), "at least one NodeSpec"),
    (lambda r: replace(r, initial_state=None), "InitialStateSpec"),
    (lambda r: replace(r, system=ContentRef("scenario", "x", sha("x"))), "system ContentRef"),
])
def test_structurally_invalid_requests_are_refused(mutate, match):
    with pytest.raises(InvalidScientificProblem, match=match):
        mutate(_req())


def test_a_literal_input_needs_an_explicit_uncertainty_and_a_derived_node_cannot_be_declared():
    with pytest.raises(InvalidScientificProblem, match="explicit Uncertainty"):
        LiteralInput("x", Quantity(1, "A"), None)
    with pytest.raises(InvalidScientificProblem, match="derived by the planner"):
        NodeSpec("mat", NodeKind.RESOLVE_MATERIAL, AuthorityRef("a", "k", sha("a")), (NodeOutputSpec("v", "K"),))


# ------------------------------------------------------------------------------------------ plan refusals
def _with_nodes(request, nodes, observables=None):
    return replace(request, nodes=tuple(nodes), observables=observables or request.observables, constraint_observations=())


def test_a_cycle_in_the_generic_graph_is_refused_and_named():
    request = _req()
    auth = request.nodes[0].authority
    a = NodeSpec("a", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("x", "K"),), inputs=(NodeInput("i", "b", "y", "K"),))
    b = NodeSpec("b", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("y", "K"),), inputs=(NodeInput("i", "a", "x", "K"),))
    with pytest.raises(InvalidScientificProblem, match="cycle among \\['a', 'b'\\]"):
        compile_plan(_with_nodes(request, (a, b), (RequestedObservable("o", "a", "x", "K"),)))


@pytest.mark.parametrize("build_nodes,match", [
    (lambda auth: (NodeSpec("a", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("x", "K"),), depends_on=("ghost",)),), "unknown node"),
    (lambda auth: (NodeSpec("a", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("x", "K"),), inputs=(NodeInput("i", "ghost", "y", "K"),)),), "depends on unknown node 'ghost'"),
    (lambda auth: (NodeSpec("a", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("x", "K"),)),
                   NodeSpec("b", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("y", "K"),), inputs=(NodeInput("i", "a", "nope", "K"),))), "unknown output"),
    (lambda auth: (NodeSpec("a", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("x", "K"),)),
                   NodeSpec("b", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("y", "K"),), inputs=(NodeInput("i", "a", "x", "W"),))), "expects 'W'"),
    (lambda auth: (NodeSpec("env.a", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("x", "K"),)),), "reserved"),
    (lambda auth: (NodeSpec("a", NodeKind.MULTIPHYSICS_EXECUTION, auth, (NodeOutputSpec("x", "K"),)),), "does not declare mode"),
    (lambda auth: (NodeSpec("a", NodeKind.NUMERICAL_EXECUTION, auth, (NodeOutputSpec("x", "K"),), provider_binding_ids=("ghost",)),), "unknown provider binding"),
])
def test_the_planner_refuses_dangling_wiring_unit_mismatches_and_undeclared_modes(build_nodes, match):
    request = _req()
    auth = request.nodes[0].authority
    nodes = build_nodes(auth)
    with pytest.raises(InvalidScientificProblem, match=match):
        compile_plan(_with_nodes(request, nodes, (RequestedObservable("o", nodes[0].node_id.replace("env.", "a"), "x", "K"),)))


def test_an_observable_must_name_a_declared_output_with_a_compatible_unit():
    request = _req()
    with pytest.raises(InvalidScientificProblem, match="unknown output"):
        compile_plan(replace(request, observables=(RequestedObservable("o", "heat", "nope", "W"),), constraint_observations=()))
    with pytest.raises(InvalidScientificProblem, match="disagrees"):
        compile_plan(replace(request, observables=(RequestedObservable("o", "heat", "power", "K"),), constraint_observations=()))


def test_a_plan_cannot_be_reordered_or_tampered_into_validity():
    plan = compile_plan(_req())
    wire = json.loads(json.dumps(plan.to_dict()))
    wire["nodes"] = list(reversed(wire["nodes"]))
    with pytest.raises(InvalidScientificProblem, match="dependency order"):
        SystemExecutionPlan.from_dict(wire)
    wire = json.loads(json.dumps(plan.to_dict()))
    wire["nodes"][0]["configuration_digest"] = sha("tampered")
    assert SystemExecutionPlan.from_dict(wire).digest != plan.digest


# ------------------------------------------------------------------------------------------ state
def _state():
    request = _req()
    spec = request.initial_state
    return SystemState.initial(spec, request_digest=request.digest, system_digest=request.system.digest, environment_digest=request.environment.digest)


def test_state_advances_as_a_digest_chain_and_never_reshapes_or_reverses():
    s0 = _state()
    new = OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(305, "K"), UNKNOWN),))
    s1 = s0.advance(time=Quantity(10, "s"), updates=(new,), produced_by="thermal")
    assert s1.sequence == 1 and s1.previous_digest == s0.digest and s1.digest != s0.digest
    assert SystemState.from_dict(s1.to_dict()) == s1
    with pytest.raises(InvalidScientificProblem, match="backwards"):
        s1.advance(time=Quantity(5, "s"), updates=(new,), produced_by="x")
    with pytest.raises(InvalidScientificProblem, match="unknown owner"):
        s0.advance(time=Quantity(1, "s"), updates=(OwnerState("ghost", "component", new.values),), produced_by="x")
    other = OwnerState("cell", "component", (InitialStateValue("pressure", Quantity(1, "Pa"), UNKNOWN),))
    with pytest.raises(InvalidScientificProblem, match="variable set"):
        s0.advance(time=Quantity(1, "s"), updates=(other,), produced_by="x")
    wrong_dim = OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(1, "Pa"), UNKNOWN),))
    with pytest.raises(InvalidScientificProblem, match="changed dimension"):
        s0.advance(time=Quantity(1, "s"), updates=(wrong_dim,), produced_by="x")


def test_a_state_value_needs_its_uncertainty_stated_and_an_owner_needs_values():
    with pytest.raises(InvalidScientificProblem):
        InitialStateValue("t", Quantity(1, "K"), None)
    with pytest.raises(InvalidScientificProblem, match="empty state is not"):
        OwnerState("cell", "component", ())


def test_only_the_initial_state_may_lack_a_previous_digest():
    s0 = _state()
    wire = s0.to_dict()
    wire["sequence"] = 3
    with pytest.raises(InvalidScientificProblem, match="no previous digest"):
        SystemState.from_dict(wire)
