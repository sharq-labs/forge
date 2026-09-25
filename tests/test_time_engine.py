"""Time Engine (BIG 2) focused adversarial tests.

Replay, roundtrip and digest agreement below are reproducibility checks only;
none of them is validation of any physical claim.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime,
)
from engcore.scenarios import (
    CycleHistory, CycleRecord, HistoryEntry, NamedQuantity, QuantityHistory,
    ScenarioEvent, ScenarioSegment, ScenarioSpecification, TimeBasis,
    TimeBasisKind, Timeline, TimelineEvent, TimelineEventKind, TimePoint,
    TimeSample, TimeSeriesInput, TimeWindow, ValueStatus, WindowClosure,
    compare_replay, order_events,
)
from engcore.scenarios.contracts import InterpolationKind
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec,
    PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.multiphysics.receipts import StateTransitionReceipt
from engcore.scientific.multiphysics.state import CheckpointRecord
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

B = "elapsed"
BASIS = TimeBasis(B, TimeBasisKind.ELAPSED, "scenario-start")


def tp(seconds, basis=B):
    return TimePoint(basis, Quantity(seconds, "second"))


def win(a, b, closure=WindowClosure.HALF_OPEN):
    return TimeWindow(tp(a), tp(b), closure)


def horizon(a=0, b=10):
    return win(a, b, WindowClosure.CLOSED)


def std(value, unit):
    return Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(value, unit), method="fixture")


def D(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


# ---- basis / points / windows ------------------------------------------------


def test_time_point_requires_a_basis_and_a_time_quantity():
    with pytest.raises(InvalidScientificProblem, match="basis"):
        TimePoint(None, Quantity(1, "s"))
    with pytest.raises(InvalidScientificProblem, match="basis"):
        TimePoint("", Quantity(1, "s"))
    with pytest.raises(InvalidScientificProblem, match="time Quantity"):
        TimePoint(B, Quantity(1, "m"))
    with pytest.raises(InvalidScientificProblem, match="time Quantity"):
        TimePoint(B, 1.0)


def test_time_basis_requires_origin_and_utc_epoch_is_fixed():
    with pytest.raises(InvalidScientificProblem, match="origin"):
        TimeBasis("b", TimeBasisKind.ELAPSED, "")
    with pytest.raises(InvalidScientificProblem, match="ABSOLUTE_UTC"):
        TimeBasis("utc", TimeBasisKind.ABSOLUTE_UTC, "2000-01-01T00:00:00Z")
    with pytest.raises(InvalidScientificProblem, match="unsupported time basis"):
        TimeBasis("b", "sidereal", "x")


def test_cross_basis_ordering_is_refused_not_guessed():
    assert tp(1) < tp(2)
    assert tp(60) == TimePoint(B, Quantity(1, "minute"))
    with pytest.raises(InvalidScientificProblem, match="different bases"):
        tp(1) < tp(2, "other")
    with pytest.raises(InvalidScientificProblem, match="different bases"):
        TimeWindow(tp(0), tp(1, "other"))


def test_inconsistent_windows_are_refused():
    with pytest.raises(InvalidScientificProblem, match="strictly after"):
        win(5, 5)
    with pytest.raises(InvalidScientificProblem, match="strictly after"):
        win(5, 1)
    with pytest.raises(InvalidScientificProblem, match="closure"):
        TimeWindow(tp(0), tp(1), "open")


def test_window_ownership_matches_segment_rule():
    w = win(0, 10)
    assert w.contains(tp(0)) and not w.contains(tp(10))
    assert horizon().contains(tp(10))
    assert not win(0, 5).overlaps(win(5, 10))
    assert horizon().covers(win(9, 10))


# ---- events ------------------------------------------------------------------


def test_ambiguous_order_sensitive_events_are_refused():
    a = TimelineEvent("a", TimelineEventKind.STATE_CHANGE_REQUEST, tp(2), "valve")
    b = TimelineEvent("b", TimelineEventKind.DISCONTINUITY, tp(2), "load")
    with pytest.raises(InvalidScientificProblem, match="ambiguous event ordering"):
        order_events((a, b))
    a1 = TimelineEvent("a", TimelineEventKind.STATE_CHANGE_REQUEST, tp(2), "valve", 1)
    b1 = TimelineEvent("b", TimelineEventKind.DISCONTINUITY, tp(2), "load", 1)
    with pytest.raises(InvalidScientificProblem, match="distinct"):
        order_events((a1, b1))
    b0 = TimelineEvent("b", TimelineEventKind.DISCONTINUITY, tp(2), "load", 0)
    assert [e.event_id for e in order_events((a1, b0))] == ["b", "a"]


def test_synchronization_markers_commute_and_order_is_input_independent():
    s1 = TimelineEvent("s1", TimelineEventKind.SCHEDULED_SYNCHRONIZATION, tp(2))
    s2 = TimelineEvent("s2", TimelineEventKind.SCHEDULED_SYNCHRONIZATION, tp(2))
    c = TimelineEvent("c", TimelineEventKind.STATE_CHANGE_REQUEST, tp(2), "valve")
    assert order_events((s2, c, s1)) == order_events((c, s1, s2))


def test_order_sensitive_event_requires_subject_and_unique_ids():
    with pytest.raises(InvalidScientificProblem, match="subject_id"):
        TimelineEvent("x", TimelineEventKind.DISCONTINUITY, tp(1))
    e = TimelineEvent("x", TimelineEventKind.SCHEDULED_SYNCHRONIZATION, tp(1))
    with pytest.raises(InvalidScientificProblem, match="duplicate"):
        order_events((e, e))


def test_event_outside_horizon_or_on_foreign_basis_is_refused():
    with pytest.raises(InvalidScientificProblem, match="outside"):
        Timeline("t", BASIS, horizon(), events=(TimelineEvent("x", "scheduled_synchronization", tp(11)),))
    with pytest.raises(InvalidScientificProblem, match="basis"):
        Timeline("t", BASIS, horizon(), events=(TimelineEvent("x", "scheduled_synchronization", tp(1, "other")),))


# ---- histories -------------------------------------------------------------


def _usage():
    return QuantityHistory(
        "power", "usage", "power", "W",
        (
            HistoryEntry(win(0, 2), NamedQuantity("power", Quantity(10, "W"), std(1, "W"))),
            HistoryEntry(win(2, 4), NamedQuantity("power", Quantity(20, "W"), std(2, "W"))),
            HistoryEntry(win(6, 8), NamedQuantity("power", Quantity(5, "W"))),
        ),
    )


def test_history_gap_is_unknown_never_zero():
    h = _usage()
    assert h.value_at(tp(1)).value.value == Quantity(10, "W")
    gap = h.value_at(tp(5))
    assert gap.status is ValueStatus.UNKNOWN and gap.value is None
    assert h.value_at(tp(4)).status is ValueStatus.UNKNOWN  # [2,4) does not own 4


def test_integral_over_gap_is_unknown():
    result = _usage().integrate(win(0, 7))
    assert result.status is ValueStatus.UNKNOWN
    assert "(4.0, 6.0)" in result.reason


def test_integral_uncertainty_bound_and_unknown_propagation():
    h = _usage()
    result = h.integrate(win(1, 3))
    assert result.status is ValueStatus.KNOWN
    assert result.value.value.magnitude == pytest.approx(10 * 1 + 20 * 1)
    assert result.value.value.units == Quantity(1, "W*s").units
    assert result.value.uncertainty.kind is UncertaintyKind.STANDARD
    assert result.value.uncertainty.standard_uncertainty.magnitude == pytest.approx(1 + 2)
    unknown_part = h.integrate(win(6, 8))
    assert unknown_part.status is ValueStatus.KNOWN
    assert unknown_part.value.uncertainty.kind is UncertaintyKind.UNKNOWN


def test_affine_unit_integral_is_unknown():
    h = QuantityHistory("t", "exposure", "ambient", "degC", (HistoryEntry(win(0, 1), NamedQuantity("ambient", Quantity(20, "degC"))),))
    assert h.integrate(win(0, 1)).status is ValueStatus.UNKNOWN


def test_history_overlap_wrong_quantity_and_unsupported_representation_refused():
    with pytest.raises(InvalidScientificProblem, match="overlapping"):
        QuantityHistory("p", "usage", "p", "W", (
            HistoryEntry(win(0, 2), NamedQuantity("p", Quantity(1, "W"))),
            HistoryEntry(win(1, 3), NamedQuantity("p", Quantity(2, "W"))),
        ))
    with pytest.raises(InvalidScientificProblem, match="names"):
        QuantityHistory("p", "usage", "p", "W", (HistoryEntry(win(0, 2), NamedQuantity("q", Quantity(1, "W"))),))
    with pytest.raises(InvalidScientificProblem, match="representation"):
        QuantityHistory("p", "usage", "p", "W", (HistoryEntry(win(0, 2), NamedQuantity("p", Quantity(1, "W"))),), "linear")
    with pytest.raises(InvalidScientificProblem, match="half-open"):
        HistoryEntry(win(0, 2, WindowClosure.CLOSED), NamedQuantity("p", Quantity(1, "W")))


def test_missing_history_uncertainty_stays_unknown():
    entry = HistoryEntry(win(0, 1), NamedQuantity("p", Quantity(1, "W")))
    assert entry.value.uncertainty.kind is UncertaintyKind.UNKNOWN


# ---- cycles ----------------------------------------------------------------


def _cycles():
    return CycleHistory("charge", "charge_discharge", tuple(
        CycleRecord(f"c{i}", i, win(2 * i, 2 * i + 2)) for i in range(3)
    ))


def test_cycle_counting_never_counts_partial_cycles():
    count = _cycles().count_within(win(1, 6))
    assert count.complete == 2 and count.partial_cycle_ids == ("c0",)


def test_cycle_gaps_and_misordering_refused():
    with pytest.raises(InvalidScientificProblem, match="skips"):
        CycleHistory("h", "k", (CycleRecord("a", 0, win(0, 1)), CycleRecord("b", 2, win(1, 2))))
    with pytest.raises(InvalidScientificProblem, match="order"):
        CycleHistory("h", "k", (CycleRecord("a", 0, win(1, 2)), CycleRecord("b", 1, win(0, 1))))


# ---- interpolation / discontinuities ---------------------------------------


def _linear():
    return TimeSeriesInput("load", (TimeSample(Quantity(0, "s"), Quantity(0, "N")), TimeSample(Quantity(10, "s"), Quantity(10, "N"))), InterpolationKind.LINEAR)


def test_unsupported_interpolation_and_mismatch_refused():
    t = Timeline("t", BASIS, horizon())
    with pytest.raises(InvalidScientificProblem, match="unsupported interpolation"):
        t.input_value_at(_linear(), tp(5), "cubic")
    with pytest.raises(InvalidScientificProblem, match="declares linear"):
        t.input_value_at(_linear(), tp(5), "step")
    assert t.input_value_at(_linear(), tp(5), "linear").magnitude == pytest.approx(5)


def test_linear_interpolation_across_declared_discontinuity_refused():
    t = Timeline("t", BASIS, horizon(), events=(TimelineEvent("jump", TimelineEventKind.DISCONTINUITY, tp(4), "load"),))
    with pytest.raises(InvalidScientificProblem, match="discontinuity"):
        t.input_value_at(_linear(), tp(5), InterpolationKind.LINEAR)
    # at a declared sample the value is declared, not interpolated
    assert t.input_value_at(_linear(), tp(10), InterpolationKind.LINEAR).magnitude == 10


# ---- state transitions (existing receipt authority) -------------------------


def _tr(i, a, b, start, end, pid="body"):
    return StateTransitionReceipt(pid, i, Quantity(a, "s"), Quantity(b, "s"), D(start), D(end))


def test_state_chain_digest_break_and_time_gap_refused():
    ok = Timeline("t", BASIS, horizon(), initial_state_digests=(("body", D("s0")),),
                  state_transitions=(_tr(0, 0, 1, "s0", "s1"), _tr(1, 1, 2, "s1", "s2")))
    assert ok.state_at("body", tp(2)).state_digest == D("s2")
    assert ok.state_at("body", tp(1.5)).status is ValueStatus.UNKNOWN
    with pytest.raises(InvalidScientificProblem, match="state discontinuity"):
        Timeline("t", BASIS, horizon(), state_transitions=(_tr(0, 0, 1, "s0", "s1"), _tr(1, 1, 2, "sX", "s2")))
    with pytest.raises(InvalidScientificProblem, match="gap"):
        Timeline("t", BASIS, horizon(), state_transitions=(_tr(0, 0, 1, "s0", "s1"), _tr(1, 1.5, 2, "s1", "s2")))
    with pytest.raises(InvalidScientificProblem, match="initial state"):
        Timeline("t", BASIS, horizon(), initial_state_digests=(("body", D("other")),), state_transitions=(_tr(0, 0, 1, "s0", "s1"),))


def test_transition_for_other_scenario_is_refused():
    receipt = StateTransitionReceipt("body", 0, Quantity(0, "s"), Quantity(1, "s"), D("a"), D("b"), scenario_digest=D("other"))
    with pytest.raises(InvalidScientificProblem, match="different scenario"):
        Timeline("t", BASIS, horizon(), scenario_digest=D("mine"), state_transitions=(receipt,))


# ---- serialization / digest / checkpoint / replay --------------------------


def _full():
    return Timeline(
        "full", BASIS, horizon(), D("scenario"),
        events=(TimelineEvent("sync", "scheduled_synchronization", tp(4)),
                TimelineEvent("req", "state_change_request", tp(6), "valve")),
        histories=(_usage(),), cycle_histories=(_cycles(),),
        initial_state_digests=(("body", D("s0")),),
        state_transitions=(_tr(0, 0, 2, "s0", "s1"), _tr(1, 2, 4, "s1", "s2")),
    )


def test_roundtrip_and_digest_are_deterministic_and_order_independent():
    t = _full()
    text = json.dumps(t.to_dict(), sort_keys=True)
    again = Timeline.from_dict(json.loads(text))
    assert again == t and again.digest == t.digest
    shuffled = Timeline("full", BASIS, horizon(), D("scenario"),
                        events=tuple(reversed(t.events)), histories=t.histories,
                        cycle_histories=t.cycle_histories, initial_state_digests=t.initial_state_digests,
                        state_transitions=tuple(reversed(t.state_transitions)))
    assert shuffled.digest == t.digest


def test_from_dict_rejects_extra_keys_and_forged_classification():
    payload = _full().to_dict()
    with pytest.raises(InvalidScientificProblem, match="shape"):
        Timeline.from_dict({**payload, "validated": True})
    event = dict(payload["events"][0], classification="evidence")
    with pytest.raises(InvalidScientificProblem, match="classification"):
        TimelineEvent.from_dict(event)


def test_checkpoint_binds_prefix_and_participant_state():
    t = _full()
    cp = t.checkpoint("cp", tp(4), (CheckpointRecord("body", Quantity(4, "s"), D("s2"), True),))
    t2 = t.with_checkpoint(cp)
    assert Timeline.from_dict(t2.to_dict()) == t2
    with pytest.raises(InvalidScientificProblem, match="state differs"):
        t.checkpoint("bad", tp(4), (CheckpointRecord("body", Quantity(4, "s"), D("wrong"), True),))
    with pytest.raises(InvalidScientificProblem, match="splits"):
        t.checkpoint("mid", tp(3))
    with pytest.raises(InvalidScientificProblem, match="ambiguous"):
        t.checkpoint("clash", tp(6))


def test_checkpoint_from_diverged_timeline_is_refused():
    t = _full()
    cp = t.checkpoint("cp", tp(4))
    other = Timeline("full", BASIS, horizon(), D("scenario"), histories=t.histories,
                     cycle_histories=t.cycle_histories, initial_state_digests=t.initial_state_digests,
                     state_transitions=t.state_transitions)  # the sync event at t=4 is missing
    with pytest.raises(InvalidScientificProblem, match="prefix"):
        other.with_checkpoint(cp)


def test_replay_comparison_detects_divergence_and_refuses_empty_prefix():
    t = _full()
    same = compare_replay(t, Timeline.from_dict(t.to_dict()))
    assert same.consistent and same.to_dict()["classification"] == "replay_consistency_not_validation"
    changed = Timeline("full", BASIS, horizon(), D("scenario"), events=t.events, histories=t.histories,
                       cycle_histories=t.cycle_histories, initial_state_digests=t.initial_state_digests,
                       state_transitions=(_tr(0, 0, 2, "s0", "s1"), _tr(1, 2, 4, "s1", "sZ")))
    diverged = compare_replay(t, changed)
    assert not diverged.consistent and "state_transitions" in diverged.reason
    # divergence after `through` does not affect an earlier prefix
    assert compare_replay(t, changed, through=tp(2)).consistent
    with pytest.raises(InvalidScientificProblem, match="empty prefix"):
        compare_replay(Timeline("e", BASIS, horizon()), Timeline("e", BASIS, horizon()))


# ---- scenario + multiphysics integration -----------------------------------


def _scenario():
    return ScenarioSpecification(
        "mission", "1", Quantity(0, "s"), Quantity(1, "s"),
        segments=(ScenarioSegment("all", Quantity(0, "s"), Quantity(1, "s")),),
        events=(ScenarioEvent("switch", Quantity(0.5, "s")),),
    )


def _runtime():
    spec = ParticipantSpec(
        "body", "model", "1", "realization", "1", "solver", "1", "adapter", "1",
        (PortDefinition("forcing", PortDirection.INPUT, PortKind.SCALAR, "forcing", "K"),
         PortDefinition("temperature", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")),
        transient=True,
    )
    unknown = Uncertainty.unknown("not quantified")
    counter = {"n": 0}

    def initialize(_instant, _inputs, _uq):
        return InitializationResult({"temperature": Quantity(300, "K")}, {"temperature": unknown})

    def advance(request):
        counter["n"] += 1
        return AdvanceResult(request.end, {"temperature": Quantity(300, "K")}, {"temperature": unknown}, 1, True)

    participant = CallbackParticipant(
        spec, initialize=initialize, advance=advance,
        state_identity=lambda _instant: D(f"state{counter['n']}"),
    )
    plan = CouplingPlan("plan", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(PhysicsGraph("g", (spec,), ()), plan, {"body": participant},
                               resolver=BulkDataResolver(store), store=store)


def test_timeline_binds_scenario_and_real_run_receipts():
    scenario = _scenario()
    timeline = Timeline.from_scenario(scenario, timeline_id="mission-timeline", basis=BASIS)
    assert timeline.scenario_digest == scenario.digest
    run = _runtime().run(
        "run", external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
        scheduled_events=scenario.events, scenario_digest=scenario.digest,
    )
    bound = timeline.bind_run(run)
    kinds = [e.kind for e in bound.events]
    assert TimelineEventKind.REACHED_SYNCHRONIZATION in kinds
    assert len(run.state_transitions) == 2  # windows [0,0.5) and [0.5,1]
    assert bound.state_transitions == run.state_transitions
    assert bound.state_at("body", tp(0.5)).status is ValueStatus.KNOWN
    assert Timeline.from_dict(bound.to_dict()).digest == bound.digest
    rerun = _runtime().run(
        "run", external_inputs={PortRef("body", "forcing"): Quantity(0, "K")},
        scheduled_events=scenario.events, scenario_digest=scenario.digest,
    )
    assert compare_replay(bound, timeline.bind_run(rerun)).consistent


def test_run_for_a_different_scenario_cannot_bind():
    scenario = _scenario()
    timeline = Timeline.from_scenario(scenario, timeline_id="t", basis=BASIS)
    run = _runtime().run("run", external_inputs={PortRef("body", "forcing"): Quantity(0, "K")}, scenario_digest=D("other"))
    with pytest.raises(InvalidScientificProblem, match="different scenario"):
        timeline.bind_run(run)


def test_from_scenario_requires_elapsed_basis():
    utc = TimeBasis("utc", TimeBasisKind.ABSOLUTE_UTC, "1970-01-01T00:00:00Z")
    with pytest.raises(InvalidScientificProblem, match="ELAPSED"):
        Timeline.from_scenario(_scenario(), timeline_id="t", basis=utc)
