"""OD-27: a coupled run is admitted only under the scenario its system execution is authorized for.

``MultiphysicsAuthority.execute`` used to check the run's id, graph and plan but never its scenario, so a
``run_kwargs`` -- or a runtime -- that bound the run to another scenario still produced a SUCCEEDED node and a
committed state whose transition receipts named the wrong scenario. Every run here is a genuine
``MultiphysicsRuntime`` execution (BR7 refuses anything else); the adversaries substitute scenario identity, not
the record type.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitializationResult, InitialStateDefinition, InitialStateReceipt, MultiphysicsRuntime,
)
from engcore.scientific.multiphysics import (
    CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, TimePolicy,
)
from engcore.scientific.multiphysics.receipts import StateVariableValue
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport, ExecutionProfile, MultiphysicsAuthority, NodeKind, NodeOutputSpec, NodeSpec, NodeStatus, OwnerState,
    RequestedObservable, RunStatus, SystemExecutor,
)
from tests.system_runtime_fixtures import UNKNOWN, build, scenario, sha

KNOWN = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, "K"), source="declared", method="declared")
OTHER_SCENARIO = scenario("2").digest  # a valid, different scenario of the same family


class _Body:
    """One transient participant on a real graph and explicit plan; counts how often it actually advanced."""

    def __init__(self) -> None:
        self.advanced = 0
        unknown_output = Uncertainty.unknown("coupled-run output: the participant states no uncertainty")
        self.spec = ParticipantSpec(
            "body", "lumped-body", "1", "closed-form", "1", "test-solver", "1", "test-adapter", "1",
            (PortDefinition("temperature", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K"),), transient=True,
        )
        held = {"value": InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN)}

        def digest(value):
            return hashlib.sha256(json.dumps(value.to_dict(), sort_keys=True).encode()).hexdigest()

        def initialize(_instant, _inputs, _uq):
            held["value"] = InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN)
            return InitializationResult({"temperature": held["value"].value}, {"temperature": unknown_output})

        def initialize_state(instant, state, _inputs, _uq):
            held["value"] = state["temperature"]
            return InitializationResult({"temperature": held["value"].value}, {"temperature": unknown_output},
                                        initial_state_receipt=InitialStateReceipt("body", instant, (state["temperature"],),
                                                                                  digest(state["temperature"])))

        def advance(request):
            self.advanced += 1
            held["value"] = InitialStateValue("temperature", Quantity(305.0, "K"), KNOWN)
            return AdvanceResult(request.end, {"temperature": held["value"].value}, {"temperature": unknown_output}, 1, True)

        self.participant = CallbackParticipant(
            self.spec, initialize=initialize, advance=advance,
            initial_state_definitions=(InitialStateDefinition("temperature", "K"),), initialize_state=initialize_state,
            state_identity=lambda _instant: digest(held["value"]),
            public_state=lambda _instant: (StateVariableValue("temperature", held["value"].value, held["value"].uncertainty),),
        )

    def runtime(self) -> MultiphysicsRuntime:
        graph = PhysicsGraph("od27-coupled", (self.spec,), ())
        plan = CouplingPlan("od27-plan", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                            TimePolicy(Quantity(0.0, "s"), Quantity(1800.0, "s"), Quantity(1800.0, "s")))
        store = InMemoryBulkStore()
        return MultiphysicsRuntime(graph, plan, {"body": self.participant}, resolver=BulkDataResolver(store), store=store)


class _Substituting:
    """An adversarial runtime: the real graph and plan, but it decides the run's scenario itself.

    ``bind`` returns the scenario digest it actually runs under, whatever ``run_kwargs`` said; ``replay`` hands back
    a genuine record produced earlier (for another scenario) under the run id it is asked for.
    """

    def __init__(self, inner: MultiphysicsRuntime, *, bind=None, replay=None) -> None:
        self.inner, self.graph, self.plan, self.participants = inner, inner.graph, inner.plan, inner.participants
        self._bind, self._replay, self.calls = bind, replay, 0

    def run(self, run_id, **kwargs):
        self.calls += 1
        if self._replay is not None and self.calls > 1:
            return self._replay(run_id)
        if self._bind is not None:
            kwargs = {**kwargs, "scenario_digest": self._bind(kwargs.get("scenario_digest", ""))}
        return self.inner.run(run_id, **kwargs)


def _request(runtime, run_kwargs, *, owners=True):
    request, context, _ = build()
    auth = MultiphysicsAuthority("od27-coupled", runtime, run_kwargs=run_kwargs, outputs={"temperature": "body.temperature"},
                                 state_owners={"body": "cell"} if owners else {},
                                 applicability=lambda run, call: (ApplicabilityReport("ok", "within", sha("e")),))
    context.authorities.register(auth)
    prior = OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(300.0, "K"), KNOWN),))
    node = NodeSpec("coupled", NodeKind.MULTIPHYSICS_EXECUTION, auth.ref, (NodeOutputSpec("temperature", "K"),),
                    commits_state=owners, writes_owners=("cell",) if owners else (), applicability_checks=("ok",))
    request = replace(request, nodes=(node,), observables=(RequestedObservable("t", "coupled", "temperature", "K"),),
                      constraint_observations=(), profile=ExecutionProfile(("multiphysics",)),
                      initial_state=replace(request.initial_state, owners=(prior,) if owners else request.initial_state.owners))
    return request, context


def _authorized(call):
    return {"external_inputs": {}, "scenario_digest": call.context.scenario.digest}


def _refused_and_nothing_exposed(result, reason):
    receipt = result.receipt("coupled")
    assert receipt.status is NodeStatus.FAILED and reason in receipt.reason, receipt.reason
    assert result.node_outputs.get("coupled") is None
    assert result.observable("t").value is None
    assert len(result.state_history) == 1  # the initial state only: nothing was committed
    assert result.final_state.owner("cell").values[0].value.magnitude == pytest.approx(300.0)


# --------------------------------------------------------------------------------------------------- admitted
@pytest.mark.parametrize("spelling", [str.lower, str.upper], ids=["lower", "upper"])
def test_the_authorized_scenario_is_admitted_and_commits(spelling):
    body = _Body()
    request, context = _request(body.runtime(), lambda call: {"external_inputs": {},
                                                               "scenario_digest": spelling(call.context.scenario.digest)})
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in result.node_receipts]
    assert result.final_state.owner("cell").values[0].value.magnitude == pytest.approx(305.0)
    assert body.advanced == 1


def test_a_run_that_does_not_depend_on_any_scenario_is_admitted_when_it_names_the_authorized_one():
    """No state, inputs, events or QoI from the scenario: the run still names the scenario it executes under."""
    body = _Body()
    request, context = _request(body.runtime(), _authorized, owners=False)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in result.node_receipts]
    assert result.node_outputs["coupled"]["temperature"].value.magnitude == pytest.approx(305.0)


def test_an_unbound_run_is_refused_inside_an_authorized_execution_even_without_scenario_evidence():
    """Review M1: absence of scenario evidence on a record is no proof of independence (a runtime factory can bake
    scenario-derived state or inputs into participants), so inside an execution with an authorized scenario a run
    that names none is refused -- before anything runs."""
    body = _Body()
    request, context = _request(body.runtime(), lambda call: {"external_inputs": {}}, owners=False)
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("coupled")
    assert receipt.status is NodeStatus.FAILED and "names no scenario digest" in receipt.reason
    assert result.node_outputs.get("coupled") is None and body.advanced == 0


# --------------------------------------------------------------------------------------------------- refused before the run
def test_a_different_valid_scenario_digest_is_refused_before_anything_runs():
    body = _Body()
    request, context = _request(body.runtime(), lambda call: {"external_inputs": {}, "scenario_digest": OTHER_SCENARIO})
    assert OTHER_SCENARIO != context.scenario.digest
    result = SystemExecutor(context).run(request)
    _refused_and_nothing_exposed(result, "not the authorized scenario")
    assert body.advanced == 0


@pytest.mark.parametrize("kwargs", [{"external_inputs": {}}, {"external_inputs": {}, "scenario_digest": ""},
                                    {"external_inputs": {}, "scenario_digest": "   "}], ids=["missing", "empty", "blank"])
def test_a_scenario_driven_run_without_a_scenario_digest_is_refused_before_anything_runs(kwargs):
    body = _Body()
    request, context = _request(body.runtime(), lambda call: dict(kwargs))
    result = SystemExecutor(context).run(request)
    _refused_and_nothing_exposed(result, "names no scenario digest")
    assert body.advanced == 0


def test_a_malformed_scenario_digest_is_refused_before_anything_runs():
    body = _Body()
    request, context = _request(body.runtime(), lambda call: {"external_inputs": {}, "scenario_digest": "not-a-digest"})
    result = SystemExecutor(context).run(request)
    _refused_and_nothing_exposed(result, "not the authorized scenario")
    assert body.advanced == 0


# --------------------------------------------------------------------------------------------------- refused on the record
def test_correct_run_id_graph_and_plan_but_a_substituted_scenario_is_refused_and_commits_nothing():
    """The runtime ignores the authorized digest it was given and runs (genuinely) under another scenario."""
    body = _Body()
    runtime = _Substituting(body.runtime(), bind=lambda _given: OTHER_SCENARIO)
    request, context = _request(runtime, _authorized)
    result = SystemExecutor(context).run(request)
    _refused_and_nothing_exposed(result, "is bound to scenario")
    assert body.advanced == 1  # it did run -- under the wrong scenario -- and nothing of it was admitted


def test_a_repeated_execution_that_returns_a_record_of_another_scenario_is_refused():
    body = _Body()
    inner = body.runtime()
    recorded = {}

    def replay(run_id):
        # a genuine record of the same graph and plan under the requested run id, produced for another scenario
        recorded["run"] = inner.run(run_id, external_inputs={}, scenario_digest=OTHER_SCENARIO, initial_state={
            "body": {"temperature": InitialStateValue("temperature", Quantity(300.0, "K"), KNOWN)}})
        return recorded["run"]

    runtime = _Substituting(inner, replay=replay)
    first_request, first_context = _request(runtime, _authorized)
    assert SystemExecutor(first_context).run(first_request).status is RunStatus.SUCCEEDED
    second_request, second_context = _request(runtime, _authorized)
    result = SystemExecutor(second_context).run(second_request)
    assert recorded["run"].scenario_digest == OTHER_SCENARIO
    _refused_and_nothing_exposed(result, "is bound to scenario")


def test_the_scenario_check_runs_before_outputs_artifacts_and_extractors():
    """Admission precedes publication: no extractor or artifact hook is ever called for a wrong-scenario run."""
    body = _Body()
    runtime = _Substituting(body.runtime(), bind=lambda _given: OTHER_SCENARIO)
    request, context = build()[:2]
    touched = []
    auth = MultiphysicsAuthority("od27-hooks", runtime, run_kwargs=_authorized, outputs={}, state_owners={"body": "cell"},
                                 extractors={"peak": lambda run, call: touched.append("extractor") or Quantity(305.0, "K")},
                                 artifacts=lambda run, call: touched.append("artifacts") or (),
                                 providers=lambda run: touched.append("providers") or (),
                                 applicability=lambda run, call: touched.append("applicability") or (
                                     ApplicabilityReport("ok", "within", sha("e")),))
    context.authorities.register(auth)
    prior = OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(300.0, "K"), KNOWN),))
    node = NodeSpec("coupled", NodeKind.MULTIPHYSICS_EXECUTION, auth.ref, (NodeOutputSpec("peak", "K"),), commits_state=True,
                    writes_owners=("cell",), applicability_checks=("ok",))
    request = replace(request, nodes=(node,), observables=(RequestedObservable("t", "coupled", "peak", "K"),),
                      constraint_observations=(), profile=ExecutionProfile(("multiphysics",)),
                      initial_state=replace(request.initial_state, owners=(prior,)))
    result = SystemExecutor(context).run(request)
    assert result.receipt("coupled").status is NodeStatus.FAILED and "is bound to scenario" in result.receipt("coupled").reason
    assert touched == []


class _Rewriting(_Substituting):
    """Runs genuinely under another scenario, then rewrites a field of the returned record after construction."""

    def __init__(self, inner, rewrite):
        super().__init__(inner, bind=lambda _given: OTHER_SCENARIO)
        self._rewrite = rewrite

    def run(self, run_id, **kwargs):
        record = super().run(run_id, **kwargs)
        self._rewrite(record)
        return record


def test_a_record_whose_digest_was_rewritten_to_the_authorized_one_is_refused_on_its_receipts():
    """Review m1: the top-level digest alone is not trusted; every state transition must name the authorized scenario."""
    body = _Body()
    holder = {}
    runtime = _Rewriting(body.runtime(), lambda record: object.__setattr__(record, "scenario_digest", holder["authorized"]))
    request, context = _request(runtime, _authorized)
    holder["authorized"] = context.scenario.digest
    result = SystemExecutor(context).run(request)
    _refused_and_nothing_exposed(result, "receipts bound to another scenario")


def test_a_record_whose_digest_was_cleared_is_refused():
    """Review m2: a scenario-driven record stripped of its digest after construction is not admitted."""
    body = _Body()
    runtime = _Rewriting(body.runtime(), lambda record: object.__setattr__(record, "scenario_digest", ""))
    request, context = _request(runtime, _authorized)
    result = SystemExecutor(context).run(request)
    _refused_and_nothing_exposed(result, "is bound to scenario none")
