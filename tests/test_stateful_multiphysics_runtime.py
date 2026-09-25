import hashlib
from dataclasses import replace

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitializationResult,
    InitialStateDefinition, InitialStateReceipt, InitialStateValue,
    MultiphysicsRuntime,
)
from engcore.scientific.errors import InvalidScientificProblem, UnitCompatibilityError
from engcore.scientific.ir.constraints import ConstraintCheck
from engcore.scientific.multiphysics import (
    CouplingPlan, CouplingScheme, IterationSemantics, MultiphysicsRunRecord,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind,
    PortRef, QuantityOfInterestRecord, ScenarioInputReceipt, TerminationReceipt,
    TimePolicy,
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
    held["state_digest"] = hashlib.sha256(
        str(
            InitialStateValue(
                "temperature",
                held["temperature"],
                Uncertainty.unknown("initial state uncertainty unknown"),
            ).to_dict()
        ).encode()
    ).hexdigest()
    unknown = Uncertainty.unknown("state/output uncertainty not quantified")

    def initialize(_instant, _inputs, _uq):
        return InitializationResult({"temperature": held["temperature"]}, {"temperature": unknown})

    def initialize_state(instant, state, _inputs, _uq):
        held["temperature"] = state["temperature"].value
        acknowledged = InitialStateValue(
            "temperature", Quantity(acknowledge, "K"), state["temperature"].uncertainty
        )
        digest = hashlib.sha256(str(acknowledged.to_dict()).encode()).hexdigest()
        held["state_digest"] = digest
        return InitializationResult(
            {"temperature": held["temperature"]}, {"temperature": unknown},
            initial_state_receipt=InitialStateReceipt("body", instant, (acknowledged,), digest),
        )

    def state_identity(_instant):
        return held["state_digest"]

    def advance(request):
        return AdvanceResult(
            request.end, {"temperature": held["temperature"]},
            {"temperature": unknown}, 1, True,
        )

    participant = CallbackParticipant(
        spec, initialize=initialize, advance=advance,
        initial_state_definitions=(InitialStateDefinition("temperature", "K"),),
        initialize_state=initialize_state,
        state_identity=state_identity,
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


def _basic_run(run_id="run-record-integrity", *, scenario_digest=""):
    return _runtime().run(
        run_id,
        external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
        scenario_digest=scenario_digest,
    )


def test_run_record_refuses_end_after_plan_horizon():
    run = _basic_run("after-horizon")
    with pytest.raises(InvalidScientificProblem, match="ended after"):
        replace(run, ended_at=Quantity(2, "s"))


def test_termination_receipt_must_match_actual_run_end_even_at_nominal_horizon():
    digest = "d" * 64
    run = _basic_run("termination-at-horizon", scenario_digest=digest)
    receipt = TerminationReceipt(
        "stop",
        1,
        run.ended_at,
        ConstraintCheck(
            "stop",
            True,
            Quantity(0, "K"),
            Quantity(300, "K"),
        ),
        "fixture stop",
        digest,
    )
    bound = replace(run, termination=receipt)
    assert bound.termination.instant == bound.ended_at

    stale = replace(receipt, boundary_index=0, instant=run.started_at)
    with pytest.raises(
        InvalidScientificProblem,
        match="instant disagrees with run ended_at",
    ):
        replace(bound, termination=stale)


def test_each_iteration_must_record_exactly_one_step_for_every_graph_participant():
    run = _basic_run("missing-participant-step")
    window = run.windows[0]
    iteration = window.iterations[0]
    forged_iteration = replace(iteration, participant_steps=())
    forged_window = replace(window, iterations=(forged_iteration,))
    with pytest.raises(InvalidScientificProblem, match="exactly one step"):
        replace(run, windows=(forged_window,))


def test_participant_step_must_span_its_coupling_window():
    run = _basic_run("short-participant-step")
    window = run.windows[0]
    iteration = window.iterations[0]
    step = iteration.participant_steps[0]
    forged_step = replace(step, start=Quantity(0.1, "s"))
    forged_iteration = replace(iteration, participant_steps=(forged_step,))
    forged_window = replace(window, iterations=(forged_iteration,))
    with pytest.raises(InvalidScientificProblem, match="does not span coupling window"):
        replace(run, windows=(forged_window,))


def test_scheduled_event_inside_executed_horizon_requires_reached_receipt():
    event = ScenarioEvent("midpoint", Quantity(0.5, "s"))
    run = _runtime().run(
        "missing-reached-event",
        external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
        scheduled_events=(event,),
        scenario_digest="e" * 64,
    )
    with pytest.raises(InvalidScientificProblem, match="no reached-event receipt"):
        replace(run, reached_scheduled_events=())


def test_state_transition_chain_is_bound_to_initial_state_and_previous_window():
    state = InitialStateValue(
        "temperature",
        Quantity(310, "K"),
        Uncertainty.unknown("initial state uncertainty unknown"),
    )
    run = _runtime().run(
        "broken-state-chain",
        external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
        initial_state={"body": {"temperature": state}},
        scheduled_events=(ScenarioEvent("midpoint", Quantity(0.5, "s")),),
        scenario_digest="f" * 64,
    )
    assert len(run.state_transitions) == 2
    assert run.state_transitions[0].start_state_digest == run.initial_state_receipts[0].state_digest

    second = replace(
        run.state_transitions[1],
        start_state_digest="0" * 64,
    )
    with pytest.raises(InvalidScientificProblem, match="state chain breaks"):
        replace(
            run,
            state_transitions=(run.state_transitions[0], second),
        )


def test_scenario_input_receipt_is_checked_against_target_port_contract():
    digest = "1" * 64
    run = _basic_run("bad-scenario-input-receipt", scenario_digest=digest)
    forged = ScenarioInputReceipt(
        "forcing",
        PortRef("body", "forcing"),
        0,
        run.started_at,
        "segment",
        Quantity(1, "V"),
        Uncertainty.unknown("fixture"),
        digest,
    )
    with pytest.raises(UnitCompatibilityError):
        replace(run, scenario_input_receipts=(forged,))


def test_quantity_of_interest_receipt_is_checked_against_output_port_contract():
    digest = "2" * 64
    run = _basic_run("bad-qoi-receipt", scenario_digest=digest)
    forged = QuantityOfInterestRecord(
        "temperature-qoi",
        "temperature",
        PortRef("body", "temperature"),
        run.ended_at,
        Quantity(1, "V"),
        Uncertainty.unknown("fixture"),
        digest,
    )
    with pytest.raises(UnitCompatibilityError):
        replace(run, quantities_of_interest=(forged,))
