"""Phase 1 BR4 -- exact coupling-window boundaries.

Window boundaries are exact rationals under the repository's same-instant rule
(``scenarios.timeline.exact_seconds``); a nominal window ends at
``start + k * width`` computed exactly, never at a float running sum.  The only
resolution a schedule is held to is the float64 spacing of its own values.

NOT RUN (Phase 1 build phase): docs/work/DEFERRED_VALIDATION.md, DV-38.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsExecutionError, MultiphysicsRuntime,
)
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scenarios import ScenarioEvent
from engcore.scientific.multiphysics import (
    CheckpointRecord, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")
DIGEST = "a" * 64


def _runtime(end, window, max_windows=100000):
    spec = ParticipantSpec("p", "m", "1", "r", "1", "s", "1", "a", "1",
                           (PortDefinition("x", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K"),),
                           transient=True, checkpointable=True, deterministic_restore=True)
    participant = CallbackParticipant(
        spec, initialize=lambda *_: InitializationResult({"x": Quantity(300, "K")}, {"x": UNKNOWN}),
        advance=lambda r: AdvanceResult(r.end, {"x": Quantity(300, "K")}, {"x": UNKNOWN}, 1, True),
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord("p", t, "0" * 64, True), None),
        restore=lambda cp: None)
    plan = CouplingPlan("grid", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(end, "s"), Quantity(window, "s"), max_windows=max_windows))
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(PhysicsGraph("grid", (spec,), ()), plan, {"p": participant},
                               resolver=BulkDataResolver(store), store=store)


def _ends(run):
    return [w.end.magnitude_in("s") for w in run.windows]


def test_ten_windows_of_a_tenth_end_exactly_at_the_horizon():
    run = _runtime(1.0, 0.1).run("tenths", external_inputs={})
    assert _ends(run) == [float(Fraction(k, 10)) for k in range(1, 11)]
    assert run.ended_at.magnitude_in("s") == 1.0
    assert "_time_grid" not in run.final_outputs


def test_a_long_horizon_has_no_drift_and_no_sliver_window():
    run = _runtime(100.0, 0.1).run("long", external_inputs={})
    assert len(run.windows) == 1000
    assert _ends(run)[-1] == 100.0
    assert _ends(run) == [float(Fraction(k, 10)) for k in range(1, 1001)]


def test_a_true_remainder_is_a_window_of_its_own():
    run = _runtime(1.0, 0.3).run("remainder", external_inputs={})
    assert _ends(run) == [0.3, 0.6, 0.9, 1.0]
    assert "_time_grid" not in run.final_outputs


def test_a_sub_resolution_remainder_is_absorbed_and_recorded():
    # 3 * 0.3333333333333333 = 0.9999999999999999 exactly: the 1e-16 s left is float64, not schedule
    run = _runtime(1.0, 0.3333333333333333).run("thirds", external_inputs={})
    assert len(run.windows) == 3
    assert _ends(run)[-1] == 1.0
    events = run.final_outputs["_time_grid"]["events"]
    assert [e["action"] for e in events] == ["absorbed_sub_resolution_remainder"]


def test_an_event_moves_the_grid_and_lands_exactly():
    run = _runtime(0.6, 0.1).run("event", external_inputs={}, scenario_digest=DIGEST,
                                 scheduled_events=(ScenarioEvent("cut", Quantity(0.25, "s")),))
    assert _ends(run) == [0.1, 0.2, 0.25, 0.35, 0.45, 0.55, 0.6]
    reached = {item.event_id: item.boundary_index for item in run.reached_scheduled_events}
    assert reached == {"cut": 3}


def test_an_event_within_float_resolution_of_a_grid_point_is_the_grid_point_window():
    # 0.30000000000000004 is the float sum 0.1 + 0.2; it is absorbed into the window ending there
    run = _runtime(0.5, 0.1).run("near", external_inputs={}, scenario_digest=DIGEST,
                                 scheduled_events=(ScenarioEvent("near", Quantity(0.30000000000000004, "s")),))
    assert _ends(run)[:3] == [0.1, 0.2, 0.30000000000000004]
    assert all(b - a > 1e-12 for a, b in zip([0.0] + _ends(run), _ends(run)))


def test_two_events_one_float_apart_are_refused():
    events = (ScenarioEvent("a", Quantity(0.25, "s")), ScenarioEvent("b", Quantity(0.25000000000000006, "s")))
    with pytest.raises(MultiphysicsExecutionError, match="cannot be represented consistently"):
        _runtime(0.5, 0.1).run("pair", external_inputs={}, scenario_digest=DIGEST, scheduled_events=events)


def test_max_windows_still_bounds_the_run():
    with pytest.raises(MultiphysicsExecutionError, match="max_windows"):
        _runtime(1.0, 0.1, max_windows=5).run("bounded", external_inputs={})


def test_an_identical_rerun_produces_an_identical_record():
    first = _runtime(1.0, 0.3333333333333333).run("same", external_inputs={})
    second = _runtime(1.0, 0.3333333333333333).run("same", external_inputs={})
    assert first.to_dict() == second.to_dict()
