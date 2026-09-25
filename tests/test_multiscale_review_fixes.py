"""BIG 10 review findings, each pinned by an adversarial test (F1-F4, F6-F8, F11).

Numerical/orchestration facts only; nothing here is validation.
"""

from __future__ import annotations

import importlib.util
import pathlib
from fractions import Fraction
from types import MappingProxyType

import pytest

from engcore.domains.hygrothermal.moisture_uptake import LinearWetnessMoistureUptake
from engcore.coupling import ParticipantStateContract
from engcore.multiscale import (
    AdaptationRule, ComponentStatus, ErrorComponent, EventHandling, FastExecutionResult, FastStateAtMacroStart, FastSystem,
    FastSystemIdentity, LifecycleBinding, MacroCheckpoint, MacroStepPolicy, MultiTimescaleRuntime, OutputSample, OutputSeries,
    RepresentativePolicy, RepresentativeWindow, ResumeRefused, ScaleHierarchy, ScaleLevel, StateOwnership, aggregate,
    compare_resume,
)
from engcore.scenarios import InputBinding, TimelineEvent, TimelineEventKind, TimeWindow
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.execution.multiphysics import InitialStateValue

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("multiscale_reference_rf", str(HERE / "multiscale_reference.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
DAY, HOUR = R.DAY, R.HOUR


# ---- F1: repetition is measured against the resolved period's inputs -------------------------


def test_f1_non_periodic_usage_rejects_the_repetition_and_refines():
    env, _ = R.build_environment(14, off_days=(5, 6))  # heater off all of days 5 and 6
    rt, _, _ = R.build_runtime(14, environment=env, near_threshold=False)
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status == "completed", run.reason
    rejected = [r for s in run.steps for r in s.refinements if r.kind == "representativity_rejected"]
    assert rejected and "supply" in rejected[0].detail and run.accounting["representativity_rejections"] >= 1
    for step in run.steps:
        for e in step.executions:
            rep = e.representative
            if rep.weight != 1:  # every accepted repetition carries its MEASURED deviation, within tolerance
                deviation = dict(rep.input_deviation)
                assert float(deviation["supply"].split()[0]) == 0.0 and float(deviation["air_temperature"].split()[0]) <= 2.0
                # and no repeated tile stands for an off day while resolving an on day
                assert not (rep.represented.start.seconds < 7 * DAY and rep.represented.end.seconds > 5 * DAY)


def test_f5_fractional_windows_repeat_whole_periods_and_resolve_the_remainder():
    tiles = R.REPRESENTATIVE_DAY.build(TimeWindow(R.p(28 * DAY), R.p(30 * DAY + 12 * HOUR)), "m")
    assert [t.weight for t in tiles] == [2, 1]
    assert tiles[0].represented.end.seconds == 30 * DAY and tiles[1].resolved == tiles[1].represented


# ---- F2: fast systems get read-only state; records are immutable snapshots -------------------


class _Mutating(R.ReferenceHeaterSystem):
    def execute(self, request):
        request.slow_state["thermal"]["moisture_content"] = request.slow_state["thermal"]["moisture_content"]
        return super().execute(request)


def test_f2_a_fast_system_cannot_write_back_into_slow_state():
    env, _ = R.build_environment(7)
    rt = R.MultiTimescaleRuntime(run_id="mut", hierarchy=R.hierarchy(), policy=R.policy(near_threshold=False),
                                 fast_system=_Mutating(env), environment=env, aggregations=R.aggregations(), lifecycle=R.lifecycle())
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status == "refused" and "TypeError" in run.reason and not run.steps
    ok, _, _ = R.build_runtime(14, near_threshold=False)
    good = ok.run(initial_slow_state=R.initial_slow())
    assert isinstance(good.steps[0].slow_after, MappingProxyType) and isinstance(good.checkpoints[0].slow_state, MappingProxyType)
    with pytest.raises(TypeError):
        good.steps[0].slow_after["thermal"]["moisture_content"] = None


# ---- F3: the ledger survives resume --------------------------------------------------------


def test_f3_resumed_ledger_remembers_earlier_repetition():
    full, _, _ = R.build_runtime(8, near_threshold=False)
    uninterrupted = full.run(initial_slow_state=R.initial_slow())
    first_rt, _, _ = R.build_runtime(8, near_threshold=False)
    first = first_rt.run(initial_slow_state=R.initial_slow(), until=R.p(7 * DAY))
    second, _, _ = R.build_runtime(8, near_threshold=False)
    resumed = second.resume(MacroCheckpoint.deserialize(first.last_valid_checkpoint.serialize()))
    assert all(e.representative.weight == 1 for s in resumed.steps for e in s.executions)  # [7, 8] d is fully resolved
    assert resumed.ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.UNKNOWN
    assert compare_resume(uninterrupted, first, resumed).matched


# ---- F4 / F6: cycle and extrema aggregates do not undercount or overclaim -------------------------


def _power(values, start=0):
    return OutputSeries("heater_power", "W", tuple(OutputSample(TimeWindow(R.p(start + i * HOUR), R.p(start + (i + 1) * HOUR)), Quantity(v, "W"))
                                                   for i, v in enumerate(values)), "a" * 64)


def test_f4_cycle_count_is_unknown_when_a_cycle_may_straddle_a_boundary():
    by_id = {a.aggregate_id: a for a in R.aggregations()}
    day, week = TimeWindow(R.p(0), R.p(DAY)), TimeWindow(R.p(0), R.p(7 * DAY))
    rep = RepresentativeWindow("r", day, week, Fraction(7), "leading_period", ("repeat",), "p", "x")
    duty = [6.0 if 6 <= h < 18 else 0.3 for h in range(24)]
    assert aggregate(by_id["heater_on_cycles"], [(rep, _power(duty))], week).value.magnitude == 7
    starts_on = [6.0 if h < 12 else 0.3 for h in range(24)]
    unknown = aggregate(by_id["heater_on_cycles"], [(rep, _power(starts_on))], week)
    assert unknown.status == "unknown" and "not zero cycles" in unknown.reason
    not_closed = [0.3] * 12 + [6.0] * 12
    open_rec = aggregate(by_id["heater_on_cycles"], [(rep, _power(not_closed))], week)
    assert open_rec.status == "unknown" and "does not close" in open_rec.reason
    full = RepresentativeWindow("d1", TimeWindow(R.p(DAY), R.p(2 * DAY)), TimeWindow(R.p(DAY), R.p(2 * DAY)), Fraction(1), "fully_resolved", (), "p", "x")
    first = RepresentativeWindow("d0", day, day, Fraction(1), "fully_resolved", (), "p", "x")
    two_days = aggregate(by_id["heater_on_cycles"], [(first, _power([0.3] * 12 + [6.0] * 12)), (full, _power([6.0] * 12 + [0.3] * 12, start=DAY))],
                         TimeWindow(R.p(0), R.p(2 * DAY)))
    assert two_days.value.magnitude == 1  # the on-period straddling the tile boundary is one cycle, counted once


def test_f6_extrema_of_a_repeated_window_are_unknown():
    by_id = {a.aggregate_id: a for a in R.aggregations()}
    day, week = TimeWindow(R.p(0), R.p(DAY)), TimeWindow(R.p(0), R.p(7 * DAY))
    rep = RepresentativeWindow("r", day, week, Fraction(7), "leading_period", ("repeat",), "p", "x")
    temps = OutputSeries("heater_temperature", "K", tuple(OutputSample(TimeWindow(R.p(i * HOUR), R.p((i + 1) * HOUR)), Quantity(300 + i, "K"))
                                                          for i in range(24)), "b" * 64)
    rec = aggregate(by_id["heater_temp_max"], [(rep, temps)], week)
    assert rec.status == "unknown" and rec.value is None and not rec.preserved_features


# ---- F7: fast state carried or declared, validated, bound to identity ------------------------


def _toy_hierarchy():
    return ScaleHierarchy("toy", "1", (ScaleLevel("f", "fast", Quantity(60, "s"), "toy fast"), ScaleLevel("s", "slow", Quantity(30, "day"), "toy slow")),
                          (StateOwnership("thermal", "core_temperature", "fast", "K"), StateOwnership("thermal", "moisture_content", "slow", "dimensionless")))


class _ToyFast(FastSystem):
    """Warms a core by 1 K per resolved hour from the requested fast state (a pure function of the request)."""

    def __init__(self, env):
        self.env = env
        contract = ParticipantStateContract("thermal", ("core_temperature", "moisture_content"), ("core_temperature",), "declared_complete",
                                            "toy: the next core temperature is start + resolved hours")
        self.identity = FastSystemIdentity("toy", "1", "0" * 64, {}, (("toy", "1"),), {}, (contract,), (), (("heater_temperature", "K"),),
                                           pure=True, purity_basis="closed-form function of the request")

    def execute(self, request):
        from engcore.scientific.multiphysics.receipts import StateVariableValue
        t0 = request.fast_state["thermal"]["core_temperature"].value.magnitude
        n = int((request.window.end.seconds - request.window.start.seconds) // HOUR)
        s0 = request.window.start.seconds
        series = OutputSeries("heater_temperature", "K", tuple(OutputSample(TimeWindow(R.p(s0 + i * HOUR), R.p(s0 + (i + 1) * HOUR)), Quantity(t0 + i, "K"))
                                                               for i in range(n)), "c" * 64)
        end = {"thermal": {"core_temperature": StateVariableValue("core_temperature", Quantity(t0 + n, "K"), Uncertainty.unknown("toy"))}}
        return FastExecutionResult(request.identity, ("toy",), ("d" * 64,), (series,), end, (), (), n, n, ("converged",) * n, (("toy", "1"),),
                                   consumed_environment_digest=self.env.digest, consumed_timeline_digest=self.env.timeline.digest)


def _toy_runtime(env, fast_policy, representative=R.FULLY_RESOLVED):
    policy = MacroStepPolicy("toy", "1", (AdaptationRule("default", "default", Quantity(1, "day")),), Quantity(1, "day"),
                             EventHandling.SPLIT, representative)
    lifecycle = (LifecycleBinding("thermal", LinearWetnessMoistureUptake(k_uptake=Quantity(6e-8, "1/s"), max_wet_time=Quantity(10, "day")),
                                  (InputBinding("wet_time", "wetness"),)),)
    return MultiTimescaleRuntime(run_id="toy", hierarchy=_toy_hierarchy(), policy=policy, fast_system=_ToyFast(env), environment=env,
                                 lifecycle=lifecycle, fast_state_policy=fast_policy)


def _toy_state(t=300.0):
    u = Uncertainty.unknown("declared")
    return ({"thermal": {"moisture_content": InitialStateValue("moisture_content", Quantity(0.0, "dimensionless"), u)}},
            {"thermal": {"core_temperature": InitialStateValue("core_temperature", Quantity(t, "K"), u)}})


def test_f7_fast_state_is_carried_only_when_resolved_and_declared_state_is_identity():
    env, _ = R.build_environment(4)
    slow, fast = _toy_state()
    carried = _toy_runtime(env, FastStateAtMacroStart.CARRY_RESOLVED_END).run(initial_slow_state=slow, initial_fast_state=fast)
    assert carried.status == "completed" and carried.final_fast_state["thermal"]["core_temperature"].value.magnitude == 300 + 4 * 24
    declared = _toy_runtime(env, FastStateAtMacroStart.DECLARED_INITIAL).run(initial_slow_state=slow, initial_fast_state=fast)
    assert declared.final_fast_state["thermal"]["core_temperature"].value.magnitude == 300  # the macro-end fast state is not claimed
    repeated = _toy_runtime(env, FastStateAtMacroStart.CARRY_RESOLVED_END,
                            representative=R.RepresentativePolicy("lead", "leading_period", Quantity(1, "day"), ("repeat",), "p", "x",
                                                                  periodicity_tolerances=R.REPRESENTATIVE_DAY.periodicity_tolerances))
    rt = MultiTimescaleRuntime(run_id="toy", hierarchy=repeated.hierarchy,
                               policy=MacroStepPolicy("toy", "1", (AdaptationRule("default", "default", Quantity(4, "day")),), Quantity(1, "day"),
                                                      EventHandling.SPLIT, repeated.policy.representative),
                               fast_system=repeated.fast_system, environment=env, lifecycle=repeated.lifecycle,
                               fast_state_policy=FastStateAtMacroStart.CARRY_RESOLVED_END)
    refused = rt.run(initial_slow_state=slow, initial_fast_state=fast)
    assert refused.status == "refused" and "invent a trajectory" in refused.reason
    # a resume with a different declared initial fast state is a different run identity
    first = _toy_runtime(env, FastStateAtMacroStart.DECLARED_INITIAL).run(initial_slow_state=slow, initial_fast_state=fast, until=R.p(2 * DAY))
    other = _toy_runtime(env, FastStateAtMacroStart.DECLARED_INITIAL)
    other.set_declared_fast_state(_toy_state(310.0)[1])
    with pytest.raises(ResumeRefused, match="declared_fast_state"):
        other.resume(MacroCheckpoint.deserialize(first.last_valid_checkpoint.serialize()))


# ---- F8: termination and state-change requests are acted on -----------------------------


def test_f8_termination_stops_and_an_unapplied_state_change_request_is_refused():
    term = TimelineEvent("stop-test", TimelineEventKind.TERMINATION, R.p(10 * DAY), "chamber_shutdown")
    env, _ = R.build_environment(14, extra_events=(term,))
    run = R.build_runtime(14, environment=env, near_threshold=False)[0].run(initial_slow_state=R.initial_slow())
    assert run.status == "terminated" and run.reached.seconds == 10 * DAY and run.steps[-1].window.end.seconds == 10 * DAY
    req = TimelineEvent("replace-board", TimelineEventKind.STATE_CHANGE_REQUEST, R.p(5 * DAY), "board")
    env2, _ = R.build_environment(14, extra_events=(req,))
    run2 = R.build_runtime(14, environment=env2, near_threshold=False)[0].run(initial_slow_state=R.initial_slow())
    assert run2.status == "refused" and "no declared transition authority" in run2.reason and run2.reached.seconds == 5 * DAY


# ---- F11: any failure keeps the valid checkpoints ------------------------------------------


class _Broken(R.ReferenceHeaterSystem):
    def execute(self, request):
        if request.window.start.seconds >= 7 * DAY:
            raise KeyError("provider lost a table")
        return super().execute(request)


def test_f11_a_non_scientific_failure_is_a_refusal_that_keeps_checkpoints():
    env, _ = R.build_environment(14)
    rt = R.MultiTimescaleRuntime(run_id="broken", hierarchy=R.hierarchy(), policy=R.policy(near_threshold=False), fast_system=_Broken(env),
                                 environment=env, aggregations=R.aggregations(), lifecycle=R.lifecycle())
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status == "refused" and "KeyError" in run.reason and len(run.checkpoints) == 1
    assert run.last_valid_checkpoint.at.seconds == 7 * DAY


# ---- re-review: N1-N5 and the fixes that lacked a test ---------------------------------


def test_n1_repetition_is_compared_at_both_periods_change_points():
    # resolved day: 10 V (0-12 h) then 2 V (12-24 h); the repeated days are ONE long 10 V entry
    from engcore.multiscale.runtime import RepresentativityRejected
    from engcore.scenarios import HistoryEntry, NamedQuantity, QuantityHistory
    env, _ = R.build_environment(3)
    rt, _, _ = R.build_runtime(3, environment=env, near_threshold=False, default_days=3)

    def v(a, b, x):
        return HistoryEntry(TimeWindow(R.p(a * HOUR), R.p(b * HOUR)), NamedQuantity("supply_voltage", Quantity(x, "V")))

    history = QuantityHistory("supply", "usage", "supply_voltage", "V", (v(0, 12, 10.0), v(12, 24, 2.0), v(24, 72, 10.0)))
    rep = R.REPRESENTATIVE_DAY.build(TimeWindow(R.p(0), R.p(3 * DAY)), "m")[0]
    rt._input_histories = lambda: iter([("supply", "usage", history)])
    with pytest.raises(RepresentativityRejected, match="supply"):
        rt._measure_representativity(rep)


def test_n2_and_f1_unmeasurable_or_undeclared_inputs_refuse_repetition():
    from engcore.scenarios import CycleHistory, CycleRecord, EnvironmentTimeline, Timeline
    env, _ = R.build_environment(7)
    partial = R.RepresentativePolicy("lead", "leading_period", Quantity(1, "day"), ("repeat",), "p", "x",
                                     periodicity_tolerances=(("air_temperature", Quantity(2, "K")),))
    with pytest.raises(Exception, match="periodicity tolerance"):
        R.MultiTimescaleRuntime(run_id="x", hierarchy=R.hierarchy(), environment=env, aggregations=R.aggregations(), lifecycle=R.lifecycle(),
                                fast_system=R.ReferenceHeaterSystem(env), policy=R.policy(representative=partial))
    tl = env.timeline
    cycles = CycleHistory("door", "door_open", (CycleRecord("c0", 0, TimeWindow(R.p(0), R.p(HOUR))),))
    tl2 = Timeline(tl.timeline_id, tl.basis, tl.horizon, tl.scenario_digest, tl.events, tl.histories, (cycles,))
    env2 = EnvironmentTimeline(env.environment_id, tl2, env.registry, env.sources, env.channels)
    with pytest.raises(Exception, match="cannot yet be compared"):
        R.build_runtime(7, environment=env2)


def test_n3_forged_checkpoint_accounting_never_upgrades_the_ledger():
    from dataclasses import replace
    kw = dict(near_threshold=False, default_days=1, representative=R.FULLY_RESOLVED)
    first = R.build_runtime(8, **kw)[0].run(initial_slow_state=R.initial_slow(), until=R.p(4 * DAY))
    cp = first.last_valid_checkpoint
    assert first.ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.NOT_APPLICABLE
    resumed = R.build_runtime(8, **kw)[0].resume(cp)
    assert resumed.ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.UNKNOWN  # attested only by the checkpoint
    with pytest.raises(ResumeRefused, match="counters"):
        R.build_runtime(8, **kw)[0].resume(replace(cp, accounting={k: v for k, v in cp.accounting.items() if k != "repeated_windows"}))


def test_n4_events_at_the_horizon_end_still_act():
    req = TimelineEvent("late-request", TimelineEventKind.STATE_CHANGE_REQUEST, R.p(7 * DAY), "board")
    env, _ = R.build_environment(7, extra_events=(req,))
    run = R.build_runtime(7, environment=env, near_threshold=False)[0].run(initial_slow_state=R.initial_slow())
    assert run.status == "refused" and "horizon end" in run.reason


class _Impure(R.ReferenceHeaterSystem):
    def __init__(self, env, **kw):
        super().__init__(env, **kw)
        from dataclasses import replace
        self.identity = replace(self.identity, pure=False, purity_basis="")


class _OtherEnv(R.ReferenceHeaterSystem):
    def execute(self, request):
        from dataclasses import replace
        return replace(super().execute(request), consumed_environment_digest="0" * 64)


def test_f10_reuse_needs_declared_purity_and_the_consumed_environment_must_match():
    limits = (R.StateChangeLimit("thermal", "moisture_content", Quantity(0.10, "dimensionless"), 0.05),
              R.StateChangeLimit("electrical", "resistance_drift", Quantity(0.10, "dimensionless"), 5.0))
    rt, system, _ = R.build_runtime(14, near_threshold=False, limits=limits, system_cls=_Impure)
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.accounting["rejections"] >= 1 and run.accounting["cache_reuses"] == 0
    assert system.executions == run.accounting["fast_executions"]
    other = R.build_runtime(7, near_threshold=False, system_cls=_OtherEnv)[0].run(initial_slow_state=R.initial_slow())
    assert other.status == "refused" and "different environment" in other.reason


def test_f9_a_caller_mapping_is_not_a_physics_aggregate():
    from types import SimpleNamespace
    from engcore.scenarios import evaluate_degradation_step
    from engcore.scientific.multiphysics.receipts import StateVariableValue
    env, _ = R.build_environment(7)
    lb = R.lifecycle()[1]
    week = TimeWindow(R.p(0), R.p(7 * DAY))
    fake = SimpleNamespace(aggregate_id="heater_teq", quantity_id="heater_temperature",
                           form_key="domain_defined:electrical.arrhenius_equivalent_time", preserved_features={"dwell"}, represented=week,
                           named_value=lambda i: None, classification="derived_aggregate_not_measurement", digest="Z" * 64, reason="")
    prior = (StateVariableValue("resistance_drift", Quantity(0, "dimensionless"), Uncertainty.unknown("x")),)
    with pytest.raises(Exception, match="not a digest-bound derived physics-aggregate"):
        evaluate_degradation_step(lb.model, environment=env, window=week, participant_id="electrical", prior_values=prior,
                                  prior_state_digest="a" * 64, bindings=lb.bindings, run_id="x", run_digest_value="b" * 64,
                                  aggregates={"heater_teq": fake})


def test_f12_min_extrema_compress_with_their_statistic_and_f13_out_of_range_temperature_is_unknown():
    from engcore.multiscale import AggregationSpec, compress_history
    from engcore.scenarios import AggregateForm
    spec = AggregationSpec("tmin", "heater_temperature", AggregateForm.EXTREMA, statistic="min")
    recs = []
    for d, base in ((0, 300.0), (1, 290.0)):
        w = TimeWindow(R.p(d * DAY), R.p((d + 1) * DAY))
        rep = RepresentativeWindow(f"r{d}", w, w, Fraction(1), "fully_resolved", (), "p", "x")
        series = OutputSeries("heater_temperature", "K", tuple(
            OutputSample(TimeWindow(R.p(d * DAY + i * HOUR), R.p(d * DAY + (i + 1) * HOUR)), Quantity(base + i, "K")) for i in range(24)), "e" * 64)
        recs.append(aggregate(spec, [(rep, series)], w))
    assert compress_history("tmin", recs).value.magnitude == 290.0
    day = TimeWindow(R.p(0), R.p(DAY))
    rep = RepresentativeWindow("h", day, day, Fraction(1), "fully_resolved", (), "p", "x")
    hot = OutputSeries("heater_temperature", "K", tuple(OutputSample(TimeWindow(R.p(i * HOUR), R.p((i + 1) * HOUR)), Quantity(500.0, "K"))
                                                        for i in range(24)), "f" * 64)
    teq = aggregate(next(a for a in R.aggregations() if a.aggregate_id == "heater_teq"), [(rep, hot)], day)
    assert teq.status == "unknown" and "outside the declared Arrhenius range" in teq.reason


def test_f14_resume_under_another_run_id_is_refused():
    first = R.build_runtime(14, near_threshold=False)[0].run(initial_slow_state=R.initial_slow(), until=R.p(7 * DAY))
    other, _, _ = R.build_runtime(14, near_threshold=False, run_id="someone-else")
    with pytest.raises(ResumeRefused, match="belongs to run"):
        other.resume(first.last_valid_checkpoint)
