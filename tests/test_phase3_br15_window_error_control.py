"""Phase 3 BR15 -- error-aware coupling windows, recorded clock disagreements, explicit subcycling contract.

The participant integrates y' = -k y with ONE forward-Euler step per window
(k = 1 / s, y(0) = 1 K), so its local error depends on the window width and
the step-doubling difference is known in closed form:

    coarse  y0 (1 - k h)          fine  y0 (1 - k h / 2)^2          |c - f| = y0 (k h)^2 / 4

With atol = 0.1 K and rtol = 0: h = 1 s gives 0.25 K (indicator 2.5, rejected);
h = 0.5 s gives 0.0625 K (0.625, accepted, y = 0.5 K); the remaining window
[0.5, 1] s from y0 = 0.5 K gives 0.03125 K (0.3125, accepted, y = 0.25 K).
The COARSE values are kept: the run is the one the plan scheduled.

NOT RUN (Phase 3 build phase): docs/work/DEFERRED_VALIDATION.md, DV-73..DV-76.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, CouplingWindowNotConverged, InitializationResult, MultiphysicsRuntime,
)
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.execution.multiphysics.runtime import CouplingWindowErrorNotControlled
from engcore.execution.multiphysics.subcycling import INPUT_HOLD, subcycling_contract
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, RelaxationPolicy, TimePolicy, WindowControlPolicy,
)
from engcore.scientific.multiphysics.plan import MonitoredOutput, WindowErrorControl
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test")


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _spec(pid, ports, *, restorable=True, maximum_step=None):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=restorable, deterministic_restore=restorable,
                           maximum_time_step=maximum_step)


def _digest(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()


def _decay(spec, k=1.0):
    """y' = -k y, one forward-Euler step over each requested window."""
    state = {"y": 1.0}

    def advance(request):
        h = request.end.magnitude_in("s") - request.start.magnitude_in("s")
        state["y"] = state["y"] * (1.0 - k * h)
        return AdvanceResult(request.end, {"y": Quantity(state["y"], "K")}, {"y": UNKNOWN}, 1, True)

    def checkpoint(t):
        return RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, _digest(state["y"]), True), state["y"])

    def restore(cp):
        state["y"] = cp.token

    return CallbackParticipant(spec, initialize=lambda *_: InitializationResult({"y": Quantity(1.0, "K")}, {"y": UNKNOWN}),
                               advance=advance, checkpoint=checkpoint, restore=restore)


def _copy(spec, *, end_offset=0.0):
    def advance(request):
        end = request.end if not end_offset else Quantity(math.nextafter(request.end.magnitude_in("s"), math.inf), "s")
        return AdvanceResult(end, {"z": request.inputs["y"]}, {"z": UNKNOWN}, 1, True)

    kwargs = {}
    if spec.checkpointable:
        kwargs = {"checkpoint": lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, "0" * 64, True), None),
                  "restore": lambda cp: None}
    return CallbackParticipant(spec, initialize=lambda *_: InitializationResult({"z": Quantity(1.0, "K")}, {"z": UNKNOWN}),
                               advance=advance, **kwargs)


def _runtime(control, *, end=1.0, restorable_copy=True, clock_offset=False, monitored=("a", "y")):
    a = _spec("a", [_port("y", "output")])
    b = _spec("b", [_port("y", "input"), _port("z", "output")], restorable=restorable_copy)
    graph = PhysicsGraph("decay", (a, b), (CouplingEdge("e", PortRef("a", "y"), PortRef("b", "y")),))
    plan = CouplingPlan("decay", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(end, "s"), Quantity(1, "s")), (), (), RelaxationPolicy(),
                        1, True, window_control=control)
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, {"a": _decay(a), "b": _copy(b, end_offset=clock_offset)},
                               resolver=BulkDataResolver(store), store=store)


def _error_control(atol=0.1, monitored=("a", "y")):
    return WindowErrorControl((MonitoredOutput(monitored[0], monitored[1], Quantity(atol, "K"), 0.0),))


def _control(error_control=None, *, minimum=0.25, subdivisions=4):
    return WindowControlPolicy(Quantity(minimum, "s"), 0.5, subdivisions, error_control=error_control)


# ---- the policy record ------------------------------------------------------------------------------------------


def test_a_monitored_output_needs_a_tolerance_it_can_meet():
    with pytest.raises(InvalidScientificProblem, match="bit for bit"):
        MonitoredOutput("a", "y", Quantity(0.0, "K"), 0.0)
    with pytest.raises(InvalidScientificProblem):
        WindowErrorControl(())


def test_window_control_without_error_control_keeps_its_serialized_form():
    plain = _control()
    assert "error_control" not in plain.to_dict()
    with_error = _control(_error_control())
    assert with_error.to_dict()["error_control"]["indicator"] == "step_doubling_local_difference"
    assert WindowControlPolicy.from_dict(with_error.to_dict()) == with_error


def test_error_control_is_refused_for_a_participant_that_cannot_be_restored():
    with pytest.raises(InvalidScientificProblem, match="deterministic restore"):
        _runtime(_control(_error_control()), restorable_copy=False)


def test_error_control_monitors_outputs_only():
    with pytest.raises(InvalidScientificProblem, match="not an output"):
        _runtime(_control(_error_control(monitored=("b", "y"))))


# ---- step doubling -----------------------------------------------------------------------------------------------


def _events(run, action):
    return [e for e in run.final_outputs["_window_control"]["events"] if e["action"] == action]


def test_a_window_whose_indicator_exceeds_tolerance_is_rejected_as_an_error_not_as_non_convergence():
    run = _runtime(_control(_error_control())).run("decay", external_inputs={})
    assessed = _events(run, "error_indicator")
    assert [round(e["indicator"], 12) for e in assessed] == [2.5, 0.625, 0.3125]
    assert [e["accepted"] for e in assessed] == [False, True, True]
    assert len(_events(run, "rejected_error_indicator")) == 1 and not _events(run, "subdivided")
    assert [(w.start.magnitude, w.end.magnitude) for w in run.windows] == [(0.0, 0.5), (0.5, 1.0)]
    # the coarse values are the run's: 1 -> 0.5 -> 0.25 K
    assert run.final_outputs["a.y"]["magnitude"] == pytest.approx(0.25)
    assert all("not a bound" in e["notice"] for e in assessed)


def test_an_indicator_that_never_meets_tolerance_ends_in_a_retryable_error_failure():
    with pytest.raises(CouplingWindowErrorNotControlled) as raised:
        _runtime(_control(_error_control(atol=1e-6), minimum=0.01, subdivisions=2)).run("decay", external_inputs={})
    assert isinstance(raised.value, CouplingWindowNotConverged)
    assert "error indicator" in str(raised.value)


# ---- schedule-forced short windows and participant clocks --------------------------------------------------------


def test_a_horizon_forced_window_below_minimum_window_is_recorded_not_refused():
    run = _runtime(_control(), end=1.1).run("decay", external_inputs={})
    forced = _events(run, "forced_below_minimum_window")
    assert len(forced) == 1 and forced[0]["start_s"] == 1.0 and forced[0]["minimum_window_s"] == 0.25
    assert len(run.windows) == 2


def test_a_participant_clock_within_the_reporting_tolerance_is_recorded():
    run = _runtime(None, clock_offset=True).run("decay", external_inputs={})
    events = [e for e in run.final_outputs["_time_grid"]["events"] if e["action"] == "participant_clock_disagreement"]
    assert events and events[0]["participant_id"] == "b" and events[0]["difference_s"] > 0.0


def test_a_run_whose_participants_report_exact_ends_records_no_time_grid():
    assert "_time_grid" not in _runtime(None).run("decay", external_inputs={}).final_outputs


# ---- subcycling contract -----------------------------------------------------------------------------------------


def test_the_subcycling_contract_states_the_input_hold_and_the_minimum_substeps():
    a = _spec("a", [_port("y", "output")], maximum_step=Quantity(0.3, "s"))
    b = _spec("b", [_port("y", "input"), _port("z", "output")])
    graph = PhysicsGraph("decay", (a, b), (CouplingEdge("e", PortRef("a", "y"), PortRef("b", "y")),))
    plan = CouplingPlan("decay", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), (), (), RelaxationPolicy(), 1, True)
    contract = subcycling_contract(graph, plan, max_substeps=10).to_dict()
    entry = {item["participant_id"]: item for item in contract["participants"]}
    # ceil(1 / 0.3) = 4 internal steps at least
    assert entry["a"]["minimum_substeps_per_nominal_window"] == 4 and entry["a"]["input_hold"] == INPUT_HOLD
    assert entry["b"]["minimum_substeps_per_nominal_window"] is None
    with pytest.raises(InvalidScientificProblem, match="budget"):
        subcycling_contract(graph, plan, max_substeps=3)
