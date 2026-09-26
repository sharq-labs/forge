"""BIG 10 multi-timescale runtime: executable proofs A-E (lumped + SciPy fast system) and adversarial tests.

The fast physics is a REAL BIG 9 ``MultiphysicsRuntime`` implicit coupling of a
BIG 6 dense-LU thermal network with a BIG 6 SciPy-root heater circuit; the
FEniCSx fast window (proof F) lives in ``providers/fenicsx/tests``.  Nothing
here is validation: comparisons are against a more temporally resolved
NUMERICAL reference, and resume agreement is reproducibility.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import replace
from fractions import Fraction

import pytest

from engcore.coupling import ParticipantStateContract, StateCompleteness, provider_participant, scalar_port
from engcore.coupling.adapters import CouplingRefusal
from engcore.data import InMemoryBulkStore
from engcore.domains.electrical.resistance_drift import MeanTemperatureDrift
from engcore.execution.multiphysics import AdvanceRequest, InitialStateDefinition, InitialStateValue
from engcore.multiscale import (
    AggregationSpec, ApproximationStatus, ComponentStatus, ErrorComponent, MacroCheckpoint, MultiTimescaleRuntime,
    OutputSample, OutputSeries, ReferenceDiscrepancy, RepresentativeWindow, ResumeRefused, ScaleHierarchy, ScaleLevel,
    StateChangeLimit, StateOwnership, aggregate, compare_resume, compress_history,
)
from engcore.scenarios import AggregateForm, AggregateRequirement, HistoryFeature, StepStatus, TimePoint, TimeWindow
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import ParticipantSpec
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("multiscale_reference", str(HERE / "multiscale_reference.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

DAY, HOUR = R.DAY, R.HOUR
CHANGE_HOUR = 30 * 24 + 12  # declared chamber program change at day 30.5


def _slow(record_state, pid, var):
    return record_state[pid][var].value.magnitude


@pytest.fixture(scope="module")
def long_run():
    runtime, system, env = R.build_runtime(63, change_at_hour=CHANGE_HOUR)
    return runtime, system, env, runtime.run(initial_slow_state=R.initial_slow())


# ---- Proof B: long horizon, feed-forward, no brute force ------------------------------------


def test_proof_b_long_horizon_changes_state_and_future_physics_without_brute_force(long_run):
    runtime, system, env, run = long_run
    assert run.status == "completed", run.reason
    acc = run.accounting
    represented, resolved = Fraction(acc["represented_seconds"]), Fraction(acc["resolved_seconds"])
    assert represented == 63 * DAY and resolved < represented / 3  # not brute force
    assert acc["coupled_solve_windows"] == int(Fraction(acc["executed_fast_seconds"]) / HOUR)
    # slow state moved, only through APPLIED degradation steps
    assert _slow(run.final_slow_state, "thermal", "moisture_content") > 0.05
    assert _slow(run.final_slow_state, "electrical", "resistance_drift") > 0.1
    assert all(d.status is StepStatus.APPLIED for s in run.steps for d in s.degradation)
    # each macro window's fast physics resolved the board at THAT window's moisture (BIG 5 re-resolution)
    ks = []
    for step in run.steps:
        m = step.slow_before["thermal"]["moisture_content"].value.magnitude
        props = step.executions[0].resolved_properties
        # re-resolved at every solved temperature bound; the (temperature-independent) data give one value
        assert props and len({p["value_W_mK"] for p in props}) == 1 and len({p["state_digest"] for p in props}) > 1
        ks.append((m, props[0]["value_W_mK"], props[0]["derivation"]))
    assert ks[0][0] == 0.0 and ks[0][2] == "sourced" and ks[-1][2] == "interpolated"
    assert all(a[1] < b[1] for a, b in zip(ks, ks[1:]))  # wetter board -> higher conductivity, every window
    # physics(day N) != physics(day 0) BECAUSE accumulated state changed: same day-0 window, same
    # environment and usage, only the slow state differs (a controlled counterfactual execution)
    first = run.steps[0].executions[0].representative.resolved
    from engcore.multiscale import FastExecutionRequest
    def request(slow):
        return FastExecutionRequest("cf", system.identity.digest, env.timeline.scenario_digest, env.timeline.digest, env.digest,
                                    first, slow, {}, runtime._environment_context(first), runtime._usage_context(first))
    day0 = system.execute(request(run.steps[0].slow_before)).series_for("heater_temperature")
    dayN = system.execute(request(run.final_slow_state)).series_for("heater_temperature")
    on_hours = [i for i in range(24) if 6 <= i < 18]
    assert all(dayN.samples[i].value.magnitude < day0.samples[i].value.magnitude - 1.0 for i in on_hours)


def test_proof_b_records_adaptation_event_split_threshold_and_accounting(long_run):
    runtime, system, env, run = long_run
    sizes = [(float(s.window.start.seconds) / DAY, float(s.window.end.seconds - s.window.start.seconds) / DAY) for s in run.steps]
    # event refinement: a macro window ends exactly at the declared program change (day 30.5)
    assert any(abs(start + size - 30.5) < 1e-12 for start, size in sizes)
    splits = [r for s in run.steps for r in s.refinements if r.kind == "event_split"]
    assert splits and splits[0].subject == "program-change" and run.accounting["event_splits"] >= 1
    # adaptation: explicit, recorded decisions (7-day default -> 2-day near the moisture breakpoint -> back)
    decisions = [s.adaptation for s in run.steps if s.adaptation is not None]
    assert decisions[0].old_seconds is None and decisions[0].rule_id == "default"
    near = [d for d in decisions if d.rule_id == "near-moisture-breakpoint"]
    assert near and near[0].new_seconds == 2 * DAY and near[0].policy_digest == runtime.policy.digest and "threshold" in near[0].reason
    assert run.accounting["adaptation_changes"] >= 2
    # the moisture breakpoint crossing happened inside a window no longer than the declared localization
    crossing = [s for s in run.steps if "moisture-breakpoint" in s.threshold_crossings]
    assert len(crossing) == 1 and crossing[0].represented_seconds <= 2 * DAY
    # every accepted step has a checkpoint; representative contracts are declared approximations
    assert len(run.checkpoints) == len(run.steps)
    reps = [e.representative for s in run.steps for e in s.executions]
    assert any(r.status is ApproximationStatus.DECLARED_APPROXIMATION for r in reps)
    assert all(r.weight * (r.resolved.end.seconds - r.resolved.start.seconds) == r.represented.end.seconds - r.represented.start.seconds for r in reps)
    ledger = run.ledger
    assert ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.UNKNOWN
    assert ledger.entry(ErrorComponent.MODEL_DISCREPANCY).status is ComponentStatus.UNKNOWN
    assert ledger.entry(ErrorComponent.MAPPING).status is ComponentStatus.NOT_APPLICABLE
    assert all(e.bound is None for e in ledger.entries)  # nothing quantified is invented


# ---- Proof A: more temporally resolved numerical reference vs multi-timescale ------------------


def test_proof_a_resolved_reference_vs_multiscale_72h_discrepancy_is_recorded_not_validation():
    env, _ = R.build_environment(3)
    ref_rt, _, _ = R.build_runtime(3, environment=env, default_days=1, representative=R.FULLY_RESOLVED, near_threshold=False, run_id="ref-72h")
    ms_rt, _, _ = R.build_runtime(3, environment=env, default_days=3, near_threshold=False, run_id="ms-72h")
    ref = ref_rt.run(initial_slow_state=R.initial_slow())
    ms = ms_rt.run(initial_slow_state=R.initial_slow())
    assert ref.status == ms.status == "completed"
    assert Fraction(ref.accounting["resolved_seconds"]) == 3 * DAY and Fraction(ms.accounting["resolved_seconds"]) == DAY
    assert ref.ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.NOT_APPLICABLE
    assert ms.ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.UNKNOWN
    scope = f"scenario {env.timeline.scenario_digest[:12]}, horizon 72 h, lumped fast system"
    ledger = ms.ledger
    for pid, var in (("thermal", "moisture_content"), ("electrical", "resistance_drift")):
        obs = ReferenceDiscrepancy(f"{pid}.{var}", ref.final_slow_state[pid][var].value, ms.final_slow_state[pid][var].value, scope)
        ledger = ledger.with_observation(obs)
    drift = ledger.observations[1]
    # Two effects the representative run cannot see, recorded rather than predicted: (i) the declared
    # 0.25 K/day upper-temperature rise is invisible to a repeated first day; (ii) drift is held fixed
    # for 72 h, missing the daily feed-forward (more drift -> less power -> slower aging).  Observed
    # here: (ii) dominates and the representative run over-ages by ~2 %.  One observation, not a bound.
    assert drift.relative is not None and 0 < drift.relative < 0.1
    assert drift.multiscale_value.magnitude > drift.reference_value.magnitude
    assert ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.UNKNOWN
    assert ledger.to_dict()["observations"][0]["classification"].endswith("not_validation")
    # environment-driven moisture is integrated from the full BIG 3 history in both: identical
    assert ledger.observations[0].absolute == 0.0


# ---- Proof C: event refinement ----------------------------------------------------------


def test_proof_c_event_inside_macro_window_is_split_or_refused():
    rt, _, _ = R.build_runtime(14, change_at_hour=4 * 24 + 7, near_threshold=False)
    run = rt.run(initial_slow_state=R.initial_slow())
    ends = [s.window.end.seconds for s in run.steps]
    assert (4 * 24 + 7) * HOUR in ends  # the window ends exactly at the event, never smooths across it
    refused_rt, _, _ = R.build_runtime(14, change_at_hour=4 * 24 + 7, near_threshold=False, event_handling="refuse")
    refused = refused_rt.run(initial_slow_state=R.initial_slow())
    assert refused.status == "refused" and "program-change" in refused.reason and not refused.steps and not refused.checkpoints


# ---- Proof D: aggregation refusal -----------------------------------------------------


def test_proof_d_mean_only_history_is_refused_by_a_dwell_requiring_model():
    env, _ = R.build_environment(7)
    system = R.ReferenceHeaterSystem(env)
    lifecycle = R.lifecycle(drift_model=MeanTemperatureDrift(k_drift=Quantity(5.6e-9, "1/s"), max_equivalent_time=Quantity(3e7, "s")),
                            drift_aggregate="heater_temp_mean")
    rt = MultiTimescaleRuntime(run_id="mean-only", hierarchy=R.hierarchy(), policy=R.policy(near_threshold=False), fast_system=system,
                               environment=env, aggregations=R.aggregations(), lifecycle=lifecycle)
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status == "stopped" and not run.steps and not run.checkpoints
    assert "insufficient_history" in run.reason and "dwell" in run.reason
    assert _slow(run.final_slow_state, "electrical", "resistance_drift") == 0.0  # no guessed degradation


def test_domain_aggregator_refuses_a_source_series_that_is_itself_only_a_mean():
    w = TimeWindow(R.p(0), R.p(DAY))
    rep = RepresentativeWindow("r", w, w, Fraction(1), "fully_resolved", (), "test", "exact")
    mean_only = OutputSeries("heater_temperature", "K", (OutputSample(w, Quantity(400, "K")),), "a" * 64,
                             resolution="a single time-weighted mean", preserved_features=frozenset({HistoryFeature.MEAN}))
    spec = next(a for a in R.aggregations() if a.aggregate_id == "heater_teq")
    rec = aggregate(spec, [(rep, mean_only)], w)
    assert rec.status == "unknown" and rec.value is None and "dwell" in rec.reason
    requirement = AggregateRequirement("x", (AggregateForm.HISTOGRAM.value,), (HistoryFeature.ORDER,))
    hist = aggregate(next(a for a in R.aggregations() if a.aggregate_id == "heater_temp_histogram"),
                     [(rep, OutputSeries("heater_temperature", "K", (OutputSample(w, Quantity(400, "K")),), "b" * 64))], w)
    assert "order" in requirement.admit(hist)  # a sequence-dependent model must not run on a histogram


# ---- Proof E: checkpoint -> serialize -> restore in a FRESH process -> continue ----------------


RESUME_SCRIPT = r"""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("R", sys.argv[1]); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
from engcore.multiscale import MacroCheckpoint
from engcore.multiscale.checkpoint import state_to_list
payload = json.load(open(sys.argv[2]))
rt, _, _ = R.build_runtime(28, change_at_hour=int(sys.argv[4]))
run = rt.resume(MacroCheckpoint.deserialize(payload))
json.dump({"status": run.status, "resumed_from": run.resumed_from, "steps": [s.digest for s in run.steps],
           "final": state_to_list(run.final_slow_state), "accounting": run.accounting, "digest": run.digest}, open(sys.argv[3], "w"))
"""


def test_proof_e_checkpoint_resume_in_a_fresh_process_matches_uninterrupted(tmp_path):
    from engcore.multiscale.checkpoint import state_to_list
    change = 17 * 24 + 12
    full_rt, _, _ = R.build_runtime(28, change_at_hour=change)
    uninterrupted = full_rt.run(initial_slow_state=R.initial_slow())
    first_rt, _, _ = R.build_runtime(28, change_at_hour=change)
    first = first_rt.run(initial_slow_state=R.initial_slow(), until=R.p(12 * DAY))
    assert first.status == "paused" and 0 < len(first.steps) < len(uninterrupted.steps)
    payload = json.loads(json.dumps(first.last_valid_checkpoint.serialize()))  # real serialization boundary
    # (1) fresh runtime objects in this process: the checkpoint is used for continuation
    second_rt, _, _ = R.build_runtime(28, change_at_hour=change)
    resumed = second_rt.resume(MacroCheckpoint.deserialize(payload))
    comparison = compare_resume(uninterrupted, first, resumed)
    assert comparison.matched, comparison.first_mismatch
    assert comparison.to_dict()["classification"] == "reproducibility_not_validation"
    # (2) a separate OS process restores from the file and continues
    cp_file, out_file = tmp_path / "cp.json", tmp_path / "out.json"
    cp_file.write_text(json.dumps(payload))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(HERE.parent / "src"), str(HERE.parent)]))
    proc = subprocess.run([sys.executable, "-c", RESUME_SCRIPT, str(HERE / "multiscale_reference.py"), str(cp_file), str(out_file), str(change)],
                          env=env, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-3000:]
    other = json.loads(out_file.read_text())
    assert other["resumed_from"] == first.last_valid_checkpoint.digest
    assert [s.digest for s in first.steps] + other["steps"] == [s.digest for s in uninterrupted.steps]
    assert other["accounting"] == uninterrupted.accounting
    assert other["digest"] == resumed.digest
    assert other["final"] == state_to_list(resumed.final_slow_state) == state_to_list(uninterrupted.final_slow_state)


def test_resume_is_refused_for_tampered_foreign_or_incomplete_checkpoints():
    rt, _, _ = R.build_runtime(14, near_threshold=False)
    first = rt.run(initial_slow_state=R.initial_slow(), until=R.p(7 * DAY))
    payload = first.last_valid_checkpoint.serialize()
    tampered = json.loads(json.dumps(payload))
    tampered["checkpoint"]["slow_state"][0]["value"]["value"]["magnitude"] = 0.5
    with pytest.raises(InvalidScientificProblem, match="altered|re-serialize"):
        MacroCheckpoint.deserialize(tampered)
    other_rt, _, _ = R.build_runtime(14, near_threshold=False, version="2")  # different policy identity
    with pytest.raises(ResumeRefused, match="policy"):
        other_rt.resume(MacroCheckpoint.deserialize(payload))
    incomplete_rt, _, _ = R.build_runtime(14, near_threshold=False, system_kwargs={"completeness": StateCompleteness.NOT_ESTABLISHED})
    run = incomplete_rt.run(initial_slow_state=R.initial_slow(), until=R.p(7 * DAY))
    assert run.status == "paused"  # normal execution may continue ...
    cp = run.last_valid_checkpoint
    assert not cp.resumable and "NOT_ESTABLISHED" in cp.resumable_reason
    with pytest.raises(ResumeRefused, match="NOT_ESTABLISHED"):  # ... but resume/replay claims are refused
        incomplete_rt.resume(MacroCheckpoint.deserialize(cp.serialize()))


def test_failed_macro_step_keeps_the_previous_valid_checkpoint():
    rt, system, _ = R.build_runtime(21, near_threshold=False, system_kwargs={"fail_after_s": 14 * DAY})
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status == "refused" and "declared participant failure" in run.reason
    assert len(run.steps) == 2 and run.last_valid_checkpoint.at.seconds == 14 * DAY
    assert run.last_valid_checkpoint.chain_digest == run.steps[-1].digest


# ---- identity, reuse, limits, materials ---------------------------------------------------


def test_one_representative_weight_or_the_hierarchy_changes_run_identity():
    rt, _, _ = R.build_runtime(14, near_threshold=False)
    a = rt.run(initial_slow_state=R.initial_slow())
    step = a.steps[0]
    rep = step.executions[0].representative
    shifted = RepresentativeWindow(rep.window_id, TimeWindow(rep.resolved.start, R.p(2 * DAY)), rep.represented, Fraction(7, 2),
                                   rep.selection, rep.assumptions, rep.applicability, rep.aggregation_semantics)
    changed = replace(step, executions=(replace(step.executions[0], representative=shifted),))
    assert changed.digest != step.digest
    b_rt, _, _ = R.build_runtime(14, near_threshold=False, default_days=2)
    assert b_rt.run(initial_slow_state=R.initial_slow()).digest != a.digest
    h2 = R.hierarchy(version="2")
    assert h2.digest != R.hierarchy().digest
    c = MultiTimescaleRuntime(run_id=rt.run_id, hierarchy=h2, policy=rt.policy, fast_system=rt.fast_system, environment=rt.environment,
                              aggregations=rt.aggregations, lifecycle=rt.lifecycle)
    assert c.identities()["hierarchy"] != rt.identities()["hierarchy"]


def test_exact_reuse_only_for_identical_requests_and_state_change_limit_refines():
    limits = (StateChangeLimit("thermal", "moisture_content", Quantity(0.10, "dimensionless"), 0.05),
              StateChangeLimit("electrical", "resistance_drift", Quantity(0.10, "dimensionless"), 5.0))
    rt, system, _ = R.build_runtime(14, near_threshold=False, limits=limits)
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status == "completed"
    rejected = [r for s in run.steps for r in s.refinements if r.kind == "state_change_rejected"]
    assert rejected and "scale 0.1" in rejected[0].detail  # explicit normalization, never a default of 1
    # a 7-day step moves moisture ~0.009 (0.09 of scale) > 0.05 -> refined to 3.5 days, whose leading
    # day is the SAME request as the rejected attempt's: reused exactly, not recomputed
    assert run.accounting["rejections"] >= 1 and run.accounting["cache_reuses"] >= 1
    assert system.executions == run.accounting["fast_executions"]
    with pytest.raises(InvalidScientificProblem, match="normalization"):
        StateChangeLimit("thermal", "moisture_content", Quantity(0, "dimensionless"), 0.1)


def test_stale_material_resolution_is_refused():
    rt, _, _ = R.build_runtime(14, near_threshold=False, system_kwargs={"stale_material": True})
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status == "refused" and "stale" in run.reason and len(run.steps) == 1


def test_unknown_environment_stops_the_run_instead_of_assuming_zero_exposure():
    env, _ = R.build_environment(14, gap_hours=range(9 * 24, 9 * 24 + 3))
    rt, _, _ = R.build_runtime(14, environment=env, near_threshold=False)
    run = rt.run(initial_slow_state=R.initial_slow())
    assert run.status in ("stopped", "refused") and len(run.steps) == 1
    assert run.final_slow_state == run.steps[0].slow_after


def test_fast_solver_may_not_mutate_slow_state():
    env, _ = R.build_environment(7)
    system = R.ReferenceHeaterSystem(env)
    evolving = ParticipantStateContract("thermal", ("moisture_content",), ("moisture_content",), "declared_complete", R.COMPLETE)
    system.identity = replace(system.identity, contracts=(system.identity.contract("electrical"), evolving))
    with pytest.raises(InvalidScientificProblem, match="must not mutate slow"):
        MultiTimescaleRuntime(run_id="bad", hierarchy=R.hierarchy(), policy=R.policy(), fast_system=system, environment=env,
                              aggregations=R.aggregations(), lifecycle=R.lifecycle())


# ---- B10-1: participant adapter state progression -----------------------------------------


def _adapter(evolved=(), returns_next=None, contract=None):
    spec = ParticipantSpec("p", "m", "1", "r", "1", "s", "1", "a", "1",
                           (scalar_port("f", "input", "temperature", "K"), scalar_port("x", "output", "temperature", "K")),
                           transient=True, checkpointable=True, deterministic_restore=True)

    class Rec:
        succeeded, reason, execution_identity, digest = True, "", "e", "d"

    def solve(inputs, start, end, uq, state):
        nxt = returns_next(state) if returns_next else {}
        return (Rec(), {"x": inputs["f"]}, nxt) if returns_next else (Rec(), {"x": inputs["f"]})

    defs = (InitialStateDefinition("fast_t", "K"), InitialStateDefinition("slow_m", "dimensionless"))
    return provider_participant(spec, solve=solve, initial_outputs=lambda: {"x": Quantity(0, "K")}, store=InMemoryBulkStore(),
                                state_definitions=defs, evolved_state=evolved, state_contract=contract)


def _init(participant, fast_uq="unknown"):
    u = Uncertainty.unknown("x")
    state = {"fast_t": InitialStateValue("fast_t", Quantity(300, "K"), u), "slow_m": InitialStateValue("slow_m", Quantity(0.1, "dimensionless"), u)}
    participant.initialize_state(Quantity(0, "s"), state, {}, {})
    return state


def _advance(participant):
    return participant.advance(AdvanceRequest(Quantity(0, "s"), Quantity(1, "s"), {"f": Quantity(1, "K")},
                                              {"f": Uncertainty.unknown("x")}, Quantity(1, "s")))


def test_adapter_advances_declared_fast_state_and_refuses_slow_state_mutation():
    p = _adapter(evolved=("fast_t",), returns_next=lambda s: {"fast_t": Quantity(s["fast_t"].value.magnitude + 5, "K")})
    _init(p)
    before = p.state_identity(Quantity(0, "s"))
    cp = p.checkpoint(Quantity(0, "s"))
    _advance(p)
    after = p.state_identity(Quantity(1, "s"))
    assert before != after
    published = {v.variable_id: v.value.magnitude for v in p.public_state(Quantity(1, "s"))}
    assert published == {"fast_t": 305, "slow_m": 0.1}
    p.restore(cp)
    assert p.state_identity(Quantity(0, "s")) == before
    assert p.state_contract.completeness is StateCompleteness.NOT_ESTABLISHED  # nothing was declared
    bad = _adapter(evolved=("fast_t",), returns_next=lambda s: {"fast_t": Quantity(1, "K"), "slow_m": Quantity(0.9, "dimensionless")})
    _init(bad)
    with pytest.raises(CouplingRefusal, match="only an explicit state transition"):
        _advance(bad)
    omitted = _adapter(evolved=("fast_t",), returns_next=lambda s: {})
    _init(omitted)
    with pytest.raises(CouplingRefusal, match="omitted evolved state"):
        _advance(omitted)


def test_adapter_state_digest_covers_uncertainty():
    p = _adapter()
    _init(p)
    a = p.state_identity(Quantity(0, "s"))
    u = Uncertainty.unknown("a different statement")
    p.initialize_state(Quantity(0, "s"), {"fast_t": InitialStateValue("fast_t", Quantity(300, "K"), u),
                                          "slow_m": InitialStateValue("slow_m", Quantity(0.1, "dimensionless"), u)}, {}, {})
    assert p.state_identity(Quantity(0, "s")) != a


# ---- aggregation / compression unit semantics ---------------------------------------------


def _series(values, *, start=0, step=HOUR):
    samples = tuple(OutputSample(TimeWindow(R.p(start + i * step), R.p(start + (i + 1) * step)), Quantity(v, "K")) for i, v in enumerate(values))
    return OutputSeries("heater_temperature", "K", samples, "c" * 64)


def test_aggregation_states_information_loss_repetition_and_gaps():
    day = TimeWindow(R.p(0), R.p(DAY))
    week = TimeWindow(R.p(0), R.p(7 * DAY))
    rep = RepresentativeWindow("r", day, week, Fraction(7), "leading_period", ("repeat",), "periodic", "extensive x weight")
    series = _series([300 + 100 * (6 <= h < 18) for h in range(24)])
    by_id = {a.aggregate_id: a for a in R.aggregations()}
    mean = aggregate(by_id["heater_temp_mean"], [(rep, series)], week)
    assert mean.value.magnitude == pytest.approx(350.0) and mean.preserved_features == {"mean"} and mean.assumption_dependent
    extrema = aggregate(by_id["heater_temp_max"], [(rep, series)], week)
    assert extrema.status == "unknown" and not extrema.preserved_features  # other days were not resolved
    dwell = aggregate(by_id["heater_hot_dwell"], [(rep, series)], week)
    assert dwell.value.magnitude == pytest.approx(7 * 12 * HOUR)
    frac = RepresentativeWindow("r", day, TimeWindow(R.p(0), R.p(DAY * 5 // 2)), Fraction(5, 2), "leading_period", ("repeat",), "p", "x")
    power = OutputSeries("heater_power", "W", tuple(OutputSample(s.window, Quantity(6 if s.value.magnitude > 350 else 0.3, "W")) for s in series.samples), "d" * 64)
    cycles = aggregate(by_id["heater_on_cycles"], [(frac, power)], frac.represented)
    assert cycles.status == "unknown" and "fractional" in cycles.reason  # 2.5 cycles are not declared
    gappy = OutputSeries("heater_temperature", "K", series.samples[:10] + series.samples[11:], "e" * 64)
    missing = aggregate(by_id["heater_temp_mean"], [(rep, gappy)], week)
    assert missing.status == "unknown" and "not zero" in missing.reason
    affine = AggregationSpec("dose_degC", "heater_temperature", AggregateForm.INTEGRAL_DOSE)
    celsius = OutputSeries("heater_temperature", "degC", tuple(OutputSample(s.window, Quantity(20, "degC")) for s in series.samples), "f" * 64)
    assert aggregate(affine, [(rep, celsius)], week).status == "unknown"
    # compression: derived, contiguous only, never gains features, UNKNOWN propagates
    second = TimeWindow(R.p(7 * DAY), R.p(14 * DAY))
    rep2 = RepresentativeWindow("r2", TimeWindow(R.p(7 * DAY), R.p(8 * DAY)), second, Fraction(7), "leading_period", ("repeat",), "p", "x")
    dose2 = aggregate(by_id["heater_hot_dwell"], [(rep2, _series([400] * 24, start=7 * DAY))], second)
    compressed = compress_history("hot-dwell-2w", [dwell, dose2])
    assert compressed.value.magnitude == pytest.approx(dwell.value.magnitude + dose2.value.magnitude)
    assert compressed.to_dict()["classification"] == "compressed_derived_history_not_measurement"
    assert set(compressed.preserved) <= dwell.preserved_features and compressed.uncertainty.kind.value == "unknown"
    with pytest.raises(InvalidScientificProblem, match="contiguous"):
        compress_history("gap", [dwell, replace(dose2, represented=TimeWindow(R.p(8 * DAY), R.p(15 * DAY)))])
    mean2_gappy = aggregate(by_id["heater_temp_mean"], [(rep2, OutputSeries("heater_temperature", "K", _series([400] * 24, start=7 * DAY).samples[1:], "g" * 64))], second)
    assert mean2_gappy.status == "unknown"
    assert compress_history("with-unknown", [mean, mean2_gappy]).status == "unknown"
    with pytest.raises(InvalidScientificProblem, match="ONE aggregation spec"):
        compress_history("mixed", [dwell, replace(dose2, spec_digest="0" * 64)])


def test_representative_window_and_hierarchy_contracts_are_explicit():
    day = TimeWindow(R.p(0), R.p(DAY))
    with pytest.raises(InvalidScientificProblem, match="exactly"):
        RepresentativeWindow("r", day, TimeWindow(R.p(0), R.p(7 * DAY)), Fraction(365), "leading_period", ("x",), "p", "s")
    with pytest.raises(InvalidScientificProblem, match="assumptions"):
        RepresentativeWindow("r", day, TimeWindow(R.p(0), R.p(7 * DAY)), Fraction(7), "leading_period", (), "p", "s")
    with pytest.raises(InvalidScientificProblem, match="not faster"):
        ScaleHierarchy("h", "1", (ScaleLevel("f", "fast", Quantity(2, "day"), "x"), ScaleLevel("s", "slow", Quantity(1, "day"), "y")), ())
    with pytest.raises(InvalidScientificProblem, match="FAST or the SLOW"):
        StateOwnership("p", "v", "operational", "K")
