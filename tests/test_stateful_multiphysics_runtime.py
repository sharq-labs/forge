import hashlib

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitializationResult,
    InitialStateDefinition, InitialStateReceipt, InitialStateValue,
    MultiphysicsRuntime,
)
from engcore.scientific.errors import InvalidScientificProblem, UnitCompatibilityError
from engcore.scientific.multiphysics import (
    CouplingPlan, CouplingScheme, IterationSemantics, MultiphysicsRunRecord,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind,
    PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from engcore.scenarios import ScenarioEvent


def _runtime(*, acknowledge=310.0):
    spec = ParticipantSpec(
        "body", "model", "1", "realization", "1", "solver", "1",
        "adapter", "1",
        (
            PortDefinition("forcing", PortDirection.INPUT, PortKind.SCALAR, "forcing", "K"),
            PortDefinition("temperature", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K"),
        ),
        transient=True,
    )
    held = {"temperature": Quantity(300, "K")}
    unknown = Uncertainty.unknown("state/output uncertainty not quantified")

    def initialize(_instant, _inputs, _uq):
        return InitializationResult({"temperature": held["temperature"]}, {"temperature": unknown})

    def initialize_state(instant, state, _inputs, _uq):
        held["temperature"] = state["temperature"].value
        acknowledged = InitialStateValue(
            "temperature", Quantity(acknowledge, "K"), state["temperature"].uncertainty
        )
        digest = hashlib.sha256(str(acknowledged.to_dict()).encode()).hexdigest()
        return InitializationResult(
            {"temperature": held["temperature"]}, {"temperature": unknown},
            initial_state_receipt=InitialStateReceipt("body", instant, (acknowledged,), digest),
        )

    def advance(request):
        return AdvanceResult(
            request.end, {"temperature": held["temperature"]},
            {"temperature": unknown}, 1, True,
        )

    participant = CallbackParticipant(
        spec, initialize=initialize, advance=advance,
        initial_state_definitions=(InitialStateDefinition("temperature", "K"),),
        initialize_state=initialize_state,
    )
    graph = PhysicsGraph("stateful", (spec,), ())
    plan = CouplingPlan(
        "stateful-plan", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")),
    )
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(
        graph, plan, {"body": participant},
        resolver=BulkDataResolver(store), store=store,
    )


def test_typed_initial_state_changes_output_and_roundtrips_receipt():
    runtime = _runtime()
    state = InitialStateValue(
        "temperature", Quantity(310, "K"), Uncertainty.unknown("initial state uncertainty unknown")
    )
    run = runtime.run(
        "stateful-run",
        external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
        initial_state={"body": {"temperature": state}},
        scenario_digest="b" * 64,
    )

    assert run.final_outputs["body.temperature"]["magnitude"] == 310
    assert run.initial_state_receipts[0].values == (state,)
    # Scenario identity is bound although this scenario declares no event.
    assert run.scenario_digest == "b" * 64
    restored = MultiphysicsRunRecord.from_dict(run.to_dict())
    assert restored.initial_state_receipts == run.initial_state_receipts
    assert restored.final_outputs == run.final_outputs


def test_mismatched_initial_state_acknowledgement_is_refused():
    runtime = _runtime(acknowledge=300.0)
    state = InitialStateValue(
        "temperature", Quantity(310, "K"), Uncertainty.unknown("unknown")
    )
    with pytest.raises(InvalidScientificProblem, match="does not acknowledge exact"):
        runtime.run(
            "bad-state-receipt",
            external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
            initial_state={"body": {"temperature": state}},
            scenario_digest="b" * 64,
        )


def test_initial_state_for_unknown_participant_is_refused():
    state = InitialStateValue(
        "temperature", Quantity(310, "K"), Uncertainty.unknown("unknown")
    )
    with pytest.raises(InvalidScientificProblem, match="outside the execution graph"):
        _runtime().run(
            "unknown-state-owner",
            external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
            initial_state={"not-in-graph": {"temperature": state}},
        )


def test_initial_state_uncertainty_must_match_value_dimension():
    uncertainty = Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(1, "s"),
        method="test fixture",
    )
    with pytest.raises(UnitCompatibilityError, match="incompatible units"):
        InitialStateValue("temperature", Quantity(310, "K"), uncertainty)


def test_scheduled_event_creates_exact_window_boundary_and_receipt():
    event = ScenarioEvent("switch", Quantity(0.5, "s"))
    run = _runtime().run(
        "scheduled-event",
        external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
        scheduled_events=(event,),
        scenario_digest="a" * 64,
    )

    assert [window.end.magnitude_in("s") for window in run.windows] == [0.5, 1.0]
    assert run.scheduled_events[0].event_id == event.event_id
    assert run.reached_scheduled_events[0].boundary_index == 1
    assert "_scheduled_events" not in run.final_outputs


def test_scheduled_event_outside_runtime_horizon_is_refused():
    with pytest.raises(InvalidScientificProblem, match="outside the coupling-plan horizon"):
        _runtime().run(
            "bad-scheduled-event",
            external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
            scheduled_events=(ScenarioEvent("late", Quantity(2, "s")),),
            scenario_digest="a" * 64,
        )
